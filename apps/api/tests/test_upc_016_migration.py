"""upc-016 -- migration 0129_university_commission_terms (spec §2). Round trip, constraints and the downgrade refusal run in a throwaway
database built from scratch (the rec-008 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql
from tests.test_upc_014_migration import _agreement
from tests.test_upc_026_migration import _setup

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_upc_016_migration_0129", VERSIONS / "0129_university_commission_terms.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0128_university_milestones", "0129_university_commission_terms"
COLUMNS = {
    "id", "agreement_id", "commission_percent", "fixed_amount", "currency", "conditions", "course_ids", "country_ids", "payment_timeline",
    "trigger", "payment_terms", "created_by_user_id", "updated_by_user_id", "created_at", "updated_at",
}  # fmt: skip


def test_migration_chains_after_0128_and_there_is_a_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import COMMISSION_CURRENCIES, COMMISSION_TERM_CHECKS, COMMISSION_TRIGGERS, UniversityCommissionTerm

    assert _migration.TRIGGERS == COMMISSION_TRIGGERS and _migration.CURRENCIES == COMMISSION_CURRENCIES
    assert _migration.CHECKS == COMMISSION_TERM_CHECKS
    table = UniversityCommissionTerm.__table__
    assert {c.name for c in table.columns} == COLUMNS
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(COMMISSION_TERM_CHECKS) | {"ix_university_commission_terms_agreement"} <= names
    for name, sql in COMMISSION_TERM_CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc016_migration_{uuid.uuid4().hex[:8]}"
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


def _term(url, agreement_id, user_id, **over) -> None:
    values = {"id": uuid.uuid4(), "a": agreement_id, "by": user_id, "pct": 15, "fixed": None, "cur": "GBP", "trig": "visa_and_enrolment"} | over
    _sql(
        url,
        "INSERT INTO university_commission_terms (id, agreement_id, commission_percent, fixed_amount, currency, course_ids, country_ids, trigger, "
        "created_by_user_id, updated_by_user_id, created_at, updated_at) VALUES (:id, :a, :pct, :fixed, :cur, '[]', '[]', :trig, :by, :by, now(), now())",
        values,
    )


def test_round_trip_and_constraints(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _sql(url, "SELECT to_regclass('university_commission_terms')") == [(None,)]
    command.upgrade(cfg, HEAD)
    uni_id, user_id = _setup(url)
    agreement = _agreement(url, uni_id, user_id)
    _term(url, agreement, user_id)
    _term(url, agreement, user_id, pct=None, fixed=1500)
    for over, check in (
        ({"pct": 15, "fixed": 1500}, "ck_university_commission_terms_one_rate"),
        ({"pct": None, "fixed": None}, "ck_university_commission_terms_one_rate"),
        ({"pct": 0}, "ck_university_commission_terms_percent"),
        ({"pct": 100.01}, "ck_university_commission_terms_percent"),
        ({"pct": None, "fixed": 0}, "ck_university_commission_terms_fixed"),
        ({"cur": "XYZ"}, "ck_university_commission_terms_currency"),
        ({"trig": "application"}, "ck_university_commission_terms_trigger"),
    ):
        with pytest.raises(Exception, match=check):
            _term(url, agreement, user_id, **over)
    _sql(url, "DELETE FROM university_commission_terms")
    command.downgrade(cfg, BASE)
    assert _sql(url, "SELECT to_regclass('university_commission_terms')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_terms_exist(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    uni_id, user_id = _setup(url)
    _term(url, _agreement(url, uni_id, user_id), user_id)
    with pytest.raises(Exception, match="commission terms exist"):
        command.downgrade(cfg, BASE)
