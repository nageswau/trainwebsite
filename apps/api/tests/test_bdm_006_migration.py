"""bdm-006 -- migration 0070_bdm_appointments (spec §4). Round trip and the downgrade refusal run in a throwaway database (the
bdm-001/002 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_bdm_006_migration_0070", VERSIONS / "0070_bdm_appointments.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0069_bdm_org_profiles"
HEAD = "0070_bdm_appointments"
ORGS = "SELECT id, code FROM bdm_organizations ORDER BY id"


def test_migration_chains_after_0069_bdm_org_profiles_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


def test_models_match_the_migration():
    from app.models import BdmAppointment, BdmAppointmentEvent

    appt = BdmAppointment.__table__
    assert {c.name for c in appt.columns} == {
        "id", "code", "bdm_user_id", "organization_id", "contact_id", "contact_name", "contact_designation", "contact_phone",
        "contact_email", "starts_at", "duration_minutes", "appointment_type", "location", "purpose", "remarks", "status", "outcome",
        "next_follow_up_on", "expected_leads", "expected_revenue", "created_at", "updated_at",
        "trip_id",  # bdm-011, migration 0085
    }
    for required in ("code", "bdm_user_id", "organization_id", "contact_name", "starts_at", "duration_minutes", "appointment_type", "status"):
        assert not appt.c[required].nullable, required
    assert appt.c.contact_id.nullable
    assert next(iter(appt.c.contact_id.foreign_keys)).ondelete == "SET NULL"
    names = {i.name for i in appt.indexes} | {c.name for c in appt.constraints}
    assert {
        "uq_bdm_appointments_code", "ck_bdm_appointments_status", "ck_bdm_appointments_type", "ck_bdm_appointments_outcome",
        "ck_bdm_appointments_outcome_completed", "ck_bdm_appointments_follow_up", "ck_bdm_appointments_duration",
        "ck_bdm_appointments_expected_leads", "ck_bdm_appointments_expected_revenue", "ix_bdm_appointments_bdm_starts",
        "ix_bdm_appointments_org_starts", "ix_bdm_appointments_contact",
    } <= names
    event = BdmAppointmentEvent.__table__
    assert {c.name for c in event.columns} == {
        "id", "appointment_id", "actor_user_id", "from_status", "to_status", "old_starts_at", "new_starts_at", "reason", "position", "created_at",
    }
    names = {i.name for i in event.indexes} | {c.name for c in event.constraints}
    assert {"ck_bdm_appointment_events_to_status", "ix_bdm_appointment_events_appointment"} <= names


def test_catalogues_match_the_source():
    from app.models import (
        BDM_APPOINTMENT_AGENT_OUTCOMES,
        BDM_APPOINTMENT_ALL_TYPES,
        BDM_APPOINTMENT_COMMON_OUTCOMES,
        BDM_APPOINTMENT_COMMON_TYPES,
        BDM_APPOINTMENT_MODULE_TYPES,
    )

    assert len(BDM_APPOINTMENT_COMMON_TYPES) == 8
    assert {k: len(v) for k, v in BDM_APPOINTMENT_MODULE_TYPES.items()} == {"agent": 9, "school": 11, "college": 12}
    assert len(BDM_APPOINTMENT_COMMON_OUTCOMES) == 9 and len(BDM_APPOINTMENT_AGENT_OUTCOMES) == 8
    assert len(BDM_APPOINTMENT_ALL_TYPES) == len(set(BDM_APPOINTMENT_ALL_TYPES))
    assert all(max(len(k) for k in group) <= 40 for group in (BDM_APPOINTMENT_ALL_TYPES, BDM_APPOINTMENT_COMMON_OUTCOMES))


@pytest.mark.asyncio
async def test_tables_and_sequence_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert (await conn.execute(sa.text("SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = 'bdm_appointment_code_seq'"))).first()
    assert (await conn.execute(sa.text("SELECT 1 FROM pg_class WHERE relname = 'bdm_appointment_events'"))).first()


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@pytest.fixture
def isolated_db():
    """A fresh database at 0069_bdm_org_profiles with one bdm user, one organization and one contact."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        # bdm-007's tables (built by 0001's create_all from the current models) reference bdm_appointments, which 0070 drops.
        _sql(url, "DROP TABLE IF EXISTS bdm_tasks, bdm_meeting_reports")
        user, org, contact = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"bdm-{name}@example.local"})
        _sql(url, "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) VALUES (:id, 'ORG-9', 'college', 'college', 'A', 'a', 'K', 'k', :u, :u)", {"id": org, "u": user})
        _sql(url, "INSERT INTO bdm_organization_contacts (id, organization_id, name, is_primary) VALUES (:id, :org, 'C', true)", {"id": contact, "org": org})
        yield {"cfg": cfg, "url": url, "user": user, "org": org, "contact": contact}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_organizations_and_drops_the_sequence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, ORGS)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, ORGS) == before
    assert not _sql(url, "SELECT 1 FROM pg_class WHERE relname = 'bdm_appointment_code_seq'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, ORGS) == before


INSERT = (
    "INSERT INTO bdm_appointments (id, code, bdm_user_id, organization_id, contact_id, contact_name, starts_at, appointment_type, status, outcome) "
    "VALUES (:id, :code, :u, :org, :c, 'C', now(), :type, :status, :outcome)"
)


def test_constraints_hold_and_downgrade_refuses_while_appointments_exist(isolated_db):
    cfg, url, user, org, contact = (isolated_db[k] for k in ("cfg", "url", "user", "org", "contact"))
    # 0001 builds a fresh database from the current models, so the tables already exist at BASE; drop them and let 0070's own DDL
    # create them, so the constraints below are the migration's, not create_all's.
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    row = {"u": user, "org": org, "c": contact, "type": "college_meeting", "status": "scheduled", "outcome": None}
    with pytest.raises(Exception, match="ck_bdm_appointments_type"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-1", "type": "lunch"})
    with pytest.raises(Exception, match="ck_bdm_appointments_outcome_completed"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-2", "status": "completed"})
    with pytest.raises(Exception, match="ck_bdm_appointments_outcome_completed"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-3", "outcome": "interested"})
    appt = uuid.uuid4()
    _sql(url, INSERT, {**row, "id": appt, "code": "APT-4"})
    with pytest.raises(Exception, match="uq_bdm_appointments_code"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-4"})
    # A5: deleting the contact nulls the link and keeps the snapshot.
    _sql(url, "DELETE FROM bdm_organization_contacts WHERE id = :c", {"c": contact})
    assert _sql(url, "SELECT contact_id, contact_name FROM bdm_appointments WHERE id = :id", {"id": appt}) == [(None, "C")]
    with pytest.raises(Exception, match="appointments exist"):
        command.downgrade(cfg, BASE)


def test_inlined_migration_catalogues_equal_the_model_tuples():
    from app.models import BDM_APPOINTMENT_ALL_OUTCOMES, BDM_APPOINTMENT_ALL_TYPES, BDM_APPOINTMENT_STATUSES

    assert _migration.STATUSES == BDM_APPOINTMENT_STATUSES
    assert _migration.ALL_TYPES == BDM_APPOINTMENT_ALL_TYPES
    assert _migration.ALL_OUTCOMES == BDM_APPOINTMENT_ALL_OUTCOMES
