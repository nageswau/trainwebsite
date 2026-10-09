# upc-021 — Monthly partnership targets vs actual — design

- **Feature:** upc-021 (`docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-021; Appendix B T1–T7; EVID-020 §21, L695–L719)
- **Decision:** `DEC-SCOPE-144`. Migration `0129_partnership_targets` after `0128_university_milestones`; API §12BL; RBAC §2.70 (numbers
  are provisional until merge, the existing re-chain idiom).
- **Branch:** `worktree-upc-021` from `origin/main` @ `52646217` (upc-008 merged, PR #188); pushed as `feature/upc-021`.
- **Dependencies:** upc-001 (roles, `partnership_profiles`) and upc-007 (stage history) — merged. upc-014 (agreement events) — merged,
  so T6 is tracked. **upc-009 (Meetings) is not built**, so T3 is "Not tracked" (the bdm-016 R7 idiom) until it lands. upc-018 owns
  `services/partnership_metrics.py` but is not built; this item creates the module with the target actuals only.
- **Evidence:** EVID-020 §21 (`DERIVED_BLUEPRINT`); backlog U3 (`EXPLICIT_APPROVAL`: `partnership_head` sets targets); Q-23 ("the 7 §21
  KPIs per manager per month; set by the head; history kept"); Appendix B T1–T7 and D6/D7/D9/D11/D12. The numbers in §21 (50, 30, …) are
  illustrative, not requirement values.
- **Status of answers:** the owner directed this session to proceed with the recommended answers. TG1–TG12 below are those
  recommendations (`NEEDS_CONFIRMATION` at sign-off, not `EXPLICIT_APPROVAL`).

## 1. Understanding

A partnership head opens **Targets & Forecast**, picks a month and sees every direct-report manager against the 7 §21 KPIs: actual vs
target and achievement %, plus a team row. They open one manager to set that month's targets. A manager opens the same menu and sees
their own month (read-only). Actuals are computed by the CRM; targets are the only stored figures. Every change is audited (history
kept, Q-23). The forecast half of the page is upc-023.

## 2. Recommendations (TG1–TG12)

| # | Question | Recommended answer (used) |
|---|---|---|
| TG1 | KPI catalogue | Exactly the 7 §21 KPIs, in source order: `new_universities` (T1), `contacted` (T2), `meetings` (T3), `proposals` (T4), `negotiations` (T5), `mous` (T6), `new_active` (T7). Fixed in code; the DB CHECK repeats it. |
| TG2 | Month | `YYYY-MM`, IST month window `[1st 00:00 IST, next 1st 00:00 IST)`. Default: the current IST month (bdm-016 R2). |
| TG3 | Which months are editable | Current month and up to 12 ahead; a past month only by `super_admin` (bdm-016 R3). |
| TG4 | Target value | Whole number 0–100000; `null` in a batch clears it (bdm-016 R4). |
| TG5 | Achievement % | `round(actual × 100 / target)`; no target, target 0, not tracked or future → `null` ("—"). May exceed 100. |
| TG6 | Who sets | `partnership_head` for their direct reports (`partnership_profiles.reporting_head_user_id`); `super_admin` for any manager. A manager writing (even their own) → 403 (backlog negative scenario). Other roles → 403. Outside the head's team → 404. Inactive manager write → 422. |
| TG7 | Who reads | Manager: own only (another id → 404). Head: direct reports. `super_admin`: all. `overseas_admin` and others → 403 (targets are not in U3's overseas_admin read access). |
| TG8 | Attribution ("this manager") | A KPI event counts for the university's **primary manager at the time of the event**, reconstructed from the append-only `university_assignment_history` (latest primary row at or before the event → its `to`; else the earliest later row's `from`; else the current primary). The backup manager is not credited. |
| TG9 | "Past months are never re-scored" (AC) | Every actual is derived from immutable facts only — `university_stage_history`, `university_agreement_events`, `university_assignment_history` (all append-only) — and TG8 resolves the owner as of the event. A later reassignment, Lost flag, deactivation or stage move back never changes a closed month. No snapshot table. |
| TG10 | Counting | T1: universities whose **first-ever primary assignment** is in the month, credited to that assignee (upc-003 UM8: managers never create universities; heads create them unowned and then assign, so "created with this manager as primary" is read as the first primary assignment — a creation-date reading would re-score a closed month when the assignment comes later). T2 (=D6): universities whose **first** history entry into Initial Contact or a later stage is in the month. T4/T5/T7: distinct universities with a `move` into Proposal Sent / Commercial Discussion / Partner Activated in the month (a university bounced back and re-entered counts once a month). T6 (=D11): agreements with a status event to `signed` in the month (all agreement types; a signed renewal counts). T3 (=D7, meetings completed): **Not tracked** until upc-009. Lost/inactive universities still count (TG9). |
| TG11 | Manager joining mid-month (edge case) | Listed for every month from the month their user was created; credited only for events after they became primary (TG8). Managers created after a month are not listed for it. A deactivated manager is listed only for months where they have a target. |
| TG12 | Team comparison | Team target = Σ set targets (null when none set); team actual = Σ listed managers' actuals; team % from those. |

## 3. Data

`partnership_targets` (migration `0129_partnership_targets`, additive; guarded create; downgrade refuses while rows exist):

| Column | Type | Notes |
|---|---|---|
| id | uuid PK | |
| manager_user_id | uuid FK users RESTRICT | |
| month | date | CHECK first day of the month |
| kpi_key | varchar(40) | CHECK in the TG1 catalogue |
| target | integer | CHECK 0 ≤ target ≤ 100000 |
| set_by_user_id | uuid FK users RESTRICT | last writer |
| set_at | timestamptz | server `now()` on each write |
| created_at / updated_at | timestamptz | TimestampMixin |

`UNIQUE (manager_user_id, month, kpi_key)` (`uq_partnership_targets_manager_month_kpi`) — also the read index.

## 4. API (`app/api/partnership_targets.py`)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/partnership/targets?month=` | manager (own row) / head (reports) / super_admin (all) | `PartnershipTargetTeam` `{month, month_status, editable, kpis:[{key,label,definition,tracked}], managers:[{manager{id,full_name}, active, kpis:[{key,target,achieved,percent}]}], team:[{key,target,achieved,percent}]}` |
| GET | `/partnership/targets/{manager_user_id}?month=` | manager (self) / head (reports) / super_admin | `PartnershipTargetSheet` `{month, month_status, editable, manager{id,full_name}, kpis:[{key,label,definition,tracked,target,achieved,percent}]}`; out of scope → 404 |
| PUT | `/partnership/targets` | head / super_admin | body `{month, items:[{manager_user_id, kpi_key, target:int|null}]}` (1–200, no duplicate pair) → `{month, changed}` |

Errors: malformed month → 422; unknown KPI → 422; target outside 0–100000 → 422; past month by a head → 422; > 12 months ahead → 422;
manager outside team / missing → 404; inactive manager write → 422; manager/other role PUT → 403; other roles GET → 403.
`editable` is false for a manager's own read and for an inactive manager.

**Query count** is constant for any team size: managers, targets, and one query per fact source (created universities, first-contact,
stage entries, signed agreements, assignment history, current primaries).

### Transactions and races
PUT (bdm-016 idiom): validate the whole body first (nothing written on any error); lock the affected rows `FOR UPDATE`; upsert with
`INSERT … ON CONFLICT (manager_user_id, month, kpi_key) DO UPDATE` (last write wins, no duplicates); delete cleared ones; one `AuditLog`
per manager changed (`partnership_target.set`, metadata `{month, changes:[{kpi, from, to}]}` — keys and numbers only); unchanged values
are neither written nor audited; one commit. Logs carry actor id, month and count only.

## 5. Frontend

- `/partnership/targets` (menu "Targets & Forecast", upc-021 now `live`; added to the head nav and the super_admin nav):
  - month picker (a plain GET form; malformed month → this month + note);
  - manager: their own sheet, read-only (target / actual / achievement per KPI; "Not tracked" for T3);
  - head / super_admin: comparison table, one row per manager and a Team row, each cell "actual / target · %", with "Set targets" /
    "View" per manager; empty state "No partnership managers report to you yet."
- `/partnership/targets/[managerId]?month=`: one manager's editable sheet. Reuses the bdm-016 editor, generalised to a
  `TargetsEditor` (owner id + endpoints as props); `BdmTargetsEditor` becomes a thin wrapper so the BDM pages are unchanged.
- Loading, error (`accessUnavailable` / `accessDenied`), empty and refusal messages follow the existing pages.

## 6. Acceptance criteria (testable)

1. AC1 Each actual matches its definition (TG10) in fixtures; T3 is not tracked.
2. AC2 Past months are never re-scored: reassigning, marking lost or deactivating a university, or moving it back after the month leaves
   that month's actuals unchanged.
3. AC3 The head sets a manager's monthly targets; history is kept (audit row with from/to).
4. AC4 A manager setting their own target → 403; a manager reading another manager → 404; another role → 403.
5. AC5 A head cannot set targets for another head's manager (404) or a past month (422); super_admin can.
6. AC6 Comparison per manager and team (TG12).
7. AC7 A manager joining mid-month is listed for that month and credited only after assignment (TG8/TG11).
8. AC8 The page works for manager (read-only) and head (edit) at desktop, tablet and mobile widths, with keyboard access.

## 7. Testing

- `tests/test_upc_021_targets.py` (rules, scope, PUT, audit), `tests/test_upc_021_actuals.py` (T1–T7, attribution, re-scoring),
  `tests/test_upc_021_migration.py` (CHECK parity, guarded downgrade).
- Vitest: `PartnershipTargets*.test.tsx` (page states, editor reuse) + the existing `BdmTargets*.test.tsx` unchanged and green.
- Playwright: `e2e/upc-021-partnership-targets.spec.ts` (head sets a target, manager sees it read-only).

## 8. Regression risks

- `BdmTargetsEditor` extraction (BDM targets pages) — covered by the existing BDM vitest.
- `lib/navigation.ts` menu (`PartnershipMenuCard` count) and shared `models.py`/`schemas.py`/`main.py` append blocks.

## 9. Implementation plan (TDD, one slice at a time)

1. Model + migration `0129` + migration test (CHECK parity, guarded downgrade).
2. `services/partnership_metrics.py` `target_actuals(db, manager_ids, month)` — RED tests T1–T7, TG8 attribution, AC2 re-scoring → GREEN.
3. `services/partnership_targets.py` (rules, sheet, comparison, save) + `api/partnership_targets.py` + schemas — RED scope/rule/audit tests → GREEN.
4. Web: extract `TargetsEditor`; `lib/partnershipTargets.ts`; the two pages; nav entries — vitest first.
5. Playwright e2e; docs (DEC-SCOPE-144, API §12BL, RBAC §2.70, DATA_MODEL, SCREEN_CATALOG, backlog status).

## 10. Phase 3 reviews (applied above)

- **API:** GETs are side-effect free (no lazy snapshot); PUT is an idempotent batch upsert returning `{month, changed}`; a non-list
  comparison has no pagination (constant query count; teams are small). Existing contracts are untouched.
- **Security:** inline checks role → scope (403 then 404, the project convention); a manager id outside scope is a 404 (no IDOR
  oracle); the body's owner ids are re-checked server-side; Pydantic `extra="forbid"`, StrictInt bounds and the DB CHECKs back the
  input; ORM-bound queries only; audit + logs carry ids, keys and numbers (no PII). No commission data is involved. CSRF follows the
  existing cookie/same-site setup of every PUT. No new dependency.
- **Frontend:** existing `portal-title`, `analytics-form`, `table-scroll` region and `table` idioms; numeric inputs with labels;
  `role=status`/`role=alert` messages; double-submit guard (the editor's `inFlight`); the wide comparison scrolls inside its focusable
  region on mobile.

## 11. QA evidence (2026-10-09, Docker stack `upc021`, Chromium via Playwright)

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA21-01 | High | Manager `/partnership/targets` (and every BDM target sheet via the shared editor) | Sign in as a manager, open Targets & Forecast | Own month, read-only | "Application error: a server-side exception"; web log: "Functions cannot be passed directly to Client Components … sheetUrl: function" | **Fixed**: the editor takes data-only props and re-reads `{saveUrl}/{ownerId}?month=`; unit tests assert no function props (partnership pages + `BdmTargetsEditor`); manager page and the BDM sheet re-verified in the browser, bdm-016 e2e green |

Exploratory pass (all as expected after the fix): manager PUT → 403 "Only a partnership head can set targets"; manager → peer or
malformed id → "Partnership manager not found"; head → another head's manager → same; other head's managers not listed; counselor →
"Partnership targets access required"; signed out → `/overseas/login?next=/partnership/targets`; invalid target (-3, 4.5) refused in place;
save, no-change save ("No target changed."), refresh keeps the value, blank clears ("Saved 1 target."), back returns to the list; past
month read-only with only "View"; future month "Not started"; malformed month falls back with a note; team row sums (2 / 5 · 40% for two
Proposal Sent moves); 820 px and 375 px have no page side-scroll (the table scrolls in its region); no console errors; no 5xx (only
Next.js `_rsc` prefetches aborted by navigation). Super admin sees every manager (145 in the shared test DB) in one table — see risks.
