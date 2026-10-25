"""ccrm-027 (DEC-SCOPE-262) -- enrolment only after confirmation: the counselor/Admin `PUT …/enrollment` (document, checklist, student
number, course start date; agency applications too: CC4), the 422 on every other way into `enrolled`, corrections once enrolled, the
non-arrival / cancelled outcomes, and the funnel counting confirmed enrolments only."""

from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import AgentCommission, ApplicationStatusHistory, AuditLog, OverseasApplication
from app.services import management_funnel
from tests.agn001_helpers import client_for
from tests.agn009_helpers import PDF, mk_doc
from tests.agn023_helpers import ADVANCE, ASSIGN, UPDATE, assign_world, fresh, history_notes, notices

BASE = "/api/v1/workflows/overseas/applications/{}"
ENROLL = BASE + "/enrollment"
UPLOAD = BASE + "/enrollment-documents"
SUB = BASE + "/sub-status"
OUTCOME = BASE + "/outcome"
CONFIRMATION = "Enrolment confirmation"
GATE = "Enrolment is confirmed with the enrolment confirmation document, not by a stage change"


@pytest_asyncio.fixture
async def world(db_session):
    w = await assign_world(db_session, status="offer")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    w["direct_doc"] = await mk_doc(db_session, student=w["direct_student"], application=w["direct_app"], document_type=CONFIRMATION)
    w["agency_doc"] = await mk_doc(db_session, record=w["record"], application=w["app"], document_type=CONFIRMATION)
    return w


def body(document, **overrides) -> dict:
    data = {
        "expected_status": "offer",
        "enrollment_date": date.today().isoformat(),
        "enrollment_document_id": str(document.id),
        "pre_enrollment_checklist_complete": True,
        "university_student_id": "U-12345",
        "course_start_date": (date.today() + timedelta(days=14)).isoformat(),
    }
    return data | overrides


async def _history_count(db, app) -> int:
    return await db.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app.id))


@pytest.mark.asyncio
async def test_the_counselor_confirms_a_direct_enrolment_with_the_document_and_checklist(db_session, world):  # AC1, Appendix B
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.put(ENROLL.format(app.id), json=body(world["direct_doc"], notes="Arrived and registered"))
        got = (await c.get(ENROLL.format(app.id))).json()
    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["sub_status"], r.json()["changed"]) == ("enrolled", "enrolled", True)
    row = await fresh(db_session, app)
    assert (row.status, row.sub_status, row.university_student_id, row.enrollment_document_id) == ("enrolled", "enrolled", "U-12345", world["direct_doc"].id)
    assert row.pre_enrollment_checklist_complete is True and row.enrollment_confirmed_at is not None
    assert row.course_start_date == date.today() + timedelta(days=14)
    assert (await history_notes(db_session, app))[-1] == "Enrolment confirmed -- Arrived and registered"
    enrollment = got["enrollment"]
    assert enrollment["document"]["id"] == str(world["direct_doc"].id) and enrollment["confirmed"] is True
    assert [d["id"] for d in got["documents"]] == [str(world["direct_doc"].id)] and "file_url" not in str(got)
    assert "Enrolment confirmed" in [n.title for n in await notices(db_session, world["direct_student"])]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.enrollment"))
    assert audit.metadata_json == {"from_status": "offer", "to_status": "enrolled", "confirmed": True}


@pytest.mark.asyncio
async def test_the_upload_route_stores_an_enrolment_confirmation_document(db_session, world):
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        r = await c.post(UPLOAD.format(app.id), files={"file": ("confirmation.pdf", PDF, "application/pdf")})
        listed = (await c.get(ENROLL.format(app.id))).json()["documents"]
    assert r.status_code == 201, r.text
    assert r.json()["document"]["id"] in [d["id"] for d in listed]


@pytest.mark.asyncio
async def test_confirming_needs_the_document_the_checklist_and_an_offer(db_session, world):  # AC2
    app = world["direct_app"]
    passport = await mk_doc(db_session, student=world["direct_student"], application=app, document_type="Passport")
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ENROLL.format(app.id), json={k: v for k, v in body(world["direct_doc"]).items() if k != "enrollment_document_id"})).status_code == 422
        assert (await c.put(ENROLL.format(app.id), json=body(world["direct_doc"], pre_enrollment_checklist_complete=False))).status_code == 422
        for document in (passport, world["agency_doc"]):
            r = await c.put(ENROLL.format(app.id), json=body(document))
            assert r.status_code == 422 and r.json()["detail"] == "Choose an enrolment confirmation uploaded for this application"
        stale = await c.put(ENROLL.format(app.id), json=body(world["direct_doc"], expected_status="enquiry"))
    assert stale.status_code == 409
    row = await fresh(db_session, app)
    row.status = "university_selection"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        r = await c.put(ENROLL.format(app.id), json=body(world["direct_doc"], expected_status="university_selection"))
    assert r.status_code == 422 and r.json()["detail"] == "An offer is needed before enrollment"
    assert (await fresh(db_session, app)).status == "university_selection"


@pytest.mark.asyncio
async def test_on_hold_and_closed_applications_refuse_confirmation(db_session, world):  # AC2
    app = world["direct_app"]
    for outcome in ("on_hold", "rejected"):
        row = await fresh(db_session, app)
        row.outcome = outcome
        await db_session.commit()
        async with client_for(world["counselor"].email) as c:
            assert (await c.put(ENROLL.format(app.id), json=body(world["direct_doc"]))).status_code == 409
    assert (await fresh(db_session, app)).status == "offer"


@pytest.mark.asyncio
async def test_every_other_way_into_enrolled_is_a_422(db_session, world):  # AC3
    direct, agency = world["direct_app"], world["app"]
    before = await _history_count(db_session, direct)
    async with client_for(world["counselor"].email) as c:
        advance = await c.post(ADVANCE.format(direct.id), json={"to_status": "enrolled"})
        sub = await c.post(SUB.format(direct.id), json={"sub_status": "enrolled"})
    async with client_for(world["admin"].email) as c:
        patch = await c.patch(UPDATE.format(direct.id), json={"status": "enrolled"})
        admin_sub = await c.post(SUB.format(agency.id), json={"sub_status": "enrolled"})
    for r in (advance, sub, patch, admin_sub):
        assert r.status_code == 422 and r.json()["detail"] == GATE, r.text
    assert (await fresh(db_session, direct)).status == "offer" and await _history_count(db_session, direct) == before
    assert (await fresh(db_session, agency)).status == "offer"


@pytest.mark.asyncio
async def test_the_counselor_confirms_an_agency_enrolment_once_with_one_commission(db_session, world):  # AC4, CC4, CC5, E9
    app = world["app"]
    async with client_for(world["counselor2"].email) as c:
        assert (await c.put(ENROLL.format(app.id), json=body(world["agency_doc"]))).status_code == 403  # the `_assigned_application` scope
    async with client_for(world["counselor"].email) as c:
        r = await c.put(ENROLL.format(app.id), json=body(world["agency_doc"]))
        again = await c.put(ENROLL.format(app.id), json=body(world["agency_doc"]))
    assert r.status_code == 200, r.text
    assert again.status_code == 409  # the screen still says offer: stale
    commissions = await db_session.scalar(select(func.count()).select_from(AgentCommission).where(AgentCommission.application_id == app.id))
    assert commissions == 1
    assert (await fresh(db_session, app)).enrollment_confirmed_at is not None
    told = [n for n in await notices(db_session, world["staff"]["user"]) if n.title == "Application status changed"]
    assert told and told[-1].body.endswith("→ Enrolled.")


@pytest.mark.asyncio
async def test_once_enrolled_the_route_corrects_the_details_without_a_history_row(db_session, world):  # AC5, E7
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ENROLL.format(app.id), json=body(world["direct_doc"]))).status_code == 200
        rows = await _history_count(db_session, app)
        fix = await c.put(ENROLL.format(app.id), json=body(world["direct_doc"], expected_status="enrolled", university_student_id="U-99999"))
        same = await c.put(ENROLL.format(app.id), json=body(world["direct_doc"], expected_status="enrolled", university_student_id="U-99999"))
    assert fix.status_code == 200 and fix.json()["changed"] is True
    assert same.json()["changed"] is False
    assert (await fresh(db_session, app)).university_student_id == "U-99999"
    assert await _history_count(db_session, app) == rows
    audits = (await db_session.scalars(select(AuditLog.metadata_json).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.enrollment"))).all()
    assert {"fields": ["university_student_id"], "confirmed": False} in audits


@pytest.mark.asyncio
async def test_non_arrival_and_cancelled_need_a_reason_and_an_offer_and_close_the_application(db_session, world):  # AC6, E6
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.post(OUTCOME.format(app.id), json={"outcome": "non_arrival"})).status_code == 422
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "non_arrival", "reason": "Did not travel"})
        advance = await c.post(ADVANCE.format(app.id), json={"to_status": "visa_documentation"})
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "non_arrival" and r.json()["detail"]["terminal"] is True
    assert advance.status_code == 409
    early = await fresh(db_session, world["app"])
    early.status = "university_selection"
    await db_session.commit()
    async with client_for(world["counselor"].email) as c:
        r = await c.post(OUTCOME.format(early.id), json={"outcome": "cancelled", "reason": "Changed plans"})
    assert r.status_code == 422 and r.json()["detail"] == "An offer is needed before this outcome"


@pytest.mark.asyncio
async def test_an_enrolled_application_takes_no_cancelled_outcome(db_session, world):  # AC6
    app = world["direct_app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ENROLL.format(app.id), json=body(world["direct_doc"]))).status_code == 200
        r = await c.post(OUTCOME.format(app.id), json={"outcome": "cancelled", "reason": "Changed plans"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_the_funnel_counts_only_confirmed_enrolments(db_session, world):  # AC7, E4
    async with client_for(world["counselor"].email) as c:
        assert (await c.put(ENROLL.format(world["direct_app"].id), json=body(world["direct_doc"]))).status_code == 200
    legacy = await fresh(db_session, world["app"])  # an enrolment written before ccrm-027: no confirmation
    legacy.status = "enrolled"
    db_session.add(ApplicationStatusHistory(application_id=legacy.id, from_status="offer", to_status="enrolled", changed_by_id=world["counselor"].id))
    await db_session.commit()
    today = datetime.now(UTC).date()
    [stmt] = [s for key, *_, s in management_funnel._stages(today - timedelta(days=1), today + timedelta(days=1)) if key == "enrollment"]
    ids = set((await db_session.scalars(stmt.where(OverseasApplication.id.in_([world["direct_app"].id, legacy.id])))).all())
    assert ids == {world["direct_app"].id}


@pytest.mark.asyncio
async def test_readers_see_no_document_picker_and_cannot_write(db_session, world):
    app = world["direct_app"]
    async with client_for(world["direct_student"].email) as c:
        got = await c.get(ENROLL.format(app.id))
        put = await c.put(ENROLL.format(app.id), json=body(world["direct_doc"]))
    assert got.status_code == 200 and got.json()["documents"] == []
    assert put.status_code == 403
