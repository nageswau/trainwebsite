"""ccrm-015 (DEC-SCOPE-244, O1-O4) -- an application's exception outcome: per-application (AC 9), per-outcome fields, terminal and on-hold
guards, resume / reopen, the agency withdraw, re-application (O3), notices (CC5) and the reads. Agency world: tests/agn023_helpers.py."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.application_outcome import OUTCOMES, TERMINAL, label
from app.models import ApplicationOutcome, StudentDocument
from tests.agn001_helpers import client_for
from tests.agn003_helpers import mk_university
from tests.agn008_helpers import APPS, mk_application
from tests.agn023_helpers import ADVANCE, ASSIGN, PORTAL, UPDATE, assign_world, fresh, history_notes, notices

OUTCOME = "/api/v1/workflows/overseas/applications/{}/outcome"
REOPEN = OUTCOME + "/reopen"
SUB = "/api/v1/workflows/overseas/applications/{}/sub-status"
STATUS = "/api/v1/workflows/overseas/applications/{}/status"
CREATE = "/api/v1/workflows/overseas/applications"
AGENT_STATUS = APPS + "/{}/status"
TODAY = date.today()


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="university_selection")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


async def _events(db, app) -> list[ApplicationOutcome]:
    stmt = select(ApplicationOutcome).where(ApplicationOutcome.application_id == app.id).order_by(ApplicationOutcome.created_at)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


def test_the_values_are_the_owner_list():  # O2, O4
    # ccrm-027 (DEC-SCOPE-262, E6) adds non_arrival and cancelled, both terminal
    assert OUTCOMES == ("rejected", "withdrawn", "deferred", "on_hold", "offer_declined", "visa_refused", "non_arrival", "cancelled")
    assert {"rejected", "withdrawn", "offer_declined", "visa_refused", "non_arrival", "cancelled"} == TERMINAL
    assert label("offer_declined") == "Offer declined" and label(None) is None


@pytest.mark.asyncio
async def test_rejecting_university_c_leaves_a_and_b_unchanged(db_session, world):  # AC 9, Appendix B
    student, counselor = world["direct_student"], world["counselor"]
    a, b = world["direct_app"], await mk_application(db_session, agent=None, university=await mk_university(db_session), student=student, status="offer", counselor_id=counselor.id)
    c_app = await mk_application(db_session, agent=None, university=await mk_university(db_session), student=student, status="university_selection", counselor_id=counselor.id)
    async with client_for(counselor.email) as c:
        r = await c.post(OUTCOME.format(c_app.id), json={"outcome": "rejected", "reason": "Grades below the cut-off", "next_steps": "Apply for the foundation year"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["status"], body["outcome"]) == ("university_selection", "rejected")
    assert body["detail"]["reason"] == "Grades below the cut-off" and body["detail"]["terminal"] is True
    assert body["detail"]["outcome_date"] == TODAY.isoformat()
    for other in (a, b):
        assert (await fresh(db_session, other)).outcome is None
    assert (await history_notes(db_session, c_app))[-1] == "Outcome: Rejected -- Grades below the cut-off"
    assert any("Rejected" in n.body for n in await notices(db_session, student))


@pytest.mark.asyncio
async def test_each_outcome_requires_its_fields(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        for body in (
            {"outcome": "rejected"},
            {"outcome": "withdrawn", "reason": "Changed plans"},  # who requested
            {"outcome": "deferred"},
            {"outcome": "on_hold", "reason": "Awaiting funds"},  # review date (AC)
            {"outcome": "offer_declined"},
            {"outcome": "visa_refused", "reason": "x"},  # O4: ccrm-026 writes it
            {"outcome": "waitlisted", "reason": "x"},  # O4: no waitlist
            {"outcome": "rejected", "reason": "x", "outcome_date": (TODAY + timedelta(days=1)).isoformat()},
        ):
            assert (await c.post(OUTCOME.format(app.id), json=body)).status_code == 422, body
        past = {"outcome": "on_hold", "reason": "Awaiting funds", "review_date": (TODAY - timedelta(days=1)).isoformat()}
        r = await c.post(OUTCOME.format(app.id), json=past)
        assert r.status_code == 422 and r.json()["detail"] == "The review date cannot be in the past"
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "offer_declined", "reason": "Prefers another"})
        assert r.status_code == 422 and r.json()["detail"] == "An offer is needed before it can be declined"
    assert await _events(db_session, app) == []


@pytest.mark.asyncio
async def test_a_terminal_outcome_closes_every_stage_write_until_the_admin_reopens(db_session, world):  # O2
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "No place"})).status_code == 200
        closed = "This application is rejected -- only the Overseas Admin can reopen it"
        for url, body in (
            (ADVANCE.format(app.id), {"to_status": "offer"}),
            (SUB.format(app.id), {"sub_status": "submitted"}),
            (OUTCOME.format(app.id), {"outcome": "deferred", "new_intake": "Jan 2028"}),
        ):
            r = await c.post(url, json=body)
            assert r.status_code == 409 and r.json()["detail"] == closed, url
        r = await c.post(REOPEN.format(app.id), json={"reason": "Appeal upheld"})
        assert r.status_code == 403 and r.json()["detail"] == "Only the Overseas Admin can reopen a closed application"
    async with client_for(world["admin"].email) as c:
        assert (await c.patch(UPDATE.format(app.id), json={"status": "offer"})).status_code == 409
        assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(world["counselor2"].id)})).status_code == 409
        assert (await c.post(REOPEN.format(app.id), json={"reason": " "})).status_code == 422
        r = await c.post(REOPEN.format(app.id), json={"reason": "Appeal upheld"})
        assert r.status_code == 200 and r.json()["outcome"] is None
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(ADVANCE.format(app.id), json={"to_status": "offer"})).status_code == 200
    assert [e.outcome for e in await _events(db_session, app)] == ["rejected", "cleared"]
    assert "Reopened (Rejected) -- Appeal upheld" in await history_notes(db_session, app)


@pytest.mark.asyncio
async def test_on_hold_pauses_moves_and_the_counselor_resumes(db_session, world):
    app = world["direct_app"]
    review = (TODAY + timedelta(days=14)).isoformat()
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "on_hold", "reason": "Awaiting funds", "review_date": review, "hold_owner_id": str(world["it_counselor"].id)})
        assert r.status_code == 422 and r.json()["detail"] == "Choose an active overseas counselor or admin as the hold owner"
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "on_hold", "reason": "Awaiting funds", "review_date": review})
        assert r.status_code == 200 and r.json()["detail"]["review_date"] == review
        r = await c.post(SUB.format(app.id), json={"sub_status": "submitted"})
        assert r.status_code == 409 and "on hold" in r.json()["detail"]
        assert (await c.post(ADVANCE.format(app.id), json={"to_status": "offer"})).status_code == 409
        r = await c.post(REOPEN.format(app.id), json={"reason": "Funds arrived"})
        assert r.status_code == 200 and r.json()["outcome"] is None
        assert (await c.post(SUB.format(app.id), json={"sub_status": "submitted"})).status_code == 200
        r = await c.post(REOPEN.format(app.id), json={"reason": "again"})
        assert r.status_code == 409 and r.json()["detail"] == "This application has no outcome to clear"
    events = await _events(db_session, app)
    assert events[0].hold_owner_id == world["counselor"].id and events[0].review_date == TODAY + timedelta(days=14)


@pytest.mark.asyncio
async def test_deferral_moves_the_intake_and_the_application_continues(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "deferred", "new_intake": "January 2028", "application_deadline": "2027-09-30"})
        assert r.status_code == 200, r.text
        assert (await c.post(SUB.format(app.id), json={"sub_status": "submitted"})).status_code == 200
    item = await fresh(db_session, app)
    assert (item.intake, item.application_deadline, item.outcome) == ("January 2028", date(2027, 9, 30), "deferred")
    assert (await _events(db_session, app))[0].previous_intake == "Fall 2027"


@pytest.mark.asyncio
async def test_counselor_withdrawal_sets_status_and_the_admin_reopen_restores_the_stage(db_session, world):  # O1
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(SUB.format(app.id), json={"sub_status": "submitted"})).status_code == 200
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "withdrawn", "reason": "Chose a UK offer", "requested_by": "student"})
        assert r.status_code == 200 and (r.json()["status"], r.json()["outcome"]) == ("withdrawn", "withdrawn")
        assert r.json()["detail"]["requested_by"] == "student"
    async with client_for(world["admin"].email) as c:
        r = await c.post(REOPEN.format(app.id), json={"reason": "Student changed their mind"})
    assert r.status_code == 200
    item = await fresh(db_session, app)
    assert (item.status, item.sub_status, item.outcome) == ("university_selection", "submitted", None)


@pytest.mark.asyncio
async def test_an_offer_can_be_declined_and_enrolled_is_refused(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(ADVANCE.format(app.id), json={"to_status": "offer"})).status_code == 200
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "offer_declined", "reason": "Prefers B", "another_offer_preferred": True})
        assert r.status_code == 200 and r.json()["detail"]["another_offer_preferred"] is True
    other = await mk_application(db_session, agent=None, university=await mk_university(db_session), student=world["direct_student"], status="enrolled", counselor_id=world["counselor"].id)
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OUTCOME.format(other.id), json={"outcome": "rejected", "reason": "x"})
    assert r.status_code == 409 and r.json()["detail"] == "An enrolled application cannot be given an outcome"


@pytest.mark.asyncio
async def test_the_rejection_letter_must_belong_to_the_application(db_session, world):
    app = world["direct_app"]
    mine = StudentDocument(student_id=world["direct_student"].id, application_id=app.id, document_type="rejection_letter", file_url="k1", verification_status="pending")
    other_app = await mk_application(db_session, agent=None, university=await mk_university(db_session), student=world["direct_student"], counselor_id=world["counselor"].id)
    theirs = StudentDocument(student_id=world["direct_student"].id, application_id=other_app.id, document_type="rejection_letter", file_url="k2", verification_status="pending")
    db_session.add_all([mine, theirs])
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "x", "document_id": str(theirs.id)})
        assert r.status_code == 422 and r.json()["detail"] == "Choose a document uploaded for this application"
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "x", "document_id": str(mine.id)})
    assert r.status_code == 200 and r.json()["detail"]["document_id"] == str(mine.id)


@pytest.mark.asyncio
async def test_scope_and_roles(db_session, world):
    body = {"outcome": "rejected", "reason": "x"}
    for who in ("counselor2", "direct_student", "master"):
        async with client_for(world[who].email) as c:
            assert (await c.post(OUTCOME.format(world["direct_app"].id), json=body)).status_code == 403, who


@pytest.mark.asyncio
async def test_a_rejected_application_frees_the_slot_for_a_new_one(db_session, world):  # O3
    app = world["direct_app"]
    payload = {"student_id": str(world["direct_student"].id), "university_id": str(app.university_id), "intake": "Sep 2028"}
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(CREATE, json=payload)).status_code == 409
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "x"})).status_code == 200
        assert (await c.post(CREATE, json=payload)).status_code == 201


@pytest.mark.asyncio
async def test_counselor_outcome_on_an_agency_application_tells_the_agency(db_session, world):  # CC4, CC5
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "Course full"})).status_code == 200
    assert "Application outcome changed" in [n.title for n in await notices(db_session, world["staff"]["user"])]
    async with client_for(world["master"].email) as c:
        detail = (await c.get(f"{APPS}/{app.id}")).json()["application"]
        assert detail["read_only_reason"] == "rejected" and detail["outcome"]["reason"] == "Course full"
        r = await c.post(AGENT_STATUS.format(app.id), json={"to_status": "offer"})
        assert r.status_code == 409


@pytest.mark.asyncio
async def test_the_agency_withdraw_records_the_outcome_and_tells_the_counselor(db_session, world):  # O1, CC5
    app = world["app"]
    async with client_for(world["master"].email) as c:
        r = await c.post(AGENT_STATUS.format(app.id), json={"to_status": "offer", "requested_by": "student"})
        assert r.status_code == 422
        r = await c.post(AGENT_STATUS.format(app.id), json={"to_status": "withdrawn", "notes": "Student asked", "requested_by": "student"})
        assert r.status_code == 200, r.text
        assert r.json()["application"]["outcome"]["requested_by"] == "student"
    item = await fresh(db_session, app)
    assert (item.status, item.outcome) == ("withdrawn", "withdrawn")
    assert [(e.outcome, e.requested_by, e.reason) for e in await _events(db_session, app)] == [("withdrawn", "student", "Student asked")]
    assert "Application outcome changed" in [n.title for n in await notices(db_session, world["counselor"])]


@pytest.mark.asyncio
async def test_on_hold_blocks_the_agency_moves_but_not_its_withdraw(db_session, world):
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        hold = {"outcome": "on_hold", "reason": "Docs", "review_date": (TODAY + timedelta(days=3)).isoformat()}
        assert (await c.post(OUTCOME.format(app.id), json=hold)).status_code == 200
    async with client_for(world["master"].email) as c:
        assert (await c.post(AGENT_STATUS.format(app.id), json={"to_status": "offer"})).status_code == 409
        assert (await c.post(AGENT_STATUS.format(app.id), json={"to_status": "withdrawn"})).status_code == 200
    assert (await _events(db_session, app))[-1].requested_by == "agent"


@pytest.mark.asyncio
async def test_reads_carry_the_outcome_and_the_student_view_is_filtered(db_session, world):
    app = world["direct_app"]
    review = (TODAY + timedelta(days=7)).isoformat()
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "on_hold", "reason": "Awaiting funds", "review_date": review})).status_code == 200
        table = (await c.get(PORTAL.format("counselor", "applications"))).json()
        assert {"key": "outcome_summary", "label": "Outcome"} in table["columns"]
        row = next(r for r in table["rows"] if r["id"] == str(app.id))
        assert (row["outcome"], row["outcome_summary"]) == ("on_hold", f"On hold until {review} -- Awaiting funds")
    async with client_for(world["direct_student"].email) as c:
        status = (await c.get(STATUS.format(app.id))).json()["outcome"]
        assert status["outcome"] == "on_hold" and "reason" not in status and "hold_owner" not in status
        table = (await c.get(PORTAL.format("student", "applications"))).json()
        assert next(r for r in table["rows"] if r["id"] == str(app.id))["outcome_label"] == "On hold"
    async with client_for(world["admin"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "x"})).status_code == 200
        table = (await c.get(PORTAL.format("admin", "applications"))).json()
        assert {"key": "reopen", "label": "", "type": "reopen_outcome"} in table["columns"]
        row = next(r for r in table["rows"] if r["id"] == str(app.id))
        assert row["reopen"] == str(app.id) and row["assign"] is None
