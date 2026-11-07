import math

import numpy as np

from app.services.gesture_rules import measured_coaching, prepare_gesture_events
from app.services.motion_intervals import motion_pattern
from app.services.upload_practice import PoseEventCollector


def test_motion_interval_excludes_stationary_lead_in_and_tail():
    samples = [(i / 10, 0 if i < 20 else 0.4 * math.sin((i / 10 - 2) * 4))
               for i in range(75)]
    result = motion_pattern(samples, 0.08, 0.2, 2)
    assert result and result["pattern_start_seconds"] >= 1.9
    assert result["pattern_end_seconds"] <= 7.4
    stopped = samples + [(7.5 + i / 10, samples[-1][1]) for i in range(15)]
    assert motion_pattern(stopped, 0.08, 0.2, 2) is None


def test_earlier_burst_cannot_justify_a_later_isolated_turn():
    samples = [(i / 10, 0.4 * math.sin(i / 10 * 5)) for i in range(35)]
    samples += [(3.5 + i / 10, 0) for i in range(25)]
    samples += [(6 + i / 10, i / 30) for i in range(10)]
    assert motion_pattern(samples, 0.08, 0.2, 2) is None


def test_motion_episode_length_is_not_a_fixed_window():
    lengths = []
    for duration in (4, 12, 25):
        samples = [(i / 10, 0.4 * math.sin(i / 10 * 4)) for i in range(duration * 10)]
        result = motion_pattern(samples, 0.08, 0.2, 2)
        assert result
        lengths.append(result["pattern_end_seconds"] - result["pattern_start_seconds"])
    assert lengths[0] < lengths[1] < lengths[2]


def test_overlapping_motion_fragments_merge_and_counts_are_deduplicated(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    frame = np.zeros((40, 40, 3), np.uint8)
    points = [(10, 10, 1)] * 17
    kind = "repeated_head_movement"
    for timestamp, start, turns in ((4, 2, [2.5, 3.5]), (4.2, 2.2, [2.5, 3.5]),
                                    (6, 3.8, [4.5, 5.5])):
        if timestamp == 6:
            collector._finish(kind)
        collector.observe(timestamp, {kind: 0.8}, frame, points, {kind: {
            "axis": "side to side", "pattern_start_seconds": start,
            "pattern_end_seconds": timestamp, "reversal_seconds": turns,
        }})
    events = collector.finish_all()
    assert len(events) == 1
    assert events[0]["start_seconds"] == 2
    assert events[0]["end_seconds"] == 6.2
    assert events[0]["duration_seconds"] == 4.2
    assert "at least 4 times" in measured_coaching(events[0])["observation"]


def test_face_hold_includes_tracked_time_before_qualification(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    for t in (11, 11.2, 11.4):
        collector.observe(t, {"hand_near_face": 0.8}, np.zeros((40, 40, 3), np.uint8),
                          [(10, 10, 1)] * 17, {"hand_near_face": {
                              "body_part": "your left hand", "pattern_start_seconds": 10,
                          }})
    event = collector.finish_all()[0]
    assert event["start_seconds"] == 10
    assert event["end_seconds"] == 11.6
    assert event["duration_seconds"] == 1.6


def test_different_crossed_arm_actions_do_not_count_as_the_same_repetition():
    events = [{"type": "arms_crossed", "start_seconds": start, "end_seconds": start + 0.6,
               "duration_seconds": 0.6, "measurements": [facts]}
              for start, facts in [(1, {"body_part": "your left arm",
                                        "posture": "toward the opposite shoulder"}),
                                    (5, {"body_part": "both forearms",
                                         "posture": "folded across your torso"})]]
    assert prepare_gesture_events(events) == []
    events[1]["measurements"] = events[0]["measurements"]
    result = prepare_gesture_events(events)
    assert len(result) == 2
    assert all(event["detection"]["nearby_episodes"] == 2 for event in result)


def test_turn_counts_outside_the_displayed_interval_are_not_claimed():
    event = {"type": "repeated_head_movement", "start_seconds": 10, "end_seconds": 12,
             "duration_seconds": 2, "measurements": [{"axis": "side to side",
             "reversals": 9, "reversal_seconds": [1, 3, 5, 7, 10.5, 11]}]}
    assert "at least 2 times" in measured_coaching(event)["observation"]


def test_saved_frame_is_inside_the_actual_motion_interval_not_later_qualification(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    frame = np.zeros((40, 40, 3), np.uint8)
    points = [(10, 10, 1)] * 17
    for timestamp in (3.6, 3.8, 4.0):
        collector.observe(timestamp, {}, frame, points)
    collector.observe(4.4, {"repeated_head_movement": 0.8}, frame, points, {
        "repeated_head_movement": {"pattern_start_seconds": 2,
                                   "pattern_end_seconds": 4,
                                   "reversal_seconds": [2.5, 3.5]},
    })
    event = collector.finish_all()[0]
    assert event["start_seconds"] <= event["evidence_seconds"] < event["end_seconds"]
    assert event["evidence_seconds"] == 4
