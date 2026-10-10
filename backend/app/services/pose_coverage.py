"""Visibility telemetry, independent of gesture scores and event thresholds."""

import math

CHECKS = {
    "repeated_head_movement": ("Repeated head movement", (0, 1, 2, 5, 6), 1.8),
    "hands_clasped_low": ("Hands resting together", (5, 6, 9, 10, 11, 12), 0.8),
    "arms_crossed": ("Arms crossing the body", (5, 6), 0.4),
    "gesture_box_excursion": ("Wide arm extensions", (5, 6, 7, 8, 9, 10, 11, 12), 0.4),
    "repeated_swaying": ("Repeated torso swaying", (5, 6, 11, 12), 3.0),
    "hand_near_face": ("Repeated movements near the face", (0, 5, 6), 2.0),
}


class PoseCoverage:
    def __init__(self, duration: float, interval: float):
        self.duration = max(0.0, duration)
        self.interval = interval
        self.samples = 0
        self.person_seconds = 0.0
        self.reliable_seconds = 0.0
        self.sampled_seconds = 0.0
        self.reasons = {"no_person": 0.0, "unreliable_body": 0.0}
        self.check_seconds = dict.fromkeys(CHECKS, 0.0)
        self.longest = dict.fromkeys(CHECKS, 0.0)
        self.current = dict.fromkeys(CHECKS, 0.0)

    def observe(self, timestamp, points, accepted, width, height):
        span = min(self.interval, max(0.0, self.duration - timestamp))
        self.samples += 1
        self.sampled_seconds += span
        if points:
            self.person_seconds += span
        if accepted:
            self.reliable_seconds += span
        else:
            self.reasons["unreliable_body" if points else "no_person"] += span

        def visible(index, confidence=0.25):
            return (
                index < len(points)
                and points[index][2] >= confidence
                and 0 <= points[index][0] < width
                and 0 <= points[index][1] < height
            )

        for kind, (_, indices, _) in CHECKS.items():
            ready = accepted and all(visible(index) for index in indices)
            # Static classifiers share a torso/hands prerequisite before any check runs.
            if kind == "hands_clasped_low":
                ready = ready and all(visible(i) for i in (5, 6, 9, 10, 11, 12))
            else:
                ready = ready and math.dist(points[5][:2], points[6][:2]) >= 10
            if kind == "hand_near_face":
                ready = ready and visible(0, 0.5) and (visible(9, 0.5) or visible(10, 0.5))
            if kind == "arms_crossed":
                ready = ready and ((visible(7) and visible(9)) or (visible(8) and visible(10)))
            if kind == "repeated_head_movement":
                ready = ready and all(visible(i, 0.5) for i in (0, 1, 2, 5, 6))
                ready = ready and math.dist(points[1][:2], points[2][:2]) >= 8
            self.current[kind] = self.current[kind] + span if ready else 0.0
            self.longest[kind] = max(self.longest[kind], self.current[kind])
            if ready:
                self.check_seconds[kind] += span

    def result(self):
        def percent(seconds):
            return round(min(100.0, 100 * seconds / self.duration), 1) if self.duration else 0.0

        checks = []
        for kind, (label, _, minimum) in CHECKS.items():
            seconds = self.check_seconds[kind]
            coverage = percent(seconds)
            status = (
                "reliable"
                if coverage >= 80 and self.longest[kind] >= minimum
                else "limited"
                if self.longest[kind] >= minimum
                else "insufficient"
            )
            checks.append(
                {
                    "type": kind,
                    "label": label,
                    "status": status,
                    "coverage_percent": coverage,
                    "tracked_seconds": round(seconds, 2),
                    "longest_tracked_seconds": round(self.longest[kind], 2),
                }
            )
        status = (
            "reliable"
            if all(c["status"] == "reliable" for c in checks)
            else "insufficient"
            if all(c["status"] == "insufficient" for c in checks)
            else "limited"
        )
        return {
            "version": 1,
            "status": status,
            "sample_count": self.samples,
            "sampled_seconds": round(self.sampled_seconds, 2),
            "duration_seconds": round(self.duration, 2),
            "person_visible_percent": percent(self.person_seconds),
            "reliable_body_percent": percent(self.reliable_seconds),
            "reliable_body_seconds": round(self.reliable_seconds, 2),
            "unassessed_seconds": round(max(0, self.duration - self.sampled_seconds), 2),
            "unavailable_seconds": {k: round(v, 2) for k, v in self.reasons.items()},
            "checks": checks,
        }
