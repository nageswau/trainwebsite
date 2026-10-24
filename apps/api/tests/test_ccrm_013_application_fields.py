"""ccrm-013 (DEC-SCOPE-256, F1-F9) -- an application's university-side fields and its counselor-editable dates: the details route's
scope (counselor of the application, direct and agency; Overseas Admin), the field rules, the audit diff, the CC5 notices, and the reads
(the student's page, the agency detail). Agency world: tests/agn023_helpers.py."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.application_fields import CURRENCIES, SCHOLARSHIP_STATUSES
from app.models import AuditLog
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS
from tests.agn023_helpers import ASSIGN, PORTAL, UPDATE, assign_world, fresh, notices

DETAILS = "/api/v1/workflows/overseas/applications/{}/details"

FULL = {
    "faculty": "Faculty of Engineering",
    "campus": "Main campus",
    "course_start_date": "2027-09-20",
    "university_portal_url": "https://apply.example.ac.uk/portal",
    "university_contact_name": "Admissions Office",
    "university_contact_email": "admissions@example.ac.uk",
    "tuition_fee": "18500.00",
    "currency": "GBP",
    "scholarship_status": "awarded",
    "scholarship_amount": "2000.00",
    "documents_completed_on": "2026-10-01",
    "decision_due_on": "2026-12-15",
    "submitted_on": "2026-10-10",
    "application_deadline": "2026-11-30",
    "offer_deadline": "2027-01-31",
}


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="university_selection")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


def _money(value) -> str:
    return f"{float(value):.2f}"


def test_the_lists_are_the_recommended_defaults():  # F1, F3
    assert CURRENCIES == ("INR", "GBP", "USD", "EUR", "CAD", "AUD", "NZD", "SGD", "AED")
    assert SCHOLARSHIP_STATUSES == ("none", "applied", "awarded", "declined")


@pytest.mark.asyncio
async def test_every_field_round_trips_and_null_clears(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(DETAILS.format(app.id), json=FULL)
        assert r.status_code == 200, r.text
        assert r.json()["changed"] is True
        got = (await c.get(DETAILS.format(app.id))).json()
    for key, value in FULL.items():
        assert (_money(got[key]) if key in {"tuition_fee", "scholarship_amount"} else got[key]) == value, key
    assert got["scholarship_label"] == "Awarded" and got["application_code"].startswith("APP-")
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(DETAILS.format(app.id), json={"faculty": None, "tuition_fee": None, "scholarship_status": "applied"})
        assert r.status_code == 200, r.text
    item = await fresh(db_session, app)
    assert item.faculty is None and item.tuition_fee is None
    assert item.scholarship_status == "applied" and item.scholarship_amount is None  # F3: leaving awarded clears the amount
    assert item.campus == "Main campus" and item.submitted_on == date(2026, 10, 10)  # omitted = unchanged


@pytest.mark.asyncio
async def test_the_same_values_twice_change_nothing(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.patch(DETAILS.format(app.id), json={"faculty": "Law"})).json()["changed"] is True
        assert (await c.patch(DETAILS.format(app.id), json={"faculty": "Law"})).json()["changed"] is False
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.details"))).all()
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_the_counselor_edits_an_agency_application_and_the_agency_is_told(db_session, world):  # CC4, CC5
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(DETAILS.format(app.id), json={"application_deadline": "2026-12-01", "faculty": "Business"})
        assert r.status_code == 200, r.text
        # the generic PATCH still refuses a counselor on an agency application (AGN-023 H4)
        assert (await c.patch(UPDATE.format(app.id), json={"next_action": "x"})).status_code == 403
    assert (await fresh(db_session, app)).application_deadline == date(2026, 12, 1)
    titles = [n.title for n in await notices(db_session, world["staff"]["user"])]  # AGN-017 recipients: the assigned staff member
    assert "Application details updated" in titles
    async with client_for(world["master"].email) as c:
        detail = (await c.get(f"{APPS}/{app.id}")).json()["application"]
    assert detail["faculty"] == "Business" and detail["scholarship_status"] is None  # F9: the agency reads them


@pytest.mark.asyncio
async def test_the_audit_keeps_before_and_after_with_the_author(db_session, world):  # F8
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        await c.patch(DETAILS.format(app.id), json={"campus": "North"})
        await c.patch(DETAILS.format(app.id), json={"campus": "South", "tuition_fee": "100", "currency": "INR"})
    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.details").order_by(AuditLog.created_at))).all()
    assert rows[-1].user_id == world["counselor"].id
    assert rows[-1].metadata_json["campus"] == {"from": "North", "to": "South"}
    assert rows[-1].metadata_json["currency"] == {"from": None, "to": "INR"}


@pytest.mark.asyncio
async def test_scope_other_counselor_agent_and_student_are_refused(db_session, world):
    app = world["direct_app"]
    for email in (world["counselor2"].email, world["master"].email, world["direct_student"].email):
        async with client_for(email) as c:
            assert (await c.patch(DETAILS.format(app.id), json={"faculty": "X"})).status_code == 403, email
            assert (await c.get(DETAILS.format(app.id))).status_code == 403, email
    async with client_for(world["admin"].email) as c:
        assert (await c.patch(DETAILS.format(app.id), json={"faculty": "Admin set"})).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "needle"),
    [
        ({"tuition_fee": "100"}, "Currency is required"),
        ({"scholarship_status": "applied", "scholarship_amount": "50", "currency": "GBP"}, "only when the scholarship is awarded"),
        ({"currency": "JPY"}, "currency"),
        ({"scholarship_status": "maybe"}, "scholarship_status"),
        ({"tuition_fee": "-1", "currency": "GBP"}, "tuition_fee"),
        ({"submitted_on": (date.today() + timedelta(days=5)).isoformat()}, "future"),
        ({"documents_completed_on": (date.today() + timedelta(days=5)).isoformat()}, "future"),
        ({"decision_due_on": "0202-01-01"}, "between 2000 and 2100"),
        ({"university_portal_url": "https://user:secret@portal.example.com"}, "credentials"),
        ({"university_portal_url": "javascript:alert(1)"}, "http"),
        ({"university_contact_email": "not-an-email"}, "university_contact_email"),
        ({"intake": "Sep"}, "extra"),
    ],
)
async def test_field_rules(db_session, world, body, needle):
    async with client_for(world["counselor"].email) as c:
        r = await c.patch(DETAILS.format(world["direct_app"].id), json=body)
    assert r.status_code == 422, r.text
    assert needle.lower() in r.text.lower()


@pytest.mark.asyncio
async def test_a_fee_already_set_keeps_its_currency(db_session, world):  # F4 on the merged row, not just the payload
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.patch(DETAILS.format(app.id), json={"tuition_fee": "100", "currency": "USD"})).status_code == 200
        r = await c.patch(DETAILS.format(app.id), json={"currency": None})
        assert r.status_code == 422 and "Currency is required" in r.text
        assert (await c.patch(DETAILS.format(app.id), json={"tuition_fee": None, "currency": None})).status_code == 200


@pytest.mark.asyncio
async def test_the_student_sees_the_scholarship_and_is_told_only_when_it_changes(db_session, world):  # nehn-037 AC2, F8, F9
    app, student = world["direct_app"], world["direct_student"]
    async with client_for(world["counselor"].email) as c:
        await c.patch(DETAILS.format(app.id), json={"faculty": "Arts"})
    assert not [n for n in await notices(db_session, student) if n.title == "Scholarship update"]
    async with client_for(world["counselor"].email) as c:
        await c.patch(DETAILS.format(app.id), json={"scholarship_status": "awarded", "scholarship_amount": "1500", "currency": "GBP", "course_start_date": "2027-09-01"})
    assert [n for n in await notices(db_session, student) if n.title == "Scholarship update"]
    async with client_for(student.email) as c:
        page = (await c.get(PORTAL.format("student", "applications"))).json()
    row = next(r for r in page["rows"] if r["id"] == str(app.id))
    assert row["scholarship"] == "Awarded — GBP 1,500.00" and row["course_start_date"] == "2027-09-01"
    assert "university_portal_url" not in row and "tuition_fee" not in row  # F9: staff/agency-side only


@pytest.mark.asyncio
async def test_the_agency_form_still_takes_a_submission_date(db_session, world):
    """Regression pin: ccrm-007's two-argument `_not_future` once shadowed AGN-008's, so the agency date validators raised a TypeError (500)."""
    async with client_for(world["master"].email) as c:
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"submitted_on": date.today().isoformat()})
        assert r.status_code == 200, r.text
        r = await c.patch(f"{APPS}/{world['app'].id}", json={"submitted_on": (date.today() + timedelta(days=5)).isoformat()})
        assert r.status_code == 422 and "Submission date cannot be in the future" in r.text


@pytest.mark.asyncio
async def test_an_unknown_application_is_404(db_session, world):
    async with client_for(world["counselor"].email) as c:
        assert (await c.get(DETAILS.format("00000000-0000-0000-0000-000000000000"))).status_code == 404
