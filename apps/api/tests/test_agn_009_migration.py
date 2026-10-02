"""AGN-009 -- migration 0058_agent_documents (spec §3). Round trip and downgrade refusals run in a throwaway database built from
scratch (the AGN-008 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls
asyncio.run() itself."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_agn_009_migration_0058", VERSIONS / "0058_agent_documents.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0057_agent_applications"
HEAD = "0058_agent_documents"
DOC_COLUMNS = "SELECT id, student_id, application_id, document_type, file_url, verification_status FROM student_documents ORDER BY id"
NEW_DOC_COLUMNS = ("agent_student_id", "document_label", "uploaded_by_user_id", "fulfils_request_id")


def test_migration_chains_after_0057_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


def test_models_declare_the_new_shape():
    from app.models import DocumentEvent, DocumentRequest, StudentDocument

    columns = StudentDocument.__table__.columns
    assert columns["student_id"].nullable
    for name in NEW_DOC_COLUMNS:
        assert name in columns and columns[name].nullable, name
    assert any(getattr(c, "name", None) == _migration.FULFILS_UNIQUE for c in StudentDocument.__table__.constraints)
    assert {"agent_student_id", "document_type", "document_label", "note", "status", "requested_by_user_id", "closed_at"} <= set(DocumentRequest.__table__.columns.keys())
    assert {"seq", "document_id", "request_id", "event", "actor_user_id", "from_status", "to_status", "notes", "file_key", "created_at"} <= set(DocumentEvent.__table__.columns.keys())


@pytest.mark.asyncio
async def test_shared_database_has_the_new_objects(db_session):
    conn = await db_session.connection()
    cols = await conn.run_sync(lambda sync: {c["name"]: c for c in inspect(sync).get_columns("student_documents")})
    tables = await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    checks = await conn.run_sync(lambda sync: {c["name"] for c in inspect(sync).get_check_constraints("student_documents")})
    assert cols["student_id"]["nullable"]
    for name in NEW_DOC_COLUMNS:
        assert name in cols, name
    assert {"document_requests", "document_events"} <= tables
    assert _migration.OWNER_CHECK in checks


@pytest.mark.asyncio
async def test_a_document_needs_an_owner(db_session):
    from app.models import StudentDocument

    db_session.add(StudentDocument(student_id=None, agent_student_id=None, document_type="Passport", file_url="agent-documents/x", verification_status="pending"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


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
    """A fresh database at 0057 with one student document (a student with an account) and one agency student with no login."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"agn009_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        ids = {k: uuid.uuid4() for k in ("agent", "student", "record", "document")}
        for key, role in (("agent", "agent"), ("student", "overseas_student")):
            _sql(
                url,
                "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                "VALUES (:id, :email, 'x', :name, :role, 'overseas', true, true, 'en-GB', '{}')",
                {"id": ids[key], "email": f"{key}-{name}@example.local", "name": f"{key} user", "role": role},
            )
        _sql(url, "INSERT INTO agent_students (id, agent_id, student_id, status, full_name) VALUES (:id, :agent, NULL, 'active', 'No Login')", {"id": ids["record"], "agent": ids["agent"]})
        _sql(
            url,
            "INSERT INTO student_documents (id, student_id, document_type, file_url, verification_status) VALUES (:id, :student, 'Passport', 'uploads/p.pdf', 'verified')",
            {"id": ids["document"], "student": ids["student"]},
        )
        yield {"cfg": cfg, "url": url, "ids": ids}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_existing_rows_identical(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, DOC_COLUMNS)
    command.upgrade(cfg, HEAD)
    assert _sql(url, DOC_COLUMNS) == before
    assert _sql(url, "SELECT agent_student_id, document_label, uploaded_by_user_id, fulfils_request_id FROM student_documents") == [(None, None, None, None)]
    command.downgrade(cfg, BASE)
    assert _sql(url, DOC_COLUMNS) == before
    command.upgrade(cfg, HEAD)
    assert _sql(url, DOC_COLUMNS) == before


@pytest.mark.parametrize(
    ("setup_sql", "message"),
    [
        (
            "INSERT INTO student_documents (id, agent_student_id, document_type, file_url, verification_status) VALUES (gen_random_uuid(), :record, 'CV', 'agent-documents/x', 'pending')",
            "agency documents exist",
        ),
        (
            "INSERT INTO document_requests (id, agent_student_id, document_type, status, created_at, updated_at) VALUES (gen_random_uuid(), :record, 'CV', 'open', now(), now())",
            "document requests exist",
        ),
        ("INSERT INTO document_events (id, document_id, event) VALUES (gen_random_uuid(), :document, 'downloaded')", "document history exists"),
    ],
)
def test_downgrade_refuses_to_lose_agn009_data(isolated_db, setup_sql, message):
    cfg, url, ids = isolated_db["cfg"], isolated_db["url"], isolated_db["ids"]
    command.upgrade(cfg, HEAD)
    _sql(url, setup_sql, {"record": ids["record"], "document": ids["document"]})
    with pytest.raises(RuntimeError, match=message):
        command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT version_num FROM alembic_version") == [(HEAD,)]
