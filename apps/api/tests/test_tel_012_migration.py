"""tel-012 -- migration 0078_tel_content (spec §3; AC1). Round trip, seed and downgrade refusal run in a throwaway database built from
scratch (the tel-001/tel-002 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import select
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.tel_content_kinds import EMAIL_KINDS, WHATSAPP_KINDS
from tests.test_tel_001_migration import _config, _sql

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_tel_012_migration_0078", VERSIONS / "0078_tel_content.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0077_bdm_tasks_followups", "0078_tel_content"
STEPS = [
    "Introduction",
    "Understand qualification",
    "Ask career goal",
    "Explain course",
    "Check availability",
    "Fix counselling appointment",
    "Assign counselor",
]
TEMPLATES = "SELECT channel, kind FROM tel_message_templates"
SCRIPTS = "SELECT s.name, s.steps, p.name FROM tel_scripts s JOIN tel_products p ON p.id = s.product_id"


def test_migration_chains_after_0077_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    assert ScriptDirectory.from_config(_config()).get_heads() == [HEAD]


def test_models_match_the_migration():
    from app.models import TelAsset, TelMessageTemplate, TelScript

    script, template, asset = TelScript.__table__, TelMessageTemplate.__table__, TelAsset.__table__
    assert {c.name for c in script.columns} == {"id", "product_id", "name", "steps", "active", "created_at", "updated_at"}
    assert {c.name for c in template.columns} == {
        "id",
        "channel",
        "kind",
        "name",
        "product_id",
        "asset_id",
        "subject",
        "body",
        "active",
        "created_at",
        "updated_at",
    }
    assert {c.name for c in asset.columns} == {
        "id",
        "name",
        "kind",
        "product_id",
        "storage_key",
        "file_name",
        "size_bytes",
        "active",
        "uploaded_by_user_id",
        "created_at",
        "updated_at",
    }
    assert template.c.subject.nullable and template.c.product_id.nullable and template.c.asset_id.nullable and not template.c.body.nullable
    assert not script.c.product_id.nullable and asset.c.product_id.nullable and not asset.c.storage_key.nullable
    names = {i.name for t in (script, template, asset) for i in t.indexes} | {c.name for t in (script, template, asset) for c in t.constraints}
    assert {
        "uq_tel_scripts_active_product",
        "ck_tel_message_templates_channel",
        "ck_tel_message_templates_kind",
        "ck_tel_message_templates_subject",
        "uq_tel_message_templates_channel_name",
        "ck_tel_assets_kind",
        "uq_tel_assets_storage_key",
    } <= names


@pytest.mark.asyncio
async def test_seed_is_in_the_shared_database(db_session):
    """AC1: the shared test database was upgraded to head -- every §11/§12 kind has a generic template and the §6 script exists."""
    from app.models import TelMessageTemplate, TelProduct, TelScript

    seeded = (await db_session.execute(select(TelMessageTemplate.channel, TelMessageTemplate.kind).where(TelMessageTemplate.name.in_(_migration.SEED_NAMES)))).all()
    assert {("whatsapp", k) for k in WHATSAPP_KINDS} | {("email", k) for k in EMAIL_KINDS} <= set(seeded)
    script = await db_session.scalar(select(TelScript).join(TelProduct, TelProduct.id == TelScript.product_id).where(TelProduct.name == "Cyber Security"))
    assert [s["title"] for s in script.steps] == STEPS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel012_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _seed_again(url):
    for statement, params in _migration.seed_statements():
        _sql(url, statement, params)


def test_seed_round_trip_and_idempotence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    rows = _sql(url, TEMPLATES)
    assert len(rows) == 16 and {r for r in rows if r[0] == "whatsapp"} == {("whatsapp", k) for k in WHATSAPP_KINDS}
    assert {r for r in rows if r[0] == "email"} == {("email", k) for k in EMAIL_KINDS}
    scripts = _sql(url, SCRIPTS)
    assert len(scripts) == 1 and scripts[0][2] == "Cyber Security" and [s["title"] for s in scripts[0][1]] == STEPS
    _seed_again(url)
    assert len(_sql(url, TEMPLATES)) == 16 and len(_sql(url, SCRIPTS)) == 1
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    assert len(_sql(url, TEMPLATES)) == 16 and len(_sql(url, SCRIPTS)) == 1


def test_script_seed_skips_a_missing_or_scripted_product(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    _sql(url, "UPDATE tel_products SET name = 'Cyber Defence' WHERE name = 'Cyber Security'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, SCRIPTS) == []


def test_constraints_hold(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    insert = "INSERT INTO tel_message_templates (id, channel, kind, name, subject, body) VALUES (:id, :c, :k, :n, :s, 'b')"
    with pytest.raises(Exception, match="ck_tel_message_templates_kind"):
        _sql(url, insert, {"id": uuid.uuid4(), "c": "whatsapp", "k": "fee_proposal", "n": "X", "s": None})
    with pytest.raises(Exception, match="ck_tel_message_templates_subject"):
        _sql(url, insert, {"id": uuid.uuid4(), "c": "email", "k": "fee_proposal", "n": "X", "s": None})
    with pytest.raises(Exception, match="ck_tel_message_templates_subject"):
        _sql(url, insert, {"id": uuid.uuid4(), "c": "whatsapp", "k": "welcome", "n": "X", "s": "Hi"})
    with pytest.raises(Exception, match="uq_tel_message_templates_channel_name"):
        _sql(url, insert, {"id": uuid.uuid4(), "c": "whatsapp", "k": "welcome", "n": "welcome MESSAGE", "s": None})
    _sql(url, insert, {"id": uuid.uuid4(), "c": "email", "k": "follow_up", "n": "Welcome message", "s": "S"})  # same name, other channel
    product = _sql(url, "SELECT id FROM tel_products WHERE name = 'Cyber Security'")[0][0]
    with pytest.raises(Exception, match="uq_tel_scripts_active_product"):
        _sql(url, "INSERT INTO tel_scripts (id, product_id, name, steps) VALUES (:id, :p, 'Second', '[]')", {"id": uuid.uuid4(), "p": product})
    _sql(url, "INSERT INTO tel_scripts (id, product_id, name, steps, active) VALUES (:id, :p, 'Old', '[]', false)", {"id": uuid.uuid4(), "p": product})
    user = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'M', 'telecaller_manager', 'global', true, true, 'en-GB', '{}')",
        {"id": user, "email": f"m-{user.hex[:8]}@example.local"},
    )
    asset = "INSERT INTO tel_assets (id, name, kind, storage_key, file_name, size_bytes, uploaded_by_user_id) VALUES (:id, 'A', :k, :key, 'a.pdf', 1, :u)"
    with pytest.raises(Exception, match="ck_tel_assets_kind"):
        _sql(url, asset, {"id": uuid.uuid4(), "k": "video", "key": "tel-assets/x", "u": user})
    _sql(url, asset, {"id": uuid.uuid4(), "k": "fee", "key": "tel-assets/y", "u": user})
    with pytest.raises(Exception, match="uq_tel_assets_storage_key"):
        _sql(url, asset, {"id": uuid.uuid4(), "k": "brochure", "key": "tel-assets/y", "u": user})


def test_downgrade_refuses_while_manager_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    _sql(url, "UPDATE tel_message_templates SET body = 'Edited' WHERE name = 'Reminder'")
    with pytest.raises(Exception, match="manager data"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM tel_message_templates WHERE name = 'Reminder'")
    _seed_again(url)
    _sql(url, "UPDATE tel_scripts SET name = 'Renamed'")
    with pytest.raises(Exception, match="manager data"):
        command.downgrade(cfg, BASE)
