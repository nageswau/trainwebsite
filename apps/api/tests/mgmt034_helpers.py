"""mgmt-034 test builders: one fixture "world" for the management permission matrix and the confidentiality sweep (spec
docs/superpowers/specs/2026-10-14-mgmt-034-confidentiality-sweep-design.md, CS4/CS6/CS7). Users are inserted directly and signed in with a
minted session cookie (no bcrypt round); every management record is made through its real route as the partner or the accountant, so each
is valid. Every value is unique per call: the test database is shared and never emptied."""

import random
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.models import (
    Department,
    Investment,
    LedgerCategory,
    LedgerEntry,
    PartnerCapitalEntry,
    SalaryMonthTotal,
    School,
    UniversityCommissionReceipt,
    User,
)
from tests.bdm005_helpers import PDF_BYTES
from tests.tel026_helpers import headers
from tests.test_mgmt_006_abroad_revenue import linked_application

__all__ = ["MANAGEMENT", "PDF_BYTES", "ROLES", "headers", "plant_finance", "plant_partner_only", "today", "world"]

API = "/api/v1"
IST = ZoneInfo("Asia/Kolkata")
# CS4: who calls. `owner` is the staff member named on the world's task, decision and meeting (M14); `partner2` is a partner who did not
# create the world's records (ML approval: a partner never approves their own entry).
ACCOUNTS = {
    "partner": ("partner", "global"),
    "partner2": ("partner", "global"),
    "accountant": ("accountant", "global"),
    "super": ("super_admin", "global"),
    "it_admin": ("it_admin", "it"),
    "ovs_admin": ("overseas_admin", "overseas"),
    "bdm_manager": ("bdm_manager", "global"),
    "tel_manager": ("telecaller_manager", "global"),
    "p_head": ("partnership_head", "global"),
    "counselor": ("counselor", "overseas"),
    "trainer": ("trainer", "it"),
    "owner": ("telecaller", "it"),
    "student": ("student", "it"),
    "agent": ("agent", "overseas"),
}
ROLES = (*ACCOUNTS, "anon")
MANAGEMENT = ("partner", "accountant", "super")  # the three tiers the delta sweep compares (CS7)


def today() -> date:
    return datetime.now(IST).date()


def _u(label: str = "") -> str:
    return f"{label}{uuid.uuid4().hex[:8]}"


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


async def _add(db, row):
    db.add(row)
    await db.flush()
    return row


async def _user(db, key: str) -> User:
    role, division = ACCOUNTS[key]
    return await _add(db, User(email=f"{_u('m34-')}@example.local", password_hash="!", full_name=f"M34 {key} {_u()}", role=role, division=division,
                               active=True, email_verified=True))  # fmt: skip


async def _ok(response, status: int = 201) -> dict:
    assert response.status_code == status, f"world setup: {response.request.method} {response.request.url} {response.status_code} {response.text[:300]}"
    return response.json()


def _soon(hours: int) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).replace(second=0, microsecond=0).isoformat()


async def world(client, db) -> dict:
    """The users of every CS4 role and one of each management record the routes take an id of."""
    users = {key: await _user(db, key) for key in ACCOUNTS}
    await db.commit()
    p, a = headers(users["partner"]), headers(users["accountant"])
    w: dict = {"users": users, "today": today().isoformat(), "month": month_key(today()), "owner_id": str(users["owner"].id)}
    w["partner_id"], w["partner2_id"] = str(users["partner"].id), str(users["partner2"].id)

    # mgmt-004 ledger: a category, a draft, a submitted, an approved entry, all by the accountant (so either partner may approve)
    category = await _ok(await client.post(f"{API}/management/ledger/categories", headers=a, json={"kind": "expense", "nature": "variable", "name": f"M34 {_u()}"}))
    w["category"] = category["id"]

    async def entry(*, submit: bool = False, approve: bool = False) -> str:
        body = {"entry_date": w["today"], "kind": "expense", "category_id": category["id"], "amount": "1200.00", "description": "M34 entry", "vertical": "shared"}
        made = await _ok(await client.post(f"{API}/management/ledger", headers=a, json=body))
        if submit or approve:
            await _ok(await client.post(f"{API}/management/ledger/{made['id']}/submit", headers=a), 200)
        if approve:
            await _ok(await client.post(f"{API}/management/ledger/{made['id']}/approve", headers=p), 200)
        return made["id"]

    w["draft"] = await entry()
    await _ok(await client.put(f"{API}/management/ledger/{w['draft']}/receipt", headers=a, files={"file": ("r.pdf", PDF_BYTES, "application/pdf")}), 200)
    w["submitted"] = await entry(submit=True)
    w["approved"] = await entry(approve=True)

    # mgmt-014 investment, mgmt-011 department, mgmt-022 school
    investment = {"invested_on": w["today"], "investor_kind": "company", "amount": "50000", "purpose": f"M34 {_u()}", "vertical": "it"}
    w["investment"] = (await _ok(await client.post(f"{API}/management/investments", headers=p, json=investment)))["id"]
    w["department"] = (await _ok(await client.post(f"{API}/management/departments", headers=a, json={"name": f"M34 Dept {_u()}"})))["id"]
    school = await _add(db, School(name=f"M34 School {_u()}", created_by_user_id=users["super"].id))
    w["school"] = str(school.id)
    await db.commit()

    # mgmt-027 discussion (owner responsible, one shareable attachment), mgmt-028 task (owner), mgmt-029 meeting (owner invited)
    discussion = {"topic": f"M34 topic {_u()}", "discussion_date": w["today"], "decision": "Open a Kochi office", "responsible_user_id": w["owner_id"],
                  "deadline": (today() + timedelta(days=30)).isoformat()}  # fmt: skip
    w["discussion"] = (await _ok(await client.post(f"{API}/management/discussions", headers=p, json=discussion)))["id"]
    attachment = await client.post(f"{API}/management/discussions/{w['discussion']}/attachments", headers=p,
                                   files={"file": ("terms.pdf", PDF_BYTES, "application/pdf")}, data={"shareable": "true"})  # fmt: skip
    w["attachment"] = (await _ok(attachment))["attachments"][0]["id"]
    task = {"title": f"M34 task {_u()}", "owner_user_id": w["owner_id"], "deadline": (today() + timedelta(days=7)).isoformat()}
    w["task"] = (await _ok(await client.post(f"{API}/management/tasks", headers=p, json=task)))["id"]
    meeting = {"title": f"M34 meeting {_u()}", "kind": "partner", "starts_at": _soon(-2), "mode": "Online", "meeting_url": "https://meet.example.com/m34",
               "participant_ids": [w["owner_id"]]}  # fmt: skip
    w["meeting"] = (await _ok(await client.post(f"{API}/management/meetings", headers=p, json=meeting)))["id"]
    await _ok(await client.post(f"{API}/management/meetings/{w['meeting']}/minutes", headers=p, json={"minutes": "M34 minutes"}), 200)

    # mgmt-026 plan: the next month inside the window, cleared first (one plan per month), with one free-text item
    from tests.test_mgmt_026_plans import add_months, clear

    plan_month, free_month = (add_months(today().replace(day=1), ahead) for ahead in random.sample(range(1, 13), 2))
    await clear(db, [plan_month, free_month])
    w["plan_month"] = month_key(plan_month)
    await _ok(await client.post(f"{API}/management/plans", headers=p, json={"month": w["plan_month"]}))
    w["item"] = (await _ok(await client.post(f"{API}/management/plans/{w['plan_month']}/items", headers=p, json={"vertical": "abroad", "text": "M34 item"})))["id"]
    w["free_month"] = month_key(free_month)

    # mgmt-032 review: a draft for a random finished month far in the past, its three Problems answered (so it can be finalised)
    while True:  # a month no earlier run has a review for (generate answers 200 for an existing draft, 409 for a final one)
        w["review_month"] = f"{random.randint(1000, 1999):04d}-{random.randint(1, 12):02d}"
        if (await client.post(f"{API}/management/reviews/{w['review_month']}/generate", headers=p)).status_code == 201:
            break
    problems = {"went_wrong": "Nothing", "delayed": "Nothing", "intervention": "None needed"}
    await _ok(await client.patch(f"{API}/management/reviews/{w['review_month']}", headers=p, json=problems), 200)
    # the university a CS7 commission receipt is planted on: made here, before any snapshot, so its application changes no later read
    w["university"] = (await linked_application(db))[0].university_id
    return w


# --- CS7 plants: written directly, today, without an audit row -------------------------------------------------------------------
async def plant_partner_only(db, w: dict) -> None:
    """Partner-only data (M2/M3/M13): an investment, a capital entry and a university commission receipt in rupees."""
    partner = w["users"]["partner"]
    db.add(Investment(code=f"M34{_u()}"[:20], invested_on=today(), investor_kind="company", amount=Decimal("777000.00"), purpose="M34 plant", vertical="abroad",
                      created_by_user_id=partner.id, updated_by_user_id=partner.id))  # fmt: skip
    db.add(PartnerCapitalEntry(partner_user_id=partner.id, entry_date=today(), kind="additional", amount=Decimal("333000.00"), created_by_user_id=partner.id))
    db.add(UniversityCommissionReceipt(university_id=w["university"], amount=Decimal("88000.00"), currency="INR", received_on=today(),
                                       reference=f"M34-{_u()}", created_by_user_id=partner.id))  # fmt: skip
    await db.commit()


async def plant_finance(db, w: dict) -> None:
    """Finance data (M13): an approved manual income line and a department salary month."""
    accountant, partner = w["users"]["accountant"], w["users"]["partner"]
    category = await _add(db, LedgerCategory(kind="income", name=f"M34 income {_u()}", created_by_user_id=accountant.id, updated_by_user_id=accountant.id))
    db.add(LedgerEntry(entry_date=today(), kind="income", category_id=category.id, amount=Decimal("555000.00"), description="M34 plant", vertical="it",
                       status="approved", created_by_user_id=accountant.id, updated_by_user_id=partner.id))  # fmt: skip
    department = await _add(db, Department(name=f"M34 plant {_u()}", created_by_user_id=accountant.id, updated_by_user_id=accountant.id))
    db.add(SalaryMonthTotal(month=today().replace(day=1), department_id=department.id, headcount=3, payable=Decimal("90000"), paid=Decimal("90000"),
                            incentives=Decimal("0"), commissions=Decimal("0"), employer_cost=Decimal("0"),
                            created_by_user_id=accountant.id, updated_by_user_id=accountant.id))  # fmt: skip
    await db.commit()


