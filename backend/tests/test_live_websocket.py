from fastapi.testclient import TestClient

from app.api.v1 import live
from app.core.auth import Auth0Principal
from app.main import app


def authenticate(websocket) -> None:
    websocket.send_json({"type": "authenticate", "access_token": "test-token"})
    assert websocket.receive_json()["type"] == "ready"


def observation(sequence: int) -> dict:
    return {
        "type": "observation",
        "sequence": sequence,
        "timestamp_ms": 1_000 + sequence,
        "person_detected": False,
    }


def test_live_websocket_rejects_observations_while_paused(monkeypatch) -> None:
    monkeypatch.setattr(
        live,
        "_authenticate_websocket_message",
        lambda payload: Auth0Principal(subject="auth0|test-user"),
    )

    with TestClient(app).websocket_connect("/api/v1/live/stream") as websocket:
        authenticate(websocket)
        websocket.send_json({"type": "pause"})
        assert websocket.receive_json()["type"] == "paused"
        websocket.send_json(observation(1))
        warning = websocket.receive_json()
        assert warning["code"] == "LIVE_SESSION_PAUSED"
        websocket.send_json({"type": "resume"})
        assert websocket.receive_json()["type"] == "resumed"
        websocket.send_json(observation(1))
        assert websocket.receive_json()["type"] == "feedback"


def test_live_websocket_rejects_replayed_sequence_and_recalibrates(monkeypatch) -> None:
    monkeypatch.setattr(
        live,
        "_authenticate_websocket_message",
        lambda payload: Auth0Principal(subject="auth0|test-user"),
    )

    with TestClient(app).websocket_connect("/api/v1/live/stream") as websocket:
        authenticate(websocket)
        websocket.send_json(observation(2))
        assert websocket.receive_json()["type"] == "feedback"
        websocket.send_json(observation(2))
        assert websocket.receive_json()["code"] == "LIVE_STALE_OBSERVATION"
        websocket.send_json({"type": "recalibrate", "timestamp_ms": 2_000})
        recalibrating = websocket.receive_json()
        assert recalibrating["type"] == "recalibrating"
        assert recalibrating["calibration_required"] > 0
