"""Bounded upload parallelism with serialized, monotonic progress writes."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

logger = logging.getLogger(__name__)


class PracticeProgress:
    def __init__(self, save):
        self._save = save
        self._lock = Lock()
        self._tracks = {
            "gestures": {"status": "queued", "label": "Waiting to review body language",
                         "progress_percent": 0},
            "speech": {"status": "queued", "label": "Waiting to review speech",
                       "progress_percent": 0},
        }

    def update(self, track, percent, label, status="running"):
        # Each worker uses a fresh DB session through save. This lock also keeps
        # an older snapshot from overwriting newer progress from the other track.
        with self._lock:
            previous = self._tracks[track]["progress_percent"]
            self._tracks[track] = {
                "status": status, "label": label,
                "progress_percent": max(previous, min(100, max(0, int(percent)))),
            }
            total = (self._tracks["gestures"]["progress_percent"] * .65
                     + self._tracks["speech"]["progress_percent"] * .35)
            self._save(
                progress_percent=20 + round(total * .75),
                pose_tracking={"processing": {k: dict(v) for k, v in self._tracks.items()}},
            )


def run_practice_tracks(gestures, speech):
    # The executor joins BOTH workers even if one raises. The caller must not
    # delete source/audio/evidence files while a surviving worker still uses them.
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="recording-review") as pool:
        futures = {pool.submit(gestures): "gestures", pool.submit(speech): "speech"}
        results = {}
        for future in as_completed(futures):
            name = futures[future]
            try:
                results[name] = future.result()
            except Exception:
                logger.exception("Recording %s track failed", name)
                for other in futures:
                    other.cancel()
                raise
    return results["gestures"], results["speech"]
