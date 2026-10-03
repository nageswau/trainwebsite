"""AGN-020 (DEC-SCOPE-063) -- agency reports: filters, intake folding, report values against hand counts, parity with the AGN-018
dashboard, paging and options (spec §4, §5, §8)."""

from datetime import date

import pytest
import pytest_asyncio

from app.services.agent_reports import PAGE_SIZE, REPORT_KINDS, ReportInputError, intake_key, parse_filters, parse_page
from tests.agn020_helpers import load_user, reports_world


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
