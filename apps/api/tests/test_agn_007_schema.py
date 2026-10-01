"""AGN-007 -- models, migration 0056_agent_shortlist and request schemas (spec §4, §5.3; AC03 DB-level, Review Focus 5)."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings
from app.models import AgentStudentShortlistEntry, AgentUniversity
from app.schemas import AgentUniversityCreate, AgentUniversityUpdate, ShortlistEntryCreate
from tests.agn001_helpers import mk_active_org
from tests.agn004_helpers import mk_record
from tests.agn007_helpers import mk_catalogue

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_007_migration", VERSIONS / "0056_agent_shortlist.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)


def test_migration_is_the_single_head():
    assert _migration.revision == "0056_agent_shortlist"
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert set(parents) - set(parents.values()) == {"0056_agent_shortlist"}


@pytest.mark.asyncio
async def test_tables_constraints_and_indexes_exist(db_session):
    conn = await db_session.connection()

    def _read(sync):
        i = inspect(sync)
        return (
            {c["name"] for c in i.get_check_constraints("agent_student_shortlist_entries")},
            {x["name"] for x in i.get_indexes("agent_student_shortlist_entries")} | {x["name"] for x in i.get_indexes("agent_universities")},
        )

    checks, indexes = await conn.run_sync(_read)
    assert {"ck_shortlist_one_university", "ck_shortlist_catalogue_course", "ck_shortlist_one_course_form"} <= checks
    assert {"ix_shortlist_student_created", "uq_agent_universities_org_name_country", "ix_agent_universities_org_id"} <= indexes


async def _student(db):
    ctx = await mk_active_org(db, name="Schema Agency")
    return ctx, await mk_record(db, agent=ctx["master"], full_name="Schema Student")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["both_universities", "no_university", "catalogue_course_with_agency", "both_course_forms"])
async def test_check_constraints_reject_invalid_rows(db_session, bad):  # AGN-007-AC03 (database level)
    ctx, student = await _student(db_session)
    cat = await mk_catalogue(db_session)
    agency_uni = AgentUniversity(org_id=ctx["org"].id, name=f"U {uuid.uuid4().hex[:6]}", country="Ireland")
    db_session.add(agency_uni)
    await db_session.commit()
    values = {
        "both_universities": {"university_id": cat["university"].id, "agent_university_id": agency_uni.id},
        "no_university": {},
        "catalogue_course_with_agency": {"agent_university_id": agency_uni.id, "course_id": cat["course"].id},
        "both_course_forms": {"university_id": cat["university"].id, "course_id": cat["course"].id, "course_title": "Typed"},
    }[bad]
    db_session.add(AgentStudentShortlistEntry(agent_student_id=student.id, **values))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_agency_university_name_and_country_are_unique_per_agency_case_insensitive(db_session):
    ctx = await mk_active_org(db_session, name="Unique Agency")
    other = await mk_active_org(db_session, name="Unique Other")
    db_session.add_all([AgentUniversity(org_id=ctx["org"].id, name="Trinity", country="Ireland"), AgentUniversity(org_id=other["org"].id, name="Trinity", country="Ireland")])
    await db_session.commit()
    db_session.add(AgentUniversity(org_id=ctx["org"].id, name="TRINITY", country="ireland"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_text_is_cleaned_and_controls_rejected():  # Review Focus 5
    assert AgentUniversityCreate(name="  Trinity  ", country="Ireland", city="   ").model_dump() == {"name": "Trinity", "country": "Ireland", "city": None, "entry_requirements": None}
    for bad in ({"name": "   ", "country": "Ireland"}, {"name": "A\x00B", "country": "Ireland"}, {"name": "x" * 201, "country": "Ireland"}):
        with pytest.raises(ValidationError):
            AgentUniversityCreate(**bad)
    with pytest.raises(ValidationError):
        ShortlistEntryCreate(entry_requirements="y" * 2001)
    with pytest.raises(ValidationError):
        ShortlistEntryCreate(org_id=str(uuid.uuid4()))  # mass assignment (extra="forbid")


def test_university_update_cannot_clear_name_or_country():
    assert AgentUniversityUpdate(city=None).model_dump(exclude_unset=True) == {"city": None}
    for bad in ({"name": None}, {"country": "  "}):
        with pytest.raises(ValidationError):
            AgentUniversityUpdate(**bad)


API_ROOT = Path(__file__).resolve().parents[1]
BASE = _migration.down_revision
NEW_TABLES = {"agent_universities", "agent_student_shortlist_entries"}


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


def _tables(url: str) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_round_trip_keeps_existing_rows_and_drops_only_new_tables():
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn007_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)  # 0001/0003 create_all from the CURRENT models, so the new tables may already exist here
        before = _sql(url, "SELECT count(*) FROM agent_students")
        command.upgrade(cfg, "0056_agent_shortlist")
        assert NEW_TABLES <= _tables(url)
        assert _sql(url, "SELECT count(*) FROM agent_students") == before
        command.downgrade(cfg, BASE)
        assert not NEW_TABLES & _tables(url)
        assert _sql(url, "SELECT count(*) FROM agent_students") == before
        command.upgrade(cfg, "0056_agent_shortlist")
        assert NEW_TABLES <= _tables(url)
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)
