import logging

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import create_app


def test_http_rejection_logs_reason_and_request_id(caplog):
    app = create_app()

    @app.get("/test-rejection")
    def reject():
        raise HTTPException(413, "File exceeds upload limit")

    with caplog.at_level(logging.INFO):
        response = TestClient(app).get(
            "/test-rejection?secret=hidden", headers={"Authorization": "Bearer hidden-token"}
        )
    assert response.status_code == 413
    assert response.headers["x-request-id"] in caplog.text
    assert "File exceeds upload limit" in caplog.text
    assert "hidden-token" not in caplog.text
    assert "secret=hidden" not in "\n".join(
        record.message for record in caplog.records if record.name.startswith("app.")
    )


def test_validation_logs_fields_without_input(caplog):
    app = create_app()

    @app.post("/test-validation")
    def validate(count: int):
        return count

    with caplog.at_level(logging.WARNING):
        response = TestClient(app).post("/test-validation?count=private-input")
    assert response.status_code == 422
    assert "int_parsing" in caplog.text
    assert "private-input" not in caplog.text


def test_unhandled_error_logs_traceback(caplog):
    app = create_app()

    @app.get("/test-error")
    def fail():
        raise RuntimeError("test failure")

    with caplog.at_level(logging.ERROR):
        response = TestClient(app, raise_server_exceptions=False).get("/test-error")
    assert response.status_code == 500
    assert "path=/test-error" in caplog.text
    assert "RuntimeError: test failure" in caplog.text
