"""UNI-001 -- University Representative portal.

Most of the confirmed scope already existed: the `dashboard`/`applications`/
`offer-letters`/`admission-updates` sections were already correctly implemented and
scoped to the Rep's own institution via `User.profile["university_id"]` (used
consistently by `_assigned_application`, `list_overseas_applications`, and the portal
dashboard) -- `DATA_MODEL.md` #6.10 describes this scope field as still needing to be
built, but it was already added as a byproduct of earlier session work and confirmed
directly, not assumed.

Two real, confirmed gaps found instead:

1. `reports` -- `PORTAL_NAV["overseas/university"]` lists "Reports", but
   `services/portal.py`'s handler for that section was guarded `and user.role ==
   "counselor"` only, so a University Rep's own link 404'd ("Workspace not found"). Exact
   same bug class `CNS-001` found and fixed for the Counselor's own Leads/Reports, not
   carried over to this role. Added a Rep-specific aggregate, scoped to their own
   already-filtered applications.
2. No endpoint existed anywhere for `API_CONTRACT.md` §9's explicitly-named
   `POST /university-rep/applications/{id}/updates` ("Posts an admission update, visible
   to the assigned Counselor and Student") -- the generic PATCH only lets a Rep edit the
   application's own fields, with no distinct communication action. Added
   `POST /workflows/overseas/university-rep/applications/{id}/updates`, reusing the
   existing `_notify_user` mechanism (no new model/migration) and the same
   `_assigned_application` own-institution IDOR check used everywhere else for this role.
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models import Country, Notification, OverseasApplication, University, User


async def _create_user(db_session, *, role: str, division: str = "overseas", **overrides) -> User:
    defaults = dict(
        email=f"uni001-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password("Sup3r-Secret-Pass!"),
        full_name=f"Test {role.title()}",
        role=role,
        division=division,
        active=True,
    )
    defaults.update(overrides)
    user = User(**defaults)
    db_session.add(user)
    await db_session.commit()
    return user


async def _make_university(db_session, name: str | None = None) -> University:
    country = Country(
        slug=f"uni001-country-{uuid.uuid4().hex[:8]}",
        name="Testland",
        overview="A test destination.",
        tuition="USD 20,000/year",
        living_expenses="USD 1,000/month",
        visa_process=[],
        work_opportunities="",
        post_study_work="",
        pr_opportunities="",
        faq=[],
    )
    db_session.add(country)
    await db_session.flush()
    university = University(
        country_id=country.id,
        slug=f"uni001-university-{uuid.uuid4().hex[:8]}",
        name=name or f"UNI-001 Test University {uuid.uuid4().hex[:8]}",
        city="Testville",
        overview="A test university.",
        eligibility="",
        requirements=[],
        deadlines=[],
        scholarships=[],
    )
    db_session.add(university)
    await db_session.commit()
    return university


async def _create_rep(db_session, university: University) -> User:
    return await _create_user(db_session, role="university_rep", profile={"demo": False, "university_id": str(university.id)})


async def _login(client, email: str) -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "Sup3r-Secret-Pass!", "division": "overseas"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reports_section_renders_for_university_rep_instead_of_404ing(db_session, client):
    university = await _make_university(db_session)
    rep = await _create_rep(db_session, university)
    student = await _create_user(db_session, role="overseas_student")
    application = OverseasApplication(student_id=student.id, university_id=university.id, status="offer", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.get("/api/v1/portal/overseas/university/reports")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "University Partner Report"
    metrics = {m["label"]: m["value"] for m in body["metrics"]}
    assert metrics["Applications"] == 1
    assert metrics["Offers extended"] == 1


@pytest.mark.asyncio
async def test_reports_only_counts_the_reps_own_institution(db_session, client):
    university_a = await _make_university(db_session)
    university_b = await _make_university(db_session)
    rep = await _create_rep(db_session, university_a)
    student = await _create_user(db_session, role="overseas_student")
    db_session.add(OverseasApplication(student_id=student.id, university_id=university_a.id, status="enquiry", next_action="", intake="September 2027"))
    db_session.add(OverseasApplication(student_id=student.id, university_id=university_b.id, status="enquiry", next_action="", intake="September 2027"))
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.get("/api/v1/portal/overseas/university/reports")
    assert response.status_code == 200
    metrics = {m["label"]: m["value"] for m in response.json()["metrics"]}
    assert metrics["Applications"] == 1


@pytest.mark.asyncio
async def test_offer_letters_section_shows_a_dedicated_filtered_view(db_session, client):
    # Tester feedback (2026-09-04, RAID.md I-12): the "Offer Letters" nav item rendered
    # the exact same unfiltered "Application Tracking" table as "Applications" -- byte-
    # identical heading and rows, indistinguishable as a feature of its own. Confirmed
    # directly against the running app before this fix. Mirrors the Student role's own
    # existing "offer-letters" section (services/portal.py, overseas_student branch),
    # which already filters to `offer_letter_url` set or status offer/accepted.
    university = await _make_university(db_session)
    rep = await _create_rep(db_session, university)
    student = await _create_user(db_session, role="overseas_student")
    enquiry_stage = OverseasApplication(student_id=student.id, university_id=university.id, status="enquiry", next_action="", intake="September 2027")
    offer_stage = OverseasApplication(student_id=student.id, university_id=university.id, status="offer_received", offer_letter_url="https://example.local/offer.pdf", next_action="", intake="September 2027")
    db_session.add_all([enquiry_stage, offer_stage])
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.get("/api/v1/portal/overseas/university/offer-letters")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Offer Letters"
    rows = body["rows"]
    assert len(rows) == 1
    assert rows[0]["offer"] == "https://example.local/offer.pdf"


@pytest.mark.asyncio
async def test_offer_letters_section_only_shows_the_reps_own_institution(db_session, client):
    university_a = await _make_university(db_session)
    university_b = await _make_university(db_session)
    rep = await _create_rep(db_session, university_a)
    student = await _create_user(db_session, role="overseas_student")
    db_session.add(OverseasApplication(student_id=student.id, university_id=university_a.id, status="offer_received", offer_letter_url="https://example.local/a.pdf", next_action="", intake="September 2027"))
    db_session.add(OverseasApplication(student_id=student.id, university_id=university_b.id, status="offer_received", offer_letter_url="https://example.local/b.pdf", next_action="", intake="September 2027"))
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.get("/api/v1/portal/overseas/university/offer-letters")
    assert response.status_code == 200
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0]["offer"] == "https://example.local/a.pdf"


@pytest.mark.asyncio
async def test_rep_posts_an_update_and_notifies_student_and_counselor(db_session, client):
    university = await _make_university(db_session)
    rep = await _create_rep(db_session, university)
    student = await _create_user(db_session, role="overseas_student")
    counselor = await _create_user(db_session, role="counselor")
    application = OverseasApplication(student_id=student.id, university_id=university.id, counselor_id=counselor.id, status="offer", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.post(f"/api/v1/workflows/overseas/university-rep/applications/{application.id}/updates", json={"message": "Offer letter has been dispatched."})
    assert response.status_code == 201
    assert response.json()["notified"] == 2

    student_note = await db_session.scalar(select(Notification).where(Notification.user_id == student.id))
    counselor_note = await db_session.scalar(select(Notification).where(Notification.user_id == counselor.id))
    assert student_note is not None and "Offer letter" in student_note.body
    assert counselor_note is not None and "Offer letter" in counselor_note.body


@pytest.mark.asyncio
async def test_rep_cannot_post_an_update_to_another_institutions_application(db_session, client):
    university_a = await _make_university(db_session)
    university_b = await _make_university(db_session)
    rep = await _create_rep(db_session, university_a)
    student = await _create_user(db_session, role="overseas_student")
    application = OverseasApplication(student_id=student.id, university_id=university_b.id, status="offer", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.post(f"/api/v1/workflows/overseas/university-rep/applications/{application.id}/updates", json={"message": "Should not be allowed."})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_a_blank_update_message_is_rejected(db_session, client):
    university = await _make_university(db_session)
    rep = await _create_rep(db_session, university)
    student = await _create_user(db_session, role="overseas_student")
    application = OverseasApplication(student_id=student.id, university_id=university.id, status="offer", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()

    await _login(client, rep.email)
    response = await client.post(f"/api/v1/workflows/overseas/university-rep/applications/{application.id}/updates", json={"message": "   "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_non_rep_role_cannot_post_a_university_update(db_session, client):
    university = await _make_university(db_session)
    student = await _create_user(db_session, role="overseas_student")
    application = OverseasApplication(student_id=student.id, university_id=university.id, status="offer", next_action="", intake="September 2027")
    db_session.add(application)
    await db_session.commit()

    await _login(client, student.email)
    response = await client.post(f"/api/v1/workflows/overseas/university-rep/applications/{application.id}/updates", json={"message": "Attempted."})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_posting_a_university_update_requires_authentication(client):
    response = await client.post(f"/api/v1/workflows/overseas/university-rep/applications/{uuid.uuid4()}/updates", json={"message": "Anon."})
    assert response.status_code == 401
