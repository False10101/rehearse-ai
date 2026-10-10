from types import SimpleNamespace

import numpy as np

from app.services import upload_practice
from app.services.upload_practice import (
    PoseEventCollector,
    build_coaching_report,
    classify_pose,
    presenter_pose_is_reliable,
    speech_metrics,
)


def keypoints(**overrides: tuple[float, float, float]) -> list[tuple[float, float, float]]:
    points = [(0.0, 0.0, 0.0) for _ in range(17)]
    defaults = {
        5: (100.0, 100.0, 1.0),
        6: (200.0, 100.0, 1.0),
        7: (110.0, 170.0, 1.0),
        8: (190.0, 170.0, 1.0),
        9: (130.0, 180.0, 1.0),
        10: (170.0, 180.0, 1.0),
        11: (115.0, 250.0, 1.0),
        12: (185.0, 250.0, 1.0),
    }
    for index, point in defaults.items():
        points[index] = point
    for name, point in overrides.items():
        points[int(name)] = point
    return points


def test_classifies_low_clasped_hands() -> None:
    scores = classify_pose(keypoints(**{"9": (145.0, 245.0, 1.0), "10": (155.0, 245.0, 1.0)}))

    assert scores["hands_clasped_low"] >= 0.8


def test_clasped_hands_at_abdomen_not_only_hips():
    scores = classify_pose(keypoints(**{"9": (145, 190, 1), "10": (155, 190, 1)}))
    assert scores["hands_clasped_low"] >= 0.72


def test_folded_arms_do_not_also_become_clasped_hands():
    scores = classify_pose(
        keypoints(
            **{
                "7": (90, 180, 1),
                "8": (210, 180, 1),
                "9": (170, 180, 1),
                "10": (130, 180, 1),
            }
        )
    )
    assert scores["arms_crossed"] >= 0.76
    assert scores["hands_clasped_low"] == 0


def test_classifies_crossed_arms() -> None:
    scores = classify_pose(
        keypoints(
            **{
                "7": (115.0, 165.0, 1.0),
                "8": (185.0, 165.0, 1.0),
                "9": (180.0, 160.0, 1.0),
                "10": (120.0, 160.0, 1.0),
            }
        )
    )

    assert scores["arms_crossed"] >= 0.76


def test_folded_forearms_detected_even_when_wrists_only_just_cross_centre():
    points = keypoints(
        **{
            "7": (90, 180, 1),
            "8": (210, 180, 1),
            "9": (170, 180, 1),
            "10": (130, 180, 1),
        }
    )
    assert classify_pose(points)["arms_crossed"] >= 0.76


def test_clear_pose_can_be_retained_after_two_samples(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i in range(2):
        collector.observe(i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
    assert collector.finish_all()[0]["duration_seconds"] == 0.4


def test_transcription_requests_word_and_segment_timestamps(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(
        upload_practice,
        "get_settings",
        lambda: SimpleNamespace(
            groq_api_key="test-key",
            upload_practice_whisper_model="test-model",
        ),
    )

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"text": "Hello", "words": [{"word": "Hello", "start": 0, "end": 1}]}

    def request(*args, **kwargs):
        seen.update(kwargs["data"])
        return Response()

    monkeypatch.setattr(upload_practice.requests, "post", request)
    source = tmp_path / "speech.wav"
    source.touch()
    upload_practice.transcribe_audio(source)
    assert seen["timestamp_granularities[]"] == ["word", "segment"]


def test_slow_passage_is_not_automatically_coached_as_a_mistake():
    report = build_coaching_report(
        {
            "pace_events": [
                {"type": "slow", "start_seconds": 90, "end_seconds": 100, "words_per_minute": 80}
            ]
        },
        [],
    )
    finding = report["findings"][0]
    assert "Keep slow sections moving" not in finding["headline"]
    assert "Do not speed up a deliberate closing" in finding["recommendation"]


def test_single_arm_reaching_opposite_shoulder_is_detected():
    for overrides in (
        {"7": (115, 170, 1), "9": (190, 108, 1)},
        {"8": (185, 170, 1), "10": (110, 108, 1)},
    ):
        assert classify_pose(keypoints(**overrides))["arms_crossed"] >= 0.76


def test_hand_at_own_shoulder_is_not_crossed_arm():
    assert classify_pose(keypoints(**{"9": (100, 110, 1)}))["arms_crossed"] == 0


def test_one_arm_crossing_does_not_require_the_other_wrist():
    assert (
        classify_pose(
            keypoints(
                **{
                    "7": (115, 170, 1),
                    "9": (190, 108, 1),
                    "10": (0, 0, 0),
                }
            )
        )["arms_crossed"]
        >= 0.76
    )


def test_brief_score_dropout_does_not_split_sustained_arm_crossing(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i, score in enumerate((0.85, 0.85, 0, 0.85, 0.85, 0.85)):
        collector.observe(i * 0.2, {"arms_crossed": score}, frame, keypoints())
    events = collector.finish_all()
    assert len(events) == 1
    assert events[0]["duration_seconds"] == 1.0  # Dropout is NOT counted.


def test_missing_tracking_cannot_bridge_an_arm_crossing(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i in range(3):
        collector.observe(i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
    collector.observe(0.6, {}, frame, [])
    for i in range(4, 7):
        collector.observe(i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
    events = collector.finish_all()
    assert len(events) == 2
    assert all(event["duration_seconds"] == 0.6 for event in events)
    assert events[0]["end_seconds"] < events[1]["start_seconds"]


def test_does_not_classify_hands_that_only_cross_the_torso_midline() -> None:
    scores = classify_pose(keypoints(**{"9": (165.0, 180.0, 1.0), "10": (135.0, 180.0, 1.0)}))

    assert scores["arms_crossed"] == 0


def test_classifies_gesture_box_excursion() -> None:
    scores = classify_pose(keypoints(**{"7": (35.0, 105.0, 1.0), "9": (-10.0, 108.0, 1.0)}))

    assert scores["gesture_box_excursion"] >= 0.76


def test_wide_arm_can_be_detected_when_other_hand_is_hidden():
    scores = classify_pose(
        keypoints(
            **{
                "7": (35, 105, 1),
                "9": (-10, 108, 1),
                "10": (0, 0, 0),
            }
        )
    )
    assert scores["gesture_box_excursion"] >= 0.76


def test_every_gesture_keeps_evidence_despite_legacy_budget(tmp_path):
    collector = PoseEventCollector(tmp_path, 2, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for start in (0, 2):
        for i in range(3):
            collector.observe(start + i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
        collector.observe(start + 1, {}, frame, [])
    for i in range(6):
        collector.observe(4 + i * 0.2, {"hand_near_face": 0.8}, frame, keypoints())
    events = collector.finish_all()
    assert events[-1]["evidence_index"] is not None
    assert sum(e["evidence_index"] is not None for e in events) == 3
    assert len({e["evidence_index"] for e in events}) == 3


def test_frame_failure_does_not_create_an_evidenceless_detection(monkeypatch, tmp_path):
    import pytest

    monkeypatch.setattr(upload_practice.cv2, "imwrite", lambda *a, **kw: False)
    collector = PoseEventCollector(tmp_path, 0, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i in range(3):
        collector.observe(i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
    with pytest.raises(upload_practice.UploadPracticeError, match="evidence could not be saved"):
        collector.finish_all()
    assert collector.events == []


def test_brief_classification_gap_merges_same_action_but_not_lost_tracking(tmp_path):
    collector = PoseEventCollector(tmp_path, 1, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for i in range(3):
        collector.observe(i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
    collector._finish("arms_crossed")
    for i in range(5, 8):
        collector.observe(i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
    events = collector.finish_all()
    assert len(events) == 1
    assert events[0]["duration_seconds"] == 1.2  # Gap is not counted.
    assert events[0]["end_seconds"] == 1.6


def test_more_than_twelve_detections_all_have_existing_unique_frames(tmp_path):
    collector = PoseEventCollector(tmp_path, 12, 0.2)
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    for event in range(14):
        for i in range(3):
            collector.observe(event * 2 + i * 0.2, {"arms_crossed": 0.85}, frame, keypoints())
        collector.observe(event * 2 + 1, {}, frame, [])
    events = collector.finish_all()
    assert len(events) == 14
    for event in events:
        assert (tmp_path / f"evidence_{event['evidence_index']:03d}.jpg").is_file()


def test_does_not_classify_an_ordinary_forward_or_moderately_wide_gesture() -> None:
    scores = classify_pose(keypoints(**{"7": (80.0, 145.0, 1.0), "9": (45.0, 165.0, 1.0)}))

    assert scores["gesture_box_excursion"] == 0


def test_reliable_presenter_pose_requires_a_visible_face_and_body() -> None:
    without_face = keypoints()
    with_face = keypoints(
        **{
            "0": (150.0, 45.0, 0.9),
            "1": (140.0, 40.0, 0.8),
            "2": (160.0, 40.0, 0.8),
        }
    )

    assert presenter_pose_is_reliable(without_face) is False
    assert presenter_pose_is_reliable(with_face) is True


def test_speech_metrics_include_timed_fillers_and_configured_cautions(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_practice,
        "get_settings",
        lambda: SimpleNamespace(upload_practice_sensitive_terms="idiot"),
    )
    transcription = {
        "text": "Um you know this is an idiot example",
        "words": [
            {"word": "Um", "start": 0.0, "end": 0.2},
            {"word": "you", "start": 0.3, "end": 0.5},
            {"word": "know", "start": 0.5, "end": 0.7},
            {"word": "this", "start": 0.8, "end": 1.0},
            {"word": "is", "start": 1.0, "end": 1.1},
            {"word": "an", "start": 1.1, "end": 1.2},
            {"word": "idiot", "start": 1.2, "end": 1.5},
            {"word": "example", "start": 1.5, "end": 1.8},
        ],
    }

    result = speech_metrics(transcription)

    assert [event["term"] for event in result["filler_events"]] == ["um", "you know"]
    assert result["sensitive_term_flags"][0]["term"] == "idiot"
    assert result["word_count"] == 8


def test_speech_metrics_detect_delivery_events_without_counting_content_like(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        upload_practice,
        "get_settings",
        lambda: SimpleNamespace(upload_practice_sensitive_terms=""),
    )
    tokens = [
        ("It", 0.0, 0.2),
        ("works", 0.2, 0.5),
        ("kind", 0.5, 0.7),
        ("of", 0.7, 0.8),
        ("like", 0.8, 1.0),
        ("a", 1.0, 1.1),
        ("lock", 1.1, 1.4),
        ("and", 1.4, 1.6),
        ("key", 1.6, 1.9),
        ("um", 4.5, 4.7),
        ("we", 4.8, 5.0),
        ("we", 5.0, 5.2),
        ("can", 5.2, 5.4),
        ("continue", 5.4, 5.8),
        ("uh", 6.0, 6.2),
        ("you", 6.4, 6.6),
        ("know", 6.6, 6.8),
    ]
    transcription = {
        "text": " ".join(token[0] for token in tokens),
        "words": [{"word": word, "start": start, "end": end} for word, start, end in tokens],
    }

    result = speech_metrics(transcription)

    assert "kind of" not in [event["term"] for event in result["filler_events"]]
    assert "like" not in [event["term"] for event in result["filler_events"]]
    assert result["pause_events"][0]["duration_seconds"] == 2.6
    assert result["filler_clusters"][0]["count"] == 3
    assert result["repetition_events"][0]["phrase"].lower() == "we"


def test_speech_metrics_retains_complete_pace_series(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_practice,
        "get_settings",
        lambda: SimpleNamespace(upload_practice_sensitive_terms=""),
    )
    words = [
        {"word": f"word{index}", "start": index * 0.3, "end": index * 0.3 + 0.2}
        for index in range(120)
    ]

    result = speech_metrics({"text": " ".join(item["word"] for item in words), "words": words})

    assert len(result["pace_samples"]) >= 5
    assert {"timestamp_seconds", "words_per_minute", "word_count", "type"} <= set(
        result["pace_samples"][0]
    )
    assert all(sample["type"] in {"slow", "steady", "fast"} for sample in result["pace_samples"])


def test_coaching_report_turns_raw_metrics_into_ranked_actions() -> None:
    report = build_coaching_report(
        {
            "words_per_minute": 154.0,
            "pace_events": [
                {
                    "type": "fast",
                    "start_seconds": 30.0,
                    "end_seconds": 70.0,
                    "words_per_minute": 190.0,
                }
            ],
            "filler_events": [
                {"term": "basically", "timestamp_seconds": 10.0},
                {"term": "basically", "timestamp_seconds": 20.0},
                {"term": "basically", "timestamp_seconds": 28.0},
            ],
            "pause_events": [],
            "repetition_events": [],
        },
        [],
    )

    assert [finding["id"] for finding in report["findings"]] == [
        "pace-control",
        "verbal-habit",
    ]
    assert "120–160" in report["findings"][0]["recommendation"]
    assert report["practice_plan"]
    # No events alone must not imply successful body tracking.
    assert not any("posture" in strength for strength in report["strengths"])


def test_speech_metrics_retains_repeated_contextual_verbal_habits(monkeypatch) -> None:
    monkeypatch.setattr(
        upload_practice,
        "get_settings",
        lambda: SimpleNamespace(upload_practice_sensitive_terms=""),
    )
    tokens = "Basically we begin then basically we explain and basically we finish".split()
    transcription = {
        "text": " ".join(tokens),
        "words": [
            {"word": word, "start": index * 0.3, "end": index * 0.3 + 0.2}
            for index, word in enumerate(tokens)
        ],
    }

    result = speech_metrics(transcription)

    assert [event["term"] for event in result["filler_events"]] == [
        "basically",
        "basically",
        "basically",
    ]


def test_pace_never_extrapolates_a_short_final_window() -> None:
    words = [{"word": "test", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(43)]
    samples = upload_practice._pace_samples(words)
    assert [s["start_seconds"] for s in samples] == [0, 5]
    assert all(s["end_seconds"] - s["start_seconds"] == 15 for s in samples)
    assert upload_practice._pace_samples(words[:20]) == []


def test_pace_intervals_break_at_normal_samples_and_do_not_double_count() -> None:
    samples = [
        {
            "start_seconds": i * 5,
            "end_seconds": i * 5 + 15,
            "timestamp_seconds": i * 5 + 7.5,
            "type": kind,
            "words_per_minute": pace,
            "word_count": 50,
            "context": "example",
        }
        for i, (kind, pace) in enumerate(
            [
                ("fast", 200),
                ("fast", 220),
                ("steady", 150),
                ("fast", 190),
            ]
        )
    ]
    events = upload_practice._pace_events(samples)
    assert len(events) == 2
    assert (events[0]["start_seconds"], events[0]["end_seconds"]) == (5, 15)
    assert events[0]["words_per_minute"] == 210
    assert (events[1]["start_seconds"], events[1]["end_seconds"]) == (20, 25)
    assert all("word_count" not in event for event in events)


def test_old_partial_pace_samples_do_not_create_an_event() -> None:
    assert (
        upload_practice._pace_events(
            [
                {
                    "start_seconds": 390,
                    "end_seconds": 391,
                    "timestamp_seconds": 390.5,
                    "type": "fast",
                    "words_per_minute": 600,
                }
            ]
        )
        == []
    )


def test_pose_events_require_sustained_detection_and_save_one_evidence_frame(tmp_path) -> None:
    collector = PoseEventCollector(
        evidence_directory=tmp_path,
        maximum_evidence_frames=12,
        sample_interval=0.2,
    )
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    points = keypoints(**{"9": (145.0, 245.0, 1.0), "10": (155.0, 245.0, 1.0)})
    for sample in range(5):
        collector.observe(sample * 0.2, {"hands_clasped_low": 0.9}, frame, points)
    collector.observe(1.0, {}, frame, points)

    events = collector.finish_all()

    assert len(events) == 1
    assert events[0]["type"] == "hands_clasped_low"
    assert events[0]["evidence_index"] == 1
    assert (tmp_path / "evidence_001.jpg").is_file()
