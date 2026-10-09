"""upc-026 -- migration 0123_university_documents (spec §2). Round trip, constraints and the downgrade refusal run in a throwaway database
built from scratch (the rec-008 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_upc_026_migration_0123", VERSIONS / "0123_university_documents.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0122_candidate_skills", "0123_university_documents"
DOCUMENT_COLUMNS = {"id", "university_id", "kind", "title", "shareable", "current_version", "created_by_user_id", "created_at", "updated_at"}
VERSION_COLUMNS = {"id", "document_id", "version", "storage_key", "file_name", "content_type", "size_bytes", "uploaded_by_user_id", "uploaded_at"}


def test_migration_chains_after_0122_and_there_is_a_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import UNIVERSITY_DOCUMENT_CHECKS, UNIVERSITY_DOCUMENT_KINDS, UNIVERSITY_DOCUMENT_VERSION_CHECKS, UniversityDocument, UniversityDocumentVersion

    assert _migration.KINDS == UNIVERSITY_DOCUMENT_KINDS and len(UNIVERSITY_DOCUMENT_KINDS) == 12
    assert _migration.DOCUMENT_CHECKS == UNIVERSITY_DOCUMENT_CHECKS
    assert _migration.VERSION_CHECKS == UNIVERSITY_DOCUMENT_VERSION_CHECKS
    documents, versions = UniversityDocument.__table__, UniversityDocumentVersion.__table__
    assert {c.name for c in documents.columns} == DOCUMENT_COLUMNS
    assert {c.name for c in versions.columns} == VERSION_COLUMNS
    names = {i.name for t in (documents, versions) for i in t.indexes} | {c.name for t in (documents, versions) for c in t.constraints}
    expected = {"uq_university_documents_title", "ix_university_documents_updated", "uq_university_document_versions_version", "uq_university_document_versions_key"}
    assert set(UNIVERSITY_DOCUMENT_CHECKS) | set(UNIVERSITY_DOCUMENT_VERSION_CHECKS) | expected <= names
    for table, checks in ((documents, UNIVERSITY_DOCUMENT_CHECKS), (versions, UNIVERSITY_DOCUMENT_VERSION_CHECKS)):
        for name, sql in checks.items():
            assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc026_migration_{uuid.uuid4().hex[:8]}"
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


def _setup(url) -> tuple[uuid.UUID, uuid.UUID]:
    user_id, uni_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'H', 'partnership_head', 'global', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"},
    )
    country_id = _sql(url, "SELECT id FROM countries LIMIT 1")[0][0]  # upc-002's migration seeds the ISO list
    _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships, "
        "created_at, updated_at) VALUES (:id, :c, :s, 'U', :k, 'X', '', '', '[]', '[]', '[]', now(), now())",
        {"id": uni_id, "c": country_id, "s": f"u-{uni_id.hex[:8]}", "k": f"u {uni_id.hex[:8]}"},
    )
    return uni_id, user_id


def _document(url, uni_id, user_id, **over) -> uuid.UUID:
    values = {"id": uuid.uuid4(), "u": uni_id, "by": user_id, "kind": "fee_structure", "title": "Fees 2026", "share": True, "cur": 1} | over
    _sql(
        url,
        "INSERT INTO university_documents (id, university_id, kind, title, shareable, current_version, created_by_user_id, created_at, updated_at) "
        "VALUES (:id, :u, :kind, :title, :share, :cur, :by, now(), now())",
        values,
    )
    return values["id"]


def _version(url, document_id, user_id, **over):
    values = {"id": uuid.uuid4(), "d": document_id, "by": user_id, "v": 1, "k": f"university-documents/{uuid.uuid4().hex}", "size": 10} | over
    _sql(
        url,
        "INSERT INTO university_document_versions (id, document_id, version, storage_key, file_name, content_type, size_bytes, uploaded_by_user_id, uploaded_at) "
        "VALUES (:id, :d, :v, :k, 'fees.pdf', 'application/pdf', :size, :by, now())",
        values,
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('university_documents')") == [(None,)]
    command.upgrade(cfg, HEAD)
    uni_id, user_id = _setup(url)
    doc = _document(url, uni_id, user_id)
    _version(url, doc, user_id)
    with pytest.raises(Exception, match="uq_university_documents_title"):
        _document(url, uni_id, user_id, title="FEES 2026")
    with pytest.raises(Exception, match="ck_university_documents_kind"):
        _document(url, uni_id, user_id, kind="invoice", title="Other")
    with pytest.raises(Exception, match="ck_university_documents_commission_internal"):
        _document(url, uni_id, user_id, kind="commission_agreement", title="Commission")
    with pytest.raises(Exception, match="uq_university_document_versions_version"):
        _version(url, doc, user_id)
    with pytest.raises(Exception, match="ck_university_document_versions_size"):
        _version(url, doc, user_id, v=2, size=0)
    _sql(url, "DELETE FROM university_document_versions")
    _sql(url, "DELETE FROM university_documents")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('university_documents')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_documents_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _document(url, *_setup(url))
    with pytest.raises(Exception, match="university documents exist"):
        command.downgrade(cfg, BASE)
