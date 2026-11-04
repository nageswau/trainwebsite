"""hrc-017 -- migration 0265_skill_taxonomy (DEC-SCOPE-388 T1-T3, T5; AC1). Seed, idempotence and the round trip run in a throwaway
database built from scratch (the rec-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_hrc_017_migration_0265", API_ROOT / "alembic" / "versions" / "0265_skill_taxonomy.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0264_candidate_notes_tasks", "0265_skill_taxonomy"
IT_SEED = ["Programming", "Java Technologies", "Frontend", "Database", "Cloud/DevOps"]
NON_IT = ["Engineering", "Healthcare", "Pharmacy", "Finance", "Sales", "Human Resources"]


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


def test_migration_chains_after_candidate_notes_tasks_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import CANDIDATE_SKILL_LEVELS, JOB_SKILL_MIN_LEVELS, SKILL_DOMAINS, JobSkill, SkillCategory

    assert SKILL_DOMAINS == _migration.DOMAINS == ("it", "non_it")
    assert CANDIDATE_SKILL_LEVELS == JOB_SKILL_MIN_LEVELS == _migration.LEVELS
    assert "domain" in SkillCategory.__table__.columns and "min_level" in JobSkill.__table__.columns
    assert JobSkill.__table__.columns["min_level"].nullable
    names = {c.name for m in (SkillCategory, JobSkill) for c in m.__table__.constraints}
    assert {"ck_skill_categories_domain", "ck_job_skills_min_level"} <= names


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc017_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_seed_adds_the_non_it_categories_after_the_untouched_it_seed(isolated_db):
    """AC1: Pharmacy exists with seed skills; every IT category stays `it` and keeps its 37 skills (backlog +/−/E)."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    rows = [tuple(r) for r in _sql(url, "SELECT name, domain FROM skill_categories ORDER BY sort_order")]
    assert rows == [(n, "it") for n in IT_SEED] + [(n, "non_it") for n in NON_IT]
    pharmacy = _sql(url, "SELECT s.name FROM skills s JOIN skill_categories c ON c.id = s.category_id WHERE c.name = 'Pharmacy' ORDER BY s.sort_order")
    assert [r[0] for r in pharmacy] == list(_migration.CATEGORIES["Pharmacy"]) and len(pharmacy) >= 5
    it_count = _sql(url, "SELECT count(*) FROM skills s JOIN skill_categories c ON c.id = s.category_id WHERE c.domain = 'it'")[0][0]
    assert it_count == 37
    assert _sql(url, "SELECT s.name FROM skill_aliases a JOIN skills s ON s.id = a.skill_id WHERE a.alias = 'GMP'")[0][0] == "Good Manufacturing Practice"


def test_seed_is_idempotent_reuses_an_existing_category_and_skips_a_taken_term(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    # a manager already made "Finance" (as IT) and an alias "Accounting" on Java before the migration ran
    _sql(url, "INSERT INTO skill_categories (id, name, sort_order) VALUES (gen_random_uuid(), 'finance', 50)")
    _sql(url, "INSERT INTO skill_aliases (id, skill_id, alias) SELECT gen_random_uuid(), id, 'Accounting' FROM skills WHERE name = 'Java'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT name, domain FROM skill_categories WHERE lower(name) = 'finance'") == [("finance", "it")]
    assert _sql(url, "SELECT 1 FROM skills WHERE lower(name) = 'accounting'") == []
    before = _sql(url, "SELECT count(*) FROM skills")[0][0]
    _sql(url, "UPDATE skills SET name = 'Pharmacovigilance (PV)' WHERE name = 'Pharmacovigilance'")
    for statement, params in _migration.seed_statements():
        _sql(url, statement, params)
    assert _sql(url, "SELECT count(*) FROM skills")[0][0] == before + 1  # the renamed skill is kept; the source spelling comes back


def test_round_trip_constraints_and_downgrade_keeps_referenced_rows(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="ck_skill_categories_domain"):
        _sql(url, "UPDATE skill_categories SET domain = 'other' WHERE name = 'Sales'")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT 1 FROM skill_categories WHERE name = 'Pharmacy'") == []
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name IN ('skill_categories', 'job_skills')")}
    assert not {"domain", "min_level"} & columns
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT domain FROM skill_categories WHERE name = 'Pharmacy'") == [("non_it",)]
