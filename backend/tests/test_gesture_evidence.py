from app.services.gesture_evidence import HeadMovementTracker, MovementTracker, save_gesture_clips


def head_points(yaw=0, translate=0):
    p = points()
    p[1], p[2] = (90, 40, 0.9), (110, 40, 0.9)
    p[0] = (100 + yaw * 20, 50, 0.9)
    return [(x + translate, y, c) for x, y, c in p]


def test_repeated_head_turns_detected_and_missing_face_resets():
    import math

    tracker = HeadMovementTracker()
    results = [tracker.observe(i / 5, head_points(0.4 * math.sin(i / 5 * 3))) for i in range(45)]
    assert any("repeated_head_movement" in r for r in results)
    tracker.observe(10, [])
    assert tracker.observe(10.2, head_points()) == {}


def test_small_head_jitter_and_whole_body_motion_are_not_head_events():
    import math

    for mode in ("jitter", "translation", "single_glance"):
        tracker = HeadMovementTracker()
        for i in range(45):
            yaw = (
                0.04 * math.sin(i)
                if mode == "jitter"
                else 0.5
                if mode == "single_glance" and i > 10
                else 0
            )
            translate = 20 * math.sin(i / 5) if mode == "translation" else 0
            assert tracker.observe(i / 5, head_points(yaw, translate)) == {}


def test_audience_turns_with_settled_positions_are_not_flagged():
    tracker = HeadMovementTracker()
    # Turn to another part of the audience and stay there between points.
    positions = [0, 0.5, 0, -0.5, 0, 0.5]
    for i in range(90):
        assert tracker.observe(i / 5, head_points(positions[i // 15])) == {}


def test_slow_continuous_audience_scan_is_not_flagged():
    import math

    tracker = HeadMovementTracker()
    for i in range(100):
        assert tracker.observe(i / 5, head_points(0.5 * math.sin(i / 5 * 0.7))) == {}


def test_head_burst_stops_promptly_when_presenter_settles():
    import math

    tracker = HeadMovementTracker()
    results = [tracker.observe(i / 5, head_points(0.4 * math.sin(i / 5 * 3))) for i in range(45)]
    assert any("repeated_head_movement" in result for result in results)
    for i in range(45, 60):
        result = tracker.observe(i / 5, head_points())
        if i >= 49:
            assert result == {}


def tilted_head_points(tilt):
    p = head_points()
    p[1], p[2] = (90, 40 - tilt * 10, 0.9), (110, 40 + tilt * 10, 0.9)
    return p


def test_repeated_sideways_tilts_detected_without_rapid_yaw():
    import math

    tracker = HeadMovementTracker()
    results = [tracker.observe(i / 5, tilted_head_points(0.3 * math.sin(i / 5 * 1.8))) for i in range(60)]
    assert any("repeated_head_movement" in result for result in results)
    for i in range(60, 70):
        result = tracker.observe(i / 5, tilted_head_points(0))
        if i >= 64:
            assert result == {}


def test_small_tilt_jitter_or_one_held_tilt_not_flagged():
    import math

    for mode in ("jitter", "held"):
        tracker = HeadMovementTracker()
        for i in range(60):
            tilt = 0.04 * math.sin(i) if mode == "jitter" else (0.3 if i >= 10 else 0)
            assert tracker.observe(i / 5, tilted_head_points(tilt)) == {}


def test_held_downward_head_position_not_called_repeated_movement():
    tracker = HeadMovementTracker()
    for i in range(60):
        p = head_points()
        if i >= 10:
            for index in (0, 1, 2):
                x, y, confidence = p[index]
                p[index] = (x, y + 25, confidence)
        assert tracker.observe(i / 5, p) == {}


def test_moderate_repeated_tilts_are_detected():
    import math

    tracker = HeadMovementTracker()
    results = [tracker.observe(i / 5, tilted_head_points(0.12 * math.sin(i / 5 * 1.8))) for i in range(60)]
    assert any("repeated_head_movement" in result for result in results)


def points(lean=0, near=False):
    p = [(100.0, 50.0, 0.9)] * 17
    p[5], p[6] = (50.0 + lean, 100.0, 0.9), (150.0 + lean, 100.0, 0.9)
    p[11], p[12] = (50.0, 200.0, 0.9), (150.0, 200.0, 0.9)
    p[9], p[10] = ((100.0, 55.0, 0.9) if near else (20.0, 180.0, 0.9)), (180.0, 180.0, 0.9)
    return p


def test_neutral_and_single_adjustment_not_flagged():
    tracker = MovementTracker()
    for i in range(80):
        assert not tracker.observe(i / 5, points(near=5 <= i <= 8))


def test_repeated_face_movements_require_two_approaches():
    tracker = MovementTracker()
    assert not tracker.observe(0, points(near=True))
    tracker.observe(1, points())
    assert "hand_near_face" in tracker.observe(2, points(near=True))
    tracker.observe(3, points())
    assert "hand_near_face" in tracker.observe(4, points(near=True))
    tracker.observe(5, [])
    assert not tracker.observe(6, points(near=True))


def test_held_hand_near_face_does_not_need_repeated_approaches():
    tracker = MovementTracker()
    results = [tracker.observe(i / 5, points(near=True)) for i in range(8)]
    assert any("hand_near_face" in result for result in results)


def test_hand_near_face_stops_when_hand_is_lowered_despite_recent_approaches():
    tracker = MovementTracker()
    tracker.observe(0, points(near=True))
    tracker.observe(1, points())
    assert "hand_near_face" in tracker.observe(2, points(near=True))
    assert "hand_near_face" not in tracker.observe(2.2, points())
    assert "hand_near_face" not in tracker.observe(3, points())


def test_clips_cover_event_end_and_are_created_for_every_event(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(
        "app.services.gesture_evidence.subprocess.run",
        lambda command, **kwargs: commands.append(command),
    )
    events = [
        dict(type="hand_near_face", start_seconds=95, end_seconds=100.4, evidence_index=i + 1)
        for i in range(14)
    ]
    save_gesture_clips(tmp_path / "source.mp4", tmp_path, events, 116)
    assert len(commands) == 14
    for event in events:
        assert event["clip_start_seconds"] <= event["start_seconds"]
        assert event["clip_end_seconds"] >= event["end_seconds"]
        assert event["clip_end_seconds"] - event["clip_start_seconds"] <= 20


def test_long_event_is_not_cut_off_to_fit_context_limit(monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.gesture_evidence.subprocess.run", lambda *a, **kw: None)
    events = [dict(type="arms_crossed", start_seconds=10, end_seconds=40, evidence_index=1)]
    save_gesture_clips(tmp_path / "source.mp4", tmp_path, events, 60)
    assert events[0]["clip_start_seconds"] <= 10
    assert events[0]["clip_end_seconds"] >= 40


def test_repeated_swaying_and_missing_tracking_reset():
    import math

    tracker = MovementTracker()
    results = [tracker.observe(i / 5, points(lean=20 * math.sin(i / 5 * 3))) for i in range(40)]
    assert any("repeated_swaying" in r for r in results)
    tracker.observe(9, [])
    assert not tracker.observe(10, points())


def test_clip_failure_does_not_claim_video(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise OSError("unavailable")

    monkeypatch.setattr("app.services.gesture_evidence.subprocess.run", fail)
    events = [dict(type="arms_crossed", start_seconds=1, end_seconds=3)]
    save_gesture_clips(tmp_path / "source.mp4", tmp_path, events, 10)
    assert "clip_index" not in events[0]
