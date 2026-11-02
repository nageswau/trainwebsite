"""itc-003 -- migration 0222_it_student_counselors (DEC-SCOPE-337). Round trip and the downgrade refusal run in a throwaway database
built from scratch (the csc-001 / upc-001 pattern); the backfill query is checked against the shared database inside a rolled-back
transaction. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import ItStudentCounselor
from tests.tel004_helpers import make_user
from tests.tel018_helpers import make_student, setup
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_003_migration_0222", VERSIONS / "0222_it_student_counselors.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0222_it_student_counselors"
BASE = _migration.down_revision
TABLE = "it_student_counselors"


def test_migration_is_the_single_head():
    assert _migration.revision == HEAD
    script = ScriptDirectory.from_config(_config())
    # itc-006's 0223 now follows this revision: still one head, and this revision is in its chain
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert ItStudentCounselor.__tablename__ == TABLE
    assert {c.name for c in ItStudentCounselor.__table__.columns} == {"id", "student_user_id", "counselor_user_id", "assigned_by_user_id", "created_at", "updated_at"}
    unique = {c.name: [col.name for col in c.columns] for c in ItStudentCounselor.__table__.constraints if c.name and c.name.startswith("uq_")}
    assert unique == {"uq_it_student_counselors_student": ["student_user_id"]}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert TABLE in await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.mark.asyncio
async def test_the_backfill_links_each_linked_it_lead_to_its_it_counselor_only(db_session):
    """An IT lead linked to a student and owned by an IT counselor -> one row; an overseas lead, an IT lead owned by someone who is not
    an IT counselor, and an unlinked lead -> none; a student who already has a link is left alone."""
    admin = await make_user(db_session, "it_admin", "it")
    _, _, counselor, it_lead = await setup(db_session, status="application_enrollment")
    _, _, ov_counselor, ov_lead = await setup(db_session, "overseas", status="application_enrollment")
    _, _, _, unlinked = await setup(db_session)
    _, _, _, admin_owned = await setup(db_session, status="application_enrollment")
    _, _, other, kept_lead = await setup(db_session, status="application_enrollment")
    it_student, ov_student, admin_student, kept_student = (await make_student(db_session), await make_student(db_session, "overseas"),
                                                           await make_student(db_session), await make_student(db_session))  # fmt: skip
    now = await db_session.scalar(select(text("now()")))
    for lead, owner, student in ((it_lead, counselor, it_student), (ov_lead, ov_counselor, ov_student), (admin_owned, admin, admin_student), (kept_lead, other, kept_student)):
        lead.owner_id, lead.converted_user_id, lead.converted_by_user_id, lead.converted_at = owner.id, student.id, admin.id, now
    unlinked.owner_id = counselor.id
    db_session.add(ItStudentCounselor(student_user_id=kept_student.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id))
    await db_session.flush()
    await db_session.execute(text(_migration.BACKFILL))
    rows = dict((await db_session.execute(select(ItStudentCounselor.student_user_id, ItStudentCounselor.counselor_user_id).where(
        ItStudentCounselor.student_user_id.in_([it_student.id, ov_student.id, admin_student.id, kept_student.id])))).all())  # fmt: skip
    assert rows == {it_student.id: counselor.id, kept_student.id: counselor.id}
    assigned_by = await db_session.scalar(select(ItStudentCounselor.assigned_by_user_id).where(ItStudentCounselor.student_user_id == it_student.id))
    assert assigned_by == admin.id
    await db_session.rollback()


@pytest.fixture
def isolated_db():
    """A fresh database at the revision before 0222."""
    cfg = _config()
    original = settings.database_url
    name = f"itc003_migration_{uuid.uuid4().hex[:8]}"
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


def _tables(url: str) -> set[str]:
    return {row[0] for row in _sql(url, "SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}


def test_round_trip_creates_and_drops_the_table(isolated_db):
    assert TABLE not in _tables(isolated_db["url"])
    command.upgrade(isolated_db["cfg"], HEAD)
    assert TABLE in _tables(isolated_db["url"])
    indexes = {row[0] for row in _sql(isolated_db["url"], f"SELECT indexname FROM pg_indexes WHERE tablename = '{TABLE}'")}
    assert {"ix_it_student_counselors_counselor_user_id", "uq_it_student_counselors_student"} <= indexes
    command.downgrade(isolated_db["cfg"], BASE)
    assert TABLE not in _tables(isolated_db["url"])


def test_downgrade_refuses_while_links_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    student, counselor = uuid.uuid4(), uuid.uuid4()
    for user_id, role in ((student, "it_student"), (counselor, "counselor")):
        _sql(
            url,
            "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
            "VALUES (:id, :email, 'x', 'Itc User', :role, 'it', '{}', true, true, 'en-GB')",
            {"id": user_id, "email": f"{user_id.hex[:8]}@example.com", "role": role},
        )
    _sql(url, f"INSERT INTO {TABLE} (id, student_user_id, counselor_user_id, assigned_by_user_id) VALUES (gen_random_uuid(), :s, :c, :c)", {"s": student, "c": counselor})
    with pytest.raises(Exception, match="IT student-counselor links exist"):
        command.downgrade(cfg, BASE)
    assert TABLE in _tables(url)
