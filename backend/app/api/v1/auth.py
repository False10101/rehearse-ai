import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import Auth0Principal, get_current_auth0_principal
from app.db.models import User
from app.db.session import get_db_session
from app.services.users import get_or_create_user

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    auth0_subject: str
    email: str | None
    display_name: str | None


@router.get("/me", response_model=CurrentUserResponse)
def get_current_user(
    principal: Auth0Principal = Depends(get_current_auth0_principal),
    session: Session = Depends(get_db_session),
) -> User:
    user = get_or_create_user(session, principal.subject)
    if user.id is None:
        session.commit()
        session.refresh(user)
    else:
        session.commit()

    return user


@router.post("/guest")
def create_guest_session(response: Response, session: Session = Depends(get_db_session)):
    import hashlib
    import secrets
    from app.core.config import get_settings
    from app.db.models import GuestSession

    if not get_settings().guest_access_enabled:
        raise HTTPException(403, "Guest access is currently closed.")
    token = "guest_" + secrets.token_urlsafe(48)
    user = User(auth0_subject=f"guest|{uuid.uuid4()}", display_name="Guest")
    session.add(user)
    session.flush()
    session.add(GuestSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id))
    session.commit()
    response.headers["Cache-Control"] = "no-store"
    return {"access_token": token}


@router.delete("/guest", status_code=204)
def leave_guest_session(
    principal: Auth0Principal = Depends(get_current_auth0_principal),
    session: Session = Depends(get_db_session),
):
    from sqlalchemy import delete
    from app.db.models import GuestSession

    if not principal.subject.startswith("guest|"):
        raise HTTPException(403, "This is not a guest session.")
    user = get_or_create_user(session, principal.subject)
    session.execute(delete(GuestSession).where(GuestSession.user_id == user.id))
    session.commit()
