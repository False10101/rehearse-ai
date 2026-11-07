"""Conservative temporal movement candidates and bounded video evidence."""

import logging
import math
import subprocess
from pathlib import Path
from statistics import median

import cv2
import numpy as np

from app.services.motion_intervals import motion_pattern

logger = logging.getLogger(__name__)


class BackgroundMotion:
    """Track image translation outside the presenter, not presenter movement.

    No new inference model: ordinary optical flow compensates camera pans before
    the sway check measures whole-body side-to-side translation.
    """

    def __init__(self):
        self.previous = None
        self.features = None
        self.offset_x = 0.0

    def observe(self, frame, people):
        height, width = frame.shape[:2]
        scale = 320 / width
        gray = cv2.cvtColor(cv2.resize(frame, (320, max(1, round(height * scale)))),
                            cv2.COLOR_BGR2GRAY)
        known = False
        if self.previous is not None and self.features is not None:
            moved, status, _ = cv2.calcOpticalFlowPyrLK(self.previous, gray, self.features, None)
            if moved is not None and status is not None:
                good = status.reshape(-1) == 1
                shifts = (moved - self.features).reshape(-1, 2)[good]
                if len(shifts) >= 8:
                    dx, dy = np.median(shifts, axis=0)
                    inliers = np.linalg.norm(shifts - [dx, dy], axis=1) < 2.5
                    if float(inliers.mean()) >= 0.7:
                        self.offset_x += float(dx) / scale
                        known = True
        mask = np.full(gray.shape, 255, np.uint8)
        for points in people:
            visible = [(x * scale, y * scale) for x, y, confidence in points if confidence >= 0.3]
            if not visible:
                continue
            xs, ys = zip(*visible)
            # Exclude the torso, head, arms and a margin, not only keypoint pixels.
            padding = max(15, (max(xs) - min(xs)) * 0.25)
            cv2.rectangle(mask, (max(0, int(min(xs) - padding)), max(0, int(min(ys) - padding))),
                          (min(gray.shape[1] - 1, int(max(xs) + padding)),
                           min(gray.shape[0] - 1, int(max(ys) + padding))), 0, -1)
        self.features = cv2.goodFeaturesToTrack(gray, maxCorners=100, qualityLevel=0.01,
                                              minDistance=7, mask=mask)
        self.previous = gray
        return self.offset_x if known else None


class HeadMovementTracker:
    """Repeated face/neck movement estimates, not eye tracking or clinical head angles."""

    def __init__(self):
        self.samples = []
        self.raw = []
        self.evidence = {}

    def reset(self):
        self.samples.clear()
        self.raw.clear()
        self.evidence = {}

    def observe(self, timestamp, points):
        self.evidence = {}
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
            required_reversals = 2 if axis == 3 else 3
            series = [(s[0], s[1][axis]) for s in self.samples if timestamp - s[0] <= window]
            pattern = motion_pattern(series, step, extent, required_reversals)
            if pattern:
                self.evidence = {"repeated_head_movement": {
                    "body_part": "head", "axis": (
                        "side to side", "side to side", "up and down", "in sideways tilts"
                    )[axis], **pattern,
                }}
                return {"repeated_head_movement": 0.8}
        return {}


class MovementTracker:
    def __init__(self):
        self.samples = []
        self.touches = []
        self.near = False
        self.near_since = None
        self.head = HeadMovementTracker()
        self.evidence = {}
        self.body_samples = []
        self.body_origin = None
        self.body_width = None

    def observe(self, timestamp, points, camera_offset_x=None):
        self.evidence = {}
        if not points:
            self.samples.clear()
            self.touches.clear()
            self.near = False
            self.near_since = None
            self.head.reset()
            self.body_samples.clear()
            self.body_origin = None
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
            self.body_samples.clear()
            self.body_origin = None
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
        self.evidence.update(self.head.evidence)
        # A held face contact can be reviewed without requiring three repetitions.
        if near and (
            len(self.touches) >= 2
            or (self.near_since is not None and timestamp - self.near_since >= 1.0)
        ):
            result["hand_near_face"] = 0.8
            wrist = min((i for i in (9, 10) if points[i][2] >= 0.5),
                        key=lambda i: math.dist(points[i][:2], points[0][:2]))
            self.evidence["hand_near_face"] = {
                "body_part": "your left hand" if wrist == 9 else "your right hand",
                "approaches": len(self.touches),
                "near_hold_seconds": round(timestamp - self.near_since, 2),
                "pattern_start_seconds": self.near_since,
            }
        if self.samples[-1][0] - self.samples[0][0] >= 2:
            pattern = motion_pattern([(s[0], s[1]) for s in self.samples], 0.12, 0.24, 2)
            hips = [s[2] for s in self.samples]
            if pattern and max(hips) - min(hips) < width * 0.5:
                result["repeated_swaying"] = 0.8
                self.evidence["repeated_swaying"] = {
                    "body_part": "torso", "axis": "torso lean", **pattern,
                }
        # A rigid side-to-side weight shift moves shoulders AND hips, so it is
        # invisible to shoulder-minus-hip lean alone. Only measure it when the
        # background supplies camera-motion compensation.
        if camera_offset_x is None:
            self.body_samples.clear()
            self.body_origin = None
        else:
            corrected = hip - camera_offset_x
            if self.body_origin is None:
                self.body_origin, self.body_width = corrected, width
            self.body_samples.append((timestamp, (corrected - self.body_origin) / self.body_width))
            self.body_samples = [s for s in self.body_samples if timestamp - s[0] <= 6]
            pattern = motion_pattern(self.body_samples, 0.12, 0.24, 2)
            if pattern:
                result["repeated_swaying"] = 0.8
                self.evidence["repeated_swaying"] = {
                    "body_part": "torso", "axis": "whole-body lateral shifting", **pattern,
                }
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
                    "veryfast",
                    "-threads",
                    "2",
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
