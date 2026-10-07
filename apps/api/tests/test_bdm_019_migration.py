"""bdm-019 -- migration 0095_bdm_agent_link (spec §3). Round trip and the downgrade refusal run in a throwaway database (the bdm-018
pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from datetime import UTC, datetime

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_bdm_018_migration import VERSIONS, _config, _sql

BASE, HEAD = "0094_bdm_daily_reports", "0095_bdm_agent_link"


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_019_migration_0095", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_chains_after_0094_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_equal_the_model():
    from app.models import BDM_ONBOARDING_CHECKS, BdmOnboardingRequest, BdmOrganization

    migration = _migration()
    assert migration.CHECKS.items() <= BDM_ONBOARDING_CHECKS.items()
    assert set(migration.CHECKS) == {"ck_bdm_onboarding_requests_kind", "ck_bdm_onboarding_requests_completed", "ck_bdm_onboarding_requests_target"}
    model_checks = {c.name: str(c.sqltext) for c in BdmOnboardingRequest.__table__.constraints if isinstance(c, CheckConstraint)}
    assert BDM_ONBOARDING_CHECKS.items() <= model_checks.items()
    assert "uq_bdm_organizations_agent_org" in {c.name for c in BdmOrganization.__table__.constraints}
    assert {fk.parent.name: fk.ondelete for fk in BdmOrganization.__table__.foreign_keys if fk.parent.name == "agent_org_id"} == {"agent_org_id": "RESTRICT"}
    assert {fk.parent.name: fk.ondelete for fk in BdmOnboardingRequest.__table__.foreign_keys if fk.parent.name == "agent_org_id"} == {"agent_org_id": "RESTRICT"}


@pytest.mark.asyncio
async def test_columns_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    org_cols, req_cols = await conn.run_sync(lambda s: ({c["name"] for c in inspect(s).get_columns("bdm_organizations")}, {c["name"] for c in inspect(s).get_columns("bdm_onboarding_requests")}))
    assert "agent_org_id" in org_cols and "agent_org_id" in req_cols


@pytest.fixture
def isolated_db():
    """A fresh database at BASE with one user, one School, one agency and two Agent organizations."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm019_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id, school_id, agency_id, org_a, org_b = (uuid.uuid4() for _ in range(5))
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'overseas', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        _sql(url, "INSERT INTO schools (id, name, created_by_user_id) VALUES (:id, 'S', :u)", {"id": school_id, "u": user_id})
        _sql(url, "INSERT INTO agent_orgs (id, name, prefix, status, master_seq, staff_seq) VALUES (:id, 'A', 'AGX', 'active', 1, 0)", {"id": agency_id})
        for code, org_id in (("ORG-A1", org_a), ("ORG-A2", org_b)):
            _sql(
                url,
                "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) "
                "VALUES (:id, :code, 'agent', 'agent', 'A', 'a', 'K', 'k', :u, :u)",
                {"id": org_id, "code": code, "u": user_id},
            )
        yield {"cfg": cfg, "url": url, "user": user_id, "school": school_id, "agency": agency_id, "org": org_a, "org_b": org_b}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _request(db, **values) -> uuid.UUID:
    request_id = uuid.uuid4()
    values = {"organization_id": db["org"], "kind": "agent", "status": "pending", **values}
    cols = "".join(f", {k}" for k in values)
    vals = "".join(f", :{k}" for k in values)
    _sql(db["url"], f"INSERT INTO bdm_onboarding_requests (id, requested_by_user_id{cols}) VALUES (:id, :u{vals})", {"id": request_id, "u": db["user"], **values})
    return request_id


RESOLVED = {"resolved_at": datetime(2026, 10, 7, 10, tzinfo=UTC)}


def test_round_trip_and_the_widened_checks(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE column_name = 'agent_org_id'")
    with pytest.raises(Exception, match="ck_bdm_onboarding_requests_kind"):
        _request(isolated_db)  # back at 0084's rule: school only
    command.upgrade(cfg, HEAD)
    linked = {"status": "completed", "resolution": "linked", **RESOLVED}
    bad = [
        ({"kind": "college"}, "ck_bdm_onboarding_requests_kind"),
        ({"status": "completed", "resolution": "linked", **RESOLVED}, "ck_bdm_onboarding_requests_completed"),
        ({**linked, "school_id": isolated_db["school"]}, "ck_bdm_onboarding_requests_target"),
        ({"kind": "school", **linked, "school_id": isolated_db["school"], "agent_org_id": isolated_db["agency"]}, "ck_bdm_onboarding_requests_target"),
    ]
    for values, check in bad:
        with pytest.raises(Exception, match=check):
            _request(isolated_db, **values)
    _request(isolated_db, **linked, agent_org_id=isolated_db["agency"])
    _request(isolated_db, kind="school", **linked, school_id=isolated_db["school"])  # a School request still completes
    _sql(url, "UPDATE bdm_organizations SET agent_org_id = :a WHERE id = :o", {"a": isolated_db["agency"], "o": isolated_db["org"]})
    with pytest.raises(Exception, match="uq_bdm_organizations_agent_org"):
        _sql(url, "UPDATE bdm_organizations SET agent_org_id = :a WHERE id = :o", {"a": isolated_db["agency"], "o": isolated_db["org_b"]})


def test_downgrade_refuses_while_agent_requests_or_links_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _request(isolated_db)
    with pytest.raises(Exception, match="agent onboarding data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM bdm_onboarding_requests")
    _sql(url, "UPDATE bdm_organizations SET agent_org_id = :a WHERE id = :o", {"a": isolated_db["agency"], "o": isolated_db["org"]})
    with pytest.raises(Exception, match="agent onboarding data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_organizations SET agent_org_id = NULL")
    _request(isolated_db, kind="school")  # School requests alone do not block this downgrade (0084 owns them)
    command.downgrade(cfg, BASE)
