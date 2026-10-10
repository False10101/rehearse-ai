from app.core.config import Settings
from app.services.live_coaching import DebugBounds, FrameObservation, LiveCoachingTracker


def settings() -> Settings:
    return Settings(
        live_front_facing_low=0.6,
        live_front_facing_high=0.7,
        live_front_facing_window_seconds=10.0,
        live_front_facing_yaw_threshold=0.16,
        live_thinking_grace_seconds=2.0,
        live_gaze_calibration_frames=2,
        live_gaze_horizontal_threshold=0.10,
        live_gaze_vertical_threshold=0.12,
        live_gaze_smoothing_frames=5,
        live_head_yaw_threshold=0.22,
        live_head_yaw_recovery_threshold=0.14,
        live_head_yaw_grace_seconds=0.75,
        live_event_recovery_seconds=0.75,
    )


def observation(
    gaze_position: tuple[float, float] = (0.5, 0.5),
    head_yaw: float = 0.0,
) -> FrameObservation:
    return FrameObservation(
        person_detected=True,
        left_gaze_position=gaze_position,
        right_gaze_position=gaze_position,
        head_yaw=head_yaw,
        debug={"face": DebugBounds(0.2, 0.1, 0.6, 0.7).as_message()},
    )


def test_tracker_calibrates_then_detects_sustained_iris_look_away() -> None:
    tracker = LiveCoachingTracker(settings())
    first = tracker.process(observation(), 1, 1_000, 20)
    second = tracker.process(observation(), 2, 1_100, 20)
    brief = tracker.process(observation((0.7, 0.5)), 3, 2_000, 20)
    extended = tracker.process(observation((0.7, 0.5)), 4, 4_100, 20)

    assert first.calibration_complete is False
    assert second.calibration_complete is True
    assert brief.gaze_on_camera is False
    assert brief.message == "Your delivery signals look balanced."
    assert extended.extended_look_away_seconds == 2.1
    assert extended.message == "Return your eyes to the camera when you finish your thought."
    assert extended.debug is not None
    assert extended.debug["gaze_offset"] == {"x": 0.2, "y": 0.0}
    assert extended.session_events[0]["kind"] == "extended_look_away"


def test_front_facing_ratio_uses_head_yaw_not_iris_gaze() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(head_yaw=0.0), 1, 1_000, 10)
    tracker.process(observation(head_yaw=0.30), 2, 6_000, 10)
    feedback = tracker.process(observation(head_yaw=0.30), 3, 11_000, 10)

    assert feedback.front_facing is False
    assert feedback.front_facing_ratio == 0.333
    assert any(event["kind"] == "fronting_balance" for event in feedback.session_events)


def test_iris_look_away_does_not_change_front_facing_ratio() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)
    feedback = tracker.process(observation((0.7, 0.5), head_yaw=0.0), 3, 2_000, 10)

    assert feedback.gaze_on_camera is False
    assert feedback.front_facing is True
    assert feedback.front_facing_ratio == 1.0


def test_diagonal_corner_glance_is_outside_elliptical_gaze_zone() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)

    feedback = tracker.process(observation((0.58, 0.59)), 3, 1_200, 10)

    assert feedback.gaze_on_camera is False


def test_one_diverted_eye_cannot_be_cancelled_by_the_other_eye() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)
    feedback = tracker.process(
        FrameObservation(
            person_detected=True,
            left_gaze_position=(0.65, 0.5),
            right_gaze_position=(0.5, 0.5),
            head_yaw=0.0,
        ),
        3,
        1_200,
        10,
    )

    assert feedback.gaze_on_camera is False


def test_tracker_records_head_yaw_only_after_grace_period() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)
    brief = tracker.process(observation(head_yaw=0.3), 3, 1_200, 10)
    sustained = tracker.process(observation(head_yaw=0.3), 4, 2_000, 10)

    assert brief.head_yaw == "turned"
    assert brief.session_events == []
    assert brief.message == "Your delivery signals look balanced."
    assert sustained.session_events[0]["kind"] == "head_yaw"
    assert sustained.message == "Turn your head back toward the camera."


def test_tracker_only_cues_for_missing_eyes_after_the_grace_period() -> None:
    tracker = LiveCoachingTracker(settings())
    brief = tracker.process(FrameObservation(person_detected=True, head_yaw=0.0), 1, 1_000, 12)
    sustained = tracker.process(
        FrameObservation(person_detected=True, head_yaw=0.0), 2, 1_900, 12
    )

    assert brief.gaze_on_camera is None
    assert brief.message == "Look at the marker while eye contact is calibrated."
    assert sustained.message == "Keep both eyes visible to begin eye-contact coaching."
    assert sustained.front_facing is True


def test_tracker_recalibrates_gaze_without_resetting_fronting_history() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)
    tracker.process(observation((0.7, 0.5)), 3, 2_000, 10)
    tracker.process(observation((0.7, 0.5)), 4, 4_100, 10)
    tracker.recalibrate_gaze(4_200)
    refreshed = tracker.process(observation(), 5, 4_500, 10)

    assert refreshed.calibration_complete is False
    assert refreshed.calibration_samples == 1
    assert refreshed.front_facing_ratio == 1.0
    assert refreshed.session_events[0]["active"] is False


def test_tracker_waits_for_stable_gaze_calibration_samples() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation((0.35, 0.5)), 1, 1_000, 10)
    unstable = tracker.process(observation((0.65, 0.5)), 2, 1_100, 10)
    tracker.process(observation(), 3, 1_200, 10)
    stable = tracker.process(observation(), 4, 1_300, 10)

    assert unstable.calibration_complete is False
    assert unstable.message == "Hold your gaze steady on the marker to finish calibration."
    assert stable.calibration_complete is True


def test_tracker_tolerates_one_brief_missing_iris_observation() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)
    tracker.process(observation((0.7, 0.5)), 3, 2_000, 10)
    tracker.process(FrameObservation(person_detected=True, head_yaw=0.0), 4, 2_400, 10)
    extended = tracker.process(observation((0.7, 0.5)), 5, 4_100, 10)

    assert extended.extended_look_away_seconds == 2.1
    assert extended.session_events[0]["kind"] == "extended_look_away"


def test_pause_closes_active_events() -> None:
    tracker = LiveCoachingTracker(settings())
    tracker.process(observation(), 1, 1_000, 10)
    tracker.process(observation(), 2, 1_100, 10)
    tracker.process(observation((0.7, 0.5)), 3, 2_000, 10)
    tracker.process(observation((0.7, 0.5)), 4, 4_100, 10)

    events = tracker.pause(4_200)

    assert events[0]["active"] is False
    assert events[0]["duration_seconds"] == 2.2
