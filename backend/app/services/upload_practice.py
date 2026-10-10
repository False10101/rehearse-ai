from __future__ import annotations

import json
import logging
import math
import re
import shutil
import subprocess
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any

import cv2
import requests
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Job, UploadPracticeSession
from app.db.session import get_session_factory
from app.services.gesture_evidence import MovementTracker, save_gesture_clips
from app.services.pose_coverage import PoseCoverage
from app.services.speech_evidence import coach_speech_moments, save_audio_excerpts, speech_moments
from app.services.storage import storage_path, upload_practice_evidence_key

logger = logging.getLogger(__name__)

GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
RELIABLE_FILLER_PHRASES = (
    "um",
    "uh",
    "erm",
    "hmm",
    "you know",
    "i mean",
)
CONTEXTUAL_FILLER_PHRASES = (
    "like",
    "sort of",
    "kind of",
    "basically",
    "actually",
)
POSE_LABELS = {
    "repeated_head_movement": "Repeated head movement",
    "repeated_swaying": "Repeated torso swaying",
    "hand_near_face": "Hand near face",
    "hands_clasped_low": "Hands clasped low",
    "arms_crossed": "Arms crossed",
    "gesture_box_excursion": "Arms extended too wide",
}
POSE_FEEDBACK = {
    "repeated_head_movement": (
        "Repeated head turns or sideways tilts were estimated in this excerpt. Review whether they supported "
        "audience contact or competed with your explanation. Try settling briefly between points; "
        "natural glances and nods are appropriate. This is a movement estimate, not eye tracking."
    ),
    "repeated_swaying": (
        "Review whether the side-to-side movement was intentional. If it competed with your "
        "explanation, try settling your stance between points."
    ),
    "hand_near_face": (
        "Your hand appeared near your face for a sustained moment or on repeated occasions. "
        "Contact is not confirmed; "
        "if these were incidental adjustments, try returning your hand to a relaxed position "
        "between points."
    ),
    "hands_clasped_low": (
        "Your hands appeared close together low on your torso. If this was a prolonged resting "
        "position, consider a relaxed gesture to emphasize your next point."
    ),
    "arms_crossed": (
        "An arm reached toward the opposite shoulder, or your forearms stayed folded across "
        "your torso. If this was unintentional, try "
        "releasing your arms between points. A deliberate pose can be appropriate."
    ),
    "gesture_box_excursion": (
        "One arm appeared close to a full sideways extension. Review whether it supported "
        "your point; if not, try returning to a relaxed position after the emphasis."
    ),
}
MIN_EVENT_SECONDS = {
    "repeated_head_movement": 0.6,
    "repeated_swaying": 1.0,
    "hand_near_face": 1.0,
    "hands_clasped_low": 0.8,
    "arms_crossed": 0.4,
    "gesture_box_excursion": 0.4,
}
POSE_EVENT_THRESHOLDS = {
    "repeated_head_movement": 0.76,
    "repeated_swaying": 0.76,
    "hand_near_face": 0.76,
    "hands_clasped_low": 0.72,
    "arms_crossed": 0.76,
    "gesture_box_excursion": 0.76,
}
SKELETON_EDGES = (
    (0, 1),
    (0, 2),
    (5, 6),
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 11),
    (6, 12),
    (11, 12),
)


class UploadPracticeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int
    codec: str
    has_audio: bool


@dataclass
class ActivePoseEvent:
    event_type: str
    start_seconds: float
    last_seconds: float
    confidence_total: float
    sample_count: int
    best_confidence: float
    best_seconds: float
    best_frame: Any
    best_keypoints: list[tuple[float, float, float]]

    def add(
        self,
        timestamp: float,
        confidence: float,
        frame: Any,
        keypoints: list[tuple[float, float, float]],
    ) -> None:
        self.last_seconds = timestamp
        self.confidence_total += confidence
        self.sample_count += 1
        if confidence > self.best_confidence:
            self.best_confidence = confidence
            self.best_seconds = timestamp
            self.best_frame = frame.copy()
            self.best_keypoints = keypoints


@dataclass
class PoseEventCollector:
    evidence_directory: Path
    # Legacy constructor argument; every reported event now retains a frame.
    maximum_evidence_frames: int
    sample_interval: float
    events: list[dict[str, Any]] = field(default_factory=list)
    active: dict[str, ActivePoseEvent] = field(default_factory=dict)
    last_tracking_loss: float = float("-inf")

    def observe(
        self,
        timestamp: float,
        detections: dict[str, float],
        frame: Any,
        keypoints: list[tuple[float, float, float]],
    ) -> None:
        if not keypoints:
            self.last_tracking_loss = timestamp
        for event_type in POSE_LABELS:
            confidence = detections.get(event_type, 0.0)
            current = self.active.get(event_type)
            gap_limit = 0.8 if event_type in {"arms_crossed", "hands_clasped_low"} else 0.4
            if current and (not keypoints or timestamp - current.last_seconds > gap_limit + 1e-6):
                self._finish(event_type)
                current = None
            threshold = POSE_EVENT_THRESHOLDS[event_type] - (0.08 if current else 0)
            if confidence >= threshold:
                if current is None:
                    self.active[event_type] = ActivePoseEvent(
                        event_type=event_type,
                        start_seconds=timestamp,
                        last_seconds=timestamp,
                        confidence_total=confidence,
                        sample_count=1,
                        best_confidence=confidence,
                        best_seconds=timestamp,
                        best_frame=frame.copy(),
                        best_keypoints=keypoints,
                    )
                else:
                    current.add(timestamp, confidence, frame, keypoints)
            elif current is not None and (
                not keypoints or timestamp - current.last_seconds >= gap_limit
            ):
                self._finish(event_type)

    def finish_all(self) -> list[dict[str, Any]]:
        for event_type in list(self.active):
            self._finish(event_type)
        return self.events

    def _finish(self, event_type: str) -> None:
        event = self.active.pop(event_type)
        duration = event.sample_count * self.sample_interval
        if duration + 1e-6 < MIN_EVENT_SECONDS[event_type]:
            return
        previous = next((e for e in reversed(self.events) if e["type"] == event_type), None)
        merge = previous is not None and (
            0 <= event.start_seconds - previous["end_seconds"] <= 0.8 + 1e-6
            and previous["end_seconds"] > self.last_tracking_loss
        )
        evidence_index = previous["evidence_index"] if merge else len(self.events) + 1
        evidence_path = self.evidence_directory / f"evidence_{evidence_index:03d}.jpg"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        annotated = annotate_pose_frame(
            event.best_frame,
            event.best_keypoints,
            POSE_LABELS[event_type],
            event.best_seconds,
        )
        if not cv2.imwrite(str(evidence_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 88]):
            raise UploadPracticeError(
                "GESTURE_EVIDENCE_FAILED", "Gesture evidence could not be saved. Please retry."
            )
        if merge:
            old_duration = previous["duration_seconds"]
            previous["confidence"] = round(
                (
                    previous["confidence"] * old_duration
                    + event.confidence_total * self.sample_interval
                )
                / (old_duration + duration),
                3,
            )
            previous["duration_seconds"] = round(old_duration + duration, 2)
            previous["end_seconds"] = round(event.last_seconds + self.sample_interval, 2)
            return
        self.events.append(
            {
                "type": event_type,
                "label": POSE_LABELS[event_type],
                "start_seconds": round(event.start_seconds, 2),
                "end_seconds": round(event.last_seconds + self.sample_interval, 2),
                "duration_seconds": round(duration, 2),
                "confidence": round(event.confidence_total / event.sample_count, 3),
                "feedback": POSE_FEEDBACK[event_type],
                "evidence_index": evidence_index,
            }
        )


def probe_video(video_path: Path) -> VideoMetadata:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(video_path),
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=30,
        )
        payload = json.loads(result.stdout)
    except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        raise UploadPracticeError(
            "VIDEO_PROBE_FAILED", "The video could not be read. Check that it is a valid MP4 file."
        ) from error

    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list):
        raise UploadPracticeError("VIDEO_INVALID", "The upload does not contain a readable video.")
    video_stream = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    if video_stream is None:
        raise UploadPracticeError("VIDEO_INVALID", "The upload does not contain a video stream.")
    try:
        width = int(video_stream["width"])
        height = int(video_stream["height"])
        duration = float(
            video_stream.get("duration") or payload.get("format", {}).get("duration") or 0
        )
    except (KeyError, TypeError, ValueError) as error:
        raise UploadPracticeError("VIDEO_INVALID", "The video metadata is incomplete.") from error
    codec = str(video_stream.get("codec_name") or "").lower()
    if codec not in {"h264", "avc1"}:
        raise UploadPracticeError("VIDEO_CODEC_UNSUPPORTED", "Use an MP4 video encoded with H.264.")
    if duration <= 0 or duration > 600:
        raise UploadPracticeError(
            "VIDEO_DURATION_UNSUPPORTED", "The rehearsal video must be 10 minutes or shorter."
        )
    if width <= 0 or height <= 0 or width > 1920 or height > 1080:
        raise UploadPracticeError(
            "VIDEO_RESOLUTION_UNSUPPORTED", "The rehearsal video must be 1080p or lower."
        )
    return VideoMetadata(
        duration_seconds=duration,
        width=width,
        height=height,
        codec=codec,
        has_audio=any(
            isinstance(stream, dict) and stream.get("codec_type") == "audio" for stream in streams
        ),
    )


def extract_audio(video_path: Path, audio_path: Path) -> bool:
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "16000",
                str(audio_path),
            ],
            capture_output=True,
            check=True,
            timeout=180,
        )
        return audio_path.is_file() and audio_path.stat().st_size > 44
    except (FileNotFoundError, subprocess.SubprocessError):
        audio_path.unlink(missing_ok=True)
        return False


def transcribe_audio(audio_path: Path) -> dict[str, Any]:
    settings = get_settings()
    if not settings.groq_api_key:
        raise UploadPracticeError(
            "SPEECH_PROVIDER_NOT_CONFIGURED",
            "Speech analysis is not configured. Add the Groq API key and retry.",
        )
    try:
        with audio_path.open("rb") as audio_file:
            response = requests.post(
                GROQ_TRANSCRIPTION_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                data={
                    "model": settings.upload_practice_whisper_model,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": ["word", "segment"],
                    "temperature": "0",
                    "language": "en",
                },
                files={"file": ("rehearsal.wav", audio_file, "audio/wav")},
                timeout=240,
            )
            response.raise_for_status()
            result = response.json()
    except (OSError, requests.RequestException, ValueError) as error:
        logger.warning("Upload-practice transcription failed: %s", error.__class__.__name__)
        raise UploadPracticeError(
            "SPEECH_TRANSCRIPTION_FAILED", "Speech transcription could not finish. Please retry."
        ) from error
    if not isinstance(result, dict):
        raise UploadPracticeError(
            "SPEECH_TRANSCRIPTION_FAILED", "Speech transcription returned an invalid result."
        )
    return result


def timed_words(transcription: dict[str, Any]) -> list[dict[str, Any]]:
    words = transcription.get("words")
    if isinstance(words, list) and words:
        return [
            {
                "word": str(item.get("word") or "").strip(),
                "start": float(item.get("start") or 0),
                "end": float(item.get("end") or item.get("start") or 0),
            }
            for item in words
            if isinstance(item, dict) and str(item.get("word") or "").strip()
        ]
    derived: list[dict[str, Any]] = []
    segments = transcription.get("segments")
    if not isinstance(segments, list):
        return derived
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        tokens = str(segment.get("text") or "").split()
        if not tokens:
            continue
        start = float(segment.get("start") or 0)
        end = max(start, float(segment.get("end") or start))
        duration = max(0.01, end - start)
        for index, token in enumerate(tokens):
            derived.append(
                {
                    "word": token,
                    "start": start + duration * index / len(tokens),
                    "end": start + duration * (index + 1) / len(tokens),
                }
            )
    return derived


def speech_metrics(transcription: dict[str, Any]) -> dict[str, Any]:
    text = str(transcription.get("text") or "").strip()
    words = timed_words(transcription)
    word_count = len(re.findall(r"\b[A-Za-z0-9']+\b", text))
    speech_duration = 0.0
    if words:
        speech_duration = max(0.0, float(words[-1]["end"]) - float(words[0]["start"]))
    elif isinstance(transcription.get("duration"), (int, float)):
        speech_duration = float(transcription["duration"])
    wpm = word_count / (speech_duration / 60) if speech_duration > 0 else 0.0
    normalized = [re.sub(r"[^a-z']", "", item["word"].lower()) for item in words]
    filler_candidates: list[dict[str, Any]] = []
    for index, word in enumerate(normalized):
        for phrase in (*RELIABLE_FILLER_PHRASES, *CONTEXTUAL_FILLER_PHRASES):
            phrase_words = phrase.split()
            if normalized[index : index + len(phrase_words)] == phrase_words:
                is_reliable = phrase in RELIABLE_FILLER_PHRASES
                before_gap = (
                    float(words[index]["start"]) - float(words[index - 1]["end"])
                    if index > 0
                    else 1.0
                )
                after_index = index + len(phrase_words)
                after_gap = (
                    float(words[after_index]["start"]) - float(words[after_index - 1]["end"])
                    if after_index < len(words)
                    else 1.0
                )
                after_word = normalized[after_index] if after_index < len(normalized) else ""
                if phrase in {"kind of", "sort of"} and after_word == "like":
                    continue
                if (
                    phrase == "like"
                    and index >= 2
                    and normalized[index - 2 : index]
                    in (
                        ["kind", "of"],
                        ["sort", "of"],
                    )
                ):
                    continue
                context_start = max(0, index - 5)
                context_end = min(len(words), after_index + 5)
                filler_candidates.append(
                    {
                        "term": phrase,
                        "timestamp_seconds": round(float(words[index]["start"]), 2),
                        "context": " ".join(
                            item["word"] for item in words[context_start:context_end]
                        ),
                        "is_reliable": is_reliable,
                        "boundary_gap": max(before_gap, after_gap),
                    }
                )
    contextual_counts: dict[str, int] = {}
    for event in filler_candidates:
        if not event["is_reliable"]:
            term = str(event["term"])
            contextual_counts[term] = contextual_counts.get(term, 0) + 1
    filler_events = [
        {
            "term": event["term"],
            "timestamp_seconds": event["timestamp_seconds"],
            "context": event["context"],
        }
        for event in filler_candidates
        if event["is_reliable"]
        or (
            event["term"] != "actually"
            and (
                contextual_counts.get(str(event["term"]), 0) >= 3
                or float(event["boundary_gap"]) >= 0.35
            )
        )
        or (
            event["term"] == "actually"
            and contextual_counts.get("actually", 0) >= 3
            and float(event["boundary_gap"]) >= 0.35
        )
    ]
    filler_events = _deduplicate_overlapping_fillers(filler_events)
    filler_clusters = _filler_clusters(filler_events)
    pause_events = _pause_events(words)
    pace_samples = _pace_samples(words)
    pace_events = _pace_events(pace_samples)
    repetition_events = _repetition_events(words, normalized)
    sensitive_terms = {
        term.strip().lower()
        for term in get_settings().upload_practice_sensitive_terms.split(",")
        if term.strip()
    }
    sensitive_flags: list[dict[str, Any]] = []
    for index, word in enumerate(normalized):
        if word not in sensitive_terms:
            continue
        context_start = max(0, index - 5)
        context_end = min(len(words), index + 6)
        sensitive_flags.append(
            {
                "term": word,
                "timestamp_seconds": round(float(words[index]["start"]), 2),
                "context": " ".join(item["word"] for item in words[context_start:context_end]),
            }
        )
    return {
        "transcript": text,
        "timed_transcript": words,
        "timing_source": "word" if transcription.get("words") else "estimated",
        "word_count": word_count,
        "speech_duration_seconds": round(speech_duration, 2),
        "words_per_minute": round(wpm, 1),
        "filler_events": filler_events,
        "filler_clusters": filler_clusters,
        "pause_events": pause_events,
        "pace_samples": pace_samples,
        "pace_events": pace_events,
        "repetition_events": repetition_events,
        "sensitive_term_flags": sensitive_flags,
    }


def _deduplicate_overlapping_fillers(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: list[dict[str, Any]] = []
    for event in events:
        if (
            deduplicated
            and abs(
                float(deduplicated[-1]["timestamp_seconds"]) - float(event["timestamp_seconds"])
            )
            < 0.05
        ):
            if len(str(event["term"])) > len(str(deduplicated[-1]["term"])):
                deduplicated[-1] = event
            continue
        deduplicated.append(event)
    return deduplicated


def _filler_clusters(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    start = 0
    for end in range(len(events)):
        while (
            float(events[end]["timestamp_seconds"]) - float(events[start]["timestamp_seconds"]) > 30
        ):
            start += 1
        window = events[start : end + 1]
        if len(window) < 3:
            continue
        candidate = {
            "start_seconds": window[0]["timestamp_seconds"],
            "end_seconds": window[-1]["timestamp_seconds"],
            "count": len(window),
            "terms": [item["term"] for item in window],
            "context": window[-1].get("context", ""),
        }
        if clusters and candidate["start_seconds"] <= clusters[-1]["end_seconds"]:
            clusters[-1] = candidate
        else:
            clusters.append(candidate)
    return clusters


def _pause_events(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for index in range(1, len(words)):
        gap = float(words[index]["start"]) - float(words[index - 1]["end"])
        if gap < 2.0:
            continue
        context_start = max(0, index - 5)
        context_end = min(len(words), index + 5)
        events.append(
            {
                "start_seconds": round(float(words[index - 1]["end"]), 2),
                "end_seconds": round(float(words[index]["start"]), 2),
                "duration_seconds": round(gap, 2),
                "severity": "long" if gap >= 4 else "noticeable",
                "context": " ".join(item["word"] for item in words[context_start:context_end]),
            }
        )
    return events


def _pace_samples(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(words) < 8:
        return []
    first = float(words[0]["start"])
    last = float(words[-1]["end"])
    window_seconds = 15.0
    step_seconds = 5.0
    samples: list[dict[str, Any]] = []
    window_start = first
    while window_start + window_seconds <= last:
        window_end = window_start + window_seconds
        window_words = [item for item in words if window_start <= float(item["start"]) < window_end]
        duration = max(0.01, window_end - window_start)
        wpm = len(window_words) / (duration / 60)
        if duration >= window_seconds:
            pace_type = "slow" if wpm < 100 else "fast" if wpm > 180 else "steady"
            samples.append(
                {
                    "start_seconds": round(window_start, 2),
                    "end_seconds": round(window_end, 2),
                    "timestamp_seconds": round((window_start + window_end) / 2, 2),
                    "words_per_minute": round(wpm, 1),
                    "word_count": len(window_words),
                    "type": pace_type,
                    "context": " ".join(item["word"] for item in window_words[:16]),
                }
            )
        window_start += step_seconds
    # A personal baseline also catches pronounced changes within the broad
    # reference range. These are review candidates, never automatic mistakes.
    if len(samples) >= 5:
        baseline = median(s["words_per_minute"] for s in samples)
        for sample in samples:
            pace = sample["words_per_minute"]
            sample["baseline_words_per_minute"] = baseline
            if sample["type"] == "steady":
                if pace >= 160 and pace >= baseline * 1.35 and pace - baseline >= 30:
                    sample["type"] = "fast"
                elif pace < 120 and pace <= baseline * 0.65 and baseline - pace >= 30:
                    sample["type"] = "slow"
    return samples


def _pace_events(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    values: list[float] = []
    for sample in samples:
        # Older reports included partial tail windows; never use them as evidence.
        if float(sample["end_seconds"]) - float(sample["start_seconds"]) < 14.99:
            current = None
            continue
        if sample.get("type") not in {"fast", "slow"}:
            current = None
            continue
        timestamp = float(sample["timestamp_seconds"])
        start, end = timestamp - 2.5, timestamp + 2.5
        if (
            current is None
            or current["type"] != sample["type"]
            or start > current["end_seconds"] + 0.01
        ):
            current = {
                "type": sample["type"],
                "start_seconds": start,
                "end_seconds": end,
                "words_per_minute": sample["words_per_minute"],
                "context": sample.get("context", ""),
            }
            values = []
            merged.append(current)
        values.append(float(sample["words_per_minute"]))
        current["end_seconds"] = end
        current["words_per_minute"] = round(sum(values) / len(values), 1)
    return merged


def _repetition_events(words: list[dict[str, Any]], normalized: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    index = 0
    while index < len(normalized) - 1:
        found = False
        for size in range(4, 0, -1):
            if index + size * 2 > len(normalized):
                continue
            phrase = normalized[index : index + size]
            if not any(phrase) or phrase != normalized[index + size : index + size * 2]:
                continue
            events.append(
                {
                    "timestamp_seconds": round(float(words[index]["start"]), 2),
                    "phrase": " ".join(item["word"] for item in words[index : index + size]),
                    "context": " ".join(
                        item["word"]
                        for item in words[max(0, index - 4) : min(len(words), index + size * 2 + 4)]
                    ),
                }
            )
            index += size * 2
            found = True
            break
        if not found:
            index += 1
    return events


def build_coaching_report(
    speech: dict[str, Any], pose_events: list[dict[str, Any]], pose_tracking: dict | None = None
) -> dict[str, list[dict[str, Any]] | list[str]]:
    candidates: list[dict[str, Any]] = []
    pace_events = [event for event in speech.get("pace_events", []) if isinstance(event, dict)]
    fast_events = [event for event in pace_events if event.get("type") == "fast"]
    slow_events = [event for event in pace_events if event.get("type") == "slow"]
    fast_duration = sum(
        max(0.0, float(event.get("end_seconds", 0)) - float(event.get("start_seconds", 0)))
        for event in fast_events
    )
    slow_duration = sum(
        max(0.0, float(event.get("end_seconds", 0)) - float(event.get("start_seconds", 0)))
        for event in slow_events
    )
    if fast_events or slow_events:
        longest_pace_event = max(
            pace_events,
            key=lambda event: (
                float(event.get("end_seconds", 0)) - float(event.get("start_seconds", 0))
            ),
        )
        if fast_events and slow_events:
            headline = "Review changes in your delivery"
            observation = (
                f"Your delivery moved between {len(fast_events)} faster section"
                f"{'s' if len(fast_events) != 1 else ''} and {len(slow_events)} slow section"
                f"{'s' if len(slow_events) != 1 else ''}. The faster sections lasted about "
                f"{format_duration_words(fast_duration)} in total."
            )
        elif fast_events:
            headline = "Review your faster passages"
            observation = (
                f"Your delivery exceeded the faster-pace reference or rose substantially "
                f"above your usual pace across {len(fast_events)} "
                f"section{'s' if len(fast_events) != 1 else ''}, lasting about "
                f"{format_duration_words(fast_duration)} in total."
            )
        else:
            headline = "Review your pauses and slower passages"
            observation = (
                f"Your delivery fell below the slower-pace reference or substantially below "
                f"your usual pace across {len(slow_events)} "
                f"section{'s' if len(slow_events) != 1 else ''}, lasting about "
                f"{format_duration_words(slow_duration)} in total."
            )
        candidates.append(
            coaching_finding(
                finding_id="pace-control",
                category="Vocal delivery",
                headline=headline,
                observation=observation,
                impact="Speed alone does not establish a problem. A slower closing, emphasis, "
                "or deliberate pause may help the audience; dense explanations may need "
                "more space.",
                recommendation=(
                    "Replay the excerpt and use its specific delivery feedback. The usual "
                    "120–160 words-per-minute range is a reference, not a required target. "
                    "Do not speed up a deliberate closing or meaningful pause just to meet it."
                ),
                drill=(
                    f"Rehearse the section beginning at "
                    f"{format_timestamp(float(longest_pace_event.get('start_seconds', 0)))} twice: "
                    "once slowly, then once at a steady conversational pace."
                ),
                start_seconds=float(longest_pace_event.get("start_seconds", 0)),
                end_seconds=float(longest_pace_event.get("end_seconds", 0)),
                priority=95 + min(15, (fast_duration + slow_duration) / 20),
            )
        )

    filler_events = [event for event in speech.get("filler_events", []) if isinstance(event, dict)]
    filler_counts: dict[str, int] = {}
    for event in filler_events:
        term = str(event.get("term") or "").strip().lower()
        if term:
            filler_counts[term] = filler_counts.get(term, 0) + 1
    if filler_counts:
        top_term, top_count = max(filler_counts.items(), key=lambda item: item[1])
        if len(filler_events) >= 3 or top_count >= 3:
            top_events = [event for event in filler_events if event.get("term") == top_term]
            first_event = top_events[0] if top_events else filler_events[0]
            candidates.append(
                coaching_finding(
                    finding_id="verbal-habit",
                    category="Verbal clarity",
                    headline=f"Reduce repeated use of “{top_term}”",
                    observation=(
                        f"“{top_term}” appeared {top_count} times. Repeating the same verbal habit "
                        "can make otherwise confident delivery sound less deliberate."
                    ),
                    impact=(
                        "Repeated verbal habits compete with the point you want the audience "
                        "to remember."
                    ),
                    recommendation=(
                        f"When you feel “{top_term}” coming, replace it with a brief silent "
                        "pause or "
                        "move directly to the next precise statement."
                    ),
                    drill=(
                        f"Repeat the section around "
                        f"{format_timestamp(float(first_event.get('timestamp_seconds', 0)))} and "
                        f"remove every unnecessary “{top_term}”."
                    ),
                    start_seconds=float(first_event.get("timestamp_seconds", 0)),
                    end_seconds=float(first_event.get("timestamp_seconds", 0)) + 2,
                    priority=85 + min(15, top_count),
                )
            )

    pause_events = [event for event in speech.get("pause_events", []) if isinstance(event, dict)]
    concerning_pauses = [
        event for event in pause_events if float(event.get("duration_seconds", 0)) >= 4
    ]
    if concerning_pauses:
        longest_pause = max(
            concerning_pauses, key=lambda event: float(event.get("duration_seconds", 0))
        )
        pause_length = float(longest_pause.get("duration_seconds", 0))
        candidates.append(
            coaching_finding(
                finding_id="long-pause",
                category="Fluency",
                headline="Review this longer pause",
                observation=(
                    f"A {pause_length:.1f}-second silence occurred at "
                    f"{format_timestamp(float(longest_pause.get('start_seconds', 0)))}."
                ),
                impact="This may be emphasis, an audience response, or a hesitation; timing "
                "alone cannot distinguish them.",
                recommendation=(
                    "Replay the sentences on either side. Keep the pause if it gives an idea "
                    "time to land; rehearse the transition only if you lost your place."
                ),
                drill=(
                    "Practise the sentence before and after this pause five times without "
                    "looking at notes."
                ),
                start_seconds=float(longest_pause.get("start_seconds", 0)),
                end_seconds=float(longest_pause.get("end_seconds", 0)),
                priority=75 + min(15, pause_length),
            )
        )

    repetition_events = [
        event for event in speech.get("repetition_events", []) if isinstance(event, dict)
    ]
    if len(repetition_events) >= 2:
        first_repeat = repetition_events[0]
        candidates.append(
            coaching_finding(
                finding_id="repeated-starts",
                category="Fluency",
                headline="Finish sentences without restarting",
                observation=(
                    f"You restarted a word or phrase {len(repetition_events)} times during "
                    "the rehearsal."
                ),
                impact="Repeated starts can make transitions sound less prepared.",
                recommendation=(
                    "Pause briefly before beginning the next sentence instead of correcting "
                    "it mid-start."
                ),
                drill=(
                    f"Rehearse the transition near "
                    f"{format_timestamp(float(first_repeat.get('timestamp_seconds', 0)))} "
                    "and begin "
                    "each sentence only after a complete breath."
                ),
                start_seconds=float(first_repeat.get("timestamp_seconds", 0)),
                end_seconds=float(first_repeat.get("timestamp_seconds", 0)) + 2,
                priority=70 + min(15, len(repetition_events) * 2),
            )
        )

    pose_groups: dict[str, list[dict[str, Any]]] = {}
    for event in pose_events:
        if isinstance(event, dict):
            event_type = str(event.get("type") or "")
            pose_groups.setdefault(event_type, []).append(event)
    if pose_groups:
        event_type, grouped_events = max(
            pose_groups.items(),
            key=lambda item: sum(float(event.get("duration_seconds", 0)) for event in item[1]),
        )
        representative = max(
            grouped_events, key=lambda event: float(event.get("duration_seconds", 0))
        )
        pose_copy = {
            "repeated_head_movement": (
                "Give your head movements a clear purpose",
                "Your head changed direction repeatedly in this excerpt.",
                "Repeated movement may compete with your explanation; natural audience scanning "
                "and nods can still be appropriate.",
                "Replay this moment and try settling your head briefly between main points.",
            ),
            "hands_clasped_low": (
                "Bring your gestures back into view",
                "Your hands stayed clasped below the visible gesture area during part of the "
                "rehearsal.",
                "Hidden, fixed hands reduce visible emphasis and can make delivery appear guarded.",
                "Let your hands rest naturally, then raise them to chest height only when "
                "emphasizing a point.",
            ),
            "arms_crossed": (
                "Reopen your posture",
                "An arm stayed across your body toward the opposite shoulder, or both arms "
                "remained folded during part of the rehearsal.",
                "A closed stance can reduce the sense of openness and audience connection.",
                "Release your arms after the transition and return to a relaxed, open resting "
                "position.",
            ),
            "gesture_box_excursion": (
                "Keep large gestures controlled",
                "One arm remained near a full sideways extension during part of the rehearsal.",
                "A sustained oversized gesture can pull attention away from the message.",
                "Use the wide gesture for emphasis, then bring your hand back toward your torso "
                "immediately.",
            ),
        }
        headline, observation, impact, recommendation = pose_copy.get(
            event_type,
            (
                "Make your body language more deliberate",
                "A sustained body-language pattern may distract from the message.",
                "Distracting movement competes with the content.",
                "Return to a relaxed neutral posture after each gesture.",
            ),
        )
        candidates.append(
            coaching_finding(
                finding_id="body-language",
                category="Body language",
                headline=headline,
                observation=observation,
                impact=impact,
                recommendation=recommendation,
                drill=(
                    f"Replay the moment at "
                    f"{format_timestamp(float(representative.get('start_seconds', 0)))} and "
                    "practise "
                    "the same sentence with one smaller, intentional gesture."
                ),
                start_seconds=float(representative.get("start_seconds", 0)),
                end_seconds=float(representative.get("end_seconds", 0)),
                priority=80
                + min(
                    15,
                    sum(float(event.get("duration_seconds", 0)) for event in grouped_events),
                ),
                evidence_index=(
                    int(representative["evidence_index"])
                    if isinstance(representative.get("evidence_index"), int)
                    else None
                ),
            )
        )

    findings = sorted(candidates, key=lambda item: float(item.pop("_priority")), reverse=True)[:3]
    strengths: list[str] = []
    overall_wpm = float(speech.get("words_per_minute") or 0)
    if 110 <= overall_wpm <= 160:
        strengths.append(
            "Your overall speaking pace stayed within a clear presentation range, even though "
            "a few sections varied."
        )
    if not pose_events and pose_tracking and pose_tracking.get("status") == "reliable":
        strengths.append(
            "No sustained closed posture or excessively wide gesture was found in the tracked "
            "portions."
        )
    if not concerning_pauses:
        strengths.append("No internal pause of four seconds or longer was measured.")
    if len(filler_events) <= 2:
        strengths.append("Your delivery contained very few clearly repeated verbal habits.")
    if not strengths:
        strengths.append(
            "You completed the rehearsal and now have specific moments to improve next."
        )
    practice_plan = [str(finding["drill"]) for finding in findings]
    if len(practice_plan) < 3:
        practice_plan.extend(
            [
                "Repeat the opening and closing once without reading directly from notes.",
                "Record one shorter rehearsal and focus on one improvement at a time.",
            ][: 3 - len(practice_plan)]
        )
    return {
        "findings": findings,
        "strengths": strengths[:3],
        "practice_plan": practice_plan[:3],
    }


def coaching_finding(
    *,
    finding_id: str,
    category: str,
    headline: str,
    observation: str,
    impact: str,
    recommendation: str,
    drill: str,
    start_seconds: float,
    end_seconds: float,
    priority: float,
    evidence_index: int | None = None,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "category": category,
        "headline": headline,
        "observation": observation,
        "impact": impact,
        "recommendation": recommendation,
        "drill": drill,
        "start_seconds": round(start_seconds, 2),
        "end_seconds": round(end_seconds, 2),
        "evidence_index": evidence_index,
        "_priority": priority,
    }


def format_duration_words(seconds: float) -> str:
    rounded = max(0, round(seconds))
    minutes, remainder = divmod(rounded, 60)
    if minutes and remainder:
        return f"{minutes} minute{'s' if minutes != 1 else ''} {remainder} seconds"
    if minutes:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{remainder} seconds"


def _point(keypoints: list[tuple[float, float, float]], index: int) -> tuple[float, float] | None:
    if index >= len(keypoints) or keypoints[index][2] < 0.25:
        return None
    return keypoints[index][0], keypoints[index][1]


def _angle_degrees(
    first: tuple[float, float],
    vertex: tuple[float, float],
    third: tuple[float, float],
) -> float:
    first_vector = (first[0] - vertex[0], first[1] - vertex[1])
    third_vector = (third[0] - vertex[0], third[1] - vertex[1])
    denominator = math.hypot(*first_vector) * math.hypot(*third_vector)
    if denominator <= 0:
        return 180.0
    cosine = max(
        -1.0,
        min(1.0, sum(a * b for a, b in zip(first_vector, third_vector)) / denominator),
    )
    return math.degrees(math.acos(cosine))


def presenter_pose_is_reliable(keypoints: list[tuple[float, float, float]]) -> bool:
    if len(keypoints) < 13:
        return False
    face_confident = keypoints[0][2] >= 0.35 and max(keypoints[1][2], keypoints[2][2]) >= 0.3
    body_indices = (5, 6, 7, 8, 9, 10, 11, 12)
    confident_body = sum(keypoints[index][2] >= 0.35 for index in body_indices)
    return face_confident and confident_body >= 7


def classify_pose(keypoints: list[tuple[float, float, float]]) -> dict[str, float]:
    left_shoulder = _point(keypoints, 5)
    right_shoulder = _point(keypoints, 6)
    left_elbow = _point(keypoints, 7)
    right_elbow = _point(keypoints, 8)
    left_wrist = _point(keypoints, 9)
    right_wrist = _point(keypoints, 10)
    left_hip = _point(keypoints, 11)
    right_hip = _point(keypoints, 12)
    single_crossing = 0.0
    if left_shoulder and right_shoulder:
        width = max(1.0, math.dist(left_shoulder, right_shoulder))
        middle = (left_shoulder[0] + right_shoulder[0]) / 2
        direction = 1 if right_shoulder[0] > left_shoulder[0] else -1
        for shoulder, elbow, wrist, opposite, outward in (
            (left_shoulder, left_elbow, left_wrist, right_shoulder, direction),
            (right_shoulder, right_elbow, right_wrist, left_shoulder, -direction),
        ):
            if elbow is None or wrist is None:
                continue
            if (
                (wrist[0] - middle) * outward > width * 0.18
                and math.dist(wrist, opposite) / width <= 0.55
                and abs(wrist[1] - opposite[1]) <= width * 0.40
                and _angle_degrees(shoulder, elbow, wrist) <= 135
            ):
                single_crossing = 0.85
    required = (left_shoulder, right_shoulder, left_hip, right_hip)
    if any(point is None for point in required):
        return {"arms_crossed": single_crossing}
    assert left_shoulder and right_shoulder
    assert left_hip and right_hip
    shoulder_width = max(1.0, math.dist(left_shoulder, right_shoulder))
    shoulder_y = (left_shoulder[1] + right_shoulder[1]) / 2
    hip_y = (left_hip[1] + right_hip[1]) / 2
    torso_height = max(1.0, abs(hip_y - shoulder_y))
    shoulder_direction = 1 if right_shoulder[0] > left_shoulder[0] else -1

    def lateral_extension(shoulder, elbow, wrist, outward_direction) -> float:
        if elbow is None or wrist is None:
            return 0.0
        elbow_angle = _angle_degrees(shoulder, elbow, wrist)
        horizontal_reach = (wrist[0] - shoulder[0]) * outward_direction / shoulder_width
        elbow_reach = (elbow[0] - shoulder[0]) * outward_direction / shoulder_width
        vertical_reach = abs(wrist[1] - shoulder[1]) / shoulder_width
        within_height = shoulder_y - torso_height * 0.35 <= wrist[1] <= hip_y + torso_height * 0.1
        if (
            elbow_angle < 145
            or horizontal_reach < 0.9
            or elbow_reach < 0.35
            or vertical_reach > horizontal_reach * 0.8
            or not within_height
        ):
            return 0.0
        return min(1.0, 0.8 + (horizontal_reach - 0.9) * 0.35)

    # A visible extended arm does not depend on tracking the other hand.
    excursion_score = max(
        lateral_extension(left_shoulder, left_elbow, left_wrist, -shoulder_direction),
        lateral_extension(right_shoulder, right_elbow, right_wrist, shoulder_direction),
    )
    if left_wrist is None or right_wrist is None:
        return {"arms_crossed": single_crossing, "gesture_box_excursion": excursion_score}
    center_x = (left_shoulder[0] + right_shoulder[0] + left_hip[0] + right_hip[0]) / 4
    wrist_distance = math.dist(left_wrist, right_wrist) / shoulder_width
    wrist_y = (left_wrist[1] + right_wrist[1]) / 2

    clasp_close = max(0.0, min(1.0, (0.55 - wrist_distance) / 0.35))
    clasp_low = max(
        0.0,
        min(
            1.0,
            (wrist_y - (shoulder_y + torso_height * 0.55)) / (torso_height * 0.35),
        ),
    )
    clasp_score = 0.5 * clasp_close + 0.5 * clasp_low if clasp_close and clasp_low else 0.0
    if wrist_distance <= 0.35 and wrist_y >= shoulder_y + torso_height * 0.55:
        # Hands resting together at the abdomen need not be down at the hips.
        clasp_score = max(clasp_score, 0.8)

    if left_elbow is None or right_elbow is None:
        crossed_score = single_crossing
        return {
            "hands_clasped_low": clasp_score,
            "arms_crossed": crossed_score,
            "gesture_box_excursion": excursion_score,
        }

    crossed_sides = (left_wrist[0] - center_x) * shoulder_direction > shoulder_width * 0.05 and (
        center_x - right_wrist[0]
    ) * shoulder_direction > shoulder_width * 0.05
    torso_band = all(
        shoulder_y - torso_height * 0.1 <= wrist[1] <= hip_y + torso_height * 0.1
        for wrist in (left_wrist, right_wrist)
    )
    opposite_distance = (
        math.dist(left_wrist, right_elbow) + math.dist(right_wrist, left_elbow)
    ) / (2 * shoulder_width)
    own_distance = (math.dist(left_wrist, left_elbow) + math.dist(right_wrist, right_elbow)) / (
        2 * shoulder_width
    )
    left_elbow_angle = _angle_degrees(left_shoulder, left_elbow, left_wrist)
    right_elbow_angle = _angle_degrees(right_shoulder, right_elbow, right_wrist)
    forearms_folded = left_elbow_angle <= 125 and right_elbow_angle <= 125
    # Wrists can sit near the centre while the forearms visibly fold across the
    # torso. Require substantial sideways forearms, not just crossed fingertips.
    forearms_across = all(
        abs(wrist[0] - elbow[0]) >= shoulder_width * 0.60
        and abs(wrist[1] - elbow[1]) <= shoulder_width * 0.45
        for wrist, elbow in ((left_wrist, left_elbow), (right_wrist, right_elbow))
    )
    opposite_contact = opposite_distance <= 0.45 and opposite_distance + 0.12 < own_distance
    crossed_score = single_crossing
    if crossed_sides and torso_band and forearms_folded and forearms_across and opposite_contact:
        closeness = max(0.0, min(1.0, (0.55 - opposite_distance) / 0.35))
        crossed_score = 0.8 + 0.2 * closeness
    folded_shape = forearms_folded and all(
        abs(wrist[0] - elbow[0]) >= shoulder_width * 0.5
        for wrist, elbow in ((left_wrist, left_elbow), (right_wrist, right_elbow))
    )
    if crossed_score >= POSE_EVENT_THRESHOLDS["arms_crossed"] or folded_shape:
        clasp_score = 0.0

    return {
        "hands_clasped_low": clasp_score,
        "arms_crossed": crossed_score,
        "gesture_box_excursion": excursion_score,
    }


def annotate_pose_frame(
    frame: Any,
    keypoints: list[tuple[float, float, float]],
    label: str,
    timestamp: float,
) -> Any:
    annotated = frame.copy()
    for start, end in SKELETON_EDGES:
        start_point = _point(keypoints, start)
        end_point = _point(keypoints, end)
        if start_point and end_point:
            cv2.line(
                annotated,
                (round(start_point[0]), round(start_point[1])),
                (round(end_point[0]), round(end_point[1])),
                (122, 92, 241),
                3,
                cv2.LINE_AA,
            )
    for index in (0, 1, 2, 5, 6, 7, 8, 9, 10, 11, 12):
        point = _point(keypoints, index)
        if point:
            cv2.circle(annotated, (round(point[0]), round(point[1])), 5, (92, 220, 255), -1)
    banner_height = max(48, round(annotated.shape[0] * 0.08))
    overlay = annotated.copy()
    cv2.rectangle(overlay, (0, 0), (annotated.shape[1], banner_height), (24, 24, 31), -1)
    cv2.addWeighted(overlay, 0.82, annotated, 0.18, 0, annotated)
    cv2.putText(
        annotated,
        f"{label}  {format_timestamp(timestamp)}",
        (18, round(banner_height * 0.67)),
        cv2.FONT_HERSHEY_SIMPLEX,
        max(0.55, annotated.shape[1] / 1800),
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    return annotated


def format_timestamp(seconds: float) -> str:
    total = max(0, round(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def analyze_pose(
    video_path: Path,
    evidence_directory: Path,
    progress: Callable[[int], None] | None = None,
    tracking: dict | None = None,
    duration_seconds: float | None = None,
) -> list[dict[str, Any]]:
    try:
        from ultralytics import YOLO
    except ImportError as error:
        raise UploadPracticeError(
            "POSE_MODEL_UNAVAILABLE", "Pose analysis is not installed on this server."
        ) from error
    settings = get_settings()
    try:
        model = YOLO(settings.upload_practice_pose_model)
    except Exception as error:
        logger.warning("Upload-practice pose model failed to load: %s", error.__class__.__name__)
        raise UploadPracticeError(
            "POSE_MODEL_UNAVAILABLE", "The pose model could not be loaded. Please retry."
        ) from error
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise UploadPracticeError("VIDEO_DECODE_FAILED", "The video could not be decoded.")
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = max(1, int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 1))
    sample_fps = max(1.0, min(settings.upload_practice_sample_fps, source_fps))
    frame_step = max(1, round(source_fps / sample_fps))
    coverage = PoseCoverage(
        duration_seconds if duration_seconds is not None else total_frames / source_fps,
        frame_step / source_fps,
    )
    collector = PoseEventCollector(
        evidence_directory=evidence_directory,
        maximum_evidence_frames=settings.upload_practice_max_evidence_frames,
        sample_interval=1 / sample_fps,
    )
    frame_number = 0
    movement = MovementTracker()
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_number % frame_step:
                frame_number += 1
                continue
            timestamp = frame_number / source_fps
            frame_number += 1
            try:
                results = model.predict(frame, verbose=False, conf=0.25, max_det=3)
            except Exception as error:
                raise UploadPracticeError(
                    "POSE_ANALYSIS_FAILED", "Pose analysis could not finish. Please retry."
                ) from error
            if not results or results[0].keypoints is None or not len(results[0].keypoints):
                coverage.observe(timestamp, [], False, frame.shape[1], frame.shape[0])
                movement.observe(timestamp, [])
                collector.observe(timestamp, {}, frame, [])
                continue
            xy_candidates = results[0].keypoints.xy.cpu().tolist()
            confidences = results[0].keypoints.conf
            confidence_candidates = (
                confidences.cpu().tolist()
                if confidences is not None
                else [[1.0] * len(candidate) for candidate in xy_candidates]
            )
            reliable_candidates: list[list[tuple[float, float, float]]] = []
            candidates = []
            for xy, conf_values in zip(xy_candidates, confidence_candidates):
                candidate = [
                    (float(point[0]), float(point[1]), float(conf_values[index]))
                    for index, point in enumerate(xy)
                ]
                candidates.append(candidate)
                if presenter_pose_is_reliable(candidate):
                    reliable_candidates.append(candidate)
            keypoints = max(
                reliable_candidates,
                key=lambda candidate: sum(candidate[index][2] for index in (0, 5, 6, 7, 8, 9, 10)),
                default=[],
            )
            diagnostic_points = keypoints or max(
                candidates, key=lambda candidate: sum(p[2] for p in candidate), default=[]
            )
            coverage.observe(
                timestamp, diagnostic_points, bool(keypoints), frame.shape[1], frame.shape[0]
            )
            detections = classify_pose(keypoints) if keypoints else {}
            detections.update(movement.observe(timestamp, keypoints))
            collector.observe(timestamp, detections, frame, keypoints)
            if progress and frame_number % max(frame_step, round(total_frames / 20)) == 0:
                progress(min(75, 20 + round(55 * frame_number / total_frames)))
    finally:
        capture.release()
        if tracking is not None:
            tracking.update(coverage.result())
    return collector.finish_all()


def _update_session(session_id: uuid.UUID, **values: Any) -> None:
    with get_session_factory()() as database:
        record = database.get(UploadPracticeSession, session_id)
        if record is None:
            return
        for field_name, value in values.items():
            setattr(record, field_name, value)
        job = database.scalar(
            select(Job)
            .where(
                Job.target_id == session_id,
                Job.job_type == "upload_practice",
            )
            .order_by(Job.created_at.desc())
        )
        if job is not None:
            if "status" in values:
                job.status = values["status"]
                if values["status"] == "processing" and job.started_at is None:
                    job.started_at = datetime.now(UTC)
                if values["status"] in {"completed", "failed"}:
                    job.completed_at = datetime.now(UTC)
            if "progress_percent" in values:
                job.progress_percent = values["progress_percent"]
            if "processing_error_code" in values:
                job.error_code = values["processing_error_code"]
            if "processing_error_message" in values:
                job.error_message = values["processing_error_message"]
        database.commit()


def run_upload_practice(session_id: uuid.UUID, source_key: str) -> None:
    source_path = storage_path(source_key)
    temporary_directory = source_path.parent
    evidence_directory: Path | None = None
    try:
        _update_session(session_id, status="processing", progress_percent=5)
        with get_session_factory()() as database:
            record = database.get(UploadPracticeSession, session_id)
            if record is None:
                return
            user_id = record.user_id
        metadata = probe_video(source_path)
        _update_session(
            session_id,
            progress_percent=12,
            duration_seconds=metadata.duration_seconds,
            video_width=metadata.width,
            video_height=metadata.height,
            video_codec=metadata.codec,
        )
        evidence_directory = storage_path(f"practice-reports/{user_id}/{session_id}")
        _update_session(session_id, progress_percent=20)
        pose_tracking: dict = {}
        pose_events = analyze_pose(
            source_path,
            evidence_directory,
            progress=lambda value: _update_session(session_id, progress_percent=value),
            tracking=pose_tracking,
            duration_seconds=metadata.duration_seconds,
        )
        _update_session(session_id, progress_percent=78, pose_tracking=pose_tracking)
        logger.info(
            "Upload practice %s pose tracking: status=%s samples=%s reliable_body=%s%% checks=%s",
            session_id,
            pose_tracking.get("status"),
            pose_tracking.get("sample_count"),
            pose_tracking.get("reliable_body_percent"),
            {c["type"]: c["status"] for c in pose_tracking.get("checks", [])},
        )
        save_gesture_clips(source_path, evidence_directory, pose_events, metadata.duration_seconds)
        _update_session(session_id, progress_percent=80)
        speech = {
            "transcript": "",
            "timed_transcript": [],
            "word_count": 0,
            "speech_duration_seconds": 0.0,
            "words_per_minute": 0.0,
            "filler_events": [],
            "filler_clusters": [],
            "pause_events": [],
            "pace_samples": [],
            "pace_events": [],
            "repetition_events": [],
            "sensitive_term_flags": [],
        }
        audio_path = temporary_directory / "speech.wav"
        if metadata.has_audio:
            if extract_audio(source_path, audio_path):
                speech = speech_metrics(transcribe_audio(audio_path))
        _update_session(session_id, progress_percent=90)
        coaching = build_coaching_report(speech, pose_events, pose_tracking)
        moments = speech_moments(speech, coaching["findings"], metadata.duration_seconds)
        if moments:
            save_audio_excerpts(audio_path, evidence_directory, moments)
            coach_speech_moments(moments)
        _update_session(
            session_id,
            status="completed",
            progress_percent=100,
            transcript=speech["transcript"],
            timed_transcript=speech["timed_transcript"],
            speech_moments=moments,
            word_count=speech["word_count"],
            speech_duration_seconds=speech["speech_duration_seconds"],
            words_per_minute=speech["words_per_minute"],
            filler_events=speech["filler_events"],
            filler_clusters=speech["filler_clusters"],
            pause_events=speech["pause_events"],
            pace_samples=speech["pace_samples"],
            pace_events=speech["pace_events"],
            repetition_events=speech["repetition_events"],
            sensitive_term_flags=speech["sensitive_term_flags"],
            pose_events=pose_events,
            processing_error_code=None,
            processing_error_message=None,
            completed_at=datetime.now(UTC),
        )
    except UploadPracticeError as error:
        logger.warning("Upload practice %s failed with %s", session_id, error.code)
        if evidence_directory is not None:
            shutil.rmtree(evidence_directory, ignore_errors=True)
        _update_session(
            session_id,
            status="failed",
            processing_error_code=error.code,
            processing_error_message=str(error),
            completed_at=datetime.now(UTC),
        )
    except Exception:
        logger.exception("Upload practice %s failed", session_id)
        if evidence_directory is not None:
            shutil.rmtree(evidence_directory, ignore_errors=True)
        _update_session(
            session_id,
            status="failed",
            processing_error_code="UPLOAD_PRACTICE_FAILED",
            processing_error_message="The rehearsal video could not be analyzed. Please retry.",
            completed_at=datetime.now(UTC),
        )
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


def evidence_path(user_id: uuid.UUID, session_id: uuid.UUID, index: int) -> Path:
    return storage_path(upload_practice_evidence_key(user_id, session_id, index))
