"""rec-029 -- migration 0147_recruitment_drives (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch
(the rec-028 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_rec_030_migration import _setup
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_rec_029_migration_0147", VERSIONS / "0147_recruitment_drives.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0146_interview_feedback", "0147_recruitment_drives"
DRIVE_COLUMNS = {
    "id", "drive_code", "company_id", "college_org_id", "college_name", "drive_date", "job_role", "vacancies", "eligibility",
    "students_registered", "students_attended", "status", "created_by_user_id", "created_at", "updated_at",
}


def test_migration_chains_after_0146_and_there_is_a_single_head():
    assert _migration.revision == HEAD and len(HEAD) <= 32
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import RECRUITMENT_DRIVE_CHECKS, RECRUITMENT_DRIVE_STATUSES, DriveRequirement, JobApplication, RecruitmentDrive

    assert _migration.CHECKS == RECRUITMENT_DRIVE_CHECKS and _migration.STATUSES == RECRUITMENT_DRIVE_STATUSES
    assert {c.name for c in RecruitmentDrive.__table__.columns} == DRIVE_COLUMNS
    assert {c.name for c in DriveRequirement.__table__.columns} == {"drive_id", "job_id"}
    assert "drive_id" in JobApplication.__table__.columns
    constraints = {c.name: c for c in RecruitmentDrive.__table__.constraints}
    for name, sql in _migration.CHECKS.items():
        assert str(constraints[name].sqltext) == sql
    indexes = {i.name for t in (RecruitmentDrive.__table__, DriveRequirement.__table__, JobApplication.__table__) for i in t.indexes}
    assert {"ix_recruitment_drives_company_date", "ix_recruitment_drives_date", "ix_drive_requirements_job", "ix_job_applications_drive"} <= indexes


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec029_migration_{uuid.uuid4().hex[:8]}"
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
def _drive(url, company_id, user_id, **sql_values: str) -> uuid.UUID:
    """One drive; each keyword overrides a column with a SQL literal (or "NULL")."""
    row = uuid.uuid4()
    values = {"college_name": "'ABC'", "drive_date": "DATE '2026-11-20'", "job_role": "'GET'", "vacancies": "10", **sql_values}
    _sql(
        url,
        f"INSERT INTO recruitment_drives (id, drive_code, company_id, created_by_user_id, {', '.join(values)}) "
        f"VALUES (:id, :code, :c, :u, {', '.join(values.values())})",
        {"id": row, "code": f"DRV-{row.hex[:6]}", "c": company_id, "u": user_id},
    )
    return row


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('recruitment_drives')") == [(None,)]
    command.upgrade(cfg, HEAD)
    company_id, user_id = _setup(url)
    _drive(url, company_id, user_id)
    assert _sql(url, "SELECT status, students_registered, students_attended FROM recruitment_drives") == [("planned", 0, 0)]
    cases = {
        "ck_recruitment_drives_status": {"status": "'closed'"},
        "ck_recruitment_drives_college": {"college_name": "NULL"},  # neither an org nor a name
        "ck_recruitment_drives_counts": {"students_attended": "-1"},
        "ck_recruitment_drives_attended": {"students_registered": "10", "students_attended": "11"},  # AC2
        "ck_recruitment_drives_vacancies": {"vacancies": "0"},
    }
    for name, override in cases.items():
        with pytest.raises(Exception, match=name):
            _drive(url, company_id, user_id, **override)
    assert _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'job_applications' AND column_name = 'drive_id'") == [("drive_id",)]
    _sql(url, "DELETE FROM recruitment_drives")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('recruitment_drives')") == [(None,)]
    assert _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'job_applications' AND column_name = 'drive_id'") == []
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_drives_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _drive(url, *_setup(url))
    with pytest.raises(Exception, match="drives exist"):
        command.downgrade(cfg, BASE)
