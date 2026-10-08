"""rec-007 -- migration 0108_job_requirements (spec §3; AC6). Backfill, status mapping, skills JSON -> rows and the downgrade refusal run
in a throwaway database built from scratch (the rec-003 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_007_migration_0108", VERSIONS / "0108_job_requirements.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0107_candidates", "0108_job_requirements"


def test_migration_chains_after_0107():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    from app.models import JOB_CHECKS, Job, JobSkill, JobStatusHistory

    assert _migration.CHECKS == JOB_CHECKS
    table = Job.__table__
    assert {name for name, _, _ in _migration.COLUMNS} | {"requirement_code"} <= {c.name for c in table.columns}
    assert not table.c.requirement_code.nullable
    assert all(table.c[name].nullable for name, _, _ in _migration.COLUMNS)
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(JOB_CHECKS) | set(_migration.INDEXES) | {"uq_jobs_requirement_code"} <= names
    assert {c.name for c in JobSkill.__table__.columns} == {"id", "job_id", "skill_id", "name", "kind", "weight", "position"}
    assert {c.name for c in JobStatusHistory.__table__.columns} == {"id", "job_id", "from_status", "to_status", "note", "changed_by_user_id", "created_at"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        command.downgrade(cfg, BASE)  # the real 0107 shape of `jobs`
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _company(url) -> uuid.UUID:
    company_id = uuid.uuid4()
    _sql(url, "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())", {"id": company_id, "n": f"Co {company_id.hex[:6]}"})
    return company_id


def _job(url, company_id, status, skills, created_at) -> uuid.UUID:
    job_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO jobs (id, company_id, title, location, description, skills, status, created_at, updated_at) VALUES (:id, :c, :t, 'Remote', '', CAST(:s AS json), :st, :at, :at)",
        {"id": job_id, "c": company_id, "t": f"Job {status}", "s": json.dumps(skills), "st": status, "at": created_at},
    )
    return job_id


def _skill(url, name, aliases=()) -> uuid.UUID:
    category = _sql(url, "SELECT id FROM skill_categories ORDER BY sort_order LIMIT 1")[0][0]
    skill_id = uuid.uuid4()
    _sql(url, "INSERT INTO skills (id, name, category_id, active, created_at, updated_at) VALUES (:id, :n, :c, true, now(), now())", {"id": skill_id, "n": name, "c": category})
    for alias in aliases:
        _sql(url, "INSERT INTO skill_aliases (id, skill_id, alias) VALUES (:id, :s, :a)", {"id": uuid.uuid4(), "s": skill_id, "a": alias})
    return skill_id


def test_upgrade_maps_statuses_codes_and_skills(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    company = _company(url)
    tag = uuid.uuid4().hex[:6]
    name = f"Zeta{tag}"
    java = _skill(url, name, aliases=(f"Core Zeta{tag}",))  # unique names: 0104 seeds the real Skills Master
    draft = _job(url, company, "draft", [f"core  zeta{tag} ", "Rust-ish"], datetime(2026, 1, 1, tzinfo=UTC))
    opened = _job(url, company, "open", [name.upper(), name.lower()], datetime(2026, 2, 1, tzinfo=UTC))
    closed = _job(url, company, "closed", [], datetime(2026, 3, 1, tzinfo=UTC))
    odd = _job(url, company, "filled", [], datetime(2026, 4, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    rows = dict(_sql(url, "SELECT id, status FROM jobs"))
    assert rows == {draft: "new", opened: "requirement_received", closed: "closed", odd: "on_hold"}
    codes = _sql(url, "SELECT id, requirement_code FROM jobs ORDER BY requirement_code")
    assert codes == [(draft, "REQ-000001"), (opened, "REQ-000002"), (closed, "REQ-000003"), (odd, "REQ-000004")]
    history = sorted(_sql(url, "SELECT job_id, from_status, to_status, note, changed_by_user_id FROM job_status_history"), key=lambda r: r[2])
    assert (odd, None, "on_hold", "Legacy status 'filled'", None) in history
    assert (draft, None, "new", "Legacy status 'draft'", None) in history
    skills = _sql(url, "SELECT job_id, skill_id, name, kind, position FROM job_skills ORDER BY job_id, position")
    assert sorted((r for r in skills if r[0] == draft), key=lambda r: r[4]) == [(draft, java, name, "required", 0), (draft, None, "Rust-ish", "required", 1)]
    assert [r for r in skills if r[0] == opened] == [(opened, java, name, "required", 0)]  # duplicates collapse
    assert json.loads(_sql(url, "SELECT skills::text FROM jobs WHERE id = :id", {"id": draft})[0][0]) == [name, "Rust-ish"]
    later = _job(url, company, "new", [], datetime(2026, 5, 1, tzinfo=UTC))  # an insert path that knows nothing of codes
    assert _sql(url, "SELECT requirement_code FROM jobs WHERE id = :id", {"id": later}) == [("REQ-000005",)]
    with pytest.raises(Exception, match="ck_jobs_status"):
        _sql(url, "UPDATE jobs SET status = 'open'")


def test_round_trip_maps_statuses_back(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    company = _company(url)
    job = _job(url, company, "open", ["Python"], datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    status, skills = _sql(url, "SELECT status, skills::text FROM jobs WHERE id = :id", {"id": job})[0]
    assert (status, json.loads(skills)) == ("open", ["Python"])
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT requirement_code FROM jobs") == [("REQ-000001",)]


@pytest.mark.parametrize("change", ["UPDATE jobs SET department = 'Engineering'", "UPDATE jobs SET priority = 'high'"])
def test_downgrade_refuses_while_requirement_data_exists(isolated_db, change):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _job(url, _company(url), "open", [], datetime(2026, 1, 1, tzinfo=UTC))
    command.upgrade(cfg, HEAD)
    _sql(url, change)
    with pytest.raises(Exception, match="job requirement data"):
        command.downgrade(cfg, BASE)
