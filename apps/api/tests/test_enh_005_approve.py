import json

import pytest
import pytest_asyncio
from enh005_helpers import login, mk_request, mk_result, mk_school, mk_staff, mk_user, move_student_directly
from sqlalchemy import func, select, update

from app.api import school_transfers
from app.core.database import SessionLocal
from app.models import (
    AuditLog,
    Notification,
    SchoolAcademicResult,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolResultStatusHistory,
    SchoolStudent,
    SchoolStudentTransferRequest,
    SchoolTestPrepRecord,
    User,
    UserRoleAssignment,
)

# ENH-005 spec §5.4: the approval transaction, D1 (parents), D3 (results), D4 (other records), S4 (audit), S5 (write set).

APPROVE = "/api/v1/overseas-admin/school-transfer-requests/{rid}/approve"
DECIDED = "This transfer request has already been decided"
STALE = "The student is no longer at the school this request was filed for; reject it and file a new one"
LOCK_BUSY = "Another change to this student is in progress; retry"


@pytest_asyncio.fixture
async def world(db_session):
    """School A (kid + sibling; kid has the teacher and a pending parent email) and school B. Parent P1 (account at A) is linked to the
    kid only; P2 (account at A) is linked to the kid AND the sibling. A pending request from A moves the kid to B."""
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B", students=0)
    kid, sibling = a["students"]
    p1 = a["parent"]
    p2 = await mk_user(db_session, role="school_parent", name="P2 two kids", school_id=a["school"].id, assigned_by=a["coordinator"])
    await db_session.flush()
    db_session.add_all(
        [
            SchoolParentLink(parent_user_id=p2.id, school_student_id=kid.id, linked_by_user_id=a["coordinator"].id),
            SchoolParentLink(parent_user_id=p2.id, school_student_id=sibling.id, linked_by_user_id=a["coordinator"].id),
        ]
    )
    kid.pending_parent_email = "pending.parent@example.local"
    await db_session.commit()
    request = await mk_request(db_session, kid, from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"], reason="Family is moving")
    staff_a = await mk_staff(db_session, a["school"], a["admin"])
    staff_b = await mk_staff(db_session, b["school"], a["admin"])
    return {"a": a, "b": b, "kid": kid, "sibling": sibling, "p1": p1, "p2": p2, "request": request, "staff_a": staff_a, "staff_b": staff_b, "admin": a["admin"]}


async def _approve(client, world, who=None):
    await login(client, (who or world["admin"]).email)
    return await client.post(APPROVE.format(rid=world["request"].id))


async def _fresh(db, model, pk):
    """Re-read one row from the database. `populate_existing` refreshes just that object; `expire_all()` would expire every fixture
    object too, and touching one afterwards is a lazy load that async SQLAlchemy forbids."""
    return await db.get(model, pk, populate_existing=True)


# ------------------------------------------------------------------------------------------ authority


@pytest.mark.asyncio
async def test_only_overseas_admin_and_super_admin_may_approve_and_everyone_else_changes_nothing(client, db_session, world):
    w = world
    assert (await client.post(APPROVE.format(rid=w["request"].id))).status_code == 401
    counselor = await mk_user(db_session, role="counselor", name="Counselor")
    await db_session.commit()
    for who in (w["a"]["coordinator"], w["b"]["coordinator"], w["a"]["teacher"], w["a"]["parent"], w["a"]["principal"], w["staff_a"], counselor):
        response = await _approve(client, w, who)
        assert response.status_code == 403, (who.role, response.text)
    request = await _fresh(db_session, SchoolStudentTransferRequest, w["request"].id)
    kid = await _fresh(db_session, SchoolStudent, w["kid"].id)
    assert (request.status, kid.school_id) == ("pending", w["a"]["school"].id)
    super_admin = await mk_user(db_session, role="super_admin", name="Super", division="global")
    await db_session.commit()
    assert (await _approve(client, w, super_admin)).status_code == 200


# ------------------------------------------------------------------------------------------ the move


@pytest.mark.asyncio
async def test_approval_moves_the_student_and_flips_every_scope(client, db_session, world):
    w = world
    response = await _approve(client, w)

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["status"], body["direction"], body["decided_by"]["id"]) == ("approved", "outgoing", str(w["admin"].id))
    assert (body["student_name"], body["from_school"]["id"], body["to_school"]["id"]) == (w["kid"].full_name, str(w["a"]["school"].id), str(w["b"]["school"].id))
    kid = await _fresh(db_session, SchoolStudent, w["kid"].id)
    assert kid.school_id == w["b"]["school"].id
    await login(client, w["a"]["coordinator"].email)
    assert (await client.get(f"/api/v1/school/students/{kid.id}")).status_code == 403  # the losing school lost it
    await login(client, w["b"]["coordinator"].email)
    assert (await client.get(f"/api/v1/school/students/{kid.id}")).status_code == 200  # the gaining school has it
    await login(client, w["staff_a"].email)
    assert kid.id not in {row["id"] for row in (await client.get("/api/v1/school/portfolio-students")).json()}
    await login(client, w["staff_b"].email)
    assert kid.id.__str__() in {row["id"] for row in (await client.get("/api/v1/school/portfolio-students")).json()}


@pytest.mark.asyncio
async def test_the_teacher_assignment_and_pending_parent_email_are_cleared_and_the_grade_is_kept(client, db_session, world):
    w = world
    before = await _fresh(db_session, SchoolStudent, w["kid"].id)
    assert before.assigned_teacher_user_id == w["a"]["teacher"].id and before.pending_parent_email
    grade, code = before.grade_or_class, before.student_code

    response = await _approve(client, w)

    assert response.json()["outcome"] == {"parents_moved": 1, "parents_kept": 1, "results_withdrawn": 0, "teacher_cleared": True, "pending_parent_email_cleared": True}
    kid = await _fresh(db_session, SchoolStudent, w["kid"].id)
    assert (kid.assigned_teacher_user_id, kid.pending_parent_email, kid.grade_or_class, kid.student_code) == (None, None, grade, code)


# ------------------------------------------------------------------------------------------ parents (D1) and the write set (S5)


@pytest.mark.asyncio
async def test_a_parent_moves_only_when_no_other_child_remains_and_every_link_is_kept(client, db_session, world):
    w = world
    await _approve(client, w)

    p1, p2 = await _fresh(db_session, User, w["p1"].id), await _fresh(db_session, User, w["p2"].id)
    assert p1.profile.get("school_id") == str(w["a"]["school"].id)  # never written to -- stays exactly as created
    assert p2.profile.get("school_id") == str(w["a"]["school"].id)
    links = {(row.parent_user_id, row.school_student_id) for row in (await db_session.scalars(select(SchoolParentLink).where(SchoolParentLink.school_student_id == w["kid"].id))).all()}
    assert links == {(w["p1"].id, w["kid"].id), (w["p2"].id, w["kid"].id)}
    for parent in (w["p1"], w["p2"]):  # both can still read the child, wherever their account is
        await login(client, parent.email)
        assert (await client.get(f"/api/v1/school/students/{w['kid'].id}")).status_code == 200
    await login(client, w["p2"].email)
    assert {row["id"] for row in (await client.get("/api/v1/school/students")).json()} == {str(w["kid"].id), str(w["sibling"].id)}


@pytest.mark.asyncio
async def test_approval_writes_nothing_on_any_linked_user_account(client, db_session, world):
    w = world
    odd = await mk_user(db_session, role="school_teacher", name="Teacher wrongly linked as a parent", school_id=w["a"]["school"].id, assigned_by=w["a"]["coordinator"])
    await db_session.flush()
    db_session.add(SchoolParentLink(parent_user_id=odd.id, school_student_id=w["kid"].id, linked_by_user_id=w["a"]["coordinator"].id))
    await db_session.commit()
    linked = [w["p1"].id, w["p2"].id, odd.id]

    async def snapshot():
        out = {}
        for uid in linked:
            u = await _fresh(db_session, User, uid)
            assignments = (await db_session.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uid))).all()
            out[uid] = (u.role, u.division, u.active, u.email, u.password_hash, u.full_name, u.profile, sorted((x.role, x.division, x.is_active, x.approval_status) for x in assignments))
        return out

    before = await snapshot()
    assert (await _approve(client, w)).status_code == 200
    assert await snapshot() == before


# ------------------------------------------------------------------------------------------ results (D3) and other records (D4)


@pytest.mark.asyncio
async def test_in_flight_results_are_withdrawn_with_history_and_published_ones_stay(client, db_session, world):
    w = world
    draft = await mk_result(db_session, w["kid"], w["staff_a"], "draft", "Draft")
    verified = await mk_result(db_session, w["kid"], w["staff_a"], "verified", "Verified")
    published = await mk_result(db_session, w["kid"], w["staff_a"], "published", "Published")
    other = await mk_result(db_session, w["sibling"], w["staff_a"], "draft", "Sibling draft")

    response = await _approve(client, w)

    assert response.json()["outcome"]["results_withdrawn"] == 2
    statuses = {}
    for r in (draft, verified, published, other):
        statuses[r.subject] = (await _fresh(db_session, SchoolAcademicResult, r.id)).status
    assert statuses == {"Draft": "withdrawn", "Verified": "withdrawn", "Published": "published", "Sibling draft": "draft"}
    history = (await db_session.scalars(select(SchoolResultStatusHistory).where(SchoolResultStatusHistory.result_id.in_([draft.id, verified.id])))).all()
    assert sorted((h.from_status, h.to_status, h.changed_by_user_id) for h in history) == sorted([("draft", "withdrawn", w["admin"].id), ("verified", "withdrawn", w["admin"].id)])
    await login(client, w["b"]["coordinator"].email)  # the gaining school sees the published result, never the withdrawn ones
    assert [r["subject"] for r in (await client.get("/api/v1/school/results")).json()] == ["Published"]


@pytest.mark.asyncio
async def test_career_psychometric_test_prep_and_language_records_follow_the_student_unchanged(client, db_session, world):
    w = world
    kid = w["kid"].id
    db_session.add_all(
        [
            SchoolCareerRecord(school_student_id=kid, career_counselor_user_id=w["staff_a"].id, record_type="guidance_session", notes="career note"),
            SchoolPsychometricRecord(school_student_id=kid, psychometric_team_user_id=w["staff_a"].id, assessment_type="aptitude"),
            SchoolTestPrepRecord(school_student_id=kid, academic_team_user_id=w["staff_a"].id, test_type="IELTS"),
            SchoolLanguageRecord(school_student_id=kid, academic_team_user_id=w["staff_a"].id, language="German"),
        ]
    )
    await db_session.commit()
    models = (SchoolCareerRecord, SchoolPsychometricRecord, SchoolTestPrepRecord, SchoolLanguageRecord)

    async def rows():
        return [[(r.id, r.school_student_id) for r in (await db_session.scalars(select(m).where(m.school_student_id == kid))).all()] for m in models]

    before = await rows()
    assert (await _approve(client, w)).status_code == 200
    assert await rows() == before
    assert all(len(group) == 1 for group in before)


# ------------------------------------------------------------------------------------------ refusals leave everything alone


@pytest.mark.asyncio
async def test_a_second_approval_a_stale_request_and_an_unknown_id_change_nothing(client, db_session, world):
    w = world
    assert (await _approve(client, w)).status_code == 200
    again = await client.post(APPROVE.format(rid=w["request"].id))
    assert (again.status_code, again.json()) == (409, {"detail": DECIDED})
    assert (await client.post(APPROVE.format(rid="00000000-0000-0000-0000-000000000000"))).status_code == 404
    assert (await client.post(APPROVE.format(rid="not-a-uuid"))).status_code == 422


@pytest.mark.asyncio
async def test_a_stale_request_is_409_and_stays_pending(client, db_session, world):
    w = world
    c = await mk_school(db_session, label="C", students=0)
    await move_student_directly(db_session, w["kid"], c["school"])  # the student left A by some other route

    response = await _approve(client, w)

    assert (response.status_code, response.json()) == (409, {"detail": STALE})
    request = await _fresh(db_session, SchoolStudentTransferRequest, w["request"].id)
    kid = await _fresh(db_session, SchoolStudent, w["kid"].id)
    assert (request.status, request.decided_by_user_id, kid.school_id) == ("pending", None, c["school"].id)
    assert (await _fresh(db_session, User, w["p1"].id)).profile["school_id"] == str(w["a"]["school"].id)


@pytest.mark.asyncio
async def test_a_rejected_or_cancelled_request_cannot_be_approved(client, db_session, world):
    w = world
    for status in ("rejected", "cancelled"):
        await db_session.execute(update(SchoolStudentTransferRequest).where(SchoolStudentTransferRequest.id == w["request"].id).values(status=status))
        await db_session.commit()
        response = await _approve(client, w)
        assert (response.status_code, response.json()) == (409, {"detail": DECIDED}), status
    assert (await _fresh(db_session, SchoolStudent, w["kid"].id)).school_id == w["a"]["school"].id


# ------------------------------------------------------------------------------------------ audit, atomicity, notifications, locking


@pytest.mark.asyncio
async def test_audit_row_names_the_moved_and_kept_parents_and_leaks_nothing_else(client, db_session, world):
    w = world
    assert (await _approve(client, w)).status_code == 200

    transfer = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.student_transfer", AuditLog.entity_id == str(w["request"].id)))).all()
    assert len(transfer) == 1 and transfer[0].user_id == w["admin"].id and transfer[0].outcome == "recorded"
    meta = transfer[0].metadata_json
    assert meta["parents_moved"] == 1 and meta["parents_kept"] == 1 and "request_id" in meta
    assert meta["parents_moved_ids"] == [str(w["p1"].id)]
    assert meta["parents_kept_ids"] == [str(w["p2"].id)]
    # Scoped to this test's own (freshly-minted) parent IDs rather than a bare global count: the shared dev/demo database
    # (test_enh_001_academic_year.py's fixtures note there is no per-test transaction rollback here) still carries
    # "school.user_school_scope_changed" rows from before this change existed, so an unscoped count is never 0 in practice.
    no_scope_rows = await db_session.scalar(
        select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.user_school_scope_changed", AuditLog.entity_id.in_([str(w["p1"].id), str(w["p2"].id)]))
    )
    assert no_scope_rows == 0  # the old per-parent audit action is no longer written at all, for either of this transfer's parents
    blob = json.dumps([x.metadata_json for x in transfer])
    assert w["kid"].full_name not in blob and w["kid"].student_code not in blob and "Family is moving" not in blob


@pytest.mark.asyncio
async def test_a_failure_inside_the_transaction_leaves_everything_exactly_as_it_was(client, db_session, world, monkeypatch):
    w = world
    draft = await mk_result(db_session, w["kid"], w["staff_a"], "draft", "Draft")
    real_audit = school_transfers._audit

    def broken_audit(db, actor_id, action, entity_id, **kw):
        if action == "school.student_transfer":  # the last write, after the student, parents and results have all been changed
            raise RuntimeError("audit write failed")  # an audit that cannot be written must abort the whole move (fail-closed)
        real_audit(db, actor_id, action, entity_id, **kw)

    monkeypatch.setattr(school_transfers, "_audit", broken_audit)
    await login(client, w["admin"].email)
    with pytest.raises(RuntimeError, match="audit write failed"):  # surfaces through the ASGI test client as the 500 it is
        await client.post(APPROVE.format(rid=w["request"].id))

    assert (await _fresh(db_session, SchoolStudent, w["kid"].id)).school_id == w["a"]["school"].id
    student = await _fresh(db_session, SchoolStudent, w["kid"].id)
    assert (student.assigned_teacher_user_id, student.pending_parent_email) == (w["a"]["teacher"].id, "pending.parent@example.local")
    assert (await _fresh(db_session, User, w["p1"].id)).profile["school_id"] == str(w["a"]["school"].id)
    assert (await _fresh(db_session, SchoolAcademicResult, draft.id)).status == "draft"
    request = await _fresh(db_session, SchoolStudentTransferRequest, w["request"].id)
    assert (request.status, request.outcome) == ("pending", None)


@pytest.mark.asyncio
async def test_notifications_go_out_after_the_commit_and_a_failure_never_undoes_the_approval(client, db_session, world, monkeypatch):
    w = world
    assert (await _approve(client, w)).status_code == 200

    async def titles(user):
        return [n.title for n in (await db_session.scalars(select(Notification).where(Notification.user_id == user.id))).all()]

    for recipient in (w["a"]["coordinator"], w["b"]["coordinator"], w["p1"], w["p2"]):
        sent = await titles(recipient)
        assert any(w["kid"].full_name in t for t in sent), (recipient.role, sent)  # approval notices name the student

    # A second world whose notification step blows up: the transfer still stands.
    async def boom(*args, **kwargs):
        raise RuntimeError("smtp exploded")

    monkeypatch.setattr(school_transfers, "_notify_transfer_approved", boom)
    w2 = await _second_world(db_session)
    await login(client, w2["admin"].email)
    response = await client.post(APPROVE.format(rid=w2["request"].id))
    assert response.status_code == 200, response.text
    assert (await _fresh(db_session, SchoolStudent, w2["kid"].id)).school_id == w2["b"]["school"].id


async def _second_world(db_session):
    a = await mk_school(db_session, label="A2")
    b = await mk_school(db_session, label="B2", students=0)
    request = await mk_request(db_session, a["students"][0], from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"])
    return {"a": a, "b": b, "kid": a["students"][0], "request": request, "admin": a["admin"]}


@pytest.mark.asyncio
async def test_a_lock_wait_past_the_timeout_is_409_and_changes_nothing(client, db_session, world, monkeypatch):
    w = world
    monkeypatch.setattr(school_transfers, "TRANSFER_LOCK_TIMEOUT", "300ms")
    holder = SessionLocal()
    try:
        await holder.execute(select(SchoolStudent).where(SchoolStudent.id == w["kid"].id).with_for_update())  # another change holds the student row
        response = await _approve(client, w)
    finally:
        await holder.rollback()
        await holder.close()

    assert (response.status_code, response.json()) == (409, {"detail": LOCK_BUSY})
    assert (await _fresh(db_session, SchoolStudentTransferRequest, w["request"].id)).status == "pending"
    assert (await _fresh(db_session, SchoolStudent, w["kid"].id)).school_id == w["a"]["school"].id
