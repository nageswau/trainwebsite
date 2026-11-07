# pob-009 PO targets, territories, daily plans and reports — Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans), inline in the pob-009 session.

**Goal:** monthly PO targets vs live actuals, territories, target-company lists, a daily plan and daily/weekly reports for Team Leads.
**Architecture:** one metric function in `recruiter_metrics` (`po_counts`), one service `recruiter_po_work.py` (targets, territory, target
companies, plan, reports), one router `api/recruiter_po_work.py`; migration `0305_po_targets_reports`; Next.js pages under `/recruiter`.
**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, Pydantic v2, Next.js App Router, Vitest, Playwright.
**Spec:** `docs/superpowers/specs/2026-11-07-pob-009-po-targets-reports-design.md`

## Global Constraints
- T1 roles: `placement_team` own, `placement_manager` direct reports (outside team 404), `super_admin` all, others 403.
- IST periods; week = Monday–Sunday; `period_start` not Monday → 422; future period → 422.
- Targets 0..100000; editable current month + 12 ahead; past = super_admin only.
- Every write: one transaction + `AuditLog` row; nothing in services commits.
- Every new `/recruiter/*` route gets a rec-038 matrix row.

## Review Focus
- A PO reading another PO's report/drill-down → 403 (own only); a Team Lead naming a PO of another team → 404.
- Double submit of a report (two tabs) → 409, counts not overwritten.
- Weekly start on a Wednesday → 422 with a clear message.
- Adding the same follow-up/company to today's plan twice → 409.
- Response rate with zero contacts reached → none ("—"), not a division error.

---

### Task 1: Migration + models
**Files:** `apps/api/alembic/versions/0305_po_targets_reports.py`, `apps/api/app/models.py`, test `apps/api/tests/test_pob_009_migration.py`
- Tables `recruiter_targets`, `recruiter_target_companies`, `recruiter_plan_items`, `recruiter_activity_reports`; columns
  `companies.territory`, `recruiter_profiles.territory` (String 120, nullable). Checks: target 0..100000, kpi in `PO_TARGET_KPIS`,
  plan item exactly one of follow_up/company, period in (daily, weekly), weekly start is Monday (`extract(isodow) = 1`).
- Test: upgrade/downgrade round trip; checks reject bad rows.

### Task 2: `po_counts` metric (AC1)
**Files:** `app/services/recruiter_metrics.py`, test `tests/test_pob_009_po.py`
- `PO_KPIS = ("outreach","responses","meetings","requirements","vendor_registrations","active_accounts","placements")`
- `async def po_counts(db, user_ids: list[UUID], start: datetime, end: datetime, first: date, last: date) -> dict[UUID, dict]`
  returns each KPI + `contacts_reached` + `response_rate`. `async def po_contacts(db, user_id, start, end) -> list[dict]` (drill-down).
- Tests: each KPI credited to the actor; reply outside the reach set not counted; rate == replied/rows of drill-down; 0 reached → None.

### Task 3: Targets, territory, target companies (AC2)
**Files:** `app/services/recruiter_po_work.py`, `app/api/recruiter_po_work.py`, `app/schemas.py`, `app/main.py`
- Reuse `bdm_targets.parse_month/month_text/month_status/edit_refusal/_percent`.
- Tests: Team Lead saves → PO sheet shows target/actual/percent; mid-month change audited from/to; past month 422 for manager; other-team PO 404;
  PO PUT 403; territory batch adds only in-scope client companies; duplicate add ignored.

### Task 4: Daily plan
- Tests: suggestions = open due follow-ups + target companies; add/done/remove; duplicate 409; yesterday's plan read-only 422; other PO's item 404.

### Task 5: Activity reports + drill-down (AC1, AC3)
- Tests: weekly covers Mon 00:00 IST – next Mon 00:00 IST (activity Sunday 23:30 IST in, Monday 00:30 next week out); non-Monday 422;
  submit freezes counts; resubmit 409; Team Lead grid statuses; drill-down rate equality.

### Task 6: Company territory field
**Files:** `app/schemas.py` (REC_COMPANY_FIELDS, Create/Update/Out), `services/recruiter_companies.py` (out + `territory` filter), web form.
- Tests: PATCH territory round-trips; list `?territory=north` case-insensitive.

### Task 7: rec-038 matrix rows; docs (API_CONTRACT, DATA_MODEL, RBAC_MATRIX, DECISION register, backlog status, RTM)

### Task 8: Web — lib `recruiterPoWork.ts`, pages (PO: targets, daily-plan, activity-reports; TL: targets, targets/[userId],
activity-reports, activity-reports/[userId]), nav entries, company form Territory; Vitest component tests; Playwright e2e `pob-009-po-work.spec.ts`.
