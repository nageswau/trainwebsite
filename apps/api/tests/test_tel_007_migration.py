"""tel-007 -- migration 0082_tel_distribution (spec §3). Round trip, constraints and downgrade refusal run in a throwaway database built
from scratch (the tel-001 pattern); a downgrade never runs against the shared test database."""

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
_spec = importlib.util.spec_from_file_location("_tel_007_migration_0082", VERSIONS / "0082_tel_distribution.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0081_lead_stage_pipeline", "0082_tel_distribution"
RULE = "INSERT INTO tel_distribution_rules (id, team, kind, product_id, city, telecaller_user_id) VALUES (:id, :team, :kind, :product, :city, :user)"


def test_migration_chains_after_0081_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_models_match_the_migration():
    from app.models import TelDistributionRule, TelRoundRobinCursor

    rules = TelDistributionRule.__table__
    assert {c.name for c in rules.columns} == {"id", "team", "kind", "product_id", "city", "telecaller_user_id", "created_at", "updated_at"}
    assert rules.c.product_id.nullable and rules.c.city.nullable and not rules.c.telecaller_user_id.nullable
    names = {i.name for i in rules.indexes} | {c.name for c in rules.constraints}
    assert {
        "ck_tel_distribution_rules_team", "ck_tel_distribution_rules_kind", "ck_tel_distribution_rules_shape",
        "uq_tel_distribution_rules_product", "uq_tel_distribution_rules_city", "ix_tel_distribution_rules_telecaller",
    } <= names
    cursors = TelRoundRobinCursor.__table__
    assert {c.name for c in cursors.columns} == {"team", "last_user_id", "updated_at"}
    assert [c.name for c in cursors.primary_key] == ["team"]


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"tel007_migration_{uuid.uuid4().hex[:8]}"
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


def _user(url) -> uuid.UUID:
    user_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) "
        "VALUES (:id, :email, 'x', 'T', 'telecaller', 'it', true, true, 'en-GB', '{}')",
        {"id": user_id, "email": f"{user_id.hex[:10]}@example.com"},
    )
    return user_id


def _product(url) -> uuid.UUID:
    product_id = uuid.uuid4()
    _sql(url, "INSERT INTO tel_products (id, product_group, name, team) VALUES (:id, 'it', :name, 'it')", {"id": product_id, "name": f"P {product_id.hex[:6]}"})
    return product_id


def _rule(url, user, **overrides):
    row = {"id": uuid.uuid4(), "team": "it", "kind": "city", "product": None, "city": "Hyderabad", "user": user}
    row.update(overrides)
    _sql(url, RULE, row)


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    user, product = _user(url), _product(url)
    _rule(url, user)
    with pytest.raises(Exception, match="uq_tel_distribution_rules_city"):
        _rule(url, user, city="hyderabad")  # case-insensitive
    _rule(url, user, team="overseas")  # the same city on the other team is a different rule
    _rule(url, user, kind="product", product=product, city=None)
    with pytest.raises(Exception, match="uq_tel_distribution_rules_product"):
        _rule(url, user, kind="product", product=product, city=None)
    cases = {
        "ck_tel_distribution_rules_team": {"team": "global", "city": "Pune"},
        "ck_tel_distribution_rules_kind": {"kind": "state", "city": "Pune"},
        "ck_tel_distribution_rules_shape": {"kind": "product", "city": "Pune"},
    }
    for constraint, overrides in cases.items():
        with pytest.raises(Exception, match=constraint):
            _rule(url, user, **overrides)
    _sql(url, "INSERT INTO tel_round_robin_cursors (team, last_user_id) VALUES ('it', :user)", {"user": user})
    with pytest.raises(Exception, match="ck_tel_round_robin_cursors_team"):
        _sql(url, "INSERT INTO tel_round_robin_cursors (team) VALUES ('global')")
    with pytest.raises(Exception, match="Cannot downgrade 0082_tel_distribution"):
        command.downgrade(cfg, BASE)
    _sql(url, "DELETE FROM tel_distribution_rules")
    command.downgrade(cfg, BASE)
    assert not _sql(url, "SELECT 1 FROM information_schema.tables WHERE table_name IN ('tel_distribution_rules', 'tel_round_robin_cursors')")
    command.upgrade(cfg, HEAD)
    assert _sql(url, "SELECT count(*) FROM tel_distribution_rules") == [(0,)]
