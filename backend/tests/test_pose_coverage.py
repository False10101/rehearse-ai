from app.services.pose_coverage import PoseCoverage
from app.services.upload_practice import build_coaching_report


def body():
    points = [(100.0, 100.0, 0.9) for _ in range(17)]
    points[5] = (100.0, 100.0, 0.9)
    points[6] = (200.0, 100.0, 0.9)
    points[0] = (150.0, 50.0, 0.9)
    points[1] = (140.0, 40.0, 0.9)
    points[2] = (160.0, 40.0, 0.9)
    return points


def test_no_person_is_insufficient_not_a_clean_result():
    tracker = PoseCoverage(10, 0.2)
    for index in range(50):
        tracker.observe(index * 0.2, [], False, 640, 480)
    result = tracker.result()
    assert result["status"] == "insufficient"
    assert result["sample_count"] == 50
    assert result["person_visible_percent"] == 0
    assert result["unavailable_seconds"]["no_person"] == 10
    assert all(check["status"] == "insufficient" for check in result["checks"])


def test_detected_person_with_unreliable_body_is_distinct():
    tracker = PoseCoverage(10, 0.2)
    for index in range(50):
        tracker.observe(index * 0.2, body(), False, 640, 480)
    result = tracker.result()
    assert result["person_visible_percent"] == 100
    assert result["reliable_body_percent"] == 0
    assert result["unavailable_seconds"]["unreliable_body"] == 10


def test_reliable_tracking_with_no_event_is_assessable():
    tracker = PoseCoverage(10, 0.2)
    for index in range(50):
        tracker.observe(index * 0.2, body(), True, 640, 480)
    result = tracker.result()
    assert result["status"] == "reliable"
    assert result["reliable_body_percent"] == 100
    assert all(check["coverage_percent"] == 100 for check in result["checks"])


def test_missing_elbow_limits_only_checks_that_need_it():
    tracker = PoseCoverage(10, 0.2)
    points = body()
    points[7] = (100, 100, 0.0)
    for index in range(50):
        tracker.observe(index * 0.2, points, True, 640, 480)
    result = tracker.result()
    checks = {check["type"]: check for check in result["checks"]}
    assert result["status"] == "limited"
    assert checks["arms_crossed"]["status"] == "reliable"  # Other arm still assessable.
    assert checks["gesture_box_excursion"]["status"] == "insufficient"
    assert checks["hands_clasped_low"]["status"] == "reliable"
    assert checks["repeated_swaying"]["status"] == "reliable"


def test_out_of_frame_wrist_cannot_count_as_trackable():
    tracker = PoseCoverage(10, 0.2)
    points = body()
    points[9] = (-10, 100, 0.9)
    for index in range(50):
        tracker.observe(index * 0.2, points, True, 640, 480)
    checks = {check["type"]: check for check in tracker.result()["checks"]}
    assert checks["hands_clasped_low"]["coverage_percent"] == 0
    assert checks["hand_near_face"]["coverage_percent"] == 100  # Other hand visible.


def test_interrupted_decode_counts_unassessed_recording():
    tracker = PoseCoverage(10, 0.2)
    for index in range(10):
        tracker.observe(index * 0.2, body(), True, 640, 480)
    result = tracker.result()
    assert result["reliable_body_percent"] == 20
    assert result["unassessed_seconds"] == 8
    assert result["status"] != "reliable"


def test_fragmented_tracking_is_not_enough_for_temporal_checks():
    tracker = PoseCoverage(10, 0.2)
    for index in range(50):
        tracker.observe(index * 0.2, body(), index % 10 != 0, 640, 480)
    checks = {check["type"]: check for check in tracker.result()["checks"]}
    assert checks["repeated_swaying"]["coverage_percent"] == 90
    assert checks["repeated_swaying"]["status"] == "insufficient"
    assert checks["hands_clasped_low"]["status"] == "reliable"


def test_no_false_positive_body_strength_for_unknown_or_limited_coverage():
    for tracking in (None, {"status": "insufficient"}, {"status": "limited"}):
        report = build_coaching_report({}, [], tracking)
        assert not any("posture" in line for line in report["strengths"])
    report = build_coaching_report({}, [], {"status": "reliable"})
    assert any("posture" in line for line in report["strengths"])


def test_pose_pipeline_records_visibility_even_without_gesture_events(monkeypatch, tmp_path):
    import sys
    from types import SimpleNamespace

    import numpy as np

    from app.services import upload_practice

    class Tensor:
        def __init__(self, values):
            self.values = values

        def cpu(self):
            return self

        def tolist(self):
            return self.values

    class Points:
        def __init__(self, points):
            self.xy = Tensor([[list(p[:2]) for p in points]])
            self.conf = Tensor([[p[2] for p in points]])

        def __len__(self):
            return 1

    class Capture:
        def __init__(self):
            self.remaining = 50

        def isOpened(self):
            return True

        def get(self, prop):
            return 5 if prop == upload_practice.cv2.CAP_PROP_FPS else 50

        def read(self):
            self.remaining -= 1
            return (
                (True, np.zeros((480, 640, 3), dtype=np.uint8))
                if self.remaining >= 0
                else (False, None)
            )

        def release(self):
            pass

    monkeypatch.setattr(upload_practice.cv2, "VideoCapture", lambda *args: Capture())
    monkeypatch.setattr(
        upload_practice,
        "get_settings",
        lambda: SimpleNamespace(
            upload_practice_pose_model="test",
            upload_practice_sample_fps=5,
            upload_practice_max_evidence_frames=12,
        ),
    )
    # Isolate visibility telemetry from gesture scoring; no events in every scenario.
    monkeypatch.setattr(upload_practice, "classify_pose", lambda points: {})
    monkeypatch.setattr(
        upload_practice,
        "MovementTracker",
        lambda: SimpleNamespace(
            observe=lambda *args: {},
        ),
    )
    for points, expected in (([], "insufficient"), (body(), "reliable")):
        result = (
            SimpleNamespace(keypoints=Points(points)) if points else SimpleNamespace(keypoints=None)
        )
        monkeypatch.setitem(
            sys.modules,
            "ultralytics",
            SimpleNamespace(
                YOLO=lambda name: SimpleNamespace(predict=lambda *args, **kwargs: [result]),
            ),
        )
        tracking = {}
        assert (
            upload_practice.analyze_pose(tmp_path / "test.mp4", tmp_path, tracking=tracking) == []
        )
        assert tracking["status"] == expected
        assert tracking["sample_count"] == 50
