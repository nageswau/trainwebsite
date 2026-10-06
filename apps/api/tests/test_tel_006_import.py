"""tel-006 -- CSV lead import per campaign (spec §1, §3; DEC-SCOPE-091; IM1, R1-R12). The test database is shared and never truncated,
and the duplicate match runs across every lead, so every row uses a fresh mobile number and email. Distribution is replaced by a recorder
(the shared database holds many active IT telecallers) and the CRM task by a list, so each test sees only its own calls."""

import csv
import io
import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.api import telecaller_import
from app.models import AuditLog, Enquiry, LeadEnquiry, LeadImportBatch, TelCampaign, TelProduct
from app.services import lead_distribution
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_telecaller, make_tl_manager, make_user

IMPORTS = "/api/v1/telecaller/imports"
TEMPLATE = f"{IMPORTS}/template"
HEADER = ["name", "phone", "email", "whatsapp_number", "city", "state", "qualification", "passing_year", "institution", "priority", "subject",
          "message"]


def mobile() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


def mail() -> str:
    return f"t6-{uuid.uuid4().hex[:10]}@example.com"


def row(**over) -> dict:
    return {"name": f"Import {uuid.uuid4().hex[:6]}", "phone": mobile(), "email": mail()} | over


def csv_bytes(rows: list[dict], header: list[str] | None = None, *, bom: bool = False) -> bytes:
    header = header or HEADER
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for r in rows:
        writer.writerow([r.get(name.strip().lower(), "") for name in header])
    return (("﻿" if bom else "") + buffer.getvalue()).encode()


async def campaign(db, *, active: bool = True, group: str = "it", product_name: str = "Cyber Security") -> TelCampaign:
    if group == "it":
        product = await db.scalar(select(TelProduct).where(TelProduct.product_group == "it", TelProduct.name == product_name))
    else:  # an `other` product without a team (T18)
        product = TelProduct(product_group="other", name=f"Other {uuid.uuid4().hex[:8]}", team=None)
        db.add(product)
        await db.flush()
    camp = TelCampaign(name=f"Import {uuid.uuid4().hex[:8]}", source="facebook", product_id=product.id, start_date=date(2026, 9, 1), active=active)
    db.add(camp)
    await db.commit()
    return camp


async def upload(client, camp, content: bytes, *, key: str | None = None, division: str | None = None):
    data = {"campaign_id": str(camp.id)} | ({"division": division} if division else {})
    headers = {"Idempotency-Key": key or uuid.uuid4().hex}
    return await client.post(IMPORTS, data=data, files={"file": ("leads.csv", content, "text/csv")}, headers=headers)


@pytest.fixture
def recorded(monkeypatch):
    """Distribution and the CRM queue, recorded instead of run."""
    calls = {"distributed": [], "crm": []}

    async def distribute(db, lead):
        calls["distributed"].append(lead.id)
        return None

    monkeypatch.setattr(lead_distribution, "distribute", distribute)
    monkeypatch.setattr(telecaller_import.sync_enquiry_to_crm_task, "delay", lambda lead_id: calls["crm"].append(lead_id))
    return calls


async def manager_in(client, db):
    manager = await make_tl_manager(db)
    await as_user(client, manager)
    return manager


async def batch_of(db, report) -> LeadImportBatch:
    db.expire_all()
    return await db.get(LeadImportBatch, uuid.UUID(report["id"]))


# --- AC1: created leads carry the campaign ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_valid_file_creates_campaign_leads_and_distributes_them(client, db_session, recorded):
    manager = await manager_in(client, db_session)
    camp = await campaign(db_session)
    rows = [row(city="Pune", priority="hot", passing_year="2024"), row(subject="Weekend batch", message="Call after 6"), row()]
    response = await upload(client, camp, csv_bytes(rows))
    assert response.status_code == 201, response.text
    report = response.json()
    assert (report["total_rows"], report["created_count"], report["attached_count"], report["rejected_count"]) == (3, 3, 0, 0)
    assert report["campaign"] == {"id": str(camp.id), "name": camp.name} and report["division"] == "it"
    assert [r["row_number"] for r in report["rows"]] == [2, 3, 4] and {r["status"] for r in report["rows"]} == {"created"}
    leads = [await db_session.get(Enquiry, uuid.UUID(r["lead_id"])) for r in report["rows"]]
    for lead, r in zip(leads, report["rows"], strict=True):
        assert (lead.campaign_id, lead.product_id, lead.source, lead.division) == (camp.id, camp.product_id, "facebook", "it")
        assert lead.metadata_json["import_batch_id"] == report["id"] and r["lead_code"] == lead.lead_code
        assert (lead.status, lead.telecaller_user_id) == ("new", None)  # R4: a manager's lead, handed to distribution
    assert (leads[0].city, leads[0].priority, leads[0].passing_year, leads[0].subject, leads[0].message) == ("Pune", "hot", 2024, "Cyber Security", "")
    assert (leads[1].subject, leads[1].message, leads[1].priority) == ("Weekend batch", "Call after 6", "warm")  # R3 defaults
    assert recorded["distributed"] == [lead.id for lead in leads]
    assert recorded["crm"] == [str(lead.id) for lead in leads]  # R6: after the commit, once per created lead
    [audit] = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == report["id"], AuditLog.action == "lead.import"))).all()
    assert audit.user_id == manager.id and audit.metadata_json["created"] == 3


@pytest.mark.asyncio
async def test_a_real_distribution_assigns_imported_leads_to_the_teams_telecallers(client, db_session, monkeypatch):
    monkeypatch.setattr(telecaller_import.sync_enquiry_to_crm_task, "delay", lambda lead_id: None)
    manager = await manager_in(client, db_session)
    await make_telecaller(db_session, manager)
    camp = await campaign(db_session)
    report = (await upload(client, camp, csv_bytes([row()]))).json()
    lead = await db_session.get(Enquiry, uuid.UUID(report["rows"][0]["lead_id"]))
    assert lead.status == "assigned" and lead.telecaller_user_id is not None  # an active IT telecaller exists, so round robin picks one


# --- AC2: duplicates attach -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_known_person_attaches_as_an_enquiry(client, db_session, recorded):
    manager = await manager_in(client, db_session)
    phone = mobile()
    old = Enquiry(division="it", name="Known", email=mail(), phone=phone, subject="Python", message="Earlier", source="website", status="lost")
    db_session.add(old)
    await db_session.commit()
    camp = await campaign(db_session)
    before = await db_session.scalar(select(func.count()).select_from(Enquiry))
    report = (await upload(client, camp, csv_bytes([row(phone=f"+91 {phone[:5]} {phone[5:]}", subject="Fees")]))).json()
    assert (report["created_count"], report["attached_count"]) == (0, 1)
    assert report["rows"][0] == {"row_number": 2, "status": "attached", "lead_id": str(old.id), "lead_code": old.lead_code, "error": None}
    assert await db_session.scalar(select(func.count()).select_from(Enquiry)) == before
    [enquiry] = (await db_session.scalars(select(LeadEnquiry).where(LeadEnquiry.lead_id == old.id))).all()
    assert (enquiry.subject, enquiry.source, enquiry.campaign_id, enquiry.created_by_user_id) == ("Fees", "facebook", camp.id, manager.id)
    assert enquiry.metadata_json == {"import_batch_id": report["id"]}
    await db_session.refresh(old)
    assert old.status == "lost"  # R5: the stage never moves
    assert recorded["crm"] == [] and recorded["distributed"] == []  # R6: nothing queued for an attached row


@pytest.mark.asyncio
async def test_the_same_person_twice_in_one_file_attaches_to_the_lead_the_first_row_made(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    email = mail()
    report = (await upload(client, camp, csv_bytes([row(email=email), row(email=email.upper(), subject="Again")]))).json()
    first, second = report["rows"]
    assert (first["status"], second["status"], second["lead_id"]) == ("created", "attached", first["lead_id"])


# --- AC3: invalid rows are reported -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_invalid_rows_are_rejected_with_their_line_and_valid_rows_still_land(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    secret = row(phone="12345")
    rows = [row(), secret, row(name=""), row(priority="urgent"), row(passing_year="1800"), row(passing_year="  ")]
    report = (await upload(client, camp, csv_bytes(rows))).json()
    assert (report["created_count"], report["rejected_count"]) == (2, 4)
    statuses = {r["row_number"]: (r["status"], r["error"]) for r in report["rows"]}
    assert statuses[2] == ("created", None) and statuses[7][0] == "created"  # a blank optional cell is just empty
    assert statuses[3][0] == "rejected" and statuses[3][1].startswith("phone")
    assert statuses[4][0] == "rejected" and statuses[4][1].startswith("name")
    assert statuses[5][0] == "rejected" and statuses[5][1].startswith("priority")
    assert statuses[6][0] == "rejected" and statuses[6][1].startswith("passing_year")
    stored = str((await batch_of(db_session, report)).results_json)
    assert secret["email"] not in stored and secret["name"] not in stored and "12345" not in stored  # R9


@pytest.mark.parametrize(("header", "detail"), [
    (["name", "email"], "Missing required column: phone"),
    (HEADER + ["course"], "Unknown column: course"),
    (HEADER + ["name"], "Duplicate column: name"),
])
@pytest.mark.asyncio
async def test_a_bad_header_is_422_before_any_row(client, db_session, recorded, header, detail):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    before = await db_session.scalar(select(func.count()).select_from(LeadImportBatch))
    response = await upload(client, camp, csv_bytes([row()], header))
    assert (response.status_code, response.json()["detail"]) == (422, detail)
    assert await db_session.scalar(select(func.count()).select_from(LeadImportBatch)) == before


@pytest.mark.asyncio
async def test_file_limits(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    empty = await upload(client, camp, csv_bytes([]))
    assert (empty.status_code, empty.json()["detail"]) == (422, "The file has no filled-in rows")
    many = await upload(client, camp, csv_bytes([{"name": "X", "phone": "9000000000"}] * 501))
    assert (many.status_code, many.json()["detail"]) == (422, "The file has more than 500 filled-in rows")
    big = await upload(client, camp, b"name,phone\n" + b"x" * (1024 * 1024))
    assert big.status_code == 413
    excel = await upload(client, camp, csv_bytes([row()], ["Name", "PHONE", "Email"], bom=True))
    assert excel.status_code == 201 and excel.json()["created_count"] == 1


# --- campaign / division (R2) -------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_an_inactive_campaign_is_422(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session, active=False)
    response = await upload(client, camp, csv_bytes([row()]))
    assert (response.status_code, response.json()["detail"]) == (422, "Choose an active campaign")


@pytest.mark.asyncio
async def test_a_product_without_a_team_needs_a_division(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session, group="other")
    missing = await upload(client, camp, csv_bytes([row()]))
    assert (missing.status_code, missing.json()["detail"]) == (422, "Choose the division (IT or Overseas) for this product")
    report = (await upload(client, camp, csv_bytes([row()]), division="overseas")).json()
    lead = await db_session.get(Enquiry, uuid.UUID(report["rows"][0]["lead_id"]))
    assert (report["division"], lead.division) == ("overseas", "overseas")


@pytest.mark.asyncio
async def test_a_division_that_contradicts_the_products_team_is_422(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    response = await upload(client, camp, csv_bytes([row()]), division="overseas")
    assert (response.status_code, response.json()["detail"]) == (422, "Cyber Security belongs to the IT team")


# --- AC4: idempotency (R8) ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_same_key_and_file_replays_and_creates_nothing(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    content, key = csv_bytes([row(), row()]), uuid.uuid4().hex
    first = await upload(client, camp, content, key=key)
    before = await db_session.scalar(select(func.count()).select_from(Enquiry))
    again = await upload(client, camp, content, key=key)
    assert again.status_code == 201 and again.json() == first.json()
    assert await db_session.scalar(select(func.count()).select_from(Enquiry)) == before
    assert len(recorded["crm"]) == 2
    other = await upload(client, camp, csv_bytes([row()]), key=key)
    assert (other.status_code, other.json()["detail"]) == (422, "Idempotency-Key was already used for a different file")
    camp2 = await campaign(db_session)
    moved = await upload(client, camp2, content, key=key)
    assert (moved.status_code, moved.json()["detail"]) == (422, "Idempotency-Key was already used for a different file")


@pytest.mark.asyncio
async def test_the_key_is_required(client, db_session, recorded):
    await manager_in(client, db_session)
    camp = await campaign(db_session)
    response = await client.post(IMPORTS, data={"campaign_id": str(camp.id)}, files={"file": ("l.csv", csv_bytes([row()]), "text/csv")})
    assert (response.status_code, response.json()["detail"]) == (422, "Idempotency-Key header is required")


# --- R1: roles -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["telecaller", "counselor"])
@pytest.mark.asyncio
async def test_other_roles_are_403(client, db_session, recorded, role):
    manager = await make_tl_manager(db_session)
    user = await make_telecaller(db_session, manager) if role == "telecaller" else await make_user(db_session, role, "it")
    await as_user(client, user)
    camp = await campaign(db_session)
    assert (await upload(client, camp, csv_bytes([row()]))).status_code == 403
    assert (await client.get(TEMPLATE)).status_code == 403
    assert (await client.get(IMPORTS)).status_code == 403


@pytest.mark.asyncio
async def test_anonymous_is_401(client, db_session, recorded):
    client.cookies.clear()
    camp = await campaign(db_session)
    assert (await upload(client, camp, csv_bytes([row()]))).status_code == 401
    assert (await client.get(IMPORTS)).status_code == 401


@pytest.mark.asyncio
async def test_the_template_is_the_header_row(client, db_session):
    await manager_in(client, db_session)
    response = await client.get(TEMPLATE)
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    assert response.text.strip().split(",") == HEADER


# --- R11: history and report ----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_history_lists_own_batches_and_the_report_is_private(client, db_session, recorded):
    camp = await campaign(db_session)
    other = await manager_in(client, db_session)
    theirs = (await upload(client, camp, csv_bytes([row()]))).json()
    me = await manager_in(client, db_session)
    mine = (await upload(client, camp, csv_bytes([row(), row(phone="1")]))).json()
    page = (await client.get(IMPORTS)).json()
    assert [item["id"] for item in page["items"]] == [mine["id"]] and page["total"] == 1
    item = page["items"][0]
    assert item["uploaded_by"] == {"id": str(me.id), "full_name": me.full_name} and item["campaign"]["name"] == camp.name
    assert (item["total_rows"], item["created_count"], item["rejected_count"]) == (2, 1, 1)
    assert (await client.get(f"{IMPORTS}/{mine['id']}")).json() == mine
    hidden = await client.get(f"{IMPORTS}/{theirs['id']}")
    assert (hidden.status_code, hidden.json()["detail"]) == (404, "Import not found")
    admin = await make_user(db_session, "super_admin", "global")
    await as_user(client, admin)
    ids = [item["id"] for item in (await client.get(f"{IMPORTS}?limit=100")).json()["items"]]
    assert {mine["id"], theirs["id"]} <= set(ids)
    assert (await client.get(f"{IMPORTS}/{theirs['id']}")).status_code == 200
    assert other.id != me.id
