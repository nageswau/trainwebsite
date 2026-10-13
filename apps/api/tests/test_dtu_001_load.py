"""dtu-001 §4.4: the loader creates, then a second run changes nothing; existing values are never overwritten."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.direct_tieups.load import load
from app.models import AuditLog, Country, OverseasCourse, University


@pytest_asyncio.fixture(autouse=True)
async def gb_visible(db_session):
    """The shared test DB has had missing or hidden catalogue countries: make GB exist and be visible."""
    gb = await db_session.scalar(select(Country).where(Country.iso2 == "GB"))
    if gb is None:
        gb = Country(slug="united-kingdom-dtu-test", name="United Kingdom", iso2="GB", region="Europe", overview="x", tuition="x", living_expenses="x",
                     work_opportunities="x", post_study_work="x", pr_opportunities="x")
        db_session.add(gb)
    gb.catalogue_visible = True
    await db_session.commit()


def _data(name: str) -> list[dict]:
    return [{
        "name": name, "country_iso2": "GB", "city": "Cardiff Campus", "campuses": ["Cardiff Campus", "Newport Campus"], "institution_type": "university",
        "website": "https://example.ac.uk/", "overview": f"{name} — direct tie-up partner.", "fee_structure": None, "deadlines": ["Jan: Mid-November"],
        "scholarships": ["£1,500-£2,500"], "agent_commission": {"percent": "13.00", "note": "0.13"}, "logo_url": None, "flags": [], "source": "test",
        "courses": [{"title": "MBA Global", "level": "PG", "category": "Business", "duration": "Not specified", "campus": "Newport Campus", "fee_text": "£18,970",
                     "tuition_amount": "18970.00", "tuition_currency": "GBP", "intakes": ["Jan", "Sep"], "intake_text": "January / September", "scholarships": ["£1,500-£2,500"]}],
    }]


@pytest.mark.asyncio
async def test_creates_then_is_a_no_op(db_session):
    name = f"Dtu Load University {uuid.uuid4().hex[:8]}"
    first = await load(db_session, _data(name))
    assert first["universities_created"] == 1 and first["courses_created"] == 1 and first["scholarships_created"] == 1
    uni = await db_session.scalar(select(University).where(University.name == name))
    assert uni.catalogue_visible and uni.active and uni.agent_commission_percent == 13 and uni.campuses == ["Cardiff Campus", "Newport Campus"]
    course = await db_session.scalar(select(OverseasCourse).where(OverseasCourse.university_id == uni.id))
    assert course.tuition_fee and course.intake == "Jan, Sep" and course.campus == "Newport Campus" and len(course.scholarship_ids) == 1
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(uni.id), AuditLog.action == "university.direct_tieup_load"))
    second = await load(db_session, _data(name))
    assert second == {"universities_created": 0, "universities_updated": 0, "courses_created": 0, "courses_skipped": 1, "scholarships_created": 0, "conflicts": 0,
                      "hidden_country": 0}


@pytest.mark.asyncio
async def test_existing_values_are_never_overwritten(db_session):
    name = f"Dtu Existing University {uuid.uuid4().hex[:8]}"
    await load(db_session, _data(name))
    uni = await db_session.scalar(select(University).where(University.name == name))
    uni.website, uni.agent_commission_percent = "https://edited.example/", 20
    await db_session.commit()
    data = _data(name)
    data[0]["fee_structure"] = "UG: £1"
    report = await load(db_session, data)
    await db_session.refresh(uni)
    assert uni.website == "https://edited.example/" and uni.agent_commission_percent == 20 and uni.fee_structure == "UG: £1"
    assert report["universities_updated"] == 1 and report["conflicts"] == 1  # the differing agent commission is reported, not changed


@pytest.mark.asyncio
async def test_unknown_country_fails_the_whole_run(db_session):
    data = _data(f"Dtu Bad Country {uuid.uuid4().hex[:8]}")
    data[0]["country_iso2"] = "ZZ"
    with pytest.raises(ValueError, match="ZZ"):
        await load(db_session, data)


@pytest.mark.asyncio
async def test_hidden_country_is_counted_not_flipped(db_session):
    gb = await db_session.scalar(select(Country).where(Country.iso2 == "GB"))
    gb.catalogue_visible = False
    await db_session.commit()
    report = await load(db_session, _data(f"Dtu Hidden University {uuid.uuid4().hex[:8]}"))
    await db_session.refresh(gb)
    assert report["hidden_country"] == 1 and gb.catalogue_visible is False


@pytest.mark.asyncio
async def test_dry_run_commits_nothing(db_session):
    name = f"Dtu Dry University {uuid.uuid4().hex[:8]}"
    report = await load(db_session, _data(name), commit=False)
    assert report["universities_created"] == 1
    assert await db_session.scalar(select(University).where(University.name == name)) is None
