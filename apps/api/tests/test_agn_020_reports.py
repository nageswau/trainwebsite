"""AGN-020 (DEC-SCOPE-063) -- agency reports: filters, intake folding, report values against hand counts, parity with the AGN-018
dashboard, paging and options (spec §4, §5, §8)."""

from datetime import date

import pytest
import pytest_asyncio

from app.models import Country
from app.services.agent_reports import PAGE_SIZE, REPORT_KINDS, ReportInputError, intake_key, parse_filters, parse_page
from tests.agn001_helpers import client_for
from tests.agn018_helpers import DASHBOARD_API
from tests.agn020_helpers import (
    MASTER_COUNTRIES,
    MASTER_INTAKES,
    MASTER_STAFF,
    MASTER_TOTAL,
    REPORTS,
    S1_COUNTRIES,
    S1_TOTAL,
    STAGES,
    counts,
    load_user,
    reports_world,
)


@pytest_asyncio.fixture
async def world(db_session):
    return await reports_world(db_session)


# --- Task 1: kinds, filters, intake folding ---


def test_seven_kinds_and_staff_is_master_only():
    assert set(REPORT_KINDS) == {"students", "applications", "enrollments", "universities", "countries", "intakes", "staff"}
    assert [k for k, v in REPORT_KINDS.items() if v.master_only] == ["staff"]
    assert {k for k, v in REPORT_KINDS.items() if v.summary} == {"universities", "countries", "intakes", "staff"}


@pytest.mark.parametrize(
    ("text", "key", "label"),
    [
        ("Sep 2027", "2027-09", "Sep 2027"),
        ("September 2027", "2027-09", "Sep 2027"),
        ("09/2027", "2027-09", "Sep 2027"),
        ("2027-09", "2027-09", "Sep 2027"),
        ("Next intake", "unstructured", "Unstructured"),
        ("Fall 2027", "unstructured", "Unstructured"),
        (None, "unstructured", "Unstructured"),
    ],
)
def test_intake_key_folds_spellings(text, key, label):
    assert intake_key(text) == (key, label)


@pytest.mark.parametrize(
    ("limit", "offset", "expected"),
    [(None, None, (PAGE_SIZE, 0)), ("1", "0", (1, 0)), ("100", "9950", (100, 9950)), ("", "", (PAGE_SIZE, 0))],
)
def test_parse_page_defaults_and_bounds(limit, offset, expected):
    assert parse_page(limit, offset) == expected


@pytest.mark.parametrize(("limit", "offset", "param"), [("0", None, "limit"), ("101", None, "limit"), ("x", None, "limit"), (None, "-1", "offset"), (None, "9951", "offset")])
def test_parse_page_rejects_out_of_range(limit, offset, param):
    with pytest.raises(ReportInputError) as raised:
        parse_page(limit, offset)
    assert raised.value.param == param


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kind", "raw", "param", "message"),
    [
        ("countries", {"university": "x"}, "university", "This filter is not available for this report"),
        ("staff", {"member": "x"}, "member", "This filter is not available for this report"),
        ("applications", {"intake": "2027-13"}, "intake", "Intake must be YYYY-MM or unstructured"),
        ("applications", {"status": "nope"}, "status", "Unknown status"),
        ("students", {"status": "enquiry"}, "status", "Unknown status"),
        ("applications", {"country": "no-such-slug"}, "country", "Unknown country"),
        ("applications", {"university": "no-such-slug"}, "university", "Unknown university"),
        ("applications", {"member": "ZZZ-S999"}, "member", "Unknown staff member"),
        ("applications", {"date_from": "20260101"}, "date_from", "date_from must be a date (YYYY-MM-DD)"),
        ("applications", {"date_from": "2026-02-30"}, "date_from", "date_from must be a date (YYYY-MM-DD)"),
        ("applications", {"date_from": "2026-02-02", "date_to": "2026-02-01"}, "date_to", "date_to must be on or after date_from"),
        ("applications", {"date_to": "9999-12-31"}, "date_to", "date_to must be before 9999-12-31"),
        ("applications", {"member": "x" * 121}, "member", "Too long"),
    ],
)
async def test_bad_filters_name_their_param(world, db_session, kind, raw, param, message):
    master = await load_user(db_session, world["master"].id)
    with pytest.raises(ReportInputError) as raised:
        await parse_filters(db_session, master, kind, raw)
    assert (raised.value.param, raised.value.message) == (param, message)


@pytest.mark.asyncio
async def test_another_agencys_member_code_is_just_unknown(world, db_session):
    """No cross-tenant oracle: a real code from another agency gets the unknown-code text."""
    master = await load_user(db_session, world["master"].id)
    with pytest.raises(ReportInputError) as raised:
        await parse_filters(db_session, master, "applications", {"member": world["noise_staff"]["member"].code})
    assert raised.value.message == "Unknown staff member"


@pytest.mark.asyncio
async def test_staff_cannot_send_the_member_filter(world, db_session):
    s1 = await load_user(db_session, world["s1"]["user"].id)
    with pytest.raises(ReportInputError) as raised:
        await parse_filters(db_session, s1, "applications", {"member": world["s1"]["member"].code})
    assert (raised.value.param, raised.value.message) == ("member", "This filter is not available for this report")


@pytest.mark.asyncio
async def test_good_filters_resolve(world, db_session):
    master = await load_user(db_session, world["master"].id)
    f = await parse_filters(
        db_session, master, "applications",
        {"date_from": "2026-01-01", "date_to": "2026-12-31", "member": world["s1"]["member"].code, "country": None,
         "university": world["u2"].slug, "intake": "2027-09", "status": "withdrawn"},
    )
    assert (f.start, f.end) == (date(2026, 1, 1), date(2026, 12, 31))
    assert f.member == world["s1"]["member"].id and f.university_id == world["u2"].id and f.status == "withdrawn"
    assert sorted(f.intake_texts) == ["09/2027", "2027-09", "Sep 2027", "September 2027"]  # every spelling of 2027-09 in scope
    assert f.echo == {"date_from": "2026-01-01", "date_to": "2026-12-31", "member": world["s1"]["member"].code, "university": world["u2"].slug, "intake": "2027-09", "status": "withdrawn"}


@pytest.mark.asyncio
async def test_unassigned_and_student_country_text(world, db_session):
    master = await load_user(db_session, world["master"].id)
    f = await parse_filters(db_session, master, "students", {"member": "unassigned", "country": "  ALAND ", "status": "all"})
    assert f.member == "unassigned" and f.student_country == "aland" and f.status == "all"


# --- Task 3: summary reports (spec §4.3, AC1, AC2, AC5) ---


async def _report(email, kind, **params):
    async with client_for(email) as c:
        response = await c.get(f"{REPORTS}/{kind}", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def _rows(body, key):
    return [(item[key], {k: item[k] for k in STAGES}) for item in body["items"]]


def _total(body):
    return {k: body["totals"][k] for k in STAGES}


@pytest.mark.asyncio
async def test_countries_equal_hand_counts(world):
    body = await _report(world["master"].email, "countries")
    assert [c["label"] for c in body["columns"]] == ["Country", "Applications", "Submitted", "Offers", "Visa apps", "Visa approved", "Enrolled"]
    assert _rows(body, "country") == MASTER_COUNTRIES
    assert _total(body) == MASTER_TOTAL and body["totals"]["country"] == "Total"
    assert body["total"] == 2 and body["offset"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("who", "expected"), [("master", MASTER_TOTAL), ("s1", S1_TOTAL)])
async def test_totals_agree_with_the_agn018_dashboard(world, who, expected):
    """AC2: the same scope, the same definitions -- the report total equals the dashboard's headline counts."""
    email = world["master"].email if who == "master" else world[who]["user"].email
    body = await _report(email, "countries")
    async with client_for(email) as c:
        dash = (await c.get(DASHBOARD_API)).json()
    shared = ("applications", "offers", "visa_applications", "visa_approvals", "enrollments")
    assert _total(body) == expected
    assert {k: dash[k] for k in shared} == {k: expected[k] for k in shared}


@pytest.mark.asyncio
async def test_staff_see_only_their_own_students(world):
    body = await _report(world["s1"]["user"].email, "countries")
    assert body["scope"] == "own" and _rows(body, "country") == S1_COUNTRIES


@pytest.mark.asyncio
async def test_universities_carry_their_country(world):
    body = await _report(world["master"].email, "universities")
    assert [(i["university"], i["country"]) for i in body["items"]] == [("Alpha University", "Aland"), ("Beta University", "Betaland")]
    assert [{k: i[k] for k in STAGES} for i in body["items"]] == [c for _, c in MASTER_COUNTRIES]


@pytest.mark.asyncio
async def test_intakes_fold_spellings_and_put_unstructured_last(world):
    body = await _report(world["master"].email, "intakes")
    assert _rows(body, "intake") == MASTER_INTAKES and _total(body) == MASTER_TOTAL


@pytest.mark.asyncio
async def test_staff_performance_per_member_and_unassigned(world):
    body = await _report(world["master"].email, "staff")
    assert [c["key"] for c in body["columns"]][:2] == ["member", "students"]
    rows = [(i["member"] if i["member"] == "Unassigned" else i["member"].split(" ", 1)[1], i["students"], {k: i[k] for k in STAGES}) for i in body["items"]]
    assert rows == MASTER_STAFF
    assert body["items"][0]["member"] == f"{world['s1']['member'].code} Staff One"
    assert body["totals"]["students"] == 4 and _total(body) == MASTER_TOTAL


@pytest.mark.asyncio
async def test_date_bounds_are_inclusive_utc_days(world):
    """a1 was created at 23:30 UTC on 31 January: in a range ending that day, out of one starting the next."""
    only_a1 = await _report(world["master"].email, "countries", date_to="2026-01-31")
    assert _rows(only_a1, "country") == [("Aland", counts(1, 0, 0, 0, 0, 0))]
    without_a1 = await _report(world["master"].email, "countries", date_from="2026-02-01")
    assert _total(without_a1)["applications"] == MASTER_TOTAL["applications"] - 1


@pytest.mark.asyncio
async def test_member_filter_narrows_to_one_assignee(world):
    s2 = await _report(world["master"].email, "countries", member=world["s2"]["member"].code)
    assert _total(s2) == counts(1, 0, 2, 1, 0, 0)
    unassigned = await _report(world["master"].email, "intakes", member="unassigned")
    assert _total(unassigned) == counts(2, 0, 2, 0, 0, 1)


@pytest.mark.asyncio
async def test_country_filter_on_a_summary(world, db_session):
    slug = (await db_session.get(Country, world["u2"].country_id)).slug
    body = await _report(world["master"].email, "universities", country=slug)
    assert [i["university"] for i in body["items"]] == ["Beta University"]
