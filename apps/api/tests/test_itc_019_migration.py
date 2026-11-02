"""itc-019 -- migration 0230_trainer_profiles (DEC-SCOPE-346): the trainer profile table. Round trip in a throwaway database built from
scratch (the upc-001 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import TrainerProfile
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_itc_019_migration_0230", VERSIONS / "0230_trainer_profiles.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD = "0230_trainer_profiles"
BASE = "0229_it_student_profiles"
TABLES = "SELECT table_name FROM information_schema.tables WHERE table_name = 'trainer_profiles'"


def test_migration_chains_after_0229_and_is_the_single_head():
    assert (_migration.revision, _migration.down_revision) == (HEAD, BASE)
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_model_matches_the_migration():
    assert {c.name for c in TrainerProfile.__table__.constraints if c.name and c.name.startswith("ck_")} == {"ck_trainer_profiles_contact_route"}


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"itc019_migration_{uuid.uuid4().hex[:8]}"
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


def test_round_trip_creates_the_table_with_private_defaults_and_refuses_to_drop_profiles(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, TABLES) == []
    command.upgrade(cfg, HEAD)
    assert _sql(url, TABLES) == [("trainer_profiles",)]
    command.downgrade(cfg, BASE)  # empty: drops cleanly
    command.upgrade(cfg, HEAD)
    user = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'Trainer', 'trainer', 'it', true, true, 'en-GB', '{}')",
        {"id": user, "email": f"t-{user.hex[:8]}@example.local"},
        autocommit=True,
    )
    with pytest.raises(Exception, match="ck_trainer_profiles_contact_route"):
        _sql(url, "INSERT INTO trainer_profiles (user_id, contact_route) VALUES (:id, 'fax')", {"id": user}, autocommit=True)
    _sql(url, "INSERT INTO trainer_profiles (user_id) VALUES (:id)", {"id": user}, autocommit=True)
    row = _sql(url, "SELECT contact_route, show_email, show_phone, show_photo, expertise::text FROM trainer_profiles")[0]
    assert tuple(row) == ("in_app", False, False, True, "[]")  # F1: personal fields hidden by default
    with pytest.raises(RuntimeError, match="trainer profiles exist"):
        command.downgrade(cfg, BASE)
