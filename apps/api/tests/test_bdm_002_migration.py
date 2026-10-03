"""bdm-002 -- migration 0066_bdm_organizations (spec §4). Round trip and the downgrade refusal run in a throwaway database (the
bdm-001 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_bdm_002_migration_0066", VERSIONS / "0066_bdm_organizations.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0065_agent_notifications"
HEAD = "0066_bdm_organizations"
USERS = "SELECT id, email, role, division FROM users ORDER BY id"


def test_migration_chains_after_0065_and_is_the_single_head():
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
    from app.models import BdmOrganization, BdmOrganizationContact

    org = BdmOrganization.__table__
    assert {c.name for c in org.columns} == {
        "id",
        "code",
        "org_type",
        "bdm_type",
        "name",
        "name_key",
        "city",
        "city_key",
        "state",
        "phone",
        "email",
        "website",
        "existing_partner",
        "courses_interested",
        "student_count",
        "assigned_bdm_user_id",
        "created_by_user_id",
        "archived_at",
        "created_at",
        "updated_at",
    }
    for required in ("code", "org_type", "bdm_type", "name", "name_key", "city", "city_key", "existing_partner", "assigned_bdm_user_id", "created_by_user_id"):
        assert not org.c[required].nullable, required
    names = {i.name for i in org.indexes} | {c.name for c in org.constraints}
    assert {
        "uq_bdm_organizations_code",
        "ck_bdm_organizations_org_type",
        "ck_bdm_organizations_bdm_type",
        "ck_bdm_organizations_student_count",
        "ix_bdm_organizations_type_assignee",
        "ix_bdm_organizations_duplicate_key",
    } <= names
    contact = BdmOrganizationContact.__table__
    assert {c.name for c in contact.columns} == {
        "id",
        "organization_id",
        "position",
        "name",
        "designation",
        "role",
        "phone",
        "email",
        "is_primary",
        "created_at",
        "updated_at",
    }
    names = {i.name for i in contact.indexes} | {c.name for c in contact.constraints}
    assert {"ck_bdm_organization_contacts_role", "ix_bdm_organization_contacts_org", "uq_bdm_organization_contacts_primary"} <= names


@pytest.mark.asyncio
async def test_tables_sequence_and_indexes_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    indexes = await conn.run_sync(lambda sync: {i["name"]: i for i in inspect(sync).get_indexes("bdm_organization_contacts")})
    assert indexes["uq_bdm_organization_contacts_primary"]["unique"]
    assert (await conn.execute(sa.text("SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = 'bdm_organization_code_seq'"))).first()


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
    """A fresh database at 0065 with one bdm user."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm002_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id = uuid.uuid4()
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        yield {"cfg": cfg, "url": url, "user": user_id}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_users_identical_and_drops_the_sequence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, USERS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before
    command.downgrade(cfg, BASE)
    assert _sql(url, USERS) == before
    assert not _sql(url, "SELECT 1 FROM pg_class WHERE relname = 'bdm_organization_code_seq'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, USERS) == before


def test_constraints_hold_and_downgrade_refuses_while_organizations_exist(isolated_db):
    cfg, url, user = isolated_db["cfg"], isolated_db["url"], isolated_db["user"]
    # 0001 builds a fresh database from the current models, so the tables already exist at BASE; drop them and let 0066's own DDL
    # create them, so the constraints below are the migration's, not create_all's.
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    insert = (
        "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) "
        "VALUES (:id, :code, :org_type, 'college', 'A', 'a', 'K', 'k', :u, :u)"
    )
    with pytest.raises(Exception, match="ck_bdm_organizations_org_type"):
        _sql(url, insert, {"id": uuid.uuid4(), "code": "ORG-1", "org_type": "ngo", "u": user})
    org = uuid.uuid4()
    _sql(url, insert, {"id": org, "code": "ORG-2", "org_type": "college", "u": user})
    with pytest.raises(Exception, match="uq_bdm_organizations_code"):
        _sql(url, insert, {"id": uuid.uuid4(), "code": "ORG-2", "org_type": "school", "u": user})
    contact = "INSERT INTO bdm_organization_contacts (id, organization_id, name, is_primary) VALUES (:id, :org, 'C', :p)"
    _sql(url, contact, {"id": uuid.uuid4(), "org": org, "p": True})
    with pytest.raises(Exception, match="uq_bdm_organization_contacts_primary"):
        _sql(url, contact, {"id": uuid.uuid4(), "org": org, "p": True})
    with pytest.raises(Exception, match="organizations exist"):
        command.downgrade(cfg, BASE)
