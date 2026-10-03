"""AGN-020 (DEC-SCOPE-063) -- agency reports: filters, intake folding, report values against hand counts, parity with the AGN-018
dashboard, paging and options (spec §4, §5, §8)."""

import re
from datetime import date

import pytest
import pytest_asyncio

from app.models import Country
from app.services.agent_reports import PAGE_SIZE, REPORT_KINDS, ReportInputError, intake_key, parse_filters, parse_page
from tests.agn001_helpers import client_for
from tests.agn008_helpers import mk_application
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


# --- Task 4: list reports and paging (spec §4.2, AC1, AC5, AC6, AC11) ---

UUID_TEXT = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _names(world, *keys):
    records = world["records"]
    return [world["login"].full_name if key == "r2" else records[key].full_name for key in keys]


@pytest.mark.asyncio
async def test_students_default_to_active_newest_first(world):
    body = await _report(world["master"].email, "students")
    assert [c["label"] for c in body["columns"]] == ["Name", "Assigned staff", "Preferred country", "Preferred intake", "Status", "Created", "Applications"]
    assert [i["name"] for i in body["items"]] == _names(world, "r5", "r3", "r2", "r1")
    r1, r5 = body["items"][3], body["items"][0]
    assert r1 | {"created": None} == {"name": _names(world, "r1")[0], "assigned_staff": f"{world['s1']['member'].code} Staff One", "preferred_country": "Aland", "preferred_intake": "Sep 2027", "status": "Active", "created": None, "applications": 2}
    assert (r5["assigned_staff"], r5["applications"]) == ("Unassigned", 2)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r1["created"])
    assert body["totals"] is None and body["total"] == 4 and body["limit"] == PAGE_SIZE


@pytest.mark.asyncio
async def test_students_status_and_country_filters(world):
    assert (await _report(world["master"].email, "students", status="all"))["total"] == 5
    archived = await _report(world["master"].email, "students", status="archived")
    assert [i["name"] for i in archived["items"]] == _names(world, "r4") and archived["items"][0]["status"] == "Archived"
    by_text = await _report(world["master"].email, "students", country="  ALAND ")
    assert [i["name"] for i in by_text["items"]] == _names(world, "r1")


@pytest.mark.asyncio
async def test_staff_list_only_their_assigned_students(world):
    body = await _report(world["s1"]["user"].email, "students")
    assert [i["name"] for i in body["items"]] == _names(world, "r2", "r1")


@pytest.mark.asyncio
async def test_applications_list_every_application_with_labels(world):
    body = await _report(world["master"].email, "applications", limit="100")
    assert [c["label"] for c in body["columns"]] == ["Student", "University", "Country", "Course", "Intake", "Application ref", "Stage", "Submitted", "Offer", "Visa", "Created"]
    assert body["total"] == 10  # withdrawn included; the School-bridged row and the noise agency are not
    by = {(i["student"], i["intake"], i["stage"]): i for i in body["items"]}
    r1, r2, r3 = _names(world, "r1", "r2", "r3")
    assert by[(r3, "Next intake", "Withdrawn")] | {"created": None} == {
        "student": r3, "university": "Alpha University", "country": "Aland", "course": None, "intake": "Next intake", "application_ref": None,
        "stage": "Withdrawn", "submitted": None, "offer": "Yes", "visa": "Refused", "created": None,
    }
    assert (by[(r2, "09/2027", "Visa documentation")]["visa"], by[(r2, "09/2027", "Visa documentation")]["submitted"]) == ("Approved", "2026-07-01")
    assert (by[(r1, "Sep 2027", "Enquiry")]["offer"], by[(r1, "Sep 2027", "Enquiry")]["visa"]) == ("No", "None")


@pytest.mark.asyncio
@pytest.mark.parametrize(("params", "total"), [({"intake": "unstructured"}, 3), ({"intake": "2027-09"}, 5), ({"status": "withdrawn"}, 2)])
async def test_applications_filters(world, params, total):
    assert (await _report(world["master"].email, "applications", **params))["total"] == total


@pytest.mark.asyncio
async def test_enrollments_by_enrollment_date(world):
    body = await _report(world["master"].email, "enrollments")
    assert [c["label"] for c in body["columns"]] == ["Student", "University", "Country", "Course", "Intake", "Enrollment date", "University student ID"]
    assert [(i["student"], i["enrollment_date"], i["university_student_id"]) for i in body["items"]] == [(_names(world, "r2")[0], "2027-09-15", "UNI-4"), (_names(world, "r5")[0], None, None)]
    dated = await _report(world["master"].email, "enrollments", date_from="2027-09-01", date_to="2027-09-30")
    assert dated["total"] == 1  # the undated legacy enrollment only shows without a date filter


@pytest.mark.asyncio
@pytest.mark.parametrize(("kind", "who", "total"), [("applications", "s1", 6), ("applications", "unassigned", 2), ("enrollments", "s1", 1), ("enrollments", "unassigned", 1)])
async def test_member_filter_on_the_lists(world, kind, who, total):
    """Final review C1: the lists join agency records (with_owner), so the assignee subqueries must not be correlated away.
    s1: a1 a2 a3 a4 a7 a10 (enrolled a4); unassigned: a8 a9 (enrolled a9)."""
    member = "unassigned" if who == "unassigned" else world[who]["member"].code
    assert (await _report(world["master"].email, kind, member=member))["total"] == total
    async with client_for(world["master"].email) as c:
        response = await c.get(f"{REPORTS}/{kind}.csv", params={"member": member})
    assert response.status_code == 200 and len(response.text.strip().splitlines()) == total + 1


@pytest.mark.asyncio
async def test_a_login_only_application_counts_for_the_logins_assignee(world, db_session):
    """Review Focus 2: an application made before AGN-008 (login only, no agency record) counts for the assignee of the agency's
    record for that login -- r2's, so s1 -- on the lists and the staff summary alike."""
    await mk_application(db_session, agent=world["master"], university=world["u2"], student=world["login"], status="enquiry", intake="Sep 2027")
    listed = await _report(world["master"].email, "applications", member=world["s1"]["member"].code)
    assert listed["total"] == 7
    staff = await _report(world["master"].email, "staff")
    assert staff["items"][0]["applications"] == MASTER_STAFF[0][2]["applications"] + 1


@pytest.mark.asyncio
async def test_paging_keeps_the_total_and_an_empty_page_past_the_end(world):
    first = await _report(world["master"].email, "students", limit="2")
    second = await _report(world["master"].email, "students", limit="2", offset="2")
    past = await _report(world["master"].email, "students", limit="2", offset="10")
    assert [i["name"] for i in first["items"] + second["items"]] == _names(world, "r5", "r3", "r2", "r1")
    assert (first["total"], second["total"], past["total"], past["items"]) == (4, 4, 4, [])
    assert (second["limit"], second["offset"]) == (2, 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["students", "applications", "enrollments", "staff"])
async def test_no_ids_or_contact_details_leave_the_api(world, db_session, kind):
    """AC11: no UUIDs, emails or phone numbers in a report."""
    async with client_for(world["master"].email) as c:
        text = (await c.get(f"{REPORTS}/{kind}")).text
    assert not UUID_TEXT.search(text) and "@example.local" not in text


# --- Task 5: filter options from the caller's scope (spec §5.2, §7.1) ---


def _values(options, key):
    return [(o["value"], o["label"]) for o in options[key]]


@pytest.mark.asyncio
async def test_master_options_cover_the_agency_only(world, db_session):
    body = await _report(world["master"].email, "applications")
    options = body["options"]
    assert set(options) == {"members", "countries", "universities", "intakes", "statuses"}
    codes = [world[s]["member"].code for s in ("s1", "s2", "s3")]
    assert _values(options, "members") == [(codes[0], f"{codes[0]} Staff One"), (codes[1], f"{codes[1]} Staff Two"), (codes[2], f"{codes[2]} Staff Three"), ("unassigned", "Unassigned")]
    aland = (await db_session.get(Country, world["u1"].country_id)).slug
    betaland = (await db_session.get(Country, world["u2"].country_id)).slug
    assert _values(options, "countries") == [(aland, "Aland"), (betaland, "Betaland")]  # the noise agency's Gammaland is not offered
    assert _values(options, "universities") == [(world["u1"].slug, "Alpha University"), (world["u2"].slug, "Beta University")]
    assert _values(options, "intakes") == [("2027-09", "Sep 2027"), ("2028-01", "Jan 2028"), ("unstructured", "Unstructured")]
    assert ("withdrawn", "Withdrawn") in _values(options, "statuses") and ("enquiry", "Enquiry") in _values(options, "statuses")


@pytest.mark.asyncio
async def test_options_follow_the_kinds_filters(world):
    assert set((await _report(world["master"].email, "countries"))["options"]) == {"members"}
    assert (await _report(world["master"].email, "staff"))["options"] == {}
    students = (await _report(world["master"].email, "students"))["options"]
    assert _values(students, "countries") == [("Aland", "Aland")]  # the records' own preferred-country text
    assert _values(students, "statuses") == [("active", "Active"), ("archived", "Archived"), ("all", "All")]


@pytest.mark.asyncio
async def test_staff_options_reveal_only_their_scope(world):
    options = (await _report(world["s2"]["user"].email, "applications"))["options"]
    assert "members" not in options
    assert [label for _, label in _values(options, "countries")] == ["Aland"]  # s2's students applied in Aland only
    assert [label for _, label in _values(options, "intakes")] == ["Jan 2028", "Unstructured"]
