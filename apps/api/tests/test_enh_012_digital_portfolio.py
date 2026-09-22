"""ENH-012 -- Digital Portfolio Module.
docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md
"""
import uuid
from datetime import date

import pytest

from app.models import PortfolioEntry, PortfolioProfile
from tests.enh005_helpers import mk_school, mk_staff


@pytest.mark.asyncio
async def test_portfolio_entry_and_profile_roundtrip(db_session):
    ctx = await mk_school(db_session, label="ENH012-Model")
    student = ctx["students"][0]
    entry = PortfolioEntry(
        school_student_id=student.id, section="project", title="Robotics club build",
        description="Built a line-following robot.", organization="School STEM Club",
        date_from=date(2026, 1, 10), date_to=date(2026, 3, 1),
        created_by_user_id=ctx["coordinator"].id, updated_by_user_id=ctx["coordinator"].id,
    )
    profile = PortfolioProfile(school_student_id=student.id, personal_statement="I want to study engineering.", updated_by_user_id=ctx["coordinator"].id)
    db_session.add_all([entry, profile])
    await db_session.commit()
    await db_session.refresh(entry)
    await db_session.refresh(profile)
    assert entry.id is not None
    assert entry.section == "project"
    assert profile.school_student_id == student.id


@pytest.mark.asyncio
async def test_portfolio_profile_school_student_id_is_unique(db_session):
    ctx = await mk_school(db_session, label="ENH012-Unique")
    student = ctx["students"][0]
    db_session.add(PortfolioProfile(school_student_id=student.id, personal_statement="First."))
    await db_session.commit()
    db_session.add(PortfolioProfile(school_student_id=student.id, personal_statement="Second."))
    with pytest.raises(Exception):
        await db_session.commit()
    await db_session.rollback()
