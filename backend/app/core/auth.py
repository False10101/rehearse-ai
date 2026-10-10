import logging
import ssl
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import certifi
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    PyJWKClientError,
    PyJWTError,
)

from app.core.config import Settings, get_settings

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Auth0Principal:
    subject: str


def get_auth0_issuer(domain: str) -> str:
    return f"https://{domain.rstrip('/')}/"


def rejected_access_token(error: Exception, detail: str) -> HTTPException:
    logger.warning("Auth0 access token rejected: %s", error.__class__.__name__)
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


@lru_cache
def get_jwks_client(domain: str) -> PyJWKClient:
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    return PyJWKClient(
        f"{get_auth0_issuer(domain)}.well-known/jwks.json",
        ssl_context=ssl_context,
    )


def get_auth0_principal(token: str, settings: Settings) -> Auth0Principal:
    if not settings.auth0_domain or not settings.auth0_audience:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Auth0 is not configured for this API.",
        )

    try:
        signing_key = get_jwks_client(settings.auth0_domain).get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=get_auth0_issuer(settings.auth0_domain),
        )
    except InvalidAudienceError as error:
        raise rejected_access_token(
            error,
            "Auth0 access token was not issued for this API audience.",
        ) from error
    except InvalidIssuerError as error:
        raise rejected_access_token(
            error,
            "Auth0 access token issuer does not match this API configuration.",
        ) from error
    except ExpiredSignatureError as error:
        raise rejected_access_token(error, "Auth0 access token has expired.") from error
    except PyJWKClientError as error:
        raise rejected_access_token(
            error,
            "Auth0 access token signing key could not be verified.",
        ) from error
    except PyJWTError as error:
        raise rejected_access_token(error, "Invalid or expired Auth0 access token.") from error

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Auth0 access token has no subject.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Auth0Principal(subject=subject)


def get_current_auth0_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Auth0Principal:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return get_auth0_principal(credentials.credentials, get_settings())
