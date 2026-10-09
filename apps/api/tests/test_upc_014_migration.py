"""upc-014 -- migration 0126_university_agreements (spec §2). Round trip, constraints and the downgrade refusal run in a throwaway database
built from scratch (the rec-008 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql
from tests.test_upc_026_migration import _setup

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_upc_014_migration_0126", VERSIONS / "0126_university_agreements.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0125_university_comms", "0126_university_agreements"
AGREEMENT_COLUMNS = {
    "id", "mou_number", "university_id", "agreement_type", "status", "status_changed_at", "start_date", "expiry_date", "renewal_date",
    "commercial_terms", "exclusivity", "territory", "recruitment_rights", "all_courses", "course_ids", "country_ids", "payment_terms",
    "marketing_rights", "document_id", "edusphere_signatory_user_id", "edusphere_signed_on", "university_signatory_name", "university_signed_on",
    "previous_agreement_id", "created_by_user_id", "created_at", "updated_at",
}  # fmt: skip
EVENT_COLUMNS = {"id", "agreement_id", "kind", "from_status", "to_status", "actor_user_id", "note", "changed", "position", "created_at"}


def test_migration_chains_after_0125_and_there_is_a_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import (
        UNIVERSITY_AGREEMENT_CHECKS,
        UNIVERSITY_AGREEMENT_EVENT_KINDS,
        UNIVERSITY_AGREEMENT_STATUSES,
        UNIVERSITY_AGREEMENT_TYPES,
        UniversityAgreement,
        UniversityAgreementEvent,
    )

    assert _migration.TYPES == UNIVERSITY_AGREEMENT_TYPES and _migration.STATUSES == UNIVERSITY_AGREEMENT_STATUSES
    assert _migration.EVENT_KINDS == UNIVERSITY_AGREEMENT_EVENT_KINDS
    assert _migration.CHECKS == UNIVERSITY_AGREEMENT_CHECKS
    agreements, events = UniversityAgreement.__table__, UniversityAgreementEvent.__table__
    assert {c.name for c in agreements.columns} == AGREEMENT_COLUMNS
    assert {c.name for c in events.columns} == EVENT_COLUMNS
    names = {i.name for t in (agreements, events) for i in t.indexes} | {c.name for t in (agreements, events) for c in t.constraints}
    expected = {"uq_university_agreements_mou_number", "uq_university_agreements_previous", "ix_university_agreements_university",
                "ix_university_agreements_expiry", "ix_university_agreement_events_agreement", "ck_university_agreement_events_kind"}  # fmt: skip
    assert set(UNIVERSITY_AGREEMENT_CHECKS) | expected <= names
    for name, sql in UNIVERSITY_AGREEMENT_CHECKS.items():
        assert str(next(c for c in agreements.constraints if c.name == name).sqltext) == sql


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc014_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _agreement(url, uni_id, user_id, **over) -> uuid.UUID:
    values = {
        "id": uuid.uuid4(), "n": f"MOU-{uuid.uuid4().hex[:6]}", "u": uni_id, "by": user_id, "type": "mou", "status": "draft",
        "start": date(2026, 1, 1), "expiry": date(2029, 1, 1), "renewal": None, "excl": "exclusive", "prev": None,
    } | over  # fmt: skip
    _sql(
        url,
        "INSERT INTO university_agreements (id, mou_number, university_id, agreement_type, status, status_changed_at, start_date, expiry_date, "
        "renewal_date, exclusivity, all_courses, course_ids, country_ids, previous_agreement_id, created_by_user_id, created_at, updated_at) "
        "VALUES (:id, :n, :u, :type, :status, now(), :start, :expiry, :renewal, :excl, false, '[]', '[]', :prev, :by, now(), now())",
        values,
    )
    return values["id"]


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('university_agreements')") == [(None,)]
    command.upgrade(cfg, HEAD)
    uni_id, user_id = _setup(url)
    first = _agreement(url, uni_id, user_id, n="MOU-000001")
    assert _sql(url, "SELECT nextval('university_agreement_mou_seq')") == [(1,)]
    with pytest.raises(Exception, match="uq_university_agreements_mou_number"):
        _agreement(url, uni_id, user_id, n="MOU-000001")
    with pytest.raises(Exception, match="ck_university_agreements_dates"):
        _agreement(url, uni_id, user_id, start=date(2026, 1, 1), expiry=date(2025, 12, 31))
    with pytest.raises(Exception, match="ck_university_agreements_renewal_window"):
        _agreement(url, uni_id, user_id, renewal=date(2030, 1, 1))
    with pytest.raises(Exception, match="ck_university_agreements_type"):
        _agreement(url, uni_id, user_id, type="lease")
    with pytest.raises(Exception, match="ck_university_agreements_status"):
        _agreement(url, uni_id, user_id, status="expiring")  # derived, never stored (AG4)
    with pytest.raises(Exception, match="ck_university_agreements_signed_complete"):
        _agreement(url, uni_id, user_id, status="signed")  # AC2 backstop
    _agreement(url, uni_id, user_id, prev=first)
    with pytest.raises(Exception, match="uq_university_agreements_previous"):
        _agreement(url, uni_id, user_id, prev=first)  # AG8: one successor
    _sql(
        url,
        "INSERT INTO university_agreement_events (id, agreement_id, kind, to_status, actor_user_id, changed, created_at) VALUES (:id, :a, 'create', 'draft', :by, '[]', now())",
        {"id": uuid.uuid4(), "a": first, "by": user_id},
    )
    _sql(url, "DELETE FROM university_agreement_events")
    _sql(url, "DELETE FROM university_agreements WHERE previous_agreement_id IS NOT NULL")
    _sql(url, "DELETE FROM university_agreements")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('university_agreements')") == [(None,)]
    assert _sql(url, "SELECT to_regclass('university_agreement_mou_seq')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_agreements_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _agreement(url, *_setup(url))
    with pytest.raises(Exception, match="university agreements exist"):
        command.downgrade(cfg, BASE)
