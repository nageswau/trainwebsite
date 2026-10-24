"""ccrm-009 (DEC-SCOPE-252, V1-V2, B1-B6) -- the counselor's student 360: read-only GET /counselor/students/{id}/overview, /documents,
/activities and /history. The overseas counselor with the student in csc-001 scope and the Overseas Admin read; anyone else is refused.
V1: inside the page the counselor sees ALL the student's applications, documents and history, marked "yours" or not; a download is
offered only where the existing download route allows it."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio

from app.models import ApplicationStatusHistory, Appointment, AuditLog, OverseasStudentCounselor, StudentDocument
from tests.agn001_helpers import login, mk_user, uniq
from tests.ccrm012_helpers import mk_lead
from tests.enh031_helpers import mk_application, mk_course, mk_university

PORTAL = "/api/v1/portal/overseas/{}/{}"


def url(student_id, tab: str) -> str:
    return f"/api/v1/counselor/students/{student_id}/{tab}"


async def mk_document(db, student, application=None, **fields) -> StudentDocument:
    doc = StudentDocument(student_id=student.id, application_id=application.id if application else None, document_type=fields.pop("document_type", "Passport"), file_url="/local-files/x.pdf", **fields)
    db.add(doc)
    await db.commit()
    return doc


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c9')} Student")
    uni = await mk_university(db_session, name=uniq("Alpha Uni"))
    course = await mk_course(db_session, uni, "MSc Data Science")
    own = await mk_application(db_session, student=student, university=uni, counselor=counselor, course=course, status="offer", reference="REF-1")
    own2 = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Beta Uni")), counselor=counselor, status="enquiry")
    foreign = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Gamma Uni")), counselor=other, status="visa_documentation")
    own.next_action = "Chase the CAS"
    await db_session.commit()
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "own": own, "own2": own2, "foreign": foreign, "uni": uni}


@pytest.mark.asyncio
async def test_overview_shows_each_application_with_its_own_status(client, world):
    await login(client, world["counselor"].email)
    response = await client.get(url(world["student"].id, "overview"))
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["student"]["id"] == str(world["student"].id) and data["student"]["full_name"] == world["student"].full_name
    assert data["student"]["email"] == world["student"].email and data["account_status"] == "active"
    apps = {a["id"]: a for a in data["applications"]}
    assert len(apps) == 3  # backlog AC: three applications, three independent statuses
    own, own2, foreign = apps[str(world["own"].id)], apps[str(world["own2"].id)], apps[str(world["foreign"].id)]
    assert (own["status"], own2["status"], foreign["status"]) == ("offer", "enquiry", "visa_documentation")
    assert own["status_label"] == "Offer" and foreign["status_label"] == "Visa documentation"
    assert own["mine"] is True and foreign["mine"] is False  # V1: all of the student's applications, marked
    assert own["course"] == "MSc Data Science" and own["university"] == world["uni"].name and own["application_code"].startswith("APP-")
    assert foreign["counselor"] == "Omar Counselor" and own["is_agency"] is False
    assert data["counts"] == {"applications": 3, "open_applications": 3, "documents_to_review": 0}
    assert data["next_actions"] == [{"application_id": str(world["own"].id), "application_code": own["application_code"], "university": world["uni"].name, "next_action": "Chase the CAS"}]
    assert data["counselor"] is None  # no csc-001 link yet: the counselor is shown per application


@pytest.mark.asyncio
async def test_a_linked_walk_in_student_with_no_applications(client, db_session, world):
    walk_in = await mk_user(db_session, role="overseas_student", full_name="Walk In")
    db_session.add(OverseasStudentCounselor(student_user_id=walk_in.id, counselor_user_id=world["counselor"].id, assigned_by_user_id=world["counselor"].id))
    await db_session.commit()
    await login(client, world["counselor"].email)
    data = (await client.get(url(walk_in.id, "overview"))).json()
    assert data["applications"] == [] and data["counselor"] == {"id": str(world["counselor"].id), "full_name": "Nora Counselor"}
    assert data["counts"]["applications"] == 0
    for tab in ("documents", "activities", "history"):
        assert (await client.get(url(walk_in.id, tab))).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("tab", ["overview", "documents", "activities", "history"])
async def test_out_of_scope_student_is_404_and_other_roles_403(client, db_session, world, tab):
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, world["counselor"].email)
    assert (await client.get(url(stranger.id, tab))).status_code == 404  # backlog AC: another counselor's student
    assert (await client.get(url(world["counselor"].id, tab))).status_code == 404  # not a student
    for role, division in (("overseas_student", "overseas"), ("agent", "overseas"), ("counselor", "it")):
        user = world["student"] if role == "overseas_student" else await mk_user(db_session, role=role, division=division)
        await login(client, user.email, division)
        assert (await client.get(url(world["student"].id, tab))).status_code == 403, role


@pytest.mark.asyncio
async def test_admin_reads_every_tab_and_sees_no_application_as_mine(client, world):
    await login(client, world["admin"].email)
    data = (await client.get(url(world["student"].id, "overview"))).json()
    assert len(data["applications"]) == 3 and not any(a["mine"] for a in data["applications"])


@pytest.mark.asyncio
async def test_documents_are_current_versions_with_download_only_where_allowed(client, db_session, world):
    student = world["student"]
    mine = await mk_document(db_session, student, world["own"], verification_status="pending", expiry_date=(datetime.now(UTC) + timedelta(days=400)).date())
    theirs = await mk_document(db_session, student, world["foreign"], document_type="Bank statement", verification_status="verified")
    loose = await mk_document(db_session, student, None, document_type="SOP", verification_status="under_review")
    await mk_document(db_session, student, world["own"], document_type="Old passport", archived_at=datetime.now(UTC))
    await login(client, world["counselor"].email)
    docs = {d["id"]: d for d in (await client.get(url(student.id, "documents"))).json()["items"]}
    assert set(docs) == {str(mine.id), str(theirs.id), str(loose.id)}  # the archived version is left out
    assert docs[str(mine.id)]["can_download"] is True and docs[str(mine.id)]["status_label"] == "Pending review"
    assert docs[str(mine.id)]["application_code"] == world["own"].application_code
    assert docs[str(theirs.id)]["can_download"] is False  # V1: the download route refuses another counselor's application
    assert docs[str(loose.id)]["can_download"] is True  # no application: allowed because the counselor has one of the student's
    overview = (await client.get(url(student.id, "overview"))).json()
    assert overview["counts"]["documents_to_review"] == 2  # pending + under_review

    await login(client, world["admin"].email)
    assert all(d["can_download"] for d in (await client.get(url(student.id, "documents"))).json()["items"])


@pytest.mark.asyncio
async def test_activities_list_appointments_and_linked_leads(client, db_session, world):
    student = world["student"]
    when = datetime.now(UTC) + timedelta(days=2)
    db_session.add(Appointment(division="overseas", student_id=student.id, staff_id=world["counselor"].id, scheduled_at=when, appointment_type="Counselling", mode="Online"))
    await db_session.commit()
    mine = await mk_lead(db_session, world["counselor"], converted_user_id=student.id, converted_at=datetime.now(UTC), converted_by_user_id=world["counselor"].id, status="application_enrollment")
    await login(client, world["counselor"].email)
    data = (await client.get(url(student.id, "activities"))).json()
    assert [(a["type"], a["staff"], a["status"]) for a in data["appointments"]] == [("Counselling", "Nora Counselor", "scheduled")]
    assert data["leads"] == [
        {
            "id": str(mine.id),
            "lead_code": mine.lead_code,
            "stage": "application_enrollment",
            "stage_label": data["leads"][0]["stage_label"],
            "owner": "Nora Counselor",
            "href": f"/overseas/counselor/leads/{mine.id}",
        }
    ]
    assert data["leads"][0]["stage_label"] and data["leads"][0]["stage_label"] != "application_enrollment"

    await login(client, world["other"].email)  # in scope through the foreign application, but not the lead's owner: no link (B2)
    assert (await client.get(url(student.id, "activities"))).json()["leads"][0]["href"] is None


@pytest.mark.asyncio
async def test_history_merges_status_changes_audit_rows_and_document_events_newest_first(client, db_session, world):
    student, counselor = world["student"], world["counselor"]
    base = datetime.now(UTC) - timedelta(hours=3)
    db_session.add(
        ApplicationStatusHistory(application_id=world["foreign"].id, from_status="offer", to_status="visa_documentation", changed_by_id=world["other"].id, notes="internal", created_at=base)
    )
    db_session.add(
        AuditLog(
            user_id=counselor.id,
            action="overseas_student_profile.update",
            entity_type="user",
            entity_id=str(student.id),
            metadata_json={"fields": ["nationality"], "role": "counselor"},
            created_at=base + timedelta(hours=1),
        )
    )
    doc = await mk_document(db_session, student, world["own"])
    db_session.add(AuditLog(user_id=student.id, action="document.upload", entity_type="student_document", entity_id=str(doc.id), created_at=base + timedelta(hours=2)))
    db_session.add(AuditLog(user_id=counselor.id, action="document.download", entity_type="student_document", entity_id=str(doc.id), created_at=base + timedelta(hours=2, minutes=5)))
    db_session.add(AuditLog(user_id=counselor.id, action="unrelated.thing", entity_type="user", entity_id=str(student.id)))
    await db_session.commit()
    await login(client, counselor.email)
    items = (await client.get(url(student.id, "history"))).json()["items"]
    assert [i["kind"] for i in items] == ["document", "audit", "status"]  # downloads and unknown actions are not history
    upload, profile, status = items
    assert upload["actor"] == student.full_name and "Passport" in upload["summary"] and upload["application_code"] == world["own"].application_code
    assert profile["actor"] == "Nora Counselor" and "nationality" in profile["summary"].lower()
    assert status["actor"] == "Omar Counselor" and "Visa documentation" in status["summary"] and status["application_code"] == world["foreign"].application_code
    assert status["notes"] == "internal"


@pytest.mark.asyncio
async def test_the_students_section_and_admin_users_link_to_the_360(client, world):
    await login(client, world["counselor"].email)
    rows = (await client.get(PORTAL.format("counselor", "students"))).json()["rows"]
    row = next(r for r in rows if r.get("student_id") == str(world["student"].id))
    assert row["open"] == f"/overseas/counselor/students/{world['student'].id}"
    await login(client, world["admin"].email)
    rows = (await client.get(PORTAL.format("admin", "users"))).json()["rows"]
    row = next((r for r in rows if r["id"] == str(world["student"].id)), None)
    if row is not None:  # the directory pages; a fresh student is on the first page unless the test DB is crowded
        assert row["open"] == f"/overseas/admin/students/{world['student'].id}"
