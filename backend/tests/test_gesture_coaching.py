from types import SimpleNamespace

import pytest

from app.services import gesture_coaching as coaching
from app.services.gesture_rules import RULE_VERSION, prepare_gesture_events, rule_decision


def event(kind="arms_crossed", start=10, duration=2, **extra):
    return {"type": kind, "start_seconds": start, "end_seconds": start + duration,
            "duration_seconds": duration, "evidence_index": 1, **extra}


def test_old_ai_approval_cannot_hide_a_code_detection():
    candidate = event(coaching={"assessment": "appropriate"})
    result = prepare_gesture_events([candidate])
    assert len(result) == 1
    assert result[0]["detection"]["is_issue"]
    assert result[0]["coaching"]["source"] == "code"


def test_old_ai_rejection_cannot_create_a_fault_from_a_brief_rest():
    candidate = event("hands_clasped_low", duration=0.8,
                      coaching={"assessment": "adjustment"})
    assert prepare_gesture_events([candidate]) == []


@pytest.mark.parametrize("kind", ["arms_crossed", "gesture_box_excursion", "hands_clasped_low",
                                   "hand_near_face", "repeated_head_movement", "repeated_swaying"])
def test_sustained_supported_patterns_have_code_feedback_without_any_ai(kind):
    result = prepare_gesture_events([event(kind, duration=4)])
    assert len(result) == 1
    assert result[0]["coaching"]["observation"]
    assert result[0]["detection"]["version"] == RULE_VERSION


def test_recurrence_not_an_arbitrary_flag_count_controls_brief_reaches():
    alone = event("gesture_box_excursion", start=2, duration=0.4)
    assert prepare_gesture_events([alone]) == []
    repeated = [alone, event("gesture_box_excursion", start=7, duration=0.4)]
    assert len(prepare_gesture_events(repeated)) == 2
    far_apart = [alone, event("gesture_box_excursion", start=80, duration=0.4)]
    assert prepare_gesture_events(far_apart) == []


def test_observation_uses_side_posture_and_real_duration():
    candidate = event(duration=2.6, measurements=[
        {"body_part": "your left arm", "posture": "toward the opposite shoulder"}
    ])
    observation = prepare_gesture_events([candidate])[0]["coaching"]["observation"]
    assert "left arm" in observation and "2.6 seconds" in observation
    assert "opposite shoulder" in observation


def test_motion_observation_uses_measured_direction_changes():
    candidate = event("repeated_head_movement", measurements=[
        {"axis": "in sideways tilts", "reversals": 4,
         "reversal_seconds": [10.2, 10.5, 11, 11.5]}
    ])
    observation = prepare_gesture_events([candidate])[0]["coaching"]["observation"]
    assert "direction at least 4 times" in observation and "sideways tilts" in observation


def test_missing_provider_keeps_all_code_feedback(monkeypatch, tmp_path):
    monkeypatch.setattr(coaching, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key=None))
    events = prepare_gesture_events([event()])
    coaching.coach_gesture_events(tmp_path, events, [])
    assert len(events) == 1 and events[0]["coaching"]["source"] == "code"


def test_provider_failure_keeps_detections_and_factual_observation(monkeypatch, tmp_path):
    monkeypatch.setattr(coaching, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="test"))

    def fail(*a, **kw):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(coaching, "_request_json", fail)
    events = prepare_gesture_events([event()])
    before = events[0]["coaching"].copy()
    coaching.coach_gesture_events(tmp_path, events, [])
    assert events[0]["coaching"] == before
    assert events[0]["detection"]["is_issue"]


def test_model_cannot_override_observation_decision_or_add_detections(monkeypatch, tmp_path):
    monkeypatch.setattr(coaching, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="test"))
    monkeypatch.setattr(coaching, "_request_json", lambda *a, **kw: {"items": [
        {"id": 0, "title": "Release the arm", "impact": "Keep hands available for emphasis.",
         "recommendation": "Release it before the next point.", "assessment": "appropriate",
         "is_issue": False, "observation": "Fake fact"},
        {"id": 999, "type": "invented"},
    ]})
    events = prepare_gesture_events([event()])
    observation = events[0]["coaching"]["observation"]
    coaching.coach_gesture_events(tmp_path, events, [])
    assert len(events) == 1 and events[0]["detection"]["is_issue"]
    assert events[0]["coaching"]["observation"] == observation
    assert events[0]["coaching"]["assessment"] == "adjustment"


def test_missing_rewritten_item_does_not_drop_an_issue(monkeypatch, tmp_path):
    monkeypatch.setattr(coaching, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="test"))
    monkeypatch.setattr(coaching, "_request_json", lambda *a, **kw: {"items": []})
    events = prepare_gesture_events([event()])
    coaching.coach_gesture_events(tmp_path, events, [])
    assert len(events) == 1 and events[0]["coaching"]["source"] == "code"


def test_body_language_finding_ignores_legacy_ai_verdict():
    from app.services.upload_practice import build_coaching_report

    candidate = event(coaching={"assessment": "appropriate"})
    report = build_coaching_report({}, [candidate])
    finding = next(item for item in report["findings"] if item["category"] == "Body language")
    expected = prepare_gesture_events([candidate])[0]["coaching"]["observation"]
    assert finding["observation"] == expected


def test_unknown_pattern_is_not_invented_as_a_detection():
    assert not rule_decision(event("not-a-supported-rule"), [])["is_issue"]


@pytest.mark.parametrize("kind,axis,label,correction", [
    ("repeated_swaying", "torso lean", "Repeated torso leaning", "shoulders back over your hips"),
    ("repeated_swaying", "whole-body lateral shifting", "Repeated sideways body shifting", "one position"),
    ("repeated_head_movement", "side to side", "Repeated head turns", "one direction"),
    ("repeated_head_movement", "up and down", "Repeated nodding", "after a nod"),
    ("repeated_head_movement", "in sideways tilts", "Repeated sideways head tilts", "either shoulder"),
])
def test_motion_variant_keeps_specific_label_and_correction(kind, axis, label, correction):
    candidate = event(kind, measurements=[{"axis": axis, "reversal_seconds": [10.2, 11.5]}])
    result = prepare_gesture_events([candidate])[0]
    assert result["label"] == label
    assert correction in result["coaching"]["recommendation"]
    assert result["duration_seconds"] == candidate["duration_seconds"]


def test_folded_and_single_arm_reach_feedback_remain_distinct():
    folded = event(measurements=[{"body_part": "both forearms", "posture": "folded across your torso"}])
    reach = event(measurements=[{"body_part": "your right arm", "posture": "toward the opposite shoulder"}])
    first, second = [prepare_gesture_events([e])[0] for e in (folded, reach)]
    assert first["label"] == "Both arms folded across torso"
    assert "Unfold both arms" in first["coaching"]["title"]
    assert "Right arm" in second["label"]
    assert "your right arm" in second["coaching"]["recommendation"]


def test_missing_measurements_do_not_invent_variant_and_mixed_keeps_both():
    generic = prepare_gesture_events([event("repeated_swaying")])[0]
    assert generic["label"] == "Repeated body swaying"
    assert "shoulders and hips" not in generic["coaching"]["observation"]
    mixed = prepare_gesture_events([event("repeated_swaying", measurements=[
        {"axis": "torso lean"}, {"axis": "whole-body lateral shifting"}
    ])])[0]
    assert "leaned" in mixed["coaching"]["observation"]
    assert "shifted sideways together" in mixed["coaching"]["observation"]


def test_old_generic_rewrite_cannot_replace_new_specific_wording():
    from app.services.gesture_rules import WORDING_VERSION
    candidate = event("repeated_swaying", measurements=[{"axis": "torso lean"}], coaching={
        "version": RULE_VERSION, "source": "rewrite", "title": "Old generic title",
        "recommendation": "Old correction", "impact": "Old impact",
    })
    result = prepare_gesture_events([candidate])[0]
    assert result["coaching"]["source"] == "code"
    assert result["coaching"]["wording_version"] == WORDING_VERSION
    assert "torso leaning" in result["coaching"]["title"]
    assert candidate["coaching"]["title"] == "Old generic title"


def test_side_preserved_for_hand_near_face_without_claiming_contact():
    result = prepare_gesture_events([event("hand_near_face", measurements=[{"body_part": "your left hand"}])])[0]
    assert result["label"] == "Left hand near face"
    assert "your left hand" in result["coaching"]["recommendation"]
    assert "touching" not in result["coaching"]["observation"]
