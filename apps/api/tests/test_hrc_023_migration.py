"""hrc-023 -- migration 0266_website_intake (DEC-SCOPE-389): the chain, the Q-25 link of existing career applications (W8) and the round
trip in a throwaway database (the hrc-022 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_hrc_023_migration_0266", VERSIONS / "0266_website_intake.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0266_website_intake", "0265_skill_taxonomy"
NEW_COLUMNS = {("candidates", "utm"), ("career_applications", "candidate_id"), ("career_applications", "utm"),
               ("career_applications", "consent_version"), ("career_applications", "consented_at")}  # fmt: skip


def test_migration_chains_after_0265():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc023_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[tuple[str, str]]:
    rows = _sql(url, "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'")
    return {(r[0], r[1]) for r in rows}


def _nullable(url, table: str, column: str) -> bool:
    return _sql(url, f"SELECT is_nullable FROM information_schema.columns WHERE table_name = '{table}' AND column_name = '{column}'")[0][0] == "YES"


def test_round_trip_links_existing_applications_by_email(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not NEW_COLUMNS & _columns(url)
    assert not _nullable(url, "candidates", "created_by_user_id") and not _nullable(url, "candidate_consents", "user_id")
    user, source, company, job, candidate = (uuid.uuid4() for _ in range(5))
    _sql(url, f"INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, profile, locale) "
              f"VALUES ('{user}', 'mig23-{user.hex[:6]}@x.local', '!', 'U', 'placement_manager', 'global', true, true, '{{}}', 'en')", autocommit=True)  # fmt: skip
    _sql(url, f"INSERT INTO rec_candidate_sources (id, name) VALUES ('{source}', 'Mig23 {source.hex[:6]}')", autocommit=True)
    _sql(url, f"INSERT INTO companies (id, name, owner_type, partner_type) VALUES ('{company}', 'Mig23 Co', 'internal', 'employer')", autocommit=True)
    _sql(url, f"INSERT INTO jobs (id, company_id, title, location, description, skills, status) VALUES ('{job}', '{company}', 'J', 'Pune', 'd', '[]', 'sourcing')", autocommit=True)
    _sql(url, f"INSERT INTO candidates (id, candidate_code, name, email, preferred_locations, source_id, created_by_user_id) "
              f"VALUES ('{candidate}', 'MIG23-{candidate.hex[:6]}', 'C', 'Known@Mig.local', '[]', '{source}', '{user}')", autocommit=True)  # fmt: skip
    for email, code in (("known@mig.local", "T1"), ("stranger@mig.local", "T2")):
        _sql(url, f"INSERT INTO career_applications (id, job_id, full_name, email, resume_url, status, tracking_code) "
                  f"VALUES ('{uuid.uuid4()}', '{job}', 'A', '{email}', '/r.pdf', 'submitted', 'MIG23-{code}-{job.hex[:6]}')", autocommit=True)  # fmt: skip

    command.upgrade(cfg, HEAD)
    assert NEW_COLUMNS <= _columns(url)
    assert _nullable(url, "candidates", "created_by_user_id") and _nullable(url, "candidate_consents", "user_id")
    linked = dict(_sql(url, f"SELECT email, candidate_id::text FROM career_applications WHERE job_id = '{job}'"))
    assert linked == {"known@mig.local": str(candidate), "stranger@mig.local": None}  # W8: linked, never created from history
    command.upgrade(cfg, HEAD)  # idempotent at head
    command.downgrade(cfg, BASE)
    assert not NEW_COLUMNS & _columns(url)
    assert not _nullable(url, "candidates", "created_by_user_id")
    command.upgrade(cfg, HEAD)
