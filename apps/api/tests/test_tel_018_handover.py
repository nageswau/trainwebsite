"""tel-018 -- handover to a counselor (spec §3.2; DEC-SCOPE-099 HO4) and the counselor's lead list/detail (AC1). The shared test
database is never truncated, so every test builds its own people and leads."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadFollowUp
from tests.tel004_helpers import make_telecaller, make_tl_manager, stage_url
from tests.tel018_helpers import COUNSELOR_LEADS, as_user, c_url, handover, handover_url, make_counselor, setup


async def _row(db, lead_id) -> Enquiry:
    return await db.scalar(select(Enquiry).where(Enquiry.id == lead_id).execution_options(populate_existing=True))


@pytest.mark.asyncio
async def test_the_telecaller_hands_a_lead_to_a_counselor_of_its_division(client, db_session):
    _, tel, counselor, lead = await setup(db_session, status="qualified")
    response = await handover(client, tel, lead, counselor)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["counselor"]["id"], body["read_only"], body["status"]) == (str(counselor.id), True, "qualified")  # stage unchanged
    assert (await _row(db_session, lead.id)).owner_id == counselor.id
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(lead.id), AuditLog.action == "lead.handover"))
    assert audit.metadata_json == {"counselor_id": str(counselor.id), "from_counselor_id": None}


@pytest.mark.asyncio
async def test_after_handover_the_telecaller_reads_but_cannot_write(client, db_session):
    """AC1."""
    _, tel, counselor, lead = await setup(db_session, status="interested")
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    assert (await client.get(f"/api/v1/telecaller/leads/{lead.id}")).status_code == 200
    for response in (
        await client.patch(f"/api/v1/telecaller/leads/{lead.id}", json={"priority": "hot"}),
        await client.post(stage_url(lead.id), json={"to_stage": "follow_up"}),
        await client.post(handover_url(lead.id), json={"counselor_id": str(counselor.id)}),
    ):
        assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_handover_cancels_the_open_follow_ups_with_a_reason(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    db_session.add(LeadFollowUp(lead_id=lead.id, due_at=datetime.now(UTC) + timedelta(days=1), reason="fee_details", created_by_user_id=tel.id))
    await db_session.commit()
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    rows = (await db_session.scalars(select(LeadFollowUp).where(LeadFollowUp.lead_id == lead.id).execution_options(populate_existing=True))).all()
    assert [(r.status, r.cancel_reason) for r in rows] == [("cancelled", "Handed over to counselor")]


@pytest.mark.asyncio
async def test_a_counselor_of_another_division_is_422(client, db_session):
    _, tel, _, lead = await setup(db_session)
    other = await make_counselor(db_session, "overseas")
    response = await handover(client, tel, lead, other)
    assert (response.status_code, response.json()["detail"][0]["msg"]) == (422, "Choose an active counselor of the lead's division")
    inactive = await make_counselor(db_session, "it", active=False)
    assert (await handover(client, tel, lead, inactive)).status_code == 422


@pytest.mark.asyncio
async def test_a_closed_lead_and_a_linked_lead_cannot_be_handed_over(client, db_session):
    _, tel, counselor, closed = await setup(db_session, status="not_interested")
    response = await handover(client, tel, closed, counselor)
    assert (response.status_code, response.json()["detail"]) == (409, "This lead is closed; reopen it before handing it over")
    _, tel2, counselor2, linked = await setup(db_session, status="application_enrollment")
    response = await handover(client, tel2, linked, counselor2)
    assert (response.status_code, response.json()["detail"]) == (409, "This lead is already past the counselor handover")


@pytest.mark.asyncio
async def test_the_manager_hands_over_and_changes_the_counselor(client, db_session):
    manager, tel, counselor, lead = await setup(db_session)
    assert (await handover(client, manager, lead, counselor)).status_code == 200
    second = await make_counselor(db_session, "it")
    response = await handover(client, manager, lead, second)
    assert (response.status_code, response.json()["counselor"]["id"]) == (200, str(second.id))
    again = await client.post(handover_url(lead.id), json={"counselor_id": str(second.id)})
    assert (again.status_code, again.json()["detail"]) == (409, "This lead is already with this counselor")


@pytest.mark.asyncio
async def test_out_of_scope_and_other_roles(client, db_session):
    _, _, counselor, lead = await setup(db_session)
    stranger = await make_telecaller(db_session, await make_tl_manager(db_session))
    assert (await handover(client, stranger, lead, counselor)).status_code == 404
    assert (await handover(client, counselor, lead, counselor)).status_code == 403
    await as_user(client, stranger)
    assert (await client.post(handover_url(uuid.uuid4()), json={"counselor_id": str(counselor.id)})).status_code == 404
    assert (await client.post(handover_url(lead.id), json={"counselor_id": str(counselor.id), "extra": 1})).status_code == 422


@pytest.mark.asyncio
async def test_the_counselor_lists_and_reads_only_their_own_leads(client, db_session):
    _, tel, counselor, lead = await setup(db_session)
    _, _, _, other_lead = await setup(db_session)
    assert (await handover(client, tel, lead, counselor)).status_code == 200
    await as_user(client, counselor)
    page = (await client.get(COUNSELOR_LEADS)).json()
    assert [item["id"] for item in page["items"]] == [str(lead.id)] and page["total"] == 1
    detail = await client.get(c_url(lead.id))
    assert detail.status_code == 200
    assert detail.json()["permissions"] == {"return": True, "link": True, "unlink": False}
    assert detail.json()["milestones"] == {"student": None, "items": []}
    assert (await client.get(c_url(other_lead.id))).status_code == 404
    assert (await client.get(c_url(lead.id, "/timeline"))).status_code == 200
    await as_user(client, tel)
    assert (await client.get(COUNSELOR_LEADS)).status_code == 403
