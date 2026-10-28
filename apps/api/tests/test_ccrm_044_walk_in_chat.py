"""ccrm-044 (DEC-SCOPE-320) -- counselor chat with walk-in students. The student's counselor-chat resolves the counselor of their latest
application, else their csc-001 linked counselor (409 only when neither exists); an overseas counselor's generic send to an overseas
student is limited to their caseload (`visible_student_ids`), and the picker (`/lookups/overseas-students`) lists that caseload."""

import pytest
from sqlalchemy import select

from app.models import Message, OverseasStudentArchive, OverseasStudentCounselor
from tests.agn001_helpers import login, mk_user
from tests.enh031_helpers import mk_application, mk_university

STUDENT_CHAT = "/api/v1/workflows/overseas/student/counselor-chat"
SEND = "/api/v1/communications/messages"


async def link(db, student, counselor):
    db.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=counselor.id))
    await db.commit()


async def sent_to(db, sender, recipient) -> list[Message]:
    return list((await db.scalars(select(Message).where(Message.sender_id == sender.id, Message.recipient_id == recipient.id))).all())


@pytest.mark.asyncio
async def test_counselor_sees_a_walk_in_in_the_picker_and_messages_them_ac1(client, db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Chat Counselor")
    walk_in = await mk_user(db_session, role="overseas_student", full_name="Walkin Chatstudent", profile={"registration_source": "counselor_walk_in"})
    await link(db_session, walk_in, counselor)
    await login(client, counselor.email)
    picker = await client.get("/api/v1/lookups/overseas-students", params={"q": "Walkin Chatstudent"})
    assert picker.status_code == 200
    assert [item["id"] for item in picker.json()["items"]] == [str(walk_in.id)]
    response = await client.post(SEND, json={"recipient_id": str(walk_in.id), "body": "Hello from your counselor", "context_type": "counselor_chat"})
    assert response.status_code == 201, response.text
    assert [m.body for m in await sent_to(db_session, counselor, walk_in)] == ["Hello from your counselor"]


@pytest.mark.asyncio
async def test_walk_in_student_reaches_the_linked_counselor_ac2(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    walk_in = await mk_user(db_session, role="overseas_student")
    await link(db_session, walk_in, counselor)
    await login(client, walk_in.email)
    response = await client.post(STUDENT_CHAT, json={"body": "Hi, I came in last week"})
    assert response.status_code == 201, response.text
    assert [m.body for m in await sent_to(db_session, walk_in, counselor)] == ["Hi, I came in last week"]


@pytest.mark.asyncio
async def test_student_with_neither_link_nor_application_counselor_gets_409_ac3(client, db_session):
    student = await mk_user(db_session, role="overseas_student")
    await mk_application(db_session, student=student, university=await mk_university(db_session))  # no counselor on it
    await login(client, student.email)
    response = await client.post(STUDENT_CHAT, json={"body": "Anyone?"})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_counselor_cannot_message_a_student_outside_their_caseload_ac4(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    other = await mk_user(db_session, role="counselor")
    theirs = await mk_user(db_session, role="overseas_student")
    await link(db_session, theirs, other)
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, counselor.email)
    for student in (theirs, stranger):
        response = await client.post(SEND, json={"recipient_id": str(student.id), "body": "Hi", "context_type": "counselor_chat"})
        assert response.status_code == 403
        assert await sent_to(db_session, counselor, student) == []


@pytest.mark.asyncio
async def test_application_counselor_wins_over_the_linked_counselor(client, db_session):
    app_counselor = await mk_user(db_session, role="counselor")
    linked_counselor = await mk_user(db_session, role="counselor")
    student = await mk_user(db_session, role="overseas_student")
    await link(db_session, student, linked_counselor)
    await mk_application(db_session, student=student, university=await mk_university(db_session), counselor=app_counselor)
    await login(client, student.email)
    assert (await client.post(STUDENT_CHAT, json={"body": "Question"})).status_code == 201
    assert len(await sent_to(db_session, student, app_counselor)) == 1
    assert await sent_to(db_session, student, linked_counselor) == []


@pytest.mark.asyncio
async def test_reassigned_walk_in_reaches_the_new_counselor(client, db_session):
    old = await mk_user(db_session, role="counselor")
    new = await mk_user(db_session, role="counselor")
    student = await mk_user(db_session, role="overseas_student")
    await link(db_session, student, old)
    row = await db_session.scalar(select(OverseasStudentCounselor).where(OverseasStudentCounselor.student_user_id == student.id))
    row.counselor_user_id = new.id  # what csc-005's reassignment does
    await db_session.commit()
    await login(client, student.email)
    assert (await client.post(STUDENT_CHAT, json={"body": "New counselor?"})).status_code == 201
    assert len(await sent_to(db_session, student, new)) == 1
    assert await sent_to(db_session, student, old) == []


@pytest.mark.asyncio
async def test_archived_walk_in_is_hidden_from_the_picker(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    archived = await mk_user(db_session, role="overseas_student", full_name="Archivedwalkin Chat")
    await link(db_session, archived, counselor)
    db_session.add(OverseasStudentArchive(student_user_id=archived.id, archived_by_user_id=counselor.id, reason="Done"))
    await db_session.commit()
    await login(client, counselor.email)
    picker = await client.get("/api/v1/lookups/overseas-students", params={"q": "Archivedwalkin Chat"})
    assert picker.json()["items"] == []


@pytest.mark.asyncio
async def test_counselor_messaging_other_staff_is_unchanged(client, db_session):
    counselor = await mk_user(db_session, role="counselor")
    admin = await mk_user(db_session, role="overseas_admin")
    await login(client, counselor.email)
    assert (await client.post(SEND, json={"recipient_id": str(admin.id), "body": "FYI"})).status_code == 201
