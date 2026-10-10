from app.services import speech_evidence
from app.services.upload_practice import timed_words


def test_segment_fallback_preserves_numbers_and_punctuation() -> None:
    words = timed_words(
        {"segments": [{"text": "Only 5% survive. Cost: $3.50.", "start": 0, "end": 5}]}
    )
    assert " ".join(w["word"] for w in words) == "Only 5% survive. Cost: $3.50."


def test_excerpt_has_source_text_and_bounded_audio_range() -> None:
    speech = {
        "timed_transcript": [{"word": f"word{i}", "start": i, "end": i + 0.5} for i in range(60)],
        "pace_events": [{"type": "fast", "start_seconds": 10, "end_seconds": 55}],
        "timing_source": "word",
    }
    moments = speech_evidence.speech_moments(speech, [], 60)
    assert len(moments) == 1
    assert moments[0]["end_seconds"] - moments[0]["start_seconds"] <= 35
    assert moments[0]["transcript_excerpt"].startswith("word6 ")
    assert moments[0]["transcript_excerpt"].endswith("word40")


def test_closing_context_is_sent_to_coach(monkeypatch):
    import json

    speech = {
        "timed_transcript": [{"word": "Thanks", "start": i, "end": i + 0.5} for i in range(60)],
        "pace_events": [{"type": "slow", "start_seconds": 50, "end_seconds": 59}],
        "timing_source": "word",
    }
    moments = speech_evidence.speech_moments(speech, [], 60)

    def request(prompt, **kwargs):
        data = json.loads(prompt.split("DATA:\n", 1)[1])[0]
        assert data["speech_position"] == "closing"
        assert data["nearby_context"]
        assert "Do NOT recommend speeding it" in prompt
        return {
            "moments": [
                {
                    "id": 1,
                    "anchor": "Thanks",
                    "observation": "A deliberate closing.",
                    "recommendation": "Keep this pause.",
                    "suggested_delivery": "Thanks. [pause]",
                }
            ]
        }

    monkeypatch.setattr(speech_evidence, "_request_json", request)
    speech_evidence.coach_speech_moments(moments)
    assert moments[0]["coaching_status"] == "ready"


def test_contextual_coaching_rejects_invented_quotes(monkeypatch) -> None:
    monkeypatch.setattr(
        speech_evidence,
        "_request_json",
        lambda *a, **kw: {
            "moments": [
                {
                    "id": 1,
                    "anchor": "invented",
                    "observation": "Issue",
                    "recommendation": "Advice",
                    "suggested_delivery": "Rewrite",
                }
            ],
        },
    )
    moments = [
        {
            "id": 1,
            "kind": "fast",
            "transcript_excerpt": "Only five survive.",
            "coaching_status": "unavailable",
        }
    ]
    speech_evidence.coach_speech_moments(moments)
    assert moments[0]["coaching_status"] == "unavailable"


def test_contextual_coaching_is_attached_to_exact_moment(monkeypatch) -> None:
    monkeypatch.setattr(
        speech_evidence,
        "_request_json",
        lambda *a, **kw: {
            "moments": [
                {
                    "id": 1,
                    "anchor": "five survive",
                    "observation": "Emphasize five.",
                    "recommendation": "Pause after five survive.",
                    "suggested_delivery": "Only five survive. [pause]",
                }
            ],
        },
    )
    moments = [
        {
            "id": 1,
            "kind": "fast",
            "transcript_excerpt": "Only five survive.",
            "coaching_status": "unavailable",
        }
    ]
    speech_evidence.coach_speech_moments(moments)
    assert moments[0]["coaching_status"] == "ready"
    assert "five" in moments[0]["recommendation"]


def test_clip_failure_keeps_report_usable(monkeypatch, tmp_path) -> None:
    def fail(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    monkeypatch.setattr(speech_evidence.subprocess, "run", fail)
    moments = [{"id": 1, "start_seconds": 2, "end_seconds": 12, "audio_available": False}]
    speech_evidence.save_audio_excerpts(tmp_path / "source.wav", tmp_path, moments)
    assert not moments[0]["audio_available"]


def test_partial_coaching_is_preserved_and_only_missing_moment_retried(monkeypatch):
    calls = []

    def request(prompt, **kwargs):
        import json

        data = json.loads(prompt.split("DATA:\n", 1)[1])
        calls.append([m["id"] for m in data])
        return {
            "moments": [
                {
                    "id": m["id"],
                    "anchor": "WRONG" if m["id"] == 2 and len(calls) == 1 else "five survive",
                    "observation": "Emphasize five.",
                    "recommendation": "Pause after five survive.",
                    "suggested_delivery": "Only five survive. [pause]",
                }
                for m in data
            ]
        }

    monkeypatch.setattr(speech_evidence, "_request_json", request)
    moments = [
        {
            "id": i,
            "kind": "fast",
            "transcript_excerpt": "Only five survive.",
            "coaching_status": "unavailable",
        }
        for i in (1, 2, 3)
    ]
    speech_evidence.coach_speech_moments(moments)
    assert calls == [[1, 2, 3], [2]]
    assert all(m["coaching_status"] == "ready" for m in moments)


def test_quote_formatting_does_not_reject_source_phrase(monkeypatch):
    monkeypatch.setattr(
        speech_evidence,
        "_request_json",
        lambda *args, **kwargs: {
            "moments": [
                {
                    "id": 1,
                    "anchor": "IT'S five",
                    "observation": "Emphasize five.",
                    "recommendation": "Pause here.",
                    "suggested_delivery": "It's five. [pause]",
                }
            ]
        },
    )
    moments = [
        {
            "id": 1,
            "kind": "fast",
            "transcript_excerpt": "It’s   five today.",
            "coaching_status": "unavailable",
        }
    ]
    speech_evidence.coach_speech_moments(moments)
    assert moments[0]["coaching_status"] == "ready"


def test_retry_does_not_rewrite_ready_moments(monkeypatch):
    monkeypatch.setattr(
        speech_evidence,
        "_request_json",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Do not call")),
    )
    moments = [{"id": 1, "coaching_status": "ready", "recommendation": "Existing advice"}]
    speech_evidence.coach_speech_moments(moments)
    assert moments[0]["recommendation"] == "Existing advice"
