"""dtu-001 §4.4: the loader creates, then a second run changes nothing; existing values are never overwritten."""

import json
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.direct_tieups import load as loader
from app.direct_tieups.load import load
from app.models import AuditLog, Country, OverseasCourse, Scholarship, University


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
                      "countries_published": 0, "country_needs_content": 0}


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


async def _hidden_country(db, iso2: str, slug: str) -> Country:
    c = await db.scalar(select(Country).where(Country.iso2 == iso2))
    if c is None:
        c = Country(slug=slug, name="Dtu Test Land", iso2=iso2, region="Europe", overview="", tuition="", living_expenses="",
                    work_opportunities="", post_study_work="", pr_opportunities="")
        db.add(c)
    c.catalogue_visible, c.overview = False, ""
    await db.commit()
    return c


def _in(data: list[dict], iso2: str) -> list[dict]:
    data[0]["country_iso2"] = iso2
    return data


@pytest.mark.asyncio
async def test_hidden_country_with_a_seed_row_is_published_and_audited(db_session, monkeypatch, tmp_path):
    c = await _hidden_country(db_session, "ZQ", "dtu-test-land")
    rows = tmp_path / "countries.json"
    rows.write_text(json.dumps([["dtu-test-land", "Dtu Test Land", "Overview.", "Tuition", "Living", "ZQ", "Europe"]]), encoding="utf-8")
    monkeypatch.setattr(loader, "COUNTRIES_FILE", rows)
    name = f"Dtu Pub University {uuid.uuid4().hex[:8]}"
    report = await load(db_session, _in(_data(name), "ZQ"))
    await db_session.refresh(c)
    assert report["countries_published"] == 1 and report["country_needs_content"] == 0 and c.catalogue_visible and c.overview == "Overview."
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(c.id), AuditLog.action == "country.direct_tieup_publish"))
    again = await load(db_session, _in(_data(name), "ZQ"))
    assert again["countries_published"] == 0 and again["country_needs_content"] == 0
    c.catalogue_visible = False
    await db_session.commit()


@pytest.mark.asyncio
async def test_hidden_country_without_a_row_stays_hidden(db_session, monkeypatch, tmp_path, capsys):
    c = await _hidden_country(db_session, "ZQ", "dtu-test-land")
    rows = tmp_path / "countries.json"
    rows.write_text("[]", encoding="utf-8")
    monkeypatch.setattr(loader, "COUNTRIES_FILE", rows)
    name = f"Dtu Hid University {uuid.uuid4().hex[:8]}"
    report = await load(db_session, _in(_data(name), "ZQ"))
    await db_session.refresh(c)
    assert report["countries_published"] == 0 and report["country_needs_content"] == 1 and c.catalogue_visible is False
    assert f"ZQ: {name} stays hidden until" in capsys.readouterr().out


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("campus", "x" * 400), ("tuition_currency", "XYZ")])
async def test_invalid_course_fails_the_run_and_writes_nothing(db_session, field, value):
    name = f"Dtu Invalid University {uuid.uuid4().hex[:8]}"
    data = _data(name)
    data[0]["courses"][0][field] = value
    with pytest.raises(ValueError, match=f"{name} / MBA Global"):
        await load(db_session, data)
    assert await db_session.scalar(select(University).where(University.name == name)) is None


@pytest.mark.asyncio
async def test_invalid_university_text_fails_the_run(db_session):
    name = f"Dtu Invalid Site {uuid.uuid4().hex[:8]}"
    data = _data(name)
    data[0]["website"] = "w" * 400
    with pytest.raises(ValueError, match=name):
        await load(db_session, data)


@pytest.mark.asyncio
async def test_stored_commission_note_is_kept_when_the_amounts_are_filled(db_session):
    name = f"Dtu Note University {uuid.uuid4().hex[:8]}"
    data = _data(name)
    data[0]["agent_commission"] = None
    await load(db_session, data)
    uni = await db_session.scalar(select(University).where(University.name == name))
    uni.agent_commission_note = "owner note"
    await db_session.commit()
    report = await load(db_session, _data(name))
    await db_session.refresh(uni)
    assert uni.agent_commission_percent == 13 and uni.agent_commission_note == "owner note" and report["universities_updated"] == 1


@pytest.mark.asyncio
async def test_long_scholarship_text_is_idempotent(db_session):
    name = f"Dtu Long Sch University {uuid.uuid4().hex[:8]}"
    data = _data(name)
    data[0]["scholarships"] = ["S" * 260]
    data[0]["courses"][0]["scholarships"] = ["S" * 260]
    await load(db_session, data)
    second = await load(db_session, data)
    uni = await db_session.scalar(select(University).where(University.name == name))
    rows = (await db_session.scalars(select(Scholarship).where(Scholarship.university_id == uni.id))).all()
    assert len(rows) == 1 and second["scholarships_created"] == 0


@pytest.mark.asyncio
async def test_dry_run_on_loaded_data_changes_nothing(db_session):
    name = f"Dtu Dry2 University {uuid.uuid4().hex[:8]}"
    await load(db_session, _data(name))
    report = await load(db_session, _data(name), commit=False)
    assert report["universities_created"] == 0 and report["universities_updated"] == 0 and report["courses_created"] == 0
    count = len((await db_session.scalars(select(AuditLog).where(AuditLog.action == "university.direct_tieup_load"))).all())
    await load(db_session, _data(name), commit=False)
    assert count == len((await db_session.scalars(select(AuditLog).where(AuditLog.action == "university.direct_tieup_load"))).all())


@pytest.mark.asyncio
async def test_dry_run_commits_nothing(db_session):
    name = f"Dtu Dry University {uuid.uuid4().hex[:8]}"
    report = await load(db_session, _data(name), commit=False)
    assert report["universities_created"] == 1
    assert await db_session.scalar(select(University).where(University.name == name)) is None
