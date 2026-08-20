"""``StyleGuide`` (Story 4.2): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_report_payload_store.py``. Covers the row's
own shape, the append-only version numbering, ``current_style_guide()``'s two
outcomes, and the ``before_update`` immutability guard.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy.exc import IntegrityError, StatementError
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres.style_guide import (
    StyleGuide,
    StyleGuideMissingError,
    create_style_guide_version,
    current_style_guide,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


# --- Row shape ----------------------------------------------------------------


def test_a_style_guide_id_is_uuidv7(session: Session) -> None:
    stored = create_style_guide_version(session, "Some content.")
    session.commit()

    assert isinstance(stored.id, UUID) and stored.id.version == 7


def test_the_first_version_created_is_1(session: Session) -> None:
    stored = create_style_guide_version(session, "Some content.")
    session.commit()

    assert stored.version == 1
    assert stored.content == "Some content."
    assert stored.created_at is not None


def test_create_style_guide_version_only_flushes_never_commits(session: Session) -> None:
    stored = create_style_guide_version(session, "Some content.")
    stored_id = stored.id
    session.rollback()

    assert session.get(StyleGuide, stored_id) is None


# --- Append-only versioning -----------------------------------------------------


def test_each_save_inserts_version_max_plus_1(session: Session) -> None:
    first = create_style_guide_version(session, "v1 content")
    session.commit()
    second = create_style_guide_version(session, "v2 content")
    session.commit()
    third = create_style_guide_version(session, "v3 content")
    session.commit()

    assert first.version == 1
    assert second.version == 2
    assert third.version == 3


def test_a_new_save_leaves_prior_rows_untouched(session: Session) -> None:
    first = create_style_guide_version(session, "v1 content")
    session.commit()

    create_style_guide_version(session, "v2 content")
    session.commit()

    reloaded_first = session.get(StyleGuide, first.id)
    assert reloaded_first is not None
    assert reloaded_first.version == 1
    assert reloaded_first.content == "v1 content"


# --- current_style_guide() -------------------------------------------------------


def test_current_style_guide_raises_when_the_table_is_empty(session: Session) -> None:
    with pytest.raises(StyleGuideMissingError, match="no rows"):
        current_style_guide(session)


def test_current_style_guide_returns_the_highest_version(session: Session) -> None:
    create_style_guide_version(session, "v1 content")
    session.commit()
    create_style_guide_version(session, "v2 content")
    session.commit()
    third = create_style_guide_version(session, "v3 content")
    session.commit()

    current = current_style_guide(session)

    assert current.id == third.id
    assert current.version == 3
    assert current.content == "v3 content"


# --- Immutability ----------------------------------------------------------------


def test_mutating_and_committing_a_persisted_style_guide_raises(session: Session) -> None:
    stored = create_style_guide_version(session, "v1 content")
    session.commit()

    stored.content = "tampered"
    session.add(stored)
    with pytest.raises((RuntimeError, StatementError)) as caught:
        session.commit()

    session.rollback()
    # The underlying RuntimeError may arrive wrapped by SQLAlchemy's flush
    # machinery (StatementError) depending on dialect -- either way, our own
    # message must be present, proving the guard fired rather than some
    # unrelated failure.
    assert "immutable" in str(caught.value)


# --- Uniqueness --------------------------------------------------------------------


def test_version_is_unique(session: Session) -> None:
    session.add(StyleGuide(version=1, content="a"))
    session.commit()

    session.add(StyleGuide(version=1, content="b"))
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
