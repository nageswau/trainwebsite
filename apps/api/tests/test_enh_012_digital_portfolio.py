"""ENH-012 -- Digital Portfolio Module.
docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md
"""
import uuid
from datetime import date

import pytest
from pydantic import ValidationError

from app.models import PortfolioEntry, PortfolioProfile
from app.schemas import PortfolioEntryCreate, PORTFOLIO_SECTIONS
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


def test_portfolio_entry_create_rejects_unknown_section():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="not_a_real_section", title="X")


def test_portfolio_entry_create_rejects_empty_title():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="")


def test_portfolio_entry_create_rejects_date_to_before_date_from():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", date_from="2026-06-01", date_to="2026-01-01")


def test_portfolio_entry_create_rejects_description_over_length_cap():
    with pytest.raises(ValidationError):
        PortfolioEntryCreate(section="project", title="X", description="a" * 2001)


def test_portfolio_entry_create_accepts_a_valid_payload():
    entry = PortfolioEntryCreate(section="award", title="Regional Science Fair — 1st place", organization="State Science Council", date_from="2026-02-01")
    assert entry.section == "award"
    assert entry.date_to is None


def test_all_ten_section_values_are_defined():
    assert PORTFOLIO_SECTIONS == {"project", "internship", "competition", "sport", "leadership", "volunteering", "extracurricular", "award", "certification", "skill"}


def test_personal_statement_rejects_payload_over_length_cap():
    from app.schemas import PersonalStatementUpdate
    with pytest.raises(ValidationError):
        PersonalStatementUpdate(personal_statement="a" * 4001)
