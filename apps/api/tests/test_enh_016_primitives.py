"""ENH-016 Task 2 -- scope primitives: D11 'portfolio started' and ENH-011 skill statuses per student (spec §6.1, AC13)."""

from datetime import date

import pytest
from enh016_helpers import make_school, make_student

from app.api.school_analytics import portfolio_started_ids, skill_statuses, students_in
from app.models import PortfolioEntry, PortfolioProfile, SchoolSkillBatch, SchoolSkillEnrollment


@pytest.mark.asyncio
async def test_portfolio_started_counts_entries_and_non_blank_statements_only(db_session):
    ctx = await make_school(db_session)
    coord = ctx["school_coordinator"].id
    profile_only = await make_student(db_session, ctx, grade_level=9, grade_or_class="Grade 9", date_of_birth=date(2011, 1, 1))
    with_entry = await make_student(db_session, ctx)
    with_statement = await make_student(db_session, ctx)
    blank_statement = await make_student(db_session, ctx)
    db_session.add_all([
        PortfolioEntry(school_student_id=with_entry.id, section="project", title="Robot", created_by_user_id=coord, updated_by_user_id=coord),
        PortfolioProfile(school_student_id=with_statement.id, personal_statement="I love physics."),
        PortfolioProfile(school_student_id=blank_statement.id, personal_statement=" \n\t "),  # Review Focus 3
    ])
    await db_session.flush()

    started = await portfolio_started_ids(db_session, students_in([ctx["school"].id]))

    assert started == {with_entry.id, with_statement.id}
    assert profile_only.id not in started and blank_statement.id not in started
    await db_session.rollback()


@pytest.mark.asyncio
async def test_skill_statuses_group_non_withdrawn_enrolments_by_module(db_session):
    ctx = await make_school(db_session)
    a = await make_student(db_session, ctx)
    b = await make_student(db_session, ctx)
    cc = ctx["career_counselor"].id
    soft = SchoolSkillBatch(school_id=ctx["school"].id, module_type="soft_skills", title="Soft", start_date=date(2026, 1, 1), created_by_user_id=cc)
    digital = SchoolSkillBatch(school_id=ctx["school"].id, module_type="digital_skills", title="Web", start_date=date(2026, 1, 1), created_by_user_id=cc)
    db_session.add_all([soft, digital])
    await db_session.flush()
    db_session.add_all([
        SchoolSkillEnrollment(batch_id=soft.id, school_student_id=a.id, status="completed", enrolled_by_user_id=cc),
        SchoolSkillEnrollment(batch_id=digital.id, school_student_id=a.id, status="withdrawn", enrolled_by_user_id=cc),
        SchoolSkillEnrollment(batch_id=digital.id, school_student_id=b.id, status="enrolled", enrolled_by_user_id=cc),
    ])
    await db_session.flush()

    statuses = await skill_statuses(db_session, [a.id, b.id])

    assert statuses["soft_skills"] == {a.id: ["completed"]}
    assert statuses["digital_skills"] == {b.id: ["enrolled"]}
    await db_session.rollback()
