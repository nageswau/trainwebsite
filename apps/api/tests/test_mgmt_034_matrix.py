"""mgmt-034 -- the Management Command Center permission matrix as built (spec docs/superpowers/specs/2026-10-14-mgmt-034-confidentiality-sweep-design.md,
RBAC_MATRIX §2.146). Every route under `/management` and `/me/management-` is called as every CS4 role (mgmt034_helpers.ROLES): two partners,
the accountant, super_admin, the division admins, module managers, staff (one of them the owner / responsible / invitee of the world's
records), a student, an agent and nobody signed in.

A row lists only the cells that are not "refused": every unlisted signed-in role must get 403 and anonymous 401 (CS4), so a role that gains
access fails here (AC2, "extra role"). The expectations are the owner-approved rules of each item (RBAC_MATRIX §2.112-§2.145; CS5).
Refused cells and every GET share one world per row; every other 2xx cell runs on its own fresh world (CS6)."""

import re
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

import pytest
import pytest_asyncio

from app.main import app
from tests.mgmt034_helpers import PDF_BYTES, ROLES, headers, retire_departments, today, world

API = "/api/v1"
OK = {200, 201, 204}
PREFIXES = ("/management", "/me/management-")  # CS3


@pytest_asyncio.fixture(autouse=True)
async def _retire_departments(db_session):
    yield
    await retire_departments(db_session)


@dataclass
class Row:
    method: str
    path: str
    body: object = None  # a dict / callable(world) -> dict, sent as JSON
    form: object = None  # callable(world) -> (data, files), sent as multipart
    cells: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def expected(self, role: str) -> int:
        return self.cells.get(role, 401 if role == "anon" else 403)


def R(method: str, path: str, body=None, *, form=None, **cells) -> Row:
    return Row(method, path, body, form, cells)


def _all(status: int, *roles: str) -> dict:
    return dict.fromkeys(roles, status)


PARTNERS = ("partner", "partner2")  # partner-only (M2/M13): investments, capital, the monthly review
FINANCE = (*PARTNERS, "accountant")  # can_view_finance
OPERATIONAL = (*PARTNERS, "super")  # can_view_operational
MANAGEMENT = (*FINANCE, "super")  # require_management
SIGNED_IN = tuple(r for r in ROLES if r != "anon")  # the own-slice routes answer every signed-in user (M14)
OTHERS = tuple(r for r in SIGNED_IN if r != "owner")


def _day(days: int) -> str:
    return (today() + timedelta(days=days)).isoformat()


def _u() -> str:
    return uuid.uuid4().hex[:8]


def _past_month() -> str:
    """A finished month nobody else uses, for the month-keyed upserts (salaries, balances, budgets) so they never overwrite live data."""
    return f"{1000 + int(_u()[:4], 16) % 999:04d}-{int(_u()[:2], 16) % 12 + 1:02d}"


PAST = _past_month()


def _pdf(_w):
    return {}, {"file": ("r.pdf", PDF_BYTES, "application/pdf")}


def _shareable_pdf(_w):
    return {"shareable": "true"}, {"file": ("t.pdf", PDF_BYTES, "application/pdf")}


MATRIX = [
    # mgmt-001 who am I, mgmt-002 activity, mgmt-003 snapshot
    R("get", "/management/me", **_all(200, *MANAGEMENT)),
    R("get", "/management/activity", **_all(200, *MANAGEMENT)),
    R("get", "/management/snapshot", **_all(200, *OPERATIONAL)),
    # operational dashboards (mgmt-016 … 025, 030, 031)
    R("get", "/management/applications", **_all(200, *OPERATIONAL)),
    R("get", "/management/crm-reports", **_all(200, *OPERATIONAL, "ovs_admin")),  # ccrm-034 R1 (DEC-SCOPE-265)
    R("get", "/management/bdm", **_all(200, *OPERATIONAL)),
    R("get", "/management/counseling", **_all(200, *OPERATIONAL)),
    R("get", "/management/training", **_all(200, *OPERATIONAL)),
    R("get", "/management/telecalling", **_all(200, *OPERATIONAL)),
    R("get", "/management/recruitment", **_all(200, *OPERATIONAL)),
    R("get", "/management/agents", **_all(200, *OPERATIONAL)),
    R("get", "/management/funnel", **_all(200, *OPERATIONAL)),
    R("get", "/management/universities", **_all(200, *OPERATIONAL)),
    R("get", "/management/health", **_all(200, *OPERATIONAL)),
    R("get", "/management/home", **_all(200, *OPERATIONAL)),
    # mixed-tier dashboards: super_admin gets the counts only (mgmt-008 RR, mgmt-012 MK, mgmt-022 SD)
    R("get", "/management/revenue/recruitment", **_all(200, *MANAGEMENT)),
    R("get", "/management/marketing", **_all(200, *MANAGEMENT)),
    R("get", "/management/schools", **_all(200, *MANAGEMENT)),
    # finance dashboards (mgmt-006/007/009/010/013/033)
    R("get", "/management/expenses", **_all(200, *FINANCE)),
    R("get", "/management/revenue/abroad", **_all(200, *FINANCE)),
    R("get", "/management/revenue/it", **_all(200, *FINANCE)),
    R("get", "/management/revenue/it/payments?unlinked=true", **_all(200, *FINANCE)),
    R("get", "/management/pnl", **_all(200, *FINANCE)),
    R("get", "/management/accounts", **_all(200, *FINANCE)),
    R("put", f"/management/accounts/balances?month={PAST}", {"cash_bank": "1000", "payables": None, "tax_liabilities": None}, **_all(200, *FINANCE)),
    R("get", "/management/drill/{chain}", **_all(200, *FINANCE)),
    R("put", f"/management/marketing/budgets?month={PAST}", {"budgets": []}, **_all(200, *FINANCE)),
    R("patch", "/management/schools/{school}", {"contract_value": "250000"}, **_all(200, *FINANCE)),
    # mgmt-011 salaries + departments (finance tier, CS2)
    R("get", "/management/salaries", **_all(200, *FINANCE)),
    R("put", f"/management/salaries?month={PAST}", lambda w: {"rows": [{"department_id": w["department"], "headcount": 2, "payable": "1000", "paid": "1000",
                                                                          "incentives": "0", "commissions": "0", "employer_cost": "0"}]}, **_all(200, *FINANCE)),  # fmt: skip
    R("get", "/management/departments", **_all(200, *FINANCE)),
    R("post", "/management/departments", lambda w: {"name": f"M34 Dept {_u()}"}, **_all(201, *FINANCE)),
    R("patch", "/management/departments/{department}", lambda w: {"name": f"M34 Renamed {_u()}"}, **_all(200, *FINANCE)),
    # mgmt-014 investments, mgmt-015 capital (partner-only)
    R("get", "/management/investments", **_all(200, *PARTNERS)),
    R("post", "/management/investments", lambda w: {"invested_on": w["today"], "investor_kind": "company", "amount": "1000", "purpose": f"M34 {_u()}", "vertical": "it"},
      **_all(201, *PARTNERS)),  # fmt: skip
    R("get", "/management/investments/{investment}", **_all(200, *PARTNERS)),
    R("patch", "/management/investments/{investment}", {"notes": "Reviewed"}, **_all(200, *PARTNERS)),
    R("get", "/management/capital", **_all(200, *PARTNERS)),
    R("post", "/management/capital/entries", lambda w: {"partner_id": w["partner_id"], "entry_date": w["today"], "kind": "additional", "amount": "1000"},
      **_all(201, *PARTNERS)),  # fmt: skip
    R("put", "/management/capital/shares", lambda w: {"effective_from": w["month"], "shares": [{"partner_id": w["partner_id"], "share_pct": "50", "commitment": "100000"}]},
      **_all(200, *PARTNERS)),  # fmt: skip
    # mgmt-004/005 ledger (finance; approval by a partner who did not create the entry)
    R("get", "/management/ledger/categories", **_all(200, *FINANCE)),
    R("post", "/management/ledger/categories", lambda w: {"kind": "income", "name": f"M34 {_u()}"}, **_all(201, *FINANCE)),
    R("patch", "/management/ledger/categories/{category}", lambda w: {"name": f"M34 {_u()}"}, **_all(200, *FINANCE)),
    R("get", "/management/ledger/options", **_all(200, *FINANCE)),
    R("get", "/management/ledger", **_all(200, *FINANCE)),
    R("get", "/management/ledger?include=auto", **_all(200, *FINANCE)),
    R("post", "/management/ledger", lambda w: {"entry_date": w["today"], "kind": "expense", "category_id": w["category"], "amount": "10", "description": "M34", "vertical": "shared"},
      **_all(201, *FINANCE)),  # fmt: skip
    R("get", "/management/ledger/{draft}", **_all(200, *FINANCE)),
    R("patch", "/management/ledger/{draft}", {"description": "M34 edited"}, **_all(200, *FINANCE)),
    R("post", "/management/ledger/{draft}/submit", **_all(200, *FINANCE)),
    R("post", "/management/ledger/{submitted}/approve", **_all(200, *PARTNERS)),
    R("post", "/management/ledger/{submitted}/reject", {"reason": "Missing receipt"}, **_all(200, *PARTNERS)),
    R("post", "/management/ledger/{approved}/reverse", {"reason": "Entered twice"}, **_all(201, *FINANCE)),
    R("put", "/management/ledger/{draft}/receipt", form=_pdf, **_all(200, *FINANCE)),
    R("get", "/management/ledger/{draft}/receipt", **_all(200, *FINANCE)),
    # mgmt-027 discussions (operational) + the responsible person's own decision line (M14)
    R("get", "/management/discussions", **_all(200, *OPERATIONAL)),
    R("get", "/management/discussions/options", **_all(200, *OPERATIONAL)),
    R("post", "/management/discussions", lambda w: {"topic": f"M34 {_u()}", "discussion_date": w["today"]}, **_all(201, *OPERATIONAL)),
    R("get", "/management/discussions/{discussion}", **_all(200, *OPERATIONAL)),
    R("patch", "/management/discussions/{discussion}", {"points": "Discussed"}, **_all(200, *OPERATIONAL)),
    R("post", "/management/discussions/{discussion}/attachments", form=_shareable_pdf, **_all(201, *OPERATIONAL)),
    R("get", "/management/discussions/{discussion}/attachments/{attachment}", **_all(200, *OPERATIONAL)),
    R("delete", "/management/discussions/{discussion}/attachments/{attachment}", **_all(204, *OPERATIONAL)),
    R("get", "/me/management-decisions", **_all(200, *SIGNED_IN)),
    R("patch", "/me/management-decisions/{discussion}", {"status": "in_progress"}, owner=200, **_all(404, *OTHERS)),
    R("get", "/me/management-decisions/{discussion}/attachments/{attachment}", owner=200, **_all(404, *OTHERS)),
    # mgmt-028 to-do + the owner's own task line (M14)
    R("get", "/management/tasks", **_all(200, *OPERATIONAL)),
    R("get", "/management/tasks/options", **_all(200, *OPERATIONAL)),
    R("post", "/management/tasks", lambda w: {"title": f"M34 {_u()}", "owner_user_id": w["owner_id"], "deadline": _day(5)}, **_all(201, *OPERATIONAL)),
    R("get", "/management/tasks/{task}", **_all(200, *OPERATIONAL)),
    R("patch", "/management/tasks/{task}", {"priority": "high"}, **_all(200, *OPERATIONAL)),
    R("get", "/me/management-tasks", **_all(200, *SIGNED_IN)),
    R("patch", "/me/management-tasks/{task}", {"status": "in_progress"}, owner=200, **_all(404, *OTHERS)),
    # mgmt-026 plans (operational)
    R("get", "/management/plans", **_all(200, *OPERATIONAL)),
    R("get", "/management/plans/options", **_all(200, *OPERATIONAL)),
    R("post", "/management/plans", lambda w: {"month": w["free_month"]}, **_all(201, *OPERATIONAL)),
    R("get", "/management/plans/{plan_month}", **_all(200, *OPERATIONAL)),
    R("patch", "/management/plans/{plan_month}", {"status": "active"}, **_all(200, *OPERATIONAL)),
    R("get", "/management/plans/{plan_month}/progress", **_all(200, *OPERATIONAL)),
    R("post", "/management/plans/{plan_month}/items", {"vertical": "it", "text": "M34 another item"}, **_all(201, *OPERATIONAL)),
    R("patch", "/management/plans/{plan_month}/items/{item}", {"done": True}, **_all(200, *OPERATIONAL)),
    R("delete", "/management/plans/{plan_month}/items/{item}", **_all(204, *OPERATIONAL)),
    R("post", "/management/plans/{plan_month}/items/{item}/tasks", lambda w: {"owner_user_id": w["owner_id"], "deadline": _day(5)}, **_all(201, *OPERATIONAL)),
    # mgmt-029 meetings (operational) + the invitee's own slice
    R("get", "/management/meetings", **_all(200, *OPERATIONAL)),
    R("get", "/management/meetings/options", **_all(200, *OPERATIONAL)),
    R("post", "/management/meetings", lambda w: {"title": f"M34 {_u()}", "kind": "partner", "starts_at": f"{_day(3)}T10:00:00+05:30", "mode": "Online",
                                                 "meeting_url": "https://meet.example.com/x"}, **_all(201, *OPERATIONAL)),  # fmt: skip
    R("get", "/management/meetings/{meeting}", **_all(200, *OPERATIONAL)),
    R("patch", "/management/meetings/{meeting}", {"title": "M34 renamed meeting"}, **_all(200, *OPERATIONAL)),
    R("post", "/management/meetings/{meeting}/minutes", {"minutes": "M34 corrected minutes"}, **_all(200, *OPERATIONAL)),
    R("post", "/management/meetings/{meeting}/decisions", lambda w: {"decision": "M34 decision", "responsible_user_id": w["owner_id"], "deadline": _day(9)},
      **_all(201, *OPERATIONAL)),  # fmt: skip
    R("post", "/management/meetings/{meeting}/tasks", lambda w: {"title": "M34 meeting task", "owner_user_id": w["owner_id"], "deadline": _day(9)}, **_all(201, *OPERATIONAL)),
    R("get", "/me/management-meetings", **_all(200, *SIGNED_IN)),
    # mgmt-032 monthly review (partner-only)
    R("get", "/management/reviews", **_all(200, *PARTNERS)),
    R("get", "/management/reviews/{review_month}", **_all(200, *PARTNERS)),
    R("post", "/management/reviews/{review_month}/generate", **_all(200, *PARTNERS)),
    R("patch", "/management/reviews/{review_month}", {"hiring": "Two trainers"}, **_all(200, *PARTNERS)),
    R("post", "/management/reviews/{review_month}/finalise", **_all(200, *PARTNERS)),
    R("get", "/management/reviews/{review_month}/pdf", **_all(200, *PARTNERS)),
]

PATH_VALUES = {"chain": "abroad"}  # the non-id path parameters


def _fill(text: str, w: dict) -> str:
    return text.format(**PATH_VALUES, **w)


async def _call(client, row: Row, w: dict, role: str):
    url = API + _fill(row.path, w)
    kwargs = {"headers": headers(None if role == "anon" else w["users"][role])}
    if row.form:
        data, files = row.form(w)
        kwargs |= {"data": data, "files": files}
    elif row.method not in ("get", "delete"):
        kwargs["json"] = row.body(w) if callable(row.body) else (row.body if row.body is not None else {})
    return await client.request(row.method.upper(), url, **kwargs)


def _operations() -> set[str]:
    """Every registered operation as "METHOD /path" (included routers are not flattened into `app.routes`)."""
    return {f"{method.upper()} {path.removeprefix(API)}" for path, ops in app.openapi()["paths"].items() for method in ops}


def _template(key: str) -> str:
    """`GET /management/ledger/{draft}?x=1` -> `GET /management/ledger/{}`: placeholders compare by position."""
    return re.sub(r"\{[^}]+\}", "{}", key.split("?")[0])


def test_every_management_route_has_a_row():
    """AC1 / CS3: a route added under the management prefixes without a matrix row (or a stale row) fails here."""
    routes = {_template(k) for k in _operations() if k.split(" ", 1)[1].startswith(PREFIXES)}
    rows = {_template(row.key) for row in MATRIX}
    assert routes - rows == set(), "routes without a matrix row"
    assert rows - routes == set(), "matrix rows without a route"


def test_no_row_is_listed_twice():
    keys = [row.key for row in MATRIX]
    assert len(keys) == len(set(keys)), "duplicate matrix rows"


@pytest.mark.asyncio
@pytest.mark.parametrize("row", MATRIX, ids=lambda r: r.key)
async def test_matrix_row(client, db_session, row):
    """AC2: every route x role cell. Refused cells and reads first on one world; then every other 2xx cell on its own fresh world."""
    shared = await world(client, db_session)
    wrong = []
    for role in ROLES:
        want = row.expected(role)
        if want in OK and row.method != "get":
            continue
        response = await _call(client, row, shared, role)
        if response.status_code != want:
            wrong.append(f"{role}: want {want}, got {response.status_code} {response.text[:160]}")
    for role in ROLES:
        want = row.expected(role)
        if want not in OK or row.method == "get":
            continue
        response = await _call(client, row, await world(client, db_session), role)
        if response.status_code != want:
            wrong.append(f"{role}: want {want}, got {response.status_code} {response.text[:200]}")
    assert not wrong, " | ".join(wrong)
