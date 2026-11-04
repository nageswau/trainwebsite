"""hrc-035 -- migration 0273_candidate_privacy (DEC-SCOPE-396 K1/K3/K7/K8). The round trip runs in a throwaway database built from scratch
(the rec-006 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_hrc_017_migration import _config, _sql

API_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("_hrc_035_migration_0273", API_ROOT / "alembic" / "versions" / "0273_candidate_privacy.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0269_match_engine", "0273_candidate_privacy"


def test_migration_chains_after_the_match_engine_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_and_rbac_match_the_migration():
    from app.core import rbac
    from app.models import CANDIDATE_CONSENT_BASIS_CHECKS, CANDIDATE_PRIVACY_CHECKS, CANDIDATE_RETENTION_CHECKS

    assert CANDIDATE_CONSENT_BASIS_CHECKS == _migration.CONSENT_CHECKS
    assert CANDIDATE_PRIVACY_CHECKS == _migration.CANDIDATE_CHECKS
    assert CANDIDATE_RETENTION_CHECKS == _migration.RETENTION_CHECKS
    for role, resource, action in _migration.SEED:
        assert f"{resource}.{action}" in rbac.DEFAULT_GRANTS[role]


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"hrc035_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_backfills_consent_sources_and_seeds_the_hr_manager(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)  # 0001 builds from the current models: go down to BASE so the columns are really added (and backfilled)
    command.downgrade(cfg, BASE)
    source = _sql(url, "SELECT id FROM rec_candidate_sources LIMIT 1")
    if not source:
        _sql(url, "INSERT INTO rec_candidate_sources (id, name, is_active) VALUES (gen_random_uuid(), 'Referral', true)")
        source = _sql(url, "SELECT id FROM rec_candidate_sources LIMIT 1")
    student, cand_user = str(uuid.uuid4()), str(uuid.uuid4())
    for uid, role in ((student, "it_student"), (cand_user, "candidate")):
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
                  f"VALUES ('{uid}', '{uid}@x.local', '!', 'U', '{role}', 'it', true, true, 'en', '{{}}')")  # fmt: skip
    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, (cid, uid) in enumerate(zip(ids, (student, cand_user, None), strict=True)):
        user = f"'{uid}'" if uid else "NULL"
        _sql(url, "INSERT INTO candidates (id, candidate_code, name, email, source_id, preferred_locations, user_id, opted_in) "
                  f"VALUES ('{cid}', 'CAN-M35{i}', 'N', '{cid}@x.local', '{source[0][0]}', '[]', {user}, true)")  # fmt: skip
        _sql(url, f"INSERT INTO candidate_consents (id, candidate_id, user_id, action, consent_version) VALUES (gen_random_uuid(), '{cid}', {user}, 'opt_in', 'v1')")
    command.upgrade(cfg, HEAD)
    rows = dict(_sql(url, "SELECT candidate_id::text, source || '/' || lawful_basis FROM candidate_consents"))
    assert [rows[c] for c in ids] == ["student/consent", "portal/consent", "website/consent"]
    assert _sql(url, "SELECT 1 FROM role_permissions WHERE role = 'hr_manager' AND resource = 'candidates' AND action = 'erase'") == [(1,)]
    with pytest.raises(Exception, match="ck_candidate_retention_settings_months"):
        _sql(url, "INSERT INTO candidate_retention_settings (id, months) VALUES (1, 3)")
    with pytest.raises(Exception, match="ck_candidates_anonymised"):
        _sql(url, f"UPDATE candidates SET anonymised_at = now() WHERE id = '{ids[2]}'")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name = 'candidate_retention_settings'") == []
    columns = {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'candidate_consents'")}
    assert columns.isdisjoint({"source", "lawful_basis"})
    assert _sql(url, "SELECT 1 FROM role_permissions WHERE role = 'hr_manager' AND resource = 'candidates' AND action = 'erase'") == []
    command.upgrade(cfg, HEAD)
