from dataclasses import replace

import pytest

from app.api.v1.live import _client_observation
from app.core.config import Settings
from app.services.live_coaching import FrameObservation, LiveCoachingTracker

TARGETS = [(0.5, 0.4), (0.46, 0.32), (0.54, 0.32), (0.5, 0.22)]
NEUTRAL = FrameObservation(
    person_detected=True, head=(0, 0, 0), eyes=(0.5, 0.5, 0.5, 0.5), face_targets=TARGETS
)


def body(cx=0.5, cy=0.58, width=0.3, hipx=0.5):
    p = [[0.5, 0.7, 0, 1] for _ in range(33)]
    p[11] = [cx - width / 2, cy, 0, 1]
    p[12] = [cx + width / 2, cy, 0, 1]
    p[23] = [hipx - 0.1, 0.88, 0, 1]
    p[24] = [hipx + 0.1, 0.88, 0, 1]
    return p


def hand(x=0.3, y=0.75):
    return [[x, y, 0, 1] for _ in range(21)]


def drive(t, obs, seconds, step=0.1):
    timestamp = round((t.previous if t.previous is not None else 0) * 1000)
    for _ in range(round(seconds / step)):
        timestamp += round(step * 1000)
        result = t.process(obs, t.frames + 1, timestamp, 0).as_message()
    return result


def ready(with_body=False):
    t = LiveCoachingTracker(Settings(live_calibration_frames=3))
    drive(t, replace(NEUTRAL, body=body() if with_body else None), 3)
    return t


def kinds(r):
    return {s["kind"] for e in r["session_events"] for s in e["signals"]}


@pytest.mark.parametrize(
    "side,head,eye",
    [
        ("left", (25, 0, 0), (0.7, 0.5)),
        ("right", (-25, 0, 0), (0.3, 0.5)),
        ("up", (0, 25, 0), (0.5, 0.3)),
        ("down", (0, -25, 0), (0.5, 0.7)),
    ],
)
@pytest.mark.parametrize("mode", ["eyes", "head", "both"])
def test_first_frame_direction_exact_threshold_and_recovery(side, head, eye, mode):
    t = ready()
    obs = replace(
        NEUTRAL,
        head=head if mode != "eyes" else (0, 0, 0),
        eyes=(*eye, *eye) if mode != "head" else NEUTRAL.eyes,
    )
    first = drive(t, obs, 0.1)
    assert first["directions"]["eyes" if mode == "eyes" else "head"] == side
    if mode == "eyes":
        assert first["session_events"] == []
        assert drive(t, obs, 0.9)["session_events"] == []
        threshold = drive(t, obs, 0.1)
        assert "eye_away" in kinds(threshold)
        assert threshold["session_events"][0]["duration_seconds"] == 1
    else:
        assert first["session_events"] == []
        assert first["directions"]["eyes"] is None
        assert drive(t, obs, 1.9)["session_events"] == []
        threshold = drive(t, obs, 0.1)
        assert "head_position" in kinds(threshold)
        assert threshold["session_events"][0]["duration_seconds"] == 2
    returned = drive(t, NEUTRAL, 1)
    assert returned["directions"] == dict(eyes="centre", head="centre")
    assert all(not e["active"] for e in returned["session_events"])


@pytest.mark.parametrize("roll,side", [(-25, "tilt_left"), (25, "tilt_right")])
def test_sideways_head_tilt(roll, side):
    r = drive(ready(), replace(NEUTRAL, head=(0, 0, roll)), 2.2)
    assert r["directions"]["head"] == side and "head_position" in kinds(r)


def test_fast_no_does_not_require_two_second_hold():
    t = ready()
    for yaw in [25, -25, 25]:
        r = drive(t, replace(NEUTRAL, head=(yaw, 0, 0)), 0.2)
    assert "head_shaking" in kinds(r) and "head_position" not in kinds(r)


def test_repeated_nods_are_separate_from_one_nod():
    t = ready()
    for pitch in [20, 0]:
        r = drive(t, replace(NEUTRAL, head=(0, pitch, 0)), 0.2)
    assert "head_nodding" not in kinds(r)
    for pitch in [20, -20, 20]:
        r = drive(t, replace(NEUTRAL, head=(0, pitch, 0)), 0.2)
    assert "head_nodding" in kinds(r)


def test_repeated_eye_only_glances():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 0.5)
        r = drive(t, NEUTRAL, 0.5)
    assert "repeated_glances" in kinds(r)
    assert "head_position" not in kinds(r)
    assert "3 glances left" in str(r["session_events"])


def test_rapid_eye_only_switching():
    t = ready()
    for eye in [(0.7, 0.5), (0.5, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.5), (0.3, 0.5), (0.5, 0.3)]:
        r = drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 0.4)
    assert "gaze_switching" in kinds(r) and r["directions"]["head"] == "centre"


def test_repeated_short_head_turns():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, head=(20, 0, 0)), 0.5)
        r = drive(t, NEUTRAL, 0.5)
    assert "repeated_head_turns" in kinds(r) and "head_position" not in kinds(r)


@pytest.mark.parametrize(
    "kind,values",
    [
        ("body_swaying", [dict(cx=x) for x in [0.58, 0.42, 0.58, 0.42, 0.58]]),
        ("body_bouncing", [dict(cy=y) for y in [0.64, 0.52, 0.64, 0.52, 0.64]]),
        ("body_rocking", [dict(width=w) for w in [0.39, 0.24, 0.39, 0.24, 0.39]]),
    ],
)
def test_repeated_body_motion(kind, values):
    t = ready(True)
    for v in values:
        r = drive(t, replace(NEUTRAL, body=body(**v)), 0.4)
    assert kind in kinds(r)


@pytest.mark.parametrize(
    "values,targets",
    [(dict(hipx=0.35), TARGETS), (dict(width=0.4), TARGETS), ({}, [(0.5, 0.47), *TARGETS[1:]])],
)
def test_posture_drift(values, targets):
    r = drive(ready(True), replace(NEUTRAL, body=body(**values), face_targets=targets), 3.2)
    assert "posture_drift" in kinds(r)


def test_face_obstruction():
    assert "face_obstruction" in kinds(
        drive(ready(), replace(NEUTRAL, hands=[hand(0.5, 0.4)]), 0.7)
    )


def test_repeated_hand_to_face_movements():
    t = ready()
    near = hand()
    near[8] = [0.5, 0.22, 0, 1]
    for _ in range(3):
        drive(t, replace(NEUTRAL, hands=[near]), 0.4)
        r = drive(t, replace(NEUTRAL, hands=[hand()]), 0.4)
    assert "repeated_face_touching" in kinds(r)


def test_repetitive_hand_movement():
    t = ready(True)
    for x in [0.3, 0.4, 0.3, 0.4, 0.3, 0.4, 0.3]:
        r = drive(t, replace(NEUTRAL, body=body(), hands=[hand(x)]), 0.3)
    assert "repetitive_hand_motion" in kinds(r)


def test_symmetric_hands_together_motion_is_not_cancelled():
    t = ready(True)
    for d in [0.02, 0.07, 0.02, 0.07, 0.02, 0.07, 0.02]:
        r = drive(
            t, replace(NEUTRAL, body=body(), hands=[hand(0.5 - d / 2), hand(0.5 + d / 2)]), 0.3
        )
    assert "repetitive_hand_motion" in kinds(r)


def test_gesture_exit_requires_observation_not_missing_hands():
    t = ready()
    edge = hand()
    edge[8][0] = 1.01
    for _ in range(2):
        drive(t, replace(NEUTRAL, hands=[edge]), 0.3)
        r = drive(t, replace(NEUTRAL, hands=[hand()]), 0.3)
    assert "gesture_out_of_view" in kinds(r)
    missing = drive(ready(), replace(NEUTRAL, hands=None), 5)
    assert missing["session_events"] == [] and missing["status"]["hands"] == "Not assessed"


def test_small_normal_movements_have_no_events():
    t = ready(True)
    for i in range(100):
        sign = 1 if i % 2 else -1
        r = drive(
            t,
            replace(
                NEUTRAL,
                head=(sign * 3, sign * 2, 0),
                eyes=(0.5 + sign * 0.02, 0.5, 0.5 + sign * 0.02, 0.5),
                body=body(cx=0.5 + sign * 0.005),
                hands=[hand(0.3 + sign * 0.005)],
            ),
            0.1,
        )
    assert r["session_events"] == []


def test_one_gradual_head_turn_and_short_glance_are_not_repetitive():
    t = ready()
    drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 0.5)
    drive(t, NEUTRAL, 0.5)
    for yaw in [5, 10, 15, 20, 15, 10, 5, 0]:
        r = drive(t, replace(NEUTRAL, head=(yaw, 0, 0)), 0.2)
    assert not {"repeated_glances", "repeated_head_turns", "head_shaking"} & kinds(r)


def test_missing_data_closes_timers_without_faults():
    t = ready()
    drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 3)
    missing = drive(t, FrameObservation(person_detected=False), 2)
    assert all(not e["active"] for e in missing["session_events"])
    assert set(missing["status"].values()) == {"Not assessed"}
    assert drive(t, NEUTRAL, 0.1)["directions"]["eyes"] == "centre"


def test_pause_recalibration_and_new_session():
    t = ready()
    drive(t, replace(NEUTRAL, head=(25, 0, 0)), 3)
    t.pause(6100)
    r = t.process(NEUTRAL, 999, 50000, 0).as_message()
    assert all(not e["active"] for e in r["session_events"])
    t.recalibrate_gaze(50100)
    assert t.baselines == {} and t.events
    assert not LiveCoachingTracker().events


def test_unknown_body_is_not_good_posture():
    t = ready(True)
    p = body()
    p[11][3] = 0.1
    r = drive(t, replace(NEUTRAL, body=p), 5)
    assert r["status"]["body"] == "Not assessed" and r["session_events"] == []


def test_binocular_disagreement_does_not_stick():
    t = ready()
    r = drive(t, replace(NEUTRAL, eyes=(0.8, 0.5, 0.5, 0.5)), 20)
    assert r["directions"]["eyes"] is None and r["session_events"] == []
    assert drive(t, NEUTRAL, 0.1)["directions"]["eyes"] == "centre"


def test_parser_validates_packets():
    def parse(**kwargs):
        return _client_observation(dict(type="observation", person_detected=True, **kwargs))

    assert parse(head=[0, float("nan"), 0]).head is None
    assert parse(body=body()).body and parse(hands=[hand()]).hands
    assert parse(eyes=[True, 0.5, 0.5, 0.5]).eyes is None


def test_invalid_shoulder_width_closes_posture_warning():
    t = ready(True)
    drive(t, replace(NEUTRAL, body=body(width=0.4)), 3.2)
    r = drive(t, replace(NEUTRAL, body=body(width=0.01)), 0.2)
    assert r["status"]["body"] == "Not assessed"
    assert all(not e["active"] for e in r["session_events"])


def test_stale_hand_samples_clear_repetition_history():
    t = ready()
    near = hand()
    near[8] = [0.5, 0.22, 0, 1]
    for _ in range(2):
        drive(t, replace(NEUTRAL, hands=[near]), 0.4)
        drive(t, replace(NEUTRAL, hands=[hand()]), 0.4)
    drive(t, replace(NEUTRAL, hands_updated=False), 1)
    r = drive(t, replace(NEUTRAL, hands=[near]), 0.4)
    assert "repeated_face_touching" not in kinds(r)


def test_face_proximity_jitter_does_not_count_as_repeated_touches():
    t = ready()
    for i in range(30):
        near = hand()
        near[8] = [0.5, 0.22 if i % 2 else 0.30, 0, 1]
        r = drive(t, replace(NEUTRAL, hands=[near]), 0.1)
    assert "repeated_face_touching" not in kinds(r)


def test_head_pitch_does_not_create_slumping_warning():
    t = ready(True)
    r = drive(
        t,
        replace(NEUTRAL, head=(0, -25, 0), body=body(), face_targets=[(0.5, 0.48), *TARGETS[1:]]),
        4,
    )
    assert "head_position" in kinds(r)
    assert "posture_drift" not in kinds(r)


def test_abrupt_repeated_head_turns():
    t = ready()
    for yaw in [20, 20, -5, -5, 20]:
        r = drive(t, replace(NEUTRAL, head=(yaw, 0, 0)), 0.1)
    assert "abrupt_head_movement" in kinds(r)


@pytest.mark.parametrize("step", [0.05, 0.1, 0.2])
def test_long_held_eye_direction_recovers_and_changes_without_latching(step):
    t = ready()
    for eye, side in [
        ((0.7, 0.5), "left"),
        ((0.3, 0.5), "right"),
        ((0.5, 0.3), "up"),
        ((0.5, 0.7), "down"),
    ]:
        r = drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 20, step=step)
        assert r["directions"]["eyes"] == side
        r = drive(t, NEUTRAL, 0.6, step=step)
        assert r["directions"]["eyes"] == "centre"
        assert all(not e["active"] for e in r["session_events"])


@pytest.mark.parametrize(
    "eye,side",
    [
        ((0.65, 0.35), "up_left"),
        ((0.35, 0.35), "up_right"),
        ((0.65, 0.65), "down_left"),
        ((0.35, 0.65), "down_right"),
    ],
)
def test_diagonal_status_is_immediate_but_lookaway_waits_one_second(eye, side):
    t = ready()
    r = drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 0.1)
    assert r["directions"]["eyes"] == side
    assert "eye_away" not in kinds(r)
    assert "eye_away" not in kinds(drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 0.9))
    assert "eye_away" in kinds(drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 0.1))
    r = drive(t, NEUTRAL, 0.1)
    assert not any(e["active"] for e in r["session_events"])


def test_three_short_corner_glances_with_blinks_count_without_hold():
    t = ready()
    corner = replace(NEUTRAL, eyes=(0.65, 0.35, 0.65, 0.35))
    for _ in range(3):
        drive(t, corner, 0.1)
        drive(t, replace(NEUTRAL, eyes=None), 0.1)
        r = drive(t, NEUTRAL, 0.1)
    assert "repeated_glances" in kinds(r)
    assert "3 glances up left" in str(r["session_events"])
    assert "eye_away" not in kinds(r)


def test_uncertain_samples_do_not_fabricate_a_glance():
    t = ready()
    for _ in range(10):
        drive(t, replace(NEUTRAL, eyes=None), 0.1)
        r = drive(t, NEUTRAL, 0.1)
    assert not r["session_events"]


def test_long_eye_tracking_loss_keeps_completed_glances_but_not_unfinished_one():
    t = ready()
    away = replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5))
    for _ in range(2):
        drive(t, away, 0.1)
        drive(t, NEUTRAL, 0.1)
    drive(t, away, 0.1)
    drive(t, replace(NEUTRAL, eyes=None), 1)
    r = drive(t, NEUTRAL, 0.1)
    assert "repeated_glances" not in kinds(r)
    drive(t, away, 0.1)
    r = drive(t, NEUTRAL, 0.1)
    assert "repeated_glances" in kinds(r)


def test_short_looks_do_not_accumulate_into_continuous_lookaway():
    t = ready()
    for _ in range(4):
        drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 0.7)
        r = drive(t, NEUTRAL, 0.1)
    assert "eye_away" not in kinds(r)
    assert "repeated_glances" in kinds(r)
