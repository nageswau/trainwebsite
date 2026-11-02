"""itc-028 (DEC-SCOPE-351) -- internal vs student-visible IT student notes (spec docs/superpowers/specs/2026-11-02-itc-028-it-student-
notes-design.md N1-N9). Staff (the itc-003 counselor, HR in the nehn-017 pool, the student's trainer, the IT Admin) write notes that start
internal; only the author or the IT Admin shares one with the student, audited; the student reads shared notes in GET /it/me/updates.
AC1: an internal note never reaches any student response or notification (the sweep at the end)."""

import uuid

import pytest
from sqlalchemy import select

from app.core import rbac
from app.main import app
from app.models import AuditLog, Batch, ItStudentCounselor, Notification, UserPermissionOverride
from tests.bdm001_helpers import make_user
from tests.tel018_helpers import enrol, make_student
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
FEED = "/api/v1/it/me/updates"
FEED_KEYS = {"id", "body", "author_name", "author_role", "shared_at"}
# lib/navigation.ts "it/student" (with itc-028's Updates)
IT_STUDENT_SECTIONS = ("dashboard", "profile", "course", "attendance", "assignments", "projects", "examinations", "certificates", "feedback", "questions",
                       "timetable", "fees", "interview-schedule", "placement-status", "job-applications", "downloads", "support", "notifications", "updates")  # fmt: skip


def notes_url(student_id, tail: str = "") -> str:
    return f"/api/v1/it/students/{student_id}/notes{tail}"


async def _world(db):
    """A student linked to a counselor, seated in a trainer's batch, in the HR pool; plus the IT Admin and an unrelated student."""
    student = await make_student(db)
    counselor = await make_user(db, "counselor", "it")
    db.add(ItStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    trainer = await make_user(db, "trainer", "it")
    seat = await enrol(db, student)
    batch = await db.get(Batch, seat.batch_id)
    batch.trainer_id = trainer.id
    await db.commit()
    return {
        "student": student, "counselor": counselor, "trainer": trainer, "hr": await make_user(db, "hr_team", "it"),
        "admin": await make_user(db, "it_admin", "it"), "other": await make_student(db),
    }  # fmt: skip


async def _add(client, author, student, body: str = "Discussed the Python module.") -> dict:
    response = await client.post(notes_url(student.id), headers=headers(author), json={"body": body})
    assert response.status_code == 201, response.text
    return response.json()


async def _share(client, actor, student, note_id, visibility: str = "student"):
    return await client.put(notes_url(student.id, f"/{note_id}/visibility"), headers=headers(actor), json={"visibility": visibility})


# --- N2 / N4: staff write and read, internal by default ------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["counselor", "trainer", "hr", "admin"])
async def test_each_staff_role_adds_an_internal_note_and_reads_everyones(client, db_session, role):
    w = await _world(db_session)
    first = await _add(client, w["counselor"], w["student"], "Counselor's first note")
    note = await _add(client, w[role], w["student"], f"A note by {role}")
    assert note["visibility"] == "internal" and note["shared_at"] is None and note["author_name"] == w[role].full_name
    page = (await client.get(notes_url(w["student"].id), headers=headers(w[role]))).json()
    assert page["student"]["id"] == str(w["student"].id) and page["total"] == 2
    ids = [item["id"] for item in page["items"]]
    assert note["id"] == ids[0] and first["id"] in ids  # N3: the shared record, newest first
    assert {item["author_role"] for item in page["items"]} <= {"counselor", "trainer", "hr_team", "it_admin"}


async def test_out_of_scope_staff_get_404_and_other_roles_get_403(client, db_session):
    w = await _world(db_session)
    other_counselor = await make_user(db_session, "counselor", "it")
    other_trainer = await make_user(db_session, "trainer", "it")
    for user in (other_counselor, other_trainer):
        assert (await client.get(notes_url(w["student"].id), headers=headers(user))).status_code == 404
        assert (await client.post(notes_url(w["student"].id), headers=headers(user), json={"body": "x"})).status_code == 404
    assert (await client.get(notes_url(uuid.uuid4()), headers=headers(w["admin"]))).status_code == 404
    assert (await client.get(notes_url(w["other"].id), headers=headers(w["counselor"]))).status_code == 404
    for role, division in (("counselor", "overseas"), ("placement_team", "it"), ("super_admin", "it"), ("overseas_admin", "overseas")):
        user = await make_user(db_session, role, division)
        assert (await client.get(notes_url(w["student"].id), headers=headers(user))).status_code == 403, role
    assert (await client.get(notes_url(w["student"].id), headers=headers(w["student"]))).status_code == 403
    assert (await client.get(notes_url(w["student"].id))).status_code == 401


async def test_hr_needs_the_progress_grant_and_the_pool(client, db_session):
    w = await _world(db_session)
    from app.models import PlacementProfile

    db_session.add(PlacementProfile(student_id=w["other"].id, withdrawn=True))  # outside the HR pool (nehn-017 H1)
    await db_session.commit()
    assert (await client.get(notes_url(w["other"].id), headers=headers(w["hr"]))).status_code == 404
    resource, action = rbac.parse_key("student_progress.view")
    db_session.add(UserPermissionOverride(user_id=w["hr"].id, resource=resource, action=action, effect="deny", reason="itc-028 test"))
    await db_session.commit()
    assert (await client.get(notes_url(w["student"].id), headers=headers(w["hr"]))).status_code == 403


async def test_a_trainer_loses_a_student_who_never_took_the_seat(client, db_session):
    w = await _world(db_session)
    pending = await make_student(db_session)
    seat = await enrol(db_session, pending, status="pending_consent")
    (await db_session.get(Batch, seat.batch_id)).trainer_id = w["trainer"].id
    await db_session.commit()
    assert (await client.get(notes_url(pending.id), headers=headers(w["trainer"]))).status_code == 404


@pytest.mark.parametrize(
    "body",
    [{"body": "   "}, {"body": "x" * 4001}, {}, {"body": "ok", "visibility": "student"}],
    ids=["blank", "too-long", "missing", "visibility-on-create"],
)
async def test_create_validation(client, db_session, body):
    w = await _world(db_session)
    response = await client.post(notes_url(w["student"].id), headers=headers(w["counselor"]), json=body)
    assert response.status_code == 422, response.text


async def test_the_list_pages(client, db_session):
    w = await _world(db_session)
    for n in range(3):
        await _add(client, w["counselor"], w["student"], f"note {n}")
    page = (await client.get(notes_url(w["student"].id, "?limit=2&offset=0"), headers=headers(w["counselor"]))).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (3, 2, 0, 2) and page["items"][0]["body"] == "note 2"
    rest = (await client.get(notes_url(w["student"].id, "?limit=2&offset=2"), headers=headers(w["counselor"]))).json()
    assert [item["body"] for item in rest["items"]] == ["note 0"]
    assert (await client.get(notes_url(w["student"].id, "?limit=101"), headers=headers(w["counselor"]))).status_code == 422


# --- N5 / N6 / N8: the explicit, audited share ------------------------------------------------------------------------------------


async def test_the_author_shares_a_note_it_is_audited_and_the_student_gets_a_generic_notice(client, db_session):
    w = await _world(db_session)
    note = await _add(client, w["hr"], w["student"], "Please add your GitHub link")  # the backlog's + case
    response = await _share(client, w["hr"], w["student"], note["id"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["changed"] is True and body["visibility"] == "student" and body["shared_at"]
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "it.student_note.visibility", AuditLog.entity_id == note["id"]))
    assert audit.user_id == w["hr"].id and audit.metadata_json["changes"] == {"visibility": ["internal", "student"]}
    assert audit.metadata_json["student_id"] == str(w["student"].id) and "GitHub" not in str(audit.metadata_json)
    notices = (await db_session.scalars(select(Notification).where(Notification.user_id == w["student"].id))).all()
    assert len(notices) == 1 and notices[0].event_type == "it.student.update_shared" and notices[0].action_url == "/it/student/updates"
    assert "GitHub" not in notices[0].title + notices[0].body

    again = await _share(client, w["hr"], w["student"], note["id"])  # a no-op: no audit, no notice
    assert again.status_code == 200 and again.json()["changed"] is False
    assert len((await db_session.scalars(select(AuditLog).where(AuditLog.action == "it.student_note.visibility", AuditLog.entity_id == note["id"]))).all()) == 1
    assert len((await db_session.scalars(select(Notification).where(Notification.user_id == w["student"].id))).all()) == 1


async def test_only_the_author_or_the_it_admin_changes_visibility(client, db_session):
    w = await _world(db_session)
    note = await _add(client, w["counselor"], w["student"])
    assert (await _share(client, w["trainer"], w["student"], note["id"])).status_code == 403
    listed = (await client.get(notes_url(w["student"].id), headers=headers(w["trainer"]))).json()["items"][0]
    assert listed["can_change_visibility"] is False
    assert (await client.get(notes_url(w["student"].id), headers=headers(w["counselor"]))).json()["items"][0]["can_change_visibility"] is True
    assert (await _share(client, w["admin"], w["student"], note["id"])).status_code == 200
    assert (await _share(client, w["student"], w["student"], note["id"])).status_code == 403


async def test_visibility_validation_and_another_students_note_is_404(client, db_session):
    w = await _world(db_session)
    note = await _add(client, w["admin"], w["student"])
    assert (await _share(client, w["admin"], w["student"], note["id"], "everyone")).status_code == 422
    assert (await _share(client, w["admin"], w["other"], note["id"])).status_code == 404  # the note belongs to another student
    assert (await _share(client, w["admin"], w["student"], uuid.uuid4())).status_code == 404


# --- N7: the student's feed ----------------------------------------------------------------------------------------------------


async def test_the_student_sees_only_their_own_shared_notes_with_allow_listed_fields_and_unsharing_hides_one(client, db_session):
    w = await _world(db_session)
    internal = await _add(client, w["counselor"], w["student"], "Internal: weak on SQL")
    shared = await _add(client, w["counselor"], w["student"], "Great progress this week")
    elsewhere = await _add(client, w["admin"], w["other"], "For the other student")
    for note, student in ((shared, w["student"]), (elsewhere, w["other"])):
        assert (await _share(client, w["admin"] if student is w["other"] else w["counselor"], student, note["id"])).status_code == 200
    feed = (await client.get(FEED, headers=headers(w["student"]))).json()
    assert feed["total"] == 1 and [item["id"] for item in feed["items"]] == [shared["id"]]
    assert set(feed["items"][0]) == FEED_KEYS and feed["items"][0]["author_role"] == "counselor"
    assert internal["body"] not in str(feed) and elsewhere["body"] not in str(feed)

    assert (await _share(client, w["counselor"], w["student"], shared["id"], "internal")).json()["changed"] is True
    assert (await client.get(FEED, headers=headers(w["student"]))).json()["total"] == 0
    assert len((await db_session.scalars(select(Notification).where(Notification.user_id == w["student"].id))).all()) == 1  # un-share is silent


async def test_the_feed_is_for_it_students_only(client, db_session):
    w = await _world(db_session)
    assert (await client.get(FEED, headers=headers(w["counselor"]))).status_code == 403
    assert (await client.get(FEED, headers=headers(await make_user(db_session, "overseas_student", "overseas")))).status_code == 403
    assert (await client.get(FEED)).status_code == 401


async def test_the_portal_links_the_notes_and_the_student_has_an_updates_section(client, db_session):
    w = await _world(db_session)
    sid = str(w["student"].id)
    mine = (await client.get("/api/v1/portal/it/counselor/students", headers=headers(w["counselor"]))).json()
    assert ("notes", "student_notes") in {(c["key"], c.get("type")) for c in mine["columns"]}
    assert next(r for r in mine["rows"] if r["id"] == sid)["notes"] == f"/it/counselor/students/{sid}/notes"
    admin = (await client.get(f"/api/v1/portal/it/admin/students?q={w['student'].email}", headers=headers(w["admin"]))).json()
    row = next((r for r in admin["rows"] if r["id"] == sid), None)
    assert row is None or row["notes"] == f"/it/admin/students/{sid}/notes"
    assert ("notes", "student_notes") in {(c["key"], c.get("type")) for c in admin["columns"]}
    updates = await client.get("/api/v1/portal/it/student/updates", headers=headers(w["student"]))
    assert updates.status_code == 200 and updates.json()["title"] == "Updates"


# --- AC1: the sweep -- no student response or notification carries internal text --------------------------------------------------


def _student_gets() -> list[str]:
    """Every parameter-less GET the API serves (the student's own reads among them), plus the IT student portal's sections."""
    paths = sorted(path for path, ops in app.openapi()["paths"].items() if "get" in ops and "{" not in path and path.startswith("/api/v1/"))
    return [*paths, *(f"/api/v1/portal/it/student/{section}" for section in IT_STUDENT_SECTIONS)]


async def test_an_internal_note_never_reaches_any_student_response_or_notification(client, db_session):
    w = await _world(db_session)
    internal_mark, shared_mark = f"Zq028internal{uuid.uuid4().hex[:6]}", f"Zq028shared{uuid.uuid4().hex[:6]}"
    for author in (w["counselor"], w["trainer"], w["hr"], w["admin"]):
        await _add(client, author, w["student"], f"{internal_mark} by {author.role}")
    shared = await _add(client, w["counselor"], w["student"], shared_mark)
    assert (await _share(client, w["counselor"], w["student"], shared["id"])).status_code == 200
    assert shared_mark in (await client.get(FEED, headers=headers(w["student"]))).text  # positive control: the sweep can see notes

    swept = 0
    for path in _student_gets():
        if path.endswith(("/logout", "/stream")):
            continue
        response = await client.get(path, headers=headers(w["student"]))
        assert internal_mark not in response.text, path
        swept += 1
    assert swept > 100
    for notice in (await db_session.scalars(select(Notification).where(Notification.user_id == w["student"].id))).all():
        assert internal_mark not in notice.title + notice.body and shared_mark not in notice.title + notice.body
