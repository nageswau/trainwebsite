"""ENH-017 School-visible Global Education pipeline (spec 2026-09-29; DEC-SCOPE-036). High-level stage only (§19)."""

import pytest
from enh016_helpers import _user, login, make_school, make_student, make_university

from app.api.school_global_education import visa_stage_label
from app.models import OverseasApplication, VisaCase

URL = "/api/v1/school/global-education/pipeline"
TOP_KEYS = {"grade", "students_in_scope", "bridged_students", "funnel", "not_tracked", "students"}
FUNNEL_KEYS = ["pathway", "profile_evaluation", "shortlisted", "offer", "visa", "admitted"]


async def bridge(db, student, university, *, status="enquiry", intake="Fall 2027", **fields) -> OverseasApplication:
    application = OverseasApplication(student_id=None, school_student_id=student.id, university_id=university.id, intake=intake, status=status, **fields)
    db.add(application)
    await db.flush()
    return application


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_coordinator", "school_principal"])
async def test_coordinator_and_principal_read_their_own_school(client, db_session, role):  # AC01
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])

    response = await client.get(URL)

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == TOP_KEYS
    assert [s["key"] for s in body["funnel"]] == FUNNEL_KEYS
    assert set(body["students"]) == {"items", "total", "limit", "offset"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "academic_team", "career_counselor", "psychometric_team", "overseas_admin", "super_admin", "it_admin"])
async def test_every_other_role_is_refused(client, db_session, role):  # AC02
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx[role])
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["counselor", "overseas_student"])
async def test_overseas_counselor_and_student_are_refused(client, db_session, role):  # AC02
    user = _user(role, "overseas")
    db_session.add(user)
    await db_session.commit()
    await login(client, user)
    assert (await client.get(URL)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_is_401(client):  # AC02
    assert (await client.get(URL)).status_code == 401


@pytest.mark.asyncio
async def test_coordinator_without_a_linked_school_is_403(client, db_session):  # AC03
    user = _user("school_coordinator", "overseas")  # profile {} -- no school_id
    db_session.add(user)
    await db_session.commit()
    await login(client, user)
    assert (await client.get(URL)).status_code == 403


def _funnel(body):
    return {s["key"]: s["count"] for s in body["funnel"]}


def _rows(body):
    return {r["full_name"]: r for r in body["students"]["items"]}


@pytest.mark.asyncio
async def test_funnel_counts_each_student_once_per_stage_reached(client, db_session):  # AC05, AC06, Review Focus 1/2/4
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    many = await make_student(db_session, ctx, name="Asha Many")
    await bridge(db_session, many, uni, status="enquiry")
    await bridge(db_session, many, uni, status="offer")
    await bridge(db_session, many, uni, status="university_selection")
    legacy = await make_student(db_session, ctx, name="Bala Legacy")
    await bridge(db_session, legacy, uni, status="offer_received")  # outside the enum, but in OFFER_ONWARD_STATUSES
    withdrawn = await make_student(db_session, ctx, name="Chen Withdrawn")
    await bridge(db_session, withdrawn, uni, status="withdrawn")  # pathway only
    blank_offer = await make_student(db_session, ctx, name="Dina Blank")
    await bridge(db_session, blank_offer, uni, status="eligibility_evaluation", offer_letter_url="")  # "" is not an offer
    visa_student = await make_student(db_session, ctx, name="Esa Visa")
    visa_app = await bridge(db_session, visa_student, uni, status="enrolled")
    db_session.add(VisaCase(application_id=visa_app.id, status="interview_prep"))
    await make_student(db_session, ctx, name="Farah NotBridged")
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    body = (await client.get(URL)).json()

    assert body["students_in_scope"] == 6
    assert body["bridged_students"] == 5
    assert _funnel(body) == {"pathway": 5, "profile_evaluation": 3, "shortlisted": 2, "offer": 3, "visa": 1, "admitted": 1}
    assert "Farah NotBridged" not in _rows(body)
    assert body["students"]["total"] == 5


@pytest.mark.asyncio
async def test_not_tracked_stages_are_listed_with_reasons(client, db_session):  # AC08
    ctx = await make_school(db_session)
    await db_session.commit()
    await login(client, ctx["school_principal"])

    body = (await client.get(URL)).json()

    assert [s["key"] for s in body["not_tracked"]] == ["applications_started", "applications_submitted", "deposit", "scholarship", "top_100", "alumni"]
    assert all(s["note"] and set(s) == {"key", "label", "note"} for s in body["not_tracked"])
    assert not {s["key"] for s in body["not_tracked"]} & {s["key"] for s in body["funnel"]}


@pytest.mark.asyncio
async def test_each_row_shows_furthest_stage_visa_label_and_count(client, db_session):  # AC09
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    s = await make_student(db_session, ctx, name="Gita Row", grade_level=12)
    first = await bridge(db_session, s, uni, status="offer")
    second = await bridge(db_session, s, uni, status="enquiry")
    db_session.add_all([VisaCase(application_id=first.id, status="documentation"), VisaCase(application_id=second.id, status="checklist")])
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    row = _rows((await client.get(URL)).json())["Gita Row"]

    assert row["furthest_stage"] == "visa" and row["furthest_stage_label"] == "Visa"
    assert row["visa_stage_label"] == "Documentation"
    assert row["application_count"] == 2
    assert row["grade"] == "12"
    assert row["student_code"] == s.student_code


def test_visa_stage_label_rules():  # AC09
    assert visa_stage_label([]) is None
    assert visa_stage_label(["checklist", "decision", "tracking"]) == "Decision"
    assert visa_stage_label(["interview_prep"]) == "Interview preparation"
    assert visa_stage_label(["approved"]) == "In progress"  # not a modelled stage
    assert visa_stage_label(["approved", "checklist"]) == "Checklist"  # a known stage wins over an unknown one


@pytest.mark.asyncio
async def test_funnel_matches_the_dashboard_kpis(client, db_session):  # AC07
    ctx = await make_school(db_session)
    uni = await make_university(db_session)
    for status in ("enquiry", "university_selection", "offer", "enrolled"):
        s = await make_student(db_session, ctx)
        application = await bridge(db_session, s, uni, status=status)
        if status in ("offer", "enrolled"):
            db_session.add(VisaCase(application_id=application.id))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    funnel = _funnel((await client.get(URL)).json())
    kpis = {k["key"]: k["value"] for k in (await client.get("/api/v1/school/dashboard")).json()["school_crm_kpis"]}

    assert funnel["pathway"] == kpis["students_in_global_education_pathway"]
    assert funnel["shortlisted"] == kpis["university_shortlisting"]
    assert funnel["visa"] == kpis["visa_applications"]
    assert funnel["admitted"] == kpis["students_admitted"]


@pytest.mark.asyncio
async def test_another_schools_bridged_students_never_appear(client, db_session):  # AC04
    mine = await make_school(db_session)
    other = await make_school(db_session)
    uni = await make_university(db_session)
    await bridge(db_session, await make_student(db_session, mine, name="Mine One"), uni)
    await bridge(db_session, await make_student(db_session, other, name="Other One"), uni, status="enrolled")
    await db_session.commit()
    await login(client, mine["school_coordinator"])

    body = (await client.get(URL)).json()

    assert set(_rows(body)) == {"Mine One"}
    assert _funnel(body)["admitted"] == 0


ROW_KEYS = {"school_student_id", "full_name", "student_code", "grade", "furthest_stage", "furthest_stage_label", "visa_stage_label", "application_count"}


@pytest.mark.asyncio
async def test_response_carries_only_the_allowlisted_keys_and_no_planted_detail(client, db_session):  # AC10, AC11
    ctx = await make_school(db_session)
    counselor = _user("counselor", "overseas")
    counselor.full_name = "PLANTED-COUNSELOR-NAME"
    db_session.add(counselor)
    uni = await make_university(db_session)
    uni.name = "PLANTED-UNIVERSITY"
    s = await make_student(db_session, ctx, name="Hana Safe")
    application = await bridge(
        db_session, s, uni, status="offer", counselor_id=counselor.id, intake="PLANTED-INTAKE",
        notes="PLANTED-NOTES", next_action="PLANTED-NEXT-ACTION", application_reference="PLANTED-REF", offer_letter_url="https://x/PLANTED-OFFER.pdf",
    )
    db_session.add(VisaCase(application_id=application.id, status="tracking", tracking_reference="PLANTED-VISA-REF"))
    await db_session.commit()
    await login(client, ctx["school_coordinator"])

    response = await client.get(URL)

    body = response.json()
    assert set(body) == TOP_KEYS
    assert all(set(s) == {"key", "label", "count"} for s in body["funnel"])
    assert set(body["students"]) == {"items", "total", "limit", "offset"}
    assert all(set(r) == ROW_KEYS for r in body["students"]["items"])
    assert "PLANTED" not in response.text
    assert str(application.id) not in response.text
