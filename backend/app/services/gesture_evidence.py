"""Conservative temporal movement candidates and bounded video evidence."""

import logging
import math
import subprocess
from pathlib import Path
from statistics import median

logger = logging.getLogger(__name__)


class HeadMovementTracker:
    """Repeated face/neck movement estimates, not eye tracking or clinical head angles."""

    def __init__(self):
        self.samples = []
        self.raw = []

    def reset(self):
        self.samples.clear()
        self.raw.clear()

    def observe(self, timestamp, points):
        if len(points) < 7 or any(points[i][2] < 0.5 for i in (0, 1, 2, 5, 6)):
            self.reset()
            return {}
        width = math.dist(points[5][:2], points[6][:2])
        eyes = math.dist(points[1][:2], points[2][:2])
        if width < 10 or eyes < 8:
            self.reset()
            return {}
        if self.raw and timestamp - self.raw[-1][0] > 0.5:
            self.reset()
        eye_x = (points[1][0] + points[2][0]) / 2
        shoulder_x = (points[5][0] + points[6][0]) / 2
        shoulder_y = (points[5][1] + points[6][1]) / 2
        values = (
            (points[0][0] - eye_x) / eyes,
            (eye_x - shoulder_x) / width,
            ((points[1][1] + points[2][1]) / 2 - shoulder_y) / width,
            # Eye-line slope captures sideways tilt independently of audience
            # turns. This is image-plane movement, not gaze or a 3D head angle.
            (points[2][1] - points[1][1]) / eyes,
        )
        self.raw.append((timestamp, values))
        self.raw = self.raw[-3:]
        smooth = tuple(median(s[1][axis] for s in self.raw) for axis in range(4))
        self.samples.append((timestamp, smooth))
        # Review bursts of repeated movement, not ordinary audience scanning.
        # Head position alone cannot establish gaze, script reading, or intent.
        self.samples = [s for s in self.samples if timestamp - s[0] <= 4.8]
        if self.samples[-1][0] - self.samples[0][0] < 1.2:
            return {}
        for axis, step, extent in (
            (0, 0.18, 0.45), (1, 0.09, 0.22), (2, 0.12, 0.28), (3, 0.08, 0.16)
        ):
            # Repeated sideways tilts can build more slowly than rapid turns.
            # Keep the audience-turn rule strict rather than weakening all axes.
            window = 4.8 if axis == 3 else 3.2
            values = [s[1][axis] for s in self.samples if timestamp - s[0] <= window]
            recent = [s[1][axis] for s in self.samples if timestamp - s[0] <= 0.6 + 1e-6]
            # Stop reporting once the head settles instead of keeping an old
            # burst active until every turn leaves the history window.
            if len(recent) < 2 or max(recent) - min(recent) < step * 0.4:
                continue
            extreme, direction, reversals = values[0], 0, 0
            for value in values[1:]:
                change = value - extreme
                if direction == 0 and abs(change) >= step:
                    direction = 1 if change > 0 else -1
                    extreme = value
                elif direction * change > 0:
                    extreme = value
                elif direction * change <= -step:
                    reversals += 1
                    direction *= -1
                    extreme = value
            required_reversals = 2 if axis == 3 else 3
            if reversals >= required_reversals and max(values) - min(values) >= extent:
                return {"repeated_head_movement": 0.8}
        return {}


class MovementTracker:
    def __init__(self):
        self.samples = []
        self.touches = []
        self.near = False
        self.near_since = None
        self.head = HeadMovementTracker()

    def observe(self, timestamp, points):
        if not points:
            self.samples.clear()
            self.touches.clear()
            self.near = False
            self.near_since = None
            self.head.reset()
            return {}
        width = math.dist(points[5][:2], points[6][:2])
        if width < 10:
            return {}
        hip = (points[11][0] + points[12][0]) / 2
        shoulder = (points[5][0] + points[6][0]) / 2
        if self.samples and (
            abs(hip - self.samples[-1][2]) > width * 0.6
            or not 0.7 < width / self.samples[-1][3] < 1.4
        ):
            self.samples.clear()
            self.touches.clear()
            self.near = False
            self.near_since = None
            self.head.reset()
        # Relative torso movement reduces sensitivity to whole-frame translation.
        self.samples.append((timestamp, (shoulder - hip) / width, hip, width))
        self.samples = [s for s in self.samples if timestamp - s[0] <= 8]
        near = any(
            points[i][2] >= 0.5
            and points[0][2] >= 0.5
            and math.dist(points[i][:2], points[0][:2]) / width < 0.60
            and points[i][1] <= points[0][1] + width * 0.35
            for i in (9, 10)
        )
        if near and not self.near:
            self.near_since = timestamp
            if not self.touches or timestamp - self.touches[-1] >= 1.5:
                self.touches.append(timestamp)
        if not near:
            self.near_since = None
        self.near = near
        self.touches = [t for t in self.touches if timestamp - t <= 15]
        result = self.head.observe(timestamp, points)
        # A held face contact can be reviewed without requiring three repetitions.
        if near and (
            len(self.touches) >= 2
            or (self.near_since is not None and timestamp - self.near_since >= 1.0)
        ):
            result["hand_near_face"] = 0.8
        if self.samples[-1][0] - self.samples[0][0] >= 2:
            values = [s[1] for s in self.samples]
            extreme = values[0]
            direction = 0
            reversals = 0
            for value in values[1:]:
                change = value - extreme
                if abs(change) >= 0.12:
                    new_direction = 1 if change > 0 else -1
                    if direction and new_direction != direction:
                        reversals += 1
                    direction = new_direction
                    extreme = value
                elif direction * change > 0:
                    extreme = value
            hips = [s[2] for s in self.samples]
            if reversals >= 2 and max(hips) - min(hips) < width * 0.5:
                result["repeated_swaying"] = 0.8
        return result


def save_gesture_clips(source: Path, directory: Path, events: list, duration: float):
    retained = [
        event
        for event in events
        if "evidence_index" not in event or event["evidence_index"] is not None
    ]
    for index, event in enumerate(retained, 1):
        lookback = {"hand_near_face": 15, "repeated_swaying": 8, "repeated_head_movement": 6}.get(
            event["type"], 3
        )
        end = min(duration, event["end_seconds"] + 3)
        # Trim context, never the detected event. Long events may need >20s.
        start = max(0, event["start_seconds"] - lookback, min(event["start_seconds"], end - 20))
        target = directory / f"gesture_{index:03d}.mp4"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-v",
                    "error",
                    "-y",
                    "-ss",
                    str(start),
                    "-i",
                    str(source),
                    "-t",
                    str(end - start),
                    "-an",
                    "-vf",
                    "scale=trunc(min(960\\,iw)/2)*2:-2",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-crf",
                    "25",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(target),
                ],
                check=True,
                capture_output=True,
                timeout=90,
            )
            event.update(clip_index=index, clip_start_seconds=start, clip_end_seconds=end)
        except (OSError, subprocess.SubprocessError):
            target.unlink(missing_ok=True)
            logger.exception("Gesture clip %s unavailable", index)
