"""ccrm-037 -- migration 0191_student_messages (DEC-SCOPE-273). The round trip and the downgrade refusal run in a throwaway database built
from scratch (the upc-012 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_037_migration_0191", VERSIONS / "0191_student_messages.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0190_overdue_escalation", "0191_student_messages"
TABLES = ("counselor_message_templates", "student_messages")


def test_migration_chains_after_0190_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import COUNSELOR_TEMPLATE_CHECKS, STUDENT_MESSAGE_CHECKS, CounselorMessageTemplate, StudentMessage

    for model, checks, migrated in ((CounselorMessageTemplate, COUNSELOR_TEMPLATE_CHECKS, _migration.TEMPLATE_CHECKS), (StudentMessage, STUDENT_MESSAGE_CHECKS, _migration.MESSAGE_CHECKS)):
        assert checks == migrated
        for name, sql in checks.items():
            assert str(next(c for c in model.__table__.constraints if c.name == name).sqltext) == sql
    assert set(_migration.INDEXES) <= {i.name for i in StudentMessage.__table__.indexes}
    assert {c.name for c in StudentMessage.__table__.columns} == {
        "id", "student_user_id", "application_id", "sender_user_id", "direction", "channel", "template_id", "template_name", "subject", "body",
        "delivery_status", "attempt_count", "sent_at", "created_at", "updated_at",
    }  # fmt: skip


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm037_migration_{uuid.uuid4().hex[:8]}"
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


def _user(url, role: str) -> uuid.UUID:
    user_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, profile, active, email_verified, locale) "
        "VALUES (:id, :email, 'x', 'Ccrm User', :role, 'overseas', '{}', true, true, 'en-GB')",
        {"id": user_id, "email": f"{user_id.hex[:8]}@example.com", "role": role},
    )
    return user_id


def test_round_trip_checks_and_the_downgrade_refuses_while_history_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert not any(_exists(url, t) for t in TABLES)
    command.upgrade(cfg, HEAD)
    assert all(_exists(url, t) for t in TABLES)
    with pytest.raises(Exception, match="ck_counselor_message_templates_subject"):  # a WhatsApp template has no subject
        _sql(url, "INSERT INTO counselor_message_templates (id, channel, name, subject, body) VALUES (:id, 'whatsapp', 'W', 'S', 'Hi')", {"id": uuid.uuid4()})
    student, counselor = _user(url, "overseas_student"), _user(url, "counselor")
    insert = "INSERT INTO student_messages (id, student_user_id, sender_user_id, direction, channel, subject, body, delivery_status, sent_at) VALUES (:id, :s, :c, :d, :ch, :subj, 'Hi', :st, now())"
    row = {"s": student, "c": counselor}
    with pytest.raises(Exception, match="ck_student_messages_outbound_email"):  # an outbound email needs its delivery status
        _sql(url, insert, {**row, "id": uuid.uuid4(), "d": "outbound", "ch": "email", "subj": "S", "st": None})
    with pytest.raises(Exception, match="ck_student_messages_inbound"):  # a reply has no delivery status
        _sql(url, insert, {**row, "id": uuid.uuid4(), "d": "inbound", "ch": "email", "subj": None, "st": "sent"})
    _sql(url, insert, {**row, "id": uuid.uuid4(), "d": "inbound", "ch": "whatsapp", "subj": None, "st": None})
    with pytest.raises(RuntimeError, match="0191_student_messages"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM student_messages")
    command.downgrade(cfg, BASE)
    assert not any(_exists(url, t) for t in TABLES)
