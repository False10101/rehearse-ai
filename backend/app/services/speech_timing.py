"""Local audio measurements and context for speech review candidates."""

import logging
import wave
from pathlib import Path
from statistics import median

import numpy as np

logger = logging.getLogger(__name__)


def audio_silences(path: Path) -> list[dict]:
    """Measure quiet runs in the mono PCM16 audio extracted for transcription.

    Quiet audio is evidence of a pause, not evidence that a pause is a mistake.
    The noise floor adapts to the recording; it cannot establish speaker intent.
    """
    with wave.open(str(path), "rb") as source:
        if source.getsampwidth() != 2 or source.getnchannels() != 1:
            raise ValueError("Pause measurement requires mono PCM16 audio")
        rate = source.getframerate()
        block = max(1, round(rate * 0.05))
        levels = []
        lengths = []
        while chunk := source.readframes(block):
            samples = np.frombuffer(chunk, dtype="<i2").astype(float) / 32768
            levels.append(20 * np.log10(max(float(np.sqrt(np.mean(samples ** 2))), 1e-6)))
            lengths.append(len(samples) / rate)
    if not levels:
        return []
    threshold = float(np.clip(np.percentile(levels, 15) + 6, -50, -30))
    runs = []
    start = None
    clock = 0.0
    for level, length in zip(levels, lengths, strict=True):
        if level < threshold:
            if start is None:
                start = clock
        elif start is not None:
            if clock - start >= 0.3:
                runs.append({"start": start, "end": clock})
            start = None
        clock += length
    if start is not None and clock - start >= 0.3:
        runs.append({"start": start, "end": clock})
    logger.info("Audio pause measurement: seconds=%.2f quiet_runs=%s threshold_db=%.1f",
                clock, len(runs), threshold)
    return runs


def contextualize_pace(samples: list[dict], words: list[dict], silences: list[dict] | None) -> None:
    """Keep measured WPM, but do not equate pauses or ordinary endings with faults."""
    if not samples or not words:
        return
    baseline = median(s["words_per_minute"] for s in samples)
    last_word = float(words[-1]["end"])
    for sample in samples:
        start, end = sample["start_seconds"], sample["end_seconds"]
        quiet = sum(max(0, min(end, s["end"]) - max(start, s["start"]))
                    for s in silences or [])
        active_seconds = max(1, end - start - quiet)
        articulation = sample["word_count"] * 60 / active_seconds
        sample["active_words_per_minute"] = round(articulation, 1)
        sample["quiet_seconds"] = round(quiet, 2)
        closing = end >= last_word - 5
        if sample["type"] == "slow":
            # Silence is reviewed separately. A modest closing slowdown is not
            # promoted to an issue; unusually low active delivery remains visible.
            pause_explains = silences is not None and articulation >= 100
            ordinary_closing = closing and sample["words_per_minute"] >= baseline * 0.65
            if pause_explains or ordinary_closing:
                sample["type"] = "steady"
                sample["context"] = (
                    "Pause within the passage" if pause_explains else "Closing slowdown"
                )
            else:
                sample["context"] = (
                    "Low speaking rate after accounting for measured pauses"
                    if silences is not None
                    else "Slower passage; audio pause measurement unavailable"
                )
        elif sample["type"] == "fast":
            sample["context"] = "Faster delivery; review idea density and phrase boundaries"
