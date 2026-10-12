"""mgmt-004 -- the management ledger: categories, manual income/expense, approval, reversal, receipts (spec ML1-ML16; AC1-AC3)."""

import datetime
import uuid
from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Batch, LedgerCategory, LedgerEntry, LedgerEntryEvent, Program
from app.services import management_audit
from app.services.storage import storage
from tests.bdm001_helpers import login, make_user
from tests.bdm005_helpers import PDF_BYTES

LEDGER = "/api/v1/management/ledger"
CATEGORIES = f"{LEDGER}/categories"
TODAY = datetime.datetime.now(ZoneInfo("Asia/Kolkata")).date()


async def as_user(client, db, role: str = "accountant"):
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def category(client, kind: str = "expense", nature: str | None = "fixed", name: str | None = None) -> dict:
    body = {"kind": kind, "name": name or f"Cat {uuid.uuid4().hex[:8]}", **({"nature": nature} if kind == "expense" else {})}
    response = await client.post(CATEGORIES, json=body)
    assert response.status_code == 201, response.text
    return response.json()


def entry_body(category_id: str, **overrides) -> dict:
    return {"entry_date": TODAY.isoformat(), "kind": "expense", "category_id": category_id, "amount": "120000.00", "description": "Office rent for October", "vertical": "shared", **overrides}


async def create(client, category_id: str, **overrides) -> dict:
    response = await client.post(LEDGER, json=entry_body(category_id, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


async def post(client, entry_id: str, action: str, **body):
    return await client.post(f"{LEDGER}/{entry_id}/{action}", json=body or None)


async def totals(client, **params) -> dict:
    response = await client.get(LEDGER, params=params)
    assert response.status_code == 200, response.text
    return response.json()["totals"]


async def submitted_by_accountant(client, db, **overrides) -> tuple[dict, dict]:
    """An accountant's submitted expense in a fresh category; returns (entry, category). The client is left signed in as the accountant."""
    await as_user(client, db)
    cat = await category(client)
    entry = await create(client, cat["id"], **overrides)
    assert (await post(client, entry["id"], "submit")).status_code == 200
    return entry, cat


# --- migration seed (ML1) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_seeded_categories_cover_section_8_and_22(db_session):
    rows = (await db_session.execute(select(LedgerCategory.kind, LedgerCategory.nature, LedgerCategory.name).where(LedgerCategory.created_by_user_id.is_(None)))).all()
    names = {(k, n, name) for k, n, name in rows}
    assert {
        ("expense", "fixed", "Office rent"),
        ("expense", "fixed", "Other fixed costs"),
        ("expense", "variable", "Agent commissions"),
        ("expense", "variable", "Student activities"),
        ("income", None, "Abroad education"),
        ("income", None, "School projects"),
    } <= names
    assert sum(1 for k, n, _ in names if k == "expense" and n == "fixed") == 8
    assert sum(1 for k, n, _ in names if k == "expense" and n == "variable") == 9
    assert sum(1 for k, _, _ in names if k == "income") == 5


def test_audit_catalogue_has_ledger_kinds_and_verbs():
    assert management_audit.KINDS["mgmt.ledger_category"][1] == "finance"
    assert {"submit", "reject", "reverse", "download"} <= management_audit.VERBS


# --- AC1 / AC2 ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_accountant_records_rent_partner_approves_it_counts(client, db_session):
    entry, cat = await submitted_by_accountant(client, db_session)
    assert (await totals(client, category=cat["id"]))["expense"] == "0.00"  # submitted: not yet counted
    partner = await as_user(client, db_session, "partner")
    response = await post(client, entry["id"], "approve")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "approved" and body["decided_by"]["id"] == str(partner.id)
    assert await totals(client, category=cat["id"]) == {"income": "0.00", "expense": "120000.00", "net": "-120000.00"}
    month = TODAY.strftime("%Y-%m")
    page = (await client.get(LEDGER, params={"month": month, "category": cat["id"]})).json()
    assert [i["id"] for i in page["items"]] == [entry["id"]] and page["totals"]["expense"] == "120000.00"
    audit = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == entry["id"]).order_by(AuditLog.created_at))).all()
    assert audit == ["mgmt.ledger.create", "mgmt.ledger.submit", "mgmt.ledger.approve"]


@pytest.mark.asyncio
async def test_ac2_unapproved_entries_are_excluded(client, db_session):
    await as_user(client, db_session)
    cat = await category(client)
    await create(client, cat["id"], amount="10.00")  # draft
    submitted = await create(client, cat["id"], amount="20.00")
    await post(client, submitted["id"], "submit")
    rejected = await create(client, cat["id"], amount="40.00")
    await post(client, rejected["id"], "submit")
    await as_user(client, db_session, "partner")
    assert (await post(client, rejected["id"], "reject", reason="No receipt")).status_code == 200
    assert (await totals(client, category=cat["id"]))["expense"] == "0.00"
    assert (await client.get(LEDGER, params={"category": cat["id"]})).json()["total"] == 3


# --- AC3 + tiers (ML16) -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("super_admin", "global"), ("it_admin", "it"), ("student", "it")])
async def test_ac3_non_finance_roles_are_refused_everywhere(client, db_session, role, division):
    await as_user(client, db_session)
    cat = await category(client)
    entry = await create(client, cat["id"])
    user = await make_user(db_session, role, division)
    await login(client, user)
    some = str(uuid.uuid4())
    calls = [
        ("GET", LEDGER, None),
        ("POST", LEDGER, entry_body(cat["id"])),
        ("GET", f"{LEDGER}/{entry['id']}", None),
        ("PATCH", f"{LEDGER}/{entry['id']}", {"amount": "1.00"}),
        ("POST", f"{LEDGER}/{entry['id']}/submit", None),
        ("POST", f"{LEDGER}/{entry['id']}/approve", None),
        ("POST", f"{LEDGER}/{entry['id']}/reject", {"reason": "no"}),
        ("POST", f"{LEDGER}/{entry['id']}/reverse", {"reason": "no"}),
        ("GET", f"{LEDGER}/{entry['id']}/receipt", None),
        ("GET", f"{LEDGER}/options", None),
        ("GET", CATEGORIES, None),
        ("POST", CATEGORIES, {"kind": "income", "name": "Consulting"}),
        ("PATCH", f"{CATEGORIES}/{some}", {"active": False}),
    ]
    for method, url, body in calls:
        response = await client.request(method, url, json=body)
        assert response.status_code == 403, (method, url, response.status_code)
    upload = await client.put(f"{LEDGER}/{entry['id']}/receipt", files={"file": ("r.pdf", PDF_BYTES, "application/pdf")})
    assert upload.status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    assert (await client.get(LEDGER)).status_code == 401


# --- validation (ML4-ML6) -----------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("amount", "-5.00"),
        ("amount", "0"),
        ("amount", "1.234"),
        ("amount", "1000000000000.00"),
        ("description", " x "),
        ("vertical", "branch"),
        ("kind", "transfer"),
        ("channel", "tv"),
        ("entry_date", (TODAY + timedelta(days=1)).isoformat()),
        ("entry_date", "1999-12-31"),
    ],
)
async def test_invalid_fields_are_422_on_the_field(client, db_session, field, value):
    await as_user(client, db_session)
    cat = await category(client)
    response = await client.post(LEDGER, json=entry_body(cat["id"], **{field: value}))
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"][-1] == field


@pytest.mark.asyncio
async def test_category_must_exist_match_kind_and_be_active(client, db_session):
    await as_user(client, db_session)
    income = await category(client, "income")
    assert (await client.post(LEDGER, json=entry_body(income["id"]))).status_code == 422  # expense entry, income category
    assert (await client.post(LEDGER, json=entry_body(str(uuid.uuid4())))).status_code == 422
    expense = await category(client)
    used = await create(client, expense["id"])
    assert (await client.patch(f"{CATEGORIES}/{expense['id']}", json={"active": False})).status_code == 200
    response = await client.post(LEDGER, json=entry_body(expense["id"]))
    assert response.status_code == 422 and "no longer in use" in response.text
    # ML3: an entry already on it can still be edited otherwise, and keeps it
    edited = await client.patch(f"{LEDGER}/{used['id']}", json={"description": "Rent, corrected"})
    assert edited.status_code == 200 and edited.json()["category"] == {"id": expense["id"], "name": expense["name"], "active": False}


@pytest.mark.asyncio
async def test_channel_only_on_expenses_and_batch_must_belong_to_program(client, db_session):
    await as_user(client, db_session)
    income = await category(client, "income")
    response = await client.post(LEDGER, json=entry_body(income["id"], kind="income", channel="google"))
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "channel"
    one, other = (await program(db_session)), (await program(db_session))
    expense = await category(client)
    tagged = await create(client, expense["id"], channel="google", program_id=str(one.id), batch_id=str(one.batch_id))
    assert tagged["channel"] == "google" and tagged["program"]["id"] == str(one.id) and tagged["batch"]["id"] == str(one.batch_id)
    mismatch = await client.post(LEDGER, json=entry_body(expense["id"], program_id=str(other.id), batch_id=str(one.batch_id)))
    assert mismatch.status_code == 422 and mismatch.json()["detail"][0]["loc"][-1] == "batch_id"
    alone = await create(client, expense["id"], batch_id=str(other.batch_id))  # a batch alone sets its program
    assert alone["program"]["id"] == str(other.id)


async def program(db):
    row = Program(
        slug=f"m004-{uuid.uuid4().hex[:8]}",
        category="Software Development",
        title=f"M004 {uuid.uuid4().hex[:6]}",
        summary="",
        duration="8 weeks",
        eligibility="",
        fees=1000,
        certification="",
        curriculum=[],
        placement_assistance="",
        trainer_name="T",
        active=True,
    )
    db.add(row)
    await db.flush()
    batch = Batch(program_id=row.id, name=f"B-{uuid.uuid4().hex[:6]}", start_date=TODAY, end_date=TODAY + timedelta(days=60), schedule="Mon-Fri", capacity=20, enrollment_open=True, status="active")
    db.add(batch)
    await db.commit()
    row.batch_id = batch.id  # test convenience only (not a column)
    return row


# --- status machine (ML7-ML9, ML12) -------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_accountant_cannot_approve_and_partner_cannot_decide_own_entry(client, db_session):
    entry, _ = await submitted_by_accountant(client, db_session)
    assert (await post(client, entry["id"], "approve")).status_code == 403
    await as_user(client, db_session, "partner")
    cat = await category(client)
    own = await create(client, cat["id"])
    await post(client, own["id"], "submit")
    response = await post(client, own["id"], "approve")
    assert response.status_code == 403 and "your own" in response.text
    assert (await post(client, own["id"], "reject", reason="x" * 3)).status_code == 403
    detail = (await client.get(f"{LEDGER}/{own['id']}")).json()
    assert detail["can"]["decide"] is False


@pytest.mark.asyncio
async def test_status_machine_conflicts(client, db_session):
    await as_user(client, db_session)
    cat = await category(client)
    entry = await create(client, cat["id"])
    await as_user(client, db_session, "partner")
    assert (await post(client, entry["id"], "approve")).status_code == 409  # still a draft
    assert (await post(client, entry["id"], "reverse", reason="Wrong")).status_code == 409
    assert (await post(client, entry["id"], "submit")).status_code == 200
    assert (await post(client, entry["id"], "submit")).status_code == 409
    assert (await client.patch(f"{LEDGER}/{entry['id']}", json={"amount": "1.00"})).status_code == 409  # submitted is locked
    # the partner created nothing here, so a decision is allowed
    assert (await post(client, entry["id"], "approve")).status_code == 200
    assert (await post(client, entry["id"], "approve")).status_code == 409
    assert (await post(client, entry["id"], "reject", reason="Late")).status_code == 409
    assert (await client.patch(f"{LEDGER}/{entry['id']}", json={"amount": "1.00"})).status_code == 409  # approved is immutable
    assert (await client.put(f"{LEDGER}/{entry['id']}/receipt", files={"file": ("r.pdf", PDF_BYTES, "application/pdf")})).status_code == 409


@pytest.mark.asyncio
async def test_reject_needs_reason_and_editing_rejected_returns_to_draft(client, db_session):
    entry, cat = await submitted_by_accountant(client, db_session)
    await as_user(client, db_session, "partner")
    assert (await post(client, entry["id"], "reject")).status_code == 422
    assert (await post(client, entry["id"], "reject", reason=" ")).status_code == 422
    rejected = (await post(client, entry["id"], "reject", reason="Amount differs from the invoice")).json()
    assert rejected["status"] == "rejected" and rejected["rejection_reason"] == "Amount differs from the invoice"
    await as_user(client, db_session)
    edited = (await client.patch(f"{LEDGER}/{entry['id']}", json={"amount": "118000.00"})).json()
    assert edited["status"] == "draft" and edited["amount"] == "118000.00" and edited["rejection_reason"] is None
    events = [(e["event"], e["from_status"], e["to_status"]) for e in edited["events"]]
    assert events == [("created", None, "draft"), ("submitted", "draft", "submitted"), ("rejected", "submitted", "rejected"), ("updated", "rejected", "draft")]
    assert edited["events"][-1]["fields"] == ["amount"]
    log = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == entry["id"], AuditLog.action == "mgmt.ledger.update"))
    assert log.metadata_json["values"] == {"amount": {"before": "120000.00", "after": "118000.00"}}


@pytest.mark.asyncio
async def test_patch_with_no_change_records_nothing(client, db_session):
    await as_user(client, db_session)
    cat = await category(client)
    entry = await create(client, cat["id"])
    same = (await client.patch(f"{LEDGER}/{entry['id']}", json={"amount": "120000", "description": "Office rent for October"})).json()
    assert [e["event"] for e in same["events"]] == ["created"]


@pytest.mark.asyncio
async def test_unknown_entry_is_404(client, db_session):
    await as_user(client, db_session)
    assert (await client.get(f"{LEDGER}/{uuid.uuid4()}")).status_code == 404
    assert (await post(client, str(uuid.uuid4()), "submit")).status_code == 404


# --- reversal (ML11) ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_reversal_corrects_an_approved_entry(client, db_session):
    entry, cat = await submitted_by_accountant(client, db_session)
    partner = await as_user(client, db_session, "partner")
    await post(client, entry["id"], "approve")
    await as_user(client, db_session)
    assert (await post(client, entry["id"], "reverse")).status_code == 422  # a reason is required
    response = await post(client, entry["id"], "reverse", reason="Duplicate of the September entry")
    assert response.status_code == 201, response.text
    reversal = response.json()
    assert (reversal["status"], reversal["reversal_of_id"], reversal["amount"], reversal["entry_date"]) == ("submitted", entry["id"], "120000.00", TODAY.isoformat())
    assert (await post(client, entry["id"], "reverse", reason="Again")).status_code == 409  # one live reversal
    original = (await client.get(f"{LEDGER}/{entry['id']}")).json()
    assert original["reversed_by_id"] == reversal["id"] and original["can"]["reverse"] is False and original["events"][-1]["event"] == "reversed"
    await login(client, partner)
    assert (await post(client, reversal["id"], "approve")).status_code == 200
    assert (await totals(client, category=cat["id"]))["expense"] == "0.00"  # the reversal nets the entry out
    assert (await post(client, reversal["id"], "reverse", reason="Undo")).status_code == 409  # a reversal is never reversed


@pytest.mark.asyncio
async def test_a_rejected_reversal_frees_the_entry_for_another(client, db_session):
    entry, _ = await submitted_by_accountant(client, db_session)
    await as_user(client, db_session, "partner")
    await post(client, entry["id"], "approve")
    first = (await post(client, entry["id"], "reverse", reason="Wrong month")).json()
    await as_user(client, db_session, "partner")  # the first partner made the reversal, so a second partner decides it
    assert (await post(client, first["id"], "reject", reason="Month is right")).status_code == 200
    assert (await post(client, entry["id"], "reverse", reason="Wrong amount")).status_code == 201


# --- receipt (ML13) -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_receipt_upload_download_and_types(client, db_session):
    await as_user(client, db_session)
    cat = await category(client)
    entry = await create(client, cat["id"])
    url = f"{LEDGER}/{entry['id']}/receipt"
    assert (await client.get(url)).status_code == 404
    assert (await client.put(url, files={"file": ("r.txt", b"hello", "text/plain")})).status_code == 415
    response = await client.put(url, files={"file": ("rent-oct.pdf", PDF_BYTES, "application/pdf")})
    assert response.status_code == 200, response.text
    assert response.json()["receipt"] == {"name": "rent-oct.pdf", "content_type": "application/pdf"}
    row = await db_session.scalar(select(LedgerEntry).where(LedgerEntry.id == uuid.UUID(entry["id"])))
    assert row.receipt_key.startswith("ledger-receipts/") and storage.read_bytes(row.receipt_key) == PDF_BYTES
    download = await client.get(url)
    assert download.status_code == 200 and download.content == PDF_BYTES
    assert download.headers["content-disposition"].startswith('attachment; filename="ledger-receipt-') and download.headers["x-content-type-options"] == "nosniff"
    replaced = await client.put(url, files={"file": ("new.pdf", PDF_BYTES, "application/pdf")})
    assert replaced.status_code == 200
    kinds = (await db_session.scalars(select(LedgerEntryEvent.event).where(LedgerEntryEvent.entry_id == row.id).order_by(LedgerEntryEvent.created_at))).all()
    assert kinds == ["created", "receipt", "receipt"]
    downloads = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == entry["id"], AuditLog.action == "mgmt.ledger.download"))
    assert downloads == 1


# --- list (ML10, ML15) --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_filters_paging_and_income_totals(client, db_session):
    await as_user(client, db_session)
    income = await category(client, "income")
    old = await create(client, income["id"], kind="income", amount="500.00", vertical="it", entry_date=(TODAY.replace(day=1) - timedelta(days=1)).isoformat())
    new = await create(client, income["id"], kind="income", amount="700.00", vertical="abroad")
    for row in (old, new):
        await post(client, row["id"], "submit")
    await as_user(client, db_session, "partner")
    for row in (old, new):
        assert (await post(client, row["id"], "approve")).status_code == 200
    page = (await client.get(LEDGER, params={"category": income["id"]})).json()
    assert [i["id"] for i in page["items"]] == [new["id"], old["id"]]  # newest date first
    assert page["totals"] == {"income": "1200.00", "expense": "0.00", "net": "1200.00"}
    month = (await client.get(LEDGER, params={"category": income["id"], "month": TODAY.strftime("%Y-%m")})).json()
    assert [i["id"] for i in month["items"]] == [new["id"]] and month["totals"]["income"] == "700.00"
    assert [i["id"] for i in (await client.get(LEDGER, params={"category": income["id"], "vertical": "it"})).json()["items"]] == [old["id"]]
    assert (await client.get(LEDGER, params={"category": income["id"], "status": "draft"})).json()["total"] == 0
    paged = (await client.get(LEDGER, params={"category": income["id"], "limit": 1, "offset": 1})).json()
    assert [i["id"] for i in paged["items"]] == [old["id"]] and paged["total"] == 2
    for bad in ({"month": "2026-13"}, {"month": "oct"}, {"limit": 0}, {"offset": 10_001}, {"status": "paid"}):
        assert (await client.get(LEDGER, params=bad)).status_code == 422, bad


# --- categories (ML2) ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_categories_create_rename_deactivate(client, db_session):
    await as_user(client, db_session, "partner")
    name = f"Courier {uuid.uuid4().hex[:6]}"
    created = await category(client, "expense", "variable", name)
    assert (created["kind"], created["nature"], created["name"], created["active"]) == ("expense", "variable", name, True)
    duplicate = await client.post(CATEGORIES, json={"kind": "expense", "nature": "fixed", "name": f"  {name.upper()} "})
    assert duplicate.status_code == 409
    assert (await client.post(CATEGORIES, json={"kind": "income", "name": name})).status_code == 201  # unique per kind only
    assert (await client.post(CATEGORIES, json={"kind": "expense", "name": "No nature"})).status_code == 422
    assert (await client.post(CATEGORIES, json={"kind": "income", "nature": "fixed", "name": "Has nature"})).status_code == 422
    assert (await client.post(CATEGORIES, json={"kind": "expense", "nature": "fixed", "name": "x"})).status_code == 422
    renamed = await client.patch(f"{CATEGORIES}/{created['id']}", json={"name": f"{name} & parcels"})
    assert renamed.status_code == 200 and renamed.json()["name"] == f"{name} & parcels"
    assert (await client.patch(f"{CATEGORIES}/{created['id']}", json={"active": False})).json()["active"] is False
    listed = (await client.get(CATEGORIES)).json()["items"]
    assert any(c["id"] == created["id"] and c["active"] is False for c in listed)
    assert (await client.patch(f"{CATEGORIES}/{uuid.uuid4()}", json={"active": False})).status_code == 404
    actions = (await db_session.scalars(select(AuditLog.action).where(AuditLog.entity_id == created["id"]).order_by(AuditLog.created_at))).all()
    assert actions == ["mgmt.ledger_category.create", "mgmt.ledger_category.update", "mgmt.ledger_category.update"]


@pytest.mark.asyncio
async def test_options_list_active_categories_channels_and_programs(client, db_session):
    await as_user(client, db_session)
    active, inactive = await category(client), await category(client)
    await client.patch(f"{CATEGORIES}/{inactive['id']}", json={"active": False})
    course = await program(db_session)
    body = (await client.get(f"{LEDGER}/options")).json()
    ids = {c["id"] for c in body["categories"]}
    assert active["id"] in ids and inactive["id"] not in ids
    assert "google" in [c["value"] for c in body["channels"]] and [v["value"] for v in body["verticals"]][-1] == "shared"
    listed = next(p for p in body["programs"] if p["id"] == str(course.id))
    assert listed["batches"] == [{"id": str(course.batch_id), "name": (await db_session.get(Batch, course.batch_id)).name}]
