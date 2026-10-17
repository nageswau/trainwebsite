"""AGN-024 -- migration 0164_agent_org_kyc (DEC-SCOPE-224). Round trip and the downgrade refusal run in a throwaway database built from
scratch (the upc-001 pattern); a downgrade never runs against the shared test database. Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_agn_024_migration_0164", VERSIONS / "0164_agent_org_kyc.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0163_monthly_reviews", "0164_agent_org_kyc"


def test_migration_chains_after_0163_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    from app.models import KYC_CHECKS, AgentOrg, AgentOrgKycDocument

    assert KYC_CHECKS == _migration.CHECKS
    assert {c.name for c in AgentOrgKycDocument.__table__.columns} == {
        "id", "org_id", "doc_type", "doc_number", "file_key", "original_filename", "content_type", "file_size", "status",
        "rejection_reason", "reviewed_by_user_id", "reviewed_at", "uploaded_by_user_id", "created_at", "updated_at",
    }  # fmt: skip
    assert "kyc_required" in {c.name for c in AgentOrg.__table__.columns}


@pytest.mark.asyncio
async def test_table_exists_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert "agent_org_kyc_documents" in await conn.run_sync(lambda sync: set(inspect(sync).get_table_names()))


@pytest.fixture
def isolated_db():
    """A fresh database at 0163_monthly_reviews."""
    cfg = _config()
    original = settings.database_url
    name = f"agn024_migration_{uuid.uuid4().hex[:8]}"
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


def test_upgrade_round_trips_checks_hold_and_downgrade_refuses_while_kyc_documents_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'agent_org_kyc_documents'")
    assert not _sql(url, "SELECT 1 FROM information_schema.columns WHERE table_name = 'agent_orgs' AND column_name = 'kyc_required'")
    command.upgrade(cfg, HEAD)
    org_id, user_id = uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
        "VALUES (:id, 'kyc@example.com', 'x', 'Kyc User', 'agent', 'agent', '{}', true, true, 'en-GB')",
        {"id": user_id},
    )
    _sql(url, "INSERT INTO agent_orgs (id, name, prefix, status, master_seq, staff_seq) VALUES (:id, 'Org', 'KYC', 'pending', 0, 0)", {"id": org_id})
    assert _sql(url, "SELECT kyc_required FROM agent_orgs")[0][0] is False
    insert = (
        "INSERT INTO agent_org_kyc_documents (id, org_id, doc_type, doc_number, file_key, content_type, file_size, status, "
        "rejection_reason, uploaded_by_user_id) VALUES (gen_random_uuid(), :org, :doc_type, 'ABCDE1234F', 'agent-kyc/x', 'image/png', 10, "
        ":status, :reason, :user)"
    )
    base = {"org": org_id, "user": user_id}
    with pytest.raises(Exception, match="ck_agent_org_kyc_documents_type"):
        _sql(url, insert, {**base, "doc_type": "passport", "status": "pending", "reason": None})
    with pytest.raises(Exception, match="ck_agent_org_kyc_documents_status"):
        _sql(url, insert, {**base, "doc_type": "pan", "status": "done", "reason": None})
    with pytest.raises(Exception, match="ck_agent_org_kyc_documents_reason"):
        _sql(url, insert, {**base, "doc_type": "pan", "status": "rejected", "reason": None})
    with pytest.raises(Exception, match="ck_agent_org_kyc_documents_reason"):
        _sql(url, insert, {**base, "doc_type": "pan", "status": "pending", "reason": "no"})
    _sql(url, insert, {**base, "doc_type": "pan", "status": "pending", "reason": None})
    with pytest.raises(Exception, match="uq_agent_org_kyc_documents_org_type"):
        _sql(url, insert, {**base, "doc_type": "pan", "status": "pending", "reason": None})
    with pytest.raises(Exception, match="KYC documents exist"):
        command.downgrade(cfg, BASE)
