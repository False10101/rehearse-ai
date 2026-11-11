import uuid
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import auth
from app.core.config import Settings
from app.db import session as db
from app.db.models import GuestSession, User, Presentation, UploadPracticeSession, Job
from app.api.v1 import auth as auth_api, practice, presentations, live
from app.main import create_app


@compiles(JSONB, "sqlite")
def compile_json(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def guest_app(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (User, GuestSession, Presentation, UploadPracticeSession, Job):
        model.__table__.create(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(guest_access_enabled=True, guest_practice_sample_id=None)
    monkeypatch.setattr(db, "get_session_factory", lambda: factory)
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth_api, "get_settings", lambda: settings, raising=False)
    from app.core import config
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(practice, "get_settings", lambda: settings)
    monkeypatch.setattr(live, "get_settings", lambda: settings)
    app = create_app()
    def database():
        with factory() as session:
            yield session
    app.dependency_overrides[db.get_db_session] = database
    yield TestClient(app), factory, settings
    engine.dispose()


def enter(client):
    response = client.post("/api/v1/auth/guest")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    token = response.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def test_guest_identity_persists_and_tokens_are_hashed(guest_app):
    client, factory, _ = guest_app
    token, headers = enter(client)
    me = client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 200
    assert client.get("/api/v1/auth/me", headers=headers).json() == me.json()
    with factory() as session:
        stored = session.scalar(select(GuestSession))
        assert stored.token_hash != token and len(stored.token_hash) == 64
    assert live._authenticate_websocket_message({"type": "authenticate", "access_token": token}).subject == me.json()["auth0_subject"]
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}bad"}).status_code == 401


def test_guest_workspaces_cannot_read_each_others_decks(guest_app):
    client, factory, _ = guest_app
    _, first = enter(client)
    _, second = enter(client)
    first_id = uuid.UUID(client.get("/api/v1/auth/me", headers=first).json()["id"])
    with factory() as session:
        deck = Presentation(user_id=first_id, title="Private guest deck", original_filename="deck.pptx", status="completed")
        session.add(deck); session.commit(); deck_id = deck.id
    assert client.get(f"/api/v1/presentations/{deck_id}", headers=second).status_code == 404
    assert client.get(f"/api/v1/presentations/{deck_id}/slides/1/image", headers=second).status_code == 404
    assert client.get(f"/api/v1/presentations/{deck_id}/transcript", headers=second).status_code == 404
    with factory() as session:
        assert presentations.owned_presentation(session, first_id, deck_id).id == deck_id


def test_closing_guest_access_and_leaving_revoke_access(guest_app):
    client, _, settings = guest_app
    token, headers = enter(client)
    assert client.delete("/api/v1/auth/guest", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    _, headers = enter(client)
    settings.guest_access_enabled = False
    assert client.post("/api/v1/auth/guest").status_code == 403
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_guest_upload_and_report_mutations_are_blocked(guest_app):
    client, _, _ = guest_app
    _, headers = enter(client)
    base = "/api/v1/practice/upload/sessions"
    assert client.post(base, headers=headers, files={"file": ("sample.mp4", b"video", "video/mp4")}).status_code == 403
    report_id = uuid.uuid4()
    for suffix in ["/speech/retry", "/gesture-review/0"]:
        assert client.post(f"{base}/{report_id}{suffix}", headers=headers).status_code == 403
    assert client.delete(f"{base}/{report_id}", headers=headers).status_code == 403
    assert client.get(base, headers=headers).json() == []


def test_only_selected_completed_sample_and_its_media_are_readable(guest_app, monkeypatch, tmp_path):
    client, factory, settings = guest_app
    _, headers = enter(client)
    with factory() as session:
        owner = User(auth0_subject="google|sample-owner")
        session.add(owner); session.flush()
        report = UploadPracticeSession(user_id=owner.id, original_filename="sample.mp4", status="completed",
            pose_events=[{"clip_index": 0, "evidence_index": 0}], speech_moments=[{"id": 0, "audio_available": True}])
        session.add(report); session.commit(); report_id, owner_id = report.id, owner.id
    base = f"/api/v1/practice/upload/sessions/{report_id}"
    assert client.get(base + "/gesture/0", headers=headers).status_code == 404
    settings.guest_practice_sample_id = str(report_id)
    paths = []
    def storage(key):
        paths.append(key)
        path = tmp_path / Path(key).name
        path.write_bytes(b"sample media")
        return path
    monkeypatch.setattr(practice, "storage_path", storage)
    monkeypatch.setattr(practice, "evidence_path", lambda owner, report, index: storage(f"{owner}/{report}/frame.jpg"))
    for suffix in ["/gesture/0", "/speech/0", "/evidence/0"]:
        assert client.get(base + suffix, headers=headers).status_code == 200
    assert all(str(owner_id) in path for path in paths)
    with factory() as session:
        guest = session.scalar(select(User).where(User.auth0_subject.like("guest|%")))
        assert practice.readable_session(session, guest, report_id).id == report_id
        with pytest.raises(HTTPException):
            practice.readable_session(session, guest, uuid.uuid4())


def test_normal_tokens_still_use_auth0(monkeypatch):
    expected = auth.Auth0Principal(subject="google|account")
    monkeypatch.setattr(auth, "get_auth0_principal", lambda token, settings: expected)
    assert auth.get_access_principal("jwt-token", Settings()) == expected


def test_sample_list_and_report_keep_signed_in_ownership(guest_app):
    client, factory, settings = guest_app
    _, headers = enter(client)
    with factory() as session:
        owner = User(auth0_subject="google|sample-owner")
        session.add(owner); session.flush()
        record = UploadPracticeSession(user_id=owner.id, original_filename="demo.mp4", status="completed")
        session.add(record); session.commit(); report_id = record.id
    settings.guest_practice_sample_id = str(report_id)
    base = "/api/v1/practice/upload/sessions"
    listed = client.get(base, headers=headers)
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [str(report_id)]
    response = client.get(f"{base}/{report_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["original_filename"] == "demo.mp4"
    with factory() as session:
        outsider = User(auth0_subject="google|someone-else")
        session.add(outsider); session.flush()
        with pytest.raises(HTTPException):
            practice.readable_session(session, outsider, report_id)


@pytest.mark.parametrize("endpoint,job_type", [("/api/v1/presentations", "slide_analysis"), ("/api/v1/presentations/transcript", "transcript_prepare")])
def test_guest_can_upload_a_deck_for_both_workflows(guest_app, monkeypatch, endpoint, job_type):
    client, factory, _ = guest_app
    _, headers = enter(client)
    from app.services import background_jobs
    monkeypatch.setattr(background_jobs, "run_background_job", lambda *args: None)
    saved = []
    async def save_upload(file, key, limit):
        saved.append((file.filename, key))
    monkeypatch.setattr(presentations, "save_upload", save_upload)
    response = client.post(endpoint, headers=headers, files={"file": ("guest.pptx", b"test upload", "application/vnd.openxmlformats-officedocument.presentationml.presentation")})
    assert response.status_code == 202
    with factory() as session:
        deck = session.get(Presentation, uuid.UUID(response.json()["id"]))
        job = session.get(Job, uuid.UUID(response.json()["job_id"]))
        guest = session.get(User, deck.user_id)
        assert guest.auth0_subject.startswith("guest|")
        assert job.user_id == guest.id and job.job_type == job_type
        assert str(guest.id) in saved[0][1]


def test_guest_live_websocket_connects_with_actual_guest_credential(guest_app):
    client, _, _ = guest_app
    token, _ = enter(client)
    with client.websocket_connect("/api/v1/live/stream") as websocket:
        websocket.send_json({"type": "authenticate", "access_token": token})
        assert websocket.receive_json()["type"] == "ready"
