"""ccrm-040 (DEC-SCOPE-276) -- archive instead of delete (AR1-AR7) and the overseas consent capture (CN1-CN5).

AR: the student's csc-001 counselor or the Overseas Admin archives a student whose applications are all closed; only the Admin restores.
An archived student and their applications leave the staff working lists, a new application for them is refused, the 360 still reads.
CN: the student accepts the current data-processing and document-sharing consents once; the 360 shows what was given."""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Agreement, AuditLog, ConsentRecord, Notification, NotificationPreference, OverseasStudentArchive, OverseasStudentCounselor, StudentMessage
from tests.agn001_helpers import login, mk_user, uniq
from tests.enh031_helpers import mk_application, mk_university

PORTAL = "/api/v1/portal/overseas/{}/{}"
REASON = "Studies finished; no further applications planned"


def url(student_id, action: str) -> str:
    return f"/api/v1/counselor/students/{student_id}/{action}"


@pytest_asyncio.fixture
async def world(db_session):
    counselor = await mk_user(db_session, role="counselor", full_name="Nora Counselor")
    other = await mk_user(db_session, role="counselor", full_name="Omar Counselor")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Ada Admin")
    student = await mk_user(db_session, role="overseas_student", full_name=f"{uniq('c40')} Student")
    db_session.add(OverseasStudentCounselor(student_user_id=student.id, counselor_user_id=counselor.id, assigned_by_user_id=admin.id))
    uni = await mk_university(db_session, name=uniq("Archive Uni"))
    closed = await mk_application(db_session, student=student, university=uni, counselor=counselor, status="withdrawn")
    enrolled = await mk_application(db_session, student=student, university=await mk_university(db_session, name=uniq("Enrolled Uni")), counselor=counselor, status="enrolled")
    return {"counselor": counselor, "other": other, "admin": admin, "student": student, "uni": uni, "closed": closed, "enrolled": enrolled}


async def archive(client, world, who="counselor", reason=REASON):
    await login(client, world[who].email)
    return await client.post(url(world["student"].id, "archive"), json={"reason": reason})


# --- AR1-AR4: archive -------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_students_counselor_archives_with_a_reason(client, db_session, world):
    response = await archive(client, world)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reason"] == REASON and body["archived_by"] == "Nora Counselor" and body["archived_at"]
    row = await db_session.get(OverseasStudentArchive, world["student"].id)
    assert row is not None and row.archived_by_user_id == world["counselor"].id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas.student.archive", AuditLog.entity_id == str(world["student"].id)))
    assert audit is not None and audit.metadata_json == {"reason": REASON}
    await db_session.refresh(world["student"])
    assert world["student"].active is True  # AR6: the login is not touched


@pytest.mark.asyncio
async def test_the_admin_archives_and_the_counselor_is_told(client, db_session, world):
    assert (await archive(client, world, "admin")).status_code == 200
    notice = await db_session.scalar(select(Notification).where(Notification.user_id == world["counselor"].id, Notification.title == "Student archived"))
    assert notice is not None and REASON in notice.body


@pytest.mark.asyncio
async def test_an_open_application_blocks_the_archive(client, db_session, world):
    live = await mk_application(db_session, student=world["student"], university=await mk_university(db_session, name=uniq("Live Uni")), counselor=world["other"], status="offer")
    response = await archive(client, world)
    assert response.status_code == 409
    assert live.application_code in response.json()["detail"]
    assert await db_session.get(OverseasStudentArchive, world["student"].id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "  ", "ab", "x" * 501])
async def test_a_reason_is_required(client, world, reason):
    assert (await archive(client, world, reason=reason)).status_code == 422


@pytest.mark.asyncio
async def test_archiving_twice_is_409(client, world):
    assert (await archive(client, world)).status_code == 200
    assert (await archive(client, world)).status_code == 409


@pytest.mark.asyncio
async def test_who_may_archive(client, db_session, world):
    # a counselor with an application for the student but who is not their counselor: in scope, not the owner
    await mk_application(db_session, student=world["student"], university=await mk_university(db_session, name=uniq("Other Uni")), counselor=world["other"], status="withdrawn")
    assert (await archive(client, world, "other")).status_code == 403
    stranger = await mk_user(db_session, role="overseas_student")
    await login(client, world["counselor"].email)
    assert (await client.post(url(stranger.id, "archive"), json={"reason": REASON})).status_code == 404
    for role, division in (("overseas_student", "overseas"), ("agent", "overseas"), ("counselor", "it"), ("university_rep", "overseas")):
        user = world["student"] if role == "overseas_student" else await mk_user(db_session, role=role, division=division)
        await login(client, user.email, division)
        assert (await client.post(url(world["student"].id, "archive"), json={"reason": REASON})).status_code == 403, role


# --- AR1 / AR4 / AR7: restore ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_only_the_admin_restores(client, db_session, world):
    assert (await archive(client, world)).status_code == 200
    assert (await client.post(url(world["student"].id, "restore"))).status_code == 403  # the counselor
    await login(client, world["admin"].email)
    response = await client.post(url(world["student"].id, "restore"))
    assert response.status_code == 200, response.text
    assert await db_session.get(OverseasStudentArchive, world["student"].id, populate_existing=True) is None
    assert await db_session.scalar(select(AuditLog.id).where(AuditLog.action == "overseas.student.restore", AuditLog.entity_id == str(world["student"].id)))
    assert await db_session.scalar(select(Notification.id).where(Notification.user_id == world["counselor"].id, Notification.title == "Student restored"))
    assert (await client.post(url(world["student"].id, "restore"))).status_code == 409  # not archived any more


@pytest.mark.asyncio
async def test_archived_list(client, db_session, world):
    assert (await archive(client, world)).status_code == 200
    for who in ("counselor", "admin"):
        await login(client, world[who].email)
        data = (await client.get("/api/v1/counselor/students/archived")).json()
        ids = [i["id"] for i in data["items"]]
        assert str(world["student"].id) in ids, who
        item = next(i for i in data["items"] if i["id"] == str(world["student"].id))
        assert item["reason"] == REASON and item["archived_by"] == "Nora Counselor" and item["student_code"] == world["student"].student_code
    await login(client, world["other"].email)
    assert str(world["student"].id) not in [i["id"] for i in (await client.get("/api/v1/counselor/students/archived")).json()["items"]]
    await login(client, world["student"].email)
    assert (await client.get("/api/v1/counselor/students/archived")).status_code == 403


# --- AR5 / AR6: what archive hides and blocks ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_hides_the_student_from_working_lists_but_not_the_360(client, db_session, world):
    async def visible(who: str) -> dict:
        await login(client, world[who].email)
        role = "counselor" if who == "counselor" else "admin"
        apps = {r["id"] for r in (await client.get(PORTAL.format(role, "applications"))).json()["rows"]}
        picker = {i["id"] for i in (await client.get("/api/v1/lookups/overseas-students", params={"q": world["student"].full_name})).json()["items"]}
        return {"apps": str(world["closed"].id) in apps, "picker": str(world["student"].id) in picker}

    assert await visible("counselor") == {"apps": True, "picker": True}
    await login(client, world["counselor"].email)
    linked = {i["id"] for i in (await client.get("/api/v1/counselor/students", params={"limit": 50})).json()["items"]}
    assert str(world["student"].id) in linked
    assert (await archive(client, world)).status_code == 200
    assert await visible("counselor") == {"apps": False, "picker": False}
    assert await visible("admin") == {"apps": False, "picker": False}
    await login(client, world["counselor"].email)
    linked = {i["id"] for i in (await client.get("/api/v1/counselor/students", params={"limit": 50})).json()["items"]}
    assert str(world["student"].id) not in linked
    overview = (await client.get(url(world["student"].id, "overview"))).json()
    assert overview["archive"]["reason"] == REASON and len(overview["applications"]) == 2
    assert overview["permissions"] == {"archive": False, "restore": False}
    history = (await client.get(url(world["student"].id, "history"))).json()["items"]
    assert any(h["summary"] == "Archived" and h["reason"] == REASON for h in history)


@pytest.mark.asyncio
async def test_no_new_application_for_an_archived_student(client, db_session, world):
    assert (await archive(client, world)).status_code == 200
    uni = await mk_university(db_session, name=uniq("New Uni"))
    for who in ("counselor", "admin", "student"):
        await login(client, world[who].email)
        body = {"university_id": str(uni.id)} | ({} if who == "student" else {"student_id": str(world["student"].id)})
        response = await client.post("/api/v1/workflows/overseas/applications", json=body)
        assert response.status_code == 409 and "archived" in response.json()["detail"], who


@pytest.mark.asyncio
async def test_overview_permissions(client, world):
    await login(client, world["counselor"].email)
    assert (await client.get(url(world["student"].id, "overview"))).json()["permissions"] == {"archive": True, "restore": False}
    await login(client, world["admin"].email)
    assert (await client.get(url(world["student"].id, "overview"))).json()["permissions"] == {"archive": True, "restore": False}
    assert (await archive(client, world, "admin")).status_code == 200
    assert (await client.get(url(world["student"].id, "overview"))).json()["permissions"] == {"archive": False, "restore": True}


# --- CN1-CN5: consent -------------------------------------------------------------------------------------------------------------


CONSENTS = "/api/v1/overseas/me/consents"


@pytest.mark.asyncio
async def test_the_student_sees_and_accepts_both_consents(client, db_session, world):
    await login(client, world["student"].email)
    items = (await client.get(CONSENTS)).json()["items"]
    assert [i["kind"] for i in items] == ["data_processing", "document_sharing"]
    assert all(i["accepted_at"] is None and i["version"] == "v1" and i["title"] and i["body"] for i in items)
    first = await client.post(f"{CONSENTS}/{items[0]['id']}/accept")
    assert first.status_code == 201, first.text
    again = await client.post(f"{CONSENTS}/{items[0]['id']}/accept")
    assert again.status_code == 200 and again.json()["accepted_at"] == first.json()["accepted_at"]  # CN3: once
    rows = (await db_session.scalars(select(ConsentRecord).where(ConsentRecord.user_id == world["student"].id))).all()
    assert len(rows) == 1 and rows[0].version == "v1"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "overseas_consent.accept", AuditLog.entity_id == str(world["student"].id)))
    assert audit.metadata_json == {"kind": "data_processing", "version": "v1"}
    items = (await client.get(CONSENTS)).json()["items"]
    assert items[0]["accepted_at"] and items[1]["accepted_at"] is None
    # CN4: the counselor's 360 shows what was given
    await login(client, world["counselor"].email)
    consents = {c["kind"]: c for c in (await client.get(url(world["student"].id, "overview"))).json()["consents"]}
    assert consents["data_processing"]["accepted_at"] and consents["document_sharing"]["accepted_at"] is None
    assert consents["data_processing"]["label"] == items[0]["title"]


@pytest.mark.asyncio
async def test_a_newer_version_asks_again(client, db_session, world):
    await login(client, world["student"].email)
    old = (await client.get(CONSENTS)).json()["items"][1]
    assert (await client.post(f"{CONSENTS}/{old['id']}/accept")).status_code == 201
    newer = Agreement(division="overseas", kind="document_sharing", version=uniq("v2")[:20], title="Share v2", body="Updated text", active=True)
    db_session.add(newer)
    await db_session.commit()
    try:
        item = (await client.get(CONSENTS)).json()["items"][1]
        assert item["id"] == str(newer.id) and item["accepted_at"] is None  # CN5
        assert (await client.post(f"{CONSENTS}/{old['id']}/accept")).status_code == 404  # no longer current
    finally:
        newer.active = False
        await db_session.commit()


@pytest.mark.asyncio
async def test_consent_routes_are_the_students_own(client, db_session, world):
    it_agreement = Agreement(division="it", version="it-x", title="IT", body="IT", active=True)
    db_session.add(it_agreement)
    await db_session.commit()
    try:
        await login(client, world["student"].email)
        assert (await client.post(f"{CONSENTS}/{it_agreement.id}/accept")).status_code == 404  # not an overseas consent
        for who in ("counselor", "admin"):
            await login(client, world[who].email)
            assert (await client.get(CONSENTS)).status_code == 403
    finally:
        it_agreement.active = False
        await db_session.commit()


# --- CN7: ccrm-037's WhatsApp honours the student's communication preference (ENH-014 opt-in) ---------------------------------


@pytest.mark.asyncio
async def test_whatsapp_to_a_student_needs_their_opt_in(client, db_session, world):
    world["student"].phone = "98765 43210"
    await db_session.commit()
    await login(client, world["counselor"].email)
    messages = url(world["student"].id, "messages")
    recipient = (await client.get(messages)).json()["recipient"]
    assert recipient["whatsapp_to"] == "919876543210" and recipient["whatsapp_opt_in"] is False  # QA-01: the UI tells "no number" from "not opted in"
    response = await client.post(messages, json={"channel": "whatsapp", "body": "Hello"})
    assert response.status_code == 409 and response.json()["detail"] == "This student has not opted in to WhatsApp messages"
    assert await db_session.scalar(select(StudentMessage.id).where(StudentMessage.student_user_id == world["student"].id)) is None
    db_session.add(NotificationPreference(user_id=world["student"].id, whatsapp_opt_in=True))
    await db_session.commit()
    recipient = (await client.get(messages)).json()["recipient"]
    assert recipient["whatsapp_to"] == "919876543210" and recipient["whatsapp_opt_in"] is True
    assert (await client.post(messages, json={"channel": "whatsapp", "body": "Hello"})).status_code == 201
