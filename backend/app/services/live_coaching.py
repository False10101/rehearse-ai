"""Session-only movement rules. Landmark inference happens in the browser; no LLMs."""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
from math import atan2, degrees, hypot
from statistics import median

from app.core.config import Settings, get_settings


@dataclass(frozen=True)
class DebugBounds:
    x: float
    y: float
    width: float
    height: float

    def as_message(self):
        return dict(x=self.x, y=self.y, width=self.width, height=self.height)


@dataclass(frozen=True)
class FrameObservation:
    person_detected: bool
    eyes: tuple[float, float, float, float] | None = None
    head: tuple[float, float, float] | None = None  # yaw, pitch, roll in degrees
    body: list | None = None  # 33 [x,y,z,visibility] points
    hands: list | None = None  # up to two sets of 21 points
    body_updated: bool = True
    hands_updated: bool = True
    face_targets: list | None = None  # mouth, left eye, right eye, forehead
    debug: dict | None = None


CUES = {
    "eye_away": "Look back toward the camera",
    "repeated_glances": "Keep your eyes forward for your next sentence",
    "gaze_switching": "Hold your gaze while finishing your sentence",
    "head_position": "Bring your head back to centre",
    "repeated_head_turns": "Face forward while finishing your point",
    "head_shaking": "Keep your head steady for your next sentence",
    "head_nodding": "Pause the repeated nodding",
    "abrupt_head_movement": "Make your head turns more gently",
    "body_swaying": "Settle your shoulders before continuing",
    "body_bouncing": "Keep your upper body steady",
    "body_rocking": "Keep a steady distance while speaking",
    "posture_drift": "Sit or stand comfortably upright again",
    "face_obstruction": "Move your hand away from your face",
    "repeated_face_touching": "Let your hands rest between gestures",
    "repetitive_hand_motion": "Let your hands settle between points",
    "gesture_out_of_view": "Keep your gestures within the camera view",
}


def direction(x, y, dead_zone=1.0):
    if hypot(x, y) <= dead_zone:
        return "centre"
    return ("left" if x > 0 else "right") if abs(x) >= abs(y) else ("down" if y > 0 else "up")


@dataclass
class LiveFeedback:
    data: dict

    def as_message(self):
        return self.data


class LiveCoachingTracker:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self.started = None
        self.previous = None
        self.baselines = {}
        self.samples = {}
        self.events = []
        self.active = {}
        self.pending = {}
        self.recovery = {}
        self.runs = {}
        self.candidates = {}
        self.completed_runs = {}
        self.motion = {}
        self.last_pulse = {}
        self.pulse_cue = (0.0, "")
        self.last_body_at = None
        self.last_hands_at = None
        self.body_text = "Not assessed"
        self.hands_text = "Not assessed"
        self.frames = 0

    def _calibrate(self, category, values, required, spread):
        if category in self.baselines:
            return self.baselines[category]
        samples = self.samples.setdefault(category, deque(maxlen=required))
        samples.append(values)
        if len(samples) < required:
            return None
        if any(
            max(s[i] for s in samples) - min(s[i] for s in samples) > spread[i]
            for i in range(len(values))
        ):
            return None
        baseline = tuple(median(s[i] for s in samples) for i in range(len(values)))
        self.baselines[category] = baseline
        return baseline

    def _hold(self, kind, condition, now, seconds, evidence, title=None, recovery_seconds=0.3):
        if condition is None:
            self._close(kind, now)
            self.pending.pop(kind, None)
            return
        if condition:
            self.recovery.pop(kind, None)
            start = self.pending.setdefault(kind, now)
            if round(now - start, 3) >= seconds:
                if kind not in self.active:
                    event = dict(
                        kind=kind,
                        start=start,
                        end=None,
                        title=title or CUES[kind],
                        evidence=evidence,
                    )
                    self.events.append(event)
                    self.active[kind] = event
                self.active[kind].update(evidence=evidence, title=title or CUES[kind])
        else:
            start = self.recovery.setdefault(kind, now)
            if round(now - start, 3) >= recovery_seconds:
                self.pending.pop(kind, None)
                self._close(kind, start)

    def _close(self, kind, now):
        event = self.active.pop(kind, None)
        if event is not None:
            event["end"] = max(event["start"], now)
        self.recovery.pop(kind, None)

    def _pulse(self, kind, start, now, evidence, cooldown=4.0):
        if now - self.last_pulse.get(kind, float("-inf")) < cooldown:
            return
        self.last_pulse[kind] = now
        self.events.append(
            dict(kind=kind, start=start, end=now, title=CUES[kind], evidence=evidence)
        )
        self.pulse_cue = (now + 1.5, CUES[kind])

    def _direction_runs(self, channel, value, now):
        """Count distinct deliberate glances, not every noisy landmark frame."""
        history = self.completed_runs.setdefault(channel, deque())
        while history and history[0][1] < now - 10:
            history.popleft()
        missing_key = f"direction_missing_{channel}"
        if value is None:
            self.candidates.pop(channel, None)
            if channel == "eyes":
                # A blink is not a return to centre and must not erase earlier
                # glances. Long gaps abandon only the unfinished movement.
                missing_since = self.motion.setdefault(missing_key, now)
                if now - missing_since > 0.35:
                    self.runs.pop(channel, None)
            else:
                self.runs.pop(channel, None)
                history.clear()
            return
        missing_since = self.motion.pop(missing_key, None)
        if missing_since is not None and now - missing_since > 0.35:
            self.runs.pop(channel, None)
        candidate = self.candidates.get(channel)
        if candidate is None or candidate[0] != value:
            candidate = (value, now)
            self.candidates[channel] = candidate
        # Eye movements count on their first classified sample; the head
        # repetition filter remains unchanged.
        if channel != "eyes" and round(now - candidate[1], 3) < 0.18:
            return
        current = self.runs.get(channel)
        if current and current[0] == value:
            return
        self.runs[channel] = candidate
        if current is None:
            return
        old, start = current
        end = candidate[1]
        history.append((start, end, old))
        minimum = 0 if channel == "eyes" else 0.18
        glances = [r for r in history if r[2] != "centre" and minimum < r[1] - r[0] <= 1.5]
        same = Counter(r[2] for r in glances)
        if same:
            side, count = same.most_common(1)[0]
            if count >= 3:
                kind = "repeated_glances" if channel == "eyes" else "repeated_head_turns"
                self._pulse(
                    kind, glances[0][0], now, f"{count} glances {side.replace('_', ' ')} in 10s"
                )
        if channel == "eyes":
            recent = [r for r in history if r[1] >= now - 8]
            if len(recent) >= 6 and len({r[2] for r in recent if r[2] != "centre"}) >= 3:
                self._pulse(
                    "gaze_switching",
                    recent[0][0],
                    now,
                    f"{len(recent)} eye-direction changes in 8s",
                )

    def _oscillation(self, key, value, now, amplitude, window, reversals):
        """Hysteresis turning points: one turn is not repeated shaking."""
        if value is None:
            self.motion.pop(key, None)
            return None
        state = self.motion.setdefault(key, dict(extreme=value, trend=0, turns=deque()))
        turns = state["turns"]
        while turns and turns[0] < now - window:
            turns.popleft()
        difference = value - state["extreme"]
        trend = state["trend"]
        changed = False
        if not trend:
            if abs(difference) >= amplitude:
                state.update(extreme=value, trend=1 if difference > 0 else -1)
        elif difference * trend >= 0:
            state["extreme"] = value
        elif abs(difference) >= amplitude:
            state.update(extreme=value, trend=-trend)
            turns.append(now)
            changed = True
        if changed and len(turns) >= reversals:
            return turns[0], len(turns)
        return None

    def _reset_motion(self, now):
        for kind in list(self.active):
            self._close(kind, now)
        self.pending.clear()
        self.recovery.clear()
        self.runs.clear()
        self.candidates.clear()
        self.completed_runs.clear()
        self.motion.clear()
        self.last_pulse.clear()
        self.pulse_cue = (0, "")
        self.samples.clear()
        self.last_body_at = self.last_hands_at = None
        self.body_text = self.hands_text = "Not assessed"

    def _head(self, angles, now):
        if angles is None:
            self.samples.pop("head", None)
            return None, "Not assessed", None
        base = self._calibrate("head", angles, self.settings.live_calibration_frames, (8, 8, 8))
        if base is None:
            return None, "Calibrating", None
        yaw, pitch, roll = [a - b for a, b in zip(angles, base)]
        magnitudes = (abs(yaw) / 15, abs(pitch) / 12, abs(roll) / 12)
        axis = magnitudes.index(max(magnitudes))
        side = "centre"
        if max(magnitudes) > 0.65:
            side = (
                ("left" if yaw > 0 else "right"),
                ("up" if pitch > 0 else "down"),
                ("tilt_right" if roll > 0 else "tilt_left"),
            )[axis]
        text = {
            "centre": "Facing forward",
            "up": "Tilted up",
            "down": "Tilted down",
            "tilt_left": "Leaning head left",
            "tilt_right": "Leaning head right",
        }.get(side, f"Turned {side}")
        self._direction_runs("head", side, now)
        for key, scalar, amp, count, label in (
            ("head_shaking", yaw, 12, 2, "sideways reversals"),
            ("head_nodding", pitch, 10, 3, "up/down reversals"),
        ):
            result = self._oscillation(key, scalar, now, amp, 2.0, count)
            if result:
                self._pulse(key, result[0], now, f"{result[1]} {label} in 2s", cooldown=2)
        previous = self.motion.get("head_speed")
        jolts = self.motion.setdefault("head_jolts", deque())
        if previous:
            dt = now - previous[0]
            change = hypot(yaw - previous[1], pitch - previous[2])
            if 0 < dt <= 0.4 and change >= 8 and change / dt >= 140:
                if not jolts or now - jolts[-1] >= 0.2:
                    jolts.append(now)
        while jolts and jolts[0] < now - 3:
            jolts.popleft()
        if len(jolts) >= 2:
            self._pulse("abrupt_head_movement", jolts[0], now, f"{len(jolts)} abrupt turns in 3s")
        self.motion["head_speed"] = (now, yaw, pitch)
        cue = {
            "up": "Lower your chin slightly",
            "down": "Lift your chin slightly",
            "tilt_left": "Level your head",
            "tilt_right": "Level your head",
        }.get(side, CUES["head_position"])
        self._hold("head_position", max(magnitudes) >= 1, now, 2, text, cue)
        return side, text, (yaw, pitch, roll)

    def _eyes(self, eyes, head, now):
        if eyes is None or head is None:
            return None, "Not assessed"
        if max(abs(head[0]) / 15, abs(head[1]) / 12, abs(head[2]) / 12) > 0.65:
            return None, "Head turned or tilted"
        base = self._calibrate(
            "eyes", eyes, self.settings.live_calibration_frames, (0.08, 0.1, 0.08, 0.1)
        )
        if base is None:
            return None, "Calibrating"
        lx, ly, rx, ry = [a - b for a, b in zip(eyes, base)]
        if hypot((lx - rx) / 0.08, (ly - ry) / 0.1) > 1.5:
            return None, "Eye direction unclear"
        x, y = (lx + rx) / 0.16, (ly + ry) / 0.2
        side = direction(x, y)
        # A corner is its own direction, rather than alternating between up
        # and left as one component becomes slightly larger than the other.
        if side != "centre" and min(abs(x), abs(y)) >= max(abs(x), abs(y)) * 0.5:
            side = ("down" if y > 0 else "up") + "_" + ("left" if x > 0 else "right")
        return side, "Looking forward" if side == "centre" else f"Looking {side.replace('_', ' ')}"

    def _body(self, points, targets, now):
        def visible(index):
            return points and len(points) > index and points[index][3] >= 0.6

        if not visible(11) or not visible(12):
            self.body_text = "Not assessed"
            self._clear_category("body_", now)
            self._hold("posture_drift", None, now, 3, "")
            return None
        left, right = points[11], points[12]
        width = hypot(left[0] - right[0], left[1] - right[1])
        if width < 0.05:
            self.body_text = "Not assessed"
            self._clear_category("body_", now)
            self._hold("posture_drift", None, now, 3, "")
            return None
        cx, cy = (left[0] + right[0]) / 2, (left[1] + right[1]) / 2
        lean = None
        if visible(23) and visible(24):
            hipx = (points[23][0] + points[24][0]) / 2
            lean = (cx - hipx) / width
        neck = (cy - targets[0][1]) / width if targets else None
        shoulder_angle = degrees(atan2(right[1] - left[1], abs(right[0] - left[0])))
        values = (cx, cy, width, lean or 0, neck or 0, shoulder_angle)
        base = self._calibrate("body", values, 8, (0.04, 0.04, 0.05, 0.15, 0.15, 8))
        if base is None:
            self.body_text = "Calibrating"
            return width
        self.body_text = "Steady"
        for kind, value, amp in (
            ("body_swaying", (cx - base[0]) / base[2], 0.18),
            ("body_bouncing", (cy - base[1]) / base[2], 0.12),
            ("body_rocking", width / base[2] - 1, 0.15),
        ):
            result = self._oscillation(kind, value, now, amp, 5, 3)
            if result:
                self._pulse(kind, result[0], now, f"{result[1]} repeated movements in 5s")
                self.body_text = {
                    "body_swaying": "Swaying",
                    "body_bouncing": "Bouncing",
                    "body_rocking": "Rocking",
                }[kind]
        slumped = neck is not None and neck < base[4] - 0.15
        leaning = lean is not None and abs(lean - base[3]) > 0.25
        forward = width > base[2] * 1.25
        tilted = abs(shoulder_angle - base[5]) > 15
        drift = slumped or leaning or forward or tilted
        evidence = (
            "Leaning sideways"
            if leaning or tilted
            else "Leaning forward"
            if forward
            else "Slumping"
        )
        self._hold("posture_drift", drift, now, 3, evidence)
        if drift:
            self.body_text = evidence
        return width

    def _clear_category(self, prefix, now):
        for kind in list(self.pending):
            if kind.startswith(prefix):
                self._hold(kind, None, now, 0, "")
        for key in list(self.motion):
            if key.startswith(prefix):
                self.motion.pop(key, None)

    def _hands(self, hands, targets, shoulder_width, now):
        if not hands:
            self.hands_text = "Not assessed"
            self._hold("face_obstruction", None, now, 0.5, "")
            self._hold("gesture_out_of_view", None, now, 1, "")
            self.motion.pop("repetitive_hand_motion", None)
            for key in list(self.motion):
                if key.startswith(("hand_motion_", "hand_rubbing", "touch", "gesture_edge")):
                    self.motion.pop(key, None)
            return
        self.hands_text = "In view"
        covering = touching = False
        span = shoulder_width or 0.3
        centres = []
        outside = False
        for hand in hands:
            palm = [hand[i] for i in (0, 5, 9, 13, 17)]
            centre = (sum(p[0] for p in palm) / 5, sum(p[1] for p in palm) / 5)
            centres.append(centre)
            outside |= any(p[0] < 0.02 or p[0] > 0.98 or p[1] < 0.02 or p[1] > 0.98 for p in hand)
            if targets:
                face_width = (
                    hypot(targets[1][0] - targets[2][0], targets[1][1] - targets[2][1]) * 1.8
                )
                fingers = [hand[i] for i in (4, 8, 12, 16, 20)]
                touching |= any(
                    hypot(p[0] - t[0], p[1] - t[1]) < face_width * 0.28
                    for p in fingers
                    for t in targets
                )
                covering |= any(
                    hypot(p[0] - t[0], p[1] - t[1]) < face_width * 0.24
                    for p in palm
                    for t in targets[:3]
                )
        self._hold("face_obstruction", covering, now, 0.5, "Hand across mouth or eye area")
        self._hold("gesture_out_of_view", outside, now, 1, "Gesture crossing camera edge")
        was_outside = self.motion.get("gesture_edge_state", False)
        edges = self.motion.setdefault("gesture_edges", deque())
        while edges and edges[0] < now - 8:
            edges.popleft()
        if outside and not was_outside:
            edges.append(now)
            if len(edges) >= 2:
                self._pulse(
                    "gesture_out_of_view",
                    edges[0],
                    now,
                    f"{len(edges)} gestures crossing the camera edge in 8s",
                )
        self.motion["gesture_edge_state"] = outside
        # Require a stable approach and withdrawal, so boundary jitter is not
        # counted as several separate hand-to-face movements.
        state = self.motion.setdefault(
            "touch_state", dict(active=False, candidate=touching, since=now)
        )
        if touching != state["candidate"]:
            state.update(candidate=touching, since=now)
        if touching != state["active"] and round(now - state["since"], 3) >= 0.18:
            state["active"] = touching
            if touching:
                touches = self.motion.setdefault("touches", deque())
                touches.append(state["since"])
                while touches and touches[0] < now - 10:
                    touches.popleft()
                if len(touches) >= 3:
                    self._pulse(
                        "repeated_face_touching",
                        touches[0],
                        now,
                        f"{len(touches)} hand-to-face movements in 10s",
                    )
        for index, centre in enumerate(sorted(centres)):
            for axis in (0, 1):
                result = self._oscillation(
                    f"hand_motion_{index}_{axis}", centre[axis] / span, now, 0.12, 5, 4
                )
                if result:
                    self._pulse(
                        "repetitive_hand_motion",
                        result[0],
                        now,
                        f"{result[1]} repeated hand movements in 5s",
                    )
        if len(centres) == 2:
            separation = hypot(centres[0][0] - centres[1][0], centres[0][1] - centres[1][1]) / span
            result = self._oscillation(
                "hand_rubbing", separation if separation < 0.5 else None, now, 0.05, 5, 4
            )
            if result:
                self._pulse(
                    "repetitive_hand_motion",
                    result[0],
                    now,
                    "Repeated movement with hands held together",
                )
        if covering:
            self.hands_text = "Near mouth or eyes"
        elif touching:
            self.hands_text = "Near face or hair"
        elif outside:
            self.hands_text = "Gesture outside view"

    def process(self, observation, sequence, timestamp_ms, processing_latency_ms):
        now = timestamp_ms / 1000
        if self.started is None:
            self.started = now
        if self.previous is not None and now - self.previous > 1:
            self._reset_motion(self.previous)
        self.previous = now
        self.frames += 1
        if not observation.person_detected:
            self._reset_motion(now)
            head_side, head_text, head_delta = None, "Not assessed", None
            eye_side, eye_text = None, "Not assessed"
        else:
            head_side, head_text, head_delta = self._head(observation.head, now)
            eye_side, eye_text = self._eyes(observation.eyes, head_delta, now)
            self._direction_runs("eyes", eye_side, now)
            eye_title = {"up": "Lower your gaze", "down": "Raise your gaze"}.get(
                eye_side, CUES["eye_away"]
            )
            self._hold(
                "eye_away",
                None if eye_side is None else eye_side != "centre",
                now,
                1,
                eye_text,
                eye_title,
                recovery_seconds=0,
            )
            if head_side is None:
                self._direction_runs("head", None, now)
                self._hold("head_position", None, now, 2, "")
                self._clear_category("head_", now)
            width = None
            if observation.body_updated:
                self.last_body_at = now
                # Chin movement changes face-to-shoulder distance; it is not
                # evidence that the torso has slumped.
                posture_targets = observation.face_targets if head_side == "centre" else None
                width = self._body(observation.body, posture_targets, now)
            elif "body" in self.baselines:
                width = self.baselines["body"][2]
            if observation.hands_updated:
                self.last_hands_at = now
                self._hands(observation.hands, observation.face_targets, width, now)
            if self.last_body_at is None or now - self.last_body_at > 0.7:
                self.body_text = "Not assessed"
                self._clear_category("body_", now)
                self._hold("posture_drift", None, now, 3, "")
            if self.last_hands_at is None or now - self.last_hands_at > 0.7:
                self._hands(None, None, None, now)
        # One cue, with short-lived pattern reminders above sustained-position cues.
        cue = "Keep presenting naturally"
        if self.active:
            cue = next(reversed(self.active.values()))["title"]
        if self.pulse_cue[0] > now:
            cue = self.pulse_cue[1]
        required = self.settings.live_calibration_frames
        calibrated = "head" in self.baselines and "eyes" in self.baselines
        if not calibrated:
            cue = "Face forward and look at the camera marker"
        elif (
            eye_side is None
            and head_side in {None, "centre"}
            and not self.active
            and self.pulse_cue[0] <= now
        ):
            cue = "Continue naturally"  # No invented eye direction from uncertain landmarks.
        if len(self.events) > self.settings.live_max_session_events:
            closed = [event for event in self.events if event["end"] is not None]
            if closed:
                self.events.remove(closed[0])
        data = dict(
            type="feedback",
            sequence=sequence,
            timestamp_ms=timestamp_ms,
            person_detected=observation.person_detected,
            calibration_complete=calibrated,
            calibration_samples=min(
                len(self.samples.get("head", [])), len(self.samples.get("eyes", []))
            ),
            calibration_required=required,
            message=cue,
            status=dict(eyes=eye_text, head=head_text, body=self.body_text, hands=self.hands_text),
            directions=dict(eyes=eye_side, head=head_side),
            processing_latency_ms=processing_latency_ms,
            debug=observation.debug,
            session_events=self._events(now),
        )
        return LiveFeedback(data)

    def _events(self, now):
        groups = []
        end = float("-inf")
        for event in sorted(self.events, key=lambda e: e["start"]):
            finish = now if event["end"] is None else event["end"]
            if not groups or event["start"] > end:
                groups.append([])
                end = finish
            else:
                end = max(end, finish)
            groups[-1].append(event)
        messages = []
        for group in groups:
            active = [e for e in group if e["end"] is None]
            primary = (active or group)[-1]
            start = min(e["start"] for e in group)
            finish = max(now if e["end"] is None else e["end"] for e in group)
            evidence = list(dict.fromkeys(e["evidence"] for e in group))
            messages.append(
                dict(
                    kind=primary["kind"],
                    title=primary["title"],
                    evidence=" · ".join(evidence),
                    started_at_seconds=round(start - self.started, 1),
                    duration_seconds=round(finish - start, 1),
                    active=bool(active),
                    signals=[
                        dict(kind=e["kind"], title=e["title"], evidence=e["evidence"])
                        for e in group
                    ],
                )
            )
        return messages

    def pause(self, timestamp_ms):
        now = timestamp_ms / 1000
        self._reset_motion(now)
        self.previous = None
        return self._events(now)

    def recalibrate_gaze(self, timestamp_ms):
        self.pause(timestamp_ms)
        self.baselines.clear()
        self.samples.clear()

    def summary(self):
        return dict(
            frames_processed=self.frames,
            session_events=self._events(self.previous or self.started or 0),
        )
