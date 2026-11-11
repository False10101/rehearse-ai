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
    assert moments[0]["end_seconds"] == 59
    assert moments[0]["transcript_excerpt"].startswith("word6 ")
    assert moments[0]["transcript_excerpt"].endswith("word58")


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
                    "recommendation": "Keep the pause after Thanks.",
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
                    "recommendation": "Pause after It's five.",
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


def test_all_displayed_pace_intervals_keep_evidence_after_twelfth_moment():
    speech = {
        "timed_transcript": [{"word": f"word{i}", "start": i, "end": i + .5} for i in range(300)],
        "pace_events": [{"type": "fast", "start_seconds": i * 15, "end_seconds": i * 15 + 5}
                        for i in range(18)],
    }
    moments = speech_evidence.speech_moments(speech, [], 300)
    assert len(moments) == 18
    assert moments[-1]["event_start_seconds"] == 255
    assert "word255" in moments[-1]["transcript_excerpt"]


def test_source_anchor_without_excerpt_specific_advice_is_retried(monkeypatch):
    calls = []

    def request(*args, **kwargs):
        calls.append(1)
        return {"moments": [{"id": 1, "anchor": "carbon nanotubes",
                             "observation": "Your speech needs improvement.",
                             "recommendation": "Speak clearly and slow down.",
                             "suggested_delivery": "carbon nanotubes"}]}

    monkeypatch.setattr(speech_evidence, "_request_json", request)
    moments = [{"id": 1, "transcript_excerpt": "carbon nanotubes form a network."}]
    speech_evidence.coach_speech_moments(moments)
    assert len(calls) == 3
    assert moments[0]["coaching_status"] == "unavailable"
    assert "recommendation" not in moments[0]


def test_measured_pause_sends_actual_words_on_each_side():
    words = [{'word': 'even', 'start': 0, 'end': .4},
             {'word': 'when', 'start': .4, 'end': 1},
             {'word': 'our', 'start': 6, 'end': 6.3},
             {'word': 'schedule', 'start': 6.3, 'end': 7}]
    speech = {'timed_transcript': words, 'timing_source': 'word',
              'pause_events': [{'start_seconds': 1, 'end_seconds': 6, 'duration_seconds': 5,
                                'timing_source': 'audio'}]}
    findings = [{'id': 'long-pause', 'category': 'Speech', 'start_seconds': 1, 'end_seconds': 6}]
    moment = speech_evidence.speech_moments(speech, findings, 10)[0]
    pause = moment['pause_measurements'][0]
    assert pause['words_before'] == 'even when'
    assert pause['words_after'] == 'our schedule'


def test_slow_coaching_gets_event_words_and_active_pace(monkeypatch):
    import json
    speech = {'timed_transcript': [{'word': 'Connect', 'start': i, 'end': i + .5} for i in range(35)],
              'pace_events': [{'type': 'slow', 'start_seconds': 10, 'end_seconds': 20}],
              'pace_samples': [{'start_seconds': 5, 'end_seconds': 20, 'words_per_minute': 112,
                                'active_words_per_minute': 150, 'quiet_seconds': 3.8, 'type': 'slow'}]}
    moments = speech_evidence.speech_moments(speech, [], 35)
    def request(prompt, **kwargs):
        data = json.loads(prompt.split('DATA:\n', 1)[1])[0]
        assert data['event_start_seconds'] == 10
        assert data['event_transcript']
        assert data['pace_measurements'][0]['active_words_per_minute'] == 150
        assert 'Do not prescribe\nadditional pauses as the main correction' in prompt
        return {'moments': [{'id': 1, 'anchor': 'Connect', 'observation': 'Connect is spaced out.',
                             'recommendation': 'Keep Connect moving within its phrase.',
                             'suggested_delivery': 'Connect'}]}
    monkeypatch.setattr(speech_evidence, '_request_json', request)
    speech_evidence.coach_speech_moments(moments)
    assert moments[0]['coaching_status'] == 'ready'
