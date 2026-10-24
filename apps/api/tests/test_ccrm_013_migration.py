"""ccrm-013 -- migration 0179_application_fields (DEC-SCOPE-256): the chain, the constants it repeats, the CHECKs, existing rows kept, and
the round trip, in a throwaway database (the ccrm-021 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_013_migration_0179", VERSIONS / "0179_application_fields.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0179_application_fields", "0178_offer_decisions_deposits"


def test_migration_chains_after_its_base_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.application_fields import CURRENCIES, SCHOLARSHIP_STATUSES
    from app.models import APPLICATION_FIELD_CHECKS

    assert _migration.CURRENCIES == CURRENCIES and _migration.SCHOLARSHIP_STATUSES == SCHOLARSHIP_STATUSES
    assert _migration.CHECKS == APPLICATION_FIELD_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm013_migration_{uuid.uuid4().hex[:8]}"
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


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'overseas_applications'")}


def test_columns_checks_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "scholarship_status" not in _columns(url)
    country, university, app = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    _sql(
        url,
        "INSERT INTO countries (id, slug, name, overview, tuition, living_expenses, visa_process, work_opportunities, post_study_work, pr_opportunities, faq) "
        "VALUES (:id, :slug, 'Testland', '', '', '', '[]', '', '', '', '[]')",
        {"id": country, "slug": f"c-{country.hex[:8]}"},
    )
    _sql(
        url,
        "INSERT INTO universities (id, country_id, slug, name, name_key, city, overview, eligibility, requirements, deadlines, scholarships) "
        "VALUES (:id, :country, :slug, 'Ccrm University', 'ccrm university', 'Town', '', '', '[]', '[]', '[]')",
        {"id": university, "country": country, "slug": f"u-{university.hex[:8]}"},
    )
    _sql(url, "INSERT INTO overseas_applications (id, university_id, status, intake, submitted_on) VALUES (:id, :u, 'offer', 'Fall 2027', '2026-09-01')", {"id": app, "u": university})

    command.upgrade(cfg, HEAD)
    assert {name for name, _ in _migration.COLUMNS} <= _columns(url)
    assert _sql(url, "SELECT intake, submitted_on::text, scholarship_status FROM overseas_applications WHERE id = :id", {"id": app})[0] == ("Fall 2027", "2026-09-01", None)
    _sql(url, "UPDATE overseas_applications SET currency = 'GBP', tuition_fee = 100, scholarship_status = 'awarded', scholarship_amount = 50 WHERE id = :id", {"id": app})
    for bad in ("currency = 'JPY'", "scholarship_status = 'maybe'", "tuition_fee = -1", "scholarship_status = 'applied'"):
        with pytest.raises(sa.exc.IntegrityError):
            _sql(url, f"UPDATE overseas_applications SET {bad} WHERE id = :id", {"id": app})  # noqa: S608 -- test constants

    command.downgrade(cfg, BASE)
    assert "scholarship_status" not in _columns(url) and "faculty" not in _columns(url)
    assert len(_sql(url, "SELECT id FROM overseas_applications")) == 1
