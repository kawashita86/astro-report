"""``CorpusEntry`` (Story 7.1): an in-memory SQLite engine stands in for
Postgres, mirroring ``tests/test_gate_result_store.py``. Covers the row's
own shape, ``add_corpus_entry``/``list_corpus_entries`` ordering, and that
``corpus_entry`` joins the FR-29 Client-deletion cascade only for a *paired*
entry -- an unpaired one (``client_id IS NULL``) survives any Client
deletion.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from datetime import time as time_of_day
from decimal import Decimal
from uuid import UUID

import pytest
from sqlmodel import Session, SQLModel, create_engine

from shell.adapters.postgres import client as client_module
from shell.adapters.postgres.client import (
    Client,
    delete_client_and_derived,
    list_clients,
)
from shell.adapters.postgres.corpus_entry import (
    CorpusEntry,
    add_corpus_entry,
    list_corpus_entries,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _make_client(session: Session, *, name: str = "Ada Lovelace") -> Client:
    client = Client(
        name=name,
        birth_date=date(2026, 1, 1),
        birth_time=time_of_day(0, 0),
        latitude=Decimal("32.7358"),
        longitude=Decimal("-97.3453"),
        iana_zone="America/Chicago",
    )
    session.add(client)
    session.flush()
    return client


# --- Row shape / writer contract --------------------------------------------


def test_a_corpus_entry_id_is_uuidv7(session: Session) -> None:
    entry = add_corpus_entry(session, content="A past report.")
    session.commit()

    assert isinstance(entry.id, UUID) and entry.id.version == 7


def test_add_corpus_entry_persists_plain_text_with_a_null_client_id(session: Session) -> None:
    entry = add_corpus_entry(session, content="Cara cliente, questo mese Marte...")
    session.commit()

    reloaded = session.get(CorpusEntry, entry.id)
    assert reloaded is not None
    assert reloaded.content == "Cara cliente, questo mese Marte..."
    assert reloaded.client_id is None
    assert reloaded.created_at is not None


def test_add_corpus_entry_only_flushes_never_commits(session: Session) -> None:
    entry = add_corpus_entry(session, content="Uncommitted prose.")
    entry_id = entry.id
    session.rollback()

    assert session.get(CorpusEntry, entry_id) is None


def test_list_corpus_entries_is_most_recent_first(session: Session) -> None:
    session.add_all(
        [
            CorpusEntry(content="older", created_at=datetime(2026, 1, 1, tzinfo=UTC)),
            CorpusEntry(content="newer", created_at=datetime(2026, 6, 1, tzinfo=UTC)),
            CorpusEntry(content="middle", created_at=datetime(2026, 3, 1, tzinfo=UTC)),
        ]
    )
    session.commit()

    assert [entry.content for entry in list_corpus_entries(session)] == [
        "newer",
        "middle",
        "older",
    ]


# --- Pairing / month (Story 7.2) ------------------------------------------------


def test_add_corpus_entry_persists_paired_client_id_and_month(session: Session) -> None:
    client = _make_client(session)
    session.commit()

    entry = add_corpus_entry(
        session,
        content="Paired and linked.",
        paired=True,
        client_id=client.id,
        month="2026-05",
    )
    session.commit()

    reloaded = session.get(CorpusEntry, entry.id)
    assert reloaded is not None
    assert reloaded.paired is True
    assert reloaded.client_id == client.id
    assert reloaded.month == "2026-05"


def test_add_corpus_entry_defaults_to_unpaired_with_no_link(session: Session) -> None:
    entry = add_corpus_entry(session, content="Just prose.")
    session.commit()

    reloaded = session.get(CorpusEntry, entry.id)
    assert reloaded is not None
    assert reloaded.paired is False
    assert reloaded.client_id is None
    assert reloaded.month is None


def test_a_paired_entry_may_have_both_link_fields_unset(session: Session) -> None:
    entry = add_corpus_entry(session, content="Chart known, not in the app.", paired=True)
    session.commit()

    reloaded = session.get(CorpusEntry, entry.id)
    assert reloaded is not None
    assert reloaded.paired is True
    assert reloaded.client_id is None
    assert reloaded.month is None


def test_list_clients_orders_by_name_then_id(session: Session) -> None:
    zoe = _make_client(session, name="Zoe")
    ada_1 = _make_client(session, name="Ada")
    ada_2 = _make_client(session, name="Ada")
    session.commit()

    listed = list_clients(session)

    assert [c.name for c in listed] == ["Ada", "Ada", "Zoe"]
    ada_ids = [c.id for c in listed[:2]]
    assert ada_ids == sorted([ada_1.id, ada_2.id])
    assert listed[2].id == zoe.id


# --- FR-29 cascade ---------------------------------------------------------------


def test_the_cascade_constant_includes_corpus_entry() -> None:
    assert "corpus_entry" in client_module._CLIENT_CASCADE_TABLES


def test_a_paired_corpus_entry_is_deleted_with_its_client(session: Session) -> None:
    client = _make_client(session)
    session.commit()
    paired = CorpusEntry(content="paired to this client", client_id=client.id)
    session.add(paired)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    assert session.get(CorpusEntry, paired.id) is None


def test_an_unpaired_corpus_entry_survives_a_client_deletion(session: Session) -> None:
    client = _make_client(session)
    session.commit()
    unpaired = add_corpus_entry(session, content="unpaired -- client_id is NULL")
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(Client, client.id) is None
    survived = session.get(CorpusEntry, unpaired.id)
    assert survived is not None
    assert survived.client_id is None


def test_deleting_one_client_touches_only_its_own_paired_entry(session: Session) -> None:
    """I/O & Edge-Case Matrix rows 8 and 9 together: a Client with one paired
    entry plus an unrelated unpaired entry -- deleting the Client removes the
    paired entry and leaves the unpaired one untouched."""
    client = _make_client(session)
    session.commit()
    paired = CorpusEntry(content="paired", client_id=client.id)
    unpaired = CorpusEntry(content="unpaired")
    session.add_all([paired, unpaired])
    session.commit()

    delete_client_and_derived(session, client=client)
    session.commit()

    assert session.get(CorpusEntry, paired.id) is None
    assert session.get(CorpusEntry, unpaired.id) is not None


def test_delete_client_and_derived_does_not_persist_corpus_deletion_without_a_commit(
    session: Session,
) -> None:
    client = _make_client(session)
    session.commit()
    paired = CorpusEntry(content="paired", client_id=client.id)
    session.add(paired)
    session.commit()

    delete_client_and_derived(session, client=client)
    session.rollback()

    assert session.get(Client, client.id) is not None
    assert session.get(CorpusEntry, paired.id) is not None
