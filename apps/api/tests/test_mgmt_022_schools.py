"""mgmt-022 -- GET /management/schools (the §18 school dashboard), PATCH /management/schools/{id} (contract / renewal value) and the
ledger's school tag (spec SD1-SD16).

The test database is shared and never truncated, so the per-school figures are checked on schools made by the test itself and the
company totals only against the ENH-016 / mgmt-020 endpoints they must equal (SD3-SD8) and the rows they must add up to (SD15)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.api.portfolio import portfolio_completion
from app.models import AuditLog, SchoolAcademicResult, SchoolParentLink
from app.services.ledger import today as ist_today
from tests.bdm001_helpers import login, make_user
from tests.bdm016_helpers import career, psychometric
from tests.enh016_helpers import make_school, make_student

pytestmark = pytest.mark.asyncio

URL = "/api/v1/management/schools"
LEDGER = "/api/v1/management/ledger"
PERIOD = {"from": "2024-06-01", "to": "2024-06-30"}
IN_PERIOD = "2024-06-12"
FIGURE_KEYS = [
    "schools_contacted", "meetings", "proposals", "mous", "active_schools", "students", "teachers", "parents", "career_guidance",
    "psychometric_tests", "academic_results", "profile_completion", "revenue",
]  # fmt: skip
STUDENT_COUNTS = ["students", "career_guidance", "psychometric_tests", "academic_results"]
MONEY = ["revenue", "contract_value", "renewal_value"]


async def as_role(client, db, role: str):
    client.cookies.clear()
    user = await make_user(db, role, "global")
    await login(client, user)
    return user


async def read(client, **params) -> dict:
    response = await client.get(URL, params={**PERIOD, **params})
    assert response.status_code == 200, response.text
    return response.json()


def row(body: dict, school) -> dict:
    return next(r for r in body["schools"] if r["id"] == str(school.id))


async def built_school(db, **fields) -> dict:
    """One school worked out by hand: 3 students, 1 teacher, 2 parents (one by link only), 1 guidance, 1 psychometric, 1 result."""
    ctx = await make_school(db, tier="gold", tier_valid_until=date.today() + timedelta(days=365), **fields)
    complete = await make_student(db, ctx, grade_or_class="Grade 9", date_of_birth=date(2010, 1, 1))
    second = await make_student(db, ctx)
    await make_student(db, ctx)
    await db.commit()
    await career(db, complete.id, ctx["career_counselor"].id)
    await career(db, second.id, ctx["career_counselor"].id, status="scheduled")  # not delivered yet (ENH-026 C5)
    await psychometric(db, complete.id, ctx["psychometric_team"].id)
    db.add(SchoolAcademicResult(school_student_id=complete.id, academic_year="2024-25", term="Term 1", subject="Maths", max_marks=100, marks_obtained=80,
                                status="published", uploaded_by_user_id=ctx["school_teacher"].id))  # fmt: skip
    linked_parent = await make_user(db, "school_parent", "overseas")  # no profile.school_id: a member through the link (ENH-008)
    db.add(SchoolParentLink(parent_user_id=linked_parent.id, school_student_id=second.id, linked_by_user_id=ctx["school_coordinator"].id))
    await db.commit()
    ctx["students"] = (complete, second)
    return ctx


# --- access (SD1) -------------------------------------------------------------------------------------------------------------
async def test_every_management_role_reads_and_others_are_refused(client, db_session):
    for role in ("partner", "accountant", "super_admin"):
        await as_role(client, db_session, role)
        assert (await client.get(URL)).status_code == 200, role
    for role in ("overseas_admin", "bdm_manager", "student"):
        await as_role(client, db_session, role)
        response = await client.get(URL)
        assert response.status_code == 403, role
        assert response.json()["detail"] == "Management access required"
    client.cookies.clear()
    assert (await client.get(URL)).status_code == 401


async def test_super_admin_gets_no_money(client, db_session):
    ctx = await built_school(db_session, contract_value=Decimal("250000"), renewal_value=Decimal("300000"))
    await as_role(client, db_session, "super_admin")
    body = await read(client)
    assert body["money_visible"] is False
    assert body["totals"]["revenue"] is None and body["untagged_revenue"] is None
    assert all(body["totals"][key] is None for key in MONEY)
    assert all(row(body, ctx["school"])[key] is None for key in MONEY)


async def test_bad_period_is_422(client, db_session):
    await as_role(client, db_session, "partner")
    assert (await client.get(URL, params={"from": "2024-06-30", "to": "2024-06-01"})).status_code == 422


# --- figures (SD3-SD10, SD15) -------------------------------------------------------------------------------------------------
async def test_figures_in_section_18_order_with_basis(client, db_session):
    await as_role(client, db_session, "partner")
    body = await read(client)
    assert [f["key"] for f in body["figures"]] == FIGURE_KEYS
    assert {f["key"]: f["basis"] for f in body["figures"]}["schools_contacted"] == "period"
    assert {f["key"]: f["basis"] for f in body["figures"]}["active_schools"] == "now"
    assert body["from"] == PERIOD["from"] and body["to"] == PERIOD["to"]


async def test_bdm_figures_equal_the_school_bdm_dashboard(client, db_session):
    await as_role(client, db_session, "partner")
    body = await read(client)
    bdm = (await client.get("/api/v1/management/bdm", params={"type": "school", **PERIOD})).json()
    by_key = {f["key"]: f["value"] for f in bdm["figures"]}
    totals = body["totals"]
    assert (totals["schools_contacted"], totals["meetings"], totals["proposals"], totals["mous"]) == (
        by_key["school_leads"], by_key["meetings"], by_key["proposals"], by_key["mous"])  # fmt: skip


async def test_school_figures_equal_the_enh016_summary(client, db_session):
    await built_school(db_session)
    await as_role(client, db_session, "super_admin")
    summary = (await client.get("/api/v1/overseas-admin/analytics/summary")).json()
    totals = (await read(client))["totals"]
    assert totals["active_schools"] == summary["schools"]["active"]
    assert totals["students"] == summary["students"]["total"]
    assert totals["career_guidance"] == summary["students"]["career_guidance"]
    assert totals["psychometric_tests"] == summary["students"]["psychometric"]


async def test_a_school_row_is_worked_out_by_hand(client, db_session):
    ctx = await built_school(db_session)
    await as_role(client, db_session, "partner")
    r = row(await read(client), ctx["school"])
    assert r["name"] == ctx["school"].name and r["tier"] == "gold" and r["active"] is True and r["renewal_due"] is False
    assert (r["students"], r["teachers"], r["parents"]) == (3, 1, 2)
    assert (r["career_guidance"], r["psychometric_tests"], r["academic_results"]) == (1, 1, 1)
    sections_none = {"sections": set(), "has_statement": False, "has_language": False}
    first = portfolio_completion(profile_complete=True, has_academic=True, has_psychometric=True, has_career=True, **sections_none)
    second = portfolio_completion(profile_complete=False, has_academic=False, has_psychometric=False, has_career=True, **sections_none)
    third = portfolio_completion(profile_complete=False, has_academic=False, has_psychometric=False, has_career=False, **sections_none)
    assert r["profile_completion"] == round((first + second + third) / 3)


async def test_a_school_without_students_or_tier(client, db_session):
    ctx = await make_school(db_session, tier=None)
    await db_session.commit()
    await as_role(client, db_session, "partner")
    r = row(await read(client), ctx["school"])
    assert r["students"] == 0 and r["profile_completion"] is None and r["active"] is False
    assert r["contract_value"] is None and r["renewal_value"] is None  # "Not entered"


async def test_student_totals_are_the_sum_of_the_rows(client, db_session):
    await built_school(db_session)
    await as_role(client, db_session, "partner")
    body = await read(client)
    for key in [*STUDENT_COUNTS, "teachers"]:
        assert body["totals"][key] == sum(r[key] for r in body["schools"]), key
    assert body["totals"]["parents"] <= sum(r["parents"] for r in body["schools"])  # SD6: a parent is counted once
    names = [(r["name"].casefold(), r["id"]) for r in body["schools"]]
    assert names == sorted(names)


# --- money (SD11-SD13) ---------------------------------------------------------------------------------------------------------
async def school_income(client, db, school, amount: str, entry_date: str, *, approve: bool = True) -> dict:
    """An accountant's School projects income tagged with `school`, approved by a partner. The client ends signed in as the partner."""
    await as_role(client, db, "accountant")
    cat = (await client.post(f"{LEDGER}/categories", json={"kind": "income", "name": f"School fee {uuid.uuid4().hex[:8]}"})).json()
    body = {"entry_date": entry_date, "kind": "income", "category_id": cat["id"], "amount": amount, "description": "School programme fee",
            "vertical": "school", "school_id": str(school.id) if school else None}  # fmt: skip
    created = await client.post(LEDGER, json=body)
    assert created.status_code == 201, created.text
    entry = created.json()
    assert (await client.post(f"{LEDGER}/{entry['id']}/submit")).status_code == 200
    await as_role(client, db, "partner")
    if approve:
        assert (await client.post(f"{LEDGER}/{entry['id']}/approve")).status_code == 200
    return entry


async def test_school_wise_revenue_reconciles_with_the_ledger(client, db_session):
    ctx = await built_school(db_session)
    await school_income(client, db_session, ctx["school"], "40000.00", IN_PERIOD)
    await school_income(client, db_session, ctx["school"], "5000.00", IN_PERIOD, approve=False)  # submitted only: not counted
    await school_income(client, db_session, ctx["school"], "7000.00", "2024-07-01")  # after the period
    await school_income(client, db_session, None, "1500.00", IN_PERIOD)  # School projects income with no school
    body = await read(client)
    assert body["money_visible"] is True
    assert row(body, ctx["school"])["revenue"] == "40000.00"
    tagged = sum(Decimal(r["revenue"]) for r in body["schools"])
    assert Decimal(body["untagged_revenue"]) >= Decimal("1500.00")
    assert tagged + Decimal(body["untagged_revenue"]) == Decimal(body["totals"]["revenue"])


async def test_an_approved_reversal_takes_the_revenue_back(client, db_session):
    ctx = await built_school(db_session)
    today = ist_today().isoformat()  # a reversal is dated today (ML11)
    entry = await school_income(client, db_session, ctx["school"], "9000.00", today)
    await as_role(client, db_session, "accountant")
    reversal = await client.post(f"{LEDGER}/{entry['id']}/reverse", json={"reason": "Invoice cancelled"})
    assert reversal.status_code == 201, reversal.text
    assert reversal.json()["school"]["id"] == str(ctx["school"].id)  # SD14: the reversal keeps the tag
    await as_role(client, db_session, "partner")
    assert (await client.post(f"{LEDGER}/{reversal.json()['id']}/approve")).status_code == 200
    body = (await client.get(URL, params={"from": today, "to": today})).json()
    assert row(body, ctx["school"])["revenue"] == "0.00"


async def test_finance_tier_sets_contract_and_renewal_value(client, db_session):
    ctx = await built_school(db_session)
    user = await as_role(client, db_session, "accountant")
    response = await client.patch(f"{URL}/{ctx['school'].id}", json={"contract_value": "250000", "renewal_value": "275000.50"})
    assert response.status_code == 200, response.text
    assert response.json() == {"id": str(ctx["school"].id), "contract_value": "250000.00", "renewal_value": "275000.50"}
    body = await read(client)
    r = row(body, ctx["school"])
    assert (r["contract_value"], r["renewal_value"]) == ("250000.00", "275000.50")
    assert Decimal(body["totals"]["contract_value"]) == sum(Decimal(s["contract_value"]) for s in body["schools"] if s["contract_value"] is not None)
    assert body["totals"]["contracts_not_entered"] == sum(1 for s in body["schools"] if s["contract_value"] is None)
    cleared = await client.patch(f"{URL}/{ctx['school'].id}", json={"renewal_value": None})
    assert cleared.json()["renewal_value"] is None and cleared.json()["contract_value"] == "250000.00"
    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_type == "mgmt.school_value", AuditLog.entity_id == str(ctx["school"].id)).order_by(AuditLog.created_at))).all()
    assert [a.user_id for a in audit] == [user.id, user.id]
    assert audit[0].metadata_json["values"]["contract_value"] == {"before": None, "after": "250000.00"}
    assert audit[1].metadata_json["fields"] == ["renewal_value"]


async def test_values_are_validated_and_refused_outside_finance(client, db_session):
    ctx = await built_school(db_session)
    path = f"{URL}/{ctx['school'].id}"
    await as_role(client, db_session, "partner")
    for bad in ({"contract_value": "-1"}, {"contract_value": "10.555"}, {"contract_value": "abc"}, {"other": "1"}, {"renewal_value": "1e20"}):
        assert (await client.patch(path, json=bad)).status_code == 422, bad
    assert (await client.patch(f"{URL}/{uuid.uuid4()}", json={"contract_value": "1"})).status_code == 404
    unchanged = await client.patch(path, json={})
    assert unchanged.status_code == 200 and unchanged.json()["contract_value"] is None
    await as_role(client, db_session, "super_admin")
    refused = await client.patch(path, json={"contract_value": "1"})
    assert refused.status_code == 403 and refused.json()["detail"] == "Finance access required"
    await as_role(client, db_session, "overseas_admin")
    assert (await client.patch(path, json={"contract_value": "1"})).status_code == 403


# --- the ledger's school tag (SD14) --------------------------------------------------------------------------------------------
async def test_school_tag_only_on_school_projects_income(client, db_session):
    ctx = await built_school(db_session)
    await as_role(client, db_session, "accountant")
    income = (await client.post(f"{LEDGER}/categories", json={"kind": "income", "name": f"Inc {uuid.uuid4().hex[:8]}"})).json()
    expense = (await client.post(f"{LEDGER}/categories", json={"kind": "expense", "nature": "variable", "name": f"Exp {uuid.uuid4().hex[:8]}"})).json()
    base = {"entry_date": IN_PERIOD, "amount": "100.00", "description": "Tagged", "school_id": str(ctx["school"].id)}
    cases = [
        {**base, "kind": "expense", "category_id": expense["id"], "vertical": "school"},
        {**base, "kind": "income", "category_id": income["id"], "vertical": "it"},
        {**base, "kind": "income", "category_id": income["id"], "vertical": "school", "school_id": str(uuid.uuid4())},
    ]
    for body in cases:
        response = await client.post(LEDGER, json=body)
        assert response.status_code == 422, body
        assert response.json()["detail"][0]["loc"] == ["body", "school_id"]
    ok = await client.post(LEDGER, json={**base, "kind": "income", "category_id": income["id"], "vertical": "school"})
    assert ok.status_code == 201 and ok.json()["school"] == {"id": str(ctx["school"].id), "name": ctx["school"].name}
    moved = await client.patch(f"{LEDGER}/{ok.json()['id']}", json={"vertical": "other"})
    assert moved.status_code == 422 and moved.json()["detail"][0]["loc"] == ["body", "school_id"]
    both = await client.patch(f"{LEDGER}/{ok.json()['id']}", json={"vertical": "other", "school_id": None})
    assert both.status_code == 200 and both.json()["school"] is None


async def test_ledger_options_list_the_schools(client, db_session):
    ctx = await built_school(db_session)
    await as_role(client, db_session, "accountant")
    options = (await client.get(f"{LEDGER}/options")).json()
    assert {"id": str(ctx["school"].id), "name": ctx["school"].name} in options["schools"]
