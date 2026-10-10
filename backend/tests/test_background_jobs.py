from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.services import background_jobs


class Database:
    def __init__(self, job, record):
        self.job = job
        self.record = record
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def get(self, model, key):
        return self.job if model is background_jobs.Job else self.record

    def scalars(self, query):
        return SimpleNamespace(all=lambda: [self.job.id])

    def commit(self):
        self.commits += 1


class Connection:
    def __init__(self, available=True):
        self.available = available
        self.unlocked = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def scalar(self, query, parameters):
        return self.available

    def execute(self, query, parameters):
        self.unlocked = True


def setup(monkeypatch, kind="upload_practice", available=True):
    job = SimpleNamespace(
        id=uuid4(),
        target_id=uuid4(),
        job_type=kind,
        status="running",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    record = SimpleNamespace(
        status="processing",
        speech_moments=[{"coaching_status": "ready"}],
        transcript="Saved text",
        progress_percent=80,
    )
    database = Database(job, record)
    connection = Connection(available)
    monkeypatch.setattr(background_jobs, "get_session_factory", lambda: lambda: database)
    monkeypatch.setattr(
        background_jobs, "get_engine", lambda: SimpleNamespace(connect=lambda: connection)
    )
    return job, record, database, connection


def test_restart_fails_abandoned_upload_and_preserves_evidence(monkeypatch):
    job, record, database, connection = setup(monkeypatch)
    job.status = "processing"  # Upload jobs use this state, unlike AI deck jobs.
    assert background_jobs.recover_interrupted_jobs(datetime.now(UTC)) == 1
    assert job.status == record.status == "failed"
    assert record.processing_error_code == "JOB_INTERRUPTED"
    assert record.transcript == "Saved text"
    assert record.speech_moments == [{"coaching_status": "ready"}]
    assert connection.unlocked


def test_restart_does_not_interrupt_another_worker(monkeypatch):
    job, record, database, connection = setup(monkeypatch, available=False)
    assert background_jobs.recover_interrupted_jobs(datetime.now(UTC)) == 0
    assert job.status == "running"
    assert record.status == "processing"
    assert database.commits == 0


def test_bulk_interruption_does_not_change_presentation_or_saved_content(monkeypatch):
    job, record, database, connection = setup(monkeypatch, kind="transcript_generate_all")
    background_jobs.recover_interrupted_jobs(datetime.now(UTC))
    assert job.status == "failed"
    assert record.transcript == "Saved text"
    assert record.status == "processing"


def test_canceled_job_cannot_be_started_again(monkeypatch):
    job, record, database, connection = setup(monkeypatch)
    job.status = "failed"
    called = []
    background_jobs.run_background_job(job.id, lambda: called.append(True))
    assert called == []
    assert connection.unlocked


def test_uncaught_task_error_fails_job_and_releases_lock(monkeypatch):
    job, record, database, connection = setup(monkeypatch)

    def fail():
        raise RuntimeError("test failure")

    background_jobs.run_background_job(job.id, fail)
    assert job.status == "failed"
    assert record.status == "failed"
    assert connection.unlocked


def test_task_cannot_return_and_leave_job_running(monkeypatch):
    job, record, database, connection = setup(monkeypatch)
    background_jobs.run_background_job(job.id, lambda: None)
    assert job.status == "failed"
    assert connection.unlocked


def test_completed_job_is_not_changed_by_wrapper(monkeypatch):
    job, record, database, connection = setup(monkeypatch)

    def finish():
        job.status = "completed"

    background_jobs.run_background_job(job.id, finish)
    assert job.status == "completed"
    assert record.status == "processing"
    assert connection.unlocked
