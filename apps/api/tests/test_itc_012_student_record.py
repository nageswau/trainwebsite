"""itc-012 (DEC-SCOPE-345) -- the IT student record: a structured profile (DOB, address, city, qualification, graduation year, emergency
contact) and per-enrolment start/end date and delivery-mode overrides that default to the batch's. The student edits their own profile,
the IT counselor only their linked students' (itc-003), the IT Admin any IT student's; trainers and HR get no route (C1, Q-11)."""

import datetime

import pytest
from sqlalchemy import select

from app.models import AuditLog, Batch, ItStudentCounselor
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, enrol, make_counselor, make_student

ME = "/api/v1/it/me/profile"
CONTACT = {"emergency_contact_name": "Ravi Kumar", "emergency_contact_relation": "Father", "emergency_contact_phone": "+91 98765 43210"}
FULL = {"date_of_birth": "2001-04-05", "address": "12 MG Road", "city": "Bengaluru", "qualification": "B.Tech CSE", "graduation_year": 2023, **CONTACT}


def counselor_url(student_id, tail: str = "/profile") -> str:
    return f"/api/v1/counselor/it/students/{student_id}{tail}"


def admin_url(student_id, tail: str = "/profile") -> str:
    return f"/api/v1/admin/it/students/{student_id}{tail}"


async def it_counselor_with_student(db):
    counselor = await make_counselor(db, "it")
    student = await make_student(db)
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()
    return counselor, student


# --- AC1 / +: the student saves and validates their own profile ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_unsaved_profile_reads_empty_and_the_student_adds_an_emergency_contact(client, db_session):
    student = await make_student(db_session)
    await as_user(client, student)
    body = (await client.get(ME)).json()
    assert body["student"]["id"] == str(student.id) and body["profile"]["exists"] is False
    assert body["profile"]["emergency_contact_name"] is None and body["enrollments"] == []

    response = await client.patch(ME, json=FULL)
    assert response.status_code == 200, response.text
    profile = (await client.get(ME)).json()["profile"]
    assert profile["exists"] is True and profile["updated_by_name"] == student.full_name
    assert {k: profile[k] for k in FULL} == FULL

    assert (await client.patch(ME, json={"city": "Mysuru"})).status_code == 200  # partial: the rest is kept
    profile = (await client.get(ME)).json()["profile"]
    assert profile["city"] == "Mysuru" and profile["emergency_contact_phone"] == CONTACT["emergency_contact_phone"]


@pytest.mark.asyncio
async def test_a_save_is_audited_with_field_names_only_never_values(client, db_session):
    student = await make_student(db_session)
    await as_user(client, student)
    assert (await client.patch(ME, json=CONTACT)).status_code == 200
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.student_profile.update", AuditLog.entity_id == str(student.id)))
    assert audit.metadata_json == {"fields": sorted(CONTACT), "role": "it_student"}
    assert "Ravi" not in str(audit.metadata_json) and "98765" not in str(audit.metadata_json)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("emergency_contact_phone", "call me"),
        ("emergency_contact_phone", "12345"),
        ("date_of_birth", (datetime.date.today() + datetime.timedelta(days=1)).isoformat()),
        ("date_of_birth", "1899-12-31"),
        ("graduation_year", 1949),
        ("graduation_year", datetime.date.today().year + 7),
        ("address", "x" * 301),
        ("emergency_contact_relation", "y" * 61),
        ("unknown_field", "x"),
    ],
)
async def test_invalid_values_are_refused(client, db_session, field, value):
    student = await make_student(db_session)
    await as_user(client, student)
    response = await client.patch(ME, json={field: value})
    assert response.status_code == 422, response.text
    assert (await client.get(ME)).json()["profile"]["exists"] is False


@pytest.mark.asyncio
async def test_blank_text_clears_a_field(client, db_session):
    student = await make_student(db_session)
    await as_user(client, student)
    await client.patch(ME, json=FULL)
    assert (await client.patch(ME, json={"address": "  ", "emergency_contact_phone": ""})).status_code == 200
    profile = (await client.get(ME)).json()["profile"]
    assert profile["address"] is None and profile["emergency_contact_phone"] is None


@pytest.mark.asyncio
async def test_only_an_it_student_has_my_profile(client, db_session):
    for user in (await make_student(db_session, "overseas"), await make_user(db_session, "trainer", "it"), await make_counselor(db_session, "it")):
        await as_user(client, user)
        assert (await client.get(ME)).status_code == 403
        assert (await client.patch(ME, json={"city": "X"})).status_code == 403


# --- AuthZ: counselor scope, admin, and roles with no route ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_linked_it_counselor_reads_and_edits_and_an_unlinked_student_is_404(client, db_session):
    counselor, student = await it_counselor_with_student(db_session)
    other = await make_student(db_session)
    await as_user(client, counselor)
    response = await client.patch(counselor_url(student.id), json=CONTACT)
    assert response.status_code == 200, response.text
    assert response.json()["profile"]["updated_by_name"] == counselor.full_name
    assert (await client.get(counselor_url(student.id))).json()["profile"]["emergency_contact_name"] == "Ravi Kumar"
    assert (await client.get(counselor_url(other.id))).status_code == 404
    assert (await client.patch(counselor_url(other.id), json={"city": "X"})).status_code == 404


@pytest.mark.asyncio
async def test_the_it_admin_reads_any_it_student_and_a_non_it_student_is_404(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    student, overseas = await make_student(db_session), await make_student(db_session, "overseas")
    await as_user(client, admin)
    assert (await client.patch(admin_url(student.id), json={"city": "Pune"})).status_code == 200
    assert (await client.get(admin_url(student.id))).json()["profile"]["city"] == "Pune"
    assert (await client.get(admin_url(overseas.id))).status_code == 404


@pytest.mark.asyncio
async def test_a_trainer_hr_overseas_counselor_and_super_admin_get_no_emergency_contact(client, db_session):
    counselor, student = await it_counselor_with_student(db_session)
    await as_user(client, student)
    await client.patch(ME, json=CONTACT)
    for role, division in (("trainer", "it"), ("hr_team", "it"), ("placement_team", "it"), ("super_admin", "it"), ("overseas_admin", "overseas")):
        await as_user(client, await make_user(db_session, role, division))
        for url in (counselor_url(student.id), admin_url(student.id)):
            response = await client.get(url)
            assert response.status_code == 403, (role, url)
            assert "Ravi" not in response.text
    await as_user(client, await make_counselor(db_session, "overseas"))
    assert (await client.get(counselor_url(student.id))).status_code == 403
    assert (await client.get(admin_url(student.id))).status_code == 403


# --- AC2 / E: enrolment overrides ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_overrides_default_to_the_batch_and_a_batch_change_does_not_overwrite_them(client, db_session):
    counselor, student = await it_counselor_with_student(db_session)
    first, second = await enrol(db_session, student), await enrol(db_session, student)
    batch = await db_session.get(Batch, first.batch_id)
    batch_start, batch_end = batch.start_date, batch.end_date
    await as_user(client, counselor)

    rows = {e["id"]: e for e in (await client.get(counselor_url(student.id))).json()["enrollments"]}
    assert set(rows) == {str(first.id), str(second.id)}
    assert rows[str(first.id)]["start_date"] == batch_start.isoformat() and rows[str(first.id)]["start_date_override"] is None
    assert rows[str(first.id)]["delivery_mode"] == batch.mode

    override = {"start_date": (batch_start + datetime.timedelta(days=7)).isoformat(), "delivery_mode": "Offline"}
    response = await client.patch(counselor_url(student.id, f"/enrollments/{first.id}"), json=override)
    assert response.status_code == 200, response.text

    batch.start_date, batch.end_date, batch.mode = batch_start + datetime.timedelta(days=30), batch_end + datetime.timedelta(days=30), "Online"
    await db_session.commit()

    rows = {e["id"]: e for e in (await client.get(counselor_url(student.id))).json()["enrollments"]}
    one = rows[str(first.id)]
    assert (one["start_date"], one["start_date_override"], one["delivery_mode"]) == (override["start_date"], override["start_date"], "Offline")
    assert one["end_date"] == (batch_end + datetime.timedelta(days=30)).isoformat()  # not overridden: follows the batch
    assert rows[str(second.id)]["start_date_override"] is None

    assert (await client.patch(counselor_url(student.id, f"/enrollments/{first.id}"), json={"start_date": None})).status_code == 200
    one = {e["id"]: e for e in (await client.get(counselor_url(student.id))).json()["enrollments"]}[str(first.id)]
    assert one["start_date"] == batch.start_date.isoformat() and one["delivery_mode"] == "Offline"

    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.enrollment.dates_update", AuditLog.entity_id == str(first.id)).order_by(AuditLog.created_at))
    assert audit.metadata_json["changes"]["start_date"] == [None, override["start_date"]]


@pytest.mark.asyncio
async def test_the_student_sees_their_effective_dates_but_cannot_override(client, db_session):
    student = await make_student(db_session)
    row = await enrol(db_session, student)
    await as_user(client, student)
    enrollments = (await client.get(ME)).json()["enrollments"]
    assert [e["id"] for e in enrollments] == [str(row.id)]
    assert (await client.patch(ME, json={"start_date": "2030-01-01"})).status_code == 422  # not a profile field


@pytest.mark.asyncio
async def test_override_validation_and_scope(client, db_session):
    admin = await make_user(db_session, "it_admin", "it")
    student, other = await make_student(db_session), await make_student(db_session)
    row, others = await enrol(db_session, student), await enrol(db_session, other)
    batch = await db_session.get(Batch, row.batch_id)
    await as_user(client, admin)
    url = admin_url(student.id, f"/enrollments/{row.id}")
    before = (batch.start_date - datetime.timedelta(days=1)).isoformat()
    assert (await client.patch(url, json={"end_date": before})).status_code == 422  # ends before the (batch) start
    assert (await client.patch(url, json={"delivery_mode": "Teleport"})).status_code == 422
    assert (await client.patch(admin_url(student.id, f"/enrollments/{others.id}"), json={"delivery_mode": "Online"})).status_code == 404
    assert (await client.patch(url, json={"delivery_mode": "Hybrid"})).status_code == 200

    counselor, mine = await it_counselor_with_student(db_session)
    await as_user(client, counselor)
    assert (await client.patch(counselor_url(student.id, f"/enrollments/{row.id}"), json={"delivery_mode": "Online"})).status_code == 404
    await as_user(client, student)
    assert (await client.patch(admin_url(student.id, f"/enrollments/{row.id}"), json={"delivery_mode": "Online"})).status_code == 403


# --- Portal: the staff tables link the profile page ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_counselor_and_admin_student_tables_link_the_profile(client, db_session):
    counselor, student = await it_counselor_with_student(db_session)
    await as_user(client, counselor)
    payload = (await client.get("/api/v1/portal/it/counselor/students")).json()
    assert {"key": "profile", "label": "", "type": "student_profile"} in payload["columns"]
    row = next(r for r in payload["rows"] if r["id"] == str(student.id))
    assert row["profile"] == f"/it/counselor/students/{student.id}/profile"

    await as_user(client, await make_user(db_session, "it_admin", "it"))
    payload = (await client.get("/api/v1/portal/it/admin/students")).json()
    row = next(r for r in payload["rows"] if r["id"] == str(student.id))
    assert row["profile"] == f"/it/admin/students/{student.id}/profile"
