"""rec-026 -- migration 0120_recruiter_messages (spec §2). The round trip, the seed and the downgrade refusal run in a throwaway database
built from scratch (the rec-024 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_rec_026_migration_0120", VERSIONS / "0120_recruiter_messages.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0117_job_descriptions", "0120_recruiter_messages"
MESSAGE_COLUMNS = {
    "id",
    "company_id",
    "contact_id",
    "candidate_id",
    "sender_user_id",
    "channel",
    "template_id",
    "template_name",
    "subject",
    "body",
    "delivery_status",
    "attempt_count",
    "sent_at",
    "created_at",
    "updated_at",
}


def test_migration_chains_after_its_base_and_there_is_a_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import REC_EMAIL_KINDS, REC_WHATSAPP_KINDS, RECRUITER_MESSAGE_CHECKS, RECRUITER_TEMPLATE_CHECKS, RecruiterMessage, RecruiterMessageTemplate

    assert (_migration.WHATSAPP_KINDS, _migration.EMAIL_KINDS) == (REC_WHATSAPP_KINDS, REC_EMAIL_KINDS)
    assert _migration.TEMPLATE_CHECKS == RECRUITER_TEMPLATE_CHECKS and _migration.MESSAGE_CHECKS == RECRUITER_MESSAGE_CHECKS
    assert {c.name for c in RecruiterMessage.__table__.columns} == MESSAGE_COLUMNS
    for model, checks in ((RecruiterMessageTemplate, RECRUITER_TEMPLATE_CHECKS), (RecruiterMessage, RECRUITER_MESSAGE_CHECKS)):
        table = model.__table__
        for name, sql in checks.items():
            assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    names = {i.name for i in RecruiterMessage.__table__.indexes}
    assert set(_migration.MESSAGE_INDEXES) <= names


def test_the_seed_is_one_template_per_source_kind_with_valid_placeholders():
    """AC1: 5 WhatsApp + 7 email kinds, each seeded once, each using the placeholders."""
    from app.services.recruiter_messages import check_placeholders

    seeds = _migration.SEED
    assert [(s["channel"], s["kind"]) for s in seeds] == [("whatsapp", k) for k in _migration.WHATSAPP_KINDS] + [("email", k) for k in _migration.EMAIL_KINDS]
    for seed in seeds:
        assert check_placeholders(seed["subject"], seed["body"])  # at least one placeholder, all known
        assert (seed["subject"] is not None) == (seed["channel"] == "email")


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"rec026_migration_{uuid.uuid4().hex[:8]}"
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


def _exists(url, table: str) -> bool:
    return _sql(url, f"SELECT to_regclass('{table}')") != [(None,)]


def _count(url) -> int:
    return _sql(url, "SELECT count(*) FROM recruiter_message_templates")[0][0]


def test_round_trip_seeds_once_and_checks_the_party(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not _exists(url, "recruiter_messages") and not _exists(url, "recruiter_message_templates")
    command.upgrade(cfg, HEAD)
    assert _count(url) == 12
    for statement, params in _migration.seed_statements():  # the seed is idempotent
        _sql(url, statement, params)
    assert _count(url) == 12
    user_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :e, 'x', 'R', 'placement_team', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "e": f"{user_id.hex[:8]}@example.local"},
    )
    with pytest.raises(Exception, match="ck_recruiter_messages_party"):  # neither a contact nor a candidate
        _sql(
            url,
            "INSERT INTO recruiter_messages (id, sender_user_id, channel, body, attempt_count, sent_at, created_at, updated_at) VALUES (:id, :u, 'whatsapp', 'Hi', 0, now(), now(), now())",
            {"id": uuid.uuid4(), "u": user_id},
        )
    command.downgrade(cfg, BASE)
    assert not _exists(url, "recruiter_messages") and not _exists(url, "recruiter_message_templates")


def test_downgrade_refuses_while_a_template_was_edited(isolated_db):
    command.upgrade(isolated_db["cfg"], HEAD)
    _sql(isolated_db["url"], "UPDATE recruiter_message_templates SET body = body || ' edited' WHERE kind = 'follow_up'")
    with pytest.raises(RuntimeError, match="0120_recruiter_messages"):
        command.downgrade(isolated_db["cfg"], BASE)
