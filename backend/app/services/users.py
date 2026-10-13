import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User

logger = logging.getLogger(__name__)


def get_or_create_user(session: Session, auth0_subject: str) -> User:
    user = session.scalar(select(User).where(User.auth0_subject == auth0_subject))
    if user is None:
        try:
            # Isolate the insert so a concurrent first request does not abort
            # the caller's transaction when the unique subject already exists.
            with session.begin_nested():
                user = User(auth0_subject=auth0_subject)
                session.add(user)
                session.flush()
        except IntegrityError as error:
            # Only a uniqueness conflict can be an expected creation race.
            if (getattr(error.orig, "sqlstate", None) != "23505"
                    and getattr(error.orig, "sqlite_errorcode", None) != 2067):
                raise
            user = session.scalar(select(User).where(User.auth0_subject == auth0_subject))
            if user is None:
                logger.exception("User creation failed; no matching account exists")
                raise
            logger.info("Concurrent user creation recovered; using existing account")
    return user
