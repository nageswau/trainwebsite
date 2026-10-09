"""rec-019 -- migration 0140_profile_shares (spec §2). Round trip and downgrade refusal run in a throwaway database built from scratch (the
rec-028 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_019_migration_0140", VERSIONS / "0140_profile_shares.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0139_recruiter_contracts", "0140_profile_shares"


def test_migration_chains_after_0139_and_there_is_a_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import PROFILE_SHARE_CHANNELS, PROFILE_SHARE_CHECKS, PROFILE_SHARE_ITEM_CHECKS, PROFILE_SHARE_RESPONSES, ProfileShare, ProfileShareItem

    assert _migration.CHANNELS == PROFILE_SHARE_CHANNELS and _migration.RESPONSES == PROFILE_SHARE_RESPONSES
    assert _migration.SHARE_CHECKS == PROFILE_SHARE_CHECKS and _migration.ITEM_CHECKS == PROFILE_SHARE_ITEM_CHECKS
    constraints = {c.name: c for t in (ProfileShare.__table__, ProfileShareItem.__table__) for c in t.constraints}
    for name, sql in {**_migration.SHARE_CHECKS, **_migration.ITEM_CHECKS}.items():
        assert str(constraints[name].sqltext) == sql
    assert "uq_profile_share_items_candidate" in constraints
    indexes = {i.name for t in (ProfileShare.__table__, ProfileShareItem.__table__) for i in t.indexes}
    assert {"ix_profile_shares_job", "ix_profile_shares_company", "ix_profile_share_items_candidate", "uq_profile_share_items_token"} <= indexes


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec019_migration_{uuid.uuid4().hex[:8]}"
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


def _setup(url) -> dict:
    ids = {k: uuid.uuid4() for k in ("company", "user", "job", "contact")}
    _sql(
        url,
        "INSERT INTO companies (id, name, partner_type, owner_type, created_at, updated_at) VALUES (:id, :n, 'recruiter', 'internal', now(), now())",
        {"id": ids["company"], "n": f"Co {ids['company'].hex[:6]}"},
    )
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": ids["user"], "e": f"{ids['user'].hex[:8]}@example.local"},
    )
    return ids


def _share(url, ids, channel: str = "other", columns: str = "", values: str = "", **params) -> uuid.UUID:
    row = uuid.uuid4()
    _sql(
        url,
        f"INSERT INTO profile_shares (id, job_id, company_id, channel, shared_by_user_id{columns}) "
        f"VALUES (:id, (SELECT id FROM jobs LIMIT 1), :c, :ch, :u{values})",
        {"id": row, "c": ids["company"], "ch": channel, "u": ids["user"], **params},
    )
    return row


def _job(url, ids) -> None:
    _sql(
        url,
        "INSERT INTO jobs (id, company_id, title, location, description, skills, status, created_at, updated_at) "
        "VALUES (:id, :c, 'Dev', 'Remote', '', '[]', 'sourcing', now(), now())",
        {"id": ids["job"], "c": ids["company"]},
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('profile_shares')") == [(None,)]
    command.upgrade(cfg, HEAD)
    ids = _setup(url)
    _job(url, ids)
    _share(url, ids)
    for name, channel in (("ck_profile_shares_channel", "fax"), ("ck_profile_shares_message", "email")):
        with pytest.raises(Exception, match=name):
            _share(url, ids, channel)
    with pytest.raises(Exception, match="ck_profile_shares_note"):
        _share(url, ids, "other", ", note", ", :note", note="x" * 501)
    _sql(url, "DELETE FROM profile_shares")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('profile_shares')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_shares_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    ids = _setup(url)
    _job(url, ids)
    _share(url, ids)
    with pytest.raises(Exception, match="shares exist"):
        command.downgrade(cfg, BASE)
