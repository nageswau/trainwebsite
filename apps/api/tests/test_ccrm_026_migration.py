"""ccrm-026 -- migration 0177_visa_lifecycle (DEC-SCOPE-252): the chain, the constants it repeats, the status backfill, the CHECK and the
round trip, in a throwaway database (the ccrm-021 pattern). Plain tests: alembic/env.py calls asyncio.run()."""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url

from alembic import command
from app.core.config import settings
from tests.test_upc_001_migration import VERSIONS, _config, _sql

_spec = importlib.util.spec_from_file_location("_ccrm_026_migration_0177", VERSIONS / "0177_visa_lifecycle.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

HEAD, BASE = "0177_visa_lifecycle", "0176_document_status"


def test_migration_chains_after_0176_and_is_the_single_head():
    assert _migration.revision == HEAD and _migration.down_revision == BASE
    script = ScriptDirectory.from_config(_config())
    assert len(script.get_heads()) == 1 and HEAD in {r.revision for r in script.walk_revisions()}


def test_the_migration_repeats_the_model_constants():
    from app.visa_status import FIRST_OF_STAGE, VISA_STATUSES

    assert _migration.STATUSES == VISA_STATUSES and _migration.FIRST_OF_STAGE == FIRST_OF_STAGE


@pytest.fixture
def isolated_db():
    cfg = _config()
    original = settings.database_url
    name = f"ccrm026_migration_{uuid.uuid4().hex[:8]}"
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
    return {r[0] for r in _sql(url, "SELECT column_name FROM information_schema.columns WHERE table_name = 'visa_cases'")}


def test_backfill_check_and_round_trip(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    assert "visa_status" not in _columns(url)
    country, university = uuid.uuid4(), uuid.uuid4()
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
    rows = {"checklist": None, "documentation": None, "tracking": None, "decision": None, "not_started": None, "refused": "refused"}
    cases = {}
    for key, decision in rows.items():
        app, case = uuid.uuid4(), uuid.uuid4()
        _sql(url, "INSERT INTO overseas_applications (id, university_id, status, intake) VALUES (:id, :u, 'offer', 'Fall 2027')", {"id": app, "u": university})
        stage = "decision" if key == "refused" else key
        _sql(
            url,
            "INSERT INTO visa_cases (id, application_id, status, checklist, decision, decided_at, created_at, updated_at) VALUES (:id, :a, :stage, '[]', :decision, :decided, now(), now())",
            {"id": case, "a": app, "stage": stage, "decision": decision, "decided": datetime(2026, 3, 4, 10, tzinfo=timezone(timedelta(hours=5, minutes=30))) if decision else None},
        )
        cases[key] = case

    command.upgrade(cfg, HEAD)
    stored = {r[0]: (r[1], r[2]) for r in _sql(url, "SELECT id, visa_status, decision_date FROM visa_cases")}
    assert {k: stored[v][0] for k, v in cases.items()} == {
        "checklist": "not_started", "documentation": "preparing", "tracking": "submitted", "decision": "decision_pending",
        "not_started": "not_started", "refused": "refused",
    }  # fmt: skip
    assert stored[cases["refused"]][1].isoformat() == "2026-03-04" and stored[cases["checklist"]][1] is None
    assert {"visa_status", "refusal_reason", "next_steps", "outcome_document_id", "appointment_place"} <= _columns(url)
    with pytest.raises(sa.exc.IntegrityError):
        _sql(url, "UPDATE visa_cases SET visa_status = 'lost' WHERE id = :id", {"id": cases["checklist"]})

    command.downgrade(cfg, BASE)
    assert "visa_status" not in _columns(url) and "refusal_reason" not in _columns(url)
    assert len(_sql(url, "SELECT id FROM visa_cases")) == len(cases)
