"""pob-024 -- the placement closure record and the invoice draft (DEC-SCOPE-432 P1-P14; AC1-AC4). The shared test database is never
truncated, so every value is unique per test."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Company, Job, Notification, Placement, RecruiterInvoice
from app.services import placements as svc
from tests.rec001_helpers import login, make_recruiter, make_user
from tests.test_rec_022_offers import _app_status, _offer, _setup, _status

PLACEMENTS = "/api/v1/recruiter/placements"
OFFERS = "/api/v1/recruiter/offers"
TODAY = date.today()
JOINED = {"joining_status": "joined", "actual_joining_date": TODAY.isoformat(), "confirmed_by": "HR - Priya"}


async def _world(client, db, *, fee=("fixed", "50000"), trigger=None, days=None) -> dict:
    s = await _setup(client, db)
    job = await db.scalar(select(Job).where(Job.id == s["job"].id))
    job.assigned_recruiter_user_id = s["recruiter"].id
    job.fee_basis, job.fee_value = (fee[0], Decimal(fee[1])) if fee else (None, None)
    job.payment_trigger, job.payment_days = trigger, days
    await db.commit()
    s["offer"] = await _offer(client, s["application"]["id"])
    return s


async def _accept(client, s) -> dict:
    response = await _status(client, s["offer"]["id"], "accepted")
    assert response.status_code == 200, response.text
    s["offer"] = response.json()["offer"]
    return s["offer"]


async def _join(client, s, body=JOINED):
    response = await client.put(f"{OFFERS}/{s['offer']['id']}/joining", json=body)
    assert response.status_code == 200, response.text
    return response.json()["offer"]


async def _placement(client, placement_id) -> dict:
    response = await client.get(f"{PLACEMENTS}/{placement_id}")
    assert response.status_code == 200, response.text
    return response.json()["placement"]


async def _count(db, offer_id) -> int:
    return await db.scalar(select(func.count()).select_from(Placement).where(Placement.offer_id == offer_id))


def _issue_body(**over) -> dict:
    return {"invoice_number": f"INV-{uuid4().hex[:8]}", "invoice_date": TODAY.isoformat(), "due_date": (TODAY + timedelta(days=30)).isoformat(), "amount": "50000.00"} | over


# --- AC1: accepting an offer creates one placement (P1/P2/P7) ------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_accepting_an_offer_creates_one_placement(client, db_session):
    s = await _world(client, db_session)
    assert s["offer"]["placement_id"] is None
    offer = await _accept(client, s)
    assert offer["placement_id"] and await _count(db_session, offer["id"]) == 1
    p = await _placement(client, offer["placement_id"])
    assert (p["status"], p["status_label"], p["role"]) == ("pending", "Joining pending", "Java Developer")
    assert p["candidate"]["id"] == str(s["candidate"].id) and p["requirement"]["id"] == str(s["job"].id)
    assert p["recruiter"]["id"] == str(s["recruiter"].id) and p["po_owner"]["id"] == str(s["recruiter"].id)  # the company owner
    assert p["source"] == "Referral"
    assert p["package"] == {"compensation": "600000.00", "currency": "INR"}
    assert p["commercials"]["expected_fee"] == "50000.00" and p["commercials"]["invoice"]["status"] == "none"
    assert (await _status(client, offer["id"], "accepted")).status_code == 409
    assert await _count(db_session, offer["id"]) == 1
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "placement.created", AuditLog.entity_id == p["id"]))
    assert audit.metadata_json["offer_id"] == offer["id"]


# --- AC2: joining creates exactly one invoice draft (P8/P9) --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_joining_creates_exactly_one_invoice_draft_due_per_the_payment_trigger(client, db_session):
    s = await _world(client, db_session, trigger="days_after_joining", days=30)
    placement_id = (await _accept(client, s))["placement_id"]
    offer = await _join(client, s)
    assert offer["placement_id"] == placement_id
    invoice = (await _placement(client, placement_id))["commercials"]["invoice"]
    assert (invoice["status"], invoice["draft_amount"], invoice["draft_due_date"]) == ("draft", "50000.00", (TODAY + timedelta(days=30)).isoformat())
    assert await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "placement.draft_created", AuditLog.entity_id == placement_id)) == 1
    assert await _app_status(db_session, s["application"]["id"]) == "joined"


@pytest.mark.asyncio
async def test_a_percentage_fee_is_priced_on_the_offer_and_due_on_joining(client, db_session):
    s = await _world(client, db_session, fee=("percent_of_ctc", "8.33"))
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    invoice = (await _placement(client, placement_id))["commercials"]["invoice"]
    assert (invoice["draft_amount"], invoice["draft_due_date"]) == ("49980.00", TODAY.isoformat())


@pytest.mark.asyncio
async def test_an_unpriced_hire_still_gets_one_draft_without_an_amount(client, db_session):
    s = await _world(client, db_session, fee=None)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    p = await _placement(client, placement_id)
    assert p["commercials"]["expected_fee"] is None
    assert (p["commercials"]["invoice"]["status"], p["commercials"]["invoice"]["draft_amount"]) == ("draft", None)


# --- AC3: issuing the draft feeds the receivables (P10) ------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_issuing_the_draft_creates_an_invoice_in_the_receivables(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    body = _issue_body()
    issued = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=body)
    assert issued.status_code == 201, issued.text
    invoice = issued.json()["placement"]["commercials"]["invoice"]
    assert invoice["status"] == "issued" and invoice["invoice"]["invoice_number"] == body["invoice_number"]
    row = await db_session.scalar(select(RecruiterInvoice).where(RecruiterInvoice.invoice_number == body["invoice_number"]))
    assert (row.job_id, row.amount) == (s["job"].id, Decimal("50000.00"))
    page = (await client.get("/api/v1/recruiter/invoices", params={"view": "outstanding", "company_id": str(s["job"].company_id)})).json()
    assert body["invoice_number"] in {i["invoice_number"] for i in page["items"]}
    revenue = (await client.get(f"/api/v1/recruiter/requirements/{s['job'].id}/revenue")).json()
    assert revenue["outstanding"] == "50000.00"
    again = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body())
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_issue_rules_number_taken_amount_and_no_draft(client, db_session):
    s = await _world(client, db_session, fee=None)
    placement_id = (await _accept(client, s))["placement_id"]
    assert (await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body())).status_code == 409  # no draft yet
    await _join(client, s)
    first = _issue_body()
    other = await _world(client, db_session)  # signs in as another team
    other_id = (await _accept(client, other))["placement_id"]
    await _join(client, other)
    assert (await client.post(f"{PLACEMENTS}/{other_id}/invoice-draft/issue", json=first)).status_code == 201
    await login(client, s["recruiter"])
    taken = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body(invoice_number=first["invoice_number"].lower()))
    assert taken.status_code == 409 and taken.json()["detail"]["code"] == "invoice_number_taken"
    late = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body(due_date=(TODAY - timedelta(days=1)).isoformat()))
    assert late.status_code == 422


# --- edge: discard, and Did Not Join (P11) ----------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_draft_can_be_discarded_with_a_reason(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    assert (await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/cancel", json={"reason": "x"})).status_code == 422
    cancelled = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/cancel", json={"reason": "Client pays through a vendor"})
    assert cancelled.status_code == 200, cancelled.text
    invoice = cancelled.json()["placement"]["commercials"]["invoice"]
    assert (invoice["status"], invoice["discard_reason"]) == ("discarded", "Client pays through a vendor")
    assert (await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body())).status_code == 409


@pytest.mark.asyncio
async def test_did_not_join_leaves_no_draft_and_a_read_only_placement(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s, {"joining_status": "did_not_join", "reason": "Took another offer"})
    p = await _placement(client, placement_id)
    assert (p["status"], p["commercials"]["invoice"]["status"], p["permissions"]["can_edit"]) == ("did_not_join", "none", False)
    refused = await client.patch(f"{PLACEMENTS}/{placement_id}", json={"candidate_confirmation": {"by": "Rahul", "on": TODAY.isoformat(), "via": "call"}})
    assert refused.status_code == 409


@pytest.mark.asyncio
async def test_did_not_join_discards_an_open_draft(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    row = await db_session.scalar(select(Placement).where(Placement.id == placement_id))
    row.invoice_status, row.draft_amount, row.draft_due_date, row.draft_created_at = "draft", Decimal("1.00"), TODAY, datetime.now(UTC)
    await db_session.commit()
    await _join(client, s, {"joining_status": "did_not_join", "reason": "Took another offer"})
    invoice = (await _placement(client, placement_id))["commercials"]["invoice"]
    assert (invoice["status"], invoice["discard_reason"]) == ("discarded", "Did not join")


# --- P5/P6: confirmations and the PO owner ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_candidate_and_client_confirmations_are_kept_separately(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    body = {"candidate_confirmation": {"by": "Rahul (candidate)", "on": TODAY.isoformat(), "via": "whatsapp"}}
    saved = await client.patch(f"{PLACEMENTS}/{placement_id}", json=body)
    assert saved.status_code == 200, saved.text
    p = saved.json()["placement"]
    assert p["candidate_confirmation"] == {"by": "Rahul (candidate)", "on": TODAY.isoformat(), "via": "whatsapp", "via_label": "WhatsApp"}
    assert p["client_confirmation"] is None
    client_body = {"client_confirmation": {"by": "HR - Priya", "on": TODAY.isoformat(), "via": "email"}}
    p = (await client.patch(f"{PLACEMENTS}/{placement_id}", json=client_body)).json()["placement"]
    assert p["candidate_confirmation"]["by"] == "Rahul (candidate)" and p["client_confirmation"]["via_label"] == "Email"
    future = {"client_confirmation": {"by": "HR", "on": (TODAY + timedelta(days=1)).isoformat(), "via": "email"}}
    assert (await client.patch(f"{PLACEMENTS}/{placement_id}", json=future)).status_code == 422
    assert (await client.patch(f"{PLACEMENTS}/{placement_id}", json={"client_confirmation": {"by": "HR", "on": TODAY.isoformat(), "via": "fax"}})).status_code == 422
    cleared = (await client.patch(f"{PLACEMENTS}/{placement_id}", json={"candidate_confirmation": None})).json()["placement"]
    assert cleared["candidate_confirmation"] is None
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "placement.updated", AuditLog.entity_id == placement_id).limit(1))
    assert audit.metadata_json["fields"] == ["candidate_confirmation"]


@pytest.mark.asyncio
async def test_only_a_team_lead_changes_the_po_owner(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    other = await make_recruiter(db_session, s["manager"])
    assert (await client.patch(f"{PLACEMENTS}/{placement_id}", json={"po_owner_user_id": str(other.id)})).status_code == 403
    await login(client, s["manager"])
    saved = await client.patch(f"{PLACEMENTS}/{placement_id}", json={"po_owner_user_id": str(other.id)})
    assert saved.status_code == 200, saved.text
    assert saved.json()["placement"]["po_owner"]["id"] == str(other.id)
    bdm = await make_user(db_session, "bdm", "it")
    assert (await client.patch(f"{PLACEMENTS}/{placement_id}", json={"po_owner_user_id": str(bdm.id)})).status_code == 422


# --- P4/P14: scope and the commercial gate -----------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scope_and_the_commercial_gate(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    outsider = await make_recruiter(db_session, await make_user(db_session, "placement_manager", "global"))
    await login(client, outsider)
    assert (await client.get(f"{PLACEMENTS}/{placement_id}")).status_code == 404
    assert (await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body())).status_code == 404
    bdm = await make_user(db_session, "bdm", "it")
    company = await db_session.scalar(select(Company).where(Company.id == s["job"].company_id))
    company.assigned_bdm_user_id = bdm.id
    await db_session.commit()
    await login(client, bdm)
    p = await _placement(client, placement_id)
    assert p["commercials"] is None and p["package"] is None and p["permissions"] == {"can_edit": False, "can_change_owner": False, "can_invoice": False}
    assert (await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body())).status_code == 403
    assert (await client.patch(f"{PLACEMENTS}/{placement_id}", json={"candidate_confirmation": None})).status_code == 403
    await login(client, await make_user(db_session, "it_student", "it"))
    assert (await client.get(f"{PLACEMENTS}/{placement_id}")).status_code == 403


# --- the list --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_list_views_and_counts(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    pending = (await client.get(PLACEMENTS, params={"view": "pending", "limit": 100})).json()
    assert placement_id in {i["id"] for i in pending["items"]} and pending["counts"]["pending"] >= 1
    await _join(client, s)
    drafts = (await client.get(PLACEMENTS, params={"view": "invoice_drafts", "limit": 100})).json()
    item = next(i for i in drafts["items"] if i["id"] == placement_id)
    assert (item["status"], item["invoice_status"], item["candidate"]["id"]) == ("joined", "draft", str(s["candidate"].id))
    assert (await client.get(PLACEMENTS, params={"view": "nope"})).status_code == 422


# --- AC4: the due and overdue notices are sent once (P12/P13) ----------------------------------------------------------------------
@pytest.mark.asyncio
async def test_due_and_overdue_notices_are_sent_once(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    row = await db_session.scalar(select(Placement).where(Placement.id == placement_id))
    row.draft_due_date = TODAY - timedelta(days=1)
    await db_session.commit()
    for _ in range(2):
        await svc.run_invoice_notices()

    async def sent(event):
        rows = await db_session.scalars(select(Notification.user_id).where(Notification.event_type == event, Notification.entity_id == placement_id))
        return sorted(str(u) for u in rows)

    expected = sorted({str(s["recruiter"].id), str(s["manager"].id)})
    assert await sent("it.recruitment.invoice_due") == expected
    assert await sent("it.recruitment.invoice_overdue") == expected
    note = await db_session.scalar(select(Notification).where(Notification.event_type == "it.recruitment.invoice_due", Notification.entity_id == placement_id).limit(1))
    assert note.action_url == f"/recruiter/placements/{placement_id}" and "50000" not in note.body


@pytest.mark.asyncio
async def test_an_issued_invoice_re_arms_and_a_paid_one_sends_nothing(client, db_session):
    s = await _world(client, db_session)
    placement_id = (await _accept(client, s))["placement_id"]
    await _join(client, s)
    issued = await client.post(f"{PLACEMENTS}/{placement_id}/invoice-draft/issue", json=_issue_body(due_date=TODAY.isoformat()))
    invoice_id = issued.json()["placement"]["commercials"]["invoice"]["invoice"]["id"]
    paid = await client.post(f"/api/v1/recruiter/invoices/{invoice_id}/payments", json={"received_on": TODAY.isoformat(), "amount": "50000.00"})
    assert paid.status_code == 201, paid.text
    await svc.run_invoice_notices()
    count = await db_session.scalar(select(func.count()).select_from(Notification).where(Notification.entity_id == placement_id, Notification.event_type.like("it.recruitment.invoice_%")))
    assert count == 0


def test_the_worker_task_imports_in_a_fresh_interpreter():
    """The worker enters main's telecaller import cycle only at the end that resolves (the pob-008 rule)."""
    import subprocess
    import sys

    code = "import app.worker; import app.services.telecaller_alerts; from app.services.placements import run_invoice_notices"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd="/app")
    assert result.returncode == 0, result.stderr[-2000:]
