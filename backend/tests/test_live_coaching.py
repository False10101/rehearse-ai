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
    r = drive(ready(), replace(NEUTRAL, hands=[hand(0.5, 0.4)]), 0.7)
    event = next(e for e in r["session_events"] if e["kind"] == "face_obstruction")
    assert event["title"] == "Hand covering face"
    assert event["evidence"] == "Hand across mouth or eye area"
    assert r["message"] == "Hand covering face"
    assert r["status"]["hands"] == "Hand covering face"


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


def test_hand_visible_in_centre_or_at_edge_is_reported_immediately():
    for points in [hand(0.5, 0.7), hand(0.01, 0.7), hand(0.99, 0.7)]:
        r = drive(ready(), replace(NEUTRAL, hands=[points]), 0.1)
        event = next(e for e in r["session_events"] if e["kind"] == "hand_in_view")
        assert event["title"] == "Keep your hands out of the camera view"
        assert event["evidence"] == "Hand visible in the camera frame"


def test_missing_or_entirely_outside_hands_do_not_trigger_visibility_warning():
    for hands in [None, [], [hand(-0.2, 0.7)], [hand(1.2, 0.7)]]:
        r = drive(ready(), replace(NEUTRAL, hands=hands), 2)
        assert not r["session_events"]


def test_hand_visibility_event_ends_on_removal_and_next_entry_is_separate():
    t = ready()
    drive(t, replace(NEUTRAL, hands=[hand(0.5, 0.7)]), 0.3)
    r = drive(t, replace(NEUTRAL, hands=[]), 0.1)
    assert all(not e["active"] for e in r["session_events"])
    r = drive(t, replace(NEUTRAL, hands=[hand(0.5, 0.7)]), 0.1)
    rows = [e for e in r["session_events"] if e["kind"] == "hand_in_view"]
    assert len(rows) == 2 and rows[0]["id"] != rows[1]["id"]


def test_small_normal_movements_only_report_the_visible_hand():
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
    assert kinds(r) == {"hand_in_view"}


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
        drive(t, corner, 0.1, step=0.05)
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
        drive(t, away, 0.1, step=0.05)
        drive(t, NEUTRAL, 0.1)
    drive(t, away, 0.1, step=0.05)
    drive(t, replace(NEUTRAL, eyes=None), 1)
    r = drive(t, NEUTRAL, 0.1)
    assert "repeated_glances" not in kinds(r)
    drive(t, away, 0.1, step=0.05)
    r = drive(t, NEUTRAL, 0.1)
    assert "repeated_glances" in kinds(r)


def test_short_looks_do_not_accumulate_into_continuous_lookaway():
    t = ready()
    for _ in range(4):
        drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 0.7)
        r = drive(t, NEUTRAL, 0.1)
    assert "eye_away" not in kinds(r)
    assert "repeated_glances" in kinds(r)


@pytest.mark.parametrize(
    "head",
    [
        (12, 0, 0),
        (-12, 0, 0),
        (0, 9, 0),
        (0, -9, 0),
        (0, 0, 9),
        (0, 0, -9),
        (12, 9, 9),
    ],
)
@pytest.mark.parametrize(
    "eye,side",
    [
        ((0.7, 0.5), "left"),
        ((0.3, 0.5), "right"),
        ((0.5, 0.3), "up"),
        ((0.5, 0.7), "down"),
        ((0.65, 0.35), "up_left"),
    ],
)
def test_eye_direction_survives_small_accompanying_head_movement(head, eye, side):
    t = ready()
    obs = replace(NEUTRAL, head=head, eyes=(*eye, *eye))
    r = drive(t, obs, 0.1)
    assert r["directions"] == {"eyes": side, "head": "centre"}
    assert not r["session_events"]
    r = drive(t, obs, 1)
    assert "eye_away" in kinds(r)
    assert "head_position" not in kinds(r)


def test_repeated_eye_glances_with_slight_head_tilt():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, head=(0, 0, 9), eyes=(0.3, 0.5, 0.3, 0.5)), 0.1, step=0.05)
        r = drive(t, replace(NEUTRAL, head=(0, 0, 9)), 0.1)
    assert "repeated_glances" in kinds(r)
    assert not {"head_position", "repeated_head_turns"} & kinds(r)


@pytest.mark.parametrize("head", [(16, 0, 0), (-16, 0, 0), (0, 13, 0), (0, 0, 13)])
def test_definite_head_turn_still_tracked_separately(head):
    t = ready()
    r = drive(t, replace(NEUTRAL, head=head), 2.2)
    assert r["directions"]["head"] != "centre"
    assert r["directions"]["eyes"] is None
    assert "head_position" in kinds(r)


def test_different_held_eye_directions_keep_their_own_rows_and_durations():
    t = ready()
    for eye, seconds in [((0.7, 0.5), 4), ((0.3, 0.5), 6), ((0.5, 0.3), 10)]:
        drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), seconds)
    r = drive(t, NEUTRAL, 0.1)
    rows = [e for e in r["session_events"] if e["kind"] == "eye_away"]
    assert [e["evidence"] for e in rows] == ["Looking left", "Looking right", "Looking up"]
    assert [e["duration_seconds"] for e in rows] == [4, 6, 10]
    assert len({e["id"] for e in rows}) == 3
    before = [(e["id"], e["title"], e["evidence"], e["duration_seconds"]) for e in rows]
    for _ in range(3):
        drive(t, replace(NEUTRAL, eyes=(0.65, 0.35, 0.65, 0.35)), 0.1, step=0.05)
        r = drive(t, NEUTRAL, 0.1)
    assert "repeated_glances" in kinds(r)
    after = [
        (e["id"], e["title"], e["evidence"], e["duration_seconds"])
        for e in r["session_events"]
        if e["kind"] == "eye_away"
    ]
    assert after == before


def test_overlapping_events_never_merge_or_replace_existing_rows():
    t = ready()
    t._pulse("eye_away", 3, 4, "Looking left")
    t._pulse("body_swaying", 4.5, 5, "Body moving")
    before = t._events(5)
    t._pulse("repeated_glances", 3.5, 6, "3 glances right")
    after = t._events(6)
    assert len(after) == 3
    assert after[:2] == before
    assert len({e["id"] for e in after}) == 3
    assert all(len(e["signals"]) == 1 for e in after)


def test_definite_head_turn_does_not_also_count_as_eye_glance():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, head=(25, 0, 0), eyes=(0.7, 0.5, 0.7, 0.5)), 0.4)
        r = drive(t, NEUTRAL, 0.4)
    assert "repeated_head_turns" in kinds(r)
    assert not {"eye_away", "repeated_glances"} & kinds(r)


def test_new_direction_does_not_replay_an_old_glance_report():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 0.1, step=0.05)
        drive(t, NEUTRAL, 0.1)
    drive(t, NEUTRAL, 4.1)
    drive(t, replace(NEUTRAL, eyes=(0.3, 0.5, 0.3, 0.5)), 0.1, step=0.05)
    r = drive(t, NEUTRAL, 0.1)
    assert len([e for e in r["session_events"] if e["kind"] == "repeated_glances"]) == 1


def test_current_session_does_not_silently_drop_older_entries_after_200_events():
    t = ready()
    for i in range(205):
        t._pulse("repeated_glances", 3 + i, 3 + i, f"Glance pattern {i}", cooldown=0)
    first_id = t.events[0]["id"]
    r = t.process(NEUTRAL, 999, 208000, 0).as_message()
    assert len(r["session_events"]) == 205
    assert r["session_events"][0]["id"] == first_id


FACE_BOX = dict(x=0.4, y=0.2, width=0.2, height=0.25)


def object_observation(label="cell phone", confidence=0.9, box=None, **kwargs):
    return replace(
        NEUTRAL,
        debug={"face": FACE_BOX},
        objects_updated=True,
        objects=[
            dict(
                label=label,
                confidence=confidence,
                bounds=box or dict(x=0.43, y=0.3, width=0.14, height=0.16),
            )
        ],
        **kwargs,
    )


def test_object_blocking_face_has_explicit_label():
    r = drive(ready(), object_observation(), 0.7)
    event = next(e for e in r["session_events"] if e["kind"] == "object_obstruction")
    assert event["title"] == "Object blocking face"
    assert event["evidence"] == "Cell phone across the face"


@pytest.mark.parametrize(
    "obs",
    [
        object_observation(box=dict(x=0.05, y=0.2, width=0.1, height=0.1)),
        object_observation(label="person"),
        object_observation(confidence=0.4),
        object_observation(box=dict(x=0, y=0, width=1, height=1)),
    ],
)
def test_objects_beside_face_low_confidence_person_or_background_do_not_flag(obs):
    assert "object_obstruction" not in kinds(drive(ready(), obs, 2))


def test_hand_holding_phone_is_not_a_duplicate_hand_covering_report():
    r = drive(ready(), object_observation(hands=[hand(0.5, 0.4)]), 1)
    assert "object_obstruction" in kinds(r)
    assert "face_obstruction" not in kinds(r)


def test_face_loss_alone_does_not_mean_object():
    t = ready()
    drive(t, replace(object_observation(), objects=[]), 0.1)
    r = drive(t, FrameObservation(person_detected=False, objects_updated=True, objects=[]), 2)
    assert "object_obstruction" not in kinds(r)


def test_actual_object_with_brief_face_loss_and_recovery():
    t = ready()
    drive(t, object_observation(), 0.1)
    obs = replace(object_observation(), person_detected=False, eyes=None, head=None, debug=None)
    r = drive(t, obs, 0.7)
    assert "object_obstruction" in kinds(r)
    r = drive(t, replace(NEUTRAL, objects_updated=True, objects=[]), 0.1)
    assert not any(e["active"] for e in r["session_events"] if e["kind"] == "object_obstruction")


def test_stale_object_measurements_do_not_remain_active():
    t = ready()
    drive(t, object_observation(), 1)
    r = drive(t, replace(NEUTRAL, debug={"face": FACE_BOX}), 1)
    assert not any(e["active"] for e in r["session_events"] if e["kind"] == "object_obstruction")


def test_object_packet_validation():
    p = _client_observation(
        dict(
            type="observation",
            person_detected=True,
            objects_updated=True,
            objects=[
                dict(label="cup", confidence=0.9, bounds=dict(x=0.4, y=0.3, width=0.1, height=0.1))
            ],
        )
    )
    assert p.objects[0]["label"] == "cup" and p.objects_updated


def test_tiny_direction_boundary_jitter_is_not_repeated_glancing():
    t = ready()
    for i in range(100):
        x = 0.582 if i % 2 else 0.578
        r = drive(t, replace(NEUTRAL, eyes=(x, 0.5, x, 0.5)), 0.1)
    assert not {"repeated_glances", "gaze_switching"} & kinds(r)


def test_corner_angle_jitter_is_not_a_series_of_glances():
    t = ready()
    for i in range(80):
        x, y = (0.65, 0.43) if i % 2 else (0.65, 0.38)
        r = drive(t, replace(NEUTRAL, eyes=(x, y, x, y)), 0.1)
    assert "repeated_glances" not in kinds(r)
    assert "gaze_switching" not in kinds(r)


def test_isolated_iris_spikes_do_not_count_as_repeat_glances():
    t = ready()
    for _ in range(10):
        drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 0.05, step=0.05)
        r = drive(t, NEUTRAL, 0.15, step=0.05)
    assert not {"repeated_glances", "gaze_switching"} & kinds(r)


def test_partial_blinks_and_reopening_do_not_count_as_downward_glances():
    t = ready()
    for _ in range(8):
        drive(t, replace(NEUTRAL, eye_openness=(0.3, 0.3)), 0.5)
        drive(t, replace(NEUTRAL, eyes=(0.5, 0.75, 0.5, 0.75), eye_openness=(0.15, 0.15)), 0.1)
        drive(t, replace(NEUTRAL, eyes=None, eye_openness=(0.05, 0.05)), 0.1)
        drive(
            t, replace(NEUTRAL, eyes=(0.5, 0.7, 0.5, 0.7), eye_openness=(0.3, 0.3)), 0.05, step=0.05
        )
        r = drive(t, replace(NEUTRAL, eye_openness=(0.3, 0.3)), 0.2, step=0.05)
    assert not r["session_events"]


def test_robust_eye_calibration_is_not_blocked_by_occasional_glance_outliers():
    t = LiveCoachingTracker(Settings(live_calibration_frames=15))
    for i in range(20):
        eye = (0.7, 0.5, 0.7, 0.5) if i in {4, 5, 9, 10} else NEUTRAL.eyes
        r = drive(t, replace(NEUTRAL, eyes=eye), 0.1)
    assert r["calibration_complete"]
    assert t.baselines["eyes"] == NEUTRAL.eyes


def test_clear_short_glances_still_work_at_camera_frame_rate():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, eyes=(0.7, 0.5, 0.7, 0.5)), 2 / 15, step=1 / 15)
        r = drive(t, NEUTRAL, 2 / 15, step=1 / 15)
    assert "repeated_glances" in kinds(r)
    assert "eye_away" not in kinds(r)


def test_ordinary_turn_return_and_later_other_turn_is_not_a_head_shake():
    t = ready()
    for yaw in [25, 0, -25, 0]:
        r = drive(t, replace(NEUTRAL, head=(yaw, 0, 0)), 0.7)
    assert "head_shaking" not in kinds(r)


def test_repeated_looks_up_and_forward_are_not_alternating_nods():
    t = ready()
    for pitch in [20, 0, 20, 0]:
        r = drive(t, replace(NEUTRAL, head=(0, pitch, 0)), 0.3)
    assert "head_nodding" not in kinds(r)


def test_spaced_eye_glances_are_not_rapid_switching():
    t = ready()
    for eye in [(0.7, 0.5), (0.5, 0.3), (0.3, 0.5), (0.5, 0.7)]:
        drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 0.2, step=0.05)
        r = drive(t, NEUTRAL, 1.8)
    assert "gaze_switching" not in kinds(r)


def test_opposite_repeated_glance_directions_do_not_block_each_others_alerts():
    t = ready()
    for eye in [(0.7, 0.5), (0.3, 0.5)]:
        for _ in range(3):
            drive(t, replace(NEUTRAL, eyes=(*eye, *eye)), 0.1, step=0.05)
            r = drive(t, NEUTRAL, 0.1, step=0.05)
    rows = [e for e in r["session_events"] if e["kind"] == "repeated_glances"]
    assert len(rows) == 2
    assert "left" in rows[0]["evidence"] and "right" in rows[1]["evidence"]


def test_sustained_downward_gaze_with_narrow_but_visible_eyes_is_not_suppressed_forever():
    t = ready()
    drive(t, replace(NEUTRAL, eye_openness=(0.4, 0.4)), 0.5)
    r = drive(t, replace(NEUTRAL, eyes=(0.5, 0.7, 0.5, 0.7), eye_openness=(0.25, 0.25)), 2)
    assert r["directions"]["eyes"] == "down"
    assert "eye_away" in kinds(r)


def test_vertical_measurement_disagreement_does_not_discard_agreed_sideways_glance():
    t = ready()
    r = drive(t, replace(NEUTRAL, eyes=(0.25, 0.5, 0.27, 0.3)), 0.1)
    assert r["directions"]["eyes"] == "right"


def test_returning_eyes_do_not_stay_stuck_after_extended_blinks():
    t = ready()
    drive(t, replace(NEUTRAL, eye_openness=(0.4, 0.4)), 0.5)
    drive(t, replace(NEUTRAL, eyes=(0.5, 0.7, 0.5, 0.7), eye_openness=(0.4, 0.4)), 1.2)
    drive(t, replace(NEUTRAL, eyes=None, eye_openness=(0.05, 0.05)), 1)
    r = drive(t, replace(NEUTRAL, eye_openness=(0.4, 0.4)), 0.3)
    assert r["directions"]["eyes"] == "centre"
    assert all(not e["active"] for e in r["session_events"])


@pytest.mark.parametrize(
    "head,side",
    [
        ((25, 20, 0), "up_left"),
        ((-25, 20, 0), "up_right"),
        ((25, -20, 0), "down_left"),
        ((-25, -20, 0), "down_right"),
    ],
)
def test_diagonal_head_turn_is_specific_in_status_event_and_eye_priority(head, side):
    t = ready()
    obs = replace(NEUTRAL, head=head, eyes=(0.7, 0.3, 0.7, 0.3))
    r = drive(t, obs, 0.1)
    assert r["directions"]["head"] == side
    assert r["directions"]["eyes"] is None
    assert r["status"]["head"] == "Turned " + side.replace("_", "-")
    assert not r["session_events"]
    r = drive(t, obs, 2)
    event = next(e for e in r["session_events"] if e["kind"] == "head_position")
    assert event["evidence"] == "Turned " + side.replace("_", "-")
    assert not {"eye_away", "repeated_glances"} & kinds(r)


def test_small_combined_head_movement_stays_forward():
    r = drive(ready(), replace(NEUTRAL, head=(8, 6, 3)), 3)
    assert r["directions"]["head"] == "centre"
    assert not r["session_events"]


def test_roll_is_not_mislabelled_as_a_diagonal_turn():
    r = drive(ready(), replace(NEUTRAL, head=(0, 0, 25)), 2.2)
    assert r["directions"]["head"] == "tilt_right"
    assert r["status"]["head"] == "Leaning head right"


def test_diagonal_head_angle_does_not_split_when_near_the_cardinal_boundary():
    t = ready()
    drive(t, replace(NEUTRAL, head=(25, 20, 0)), 0.2)
    for pitch in [12, 13, 12, 13]:
        r = drive(t, replace(NEUTRAL, head=(25, pitch, 0)), 0.2)
        assert r["directions"]["head"] == "up_left"


def test_repeated_diagonal_head_turns_have_head_specific_evidence():
    t = ready()
    for _ in range(3):
        drive(t, replace(NEUTRAL, head=(25, 20, 0)), 0.4)
        r = drive(t, NEUTRAL, 0.4)
    event = next(e for e in r["session_events"] if e["kind"] == "repeated_head_turns")
    assert "head turns up left" in event["evidence"]
