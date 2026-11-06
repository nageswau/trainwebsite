"""pob-020 -- migration 0292: frozen copies match the models, the default template is seeded, and checklist rows become legacy sessions."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text

from app.models import (
    SCREENING_ANSWER_CHECKS,
    SCREENING_BANK_CHECKS,
    SCREENING_CATEGORIES,
    SCREENING_FORM_CHECKS,
    SCREENING_FORM_QUESTION_CHECKS,
    SCREENING_FORMATS,
    SCREENING_RECOMMENDATIONS,
    SCREENING_SESSION_CHECKS,
    ApplicationScreening,
    ScreeningForm,
    ScreeningSession,
)
from app.services import application_screening
from tests.test_rec_017_tracking import _add, _candidate, _requirement, _team


def _load():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0292_screening_sessions.py"
    spec = importlib.util.spec_from_file_location("pob020_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MIGRATION = _load()


def test_checks_are_frozen_copies():
    assert (MIGRATION.CATEGORIES, MIGRATION.FORMATS, MIGRATION.RECOMMENDATIONS) == (SCREENING_CATEGORIES, SCREENING_FORMATS, SCREENING_RECOMMENDATIONS)
    assert MIGRATION.BANK_CHECKS == SCREENING_BANK_CHECKS and MIGRATION.FORM_QUESTION_CHECKS == SCREENING_FORM_QUESTION_CHECKS
    assert MIGRATION.FORM_CHECKS == SCREENING_FORM_CHECKS and MIGRATION.SESSION_CHECKS == SCREENING_SESSION_CHECKS and MIGRATION.ANSWER_CHECKS == SCREENING_ANSWER_CHECKS


def test_the_seed_has_one_question_per_category():
    assert tuple(q[0] for q in MIGRATION.DEFAULT_QUESTIONS) == SCREENING_CATEGORIES


def test_the_copy_and_the_save_snapshot_the_same_fields():
    for field in application_screening.FIELDS:
        assert f"'{field}'" in MIGRATION.LEGACY_COPY, field


@pytest.mark.asyncio
async def test_the_default_template_exists(db_session):
    form = await db_session.scalar(select(ScreeningForm).where(ScreeningForm.is_default.is_(True), ScreeningForm.job_id.is_(None)))
    assert form is not None and form.name == MIGRATION.DEFAULT_NAME


@pytest.mark.asyncio
async def test_the_copy_makes_one_legacy_session_and_is_idempotent(client, db_session):
    _, recruiter = await _team(client, db_session)
    job = await _requirement(db_session, recruiter)
    app_id = (await _add(client, job, await _candidate(db_session, recruiter))).json()["application"]["id"]
    application_id = __import__("uuid").UUID(app_id)
    db_session.add(ApplicationScreening(application_id=application_id, screened_by_user_id=recruiter.id, expected_salary=500000, notice_days=30, remarks="Old row", result="need_more_info"))
    await db_session.commit()
    await db_session.execute(text(MIGRATION.LEGACY_COPY))
    await db_session.execute(text(MIGRATION.LEGACY_COPY))
    await db_session.commit()
    rows = (await db_session.scalars(select(ScreeningSession).where(ScreeningSession.application_id == application_id))).all()
    assert len(rows) == 1
    session = rows[0]
    assert session.kind == "legacy" and session.recommendation == "hold" and session.notes == "Old row"
    assert session.legacy_snapshot["expected_salary"] == 500000.0 and session.legacy_snapshot["result"] == "need_more_info" and session.legacy_snapshot["notice_days"] == 30
    assert await db_session.get(ApplicationScreening, application_id) is not None
