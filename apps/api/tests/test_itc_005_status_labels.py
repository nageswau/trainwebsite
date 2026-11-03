"""itc-005 (DEC-SCOPE-362) -- the IT team's configurable status labels: labels, order and enable/disable of the fixed lead stages and
lifecycle stages (S1-S3), the read for IT staff and the IT Admin's write (S10), what may be disabled (S4), the label rules (S7), the audit
row (S9, AC3), the disabled stage refused for a person's move and the override but still labelled on history (S6, AC2), and the lifecycle
payloads carrying the configured words (S8, AC1). Overseas is unaffected (E). Every test starts and ends with no override rows: the shared
test database is never truncated and other suites assert the default words."""

from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from fastapi.exceptions import RequestValidationError
from sqlalchemy import delete, func, select

from app.lead_stages import STAGES
from app.models import AuditLog, Enquiry, ItStatusLabel, User
from app.schemas import ItLifecycleOverrideIn
from app.services import it_lifecycle, it_student_360, lead_follow_ups, lead_pipeline
from app.services.it_lifecycle import LABELS as LIFECYCLE_LABELS
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import lead, make_telecaller, make_tl_manager, make_user
from tests.test_itc_031_lifecycle import PAST, enrolled
from tests.test_tel_020_alerts import follow_up

pytestmark = pytest.mark.asyncio

READ = "/api/v1/it/status-labels"
ADMIN = "/api/v1/admin/it/status-labels"


def put_url(kind: str, code: str) -> str:
    return f"{ADMIN}/{kind}/{code}"


@pytest_asyncio.fixture(autouse=True)
async def no_overrides(db_session):
    await db_session.execute(delete(ItStatusLabel))
    await db_session.commit()
    yield
    await db_session.rollback()
    await db_session.execute(delete(ItStatusLabel))
    await db_session.commit()


def entry(body: dict, kind: str, code: str) -> dict:
    return next(e for e in body[kind] if e["code"] == code)


async def it_admin(db):
    return await make_user(db, "it_admin", "it")


# --- the read (S2, S3, S10) --------------------------------------------------------------------------------------------------------
async def test_it_staff_read_the_default_catalogue_in_catalogue_order(client, db_session):
    await as_user(client, await make_user(db_session, "counselor", "it"))
    res = await client.get(READ)
    assert res.status_code == 200, res.text
    body = res.json()
    assert [e["code"] for e in body["lead"]] == list(STAGES)
    assert [e["code"] for e in body["lifecycle"]] == list(LIFECYCLE_LABELS)
    interested = entry(body, "lead", "interested")
    assert interested == {"code": "interested", "label": "Interested", "default_label": "Interested", "sort_order": 60, "enabled": True, "can_disable": True}
    assert entry(body, "lead", "contacted")["can_disable"] is False
    assert entry(body, "lead", "follow_up")["can_disable"] is False  # S4: the reopen / return target
    assert entry(body, "lifecycle", "not_placed")["can_disable"] is True and entry(body, "lifecycle", "paid")["can_disable"] is False


async def test_students_and_other_divisions_cannot_read_and_only_the_it_admin_writes(client, db_session):
    for role, division in (("it_student", "it"), ("counselor", "overseas")):
        await as_user(client, await make_user(db_session, role, division))
        assert (await client.get(READ)).status_code == 403
    await as_user(client, await make_user(db_session, "super_admin", "it"))
    assert (await client.get(READ)).status_code == 200
    for role in ("counselor", "super_admin"):
        await as_user(client, await make_user(db_session, role, "it"))
        assert (await client.get(ADMIN)).status_code == 403
        assert (await client.put(put_url("lead", "interested"), json={"label": "X", "sort_order": 1, "enabled": True})).status_code == 403
    client.cookies.clear()
    assert (await client.get(READ)).status_code == 401


# --- the write (+ case, S7, S9 / AC3) ----------------------------------------------------------------------------------------------
async def test_the_it_admin_renames_interested_and_the_change_is_audited(client, db_session):
    admin = await it_admin(db_session)
    await as_user(client, admin)
    res = await client.put(put_url("lead", "interested"), json={"label": "  Course Interested ", "sort_order": 15, "enabled": True})
    assert res.status_code == 200, res.text
    out = res.json()
    assert (out["code"], out["label"], out["default_label"], out["sort_order"], out["enabled"]) == ("interested", "Course Interested", "Interested", 15, True)
    assert out["updated_by"]["id"] == str(admin.id) and out["updated_at"]
    body = (await client.get(READ)).json()
    assert entry(body, "lead", "interested")["label"] == "Course Interested"
    assert [e["code"] for e in body["lead"]][:3] == ["new", "interested", "assigned"]  # order 15 sits between New (10) and Assigned (20)
    mine = select(AuditLog).where(AuditLog.action == "it.status_label.update", AuditLog.entity_id == "lead:interested", AuditLog.user_id == admin.id)
    row = await db_session.scalar(mine)
    assert row.created_at is not None
    assert row.metadata_json["changes"]["label"] == ["Interested", "Course Interested"]

    again = await client.put(put_url("lead", "interested"), json={"label": "Course Interested", "sort_order": 15, "enabled": True})
    assert again.status_code == 200  # idempotent: nothing changed, no second audit row
    assert len((await db_session.scalars(mine)).all()) == 1


async def test_bad_writes_are_refused(client, db_session):
    await as_user(client, await it_admin(db_session))
    assert (await client.put(put_url("lead", "nope"), json={"label": "X", "sort_order": 1, "enabled": True})).status_code == 404
    assert (await client.put(put_url("nope", "new"), json={"label": "X", "sort_order": 1, "enabled": True})).status_code == 404
    for body in (
        {"label": "", "sort_order": 1, "enabled": True},
        {"label": "x" * 61, "sort_order": 1, "enabled": True},
        {"label": "X", "sort_order": -1, "enabled": True},
        {"label": "X", "sort_order": 10000, "enabled": True},
        {"label": "X"},
    ):
        assert (await client.put(put_url("lead", "interested"), json=body)).status_code == 422, body
    clash = await client.put(put_url("lead", "interested"), json={"label": "qualified", "sort_order": 50, "enabled": True})
    assert clash.status_code == 422 and "already" in clash.text  # S7: unique per kind, case-insensitive
    system = await client.put(put_url("lead", "contacted"), json={"label": "Contacted", "sort_order": 40, "enabled": False})
    assert system.status_code == 422  # S4: a system state cannot be disabled
    assert (await client.put(put_url("lifecycle", "paid"), json={"label": "Paid", "sort_order": 40, "enabled": False})).status_code == 422
    # the same label in another kind is fine
    assert (await client.put(put_url("lifecycle", "closed"), json={"label": "Lost", "sort_order": 130, "enabled": True})).status_code == 200


async def test_the_admin_read_counts_the_it_leads_in_each_stage(client, db_session):
    await lead(db_session, status="interested")
    await lead(db_session, division="overseas", status="interested")
    await as_user(client, await it_admin(db_session))
    body = (await client.get(ADMIN)).json()
    interested = entry(body, "lead", "interested")
    expected = await db_session.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.division == "it", Enquiry.status == "interested"))
    assert interested["in_use"] == expected >= 1 and interested["updated_by"] is None


# --- a disabled stage (S6 / AC2) ----------------------------------------------------------------------------------------------------
async def test_a_disabled_stage_cannot_be_chosen_for_an_it_lead_but_overseas_is_unaffected(client, db_session):
    await as_user(client, await it_admin(db_session))
    res = await client.put(put_url("lead", "interested"), json={"label": "Interested", "sort_order": 50, "enabled": False})
    assert res.status_code == 200 and res.json()["enabled"] is False
    manager = await make_tl_manager(db_session)
    tel = await make_telecaller(db_session, manager)
    row = await lead(db_session, telecaller=tel, status="qualified")
    locked = await lead_pipeline.locked_lead(db_session, row.id)
    with pytest.raises(RequestValidationError) as refused:
        await lead_pipeline.person_move(db_session, locked, tel, "telecaller", "interested", None)
    assert refused.value.errors()[0]["loc"][-1] == "to_stage"
    await db_session.commit()  # nothing was written; releases the row lock
    overseas = await lead(db_session, division="overseas", status="qualified")  # E: overseas labels and stages are not configured
    locked = await lead_pipeline.locked_lead(db_session, overseas.id)
    await lead_pipeline.person_move(db_session, locked, manager, "manager", "interested", None)
    await db_session.commit()
    assert locked.status == "interested"


async def test_a_disabled_override_is_refused_but_clearing_and_history_keep_working(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    admin = await it_admin(db_session)
    student = await db_session.get(User, enrollment.student_id)
    await it_lifecycle.set_override(db_session, admin, student, enrollment.id, ItLifecycleOverrideIn(stage="closed", reason="Left"))
    await as_user(client, admin)
    assert (await client.put(put_url("lifecycle", "closed"), json={"label": "Archived", "sort_order": 130, "enabled": False})).status_code == 200
    override = f"/api/v1/admin/it/students/{student.id}/enrollments/{enrollment.id}/lifecycle-override"
    refused = await client.put(override, json={"stage": "closed", "reason": "Again"})
    assert refused.status_code == 409
    card = (await client.get(f"/api/v1/admin/it/students/{student.id}/lifecycle")).json()["enrollments"][0]
    assert (card["stage"], card["stage_label"]) == ("closed", "Archived")  # AC2: still shown on the existing row, with its label
    assert card["override"]["stage_label"] == "Archived" and card["history"][0]["to_label"] == "Archived"
    assert (await client.put(override, json={"stage": None})).status_code == 200  # clearing is always allowed


# --- the lifecycle payloads carry the configured words (S8 / AC1) ------------------------------------------------------------------
async def test_a_renamed_lifecycle_stage_reaches_the_staff_card_and_the_students_safe_view(client, db_session):
    enrollment = await enrolled(db_session, start=PAST)
    admin = await it_admin(db_session)
    await as_user(client, admin)
    assert (await client.put(put_url("lifecycle", "training_active"), json={"label": "In class", "sort_order": 50, "enabled": True})).status_code == 200
    card = (await client.get(f"/api/v1/admin/it/students/{enrollment.student_id}/lifecycle")).json()["enrollments"][0]
    assert card["stage_label"] == "In class" and card["components"]["fee"]["stage_label"] == "Fee pending"
    views = await it_lifecycle.views_for(db_session, [enrollment.id], safe=True)
    assert views[enrollment.id] == {"stage": "training_active", "stage_label": "In class"}


# --- the IT 360's lead card (server-rendered) and the follow-up lead's division (S8 / AC1) --------------------------------------
async def test_the_it_360_lead_card_uses_the_it_words_and_follow_ups_say_the_leads_division(client, db_session):
    admin = await it_admin(db_session)
    await as_user(client, admin)
    assert (await client.put(put_url("lead", "interested"), json={"label": "Course Interested", "sort_order": 60, "enabled": True})).status_code == 200
    tel = await make_telecaller(db_session, await make_tl_manager(db_session))
    row = await lead(db_session, telecaller=tel, status="interested")
    card = await it_student_360._lead_out(db_session, (row, None), admin)
    assert (card["stage"], card["stage_label"]) == ("interested", "Course Interested")
    await follow_up(db_session, row, datetime.now(UTC) + timedelta(days=1))
    page = await lead_follow_ups.lead_page(db_session, tel, row.id, datetime.now(UTC), 10, 0)
    assert page["items"][0]["lead"]["division"] == "it"
