"""upc-017 -- migration 0132_university_courses (spec §2, CO5). Round trip, the legacy tuition / intake parse, constraints and the downgrade
refusal run in a throwaway database built from scratch (the rec-008 pattern); a downgrade never runs against the shared test database."""

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_tel_001_migration import _config, _sql
from tests.test_upc_026_migration import _setup

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_upc_017_migration_0132", VERSIONS / "0132_university_courses.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE, HEAD = "0131_partnership_targets", "0132_university_courses"
NEW_COLUMNS = {
    "tuition_amount", "tuition_currency", "application_fee", "application_fee_currency", "intakes", "entry_requirements", "english_test",
    "english_score", "scholarship_ids", "application_process", "deadline", "active", "commission_percent", "commission_amount", "commission_currency",
}  # fmt: skip


def test_migration_chains_after_0131_and_there_is_a_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    assert len(ScriptDirectory.from_config(_config()).get_heads()) == 1


def test_models_match_the_migration():
    from app.models import COUNSELING_CURRENCIES, COURSE_CHECKS, COURSE_CURRENCIES, COURSE_MONTHS, ENGLISH_TESTS, CourseImportBatch, OverseasCourse

    assert COURSE_CURRENCIES == COUNSELING_CURRENCIES == _migration.CURRENCIES
    assert _migration.MONTHS == COURSE_MONTHS and _migration.TESTS == ENGLISH_TESTS and _migration.CHECKS == COURSE_CHECKS
    table = OverseasCourse.__table__
    assert NEW_COLUMNS <= {c.name for c in table.columns}
    names = {i.name for i in table.indexes} | {c.name for c in table.constraints}
    assert set(COURSE_CHECKS) | {"ix_overseas_courses_university_level"} <= names
    for name, sql in COURSE_CHECKS.items():
        assert str(next(c for c in table.constraints if c.name == name).sqltext) == sql
    batch = CourseImportBatch.__table__
    assert {"uq_course_import_batches_key", "ck_course_import_batches_counts", "ix_course_import_batches_university"} <= {c.name for c in batch.constraints} | {i.name for i in batch.indexes}


@pytest.mark.parametrize(
    ("text", "parsed"),
    [
        ("£31,000", (Decimal("31000"), "GBP")),
        ("CAD 42,000", (Decimal("42000"), "CAD")),
        ("AUD 53,000", (Decimal("53000"), "AUD")),
        ("€24,000", (Decimal("24000"), "EUR")),
        ("GBP 18,000.50", (Decimal("18000.50"), "GBP")),
        ("US$ 30,000", (Decimal("30000"), "USD")),
        ("₹ 4,50,000", (Decimal("450000"), "INR")),
        ("12000 NZD", (Decimal("12000"), "NZD")),
        ("$30,000", None),  # a bare $ could be USD, CAD, AUD or NZD
        ("See university fee policy", None),
        ("£20,000 - £25,000", None),
        ("", None),
    ],
)
def test_legacy_tuition_parse_is_best_effort(text, parsed):
    assert _migration.parse_tuition(text) == parsed


@pytest.mark.parametrize(
    ("text", "months"),
    [
        ("September", ["Sep"]),
        ("February/July", ["Feb", "Jul"]),
        ("Sep, Jan", ["Jan", "Sep"]),
        ("January and May", ["Jan", "May"]),
        ("Winter", []),
        ("Fall", []),
        ("Sep 2026", []),
        ("", []),
    ],
)
def test_legacy_intake_parse_only_reads_month_names(text, months):
    assert _migration.parse_intakes(text) == months


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"upc017_migration_{uuid.uuid4().hex[:8]}"
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


def _course(url, uni_id, fee: str, intake: str) -> uuid.UUID:
    course_id = uuid.uuid4()
    _sql(
        url,
        "INSERT INTO overseas_courses (id, university_id, title, level, category, duration, tuition_fee, intake, created_at, updated_at) "
        "VALUES (:id, :u, 'MSc X', 'Masters', 'Tech', '1 year', :fee, :intake, now(), now())",
        {"id": course_id, "u": uni_id, "fee": fee, "intake": intake},
    )
    return course_id


def test_upgrade_parses_legacy_rows_keeps_their_texts_and_round_trips(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "tuition_amount" not in {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'overseas_courses'")}
    uni_id, user_id = _setup(url)
    parsed = _course(url, uni_id, "£31,000", "February/July")
    unparsed = _course(url, uni_id, "See university fee policy", "Winter")
    _sql(url, "INSERT INTO overseas_applications (id, student_id, university_id, course_id, status, intake, created_at, updated_at) VALUES (:id, :s, :u, :c, 'enquiry', 'Sep 2027', now(), now())",
         {"id": uuid.uuid4(), "s": user_id, "u": uni_id, "c": parsed})  # fmt: skip
    command.upgrade(cfg, HEAD)
    rows = dict((r[0], r[1:]) for r in _sql(url, "SELECT id, tuition_amount, tuition_currency, intakes::text, tuition_fee, intake, active, scholarship_ids::text FROM overseas_courses"))
    assert rows[parsed] == (Decimal("31000.00"), "GBP", '["Feb", "Jul"]', "£31,000", "February/July", True, "[]")
    assert rows[unparsed] == (None, None, "[]", "See university fee policy", "Winter", True, "[]")
    assert _sql(url, "SELECT course_id FROM overseas_applications") == [(parsed,)]  # AC2: applications keep their course
    for sql, check in (
        ("tuition_amount = -1", "ck_overseas_courses_tuition"),
        ("tuition_currency = NULL", "ck_overseas_courses_tuition"),
        ("tuition_currency = 'XYZ'", "ck_overseas_courses_tuition_currency"),
        ("application_fee = 50", "ck_overseas_courses_fee"),
        ("english_score = 6.5", "ck_overseas_courses_english_score"),
        ("english_test = 'CAE'", "ck_overseas_courses_english_test"),
        ("commission_percent = 10, commission_amount = 5, commission_currency = 'GBP'", "ck_overseas_courses_commission"),
        ("commission_percent = 101", "ck_overseas_courses_commission_percent"),
        ("commission_amount = 5", "ck_overseas_courses_commission_amount"),
    ):
        with pytest.raises(Exception, match=check):
            _sql(url, f"UPDATE overseas_courses SET {sql} WHERE id = :id", {"id": parsed})
    command.downgrade(cfg, BASE)  # parsed values are re-derivable from the kept texts, so they do not block a downgrade
    assert _sql(url, "SELECT to_regclass('course_import_batches')") == [(None,)]
    command.upgrade(cfg, HEAD)


def test_downgrade_refuses_while_master_only_data_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    command.upgrade(cfg, HEAD)
    uni_id, _ = _setup(url)
    course_id = _course(url, uni_id, "GBP 18,000", "Sep")
    _sql(url, "UPDATE overseas_courses SET english_test = 'IELTS', english_score = 6.5 WHERE id = :id", {"id": course_id})
    with pytest.raises(Exception, match="course master data exists"):
        command.downgrade(cfg, BASE)
    _sql(url, "UPDATE overseas_courses SET english_test = NULL, english_score = NULL, active = false WHERE id = :id", {"id": course_id})
    with pytest.raises(Exception, match="course master data exists"):
        command.downgrade(cfg, BASE)
