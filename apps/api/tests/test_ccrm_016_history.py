"""ccrm-016 (DEC-SCOPE-247, H1-H3) -- status history with author and reason: each history row carries the outcome it set and its reason
(H1); the counselor / admin read returns author, notes, reason, sub-status and outcome (AC 6); the student read is filtered (H2); the
agency detail gains outcome and reason. Agency world: tests/agn023_helpers.py."""

from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import ApplicationStatusHistory
from tests.agn001_helpers import client_for
from tests.agn008_helpers import APPS
from tests.agn009_helpers import mk_doc
from tests.agn023_helpers import ASSIGN, assign_world
from tests.test_ccrm_023_offers import OFFERS, WITHDRAW, body

STATUS = "/api/v1/workflows/overseas/applications/{}/status"
OUTCOME = "/api/v1/workflows/overseas/applications/{}/outcome"
REOPEN = OUTCOME + "/reopen"
SUB = "/api/v1/workflows/overseas/applications/{}/sub-status"
STAFF_FIELDS = {"notes", "reason", "changed_by"}


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="university_selection")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    return w


async def _rows(db, app) -> list[ApplicationStatusHistory]:
    stmt = select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id).order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


@pytest.mark.asyncio
async def test_the_counselor_reads_author_notes_reason_sub_status_and_outcome(db_session, world):  # AC 6
    app, counselor, admin = world["direct_app"], world["counselor"], world["admin"]
    async with client_for(counselor.email) as c:
        assert (await c.post(SUB.format(app.id), json={"sub_status": "documents_pending"})).status_code == 200
        hold = {"outcome": "on_hold", "reason": "Awaiting funds", "review_date": (date.today() + timedelta(days=7)).isoformat()}
        assert (await c.post(OUTCOME.format(app.id), json=hold)).status_code == 200
        assert (await c.post(REOPEN.format(app.id), json={"reason": "Funds arrived"})).status_code == 200
        r = await c.get(STATUS.format(app.id))
    assert r.status_code == 200, r.text
    history = r.json()["history"]
    assigned, sub, held, resumed = history[-4:]
    assert assigned["changed_by"] == admin.full_name and assigned["notes"] == "EduSphere counsellor assigned" and assigned["outcome"] is None
    assert (sub["to_sub_status"], sub["changed_by"], sub["outcome"], sub["outcome_label"]) == ("documents_pending", counselor.full_name, None, None)
    assert (held["outcome"], held["outcome_label"], held["reason"]) == ("on_hold", "On hold", "Awaiting funds")
    assert held["notes"] == "Outcome: On hold -- Awaiting funds" and held["changed_by"] == counselor.full_name
    assert (resumed["outcome"], resumed["outcome_label"], resumed["reason"]) == ("cleared", "Cleared", "Funds arrived")
    assert all(h["created_at"] == h["changed_at"] for h in history)  # the old key stays


@pytest.mark.asyncio
async def test_the_student_sees_stage_sub_status_outcome_and_time_only(db_session, world):  # H2
    app, student = world["direct_app"], world["direct_student"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "Internal: grades below cut-off"})).status_code == 200
    async with client_for(student.email) as c:
        r = await c.get(STATUS.format(app.id))
    assert r.status_code == 200
    history = r.json()["history"]
    assert history and all(not STAFF_FIELDS & set(h) for h in history)
    assert history[-1]["outcome"] == "rejected" and history[-1]["outcome_label"] == "Rejected"
    assert "Internal" not in r.text


@pytest.mark.asyncio
async def test_writers_fill_outcome_and_reason(db_session, world):  # H1
    app, direct = world["app"], world["direct_app"]
    async with client_for(world["master"].email) as c:  # the agency withdraw: the note is the reason (O1)
        r = await c.post(APPS + f"/{app.id}/status", json={"to_status": "withdrawn", "notes": "Student chose another country", "requested_by": "student"})
    assert r.status_code == 200, r.text
    last = (await _rows(db_session, app))[-1]
    assert (last.outcome, last.reason, last.to_status) == ("withdrawn", "Student chose another country", "withdrawn")
    letter = await mk_doc(db_session, student=world["direct_student"], application=direct, document_type="Offer letter")
    async with client_for(world["counselor"].email) as c:
        offer = await c.post(OFFERS.format(direct.id), json=body(letter))
        assert offer.status_code == 201, offer.text
        closed = await c.post(WITHDRAW.format(direct.id, offer.json()["offer"]["id"]), json={"status": "expired", "reason": "Deadline passed"})
        assert closed.status_code == 200, closed.text
    last = (await _rows(db_session, direct))[-1]
    assert (last.outcome, last.reason) == (None, "Deadline passed")  # an offer close is not an outcome


@pytest.mark.asyncio
async def test_the_agency_detail_carries_outcome_and_reason(db_session, world):
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "rejected", "reason": "Course full"})).status_code == 200
    async with client_for(world["master"].email) as c:
        r = await c.get(APPS + f"/{app.id}")
    assert r.status_code == 200, r.text
    last = r.json()["application"]["history"][-1]
    assert (last["outcome"], last["outcome_label"], last["reason"], last["changed_by"]) == ("rejected", "Rejected", "Course full", world["counselor"].full_name)


@pytest.mark.asyncio
async def test_the_read_scope_is_unchanged(db_session, world):
    app = world["direct_app"]
    for user, code in ((world["counselor2"], 403), (world["master"], 403), (world["admin"], 200)):  # the agency reads its own detail
        async with client_for(user.email) as c:
            assert (await c.get(STATUS.format(app.id))).status_code == code, user.full_name
    async with client_for(world["admin"].email) as c:
        assert STAFF_FIELDS <= set((await c.get(STATUS.format(app.id))).json()["history"][-1])
