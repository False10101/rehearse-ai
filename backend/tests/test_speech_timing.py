import wave

import numpy as np
import pytest

from app.services.speech_timing import audio_silences, contextualize_pace
from app.services.upload_practice import _pause_events


def test_pause_requires_audio_evidence_not_just_a_transcription_gap():
    words = [{"word": "First.", "start": 0, "end": 1},
             {"word": "Next.", "start": 5, "end": 6}]
    assert _pause_events(words, []) == []
    assert _pause_events(words, [{"start": 2, "end": 3}]) == []
    pauses = _pause_events(words, [{"start": 1.1, "end": 4.9}])
    assert len(pauses) == 1
    assert pauses[0]["duration_seconds"] == 3.8
    assert pauses[0]["timing_source"] == "audio"


def test_measures_quiet_audio_between_sound_and_excludes_spoken_sections(tmp_path):
    rate = 16000
    tone = (np.sin(np.arange(rate) * 2 * np.pi * 220 / rate) * 12000).astype("<i2")
    data = np.concatenate([tone, np.zeros(rate * 3, dtype="<i2"), tone])
    path = tmp_path / "test.wav"
    with wave.open(str(path), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(data.tobytes())
    silence = audio_silences(path)
    assert len(silence) == 1
    assert silence[0]["start"] == pytest.approx(1, abs=.06)
    assert silence[0]["end"] == pytest.approx(4, abs=.06)


def sample(start, pace, count, kind="slow"):
    return {"start_seconds": start, "end_seconds": start + 15,
            "words_per_minute": pace, "word_count": count, "type": kind}


def test_pause_explains_low_overall_pace_without_changing_measured_graph_value():
    samples = [sample(0, 80, 20)]
    contextualize_pace(samples, [{"end": 60}], [{"start": 3, "end": 9}])
    assert samples[0]["words_per_minute"] == 80
    assert samples[0]["type"] == "steady"
    assert samples[0]["active_words_per_minute"] > 100


def test_moderate_closing_slowdown_is_not_a_speed_up_instruction():
    samples = [sample(0, 140, 35, "steady"), sample(15, 140, 35, "steady"),
               sample(30, 96, 24)]
    contextualize_pace(samples, [{"end": 45}], [])
    assert samples[-1]["type"] == "steady"
    assert samples[-1]["context"] == "Closing slowdown"


def test_markedly_slow_speech_and_fast_speech_are_still_reviewable():
    samples = [sample(0, 140, 35, "steady"), sample(15, 220, 55, "fast"),
               sample(30, 48, 12)]
    contextualize_pace(samples, [{"end": 45}], [])
    assert samples[1]["type"] == "fast"
    assert samples[-1]["type"] == "slow"
