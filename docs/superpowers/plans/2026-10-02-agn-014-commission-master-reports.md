# AGN-014 Commission Master-only Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give agency Masters a Revenue figure on their dashboard and a filterable, CSV-exportable commission report, while staff stay refused on every commission route.

**Architecture:** Two read-only Master-only routes in `apps/api/app/api/workflows.py` share one guarded query helper (auth → Master → date parsing → one scoped SELECT) and group rows per currency in Python. One additive metric in `services/portal.py` `_agent`. A client `AgentCommissionReportPanel` mounted by `WorkflowPanel` on the agent `reports` section; CSV download reuses `ReportDownloadButton` via two optional props.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, pytest (api-test container); Next.js/React, vitest + Testing Library, Playwright (web-test container).

**Spec:** `docs/superpowers/specs/2026-10-02-agn-014-commission-master-reports-design.md` (decision `DEC-SCOPE-051`).

## Global Constraints

- No migration, no new dependency, no shared Master-check helper (R5); inline `_require` + `_require_agent_master`.
- Authorization order: `get_current_user` → `_require(user, {"agent"}, "overseas")` → `_require_agent_master(user)` → date parsing.
- Scope: `AgentCommission.agent_id.in_(org_member_ids(user))`.
- Dates: `date_from`/`date_to` optional `YYYY-MM-DD` strings, inclusive UTC calendar days on `AgentCommission.created_at`.
- 422 messages verbatim: `"date_from must be a date (YYYY-MM-DD)"`, `"date_to must be a date (YYYY-MM-DD)"`, `"date_to must be on or after date_from"`.
- Staff 403 message verbatim: `"Only an agency Master can view commissions"`.
- Amounts summed per currency, never across currencies; floats rounded to 2 places.
- Status order: `estimated, eligible, claimed, payout_pending, paid`.
- CSV columns verbatim: `Student, University, Country, Intake, Status, Amount, Currency, Created, Claimed, Paid, Claim reference`; headers `text/csv; charset=utf-8`, `attachment; filename=agency-commissions-<from|all>-to-<to|all>.csv`, `Cache-Control: private, no-store`.
- Dashboard metric label `"Revenue"`; value `"INR 12,000"` / `"INR 12,000 · USD 500"` / `"INR 0"`.
- Staff pages never contain the word "commission"; existing metrics, labels and subtitles unchanged.
- No audit row on report reads/exports (R7); one structured `logger.info("agent_commission_report", …)` per request.
- `admin.py` and `test_agt_004_commission_payout.py` are not edited.

## Review Focus

1. A commission on an application with no student login (bridged school student, or neither id) → student shows the school student's name, else "—"; never a 500. Test: Task 1 `test_report_names_a_student_without_a_login`.
2. A non-INR commission next to INR ones → separate rows per currency in every breakdown and in Revenue; never summed. Tests: Task 1 `test_report_groups_per_currency`, Task 3 `test_revenue_is_per_currency`.
3. Commissions created at exactly 00:00:00 and 23:59:59 UTC on the boundary days → both included; 00:00:00 the day after → excluded. Test: Task 1 `test_date_filter_is_inclusive_utc_days`.
4. A student / university / intake / claim reference starting with `=`, `+`, `-`, `@` → CSV cell prefixed with `'`. Test: Task 2 `test_csv_neutralises_formulas`.
5. An impossible date (`2026-02-30`) or `date_to` before `date_from` sent by **staff** → `403`, not `422`. Test: Task 1 `test_staff_get_403_before_any_date_error`.

## How to run tests (worktree, Windows, Git Bash)

API (one-off runner; never `docker compose up`):
```bash
cd "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-014" && docker compose -p agn014 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-014/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
```
Web (vitest/tsc/eslint):
```bash
cd "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-014" && MSYS_NO_PATHCONV=1 docker compose -p agn014 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps -v "C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/agn-014/apps/web:/app" -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```
Below, `API_TEST "<paths>"` and `WEB_TEST "<cmd>"` abbreviate these two commands.

---

### Task 1: Report JSON route (guards, scope, date filter, per-currency breakdowns)

**Files:**
- Modify: `apps/api/app/api/workflows.py` (imports; new helpers + route after `agent_commissions`, ~line 2398)
- Modify: `apps/api/app/schemas.py` (after `CommissionAmountUpdate`, ~line 639)
- Create: `apps/api/tests/agn014_helpers.py`
- Test: `apps/api/tests/test_agn_014_commission_reports.py`

**Interfaces:**
- Produces: `workflows._commission_report_items(user, db, date_from, date_to) -> tuple[list[dict], date | None, date | None]`; item keys `student, university, country, intake, status, amount (Decimal), currency, created_at, claimed_at, paid_at, claim_reference`.
- Produces: `workflows._report_logged(user, fmt: str, rows: int, start, end) -> None`.
- Produces: route `GET /api/v1/workflows/overseas/agent/commissions/report` → `schemas.CommissionReportOut`.
- Produces (tests): `agn014_helpers.mk_commission(db, ctx, *, status="paid", amount=1000, currency="INR", created_at=None, student_name="Report Student", university_name="Report University", country_name="Reportland", intake="Sep 2027", agent=None, student=True, claim_reference=None) -> AgentCommission`.

- [ ] **Step 1: Write the helper and failing tests**

`apps/api/tests/agn014_helpers.py`:
```python
"""AGN-014 test helpers: a commission on its own application, university and country, with an explicit created_at."""

import uuid
from datetime import datetime

from app.models import AgentCommission, Country, OverseasApplication, University
from tests.agn001_helpers import mk_user

REPORT = "/api/v1/workflows/overseas/agent/commissions/report"
CSV = REPORT + ".csv"


async def mk_commission(
    db, ctx: dict, *, status: str = "paid", amount: float = 1000, currency: str = "INR", created_at: datetime | None = None,
    student_name: str = "Report Student", university_name: str = "Report University", country_name: str = "Reportland",
    intake: str = "Sep 2027", agent=None, student: bool = True, claim_reference: str | None = None,
) -> AgentCommission:
    suffix = uuid.uuid4().hex[:8]
    country = Country(
        slug=f"agn014-country-{suffix}", name=country_name, overview="", tuition="", living_expenses="", visa_process=[],
        work_opportunities="", post_study_work="", pr_opportunities="", faq=[],
    )
    db.add(country)
    await db.flush()
    university = University(
        country_id=country.id, slug=f"agn014-university-{suffix}", name=university_name, city="Testville", overview="",
        eligibility="", requirements=[], deadlines=[], scholarships=[],
    )
    db.add(university)
    await db.flush()
    owner = agent or ctx["master"]
    student_user = await mk_user(db, role="overseas_student", full_name=student_name) if student else None
    application = OverseasApplication(
        student_id=student_user.id if student_user else None, university_id=university.id, agent_id=owner.id, intake=intake, status="enrolled",
    )
    db.add(application)
    await db.flush()
    commission = AgentCommission(
        agent_id=owner.id, application_id=application.id, amount=amount, currency=currency, status=status,
        created_by="system_trigger", claim_reference=claim_reference or (None if status in {"estimated", "eligible"} else f"CLM-{suffix}"),
    )
    if created_at is not None:
        commission.created_at = created_at
    db.add(commission)
    await db.commit()
    return commission
```

`apps/api/tests/test_agn_014_commission_reports.py` (first part — Task 1):
```python
"""AGN-014 (DEC-SCOPE-051) -- Master-only commission report, CSV export and dashboard Revenue (spec §5-§6, AC01-AC08)."""

from datetime import UTC, datetime

import pytest

from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff
from tests.agn014_helpers import CSV, REPORT, mk_commission


def _day(y, m, d, hh=12, mm=0, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=UTC)


@pytest.mark.asyncio
async def test_master_report_breaks_down_by_status_university_country_intake(db_session):  # AC05
    ctx = await mk_active_org(db_session, name=f"Report {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=1500, university_name="Alpha U", country_name="Aland", intake="Sep 2027")
    await mk_commission(db_session, ctx, status="estimated", amount=500, university_name="Alpha U", country_name="Aland", intake="Jan 2028")
    await mk_commission(db_session, ctx, status="claimed", amount=2000, university_name="Beta U", country_name="Bland", intake="Sep 2027")
    async with client_for(ctx["master"].email) as c:
        response = await c.get(REPORT)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["date_from"] is None and body["date_to"] is None
    assert body["totals"] == [{"currency": "INR", "count": 3, "amount": 4000.0}]
    assert [(r["status"], r["count"], r["amount"]) for r in body["by_status"]] == [("estimated", 1, 500.0), ("claimed", 1, 2000.0), ("paid", 1, 1500.0)]
    assert [(r["university"], r["country"], r["count"], r["amount"]) for r in body["by_university"]] == [("Alpha U", "Aland", 2, 2000.0), ("Beta U", "Bland", 1, 2000.0)]
    assert [(r["country"], r["amount"]) for r in body["by_country"]] == [("Aland", 2000.0), ("Bland", 2000.0)]
    assert [(r["intake"], r["count"], r["amount"]) for r in body["by_intake"]] == [("Sep 2027", 2, 3500.0), ("Jan 2028", 1, 500.0)]


@pytest.mark.asyncio
async def test_report_groups_per_currency(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name=f"Currency {uniq()}")
    await mk_commission(db_session, ctx, amount=1000, currency="INR")
    await mk_commission(db_session, ctx, amount=250, currency="USD")
    async with client_for(ctx["master"].email) as c:
        body = (await c.get(REPORT)).json()
    assert body["totals"] == [{"currency": "INR", "count": 1, "amount": 1000.0}, {"currency": "USD", "count": 1, "amount": 250.0}]
    assert {(r["status"], r["currency"]) for r in body["by_status"]} == {("paid", "INR"), ("paid", "USD")}


@pytest.mark.asyncio
async def test_report_covers_the_agency_and_staff_created_applications_but_not_other_agencies(db_session):  # AC05
    ctx = await mk_active_org(db_session, name=f"Scope {uniq()}")
    staff = await mk_staff(db_session, ctx["org"])
    other = await mk_active_org(db_session, name=f"Other {uniq()}")
    await mk_commission(db_session, ctx, amount=100, university_name="Master U")
    await mk_commission(db_session, ctx, amount=200, university_name="Staff U", agent=staff["user"])
    await mk_commission(db_session, other, amount=999, university_name="Foreign U")
    async with client_for(ctx["master"].email) as c:
        body = (await c.get(REPORT)).json()
    assert {r["university"] for r in body["by_university"]} == {"Master U", "Staff U"}
    assert body["totals"] == [{"currency": "INR", "count": 2, "amount": 300.0}]


@pytest.mark.asyncio
async def test_report_names_a_student_without_a_login(db_session):  # Review Focus 1 (CSV asserts the name in Task 2)
    ctx = await mk_active_org(db_session, name=f"Nologin {uniq()}")
    await mk_commission(db_session, ctx, student=False)
    async with client_for(ctx["master"].email) as c:
        response = await c.get(REPORT)
    assert response.status_code == 200 and response.json()["totals"][0]["count"] == 1


@pytest.mark.asyncio
async def test_empty_report_has_empty_lists(db_session):
    ctx = await mk_active_org(db_session, name=f"Empty {uniq()}")
    async with client_for(ctx["master"].email) as c:
        body = (await c.get(REPORT)).json()
    assert all(body[key] == [] for key in ("totals", "by_status", "by_university", "by_country", "by_intake"))


@pytest.mark.asyncio
async def test_date_filter_is_inclusive_utc_days(db_session):  # AC06, Review Focus 3
    ctx = await mk_active_org(db_session, name=f"Dates {uniq()}")
    await mk_commission(db_session, ctx, amount=1, created_at=_day(2026, 8, 31, 23, 59, 59))
    await mk_commission(db_session, ctx, amount=10, created_at=_day(2026, 9, 1, 0, 0, 0))
    await mk_commission(db_session, ctx, amount=100, created_at=_day(2026, 9, 30, 23, 59, 59))
    await mk_commission(db_session, ctx, amount=1000, created_at=_day(2026, 10, 1, 0, 0, 0))
    async with client_for(ctx["master"].email) as c:
        both = (await c.get(REPORT, params={"date_from": "2026-09-01", "date_to": "2026-09-30"})).json()
        only_from = (await c.get(REPORT, params={"date_from": "2026-09-01"})).json()
        only_to = (await c.get(REPORT, params={"date_to": "2026-08-31"})).json()
    assert both["date_from"] == "2026-09-01" and both["date_to"] == "2026-09-30"
    assert both["totals"] == [{"currency": "INR", "count": 2, "amount": 110.0}]
    assert only_from["totals"][0]["amount"] == 1110.0
    assert only_to["totals"][0]["amount"] == 1.0


@pytest.mark.asyncio
@pytest.mark.parametrize(("params", "detail"), [
    ({"date_from": "2026-02-30"}, "date_from must be a date (YYYY-MM-DD)"),
    ({"date_to": "yesterday"}, "date_to must be a date (YYYY-MM-DD)"),
    ({"date_from": "2026-09-30", "date_to": "2026-09-01"}, "date_to must be on or after date_from"),
])
async def test_bad_dates_are_422_for_a_master(db_session, params, detail):  # AC06
    ctx = await mk_active_org(db_session, name=f"Bad {uniq()}")
    async with client_for(ctx["master"].email) as c:
        for path in (REPORT, CSV):
            response = await c.get(path, params=params)
            assert response.status_code == 422 and response.json()["detail"] == detail, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV])
async def test_staff_get_403_before_any_date_error(db_session, path):  # AC02, Review Focus 5
    ctx = await mk_active_org(db_session, name=f"Staff {uniq()}")
    staff = await mk_staff(db_session, ctx["org"], can_view_reports=True)
    async with client_for(staff["user"].email) as c:
        for params in ({}, {"date_from": "2026-02-30"}, {"date_from": "2026-09-30", "date_to": "2026-09-01"}):
            response = await c.get(path, params=params)
            assert response.status_code == 403 and response.json()["detail"] == "Only an agency Master can view commissions", response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV])
@pytest.mark.parametrize("role", ["overseas_admin", "overseas_student"])
async def test_non_agents_are_refused(db_session, path, role):  # AC08
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.get(path)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV])
async def test_report_requires_authentication(client, path):  # AC08
    assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [REPORT, CSV])
async def test_a_suspended_agency_is_refused(db_session, path):  # AC08
    ctx = await mk_active_org(db_session, name=f"Suspended {uniq()}")
    async with client_for(ctx["master"].email) as c:  # sign in while active, then suspend
        org = ctx["org"]
        org = await db_session.get(type(org), org.id, populate_existing=True)
        org.status = "suspended"
        await db_session.commit()
        assert (await c.get(path)).status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `API_TEST "tests/test_agn_014_commission_reports.py"`
Expected: FAIL — `404 Not Found` on `/commissions/report` (route does not exist); the 401 test also fails (404).

- [ ] **Step 3: Add the response schemas** (`apps/api/app/schemas.py`, after `CommissionAmountUpdate`)

```python
# AGN-014 (DEC-SCOPE-051): the agency's commission report -- every amount is per currency, never summed across currencies.
class CommissionReportTotal(BaseModel):
    currency: str
    count: int
    amount: float


class CommissionReportStatusRow(CommissionReportTotal):
    status: str


class CommissionReportUniversityRow(CommissionReportTotal):
    university: str
    country: str


class CommissionReportCountryRow(CommissionReportTotal):
    country: str


class CommissionReportIntakeRow(CommissionReportTotal):
    intake: str


class CommissionReportOut(BaseModel):
    date_from: date | None
    date_to: date | None
    totals: list[CommissionReportTotal]
    by_status: list[CommissionReportStatusRow]
    by_university: list[CommissionReportUniversityRow]
    by_country: list[CommissionReportCountryRow]
    by_intake: list[CommissionReportIntakeRow]
```
(Confirm `date` is imported at the top of `schemas.py`; add `from datetime import date` to the existing datetime import if not.)

- [ ] **Step 4: Implement the helpers and route** (`apps/api/app/api/workflows.py`)

Imports: change `from datetime import UTC, date, datetime` to `from datetime import UTC, date, datetime, time, timedelta`; add `from decimal import Decimal`; add `SchoolStudent` to the `app.models` import list; add `CommissionReportOut` to the `app.schemas` import.

After `agent_commissions` (before `claim_commission`):
```python
# AGN-014 (DEC-SCOPE-051): the agency's commission report, Master-only like the list above. Lifecycle order for `by_status`.
COMMISSION_STATUS_ORDER = ("estimated", "eligible", "claimed", "payout_pending", "paid")


def _report_date(value: str | None, name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(422, f"{name} must be a date (YYYY-MM-DD)") from None


async def _commission_report_items(user: User, db: AsyncSession, date_from: str | None, date_to: str | None) -> tuple[list[dict], date | None, date | None]:
    """Guards first, then the dates (a refused caller never sees a 422), then one scoped read: a single snapshot for every
    breakdown. Days are inclusive UTC calendar days on the commission's created date (R3/R7)."""
    _require(user, {"agent"}, "overseas")
    _require_agent_master(user)
    start, end = _report_date(date_from, "date_from"), _report_date(date_to, "date_to")
    if start and end and end < start:
        raise HTTPException(422, "date_to must be on or after date_from")
    query = (
        select(AgentCommission, OverseasApplication.intake, University.name, Country.name, func.coalesce(User.full_name, SchoolStudent.full_name))
        .select_from(AgentCommission)
        .join(OverseasApplication, OverseasApplication.id == AgentCommission.application_id)
        .join(University, University.id == OverseasApplication.university_id)
        .join(Country, Country.id == University.country_id)
        # A bridged school-student application has no login (`student_id` NULL): outer joins, never an inner join on User.
        .outerjoin(User, User.id == OverseasApplication.student_id)
        .outerjoin(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
        .where(AgentCommission.agent_id.in_(org_member_ids(user)))
        .order_by(AgentCommission.created_at, AgentCommission.id)
    )
    if start:
        query = query.where(AgentCommission.created_at >= datetime.combine(start, time.min, tzinfo=UTC))
    if end:
        query = query.where(AgentCommission.created_at < datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC))
    items = [
        {
            "student": student or "—", "university": university, "country": country, "intake": intake,
            "status": commission.status, "amount": Decimal(commission.amount), "currency": commission.currency,
            "created_at": commission.created_at, "claimed_at": commission.claimed_at, "paid_at": commission.paid_at,
            "claim_reference": commission.claim_reference,
        }
        for commission, intake, university, country, student in (await db.execute(query)).all()
    ]
    return items, start, end


def _commission_groups(items: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """Count and amount per (keys..., currency) -- currencies are never added together."""
    groups: dict[tuple, dict] = {}
    for item in items:
        group = groups.setdefault(
            tuple(item[k] for k in keys) + (item["currency"],),
            {**{k: item[k] for k in keys}, "currency": item["currency"], "count": 0, "amount": Decimal(0)},
        )
        group["count"] += 1
        group["amount"] += item["amount"]
    return [{**group, "amount": float(round(group["amount"], 2))} for group in groups.values()]


def _ranked(groups: list[dict], keys: tuple[str, ...]) -> list[dict]:
    return sorted(groups, key=lambda g: (-g["amount"], *(g[k] for k in keys), g["currency"]))


def _report_logged(user: User, fmt: str, rows: int, start: date | None, end: date | None) -> None:
    membership = user.agent_membership
    logger.info("agent_commission_report", extra={"extra_fields": {
        "actor_id": str(user.id), "org_id": str(membership.org_id) if membership else None, "format": fmt, "rows": rows,
        "date_from": start.isoformat() if start else None, "date_to": end.isoformat() if end else None,
    }})


@router.get("/overseas/agent/commissions/report", response_model=CommissionReportOut)
async def agent_commission_report(date_from: str | None = None, date_to: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items, start, end = await _commission_report_items(user, db, date_from, date_to)
    order = {status: index for index, status in enumerate(COMMISSION_STATUS_ORDER)}
    _report_logged(user, "json", len(items), start, end)
    return {
        "date_from": start, "date_to": end,
        "totals": sorted(_commission_groups(items, ()), key=lambda g: g["currency"]),
        "by_status": sorted(_commission_groups(items, ("status",)), key=lambda g: (order.get(g["status"], len(order)), g["status"], g["currency"])),
        "by_university": _ranked(_commission_groups(items, ("university", "country")), ("university", "country")),
        "by_country": _ranked(_commission_groups(items, ("country",)), ("country",)),
        "by_intake": _ranked(_commission_groups(items, ("intake",)), ("intake",)),
    }
```

- [ ] **Step 5: Run Task 1 tests**

Run: `API_TEST "tests/test_agn_014_commission_reports.py -k 'not csv and not CSV'"` (the CSV-parametrized cases still 404 until Task 2 — run them in Task 2).
Expected: PASS for every `REPORT` case.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/workflows.py apps/api/app/schemas.py apps/api/tests/agn014_helpers.py apps/api/tests/test_agn_014_commission_reports.py
git commit -m "feat(agn-014): Master-only commission report with per-currency breakdowns"
```

### Task 2: CSV export route

**Files:**
- Modify: `apps/api/app/api/workflows.py` (imports `csv`, `io`, `Response`, `_safe_cell`; route after `agent_commission_report`)
- Test: `apps/api/tests/test_agn_014_commission_reports.py` (append)

**Interfaces:**
- Consumes: `_commission_report_items`, `_report_logged` (Task 1); `app.api.school_bulk._safe_cell(value: str) -> str` (unchanged).
- Produces: `GET /api/v1/workflows/overseas/agent/commissions/report.csv`.

- [ ] **Step 1: Append failing tests**

```python
import csv as csv_module
import io


def _csv_rows(response):
    return list(csv_module.reader(io.StringIO(response.text)))


HEADER = ["Student", "University", "Country", "Intake", "Status", "Amount", "Currency", "Created", "Claimed", "Paid", "Claim reference"]


@pytest.mark.asyncio
async def test_csv_has_one_row_per_commission_with_the_filter(db_session):  # AC07
    ctx = await mk_active_org(db_session, name=f"Csv {uniq()}")
    await mk_commission(db_session, ctx, amount=1234.5, student_name="Asha Rao", university_name="Gamma U", country_name="Gland", intake="Sep 2027", created_at=_day(2026, 9, 15), claim_reference="CLM-1")
    await mk_commission(db_session, ctx, amount=5, created_at=_day(2026, 10, 15))
    async with client_for(ctx["master"].email) as c:
        response = await c.get(CSV, params={"date_from": "2026-09-01", "date_to": "2026-09-30"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == "attachment; filename=agency-commissions-2026-09-01-to-2026-09-30.csv"
    assert response.headers["cache-control"] == "private, no-store"
    rows = _csv_rows(response)
    assert rows[0] == HEADER
    assert rows[1:] == [["Asha Rao", "Gamma U", "Gland", "Sep 2027", "paid", "1234.50", "INR", "2026-09-15", "", "", "CLM-1"]]


@pytest.mark.asyncio
async def test_empty_csv_is_header_only_and_named_all(db_session):  # AC07
    ctx = await mk_active_org(db_session, name=f"CsvEmpty {uniq()}")
    async with client_for(ctx["master"].email) as c:
        response = await c.get(CSV)
    assert _csv_rows(response) == [HEADER]
    assert response.headers["content-disposition"] == "attachment; filename=agency-commissions-all-to-all.csv"


@pytest.mark.asyncio
async def test_csv_neutralises_formulas(db_session):  # AC07, Review Focus 4
    ctx = await mk_active_org(db_session, name=f"CsvFormula {uniq()}")
    await mk_commission(db_session, ctx, student_name="=HYPERLINK(1)", university_name="+U", intake="@Sep", claim_reference="-CLM")
    async with client_for(ctx["master"].email) as c:
        row = _csv_rows(await c.get(CSV))[1]
    assert row[0] == "'=HYPERLINK(1)" and row[1] == "'+U" and row[3] == "'@Sep" and row[10] == "'-CLM"


@pytest.mark.asyncio
async def test_csv_names_a_student_without_a_login(db_session):  # Review Focus 1
    ctx = await mk_active_org(db_session, name=f"CsvNologin {uniq()}")
    await mk_commission(db_session, ctx, student=False)
    async with client_for(ctx["master"].email) as c:
        assert _csv_rows(await c.get(CSV))[1][0] == "—"
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST "tests/test_agn_014_commission_reports.py"`
Expected: FAIL — CSV cases get `404` (the `report.csv` path is unknown).

- [ ] **Step 3: Implement** (`workflows.py`)

Imports: `import csv`, `import io`; `from fastapi import APIRouter, Depends, HTTPException, Request, Response`; `from app.api.school_bulk import _safe_cell`. Verify no import cycle: `school_bulk` imports `app.api.schools`, which does not import `workflows`.

```python
COMMISSION_CSV_COLUMNS = ("Student", "University", "Country", "Intake", "Status", "Amount", "Currency", "Created", "Claimed", "Paid", "Claim reference")


def _csv_day(value: datetime | None) -> str:
    return value.astimezone(UTC).date().isoformat() if value else ""


@router.get("/overseas/agent/commissions/report.csv")
async def agent_commission_report_csv(date_from: str | None = None, date_to: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AGN-014 R4: one row per commission. Every text cell goes through `_safe_cell` -- names and references are user-entered."""
    items, start, end = await _commission_report_items(user, db, date_from, date_to)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COMMISSION_CSV_COLUMNS)
    for item in items:
        writer.writerow([
            _safe_cell(item["student"]), _safe_cell(item["university"]), _safe_cell(item["country"]), _safe_cell(item["intake"]),
            item["status"], f"{item['amount']:.2f}", _safe_cell(item["currency"]), _csv_day(item["created_at"]),
            _csv_day(item["claimed_at"]), _csv_day(item["paid_at"]), _safe_cell(item["claim_reference"] or ""),
        ])
    _report_logged(user, "csv", len(items), start, end)
    filename = f"agency-commissions-{start.isoformat() if start else 'all'}-to-{end.isoformat() if end else 'all'}.csv"
    return Response(
        content=buffer.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}", "Cache-Control": "private, no-store"},
    )
```

- [ ] **Step 4: Run all AGN-014 backend tests**

Run: `API_TEST "tests/test_agn_014_commission_reports.py"`
Expected: PASS (all, including the CSV-parametrized cases from Task 1).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/workflows.py apps/api/tests/test_agn_014_commission_reports.py
git commit -m "feat(agn-014): CSV export of the agency commission report"
```

### Task 3: Revenue on the Master dashboard

**Files:**
- Modify: `apps/api/app/services/portal.py:705-709` (inside `if not staff:` of the dashboard branch)
- Test: `apps/api/tests/test_agn_014_commission_reports.py` (append)

- [ ] **Step 1: Append failing tests**

```python
def _metric(payload, label):
    return next((m["value"] for m in payload["metrics"] if m["label"] == label), None)


@pytest.mark.asyncio
async def test_master_dashboard_shows_paid_revenue(db_session):  # AC04
    ctx = await mk_active_org(db_session, name=f"Revenue {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=12000)
    await mk_commission(db_session, ctx, status="claimed", amount=999)
    other = await mk_active_org(db_session, name=f"RevOther {uniq()}")
    await mk_commission(db_session, other, status="paid", amount=5)
    async with client_for(ctx["master"].email) as c:
        payload = (await c.get("/api/v1/portal/overseas/agent/dashboard")).json()
    assert _metric(payload, "Revenue") == "INR 12,000"
    assert [m["label"] for m in payload["metrics"]][:5] == ["Students", "Applications", "Claimable commission", "Claims", "Revenue"]


@pytest.mark.asyncio
async def test_revenue_is_inr_0_when_nothing_is_paid(db_session):  # AC04
    ctx = await mk_active_org(db_session, name=f"RevZero {uniq()}")
    await mk_commission(db_session, ctx, status="eligible", amount=700)
    async with client_for(ctx["master"].email) as c:
        assert _metric((await c.get("/api/v1/portal/overseas/agent/dashboard")).json(), "Revenue") == "INR 0"


@pytest.mark.asyncio
async def test_revenue_is_per_currency(db_session):  # Review Focus 2
    ctx = await mk_active_org(db_session, name=f"RevCur {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=12000, currency="INR")
    await mk_commission(db_session, ctx, status="paid", amount=500, currency="USD")
    async with client_for(ctx["master"].email) as c:
        assert _metric((await c.get("/api/v1/portal/overseas/agent/dashboard")).json(), "Revenue") == "INR 12,000 · USD 500"


@pytest.mark.asyncio
async def test_staff_dashboard_has_no_revenue(db_session):  # AC04
    ctx = await mk_active_org(db_session, name=f"RevStaff {uniq()}")
    await mk_commission(db_session, ctx, status="paid", amount=12000)
    staff = await mk_staff(db_session, ctx["org"])
    async with client_for(staff["user"].email) as c:
        payload = (await c.get("/api/v1/portal/overseas/agent/dashboard")).json()
    assert _metric(payload, "Revenue") is None and "commission" not in str(payload).lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST "tests/test_agn_014_commission_reports.py -k revenue"`
Expected: FAIL — `_metric(..., "Revenue")` is `None`.

- [ ] **Step 3: Implement** (`services/portal.py`, inside the existing `if not staff:` block, after the "Claims" metric)

```python
            # AGN-014 (DEC-SCOPE-051 R1): Revenue = paid commissions, per currency (never summed across currencies).
            paid: dict[str, float] = {}
            for c in commissions:
                if c.status == "paid":
                    paid[c.currency] = paid.get(c.currency, 0.0) + float(c.amount)
            metrics.append({"label": "Revenue", "value": " · ".join(f"{currency} {amount:,.0f}" for currency, amount in sorted(paid.items())) or "INR 0"})
```

- [ ] **Step 4: Run tests**

Run: `API_TEST "tests/test_agn_014_commission_reports.py tests/test_agn_002_staff_access.py tests/test_agn_002_qa_messages.py"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/portal.py apps/api/tests/test_agn_014_commission_reports.py
git commit -m "feat(agn-014): Revenue (paid commission total) on the Master dashboard"
```

### Task 4: Migrated Master (real 0046 backfill) and the §6 matrix rows

**Files:**
- Test: `apps/api/tests/test_agn_014_commission_reports.py` (append)
- Modify: `apps/api/tests/test_agn_003_matrix.py` (append rows to `STAFF_REFUSED` and `MASTER_ALLOWED` only)

- [ ] **Step 1: Write the AC01 test**

```python
import importlib.util
from pathlib import Path

from sqlalchemy import select

from app.models import AgentOrgMember, UserRoleAssignment


def _migration_0046():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0046_agent_orgs.py"
    spec = importlib.util.spec_from_file_location("migration_0046_agent_orgs", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_a_master_created_by_the_0046_backfill_sees_older_commissions(db_session):  # AC01
    legacy = await mk_user(db_session, role="agent", full_name="Legacy Agent", profile={"agency_name": f"Legacy {uniq()}"})
    db_session.add(UserRoleAssignment(user_id=legacy.id, division="overseas", role="agent", approval_status="approved"))
    await db_session.commit()
    commission = await mk_commission(db_session, {"master": legacy}, status="paid", amount=4321, university_name="Legacy U")
    connection = await db_session.connection()
    await connection.run_sync(_migration_0046()._backfill)  # the real upgrade code: legacy agent -> M001 of a new active org
    await db_session.commit()
    member = await db_session.scalar(select(AgentOrgMember).where(AgentOrgMember.user_id == legacy.id))
    assert member is not None and member.role == "master" and member.code.endswith("-M001")
    async with client_for(legacy.email) as c:
        listed = (await c.get("/api/v1/workflows/overseas/agent/commissions")).json()
        dashboard = (await c.get("/api/v1/portal/overseas/agent/dashboard")).json()
        report = (await c.get(REPORT)).json()
        csv_text = (await c.get(CSV)).text
    assert str(commission.id) in {row["id"] for row in listed}
    assert _metric(dashboard, "Revenue") == "INR 4,321"
    assert report["by_university"][0]["university"] == "Legacy U"
    assert "Legacy U" in csv_text
```
Note: `_backfill` processes every membership-less agent in the shared test DB, as a real upgrade would; the test asserts only on its own agent.

- [ ] **Step 2: Add the matrix rows** (`test_agn_003_matrix.py`)

Append to `STAFF_REFUSED`:
```python
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions/report", None, "Only an agency Master can view commissions"),  # AGN-014
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions/report.csv", None, "Only an agency Master can view commissions"),  # AGN-014
```
Append to `MASTER_ALLOWED`:
```python
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions/report", None, 200),  # AGN-014
    ("Commission", "get", "/api/v1/workflows/overseas/agent/commissions/report.csv", None, 200),  # AGN-014
```

- [ ] **Step 3: Run**

Run: `API_TEST "tests/test_agn_014_commission_reports.py tests/test_agn_003_matrix.py"`
Expected: PASS. (AC01 is a characterization test: the behavior already exists on `main`; it must pass, not fail. If it fails, stop — that is a real regression to report, not something to code around.)

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_agn_014_commission_reports.py apps/api/tests/test_agn_003_matrix.py
git commit -m "test(agn-014): migrated Master sees older commissions; report routes in the §6 matrix"
```

### Task 5: `ReportDownloadButton` accepts CSV

**Files:**
- Modify: `apps/web/components/ReportDownloadButton.tsx`
- Test: `apps/web/tests/components/ReportDownloadButton.test.tsx` (append)

- [ ] **Step 1: Append failing tests**

```tsx
describe("ReportDownloadButton CSV (AGN-014)", () => {
  it("saves a CSV when told to expect one, with its own busy label", async () => {
    let finish: (value: unknown) => void = () => {};
    vi.stubGlobal("fetch", vi.fn(() => new Promise((resolve) => { finish = resolve; })));
    render(<ReportDownloadButton url="/x.csv" label="Download CSV" filename="x.csv" contentType="text/csv" busyLabel="Preparing CSV…" />);
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(screen.getByRole("button", { name: "Preparing CSV…" })).toBeInTheDocument();
    finish({ ok: true, status: 200, headers: new Headers({ "content-type": "text/csv; charset=utf-8" }), blob: async () => new Blob(["a,b"]), json: async () => ({}) });
    expect(await screen.findByRole("status")).toHaveTextContent("Report downloaded.");
    expect(clicked).toEqual([{ href: "blob:report", download: "x.csv" }]);
  });

  it("still refuses a CSV when expecting the default PDF", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 200, headers: new Headers({ "content-type": "text/csv" }), blob: async () => new Blob([]), json: async () => ({}) }));
    fireEvent.click(renderButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
    expect(clicked).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/components/ReportDownloadButton.test.tsx"`
Expected: the CSV test FAILs (the button shows "Preparing PDF…", then an alert); the PDF-default test passes already (characterization).

- [ ] **Step 3: Implement**

Signature: `export default function ReportDownloadButton({ url, label, filename, hint, contentType = "application/pdf", busyLabel = "Preparing PDF…" }: { url: string; label: string; filename: string; hint?: string; contentType?: string; busyLabel?: string })`.
Change `response.headers.get("content-type")?.startsWith("application/pdf")` → `startsWith(contentType)`; change `{busy ? "Preparing PDF…" : label}` → `{busy ? busyLabel : label}`. Extend the header comment: "AGN-014: `contentType`/`busyLabel` let the same button save a CSV; the defaults keep every PDF caller unchanged."

- [ ] **Step 4: Run**

Run: `WEB_TEST "npx vitest run tests/components/ReportDownloadButton.test.tsx"`
Expected: PASS (all, old and new).

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ReportDownloadButton.tsx apps/web/tests/components/ReportDownloadButton.test.tsx
git commit -m "feat(agn-014): ReportDownloadButton can save a CSV (PDF defaults unchanged)"
```

### Task 6: `lib/agentCommissionReport.ts` and `AgentCommissionReportPanel`

**Files:**
- Create: `apps/web/lib/agentCommissionReport.ts`
- Create: `apps/web/components/AgentCommissionReportPanel.tsx`
- Test: `apps/web/tests/components/AgentCommissionReportPanel.test.tsx`

**Interfaces:**
- Produces: `REPORT_URL`, `CSV_URL`, `reportQuery(from: string, to: string): string` (`""` or `?date_from=…&date_to=…`), `csvFilename(from, to): string`, `STATUS_LABELS: Record<string, string>`, `isReport(data: unknown): data is CommissionReport`, types `CommissionReport`, `ReportGroup`.
- Produces: `export default function AgentCommissionReportPanel()` (no props).

- [ ] **Step 1: Write the library**

```ts
// AGN-014 (DEC-SCOPE-051): the agency commission report's shape and URLs, shared by the panel and its tests. Mirrors
// CommissionReportOut (apps/api/app/schemas.py); the server remains the authority.

export const REPORT_URL = "/api/v1/workflows/overseas/agent/commissions/report";
export const CSV_URL = `${REPORT_URL}.csv`;

export type ReportGroup = { currency: string; count: number; amount: number };
export type CommissionReport = {
  date_from: string | null;
  date_to: string | null;
  totals: ReportGroup[];
  by_status: (ReportGroup & { status: string })[];
  by_university: (ReportGroup & { university: string; country: string })[];
  by_country: (ReportGroup & { country: string })[];
  by_intake: (ReportGroup & { intake: string })[];
};

export const STATUS_LABELS: Record<string, string> = {
  estimated: "Estimated",
  eligible: "Eligible",
  claimed: "Claimed",
  payout_pending: "Payout pending",
  paid: "Paid",
};

export function reportQuery(from: string, to: string): string {
  const params = new URLSearchParams();
  if (from) params.set("date_from", from);
  if (to) params.set("date_to", to);
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function csvFilename(from: string, to: string): string {
  return `agency-commissions-${from || "all"}-to-${to || "all"}.csv`;
}

// A 200 is only trusted if it has the report's shape (a proxy login page or an empty body must not crash the panel).
export function isReport(data: unknown): data is CommissionReport {
  const d = data as Partial<CommissionReport> | null;
  return !!d && typeof d === "object" && ["totals", "by_status", "by_university", "by_country", "by_intake"].every((k) => Array.isArray((d as Record<string, unknown>)[k]));
}
```

- [ ] **Step 2: Write the failing panel tests**

```tsx
import { StrictMode } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentCommissionReportPanel from "@/components/AgentCommissionReportPanel";
import { CSV_URL, REPORT_URL, type CommissionReport } from "@/lib/agentCommissionReport";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const EMPTY: CommissionReport = { date_from: null, date_to: null, totals: [], by_status: [], by_university: [], by_country: [], by_intake: [] };
const FULL: CommissionReport = {
  date_from: null, date_to: null,
  totals: [{ currency: "INR", count: 2, amount: 3500 }],
  by_status: [{ status: "payout_pending", currency: "INR", count: 1, amount: 2000 }, { status: "paid", currency: "INR", count: 1, amount: 1500 }],
  by_university: [{ university: "Alpha U", country: "Aland", currency: "INR", count: 2, amount: 3500 }],
  by_country: [{ country: "Aland", currency: "INR", count: 2, amount: 3500 }],
  by_intake: [{ intake: "Sep 2027", currency: "INR", count: 2, amount: 3500 }],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AgentCommissionReportPanel (AGN-014)", () => {
  it("shows loading, then the totals and four breakdown tables", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(FULL)));
    render(<AgentCommissionReportPanel />);
    expect(screen.getByText("Loading commission report…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "By status" })).toBeInTheDocument();
    for (const name of ["By university", "By country", "By intake"]) expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    expect(screen.getByText("Payout pending")).toBeInTheDocument();
    expect(screen.getByText(/INR 3,500.*2 commissions/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(REPORT_URL, { credentials: "same-origin" });
  });

  it("says so when there are no commissions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(EMPTY)));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByText("No commissions in this period.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "By status" })).toBeNull();
  });

  it.each([
    [401, { detail: "Not authenticated" }, "Your session has expired. Sign in again."],
    [403, { detail: "Only an agency Master can view commissions" }, "Only an agency Master can view commissions"],
    [500, { detail: "boom" }, "Something went wrong on our side. Please try again."],
  ])("shows a %s as an alert", async (status, body, text) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(body, status)));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(text);
  });

  it("shows a network failure as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<AgentCommissionReportPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong on our side. Please try again.");
  });

  it("refuses a To before From without a request", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(EMPTY));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentCommissionReportPanel />);
    await screen.findByText("No commissions in this period.");
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-30" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("'To' must be on or after 'From'.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("applies the filter and downloads the CSV for the applied range", async () => {
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(url.startsWith(CSV_URL) ? new Response("a,b", { status: 200, headers: { "content-type": "text/csv" } }) : json(FULL)),
    );
    vi.stubGlobal("fetch", fetchMock);
    URL.createObjectURL = vi.fn(() => "blob:csv");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<AgentCommissionReportPanel />);
    await screen.findByRole("heading", { name: "By status" });
    fireEvent.change(screen.getByLabelText("From"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByLabelText("To"), { target: { value: "2026-09-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${REPORT_URL}?date_from=2026-09-01&date_to=2026-09-30`, { credentials: "same-origin" }));
    await screen.findByRole("heading", { name: "By status" });
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(`${CSV_URL}?date_from=2026-09-01&date_to=2026-09-30`, { credentials: "same-origin" }));
  });

  it("ignores a response that arrives after a newer one", async () => {
    const resolvers: ((r: Response) => void)[] = [];
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((resolve) => resolvers.push(resolve))));
    render(<StrictMode><AgentCommissionReportPanel /></StrictMode>); // StrictMode mounts twice: two requests in flight
    await vi.waitFor(() => expect(resolvers.length).toBe(2));
    resolvers[1](json(EMPTY));
    expect(await screen.findByText("No commissions in this period.")).toBeInTheDocument();
    resolvers[0](json(FULL));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByRole("heading", { name: "By status" })).toBeNull();
  });
});
```
(`within` is imported for later assertions; drop it if eslint flags it as unused.)

- [ ] **Step 3: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/components/AgentCommissionReportPanel.test.tsx"`
Expected: FAIL — cannot resolve `@/components/AgentCommissionReportPanel`.

- [ ] **Step 4: Implement the panel**

```tsx
"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import DataTable from "@/components/DataTable";
import FormMessage from "@/components/FormMessage";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import { detailMessage } from "@/lib/apiErrors";
import { CSV_URL, REPORT_URL, STATUS_LABELS, type CommissionReport, csvFilename, isReport, reportQuery } from "@/lib/agentCommissionReport";

// AGN-014 (DEC-SCOPE-051): a Master's commission report on the agent Reports page -- breakdowns per currency, a created-date
// filter and a CSV of the applied range. WorkflowPanel mounts it for Masters only; the server refuses staff (403) regardless.
type Range = { from: string; to: string };
const NONE: Range = { from: "", to: "" };
const EXPIRED = "Your session has expired. Sign in again.";
const FAILED = "Something went wrong on our side. Please try again.";
const GROUP_COLUMNS = [{ key: "count", label: "Count" }, { key: "amount", label: "Amount" }, { key: "currency", label: "Currency" }];

const money = (amount: number) => amount.toLocaleString("en-IN", { maximumFractionDigits: 2 });

export default function AgentCommissionReportPanel() {
  const [draft, setDraft] = useState<Range>(NONE);
  const [applied, setApplied] = useState<Range>(NONE);
  const [report, setReport] = useState<CommissionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const latest = useRef(0);

  async function load(range: Range) {
    const id = ++latest.current; // a response for an older request is dropped
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${REPORT_URL}${reportQuery(range.from, range.to)}`, { credentials: "same-origin" });
      const body = await response.json().catch(() => null);
      if (id !== latest.current) return;
      if (response.ok && isReport(body)) {
        setReport(body);
        setApplied(range);
      } else {
        setReport(null);
        setError(response.status === 401 ? EXPIRED : response.ok || response.status >= 500 ? FAILED : detailMessage((body as { detail?: unknown } | null)?.detail, FAILED));
      }
    } catch {
      if (id === latest.current) {
        setReport(null);
        setError(FAILED);
      }
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }

  useEffect(() => {
    void load(NONE);
  }, []);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    if (draft.from && draft.to && draft.to < draft.from) {
      setRangeError("'To' must be on or after 'From'.");
      return;
    }
    setRangeError(null);
    void load(draft);
  }

  const tables: { title: string; columns: { key: string; label: string }[]; rows: Record<string, unknown>[] }[] = report
    ? [
        { title: "By status", columns: [{ key: "status", label: "Status" }, ...GROUP_COLUMNS], rows: report.by_status.map((r) => ({ ...r, status: STATUS_LABELS[r.status] ?? r.status, amount: money(r.amount) })) },
        { title: "By university", columns: [{ key: "university", label: "University" }, { key: "country", label: "Country" }, ...GROUP_COLUMNS], rows: report.by_university.map((r) => ({ ...r, amount: money(r.amount) })) },
        { title: "By country", columns: [{ key: "country", label: "Country" }, ...GROUP_COLUMNS], rows: report.by_country.map((r) => ({ ...r, amount: money(r.amount) })) },
        { title: "By intake", columns: [{ key: "intake", label: "Intake" }, ...GROUP_COLUMNS], rows: report.by_intake.map((r) => ({ ...r, amount: money(r.amount) })) },
      ]
    : [];

  return (
    <div className="action-card" aria-busy={loading}>
      <h3>Commission report</h3>
      <p className="muted">Your agency&apos;s commissions by the date they were created (UTC). Amounts are totalled per currency.</p>
      <form aria-label="Commission report filters" onSubmit={apply} className="actions" style={{ alignItems: "flex-end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="commission-report-from">From</label>
          <input id="commission-report-from" type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="commission-report-to">To</label>
          <input id="commission-report-to" type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
        </div>
        <button className="btn" type="submit" aria-disabled={loading}>Apply</button>
      </form>
      {rangeError && <FormMessage message={{ text: rangeError, failed: true }} />}
      {loading && <p role="status">Loading commission report…</p>}
      {error && <FormMessage message={{ text: error, failed: true }} />}
      {!loading && report && report.totals.length === 0 && <p>No commissions in this period.</p>}
      {!loading && report && report.totals.length > 0 && (
        <>
          <p>
            <strong>Total:</strong>{" "}
            {report.totals.map((t) => `${t.currency} ${money(t.amount)} (${t.count} commission${t.count === 1 ? "" : "s"})`).join(" · ")}
          </p>
          {tables.map((table) => (
            <section key={table.title}>
              <h4>{table.title}</h4>
              <DataTable columns={table.columns} rows={table.rows} label={`Commissions ${table.title.toLowerCase()}`} />
            </section>
          ))}
        </>
      )}
      {!loading && report && (
        <ReportDownloadButton url={`${CSV_URL}${reportQuery(applied.from, applied.to)}`} label="Download CSV" filename={csvFilename(applied.from, applied.to)} contentType="text/csv" busyLabel="Preparing CSV…" />
      )}
    </div>
  );
}
```
Note: the totals line wording "commission(s)" is on a Master-only panel; staff never render it.

- [ ] **Step 5: Run**

Run: `WEB_TEST "npx vitest run tests/components/AgentCommissionReportPanel.test.tsx"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/lib/agentCommissionReport.ts apps/web/components/AgentCommissionReportPanel.tsx apps/web/tests/components/AgentCommissionReportPanel.test.tsx
git commit -m "feat(agn-014): agent commission report panel with filters, states and CSV"
```

### Task 7: Mount the panel for Masters on the agent Reports page

**Files:**
- Modify: `apps/web/components/WorkflowPanel.tsx` (flag near `showAgentTeam`, the early-return guard, the action grid; import)
- Test: `apps/web/tests/components/WorkflowPanel.agentCommissionReport.test.tsx`

- [ ] **Step 1: Failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const agent = (memberRole: "master" | "staff" | null) =>
  ({ id: "u1", email: "a@example.local", full_name: "A", role: "agent", division: "overseas", profile: {}, agent_member_role: memberRole, agent_permissions: memberRole === "staff" ? { can_verify_documents: false, can_view_reports: true } : null }) as unknown as User;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel agent Reports (AGN-014)", () => {
  it("shows a Master the commission report", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<WorkflowPanel user={agent("master")} section="reports" />);
    expect(screen.getByRole("heading", { name: "Commission report" })).toBeInTheDocument();
  });

  it("never shows staff the commission report, even with Reports on", () => {
    const fetchMock = vi.fn(() => new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<WorkflowPanel user={agent("staff")} section="reports" />);
    expect(screen.queryByRole("heading", { name: "Commission report" })).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/components/WorkflowPanel.agentCommissionReport.test.tsx"`
Expected: the Master test FAILs (no heading); the staff test passes (characterization).

- [ ] **Step 3: Implement**

- Import: `import AgentCommissionReportPanel from "./AgentCommissionReportPanel";` (match the file's existing import style).
- After `const showAgentTeam = ...`:
  ```tsx
  // AGN-014 (DEC-SCOPE-051): the commission report is Master-only; staff with Reports keep today's commission-free report.
  const showAgentCommissionReport = user.role === "agent" && section === "reports" && user.agent_member_role !== "staff";
  ```
- Add `&& !showAgentCommissionReport` to the early-return guard.
- Render `{showAgentCommissionReport && <AgentCommissionReportPanel/>}` right after `{showAgentTeam && <AgentStaffPanel/>}`.

- [ ] **Step 4: Run all web unit tests + type check + lint**

Run: `WEB_TEST "npx vitest run && npx tsc --noEmit && npx eslint components lib tests"`
Expected: PASS, no type or lint errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/WorkflowPanel.tsx apps/web/tests/components/WorkflowPanel.agentCommissionReport.test.tsx
git commit -m "feat(agn-014): mount the commission report for agency Masters"
```

### Task 8: Playwright spec (AC11) — written now, run in browser validation

**Files:**
- Create: `apps/web/tests/e2e/agn-014-commission-master.spec.ts`

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from "@playwright/test";

import { E2E_PASSWORD } from "./helpers/welcome";
import { adminActivate, registerApprovedAgency, signIn } from "./helpers/agency";

// AGN-014 -- a Master sees Revenue and the commission report (filter + CSV); staff are refused commissions and see no Revenue.
// Requires the stack running with `python -m app.seed` applied. The commission is made paid through the real API: a student
// applies through the new agency's Master, the Overseas Admin enrols it (auto commission), sets the amount, the Master claims,
// and the admin approves the payout (a system-triggered commission, so the same admin may approve -- AGT-004 unchanged).

const ADMIN = { email: "overseasadmin@edusphere.local", password: "Demo@123", division: "overseas" };

test("a Master sees Revenue and the commission report; staff are refused (AGN-014)", async ({ page, browser }) => {
  test.setTimeout(180_000);
  const unique = Date.now();
  const masterEmail = await registerApprovedAgency(page, unique, "agn014");
  const api = page.request;

  await api.post("/api/v1/auth/login", { data: ADMIN });
  const agents = (await (await api.get("/api/v1/overseas-admin/agents")).json()) as { id: string; email: string }[];
  const master = agents.find((a) => a.email === masterEmail);
  if (!master) throw new Error("new agency Master not listed");

  const studentName = `AGN014 Student ${unique}`;
  expect((await api.post("/api/v1/auth/register", { data: { email: `agn014-st-${unique}@example.local`, password: "Sup3r-Secret-Pass!", full_name: studentName, division: "overseas", account_type: "student" } })).ok()).toBeTruthy();
  const universities = (await (await api.get("/api/v1/public/universities")).json()) as { id: string }[];
  const created = await api.post("/api/v1/workflows/overseas/applications", { data: { university_id: universities[0].id, agent_id: master.id } });
  expect(created.ok()).toBeTruthy();
  const applicationId = (await created.json()).id as string;

  await api.post("/api/v1/auth/login", { data: ADMIN });
  expect((await api.patch(`/api/v1/workflows/overseas/applications/${applicationId}`, { data: { status: "enrolled" } })).ok()).toBeTruthy();
  const rows = (await (await api.get("/api/v1/portal/overseas/admin/commissions")).json()).rows as { id: string; student: string }[];
  const commissionId = rows.find((r) => r.student === studentName)?.id;
  if (!commissionId) throw new Error("auto-created commission not found");
  expect((await api.patch(`/api/v1/workflows/overseas/agent/commissions/${commissionId}`, { data: { amount: 20000 } })).ok()).toBeTruthy();

  await api.post("/api/v1/auth/login", { data: { email: masterEmail, password: "Sup3r-Secret-Pass!", division: "overseas" } });
  expect((await api.post(`/api/v1/workflows/overseas/agent/commissions/${commissionId}/claim`)).ok()).toBeTruthy();
  await api.post("/api/v1/auth/login", { data: ADMIN });
  expect((await api.post(`/api/v1/overseas-admin/commissions/${commissionId}/approve-payout`)).ok()).toBeTruthy();

  // Master: Revenue on the dashboard, the report with a filter, and the CSV.
  await signIn(page, masterEmail, "Sup3r-Secret-Pass!");
  await expect(page.getByText("Revenue")).toBeVisible();
  await expect(page.getByText("INR 20,000").first()).toBeVisible();
  await page.goto("/overseas/agent/reports");
  await expect(page.getByRole("heading", { name: "Commission report" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "By status" })).toBeVisible();
  const today = new Date().toISOString().slice(0, 10);
  await page.getByLabel("From").fill(today);
  await page.getByLabel("To").fill(today);
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByRole("heading", { name: "By status" })).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download CSV" }).click();
  expect((await download).suggestedFilename()).toBe(`agency-commissions-${today}-to-${today}.csv`);

  // Staff: no Commissions link, the 403 card on a typed URL, no Revenue.
  const staffEmail = `agn014-s-${unique}@example.local`;
  await api.post("/api/v1/auth/login", { data: { email: masterEmail, password: "Sup3r-Secret-Pass!", division: "overseas" } });
  expect((await api.post("/api/v1/workflows/overseas/agent/team/staff", { data: { full_name: "AGN014 Staff", email: staffEmail } })).ok()).toBeTruthy();
  const staff = await (await browser.newContext()).newPage();
  await adminActivate(staff.request, staffEmail);
  await signIn(staff, staffEmail, E2E_PASSWORD);
  await expect(staff.getByRole("link", { name: "Commissions", exact: true })).toHaveCount(0);
  await expect(staff.getByText("Revenue")).toHaveCount(0);
  await staff.goto("/overseas/agent/commissions");
  await expect(staff.getByText("Only an agency Master can open this page")).toBeVisible();
});
```
(Verify `registerApprovedAgency`'s third argument and returned email against `helpers/agency.ts` before running; adjust only the call, not the assertions.)

- [ ] **Step 2: Type-check**

Run: `WEB_TEST "npx tsc --noEmit"`
Expected: PASS. Running the spec needs the owner's stack (browser validation phase); not run here.

- [ ] **Step 3: Commit**

```bash
git add apps/web/tests/e2e/agn-014-commission-master.spec.ts
git commit -m "test(agn-014): Playwright spec for Master revenue/report and staff refusal"
```

### Task 9: Documentation and lite regression

**Files:**
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (§AGN-014 entry: traces, AC01–AC11, status IN PROGRESS — not COMPLETE)
- Modify: `docs/features/MASTER_FEATURE_CATALOG.md`, `docs/features/feature_catalog.json` (AGN-014 entry)
- Modify: `docs/architecture/API_CONTRACT.md` (two rows beside line 221's Master-only commission row)
- Modify: `docs/architecture/RBAC_MATRIX.md` (agent commission report rows: Master ✅, Staff ❌ 403)
- Modify: `docs/evidence/CONFLICT_MATRIX.md` (C-10 update line: commission reports decided as DEC-SCOPE-051; per-staff breakdown, staff performance, CRM settings remain parked)
- Modify: `docs/quality/RTM.md`, `docs/ux/SCREEN_CATALOG.md` (agent Reports: commission report panel)

- [ ] **Step 1: Write the doc entries** (each states AGN-014, DEC-SCOPE-051, the two routes, the Revenue metric, and that browser validation and Codex review are pending).

- [ ] **Step 2: Run the lite backend regression**

Run: `API_TEST "tests/test_agn_014_commission_reports.py tests/test_agt_003_commission_accrual.py tests/test_agt_004_commission_payout.py tests/test_agn_001_tenancy.py tests/test_agn_001_registration_and_gate.py tests/test_agn_002_staff_access.py tests/test_agn_002_qa_messages.py tests/test_agn_003_matrix.py tests/test_agn_003_permissions.py tests/test_agn_004_staff_guards.py tests/test_rpt_002_overseas_reporting.py tests/test_sec_001_audit_trail.py tests/test_enh_028_templates.py"`
Expected: PASS; `test_agt_004_commission_payout.py` unedited (`git diff main -- apps/api/tests/test_agt_004_commission_payout.py apps/api/app/api/admin.py` is empty).

- [ ] **Step 3: Run the full web unit suite, types and lint**

Run: `WEB_TEST "npx vitest run && npx tsc --noEmit && npx eslint ."`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add docs
git commit -m "docs(agn-014): backlog, catalog, API contract, RBAC, C-10, RTM, screens"
```

**Not in this plan (owner's next phases):** running the Playwright specs against the stack, browser validation, independent Codex review, full backend suite (owner's cadence). AGN-014 is not COMPLETE until those pass.
