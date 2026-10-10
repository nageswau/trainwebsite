# upc-015 Partnership Alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A daily (IST morning) beat job raises agreement-expiry, delayed-milestone and overdue-digest alerts once each, in-app + email,
and an Alerts page lists the caller's own alerts.

**Architecture:** Alerts are `notifications` rows with a `upc015:<kind>:…` dedupe key (no new table). One service module does the three
passes and the list query; one GET route; a worker task + beat entry; one Next.js server page reusing `SchoolNotificationList`.

**Tech Stack:** FastAPI, SQLAlchemy async, Celery beat, Next.js App Router, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-10-upc-015-partnership-alerts-design.md`

## Global Constraints

- Thresholds 90/60/30/7 days exactly; send from 09:00 IST; beat `crontab(minute=30)` (UTC).
- Expiry body begins exactly: `⚠️ {University} partnership expires in {N} days. Renewal action required.`
- Dedupe key prefix `upc015:`; keys ≤ 200 chars; channels `["email"]` only.
- Recipients: active users only; each user once per alert.
- No migration. No new npm/pip dependency. Logs: counts and ids only.

## Review Focus

- Re-running the job the same day, or the next day for expiry/milestone → no duplicate (test: run twice, run next day).
- A university with the same user as manager and reporting head (cannot happen, roles differ), or backup = primary (CHECK forbids) — still
  dedupe recipients by id (test: recipients set).
- Milestone achieved by derived event (first application) with a past target → no alert (test).
- An inactive primary manager → no alert to them, backup still alerted (test).
- `kind=bogus` on the list → 422; another user's alerts never visible (test).

---

### Task 1: Service — expiry, milestone, digest passes

**Files:** Create `apps/api/app/services/partnership_alerts.py`; Test `apps/api/tests/test_upc_015_alerts.py`

**Interfaces — Produces:** `KINDS: tuple[str, ...]`, `async send_partnership_alerts(db, *, now: datetime) -> dict[str, int]`
(`created/duplicate/failed/skipped`), `async run_partnership_alerts() -> dict`, `async page(db, user, kind, limit, offset) -> dict`.

- [ ] Write tests: AC1 (30 days → one alert per recipient, body pattern, email delivery queued), AC2 (rerun → 0 created), 90 then 60,
  expired → none, signed at 20 days → only 7, before 09:00 → nothing, renewed/draft → none, milestone yesterday → primary+backup,
  achieved (manual) → none, 8 days ago → none, inactive primary skipped, digest one per day per assignee.
- [ ] Run `pytest tests/test_upc_015_alerts.py` → fails (module missing).
- [ ] Implement using `bdm_reminders._chunks/clean/INDIA`, `partnership_milestones._rows/_derived/_items`, insert-on-conflict in a
  savepoint, `queue_deliveries(..., context={"kind": "partnership_alert", "links": [...]}, channels=["email"])`.
- [ ] Run → pass. Commit.

### Task 2: Email kind + worker + beat

**Files:** Modify `apps/api/app/notifications/delivery.py` (add `"partnership_alert"` to the bdm/tel branch), `apps/api/app/worker.py`.
Test: in `test_upc_015_alerts.py` assert the beat entry and that the task name resolves.

- [ ] Failing test → add `send_partnership_alerts_task` + `"upc015-alerts": {"task": "app.worker.send_partnership_alerts_task",
  "schedule": crontab(minute=30)}` → pass. Commit.

### Task 3: `GET /partnership/alerts`

**Files:** Create `apps/api/app/api/partnership_alerts.py`; Modify `apps/api/app/main.py`, `apps/api/app/schemas.py`
(`PartnershipAlertKind`, `PartnershipAlertItem`, `PartnershipAlertPage`); Test `apps/api/tests/test_upc_015_alerts_api.py`.

- [ ] Tests: own only, newest first, kind filter, paging, unread, 401 anonymous, 403 for overseas_admin and a manager without a profile,
  super_admin empty 200, 422 bad kind/limit.
- [ ] Implement (reader check like `partnership_expected._require_reader`). Pass. Commit.

### Task 4: Web — Alerts page, nav, badge

**Files:** Create `apps/web/lib/partnershipAlerts.ts`, `apps/web/app/partnership/alerts/page.tsx`,
`apps/web/tests/components/PartnershipAlerts.test.tsx`; Modify `apps/web/lib/navigation.ts` (Alerts live; head nav entry),
`apps/web/app/partnership/dashboard/page.tsx`, `apps/web/app/partnership/head/team/page.tsx` (badge),
`navigation.partnership.test.ts` and `PartnershipTeamTable.test.tsx` counts.

- [ ] vitest: tabs with aria-current, empty text per kind, list rendered, pager, access denied for other roles, badge helper.
- [ ] Implement; `npx vitest run` focused; `tsc`; lint. Commit.

### Task 5: E2E + docs

**Files:** `apps/web/tests/e2e/upc-015-partnership-alerts.spec.ts`; docs: DEC-SCOPE-164 (register), API §12CF, RBAC §2.90,
DATA_MODEL note (dedupe key kinds), backlog status.

- [ ] E2E: seed via API container script (run job with a fixed `now`), manager sees alert, tabs filter, Open marks read; head sees nav.
- [ ] Docs. Commit.
