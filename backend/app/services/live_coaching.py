"""Numerical live-camera coaching primitives.

The browser performs iris landmark detection locally and sends normalized
observations. This service applies per-session calibration and neutral coaching
ranges without receiving or storing camera frames.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from statistics import median

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class DebugBounds:
    x: float
    y: float
    width: float
    height: float

    def as_message(self) -> dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "width": round(self.width, 4),
            "height": round(self.height, 4),
        }


@dataclass(frozen=True)
class FrameObservation:
    person_detected: bool
    left_gaze_position: tuple[float, float] | None = None
    right_gaze_position: tuple[float, float] | None = None
    head_yaw: float | None = None
    face_bounds: DebugBounds | None = None
    left_eye_bounds: DebugBounds | None = None
    right_eye_bounds: DebugBounds | None = None
    debug: dict | None = None


@dataclass
class SessionEvent:
    kind: str
    started_at: float
    ended_at: float | None = None

    def as_message(self, session_started_at: float, now: float) -> dict:
        finished_at = self.ended_at if self.ended_at is not None else now
        return {
            "kind": self.kind,
            "started_at_seconds": round(max(0.0, self.started_at - session_started_at), 1),
            "duration_seconds": round(max(0.0, finished_at - self.started_at), 1),
            "active": self.ended_at is None,
        }


@dataclass(frozen=True)
class LiveFeedback:
    sequence: int
    timestamp_ms: int
    person_detected: bool
    front_facing: bool | None
    front_facing_ratio: float | None
    gaze_on_camera: bool | None
    extended_look_away_seconds: float
    head_yaw: str
    calibration_complete: bool
    calibration_samples: int
    calibration_required: int
    message: str
    processing_latency_ms: int
    debug: dict | None
    session_events: list[dict]

    def as_message(self) -> dict:
        return {
            "type": "feedback",
            "sequence": self.sequence,
            "timestamp_ms": self.timestamp_ms,
            "person_detected": self.person_detected,
            "front_facing": self.front_facing,
            "front_facing_ratio": self.front_facing_ratio,
            "gaze_on_camera": self.gaze_on_camera,
            "extended_look_away_seconds": self.extended_look_away_seconds,
            "head_yaw": self.head_yaw,
            "calibration_complete": self.calibration_complete,
            "calibration_samples": self.calibration_samples,
            "calibration_required": self.calibration_required,
            "message": self.message,
            "processing_latency_ms": self.processing_latency_ms,
            "debug": self.debug,
            "session_events": self.session_events,
        }


class LiveCoachingTracker:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._front_facing_window: deque[tuple[float, bool]] = deque()
        self._front_facing_started_at: float | None = None
        self._look_away_started_at: float | None = None
        self._head_yaw_started_at: float | None = None
        self._calibration_samples: list[tuple[float, float, float, float]] = []
        self._calibration_unstable = False
        self._gaze_baseline: tuple[tuple[float, float], tuple[float, float]] | None = None
        self._gaze_classifications: deque[bool] = deque(
            maxlen=self.settings.live_gaze_smoothing_frames
        )
        self._gaze_missing_started_at: float | None = None
        self._person_missing_started_at: float | None = None
        self._previous_timestamp: float | None = None
        self._session_started_at: float | None = None
        self._events: list[SessionEvent] = []
        self._active_events: dict[str, SessionEvent] = {}
        self._event_recovery_started_at: dict[str, float] = {}
        self.total_frames = 0
        self.person_frames = 0
        self.front_facing_frames = 0
        self.front_facing_observations = 0
        self.longest_look_away_seconds = 0.0
        self.head_yaw_frames = 0

    def process(
        self,
        observation: FrameObservation,
        sequence: int,
        timestamp_ms: int,
        processing_latency_ms: int,
    ) -> LiveFeedback:
        now = timestamp_ms / 1000
        self._previous_timestamp = now
        if self._session_started_at is None:
            self._session_started_at = now
        self.total_frames += 1
        calibration_required = self.settings.live_gaze_calibration_frames
        if not observation.person_detected:
            if self._person_missing_started_at is None:
                self._person_missing_started_at = now
            if (
                now - self._person_missing_started_at
                > self.settings.live_landmark_loss_grace_seconds
            ):
                self._look_away_started_at = None
                self._gaze_missing_started_at = None
                self._close_all_events(now)
                self._head_yaw_started_at = None
            return LiveFeedback(
                sequence=sequence,
                timestamp_ms=timestamp_ms,
                person_detected=False,
                front_facing=None,
                front_facing_ratio=self._front_facing_ratio(now),
                gaze_on_camera=None,
                extended_look_away_seconds=0.0,
                head_yaw="unavailable",
                calibration_complete=self._gaze_baseline is not None,
                calibration_samples=len(self._calibration_samples),
                calibration_required=calibration_required,
                message="Move closer and keep your face within the guide.",
                processing_latency_ms=processing_latency_ms,
                debug=None,
                session_events=self._events_as_messages(now),
            )

        self.person_frames += 1
        self._person_missing_started_at = None
        front_facing, head_yaw = self._front_facing(observation.head_yaw)
        if front_facing is not None:
            if self._front_facing_started_at is None:
                self._front_facing_started_at = now
            self.front_facing_observations += 1
            if front_facing:
                self.front_facing_frames += 1
            self._front_facing_window.append((now, front_facing))
            self._trim_front_facing_window(now)

        if head_yaw == "turned":
            self.head_yaw_frames += 1
            if self._head_yaw_started_at is None:
                self._head_yaw_started_at = now
            if now - self._head_yaw_started_at >= self.settings.live_head_yaw_grace_seconds:
                self._start_event("head_yaw", self._head_yaw_started_at)
        elif head_yaw == "centered":
            self._head_yaw_started_at = None
            self._recover_event("head_yaw", now)

        gaze_on_camera, gaze_offset = self._gaze_on_camera(
            observation.left_gaze_position,
            observation.right_gaze_position,
        )
        if gaze_on_camera is not None:
            self._gaze_missing_started_at = None
            if gaze_on_camera:
                self._look_away_started_at = None
                self._recover_event("extended_look_away", now)
            elif self._look_away_started_at is None:
                self._look_away_started_at = now
        elif (
            observation.left_gaze_position is None
            and observation.right_gaze_position is None
        ):
            if self._gaze_missing_started_at is None:
                self._gaze_missing_started_at = now
            if now - self._gaze_missing_started_at > self.settings.live_landmark_loss_grace_seconds:
                self._look_away_started_at = None
                self._recover_event("extended_look_away", now)

        look_away_seconds = (
            max(0.0, now - self._look_away_started_at)
            if self._look_away_started_at is not None
            else 0.0
        )
        self.longest_look_away_seconds = max(self.longest_look_away_seconds, look_away_seconds)
        if look_away_seconds >= self.settings.live_thinking_grace_seconds:
            self._start_event("extended_look_away", self._look_away_started_at or now)
        ratio = self._front_facing_ratio(now)
        fronting_ready = (
            self._front_facing_started_at is not None
            and now - self._front_facing_started_at
            >= self.settings.live_front_facing_window_seconds
        )
        if fronting_ready:
            if ratio is not None and (
                ratio < self.settings.live_front_facing_low
                or ratio > self.settings.live_front_facing_high
            ):
                self._start_event("fronting_balance", now)
            else:
                self._recover_event("fronting_balance", now)
        message = self._message(ratio if fronting_ready else None, now)
        debug = dict(observation.debug or {})
        if observation.head_yaw is not None:
            debug["head_yaw"] = round(observation.head_yaw, 3)
        if gaze_offset is not None:
            debug["gaze_offset"] = {
                "x": round(gaze_offset[0], 3),
                "y": round(gaze_offset[1], 3),
            }
        return LiveFeedback(
            sequence=sequence,
            timestamp_ms=timestamp_ms,
            person_detected=True,
            front_facing=front_facing,
            front_facing_ratio=ratio,
            gaze_on_camera=gaze_on_camera,
            extended_look_away_seconds=round(look_away_seconds, 1),
            head_yaw=head_yaw,
            calibration_complete=self._gaze_baseline is not None,
            calibration_samples=len(self._calibration_samples),
            calibration_required=calibration_required,
            message=message,
            processing_latency_ms=processing_latency_ms,
            debug=debug or None,
            session_events=self._events_as_messages(now),
        )

    def summary(self) -> dict:
        return {
            "frames_processed": self.total_frames,
            "person_detected_frames": self.person_frames,
            "front_facing_ratio": self.front_facing_frames
            / self.front_facing_observations
            if self.front_facing_observations
            else None,
            "gaze_calibrated": self._gaze_baseline is not None,
            "longest_extended_look_away_seconds": round(self.longest_look_away_seconds, 1),
            "head_yaw_frames": self.head_yaw_frames,
            "session_events": self._events_as_messages(
                self._previous_timestamp or self._session_started_at or 0.0
            ),
        }

    def recalibrate_gaze(self, timestamp_ms: int) -> None:
        """Reset only the eye-contact baseline for the active practice session."""
        now = timestamp_ms / 1000
        self._calibration_samples.clear()
        self._calibration_unstable = False
        self._gaze_baseline = None
        self._gaze_classifications.clear()
        self._gaze_missing_started_at = None
        self._person_missing_started_at = None
        self._look_away_started_at = None
        event = self._active_events.pop("extended_look_away", None)
        if event is not None:
            event.ended_at = now
        self._event_recovery_started_at.pop("extended_look_away", None)

    def pause(self, timestamp_ms: int) -> list[dict]:
        """Close active moments so paused time is never counted as coaching time."""
        now = timestamp_ms / 1000
        self._look_away_started_at = None
        self._head_yaw_started_at = None
        self._gaze_missing_started_at = None
        self._person_missing_started_at = None
        self._close_all_events(now)
        return self._events_as_messages(now)

    def _start_event(self, kind: str, started_at: float) -> None:
        self._event_recovery_started_at.pop(kind, None)
        if kind in self._active_events:
            return
        if len(self._events) >= self.settings.live_max_session_events:
            removable = next(
                (index for index, event in enumerate(self._events) if event.ended_at is not None),
                None,
            )
            if removable is not None:
                self._events.pop(removable)
        event = SessionEvent(kind=kind, started_at=started_at)
        self._events.append(event)
        self._active_events[kind] = event

    def _recover_event(self, kind: str, now: float) -> None:
        event = self._active_events.get(kind)
        if event is None:
            return
        recovery_started_at = self._event_recovery_started_at.setdefault(kind, now)
        if now - recovery_started_at < self.settings.live_event_recovery_seconds:
            return
        event.ended_at = now
        self._active_events.pop(kind, None)
        self._event_recovery_started_at.pop(kind, None)

    def _close_all_events(self, now: float) -> None:
        for event in self._active_events.values():
            event.ended_at = now
        self._active_events.clear()
        self._event_recovery_started_at.clear()

    def _events_as_messages(self, now: float) -> list[dict]:
        session_started_at = self._session_started_at or now
        return [event.as_message(session_started_at, now) for event in self._events]

    def _gaze_on_camera(
        self,
        left_position: tuple[float, float] | None,
        right_position: tuple[float, float] | None,
    ) -> tuple[bool | None, tuple[float, float] | None]:
        if left_position is None and right_position is None:
            return None, None
        if self._gaze_baseline is None:
            if left_position is None or right_position is None:
                return None, None
            self._calibration_samples.append(
                (*left_position, *right_position)
            )
            if len(self._calibration_samples) >= self.settings.live_gaze_calibration_frames:
                horizontal_spread = max(
                    max(sample[index] for sample in self._calibration_samples)
                    - min(sample[index] for sample in self._calibration_samples)
                    for index in (0, 2)
                )
                vertical_spread = max(
                    max(sample[index] for sample in self._calibration_samples)
                    - min(sample[index] for sample in self._calibration_samples)
                    for index in (1, 3)
                )
                self._calibration_unstable = (
                    horizontal_spread > self.settings.live_gaze_calibration_horizontal_spread
                    or vertical_spread > self.settings.live_gaze_calibration_vertical_spread
                )
                if self._calibration_unstable:
                    self._calibration_samples.pop(0)
                else:
                    self._gaze_baseline = (
                        (
                            median(sample[0] for sample in self._calibration_samples),
                            median(sample[1] for sample in self._calibration_samples),
                        ),
                        (
                            median(sample[2] for sample in self._calibration_samples),
                            median(sample[3] for sample in self._calibration_samples),
                        ),
                    )
            return None, None
        offsets = []
        if left_position is not None:
            offsets.append(
                (
                    left_position[0] - self._gaze_baseline[0][0],
                    left_position[1] - self._gaze_baseline[0][1],
                )
            )
        if right_position is not None:
            offsets.append(
                (
                    right_position[0] - self._gaze_baseline[1][0],
                    right_position[1] - self._gaze_baseline[1][1],
                )
            )
        distances = [
            (offset[0] / self.settings.live_gaze_horizontal_threshold) ** 2
            + (offset[1] / self.settings.live_gaze_vertical_threshold) ** 2
            for offset in offsets
        ]
        raw_on_camera = all(distance <= 1.0 for distance in distances)
        self._gaze_classifications.append(raw_on_camera)
        on_camera_votes = sum(self._gaze_classifications)
        smoothed_on_camera = on_camera_votes > len(self._gaze_classifications) / 2
        strongest_offset = offsets[distances.index(max(distances))]
        return smoothed_on_camera, strongest_offset

    def _front_facing(self, yaw: float | None) -> tuple[bool | None, str]:
        if yaw is None:
            return None, "unavailable"
        front_facing = abs(yaw) <= self.settings.live_front_facing_yaw_threshold
        if abs(yaw) >= self.settings.live_head_yaw_threshold:
            return front_facing, "turned"
        if abs(yaw) <= self.settings.live_head_yaw_recovery_threshold:
            return front_facing, "centered"
        return front_facing, "slight"

    def _trim_front_facing_window(self, now: float) -> None:
        cutoff = now - self.settings.live_front_facing_window_seconds
        while self._front_facing_window and self._front_facing_window[0][0] < cutoff:
            self._front_facing_window.popleft()

    def _front_facing_ratio(self, now: float) -> float | None:
        self._trim_front_facing_window(now)
        if not self._front_facing_window:
            return None
        return round(
            sum(item[1] for item in self._front_facing_window)
            / len(self._front_facing_window),
            3,
        )

    def _message(
        self,
        ratio: float | None,
        now: float,
    ) -> str:
        gaze_missing_long_enough = (
            self._gaze_missing_started_at is not None
            and now - self._gaze_missing_started_at
            > self.settings.live_landmark_loss_grace_seconds
        )
        if gaze_missing_long_enough:
            return "Keep both eyes visible to begin eye-contact coaching."
        if self._gaze_baseline is None:
            if self._calibration_unstable:
                return "Hold your gaze steady on the marker to finish calibration."
            return "Look at the marker while eye contact is calibrated."
        if "extended_look_away" in self._active_events:
            return "Return your eyes to the camera when you finish your thought."
        if "head_yaw" in self._active_events:
            return "Turn your head back toward the camera."
        if "fronting_balance" in self._active_events:
            if ratio is not None and ratio < self.settings.live_front_facing_low:
                return "Face the camera more consistently."
            return "A few natural turns can make your delivery feel less fixed."
        return "Your delivery signals look balanced."
