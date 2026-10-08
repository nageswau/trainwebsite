"""upc-006 -- migration 0108_university_contacts (spec §2). Round trip, the role seed and the downgrade refusal run in a throwaway
database built from scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests:
alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_upc_006_migration_0108", VERSIONS / "0108_university_contacts.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0107_candidates", "0108_university_contacts"
ROLES = [
    "International Director",
    "International Recruitment Manager",
    "Regional Manager",
    "Admissions Manager",
    "Marketing Manager",
    "Application Officer",
    "Finance Contact",
    "International Office",
    "Partnership Contact",
    "Recruitment Contact",
    "Application Contact",
    "Country Manager",
]


def test_migration_chains_after_0107_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import UNIVERSITY_CONTACT_CHECKS, UNIVERSITY_CONTACT_ROLE_SEED, UNIVERSITY_RELATIONSHIP_CHECK, University, UniversityContact, UniversityContactRole

    assert "relationship_strength" in {c.name for c in University.__table__.columns}
    assert UNIVERSITY_RELATIONSHIP_CHECK == _migration.UNIVERSITY_CHECK
    assert UNIVERSITY_CONTACT_CHECKS == _migration.CONTACT_CHECKS
    assert UNIVERSITY_CONTACT_ROLE_SEED == _migration.ROLE_SEED
    assert [label for _, label in UNIVERSITY_CONTACT_ROLE_SEED] == ROLES
    assert {c.name for c in UniversityContactRole.__table__.columns} == {"code", "label", "position"}
    assert {c.name for c in UniversityContact.__table__.columns} == {
        "id", "university_id", "name", "designation", "department", "role_code", "email", "phone", "whatsapp", "linkedin",
        "preferred_channel", "relationship_strength", "notes", "is_primary", "shareable", "created_at", "updated_at",
    }  # fmt: skip


@pytest.mark.asyncio
async def test_tables_indexes_and_seed_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    columns, indexes = await conn.run_sync(lambda sync: ({c["name"] for c in inspect(sync).get_columns("universities")}, {i["name"] for i in inspect(sync).get_indexes("university_contacts")}))
    assert "relationship_strength" in columns
    assert {"ix_university_contacts_university", "uq_university_contacts_primary", "uq_university_contacts_email"} <= indexes
    from sqlalchemy import select

    from app.models import UniversityContactRole

    assert [r.label for r in (await db_session.scalars(select(UniversityContactRole).order_by(UniversityContactRole.position))).all()] == ROLES


@pytest.fixture
def isolated_db():
    """A fresh database at 0107."""
    cfg = _config()
    original = settings.database_url
    name = f"upc006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")  # 0001's create_all builds today's models; head-then-down gives BASE its real shape
        command.downgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_upgrade_seeds_roles_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    assert [r[0] for r in _sql(url, "SELECT label FROM university_contact_roles ORDER BY position")] == ROLES
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'university_contacts'")
    command.upgrade(cfg, HEAD)
    assert len(_sql(url, "SELECT code FROM university_contact_roles")) == len(ROLES)


def test_constraints_hold_and_downgrade_refuses_while_contacts_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    country = _sql(url, "SELECT id FROM countries WHERE iso2 = 'GB'")[0][0]
    uni = _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (gen_random_uuid(), :c, 'abc', 'ABC', 'London', '', '', '[]', '[]', '[]') RETURNING id",
        {"c": country},
    )[0][0]
    with pytest.raises(Exception, match="ck_universities_relationship_strength"):
        _sql(url, "UPDATE universities SET relationship_strength = 'great'")
    insert = "INSERT INTO university_contacts (id, university_id, name, is_primary, email) VALUES (gen_random_uuid(), :u, :n, :p, :e)"
    _sql(url, insert, {"u": uni, "n": "A", "p": True, "e": "a@abc.ac.uk"})
    with pytest.raises(Exception, match="uq_university_contacts_primary"):
        _sql(url, insert, {"u": uni, "n": "B", "p": True, "e": None})
    with pytest.raises(Exception, match="uq_university_contacts_email"):
        _sql(url, insert, {"u": uni, "n": "C", "p": False, "e": "A@ABC.ac.uk"})
    with pytest.raises(Exception, match="ck_university_contacts_preferred_channel"):
        _sql(url, "UPDATE university_contacts SET preferred_channel = 'fax'")
    with pytest.raises(Exception, match="contacts or relationship strengths exist"):
        command.downgrade(cfg, BASE)
