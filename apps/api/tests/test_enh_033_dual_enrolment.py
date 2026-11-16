"""ENH-033 (DEC-SCOPE-441, D1-D9) -- dual enrolment: a target-division counselor or telecaller adds IT or Overseas to an existing
student on the same login; the student switches portals; staff of each division still find them whatever portal is active."""

import secrets

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import AuditLog, ItStudentCounselor, Notification, OverseasStudentCounselor, Payment, User, UserRoleAssignment
from app.services import student_access
from tests.agn001_helpers import login, mk_user, uniq


def enrol_url(division: str) -> str:
    return f"/api/v1/workflows/{division}/dual-enrolment"


async def it_student(db, **kw) -> User:
    student = await mk_user(db, role="it_student", division="it", full_name=kw.pop("full_name", f"{uniq('e33')} IT"), **kw)
    student.student_code = secrets.token_hex(4).upper()
    await db.commit()
    return student


async def overseas_student(db, **kw) -> User:
    student = await mk_user(db, role="overseas_student", full_name=kw.pop("full_name", f"{uniq('e33')} OVS"), **kw)
    student.student_code = secrets.token_hex(4).upper()
    await db.commit()
    return student


async def fresh(db, user: User) -> User:
    return await db.scalar(select(User).where(User.id == user.id).execution_options(populate_existing=True))


async def rows(db, user: User) -> set[tuple[str, str, bool]]:
    found = (await db.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == user.id).execution_options(populate_existing=True))).all()
    return {(r.division, r.role, r.is_active) for r in found}


async def notes(db, user: User, title: str) -> int:
    return await db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.title == title))


async def make_dual(client, db, *, start: str = "it"):
    """A student of `start` who an other-division counselor adds to the other division. Returns (student, counselor)."""
    target = "overseas" if start == "it" else "it"
    student = await (it_student(db) if start == "it" else overseas_student(db))
    counselor = await mk_user(db, role="counselor", division=target)
    await login(client, counselor.email, target)
    response = await client.post(enrol_url(target), json={"student_id": str(student.id), "counselor_id": str(counselor.id), "student_requested": True})
    assert response.status_code == 201, response.text
    return student, counselor


# --- AC1 / AC2 / AC8: adding a division --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_overseas_counselor_adds_overseas_to_an_it_student(client, db_session):
    student = await it_student(db_session)
    counselor = await mk_user(db_session, role="counselor", division="overseas", full_name="Ovs Counselor")
    await login(client, counselor.email)

    by_email = await client.get(f"{enrol_url('overseas')}/lookup", params={"ref": student.email.upper()})
    by_code = await client.get(f"{enrol_url('overseas')}/lookup", params={"ref": student.student_code.lower()})
    assert by_email.status_code == 200, by_email.text
    assert by_email.json() == by_code.json() == {"id": str(student.id), "full_name": student.full_name, "student_code": student.student_code, "divisions": ["it"]}

    response = await client.post(enrol_url("overseas"), json={"student_id": str(student.id), "counselor_id": str(counselor.id), "student_requested": True})
    assert response.status_code == 201, response.text
    assert response.json() == {"student_id": str(student.id), "division": "overseas", "counselor_id": str(counselor.id), "counselor_name": "Ovs Counselor"}

    after = await fresh(db_session, student)
    assert (after.role, after.division, after.student_code, after.password_hash) == ("it_student", "it", student.student_code, student.password_hash)  # D4
    assert await rows(db_session, student) == {("it", "it_student", True), ("overseas", "overseas_student", True)}  # the source row too
    link = await db_session.scalar(select(OverseasStudentCounselor).where(OverseasStudentCounselor.student_user_id == student.id))
    assert (link.counselor_user_id, link.assigned_by_user_id) == (counselor.id, counselor.id)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "student.dual_enrol", AuditLog.entity_id == str(student.id)))
    assert audit.user_id == counselor.id
    assert audit.metadata_json == {"division": "overseas", "counselor_id": str(counselor.id), "student_requested": True, "by_role": "counselor"}
    assert await notes(db_session, student, "You are now enrolled in Overseas") == 1
    assert await notes(db_session, counselor, "Student assigned to you") == 1


@pytest.mark.asyncio
async def test_a_telecaller_adds_with_another_counselor_and_the_reverse_direction_works(client, db_session):
    student = await overseas_student(db_session)
    telecaller = await mk_user(db_session, role="telecaller", division="it")
    counselor = await mk_user(db_session, role="counselor", division="it")
    await login(client, telecaller.email, "it")
    picker = await client.get("/api/v1/lookups/it-counselors", params={"q": counselor.full_name})
    assert picker.status_code == 200 and str(counselor.id) in [i["id"] for i in picker.json()["items"]]
    response = await client.post(enrol_url("it"), json={"student_id": str(student.id), "counselor_id": str(counselor.id), "student_requested": True})
    assert response.status_code == 201, response.text
    assert await rows(db_session, student) == {("overseas", "overseas_student", True), ("it", "it_student", True)}
    link = await db_session.scalar(select(ItStudentCounselor).where(ItStudentCounselor.student_user_id == student.id))
    assert (link.counselor_user_id, link.assigned_by_user_id) == (counselor.id, telecaller.id)
    assert await notes(db_session, student, "You are now enrolled in IT") == 1


# --- AC3: refusals -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "it"), ("telecaller", "it"), ("overseas_admin", "overseas"), ("super_admin", "global"), ("it_student", "it")])
async def test_only_target_division_counselors_and_telecallers_may_add(client, db_session, role, division):
    student = await it_student(db_session)
    counselor = await mk_user(db_session, role="counselor", division="overseas")
    caller = await mk_user(db_session, role=role, division=division)
    await login(client, caller.email, division)
    body = {"student_id": str(student.id), "counselor_id": str(counselor.id), "student_requested": True}
    assert (await client.post(enrol_url("overseas"), json=body)).status_code == 403
    assert (await client.get(f"{enrol_url('overseas')}/lookup", params={"ref": student.email})).status_code == 403
    assert await rows(db_session, student) == set()


@pytest.mark.asyncio
async def test_bad_requests_are_refused_and_nothing_is_written(client, db_session):
    student = await it_student(db_session)
    counselor = await mk_user(db_session, role="counselor", division="overseas")
    it_counselor = await mk_user(db_session, role="counselor", division="it")
    gone = await mk_user(db_session, role="counselor", division="overseas", active=False)
    trainer = await mk_user(db_session, role="trainer", division="it")
    inactive = await it_student(db_session, active=False)
    already = await overseas_student(db_session)
    await login(client, counselor.email)

    def body(**kw):
        return {"student_id": str(student.id), "counselor_id": str(counselor.id), "student_requested": True} | kw

    no_tick = await client.post(enrol_url("overseas"), json=body(student_requested=False))
    assert no_tick.status_code == 422 and no_tick.json()["detail"] == "Confirm the student asked to enrol"
    assert (await client.post(enrol_url("overseas"), json=body(counselor_id=str(it_counselor.id)))).status_code == 422
    assert (await client.post(enrol_url("overseas"), json=body(counselor_id=str(gone.id)))).status_code == 422
    for who in (trainer, inactive, already):  # not a student of the other division: the same 404 as an unknown id
        response = await client.post(enrol_url("overseas"), json=body(student_id=str(who.id)))
        assert response.status_code == 404 and response.json()["detail"] == "No student found"
        assert (await client.get(f"{enrol_url('overseas')}/lookup", params={"ref": who.email})).status_code == 404
    assert (await client.get(f"{enrol_url('overseas')}/lookup", params={"ref": "nope"})).status_code == 422
    assert (await client.post(enrol_url("abroad"), json=body())).status_code == 422
    assert await rows(db_session, student) == set()
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "student.dual_enrol", AuditLog.entity_id == str(student.id))) == 0


@pytest.mark.asyncio
async def test_a_second_add_and_an_ended_division_are_conflicts(client, db_session):
    student, counselor = await make_dual(client, db_session)
    again = await client.post(enrol_url("overseas"), json={"student_id": str(student.id), "counselor_id": str(counselor.id), "student_requested": True})
    assert again.status_code == 409 and again.json()["detail"] == "Already enrolled in Overseas"

    ended = await it_student(db_session)
    db_session.add(UserRoleAssignment(user_id=ended.id, division="overseas", role="overseas_student", is_active=False, approval_status="approved"))
    await db_session.commit()
    response = await client.post(enrol_url("overseas"), json={"student_id": str(ended.id), "counselor_id": str(counselor.id), "student_requested": True})
    assert response.status_code == 409 and response.json()["detail"] == "This student's Overseas access was ended; ask an admin"


# --- AC4 / AC5: switching and login ------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_dual_student_switches_portals_and_back(client, db_session):
    student, _ = await make_dual(client, db_session)
    await login(client, student.email, "it")
    me = (await client.get("/api/v1/auth/me")).json()
    assert (me["role"], me["division"]) == ("it_student", "it")
    assert {(a["division"], a["role"]) for a in me["role_assignments"] if a["is_active"]} == {("it", "it_student"), ("overseas", "overseas_student")}

    switched = await client.post("/api/v1/auth/switch-portal", json={"division": "overseas"})
    assert switched.status_code == 200, switched.text
    assert (switched.json()["user"]["role"], switched.json()["user"]["division"]) == ("overseas_student", "overseas")
    assert (await client.get("/api/v1/portal/overseas/student/dashboard")).status_code == 200
    assert (await client.get("/api/v1/portal/it/student/dashboard")).status_code == 403  # caller gates follow the active portal (AC7)
    assert (await client.post("/api/v1/auth/switch-portal", json={"division": "overseas"})).status_code == 200  # no-op
    back = await client.post("/api/v1/auth/switch-portal", json={"division": "it"})
    assert back.status_code == 200 and back.json()["user"]["role"] == "it_student"
    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "auth.switch_portal", AuditLog.entity_id == str(student.id)).order_by(AuditLog.created_at))).all()
    assert [a.metadata_json for a in audits] == [{"from": "it", "to": "overseas"}, {"from": "overseas", "to": "it"}]


@pytest.mark.asyncio
async def test_the_login_page_decides_for_a_dual_student_only(client, db_session):
    student, _ = await make_dual(client, db_session)
    await login(client, student.email, "overseas")  # D8: active portal was IT
    assert (await fresh(db_session, student)).role == "overseas_student"
    await login(client, student.email, "it")
    assert (await fresh(db_session, student)).role == "it_student"

    single = await it_student(db_session)
    from tests.agn001_helpers import PASSWORD

    wrong = await client.post("/api/v1/auth/login", json={"email": single.email, "password": PASSWORD, "division": "overseas"})
    assert wrong.status_code == 403 and "/it/login" in wrong.json()["detail"]
    await login(client, single.email, "it")
    refused = await client.post("/api/v1/auth/switch-portal", json={"division": "overseas"})
    assert refused.status_code == 403 and refused.json()["detail"] == "You are not enrolled in Overseas"
    counselor = await mk_user(db_session, role="counselor", division="it")
    await login(client, counselor.email, "it")
    assert (await client.post("/api/v1/auth/switch-portal", json={"division": "it"})).status_code == 403  # staff: never


# --- AC6 / AC7 / D9: subject checks, sets, payment lock and the active portal's money ---------------------------------------------


@pytest.mark.asyncio
async def test_overseas_staff_still_find_a_dual_student_in_the_it_portal(client, db_session):
    student, counselor = await make_dual(client, db_session)  # active portal: IT
    assert (await fresh(db_session, student)).role == "it_student"
    await login(client, counselor.email)
    mine = (await client.get("/api/v1/counselor/students", params={"q": student.full_name})).json()
    assert [i["id"] for i in mine["items"]] == [str(student.id)]  # once
    assert (await client.get(f"/api/v1/counselor/students/{student.id}/notes")).status_code == 200
    assert (await client.get(f"/api/v1/counselor/students/{student.id}/profile")).status_code == 200
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, admin.email)
    found = (await client.get("/api/v1/lookups/overseas-students", params={"q": student.full_name})).json()["items"]
    assert [i["id"] for i in found] == [str(student.id)]


@pytest.mark.asyncio
async def test_it_staff_still_find_a_dual_student_in_the_overseas_portal(client, db_session):
    student, counselor = await make_dual(client, db_session, start="overseas")  # active portal: Overseas
    await login(client, counselor.email, "it")
    mine = (await client.get("/api/v1/counselor/it/students", params={"q": student.full_name})).json()
    assert [i["id"] for i in mine["items"]] == [str(student.id)]
    assert (await client.get(f"/api/v1/counselor/it/students/{student.id}")).status_code == 200


@pytest.mark.asyncio
async def test_the_it_payment_lock_holds_from_the_overseas_portal(client, db_session):
    student, _ = await make_dual(client, db_session)
    await login(client, student.email, "overseas")
    student = await fresh(db_session, student)
    assert student.role == "overseas_student"
    with pytest.raises(HTTPException) as refused:
        await student_access.require(db_session, student, "assignments")  # registered, no enrolment: locked
    assert refused.value.status_code == 403 and refused.value.detail["code"] == "payment_required"
    plain = await overseas_student(db_session)
    await student_access.require(db_session, plain, "assignments")  # a single-division overseas student is not an IT student


@pytest.mark.asyncio
async def test_each_portal_shows_only_its_own_payments(client, db_session):
    student, _ = await make_dual(client, db_session)
    it_pay = Payment(user_id=student.id, division="it", reference_type="fee", amount=100, status="pending")
    ovs_pay = Payment(user_id=student.id, division="overseas", reference_type="fee", amount=200, status="pending")
    db_session.add_all([it_pay, ovs_pay])
    await db_session.commit()
    await login(client, student.email, "it")
    assert [p["id"] for p in (await client.get("/api/v1/payments/mine")).json()] == [str(it_pay.id)]
    assert (await client.get(f"/api/v1/payments/{ovs_pay.id}/receipt")).status_code == 404
    await login(client, student.email, "overseas")
    assert [p["id"] for p in (await client.get("/api/v1/payments/mine")).json()] == [str(ovs_pay.id)]
