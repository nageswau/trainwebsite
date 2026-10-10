"""upc-024 -- Global university search (spec §2 SR1-SR16, §5 AC1-AC10; DEC-SCOPE-162). The test database is shared and never
truncated, so every university here carries a per-test tag in its name and each search sends `q=<tag>`."""

import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import event, insert, select

from app.core.database import engine
from app.models import Country, OverseasCourse, Scholarship, University, UniversityCommissionTerm, UniversityRanking
from app.schemas import UniversitySearchQuery
from app.services import university_search
from tests.test_upc_014_agreements import signed
from tests.upc003_helpers import as_role, login, make_head, make_pm, make_user

SEARCH = "/api/v1/partnership/universities/search"


def tag() -> str:
    return f"Srch{uuid.uuid4().hex[:8]}"


async def country(db, iso2: str) -> Country:
    return await db.scalar(select(Country).where(Country.iso2 == iso2))


def course(title: str, *, category: str = "General", level: str = "PG", **fields) -> dict:
    return {"title": title, "category": category, "level": level} | fields


async def mk(db, t: str, iso2: str, label: str, *, stage: str = "target_university", lost: bool = False, courses=(), rankings=(), **fields) -> University:
    """One active university named "<label> <tag>" with its courses and rankings, written straight to the tables."""
    c = await country(db, iso2)
    uni = University(
        country_id=c.id, slug=f"{label}-{t}-{uuid.uuid4().hex[:6]}".lower(), name=f"{label} {t}", city=fields.pop("city", "Capital"), overview="",
        eligibility="", requirements=[], deadlines=[], scholarships=[], catalogue_visible=False, stage=stage,
        lost_at=datetime.now(UTC) if lost else None, lost_reason="No response" if lost else None, **fields,
    )  # fmt: skip
    db.add(uni)
    await db.flush()
    for row in courses:
        values = {"duration": "1 year", "tuition_fee": "", "intake": "", "intakes": [], "scholarship_ids": []} | row
        db.add(OverseasCourse(university_id=uni.id, **values))
    for system, rank, year in rankings:
        db.add(UniversityRanking(university_id=uni.id, system=system, other_name="Guardian" if system == "Other" else None, year=year, rank=rank))
    await db.commit()
    return uni


async def names(client, t: str, **params) -> set[str]:
    response = await client.get(SEARCH, params={"q": t, **params})
    assert response.status_code == 200, response.text
    return {item["name"].removesuffix(f" {t}") for item in response.json()["items"]}


async def head_in(client, db):
    head = await make_head(db)
    await login(client, head)
    return head


# --- AC1-AC3: the three §25 examples ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_three_source_examples_return_the_right_sets(client, db_session):
    t = tag()
    cyber = [course("MSc Cyber Security", category="Computer Science")]
    await mk(db_session, t, "JP", "JpTarget", courses=cyber)
    await mk(db_session, t, "JP", "JpTalking", stage="interested", courses=cyber)
    await mk(db_session, t, "JP", "JpPartner", stage="active_partner", courses=cyber)
    await mk(db_session, t, "JP", "JpLost", lost=True, courses=cyber)
    await mk(db_session, t, "JP", "JpHistory", courses=[course("BA History", category="Humanities")])
    business = [course("MBA", category="Business", level="PG")]
    await mk(db_session, t, "GB", "UkTalking", stage="meeting_completed", courses=business)
    await mk(db_session, t, "GB", "UkTarget", courses=business)
    await mk(db_session, t, "JP", "JpBusiness", stage="interested", courses=business)
    it = [course("BSc Computing", category="IT", level="UG")]
    await mk(db_session, t, "DE", "DeActive", stage="active_partner", courses=it)
    await mk(db_session, t, "DE", "DeActivated", stage="partner_activated", courses=it)
    await mk(db_session, t, "DE", "DeSigned", stage="agreement_signed", courses=it)  # PS3: Agreement Signed is still in progress
    await mk(db_session, t, "DE", "DeSecurity", stage="active_partner", courses=cyber)  # "IT" is a word, not the letters in "Security"
    await head_in(client, db_session)

    assert await names(client, t, country="Japan", course="Cyber Security", partner_status="not_partnered") == {"JpTarget", "JpTalking"}
    assert await names(client, t, region="UK", course="Business", partner_status="in_progress") == {"UkTalking"}
    assert await names(client, t, country="Germany", course="IT", partner_status="partner") == {"DeActive", "DeActivated"}
    assert await names(client, t, country="jp", partner_status="lost") == {"JpLost"}  # ISO-2, any case


# --- AC4: each filter --------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_location_institution_ranking_and_date_filters(client, db_session):
    t = tag()
    await mk(db_session, t, "GB", "Leeds", city="Leeds", institution_type="university", ownership_type="public", rankings=[("QS", "120", 2026)],
             target_partnership_date=date(2027, 3, 1))  # fmt: skip
    await mk(db_session, t, "GB", "Band", city="York", institution_type="college", ownership_type="private", rankings=[("Other", "201-250", 2025)],
             target_partnership_date=date(2027, 6, 30))  # fmt: skip
    await mk(db_session, t, "DE", "Unranked", city="Berlin", rankings=[("THE", "N/A", 2026)])
    await head_in(client, db_session)

    assert await names(client, t, region="Europe") == {"Unranked"}
    assert await names(client, t, city="lee") == {"Leeds"}
    assert await names(client, t, institution_type="college") == {"Band"}
    assert await names(client, t, ownership_type="public") == {"Leeds"}
    assert await names(client, t, ranking_max=200) == {"Leeds"}
    assert await names(client, t, ranking_max=201) == {"Leeds", "Band"}  # a band counts by its start
    assert await names(client, t, ranking_max=500, ranking_system="Other") == {"Band"}
    assert await names(client, t, ranking_max=10000, ranking_system="THE") == set()  # no leading number never matches
    assert await names(client, t, expected_from="2027-03-01", expected_to="2027-03-31") == {"Leeds"}
    assert await names(client, t, expected_from="2027-04-01") == {"Band"}
    rows = (await client.get(SEARCH, params={"q": t, "city": "York"})).json()["items"]
    assert rows[0]["ranking"] == "Guardian 2025: 201-250" and rows[0]["ownership_type"] == "private" and rows[0]["target_partnership_date"] == "2027-06-30"


@pytest.mark.asyncio
async def test_course_filters_hold_for_one_course(client, db_session):
    t = tag()
    await mk(db_session, t, "GB", "Split", courses=[course("BBA", category="Business", level="UG"), course("MA History", category="Humanities", level="PG")])
    await mk(db_session, t, "GB", "Both", courses=[
        course("MSc Business Analytics", category="Business", level="PG", intakes=["Jan", "Sep"], tuition_amount=Decimal("18000"), tuition_currency="GBP"),
        course("MBA", category="Business", level="PG", intakes=["Sep"], tuition_amount=Decimal("30000"), tuition_currency="GBP"),
        course("Old Business", category="Business", level="PG", active=False),
    ])  # fmt: skip
    await mk(db_session, t, "GB", "Dollar", courses=[course("MSc Finance", category="Business", level="PG", tuition_amount=Decimal("15000"), tuition_currency="USD")])
    await head_in(client, db_session)

    assert await names(client, t, course="Business", level="PG") == {"Both", "Dollar"}  # Split's Business course is UG
    assert await names(client, t, level="UG") == {"Split"}
    assert await names(client, t, intake="Jan") == {"Both"}  # a course with several intakes matches each month
    assert await names(client, t, intake="Sep") == {"Both"}
    assert await names(client, t, intake="May") == set()
    assert await names(client, t, tuition_min=10000, tuition_max=20000, tuition_currency="GBP") == {"Both"}
    assert await names(client, t, tuition_min=10000, tuition_max=20000, tuition_currency="USD") == {"Dollar"}
    assert await names(client, t, course="Old") == set()  # inactive courses never match
    rows = {r["name"]: r for r in (await client.get(SEARCH, params={"q": t, "course": "Business", "level": "PG"})).json()["items"]}
    assert rows[f"Both {t}"]["matching_courses"] == 2
    plain = (await client.get(SEARCH, params={"q": t})).json()["items"]
    assert {r["matching_courses"] for r in plain} == {None}


@pytest.mark.asyncio
async def test_scholarship_and_manager_filters(client, db_session):
    t = tag()
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    direct = await mk(db_session, t, "GB", "Direct", primary_manager_user_id=pm.id)
    db_session.add(Scholarship(title=f"Award {t}", university_id=direct.id, eligibility="Merit", amount="£1", active=True))
    linked = await mk(db_session, t, "GB", "Linked", primary_manager_user_id=(await make_pm(db_session, head)).id, backup_manager_user_id=pm.id)
    award = Scholarship(title=f"Linked award {t}", university_id=linked.id, eligibility="Merit", amount="£1", active=False)  # inactive itself
    db_session.add(award)
    await db_session.flush()
    db_session.add(OverseasCourse(university_id=linked.id, title="MSc", category="Science", level="PG", duration="1 year", tuition_fee="", intake="", intakes=[], scholarship_ids=[str(award.id)]))
    await mk(db_session, t, "GB", "None")
    await db_session.commit()
    await login(client, pm)

    assert await names(client, t, scholarship="true") == {"Direct", "Linked"}
    assert await names(client, t, scholarship="false") == {"Direct", "Linked", "None"}  # false is no filter
    assert await names(client, t, manager="me") == {"Direct", "Linked"}  # primary or backup
    assert await names(client, t, manager="none") == {"None"}  # no primary
    assert await names(client, t, manager=str(pm.id)) == {"Direct", "Linked"}


@pytest.mark.asyncio
async def test_deactivated_universities_are_not_searched(client, db_session):
    t = tag()
    await mk(db_session, t, "GB", "Gone", active=False)
    await mk(db_session, t, "GB", "Here")
    await head_in(client, db_session)
    assert await names(client, t) == {"Here"}


# --- AC5: the commission filter (U2, SR10) ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_commission_filter_is_for_commission_roles_only(client, db_session):
    t = tag()
    head = await make_head(db_session)
    pm = await make_pm(db_session, head)
    await mk(db_session, t, "GB", "Course12", courses=[course("MBA", commission_percent=Decimal("12"))])
    await mk(db_session, t, "GB", "Fixed", courses=[course("MBA", commission_amount=Decimal("900"), commission_currency="GBP")])
    agreed = await mk(db_session, t, "GB", "Agreed20", primary_manager_user_id=pm.id)
    await login(client, pm)
    a = await signed(client, head, pm, str(agreed.id), start_date="2026-01-01", expiry_date="2028-01-01", agreement_type="commission_agreement")
    db_session.add(UniversityCommissionTerm(agreement_id=uuid.UUID(a["id"]), created_by_user_id=pm.id, updated_by_user_id=pm.id, commission_percent=Decimal("20"),
                                            currency="GBP", trigger="enrolment", course_ids=[], country_ids=[]))  # fmt: skip
    await db_session.commit()

    for actor in (head, pm, await make_user(db_session, "super_admin", "global")):
        await login(client, actor)
        assert await names(client, t, commission_min="10") == {"Course12", "Agreed20"}
        assert await names(client, t, commission_min="15") == {"Agreed20"}
    every = {"Course12", "Fixed", "Agreed20"}
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert await names(client, t, commission_min="15") == every  # ignored: never filtered, so nothing can be inferred
    assert await names(client, t, commission_min="100") == every
    body = (await client.get(SEARCH, params={"q": t, "commission_min": "15"})).json()
    assert not any("commission" in key for item in body["items"] for key in item)


# --- AC6: readers and validation -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("bdm", "overseas"), ("overseas_student", "overseas"), ("overseas_admin", "it")])
async def test_other_roles_are_refused(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(SEARCH)).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.get(SEARCH)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"region": "Mars"}, {"level": "Masters"}, {"intake": "September"}, {"partner_status": "partnered"}, {"institution_type": "school"},
        {"ownership_type": "state"}, {"ranking_max": 0}, {"ranking_system": "Times"}, {"tuition_min": 100}, {"tuition_max": 100},
        {"tuition_min": -1, "tuition_currency": "GBP"}, {"tuition_min": 200, "tuition_max": 100, "tuition_currency": "GBP"},
        {"tuition_currency": "XYZ"}, {"expected_from": "2027-05-01", "expected_to": "2027-04-01"}, {"manager": "someone"},
        {"commission_min": 0}, {"commission_min": 101}, {"limit": 0}, {"limit": 101}, {"offset": -1}, {"country": "x" * 101},
    ],
)  # fmt: skip
async def test_bad_values_are_422(client, db_session, params):
    await head_in(client, db_session)
    response = await client.get(SEARCH, params=params)
    assert response.status_code == 422, response.text


# --- AC7: paging and facets ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_paging_and_partner_status_facets(client, db_session):
    t = tag()
    await mk(db_session, t, "GB", "A1", stage="active_partner")
    await mk(db_session, t, "GB", "A2", stage="initial_contact")
    await mk(db_session, t, "GB", "A3", stage="proposal_sent")
    await mk(db_session, t, "GB", "A4")
    await mk(db_session, t, "GB", "A5", lost=True, stage="interested")
    await head_in(client, db_session)

    first = (await client.get(SEARCH, params={"q": t, "limit": 2})).json()
    assert first["total"] == 5 and first["limit"] == 2 and first["offset"] == 0
    assert [i["name"] for i in first["items"]] == [f"A1 {t}", f"A2 {t}"]
    assert first["facets"]["partner_status"] == {"partner": 1, "in_progress": 2, "target": 1, "lost": 1}
    last = (await client.get(SEARCH, params={"q": t, "limit": 2, "offset": 4})).json()
    assert [i["name"] for i in last["items"]] == [f"A5 {t}"] and last["items"][0]["partner_status"] == "lost"
    narrowed = (await client.get(SEARCH, params={"q": t, "partner_status": "in_progress"})).json()
    assert narrowed["total"] == 2 and {i["partner_status"] for i in narrowed["items"]} == {"in_progress"}
    assert narrowed["facets"]["partner_status"] == first["facets"]["partner_status"]  # computed without its own filter
    assert first["items"][0]["stage_label"] == "Active Partner" and "permissions" in first["items"][0]


# --- AC8: fixed query count and budget (SR15) -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_query_count_does_not_grow_with_results(client, db_session):
    t = tag()
    for i in range(3):
        await mk(db_session, t, "GB", f"Q{i}", courses=[course("MBA", category="Business")], rankings=[("QS", str(100 + i), 2026)])
    await head_in(client, db_session)
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        counts = []
        for limit in (1, 3):
            statements.clear()
            assert (await client.get(SEARCH, params={"q": t, "course": "MBA", "limit": limit})).status_code == 200
            counts.append(len([s for s in statements if s.lstrip().upper().startswith("SELECT")]))
        assert counts[0] == counts[1]
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)


@pytest.mark.asyncio
async def test_thirteen_hundred_universities_search_within_budget(db_session):
    """SR15: 1,300 universities x 3 courses, written in a transaction that is rolled back, searched in under 2 s."""
    actor = await make_user(db_session, "super_admin", "global")
    t = tag()
    jp, gb = await country(db_session, "JP"), await country(db_session, "GB")
    try:
        unis = [
            {"id": uuid.uuid4(), "country_id": (jp if i % 2 else gb).id, "slug": f"perf-{t}-{i}".lower(), "name": f"Perf {i} {t}", "name_key": f"perf {i} {t}".lower(), "city": "City",
             "overview": "", "eligibility": "", "requirements": [], "deadlines": [], "scholarships": [], "catalogue_visible": False,
             "stage": ("target_university", "interested", "active_partner")[i % 3]}
            for i in range(1300)
        ]  # fmt: skip
        await db_session.execute(insert(University), unis)
        courses = [
            {"id": uuid.uuid4(), "university_id": u["id"], "title": ("MSc Cyber Security", "MBA", "BSc Computing")[k], "category": ("Computer Science", "Business", "IT")[k],
             "level": ("PG", "PG", "UG")[k], "duration": "1 year", "tuition_fee": "", "intake": "", "intakes": ["Sep"], "scholarship_ids": []}
            for u in unis for k in range(3)
        ]  # fmt: skip
        await db_session.execute(insert(OverseasCourse), courses)
        query = UniversitySearchQuery(q=t, country="Japan", course="Cyber Security", partner_status="not_partnered")
        await university_search.search(db_session, actor, query)  # warm: the rows were just written
        started = time.perf_counter()
        result = await university_search.search(db_session, actor, query)
        elapsed = time.perf_counter() - started
        assert result["total"] == 434 and len(result["items"]) == 50  # odd i (Japan) whose i % 3 != 2
        assert elapsed < 2.0, f"search took {elapsed:.2f}s"
    finally:
        await db_session.rollback()
