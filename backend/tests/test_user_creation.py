from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import User
from app.services.users import get_or_create_user


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    User.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_create_and_reuse_user(session):
    user = get_or_create_user(session, "test-subject")
    session.commit()
    assert get_or_create_user(session, "test-subject").id == user.id
    assert len(session.scalars(select(User)).all()) == 1


def test_duplicate_insert_race_recovers_and_preserves_transaction(session, caplog):
    existing = get_or_create_user(session, "test-subject")
    session.commit()
    session.add(User(auth0_subject="other-pending-user"))
    # Emulate a stale initial lookup followed by a uniqueness conflict.
    with patch.object(session, "scalar", side_effect=[None, existing]):
        result = get_or_create_user(session, "test-subject")
    assert result.id == existing.id
    session.commit()
    assert len(session.scalars(select(User)).all()) == 2


def test_unrelated_integrity_error_is_not_swallowed(session):
    with pytest.raises(IntegrityError):
        get_or_create_user(session, None)
