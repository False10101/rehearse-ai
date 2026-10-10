import uuid

from fastapi import APIRouter, Depends
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
