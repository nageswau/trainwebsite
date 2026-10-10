"""upc-027 -- the partner onboarding checklist (spec §1, §5; AC1-AC6, S1, S2; DEC-SCOPE-169 OB1-OB13)."""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, OverseasCourse, University, UniversityStageHistory
from app.services.bdm_travel import india_today
from tests.test_upc_014_agreements import ag_url, day, moved, signed, signing_fields
from tests.test_upc_017_courses import course_body
from tests.test_upc_017_import import _csv, _upload
from tests.test_upc_026_documents import _owned
from tests.upc003_helpers import as_role, login, make_pm, make_user, url
from tests.upc007_helpers import owned_university

ITEMS = (
    "counselor_training", "application_team_training", "product_training", "university_portal_access", "application_process",
    "marketing_material", "course_database_updated", "commission_setup", "university_contact_setup", "first_student_campaign",
)  # fmt: skip
MANUAL = tuple(k for k in ITEMS if k != "course_database_updated")


def ob(university_id, kind: str | None = None) -> str:
    return url(university_id, "onboarding" + (f"/{kind}" if kind else ""))


async def page(client, university_id) -> dict:
    response = await client.get(ob(university_id))
    assert response.status_code == 200, response.text
    return response.json()


async def patch_ok(client, university_id, kind: str, **body) -> dict:
    response = await client.patch(ob(university_id, kind), json=body)
    assert response.status_code == 200, response.text
    return response.json()


def by_kind(body: dict) -> dict[str, dict]:
    return {i["kind"]: i for i in body["items"]}


async def signed_university(client, db):
    """A university with one signed MoU; the client ends signed in as its primary manager."""
    head, pm, other, uni = await _owned(client, db)
    agreement = await signed(client, head, pm, uni["id"])
    return head, pm, other, uni, agreement


async def add_course(db, university_id, *, active: bool = True) -> OverseasCourse:
    row = OverseasCourse(university_id=uuid.UUID(str(university_id)), title=f"MSc {uuid.uuid4().hex[:6]}", level="PG", category="Tech",
                         duration="1 year", tuition_fee="GBP 20,000", intake="Sep", active=active)  # fmt: skip
    db.add(row)
    await db.commit()
    return row


async def stage_of(db, university_id) -> str:
    db.expire_all()
    return (await db.get(University, uuid.UUID(str(university_id)))).stage


async def audits(db, university_id, action: str) -> list[AuditLog]:
    db.expire_all()
    stmt = select(AuditLog).where(AuditLog.entity_id == str(university_id), AuditLog.action == action).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


# --- AC2 / OB3: before signing ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_before_signing_the_checklist_is_not_started_and_read_only(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    body = await page(client, uni["id"])
    assert body["started"] is False and body["started_on"] is None and body["can_edit"] is False
    assert [i["kind"] for i in body["items"]] == list(ITEMS) and {i["status"] for i in body["items"]} == {"not_started"}
    assert body["status"] == "not_started" and body["completed_count"] == 0
    response = await client.patch(ob(uni["id"], "product_training"), json={"status": "in_progress"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "onboarding_not_started"


# --- AC1 / OB2: signing starts it ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signing_shows_the_ten_items_as_not_started(client, db_session):
    _, _, _, uni, agreement = await signed_university(client, db_session)
    body = await page(client, uni["id"])
    assert body["started"] is True and body["can_edit"] is True and body["status"] == "not_started"
    assert body["started_on"] == max(agreement["edusphere_signed_on"], agreement["university_signed_on"])
    assert [i["label"] for i in body["items"]][:3] == ["Counselor training", "Application team training", "Product training"]
    first = body["items"][0]
    assert first == {"kind": "counselor_training", "label": "Counselor training", "status": "not_started", "completed_by": None,
                     "completed_on": None, "owner": None, "due_date": None, "note": None}  # fmt: skip
    assert await stage_of(db_session, uni["id"]) == "agreement_signed"


# --- AC3 / OB4 / OB5 / OB6: editing one item -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_manager_sets_status_owner_due_date_and_note(client, db_session):
    head, pm, _, uni, _ = await signed_university(client, db_session)
    due = (india_today() + timedelta(days=7)).isoformat()
    body = await patch_ok(client, uni["id"], "counselor_training", status="in_progress", owner_user_id=str(head.id), due_date=due, note="  Batch 1 on Monday  ")
    item = by_kind(body)["counselor_training"]
    assert item["status"] == "in_progress" and item["owner"] == {"id": str(head.id), "full_name": head.full_name}
    assert item["due_date"] == due and item["note"] == "Batch 1 on Monday" and item["completed_on"] is None
    assert body["status"] == "in_progress" and body["stage_advanced"] is False and len(body["items"]) == 10
    body = await patch_ok(client, uni["id"], "counselor_training", status="completed")
    item = by_kind(body)["counselor_training"]
    assert item["completed_on"] == india_today().isoformat() and item["completed_by"] == "manual" and body["completed_count"] == 1
    assert item["note"] == "Batch 1 on Monday"  # untouched fields stay
    body = await patch_ok(client, uni["id"], "counselor_training", status="in_progress", owner_user_id=None, note="", due_date=None)
    item = by_kind(body)["counselor_training"]
    assert item["completed_on"] is None and item["completed_by"] is None and item["owner"] is None and item["note"] is None and item["due_date"] is None
    assert (await page(client, uni["id"]))["items"][0]["status"] == "in_progress"  # persisted


@pytest.mark.asyncio
async def test_validation_errors_are_422(client, db_session):
    _, pm, _, uni, _ = await signed_university(client, db_session)
    for body, field in (
        ({}, None),
        ({"status": None}, "status"),
        ({"status": "done"}, "status"),
        ({"note": "x" * 501}, "note"),
        ({"owner_user_id": str(uuid.uuid4())}, "owner_user_id"),
        ({"colour": "red"}, None),
    ):
        response = await client.patch(ob(uni["id"], "product_training"), json=body)
        assert response.status_code == 422, (body, response.text)
        if field:
            assert any(e["loc"][-1] == field for e in response.json()["detail"]), response.text
    counselor = await make_user(db_session, "counselor", "overseas")
    response = await client.patch(ob(uni["id"], "product_training"), json={"owner_user_id": str(counselor.id)})
    assert response.status_code == 422 and response.json()["detail"][0]["loc"] == ["body", "owner_user_id"]
    inactive = await make_pm(db_session, await make_user(db_session, "partnership_head", "global"), active=False)
    assert (await client.patch(ob(uni["id"], "product_training"), json={"owner_user_id": str(inactive.id)})).status_code == 422
    assert (await client.patch(ob(uni["id"], "launch"), json={"status": "in_progress"})).status_code == 422


@pytest.mark.asyncio
async def test_an_unchanged_patch_writes_no_audit_and_changes_carry_no_note_text(client, db_session):
    _, _, _, uni, _ = await signed_university(client, db_session)
    await patch_ok(client, uni["id"], "product_training", status="in_progress", note="Secret pricing remark")
    await patch_ok(client, uni["id"], "product_training", status="in_progress")
    rows = await audits(db_session, uni["id"], "university.onboarding_item_updated")
    assert len(rows) == 1
    meta = rows[0].metadata_json
    assert meta == {"kind": "product_training", "fields": ["note", "status"], "status": {"from": "not_started", "to": "in_progress"}}
    assert "Secret" not in str(meta)


# --- AC4 / OB8: all completed activates the partner -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_all_ten_completed_moves_the_university_to_partner_activated(client, db_session):
    _, _, _, uni, _ = await signed_university(client, db_session)
    await add_course(db_session, uni["id"])  # the course item completes itself (OB7)
    for kind in MANUAL[:-1]:
        body = await patch_ok(client, uni["id"], kind, status="completed")
        assert body["stage_advanced"] is False
    assert body["status"] == "in_progress" and body["completed_count"] == 9
    body = await patch_ok(client, uni["id"], MANUAL[-1], status="completed")
    assert body["status"] == "completed" and body["completed_count"] == 10 and body["stage_advanced"] is True
    assert await stage_of(db_session, uni["id"]) == "partner_activated"
    history = (await db_session.scalars(select(UniversityStageHistory).where(UniversityStageHistory.university_id == uuid.UUID(uni["id"])).order_by(UniversityStageHistory.position))).all()
    assert (history[-1].from_stage, history[-1].to_stage, history[-1].note) == ("agreement_signed", "partner_activated", "Advanced by onboarding completed")
    assert [a.metadata_json for a in await audits(db_session, uni["id"], "university.onboarding_completed")] == [{"from_stage": "agreement_signed"}]
    # Moving an item back and completing it again never moves the stage again (forward only).
    await patch_ok(client, uni["id"], MANUAL[0], status="in_progress")
    body = await patch_ok(client, uni["id"], MANUAL[0], status="completed")
    assert body["stage_advanced"] is False and len(await audits(db_session, uni["id"], "university.onboarding_completed")) == 1


@pytest.mark.asyncio
async def test_a_university_already_past_partner_activated_does_not_move(client, db_session):
    head, _, _, uni, _ = await signed_university(client, db_session)
    await login(client, head)
    response = await client.post(url(uni["id"], "stage"), json={"from_stage": "agreement_signed", "to_stage": "active_partner"})
    assert response.status_code == 200, response.text
    for kind in ITEMS:
        body = await patch_ok(client, uni["id"], kind, status="completed")
    assert body["status"] == "completed" and body["stage_advanced"] is False
    assert await stage_of(db_session, uni["id"]) == "active_partner"


# --- AC5 / OB7: the automatic course item ----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_course_database_updated_completes_itself_while_an_active_course_exists(client, db_session):
    _, _, _, uni, _ = await signed_university(client, db_session)
    course = await add_course(db_session, uni["id"], active=False)
    assert by_kind(await page(client, uni["id"]))["course_database_updated"]["status"] == "not_started"  # inactive courses don't count
    course.active = True
    await db_session.commit()
    item = by_kind(await page(client, uni["id"]))["course_database_updated"]
    assert item["status"] == "completed" and item["completed_by"] == "auto" and item["completed_on"] is None
    body = await page(client, uni["id"])
    assert body["status"] == "in_progress" and body["completed_count"] == 1


@pytest.mark.asyncio
async def test_adding_the_course_that_completes_the_last_item_activates_the_partner(client, db_session):
    _, _, _, uni, _ = await signed_university(client, db_session)
    for kind in MANUAL:
        body = await patch_ok(client, uni["id"], kind, status="completed")
    assert body["stage_advanced"] is False and body["completed_count"] == 9
    response = await client.post(url(uni["id"], "courses"), json=course_body())
    assert response.status_code == 201, response.text
    assert await stage_of(db_session, uni["id"]) == "partner_activated"
    assert (await page(client, uni["id"]))["status"] == "completed"


@pytest.mark.asyncio
async def test_a_course_import_that_completes_the_last_item_activates_the_partner(client, db_session):
    _, _, _, uni, _ = await signed_university(client, db_session)
    for kind in MANUAL:
        await patch_ok(client, uni["id"], kind, status="completed")
    response = await _upload(client, uni["id"], _csv("BSc Nursing,UG,Health,3 years,,,,,,,"))
    assert response.status_code == 201, response.text
    assert await stage_of(db_session, uni["id"]) == "partner_activated"


@pytest.mark.asyncio
async def test_a_course_write_before_signing_changes_nothing(client, db_session):
    _, _, uni = await owned_university(client, db_session)
    response = await client.post(url(uni["id"], "courses"), json=course_body())
    assert response.status_code == 201, response.text
    assert await stage_of(db_session, uni["id"]) == "target_university"


# --- AC6 / OB10: re-signing after a renewal -------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_signing_a_renewal_keeps_the_checklist(client, db_session):
    head, pm, _, uni = await _owned(client, db_session)
    old = await signed(client, head, pm, uni["id"], start_date=day(-1000), expiry_date=day(20))
    await patch_ok(client, uni["id"], "product_training", status="completed")
    await patch_ok(client, uni["id"], "marketing_material", status="in_progress", note="Brochures")
    response = await client.post(ag_url(old["id"], "/renew"), json={"start_date": day(21), "expiry_date": day(1100)})
    assert response.status_code == 201, response.text
    new = response.json()["agreement"]
    for to in ("sent", "under_review"):
        new = await moved(client, new, to)
    await login(client, head)
    new = await moved(client, new, "approved")
    await login(client, pm)
    new = (await client.patch(ag_url(new["id"]), json=await signing_fields(client, uni["id"], pm.id))).json()["agreement"]
    await moved(client, new, "signed")
    items = by_kind(await page(client, uni["id"]))
    assert items["product_training"]["status"] == "completed" and items["marketing_material"]["note"] == "Brochures"
    assert items["counselor_training"]["status"] == "not_started"


# --- S1: access ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_overseas_admin_and_other_managers_read_but_cannot_edit(client, db_session):
    head, _, other, uni, _ = await signed_university(client, db_session)
    await login(client, other)
    assert (await page(client, uni["id"]))["can_edit"] is False
    assert (await client.patch(ob(uni["id"], "product_training"), json={"status": "in_progress"})).status_code == 403
    await as_role(client, db_session, "overseas_admin", "overseas")
    assert (await page(client, uni["id"]))["can_edit"] is False
    assert (await client.patch(ob(uni["id"], "product_training"), json={"status": "in_progress"})).status_code == 403
    await login(client, head)
    await patch_ok(client, uni["id"], "product_training", status="in_progress")
    await login(client, await make_user(db_session, "super_admin", "global"))
    await patch_ok(client, uni["id"], "marketing_material", status="in_progress")


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "overseas"), ("university_rep", "overseas"), ("bdm", "overseas")])
async def test_other_roles_are_refused(client, db_session, role, division):
    _, _, uni = await owned_university(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await client.get(ob(uni["id"]))).status_code == 403
    assert (await client.patch(ob(uni["id"], "product_training"), json={"status": "in_progress"})).status_code == 403


@pytest.mark.asyncio
async def test_unknown_404_inactive_409_lost_409_and_signed_out_401(client, db_session):
    head, pm, _, uni, _ = await signed_university(client, db_session)
    assert (await client.get(ob(uuid.uuid4()))).status_code == 404
    assert (await client.patch(ob(uuid.uuid4(), "product_training"), json={"status": "in_progress"})).status_code == 404
    response = await client.post(url(uni["id"], "lost"), json={"reason": "Went with another agency"})
    assert response.status_code == 200, response.text
    response = await client.patch(ob(uni["id"], "product_training"), json={"status": "in_progress"})
    assert response.status_code == 409 and response.json()["detail"]["code"] == "university_lost"
    assert (await page(client, uni["id"]))["can_edit"] is False
    await login(client, head)
    assert (await client.post(url(uni["id"], "reopen"), json={"reason": "Talks resumed"})).status_code == 200
    assert (await client.post(url(uni["id"], "deactivate"), json={})).status_code == 200
    await login(client, pm)
    response = await client.patch(ob(uni["id"], "product_training"), json={"status": "in_progress"})
    assert response.status_code == 409 and response.json()["detail"] == "Reactivate this university first"
    client.cookies.clear()
    assert (await client.get(ob(uni["id"]))).status_code == 401
