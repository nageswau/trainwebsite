"""bdm-017 -- migration 0073_enquiry_bdm_attribution (spec §3). Round trip and the downgrade refusal run in a throwaway database
(the bdm-001 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
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
_spec = importlib.util.spec_from_file_location("_bdm_017_migration_0073", VERSIONS / "0073_enquiry_bdm_attribution.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0072_bdm_meeting_reports", "0073_enquiry_bdm_attribution"
NEW_COLUMNS = {"bdm_organization_id", "bdm_user_id", "converted_user_id", "converted_at", "converted_by_user_id"}
ENQUIRIES = "SELECT id, email, source, status FROM enquiries ORDER BY id"


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_migration_chains_after_0072_bdm_meeting_reports_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_model_matches_the_migration():
    from app.models import Enquiry

    table = Enquiry.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    assert all(table.c[name].nullable for name in NEW_COLUMNS)
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert {"ck_enquiries_bdm_attribution", "ck_enquiries_conversion", "ix_enquiries_bdm_org_created", "uq_enquiries_converted_user"} <= names
    fks = {fk.parent.name: (fk.column.table.name, fk.ondelete) for fk in table.foreign_keys}
    assert fks["bdm_organization_id"] == ("bdm_organizations", "RESTRICT")
    for column in ("bdm_user_id", "converted_user_id", "converted_by_user_id"):
        assert fks[column] == ("users", "RESTRICT")


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    rows = (await db_session.execute(sa.text(
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'enquiries' AND column_name = ANY(:names)"),
        {"names": sorted(NEW_COLUMNS)})).scalars().all()
    assert set(rows) == NEW_COLUMNS


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
    """A fresh database at 0072_bdm_meeting_reports with one BDM user, one organization and one website enquiry."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        owner, org = uuid.uuid4(), uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
            "VALUES (:id, :email, 'x', 'Owner', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": owner, "email": f"owner-{name}@example.local"},
        )
        _sql(
            url,
            "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, "
            "created_by_user_id) VALUES (:id, :code, 'college', 'college', 'St Mary', 'st mary', 'Kochi', 'kochi', :owner, :owner)",
            {"id": org, "code": f"ORG-{uuid.uuid4().hex[:6]}", "owner": owner},
        )
        _sql(url, ENQUIRY, {"id": uuid.uuid4()})
        yield {"cfg": cfg, "url": url, "owner": owner, "org": org}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


ENQUIRY = (
    "INSERT INTO enquiries (id, division, name, email, subject, message, source, status, crm_sync_status, metadata_json) "
    "VALUES (:id, 'it', 'Web Lead', 'web@example.local', 'Python', 'Hello there', 'website', 'new', 'pending', '{}')"
)


def test_upgrade_keeps_existing_enquiries_unattributed_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, ENQUIRIES)
    command.upgrade(cfg, HEAD)
    assert _sql(url, ENQUIRIES) == before
    assert _sql(url, "SELECT bdm_organization_id, bdm_user_id, converted_user_id, converted_at, converted_by_user_id FROM enquiries") == [
        (None, None, None, None, None)
    ]
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'enquiries' AND column_name = 'bdm_user_id'")[0][0] == 0
    assert _sql(url, ENQUIRIES) == before


def test_checks_hold_and_downgrade_refuses_while_rows_are_attributed(isolated_db):
    cfg, url, owner, org = isolated_db["cfg"], isolated_db["url"], isolated_db["owner"], isolated_db["org"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_enquiries_bdm_attribution"):
        _sql(url, "UPDATE enquiries SET bdm_organization_id = :org", {"org": org})
    with pytest.raises(Exception, match="ck_enquiries_conversion"):
        _sql(url, "UPDATE enquiries SET converted_user_id = :u", {"u": owner})
    _sql(url, "UPDATE enquiries SET bdm_organization_id = :org, bdm_user_id = :u", {"org": org, "u": owner})
    with pytest.raises(Exception, match="attributed or converted"):
        command.downgrade(cfg, BASE)


def test_one_student_links_to_one_lead_only(isolated_db):
    cfg, url, owner = isolated_db["cfg"], isolated_db["url"], isolated_db["owner"]
    command.upgrade(cfg, HEAD)
    _sql(url, ENQUIRY, {"id": uuid.uuid4()})
    link = "UPDATE enquiries SET converted_user_id = :u, converted_at = now(), converted_by_user_id = :u WHERE id = :id"
    first, second = (row[0] for row in _sql(url, "SELECT id FROM enquiries ORDER BY id"))
    _sql(url, link, {"u": owner, "id": first})
    with pytest.raises(Exception, match="uq_enquiries_converted_user"):
        _sql(url, link, {"u": owner, "id": second})
