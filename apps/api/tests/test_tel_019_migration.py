"""tel-019 -- migration 0093_bdm_meeting_requests (spec §2). The round trip runs in a throwaway database (the tel-016 pattern); a downgrade
never runs against the shared test database. 0001 builds a fresh database from the current models, so each test first downgrades to
0092_lead_calls to reach the real pre-tel-019 shape."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_tel_019_migration_0093", VERSIONS / "0093_bdm_meeting_requests.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

NOW = datetime(2026, 10, 7, tzinfo=UTC)
BASE, HEAD = "0092_lead_calls", "0093_bdm_meeting_requests"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


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


def test_migration_chains_after_0092_and_there_is_one_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import APPOINTMENT_MODES, BDM_MEETING_REQUEST_STATUSES, BDM_MEETING_REQUEST_TYPES, BdmMeetingRequest

    table = BdmMeetingRequest.__table__
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == _migration.CHECKS
    assert {i.name for i in table.indexes} == set(_migration.INDEXES)
    assert (_migration.TYPES, _migration.STATUSES, _migration.MODES) == (BDM_MEETING_REQUEST_TYPES, BDM_MEETING_REQUEST_STATUSES, APPOINTMENT_MODES)
    assert {c.name for c in table.columns} == {
        "id", "code", "requester_user_id", "request_type", "bdm_type", "organization_name", "person_name", "contact_phone", "contact_email",
        "proposed_at", "mode", "location", "purpose", "remarks", "status", "bdm_user_id", "bdm_appointment_id", "decline_reason",
        "decided_at", "created_at", "updated_at",
    }


@pytest.fixture
def base_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel019_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, HEAD)
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


USER = ("INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'U', :role, 'it', true, true, 'en-GB', '{}')")
REQUEST = ("INSERT INTO bdm_meeting_requests (id, code, requester_user_id, request_type, bdm_type, organization_name, person_name, "
           "contact_phone, proposed_at, mode, purpose, status, bdm_user_id, decided_at, decline_reason) "
           "VALUES (:id, :code, :requester, 'corporate', 'college', 'Acme', 'Ravi', '9876543210', now(), 'Online', 'Intro', :status, "
           ":bdm, :decided, :reason)")


def _user(url, role):
    uid = uuid.uuid4()
    _sql(url, USER, {"id": uid, "email": f"{uuid.uuid4().hex[:8]}@example.local", "role": role})
    return uid


def test_upgrade_creates_the_table_and_its_rules_and_the_downgrade_is_guarded(base_db):
    cfg, url = base_db["cfg"], base_db["url"]
    assert _sql(url, "SELECT to_regclass('bdm_meeting_requests')") == [(None,)]
    command.upgrade(cfg, HEAD)
    tel, bdm = _user(url, "telecaller"), _user(url, "bdm")
    row = {"requester": tel, "status": "pending", "bdm": None, "decided": None, "reason": None}
    _sql(url, REQUEST, {"id": uuid.uuid4(), "code": "MRQ-000001", **row})
    # accepted without an appointment, declined without a reason, decided without a BDM -> refused
    with pytest.raises(Exception, match="ck_bdm_meeting_requests_accepted"):
        _sql(url, REQUEST, {"id": uuid.uuid4(), "code": "MRQ-000002", **row, "status": "accepted", "bdm": bdm, "decided": NOW})
    with pytest.raises(Exception, match="ck_bdm_meeting_requests_declined"):
        _sql(url, REQUEST, {"id": uuid.uuid4(), "code": "MRQ-000003", **row, "status": "declined", "bdm": bdm, "decided": NOW})
    with pytest.raises(Exception, match="ck_bdm_meeting_requests_decided"):
        _sql(url, REQUEST, {"id": uuid.uuid4(), "code": "MRQ-000004", **row, "status": "declined", "reason": "Busy"})
    with pytest.raises(Exception, match="uq_bdm_meeting_requests_code"):
        _sql(url, REQUEST, {"id": uuid.uuid4(), "code": "MRQ-000001", **row})
    assert _sql(url, "SELECT nextval('bdm_meeting_request_code_seq') > 0") == [(True,)]
    # a downgrade never drops requests silently
    with pytest.raises(Exception, match="meeting requests exist"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM bdm_meeting_requests")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('bdm_meeting_requests')") == [(None,)]
