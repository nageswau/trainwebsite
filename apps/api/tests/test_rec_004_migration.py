"""rec-004 -- migration 0108_company_contacts (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
(the rec-003 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_004_migration_0108", VERSIONS / "0108_company_contacts.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0107_candidates", "0108_company_contacts"
COLUMNS = {
    "id",
    "company_id",
    "position",
    "name",
    "designation",
    "department",
    "role_id",
    "mobile",
    "mobile_normalized",
    "email",
    "linkedin_url",
    "preferred_channel",
    "notes",
    "is_primary",
    "active",
    "created_by_user_id",
    "created_at",
    "updated_at",
}


def test_migration_chains_after_0107_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import COMPANY_CONTACT_CHECKS, CompanyContact

    table = CompanyContact.__table__
    assert {c.name for c in table.columns} == COLUMNS
    assert _migration.CHECKS == COMPANY_CONTACT_CHECKS
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(_migration.CHECKS) | set(_migration.INDEXES) <= names
    for name, sql in _migration.CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    assert not table.c.name.nullable and not table.c.company_id.nullable


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec004_migration_{uuid.uuid4().hex[:8]}"
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


def _company(url) -> uuid.UUID:
    company_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": company_id, "n": f"Co {company_id.hex[:6]}"},
    )
    return company_id


def _contact(url, company_id, primary=False, active=True):
    _sql(
        url,
        "INSERT INTO company_contacts (id, company_id, name, is_primary, active, created_at, updated_at) VALUES (:id, :c, 'Priya', :p, :a, now(), now())",
        {"id": uuid.uuid4(), "c": company_id, "p": primary, "a": active},
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('company_contacts')") == [(None,)]
    command.upgrade(cfg, HEAD)
    company_id = _company(url)
    _contact(url, company_id, primary=True)
    with pytest.raises(Exception, match="uq_company_contacts_primary"):
        _contact(url, company_id, primary=True)
    with pytest.raises(Exception, match="ck_company_contacts_primary_active"):
        _contact(url, company_id, primary=True, active=False)
    with pytest.raises(Exception, match="ck_company_contacts_channel"):
        _sql(url, "UPDATE company_contacts SET preferred_channel = 'fax'")
    _sql(url, "DELETE FROM company_contacts")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('company_contacts')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_contacts_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _contact(url, _company(url))
    with pytest.raises(Exception, match="company contacts exist"):
        command.downgrade(cfg, BASE)
