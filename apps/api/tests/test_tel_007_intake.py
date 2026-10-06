"""tel-007 DI2 -- website and BDM-entered leads are distributed in the intake transaction (spec §4-§5; AC7)."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadStageHistory
from app.services import lead_distribution
from tests.bdm009_helpers import bdm_with_org
from tests.bdm017_helpers import add_lead
from tests.tel007_helpers import make_telecaller, make_tl_manager

URL = "/api/v1/public/enquiries"


@pytest.fixture(autouse=True)
def no_crm(monkeypatch):
    from app.api import bdm_leads, public

    monkeypatch.setattr(public.sync_enquiry_to_crm_task, "delay", lambda _id: None)
    monkeypatch.setattr(bdm_leads.sync_enquiry_to_crm_task, "delay", lambda _id: None)


def _body(division: str = "it") -> dict:
    return {"division": division, "name": "Asha N", "email": f"{uuid.uuid4().hex[:8]}@example.com", "phone": "9876543210",
            "subject": "Cyber security course", "message": "Please call me back."}


async def _assignment(db, lead_id):
    row = await db.get(Enquiry, uuid.UUID(lead_id), populate_existing=True)
    history = (await db.execute(select(LeadStageHistory.to_stage, LeadStageHistory.event).where(LeadStageHistory.lead_id == row.id))).all()
    audits = (await db.scalars(select(AuditLog.metadata_json).where(AuditLog.action == "lead.assign", AuditLog.entity_id == str(row.id)))).all()
    return row, history, audits


@pytest.mark.asyncio
@pytest.mark.parametrize("division", ["it", "overseas"])
async def test_a_website_enquiry_is_assigned_round_robin(client, db_session, division):
    await make_telecaller(db_session, await make_tl_manager(db_session), team=division)  # at least one eligible telecaller
    response = await client.post(URL, json=_body(division))
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "assigned"
    row, history, audits = await _assignment(db_session, response.json()["id"])
    assert row.telecaller_user_id is not None and row.status == "assigned"
    assert history == [("assigned", "assigned")]
    assert audits == [{"from": None, "to": str(row.telecaller_user_id), "method": "round_robin"}]


@pytest.mark.asyncio
async def test_a_distribution_error_never_loses_the_enquiry(client, db_session, monkeypatch):
    async def broken(db, lead):
        raise RuntimeError("boom")

    monkeypatch.setattr(lead_distribution, "distribute", broken)
    response = await client.post(URL, json=_body())
    assert response.status_code == 201 and response.json()["status"] == "new"
    row, history, audits = await _assignment(db_session, response.json()["id"])
    assert row.telecaller_user_id is None and history == [] and audits == []


@pytest.mark.asyncio
async def test_a_bdm_lead_is_distributed_to_its_division(client, db_session):
    await make_telecaller(db_session, await make_tl_manager(db_session), team="it")
    _, _, org = await bdm_with_org(client, db_session, "college")  # college -> IT
    created = await add_lead(client, org["id"])
    assert created["status"] == "assigned"
    row, history, audits = await _assignment(db_session, created["id"])
    assert row.division == "it" and row.telecaller_user_id is not None
    assert history == [("assigned", "assigned")] and audits[0]["method"] == "round_robin"
