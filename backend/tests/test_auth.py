import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import get_auth0_issuer, get_auth0_principal
from app.core.config import Settings
from app.main import create_app


def test_auth0_issuer_normalizes_trailing_slash() -> None:
    assert get_auth0_issuer("dreamy-7102004.eu.auth0.com/") == (
        "https://dreamy-7102004.eu.auth0.com/"
    )


def test_auth0_requires_domain_and_audience() -> None:
    with pytest.raises(HTTPException) as exception:
        get_auth0_principal("not-used", Settings(auth0_domain=None, auth0_audience=None))

    assert exception.value.status_code == 503


def test_auth_me_requires_a_bearer_token() -> None:
    response = TestClient(create_app()).get("/api/v1/auth/me")

    assert response.status_code == 401
