"""rec-006 -- migration 0102_skills_master (spec §2; AC1). Round trip, seed and the downgrade refusal run in a throwaway database built
from scratch (the tel-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run()."""

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
_spec = importlib.util.spec_from_file_location("_rec_006_migration_0102", API_ROOT / "alembic" / "versions" / "0102_skills_master.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0100_recruiter_profiles", "0102_skills_master"
SKILLS = "SELECT c.name, s.name FROM skills s JOIN skill_categories c ON c.id = s.category_id ORDER BY c.sort_order, s.sort_order"
TAGS = "SELECT s.name, c.name FROM skill_category_tags t JOIN skills s ON s.id = t.skill_id JOIN skill_categories c ON c.id = t.category_id"
ALIASES = "SELECT s.name, a.alias FROM skill_aliases a JOIN skills s ON s.id = a.skill_id ORDER BY s.name, a.alias"
RELATED = "SELECT a.name, b.name FROM skill_related r JOIN skills a ON a.id = r.skill_a_id JOIN skills b ON b.id = r.skill_b_id"

# EVID-018 S2-§2 (lines 1126-1216), in source order; JavaScript's second listing (Frontend) becomes a tag (AC1).
SOURCE = {
    "Programming": ["Java", "Python", "JavaScript", "C", "C++", "C#", "PHP"],
    "Java Technologies": ["Core Java", "Advanced Java", "Spring", "Spring Boot", "Hibernate", "JPA", "Microservices", "REST API", "Maven", "Gradle", "JSP", "Servlets"],
    "Frontend": ["HTML", "CSS", "React", "Angular", "Vue.js"],
    "Database": ["SQL", "MySQL", "PostgreSQL", "Oracle", "MongoDB", "SQL Server"],
    "Cloud/DevOps": ["AWS", "Azure", "GCP", "Docker", "Kubernetes", "Jenkins", "Git"],
}


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


def test_migration_chains_after_the_recruiter_profiles_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import Skill, SkillAlias, SkillCategory, SkillCategoryTag, SkillRelated

    assert {c.name for c in SkillCategory.__table__.columns} == {"id", "name", "active", "sort_order", "created_at", "updated_at"}
    assert {c.name for c in Skill.__table__.columns} == {"id", "name", "category_id", "active", "sort_order", "created_at", "updated_at"}
    assert {c.name for c in SkillAlias.__table__.columns} == {"id", "skill_id", "alias", "created_at"}
    assert {c.name for c in SkillCategoryTag.__table__.columns} == {"skill_id", "category_id"}
    assert {c.name for c in SkillRelated.__table__.columns} == {"skill_a_id", "skill_b_id"}
    names = set()
    for model in (Skill, SkillAlias, SkillCategory, SkillRelated):
        names |= {i.name for i in model.__table__.indexes} | {c.name for c in model.__table__.constraints}
    assert {"uq_skill_categories_name", "uq_skills_name", "ix_skills_category", "uq_skill_aliases_alias", "ix_skill_aliases_skill", "ck_skill_related_order"} <= names


@pytest.fixture
def isolated_db():
    """A fresh database at 0100 (the parent revision)."""
    cfg = _config()
    original = settings.database_url
    name = f"rec006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_seed_holds_every_source_skill_under_its_category_with_aliases_and_the_related_pair(isolated_db):
    """AC1: 37 skills in 5 categories (source order); JavaScript once, tagged Frontend; the S2-§16 aliases; Java ⇄ Core Java."""
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    rows = _sql(url, SKILLS)
    assert [(c, s) for c, skills in SOURCE.items() for s in skills] == [tuple(r) for r in rows]
    assert len(rows) == 37
    assert [r[0] for r in _sql(url, "SELECT name FROM skill_categories ORDER BY sort_order")] == list(SOURCE)
    assert [tuple(r) for r in _sql(url, TAGS)] == [("JavaScript", "Frontend")]
    assert [tuple(r) for r in _sql(url, ALIASES)] == sorted(
        [("Java", a) for a in ("Java 8", "Java 11", "Java 17", "Java 21", "J2EE", "J2SE")] + [("React", a) for a in ("React.js", "ReactJS", "React JS")]
    )
    assert sorted(_sql(url, RELATED)[0]) == ["Core Java", "Java"]


def test_seed_is_idempotent_and_keeps_a_managers_rename(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, "UPDATE skills SET active = false WHERE name = 'PHP'")
    _sql(url, "UPDATE skill_aliases SET alias = 'J2EE (legacy)' WHERE alias = 'J2EE'")
    for statement, params in _migration.seed_statements():
        _sql(url, statement, params)
    assert len(_sql(url, "SELECT 1 FROM skills")) == 37
    assert _sql(url, "SELECT active FROM skills WHERE name = 'PHP'")[0][0] is False
    assert len(_sql(url, "SELECT 1 FROM skill_aliases")) == 10  # the renamed alias is kept, and the source spelling comes back
    assert len(_sql(url, "SELECT 1 FROM skill_category_tags")) == 1 and len(_sql(url, "SELECT 1 FROM skill_related")) == 1


def test_round_trip_and_the_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert "skills" not in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    command.upgrade(cfg, HEAD)
    with pytest.raises(Exception, match="uq_skills_name"):
        _sql(url, "INSERT INTO skills (id, name, category_id) SELECT gen_random_uuid(), 'JAVA', category_id FROM skills LIMIT 1")
    with pytest.raises(Exception, match="uq_skill_aliases_alias"):
        _sql(url, "INSERT INTO skill_aliases (id, skill_id, alias) SELECT gen_random_uuid(), id, 'reactjs' FROM skills LIMIT 1")
    with pytest.raises(Exception, match="ck_skill_related_order"):
        _sql(url, "INSERT INTO skill_related (skill_a_id, skill_b_id) SELECT id, id FROM skills LIMIT 1")


@pytest.mark.parametrize(
    "change",
    [
        "INSERT INTO skill_categories (id, name, sort_order) VALUES (gen_random_uuid(), 'Testing', 9)",
        "UPDATE skills SET name = 'Golang' WHERE name = 'PHP'",
        "INSERT INTO skill_aliases (id, skill_id, alias) SELECT gen_random_uuid(), id, 'Py3' FROM skills WHERE name = 'Python'",
        "DELETE FROM skill_related",
    ],
)
def test_downgrade_refuses_while_manager_data_exists(isolated_db, change):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, change)
    with pytest.raises(Exception, match="manager data exists"):
        command.downgrade(cfg, BASE)
