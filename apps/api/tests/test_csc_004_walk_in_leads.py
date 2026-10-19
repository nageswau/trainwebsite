"""csc-004 (DEC-SCOPE-229; W1, W2, W4, W5) -- an overseas counselor creates a walk-in lead: it is theirs (`owner_id`), in their division,
distributed to a telecaller like a manager's lead (tel-007), and read-only for that telecaller (D1/T19). The tel-005 rules (catalogue,
duplicate panel, "Add enquiry to this lead") are reused under /counselor/walk-in-leads. The shared database is never truncated, so every
test uses a fresh mobile, email and product."""

import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Enquiry, LeadEnquiry
from app.services import lead_distribution
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import stage_url
from tests.tel007_helpers import make_telecaller, make_tl_manager, make_user, product, rule

URL = "/api/v1/counselor/walk-in-leads"
CHECK = f"{URL}/duplicate-check"


@pytest.fixture(autouse=True)
def no_crm(monkeypatch):
    from app.api import counselor_walk_in_leads

    monkeypatch.setattr(counselor_walk_in_leads.sync_enquiry_to_crm_task, "delay", lambda _id: None)


def mobile() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


def mail() -> str:
    return f"c4-{uuid.uuid4().hex[:10]}@example.com"


async def setup(db):
    """An overseas counselor, an overseas telecaller with a product rule (deterministic distribution) and that product."""
    counselor = await make_user(db, "counselor", "overseas")
    telecaller = await make_telecaller(db, await make_tl_manager(db), team="overseas")
    item = await product(db, group="overseas", team="overseas")
    await rule(db, telecaller, team="overseas", product_id=item.id)
    return counselor, telecaller, item


def body(item, **over) -> dict:
    return {"name": "Walk-in Lead", "phone": mobile(), "email": mail(), "product_id": str(item.id), "source": "walk_in"} | over


# --- create (W2, W4) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_counselor_creates_a_walk_in_lead_that_is_theirs_and_distributed(client, db_session):
    counselor, telecaller, item = await setup(db_session)
    await as_user(client, counselor)
    response = await client.post(URL, json=body(item, city="Pune"))
    assert response.status_code == 201, response.text
    out = response.json()
    assert out["in_scope"] is True and out["source"] == "walk_in"
    row = await db_session.get(Enquiry, uuid.UUID(out["id"]), populate_existing=True)
    assert (row.owner_id, row.division, row.telecaller_user_id, row.status) == (counselor.id, "overseas", telecaller.id, "assigned")
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "lead.create", AuditLog.entity_id == out["id"]))
    assert audit.user_id == counselor.id and audit.metadata_json["walk_in"] is True and row.phone not in str(audit.metadata_json)
    mine = await client.get("/api/v1/counselor/leads")
    assert out["id"] in [lead["id"] for lead in mine.json()["items"]]
    assert (await client.get(f"/api/v1/counselor/leads/{out['id']}")).status_code == 200


@pytest.mark.asyncio
async def test_the_distributed_telecaller_can_read_but_not_change_it_and_their_manager_still_can(client, db_session):
    counselor, telecaller, item = await setup(db_session)
    await as_user(client, counselor)
    lead_id = (await client.post(URL, json=body(item))).json()["id"]
    await as_user(client, telecaller)
    assert (await client.get(f"/api/v1/telecaller/leads/{lead_id}")).json()["read_only"] is True
    assert (await client.post(stage_url(lead_id), json={"to_stage": "interested"})).status_code == 403


@pytest.mark.asyncio
async def test_a_distribution_failure_keeps_the_lead_with_the_counselor(client, db_session, monkeypatch):
    async def broken(db, lead):
        raise RuntimeError("boom")

    monkeypatch.setattr(lead_distribution, "distribute", broken)
    counselor, _, item = await setup(db_session)
    await as_user(client, counselor)
    response = await client.post(URL, json=body(item))
    assert response.status_code == 201
    row = await db_session.get(Enquiry, uuid.UUID(response.json()["id"]), populate_existing=True)
    assert (row.owner_id, row.telecaller_user_id, row.status) == (counselor.id, None, "new")


@pytest.mark.asyncio
async def test_an_it_team_product_is_422_and_another_division_is_422(client, db_session):
    counselor, _, item = await setup(db_session)
    it_product = await product(db_session, group="it", team="it")
    await as_user(client, counselor)
    assert (await client.post(URL, json=body(it_product))).status_code == 422
    assert (await client.post(URL, json=body(item, division="it"))).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"owner_id": str(uuid.uuid4())}, {"telecaller_user_id": str(uuid.uuid4())}, {"status": "qualified"}])
async def test_ownership_and_stage_cannot_be_supplied(client, db_session, extra):
    counselor, _, item = await setup(db_session)
    await as_user(client, counselor)
    assert (await client.post(URL, json=body(item, **extra))).status_code == 422


# --- duplicates (tel-005 R2, I5) ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_known_person_is_409_with_the_panel_and_in_scope_only_for_the_counselors_own_lead(client, db_session):
    counselor, telecaller, item = await setup(db_session)
    other = await make_user(db_session, "counselor", "overseas")
    await as_user(client, counselor)
    first = body(item)
    mine = (await client.post(URL, json=first)).json()["id"]
    response = await client.post(URL, json=body(item, phone=first["phone"], email=mail()))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "duplicate_lead" and [(m["id"], m["in_scope"]) for m in detail["matches"]] == [(mine, True)]
    assert first["phone"] not in str(detail) and first["email"] not in str(detail)
    await as_user(client, other)
    other_view = await client.get(CHECK, params={"phone": first["phone"]})
    assert other_view.status_code == 200 and [(m["id"], m["in_scope"]) for m in other_view.json()["matches"]] == [(mine, False)]
    assert (await client.get(CHECK)).status_code == 422


@pytest.mark.asyncio
async def test_the_counselor_adds_the_enquiry_to_an_existing_lead(client, db_session):
    counselor, telecaller, item = await setup(db_session)
    existing = Enquiry(division="overseas", name="Already A Lead", phone=mobile(), email=mail(), subject="MS in Germany", message="",
                       source="website", telecaller_user_id=telecaller.id)  # fmt: skip
    db_session.add(existing)
    await db_session.commit()
    await as_user(client, counselor)
    response = await client.post(f"{URL}/{existing.id}/enquiries", json={"subject": "Walked in", "source": "walk_in", "message": "Visited office"})
    assert response.status_code == 201, response.text
    row = await db_session.scalar(select(LeadEnquiry).where(LeadEnquiry.lead_id == existing.id))
    assert (row.source, row.created_by_user_id) == ("walk_in", counselor.id)
    assert (await client.post(f"{URL}/{uuid.uuid4()}/enquiries", json={"subject": "x", "source": "walk_in"})).status_code == 404


# --- who (W1) -------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "it"), ("telecaller", "overseas"), ("telecaller_manager", "global"), ("overseas_admin", "overseas"), ("overseas_student", "overseas")])
async def test_everyone_but_the_overseas_counselor_is_403(client, db_session, role, division):
    _, _, item = await setup(db_session)
    actor = await make_user(db_session, role, division)
    await as_user(client, actor)
    assert (await client.post(URL, json=body(item))).status_code == 403
    assert (await client.get(CHECK, params={"phone": mobile()})).status_code == 403
    assert (await client.post(f"{URL}/{uuid.uuid4()}/enquiries", json={"subject": "x", "source": "walk_in"})).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client):
    assert (await client.post(URL, json={})).status_code == 401
    assert (await client.get(CHECK, params={"phone": mobile()})).status_code == 401
