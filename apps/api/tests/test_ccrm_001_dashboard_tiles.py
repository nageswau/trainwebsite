"""ccrm-001 (DEC-SCOPE-238) -- the counselor's and Overseas Admin's "Awaiting documents" and "Offers" tiles count real stages.
Offers = at `offer` or later (OFFER_COUNTED_STATUSES), never withdrawn. Awaiting documents (owner answer, 2026-10-22) = an application
at `university_selection` with a document pending verification, or one whose undecided visa case has a checklist item not verified."""

import pytest
from sqlalchemy import func, select

from app.models import OverseasApplication, StudentDocument, VisaCase
from tests.agn001_helpers import client_for, mk_user
from tests.agn003_helpers import mk_university

COUNSELOR = "/api/v1/portal/overseas/counselor/dashboard"
ADMIN = "/api/v1/portal/overseas/admin/dashboard"


async def mk_app(db, counselor, university, status: str) -> OverseasApplication:
    student = await mk_user(db, role="overseas_student", full_name="Tile Student")
    application = OverseasApplication(student_id=student.id, university_id=university.id, counselor_id=counselor.id, intake="Fall 2027", status=status)
    db.add(application)
    await db.commit()
    return application


async def mk_doc(db, application, document_type: str, status: str) -> None:
    db.add(StudentDocument(student_id=application.student_id, application_id=application.id, document_type=document_type, file_url=f"tests/{document_type}.pdf", verification_status=status))
    await db.commit()


async def mk_case(db, application, checklist: list[str], decision: str | None = None) -> None:
    db.add(VisaCase(application_id=application.id, checklist=checklist, decision=decision))
    await db.commit()


async def tiles(email: str, path: str = COUNSELOR) -> dict:
    async with client_for(email) as c:
        response = await c.get(path)
    assert response.status_code == 200, response.text
    return {m["label"]: m["value"] for m in response.json()["metrics"]}


@pytest.mark.asyncio
async def test_offers_count_applications_at_offer_or_later_and_never_withdrawn(db_session):
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    for status in ("enquiry", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled", "withdrawn"):
        await mk_app(db_session, counselor, university, status)
    assert (await tiles(counselor.email))["Offers"] == 4


@pytest.mark.asyncio
async def test_awaiting_documents_counts_pending_documents_at_university_selection(db_session):
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    selection = await mk_app(db_session, counselor, university, "university_selection")
    await mk_doc(db_session, selection, "transcript", "pending")
    verified = await mk_app(db_session, counselor, university, "university_selection")
    await mk_doc(db_session, verified, "transcript", "verified")
    enquiry = await mk_app(db_session, counselor, university, "enquiry")  # a pending document before university selection does not count
    await mk_doc(db_session, enquiry, "transcript", "pending")
    await mk_app(db_session, counselor, university, "university_selection")  # no documents at all
    assert (await tiles(counselor.email))["Awaiting documents"] == 1


@pytest.mark.asyncio
async def test_awaiting_documents_counts_undecided_visa_cases_with_unverified_checklist_items(db_session):
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    missing = await mk_app(db_session, counselor, university, "visa_documentation")
    await mk_case(db_session, missing, ["passport", "bank_statement"])
    await mk_doc(db_session, missing, "passport", "verified")  # bank_statement never uploaded
    superseded = await mk_app(db_session, counselor, university, "visa_documentation")
    await mk_case(db_session, superseded, ["passport"])
    await mk_doc(db_session, superseded, "passport", "verified")
    await mk_doc(db_session, superseded, "passport", "incomplete")  # the newest document of the type decides
    complete = await mk_app(db_session, counselor, university, "visa_documentation")
    await mk_case(db_session, complete, ["passport"])
    await mk_doc(db_session, complete, "passport", "verified")
    decided = await mk_app(db_session, counselor, university, "status_tracking")
    await mk_case(db_session, decided, ["passport"], decision="approved")
    withdrawn = await mk_app(db_session, counselor, university, "withdrawn")
    await mk_case(db_session, withdrawn, ["passport"])
    enrolled = await mk_app(db_session, counselor, university, "enrolled")
    await mk_case(db_session, enrolled, ["passport"])
    assert (await tiles(counselor.email))["Awaiting documents"] == 2


@pytest.mark.asyncio
async def test_another_counselors_applications_are_not_counted(db_session):
    counselor = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    offer = await mk_app(db_session, other, university, "offer")
    await mk_case(db_session, offer, ["passport"])
    selection = await mk_app(db_session, other, university, "university_selection")
    await mk_doc(db_session, selection, "transcript", "pending")
    mine = await tiles(counselor.email)
    assert (mine["Applications"], mine["Awaiting documents"], mine["Offers"]) == (0, 0, 0)
    theirs = await tiles(other.email)
    assert (theirs["Applications"], theirs["Awaiting documents"], theirs["Offers"]) == (2, 2, 1)


@pytest.mark.asyncio
async def test_the_overseas_admin_dashboard_uses_the_same_tiles(db_session):
    admin = await mk_user(db_session, role="overseas_admin")
    counselor = await mk_user(db_session, role="counselor")
    university = await mk_university(db_session)
    before = await tiles(admin.email, ADMIN)
    offer = await mk_app(db_session, counselor, university, "offer")
    await mk_case(db_session, offer, ["passport"])
    await mk_app(db_session, counselor, university, "withdrawn")
    after = await tiles(admin.email, ADMIN)
    assert after["Offers"] >= 1 and after["Awaiting documents"] >= 1
    total = await db_session.scalar(select(func.count()).select_from(OverseasApplication))
    if total <= 500:  # the dashboard reads the newest 500 applications; on a larger shared test database the deltas are not exact
        assert after["Offers"] - before["Offers"] == 1
        assert after["Awaiting documents"] - before["Awaiting documents"] == 1
