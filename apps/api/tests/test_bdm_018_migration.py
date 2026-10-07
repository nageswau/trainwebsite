"""bdm-018 -- migration 0084_bdm_onboarding (spec §3). Round trip and the downgrade refusal run in a throwaway database (the
bdm-005 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
BASE, HEAD = "0083_tel_content", "0084_bdm_onboarding"


def _migration():
    spec = importlib.util.spec_from_file_location("_bdm_018_migration_0084", VERSIONS / f"{HEAD}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config() -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_chains_after_0083_and_is_the_single_head():
    migration = _migration()
    assert (migration.revision, migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_checks_equal_the_model():
    from app.models import BDM_ONBOARDING_CHECKS, BdmOnboardingRequest, BdmOrganization

    # bdm-019's 0098 widened two of 0084's strings and added one; 0084's frozen copy is what 0098 downgrades back to.
    later = importlib.util.spec_from_file_location("_bdm_019_migration_0098", VERSIONS / "0098_bdm_agent_link.py")
    m0098 = importlib.util.module_from_spec(later)
    later.loader.exec_module(m0098)
    assert _migration().CHECKS == {**{k: v for k, v in BDM_ONBOARDING_CHECKS.items() if k not in m0098.CHECKS}, **m0098.SCHOOL_ONLY}
    assert {k: v for k, v in BDM_ONBOARDING_CHECKS.items() if k in m0098.CHECKS} == m0098.CHECKS
    model_checks = {c.name: str(c.sqltext) for c in BdmOnboardingRequest.__table__.constraints if isinstance(c, CheckConstraint)}
    assert BDM_ONBOARDING_CHECKS.items() <= model_checks.items()
    assert {"uq_bdm_onboarding_requests_pending", "ix_bdm_onboarding_requests_status"} <= {i.name for i in BdmOnboardingRequest.__table__.indexes}
    assert "uq_bdm_organizations_school" in {c.name for c in BdmOrganization.__table__.constraints}
    assert {fk.parent.name: fk.ondelete for fk in BdmOnboardingRequest.__table__.foreign_keys} == {
        "organization_id": "RESTRICT",
        "requested_by_user_id": "RESTRICT",
        "resolved_by_user_id": "RESTRICT",
        "school_id": "RESTRICT",
        "agent_org_id": "RESTRICT",  # bdm-019
    }


@pytest.mark.asyncio
async def test_table_and_link_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    tables, org_columns = await conn.run_sync(lambda sync: (set(inspect(sync).get_table_names()), {c["name"] for c in inspect(sync).get_columns("bdm_organizations")}))
    assert "bdm_onboarding_requests" in tables
    assert "school_id" in org_columns


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
    """A fresh database at BASE with one user, one School and two organizations."""
    cfg = _config()
    original = settings.database_url
    name = f"bdm018_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user_id, school_id, org_a, org_b = (uuid.uuid4() for _ in range(4))
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'overseas', true, true, 'en-GB', '{}')",
            {"id": user_id, "email": f"bdm-{name}@example.local"},
        )
        _sql(url, "INSERT INTO schools (id, name, created_by_user_id) VALUES (:id, 'S', :u)", {"id": school_id, "u": user_id})
        for code, org_id in (("ORG-M1", org_a), ("ORG-M2", org_b)):
            _sql(
                url,
                "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) "
                "VALUES (:id, :code, 'school', 'school', 'A', 'a', 'K', 'k', :u, :u)",
                {"id": org_id, "code": code, "u": user_id},
            )
        yield {"cfg": cfg, "url": url, "user": user_id, "school": school_id, "org": org_a, "org_b": org_b}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _request(db, **values) -> uuid.UUID:
    request_id = uuid.uuid4()
    values = {"organization_id": db["org"], "kind": "school", "status": "pending", **values}
    cols = "".join(f", {k}" for k in values)
    vals = "".join(f", :{k}" for k in values)
    _sql(db["url"], f"INSERT INTO bdm_onboarding_requests (id, requested_by_user_id{cols}) VALUES (:id, :u{vals})", {"id": request_id, "u": db["user"], **values})
    return request_id


def test_round_trip_creates_the_table_and_enforces_the_checks(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    tables = {r[0] for r in _sql(url, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert "bdm_onboarding_requests" not in tables
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'bdm_organizations' AND column_name = 'school_id'")
    command.upgrade(cfg, HEAD)
    _request(isolated_db)
    with pytest.raises(Exception, match="uq_bdm_onboarding_requests_pending"):
        _request(isolated_db)
    resolved = {"resolved_at": datetime(2026, 10, 6, 10, tzinfo=UTC)}
    bad = [
        ({"kind": "agent", "status": "rejected", "reject_reason": "x", **resolved}, "ck_bdm_onboarding_requests_kind"),
        ({"status": "done", **resolved}, "ck_bdm_onboarding_requests_status"),
        ({"status": "rejected", "reject_reason": "x"}, "ck_bdm_onboarding_requests_resolved"),
        ({"status": "completed", "resolution": "created", **resolved}, "ck_bdm_onboarding_requests_completed"),
        ({"status": "rejected", **resolved}, "ck_bdm_onboarding_requests_rejected"),
        ({"status": "completed", "resolution": "merged", "school_id": isolated_db["school"], **resolved}, "ck_bdm_onboarding_requests_resolution"),
    ]
    for values, check in bad:
        with pytest.raises(Exception, match=check):
            _request(isolated_db, **values)
    _request(isolated_db, status="completed", resolution="linked", school_id=isolated_db["school"], **resolved)
    _sql(url, "UPDATE bdm_organizations SET school_id = :s WHERE id = :o", {"s": isolated_db["school"], "o": isolated_db["org"]})
    with pytest.raises(Exception, match="uq_bdm_organizations_school"):
        _sql(url, "UPDATE bdm_organizations SET school_id = :s WHERE id = :o", {"s": isolated_db["school"], "o": isolated_db["org_b"]})


def test_downgrade_refuses_while_requests_or_links_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _request(isolated_db)
    with pytest.raises(Exception, match="onboarding data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM bdm_onboarding_requests")
    _sql(url, "UPDATE bdm_organizations SET school_id = :s WHERE id = :o", {"s": isolated_db["school"], "o": isolated_db["org"]})
    with pytest.raises(Exception, match="onboarding data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE bdm_organizations SET school_id = NULL")
    command.downgrade(cfg, BASE)
