from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


def get_or_create_user(session: Session, auth0_subject: str) -> User:
    user = session.scalar(select(User).where(User.auth0_subject == auth0_subject))
    if user is None:
        user = User(auth0_subject=auth0_subject)
        session.add(user)
        session.flush()
    return user
