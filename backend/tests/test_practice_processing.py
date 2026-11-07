from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier, Event
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import upload_practice
from app.services.practice_processing import PracticeProgress, run_practice_tracks


def test_both_tracks_start_before_either_finishes():
    barrier = Barrier(2)

    def work(value):
        barrier.wait(timeout=2)
        return value

    assert run_practice_tracks(lambda: work("gesture-result"), lambda: work("speech-result")) == (
        "gesture-result", "speech-result",
    )


def test_worker_failure_is_propagated_only_after_other_worker_stops_using_files():
    started, release, finished = Event(), Event(), Event()

    def gestures():
        started.set()
        assert release.wait(2)
        finished.set()

    def speech():
        assert started.wait(2)
        release.set()
        raise ValueError("Transcription unavailable")

    with pytest.raises(ValueError, match="Transcription unavailable"):
        run_practice_tracks(gestures, speech)
    assert finished.is_set()


def test_concurrent_progress_is_monotonic_and_keeps_both_independent_tracks():
    saved = []
    reporter = PracticeProgress(lambda **values: saved.append(values))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reporter.update, track, percent, "Reviewing")
                   for track in ("gestures", "speech") for percent in (5, 70, 35, 100)]
        for future in futures:
            future.result()
    progress = [row["progress_percent"] for row in saved]
    assert progress == sorted(progress)
    assert progress[-1] == 95
    assert saved[0]["pose_tracking"]["processing"]["speech"]["progress_percent"] == 0
    assert saved[-1]["pose_tracking"]["processing"]["speech"]["progress_percent"] == 100


def test_no_audio_skips_only_the_speech_track(monkeypatch, tmp_path):
    monkeypatch.setattr(upload_practice, "extract_audio", lambda *args: pytest.fail("No audio"))
    saved = []
    speech, moments = upload_practice._review_speech(
        tmp_path / "silent.mp4", tmp_path / "speech.wav", tmp_path,
        SimpleNamespace(has_audio=False), PracticeProgress(lambda **kw: saved.append(kw)),
    )
    assert speech["word_count"] == 0 and moments == []
    track = saved[-1]["pose_tracking"]["processing"]["speech"]
    assert track["status"] == "skipped" and track["progress_percent"] == 100


def test_full_job_combines_parallel_results_before_cleaning_source(monkeypatch, tmp_path):
    source = tmp_path / "upload" / "test.mp4"
    source.parent.mkdir()
    source.write_bytes(b"source video")
    session_id, user_id = uuid4(), uuid4()
    barrier = Barrier(2)
    saved = []
    metadata = SimpleNamespace(duration_seconds=60, width=640, height=480,
                               codec="h264", has_audio=False)
    speech, _ = upload_practice._review_speech(
        source, source.with_suffix(".wav"), tmp_path, metadata,
        PracticeProgress(lambda **kwargs: None),
    )
    speech.update(transcript="Original speech", word_count=2)

    def gesture_worker(*args):
        barrier.wait(timeout=2)
        assert source.exists()
        return [{"type": "arms_crossed"}], {"status": "reliable"}

    def speech_worker(*args):
        barrier.wait(timeout=2)
        assert source.exists()
        return speech, [{"id": 1, "recommendation": "Specific advice"}]

    monkeypatch.setattr(upload_practice, "storage_path", lambda key:
                        source if key == "source-key" else tmp_path / "evidence")
    database = SimpleNamespace(get=lambda *args: SimpleNamespace(user_id=user_id))
    monkeypatch.setattr(
        upload_practice, "get_session_factory", lambda: lambda: nullcontext(database),
    )
    monkeypatch.setattr(upload_practice, "_update_session", lambda sid, **kw: saved.append(kw))
    monkeypatch.setattr(upload_practice, "probe_video", lambda path: metadata)
    monkeypatch.setattr(upload_practice, "_review_gestures", gesture_worker)
    monkeypatch.setattr(upload_practice, "_review_speech", speech_worker)
    upload_practice.run_upload_practice(session_id, "source-key")
    final = saved[-1]
    assert final["status"] == "completed" and final["progress_percent"] == 100
    assert final["transcript"] == "Original speech"
    assert final["speech_moments"][0]["recommendation"] == "Specific advice"
    assert final["pose_events"] == [{"type": "arms_crossed"}]
    assert final["pose_tracking"] == {"status": "reliable"}
    assert not source.exists()
