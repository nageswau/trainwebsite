"""ccrm-051 -- migration 0217_course_agent_commission (DEC-SCOPE-327): the chain, the CHECKs equal to the model's, and the round trip in a
throwaway database (the nehn-019 pattern); the downgrade refuses while a course agent commission exists (0157's rule). Plain tests:
alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from app.models import COURSE_AGENT_COMMISSION_CHECKS
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_051_migration_0217", VERSIONS / "0217_course_agent_commission.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0217_course_agent_commission", "0216_payment_proof_documents"
COLUMNS = ("agent_commission_percent", "agent_commission_amount", "agent_commission_currency", "agent_commission_note")


def test_migration_chains_after_0216_and_repeats_the_model_checks():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}
    assert _migration.CHECKS == COURSE_AGENT_COMMISSION_CHECKS


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm051_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, "head")
        yield {"cfg": cfg, "url": url}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def _columns(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'overseas_courses' AND column_name LIKE 'agent_commission%'")}


def _checks(url) -> set[str]:
    return {r[0] for r in _sql(url, "SELECT conname FROM pg_constraint WHERE conname LIKE 'ck_overseas_courses_agent_commission%'")}


def test_ac6_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert _columns(url) == set(COLUMNS) and _checks(url) == set(COURSE_AGENT_COMMISSION_CHECKS)
    command.downgrade(cfg, BASE)
    assert _columns(url) == set() and _checks(url) == set()
    command.upgrade(cfg, HEAD)
    assert _columns(url) == set(COLUMNS) and _checks(url) == set(COURSE_AGENT_COMMISSION_CHECKS)


def test_the_downgrade_refuses_while_a_course_agent_commission_exists(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    country = uuid.uuid4()
    uni = uuid.uuid4()
    _sql(url, f"""INSERT INTO countries (id, name, slug, faq, tuition, living_expenses, visa_process, work_opportunities, post_study_work,
              pr_opportunities, overview) VALUES ('{country}', 'Mig051land', 'mig051land', '[]', '', '', '[]', '', '', '', '')""", autocommit=True)
    _sql(url, f"""INSERT INTO universities (id, country_id, name, name_key, slug, city, overview, eligibility, requirements, deadlines, scholarships)
              VALUES ('{uni}', '{country}', 'Mig051 Uni', 'mig051 uni', 'mig051-uni', 'X', '', '', '[]', '[]', '[]')""", autocommit=True)
    _sql(url, f"""INSERT INTO overseas_courses (id, university_id, title, level, category, duration, tuition_fee, intake, agent_commission_percent)
              VALUES ('{uuid.uuid4()}', '{uni}', 'Mig051 Course', 'PG', 'CS', '1 year', '', '', 12)""", autocommit=True)
    with pytest.raises(RuntimeError, match="course agent commissions exist"):
        command.downgrade(cfg, BASE)
    assert _columns(url) == set(COLUMNS)
