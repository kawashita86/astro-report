"""``ExportedPdf`` (Story 10.1): the stored-PDF cache's row shape, its
hit/miss/replace behaviour, the fingerprint's sensitivity to every hashed
input, and that deleting a Client removes its cached PDFs without a foreign-key
error (checked against an FK-enforcing SQLite, which ignores them by default).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, select

from core.ephemeris.chart import compute_natal_chart
from core.ephemeris.identity import verify_ephemeris_identity
from core.types.place import ResolvedPlace
from shell.adapters.postgres.client import (
    Client,
    create_client_with_chart,
    delete_client_and_derived,
)
from shell.adapters.postgres.exported_pdf import (
    ExportedPdf,
    get_stored_pdf,
    pdf_fingerprint,
    store_pdf,
)
from shell.adapters.postgres.report import Report, store_report
from shell.adapters.postgres.report_run import ReportRun
from shell.computation import load_computation_config
from tests._fk import fk_enforcing_session

_CONFIG = load_computation_config()
_PLACE = ResolvedPlace(
    latitude=Decimal("32.7358"),
    longitude=Decimal("-97.3453"),
    iana_zone="America/Chicago",
    utc_offset=timedelta(hours=-6),
)


def _a_passed_report(session: Session) -> tuple[Client, Report]:
    chart = compute_natal_chart(
        datetime(2026, 1, 1, 6, 0, tzinfo=UTC), _PLACE.latitude, _PLACE.longitude, _CONFIG
    )
    client = create_client_with_chart(
        session,
        name="Ada Lovelace",
        birth_date=date(2026, 1, 1),
        birth_time=time(0, 0),
        resolved_place=_PLACE,
        natal_chart=chart,
        computation_config=_CONFIG,
        ephemeris_identity=verify_ephemeris_identity(),
    )
    run = ReportRun(client_id=client.id, month="2026-01")
    session.add(run)
    session.commit()
    report = store_report(
        session,
        run=run,
        style_guide_version=1,
        payload_schema_version=1,
        gate_vocabulary_version=1,
        gate_vocabulary_content_hash="e" * 64,
    )
    session.commit()
    return client, report


def test_a_stored_pdf_is_served_only_for_a_matching_fingerprint() -> None:
    with fk_enforcing_session() as session:
        _, report = _a_passed_report(session)
        store_pdf(session, report.id, "a" * 64, b"%PDF-one")
        session.commit()

        assert get_stored_pdf(session, report.id, "a" * 64) == b"%PDF-one"
        assert get_stored_pdf(session, report.id, "b" * 64) is None
        assert get_stored_pdf(session, uuid4(), "a" * 64) is None


def test_storing_again_replaces_the_row_so_there_is_one_per_report() -> None:
    with fk_enforcing_session() as session:
        _, report = _a_passed_report(session)
        store_pdf(session, report.id, "a" * 64, b"%PDF-one")
        session.commit()
        store_pdf(session, report.id, "b" * 64, b"%PDF-two")
        session.commit()

        rows = session.exec(select(ExportedPdf)).all()
        assert len(rows) == 1
        assert rows[0].fingerprint == "b" * 64
        assert rows[0].pdf_bytes == b"%PDF-two"
        assert get_stored_pdf(session, report.id, "a" * 64) is None


def test_a_store_failure_is_swallowed_and_leaves_the_session_usable() -> None:
    """A row for a report that does not exist violates the FK (the same
    ``IntegrityError`` family as a race on the unique ``report_id``): the
    download must still succeed."""
    with fk_enforcing_session() as session:
        _a_passed_report(session)

        store_pdf(session, uuid4(), "a" * 64, b"%PDF")

        assert session.exec(select(ExportedPdf)).all() == []
        assert session.exec(select(Report)).all() != []


def test_deleting_a_client_removes_its_stored_pdfs_before_its_reports() -> None:
    with fk_enforcing_session() as session:
        client, report = _a_passed_report(session)
        store_pdf(session, report.id, "a" * 64, b"%PDF-one")
        session.commit()

        delete_client_and_derived(session, client=client)
        session.commit()

        assert session.exec(select(ExportedPdf)).all() == []
        assert session.exec(select(Report)).all() == []


def _inputs() -> dict[str, Any]:
    return {
        "rendered": {"amore": {"text": "x"}},
        "client_name": "Ada",
        "birth_date": date(1990, 5, 17),
        "birth_time": time(9, 30),
        "birthplace_name": "Milano",
        "month": "2026-01",
        "chart_id": UUID(int=1),
        "template_hash": "t" * 64,
        "natal_orbs": Decimal("8"),
    }


def test_the_fingerprint_is_stable_and_64_hex_characters() -> None:
    fingerprint = pdf_fingerprint(**_inputs())

    assert fingerprint == pdf_fingerprint(**_inputs())
    assert len(fingerprint) == 64
    int(fingerprint, 16)


@pytest.mark.parametrize(
    ("field", "changed"),
    [
        ("rendered", {"amore": {"text": "hand-corrected"}}),
        ("client_name", "Ada L."),
        ("birth_date", date(1990, 5, 18)),
        ("birth_time", time(9, 31)),
        ("birthplace_name", "Roma"),
        ("month", "2026-02"),
        ("chart_id", UUID(int=2)),
        ("template_hash", "u" * 64),
        ("natal_orbs", Decimal("6")),
    ],
)
def test_the_fingerprint_changes_with_every_hashed_input(field: str, changed: object) -> None:
    baseline = pdf_fingerprint(**_inputs())

    assert pdf_fingerprint(**{**_inputs(), field: changed}) != baseline
