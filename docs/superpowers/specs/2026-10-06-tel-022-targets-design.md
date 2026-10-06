# tel-022 — Daily + monthly telecaller targets (design)

NO-ASSUMPTION MODE. Feature `tel-022` of `docs/delivery/TELECALLER_CRM_BACKLOG.md` (EVID-019 §15, T2, T23, T28). Branch
`feature/tel-022` from `origin/main` @ `10fce82e` (tel-003 merged; migration head `0078_enquiry_lead_record`).
Dependency tel-001 is merged (PR #68). Decision: **`DEC-SCOPE-078` (provisional)**; migration **`0079_tel_targets` (provisional)** —
tel-012 also re-chains after 0078, so whichever merges second renumbers.

## 1. Authority

| Source | Class | Content |
|---|---|---|
| EVID-019 §15 lines 528–547 | DERIVED_BLUEPRINT (in scope by T1) | Management assigns monthly/daily targets for 6 KPIs; dashboard shows achieved / target |
| T2, T23, T28 (2026-10-05) | EXPLICIT_APPROVAL | Manager sets targets; direct-report scope; daily + monthly, team default + per-telecaller override, applies from next day/month, history kept, past never re-scored |
| §22 line 713 | DERIVED_BLUEPRINT | Telecaller must not modify targets → 403 |
| G1–G4 (owner, 2026-10-06, this session) | EXPLICIT_APPROVAL | below |

- **G1 (Q-17):** no working-day calendar. A daily target applies to every IST calendar day.
- **G2:** the manager picks `effective_from`. A daily target starts tomorrow or later; a monthly target starts on the 1st of a month, next
  month or later; the earliest date is the default. Re-saving the same future date replaces that pending value. Rows whose date has
  arrived are never edited.
- **G3:** any `telecaller_manager` or `super_admin` sets team defaults for both teams. Overrides are limited to the manager's direct
  reports; `super_admin` may set any. Division admins have no write access (and no read route in this item).
- **G4:** a "My targets" card on `/telecaller/dashboard` shows targets only. tel-021 adds achieved figures.

**Out of scope:** achieved figures (they come from tel-021's `telecaller_metrics`, which does not exist yet), working-day calendars, team
history for a mid-month team move (tel-025 owns team moves; resolution uses the telecaller's current team, see §4), and BDM targets
(bdm-016 is not built, so there is nothing to share).

## 2. KPIs (Appendix B K1–K6)

| Key | Label | Achieved later from |
|---|---|---|
| `calls` | Calls | D2 |
| `connected_calls` | Connected calls | D3 |
| `qualified_leads` | Qualified leads | D11 |
| `follow_ups` | Follow-ups | D5 |
| `counselling_appointments` | Counselling appointments | D8 |
| `conversions` | Conversions | D13 |

The source's example values (80/40/15/25/8/3) are **not** seeded as defaults (Appendix A, lines 536–541). A KPI with no row is "Not set".

## 3. Data — `tel_targets` (append-only history, one row per value)

| Column | Type | Rule |
|---|---|---|
| id | uuid PK | |
| scope | varchar(10) | `team` \| `user` |
| team | varchar(20) NULL | `it` \| `overseas`; set iff scope = team |
| user_id | uuid NULL FK users | set iff scope = user |
| period | varchar(10) | `daily` \| `monthly` |
| kpi | varchar(40) | one of §2 |
| value | integer NULL | 0–100000; NULL only for scope = user and means "override removed → team default" |
| effective_from | date | monthly ⇒ day 1 |
| set_by_user_id | uuid FK users | |
| created_at / updated_at | timestamptz | |

CHECKs: scope/period/kpi/team enums; `(scope='team' AND team IS NOT NULL AND user_id IS NULL) OR (scope='user' AND user_id IS NOT NULL
AND team IS NULL)`; `value IS NULL OR value BETWEEN 0 AND 100000`; `value IS NOT NULL OR scope='user'`; `period='daily' OR
EXTRACT(DAY FROM effective_from)=1`.
Partial unique indexes (they also serve the lookups): `uq_tel_targets_team (team, period, kpi, effective_from) WHERE scope='team'` and
`uq_tel_targets_user (user_id, period, kpi, effective_from) WHERE scope='user'`.

Migration 0079: create-if-missing (0075/0076 idiom, because 0001's `create_all` already builds the table on a fresh database), no backfill,
no existing row is touched. Downgrade refuses while any row exists.

## 4. Resolution (`services/telecaller_targets.py`, the single function tel-021 will call)

`effective_targets(db, team, user_id, day)` → for each period and KPI, `{value, source}`, where `source ∈ {user, team, null}`:

1. Key date = `day` (daily) or the first of `day`'s month (monthly).
2. Take the latest `user` row with `effective_from ≤ key`. If its value is not NULL, that value wins (**AC1: the override beats the
   default**).
3. Otherwise (no user row, or the latest one removed the override) take the latest `team` row for the telecaller's **current** team with
   `effective_from ≤ key`.
4. Otherwise the value is `null` ("Not set").

This runs as one query per scope using `DISTINCT ON (period, kpi) … ORDER BY period, kpi, effective_from DESC` over the period's key date,
so there is no N+1. Because rows are never edited once their date has arrived, a past day resolves to the value it had then (**AC2/AC3**).

## 5. API (router `api/telecaller_targets.py`, mounted under `/api/v1`; inline role checks per the 2026-09-28 convention)

### `POST /telecaller/targets` → 200 `TelTargetSetOut`
Body: `{scope: "team"|"user", team?: "it"|"overseas", user_id?: uuid, period: "daily"|"monthly", effective_from?: date,
values: {<kpi>: int|null, …}}`. Unknown keys → 422.
- Role: `telecaller_manager` or `super_admin`, else 403 (**§22: a telecaller POST → 403**).
- `scope=team` needs `team` and no `user_id`. `scope=user` needs `user_id` and no `team`. Otherwise 422.
- `scope=user`: the target must be a `telecaller` with a profile who is in the caller's scope (manager: `reporting_manager_user_id ==
  me`; super_admin: anyone). Otherwise **404 "Telecaller not found"**, so another manager's report can't be enumerated. The profile row is
  read `FOR SHARE`, so a concurrent manager change waits. An inactive telecaller → 422.
- `values`: 1–6 keys from §2. Each value is an integer 0–100000 (a negative value → 422, **AC4**). `null` is allowed only for
  `scope=user` (it removes the override).
- `effective_from`: defaults to the earliest allowed date. Daily: ≥ tomorrow (IST, database clock). Monthly: day 1 and ≥ the first of next
  month. Otherwise 422 with a sentence naming the earliest date.
- Write: one `INSERT … ON CONFLICT (partial unique) DO UPDATE SET value, set_by_user_id, updated_at` per KPI, so concurrent saves to the
  same pending date can't race into a 500. The date rule guarantees only future rows are ever updated (G2).
- One `AuditLog` row: `telecaller.target_set`, entity `tel_target_subject` = team or user id, metadata `{scope, period, effective_from,
  kpis:[…]}`, ids and keys only.
- Response: `{scope, team, user, period, effective_from, values}`.

### `GET /telecaller/targets` → `TelTargetPage {items,total,limit,offset}` (history)
Manager/super_admin only (403 otherwise). Filters: `scope`, `team`, `user_id`, `period`, `kpi`. A manager sees every team row plus the
user rows of their direct reports (a `user_id` outside scope → 404). Ordered `effective_from DESC, period, kpi, id`. Item: `{id, scope,
team, user:{id,full_name}|null, period, kpi, value, effective_from, set_by:{id,full_name}, updated_at}`.

### `GET /telecaller/targets/effective?user_id=&team=&date=` → `TelTargetEffectiveOut`
- `date` defaults to today (IST). Past and future dates are allowed (a manager checks what applies next month).
- Telecaller: their own targets only. `team` → 403; a `user_id` that isn't theirs → 403 (backlog tel-021 negative scenario).
- Manager/super_admin: exactly one of `user_id` (in scope, else 404) or `team` (team defaults only, `source` ∈ {team, null}); otherwise 422.
- Any other role → 403.
- Response: `{date, month, team, user:{id,full_name}|null, daily:[{kpi,value,source}×6], monthly:[…×6]}` in §2 order.

## 6. Web

- `lib/telecallerTargets.ts`: types, `KPIS` (key + label), `TARGETS_URL`, a source label (`Override` / `Team default` / `Not set`) and
  `earliestFrom(period, today)` for the date input's `min`/default.
- **`/telecaller/manager/targets`** (new, through `TelecallerCataloguePage`'s shell, eyebrow "Settings"), with a "Targets" item in
  `TELECALLER_MANAGER_NAV`. `TelecallerTargetsPanel` (client):
  1. **Set for:** IT team default · Overseas team default · a telecaller (a select of the manager's team list, `/telecaller/manager/team`,
     paged through like `activeProducts`).
  2. **In effect** table: KPI | Today (daily) | This month (monthly), each with its source. Telecaller targets show the source.
  3. **Form:** a period (Daily / Monthly) radio, the effective date (daily: `type=date` with `min` = tomorrow IST; monthly: a select
     of the next 12 months, each sent as its 1st, because `type=month` is unsupported in Safari and Firefox desktop), and 6 integer
     inputs, `min=0 max=100000`. A blank input leaves that KPI unchanged. For a
     telecaller, each KPI also gets a "Use team default" checkbox, which sends `null`. Save is disabled while nothing is entered or while a
     save is in flight. The API's 422 message is shown in an alert; success shows a status message and refreshes both tables.
  4. **History** table (paged, 50 a page, Previous/Next) for the selected subject: Starts, Period, KPI, Target, Set by.
  Loading, empty ("No targets set yet") and error states use the existing `muted`/`role=status`/`role=alert` idioms.
- **`/telecaller/dashboard`:** `TelecallerTargetsCard` (server) reads `/telecaller/targets/effective` and shows a 3-column table (KPI ·
  Today · This month) with "Not set" for nulls and a note that achieved figures arrive later. If the fetch fails, the card shows "Targets
  are unavailable right now" and the rest of the page still renders.

## 7. Acceptance criteria (testable)

| # | Criterion | Test |
|---|---|---|
| AC1 | The override beats the team default | API: team 80, user 90 → effective 90 `user`; another telecaller → 80 `team` |
| AC2 | A change applies from its effective date only | API: save for tomorrow → today unchanged; the `date=tomorrow` read shows the new value |
| AC3 | Past days keep their old target | API: insert a past-dated row directly, save a new future value → the past date still resolves to the old value; a past `effective_from` POST → 422 |
| AC4 | A negative value → 422 | API |
| AC5 | A telecaller POST → 403; a telecaller reading another user → 403; a manager writing/reading a non-report → 404 | API |
| AC6 | Monthly targets start on the 1st of next month or later | API 422 cases + happy path |
| AC7 | Removing an override falls back to the team default from its date | API |
| AC8 | Re-saving a pending date replaces the value (one row) and is audited | API |
| AC9 | The manager page sets team and telecaller targets; the telecaller dashboard shows "My targets" | vitest + Playwright + Browser Use |

## 8. Security

Role checks first, then scope checks (an out-of-scope id → 404), then the write. There is no IDOR: `user_id` is always checked against
`reporting_manager_user_id`. Pydantic bounds every input, with `extra=forbid`. All SQL goes through SQLAlchemy and is parameterised. The
audit log carries ids and keys only, and nothing sensitive is logged. Rate limiting follows the existing global middleware (no change).
CSRF follows the existing cookie/session setup unchanged.

## 8a. Phase 3 review notes

- **API:** POST is an idempotent upsert keyed by (subject, period, kpi, effective_from), so it returns 200, not 201. GET routes take
  query parameters only. Errors are one-sentence 422s (the tel-001 `_parse` idiom); 403 means a role is refused and 404 means a subject is
  outside the caller's scope. Every write is one transaction committed by the route.
- **Frontend:** existing `form-grid`, `data-table` and `button` classes; a label on every input; a `fieldset`/`legend` around the radios;
  `role=status` and `role=alert` messages; the table scrolls horizontally on mobile (the `table-wrap` idiom); Save is disabled while in
  flight, which prevents a double submit.
- **Security:** no new auth surface. `user_id` is scope-checked (no IDOR), and roles are checked inline, so a telecaller can't escalate
  to a writer. Inputs are bounded, nothing sensitive is logged, React escapes all output (no `dangerouslySetInnerHTML`), and there is no
  raw SQL with interpolation.

## 9. Regression risk

The change is additive: a new table, routes, pages and a nav item. The shared files touched are `models.py`, `schemas.py`, `main.py`,
`navigation.ts` (one array item) and the dashboard page (one card). The navigation test that snapshots `TELECALLER_MANAGER_NAV` must be
updated.

## 10. Browser QA log (Phase 5, Edge via CDP, stack `tel022` web :3092 / api :8092, 2026-10-06)

Accounts: QA Manager One (reports: Asha IT, Bala Overseas), QA Manager Two (report: Chitra IT), all created through the admin API.

Verified with no defect: an IT team-default save (Calls 75, Follow-ups 20 from tomorrow) shows "Saved 2 targets", moves focus to the
message and adds history rows. The telecaller picker lists only direct reports (Chitra is absent for Manager One). Override saves Calls
90 and "Use team default" for Follow-ups (stored as NULL, history shows "Team default"). Monthly saves default to the 1st of next month.
The browser refuses negative, decimal and over-cap values; the API refuses a past date with its sentence and the entry is kept. A double
click sends one POST. The telecaller dashboard shows "My targets" (today "Not set", because the override starts tomorrow). A telecaller
opening `/telecaller/manager/targets` gets "Telecaller manager role required". Signed out, the page redirects (307) to `/admin/login` and
the API returns 401. Mobile (390px) and tablet (820px) have no horizontal scroll. No console errors, no failed requests.

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA-01 | Medium | Manager `/telecaller/manager/targets`; telecaller dashboard | Open either page | Tables use the portal's table style (headers, row lines, left-aligned) | "Targets in effect", "History" and "My targets" render as bare, centre-aligned tables (no `table` class) | Fixed |
| QA-02 | Medium | Manager Targets | Save Calls 75 for tomorrow, then look at "Targets in effect" | The manager can check what applies on the date a change starts | The table only shows today ("Not set"); there is no way to see a scheduled value except in the history | Fixed: an "In effect on" date picker (the API already takes `date`) |
| QA-04 | Low | Manager Targets | Clear "Starts on" (or leave a partial date) and save | A plain sentence | Raw Pydantic text "Starts: Input should be a valid date or datetime, input is too short" | Fixed: the browser asks "Choose a start date." |
| QA-05 | Low | Manager Targets | Choose "Overseas team default", refresh | The same subject stays chosen (Products/Campaigns keep their place in the URL) | Resets to "IT team default" | Fixed: `?for=it\|overseas\|<telecaller id>` |
| QA-06 | Low | Manager Targets, 390px | Tap "Use team default" | A 44px touch target (portal mobile rule) | An 18px checkbox row | Fixed |

QA-03 (withdrawn, by design): "Use team default" is offered even when no override is in effect, because it is also how a manager
ends a *scheduled* future override.

Re-verified after the fixes (Edge, same stack): the restored `?for=<id>` names the telecaller, "In effect on 10 Nov 2026" shows Calls 90
(Override), Follow-ups 20 (Team default) and November's 1800 / 50, a blank start date shows "Choose a start date.", and the checkbox rows are 44px at 390px
with no page side-scroll. There are no console errors, and the tel-001/002/017/022 Playwright specs pass (8/8).
