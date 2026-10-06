# tel-004 — Pipeline stage engine + stage history (design)

Backlog: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-004 (EVID-019 §19, Appendix A L608–L636; `DEC-SCOPE-073` T5, T13, T25, T29).
Dependency: tel-003 merged (PR #75 @ `10fce82e`); branch `feature/tel-004` from `main` @ `11f4c9c7`.
Decision: `DEC-SCOPE-078` (provisional). Migration: `0079_lead_stage_pipeline` (provisional). tel-012 and tel-022 also claim `0079` /
`DEC-SCOPE-078` on unmerged branches, so whichever merges second re-chains (the tel-003 re-chain idiom).

## 1. Owner answers (2026-10-06, `EXPLICIT_APPROVAL`) and recorded defaults

| # | Question | Answer |
|---|---|---|
| PL1 (Q-02) | Legacy `enquiries.status` mapping | **By meaning.** `new`, `contacted`, `qualified` and `lost` are kept. `converted` with a linked student becomes `application_enrollment`, and `converted` without one becomes `follow_up`. Any other text becomes `new`. The original text goes into `metadata_json.legacy_status`, and each changed lead gets one history row (`event = legacy_mapping`, no actor) |
| PL2 | Assigned vs First Call Pending | **Attempt-based.** Assignment moves `new → assigned`. The first unconnected call attempt moves `new/assigned → first_call_pending`. The first connected call moves `new/assigned/first_call_pending → contacted` |
| PL3 (Q-09) | No Response | **Manual** closed outcome with a reason. An automatic close after N attempts is deferred to tel-010 (it would be one new event) |
| PL4 | bdm-017 admin link | **Through the engine now.** Link (`student_linked`) moves the lead to `application_enrollment` (T29), and Unlink (`student_unlinked`) moves `application_enrollment → follow_up`. No person can choose `converted`; tel-018 computes it with the `converted` event |
| D1 (default) | Reasons | Required (1–500 chars, trimmed) for the 5 closed outcomes and for a reopen. Optional for the other manual moves. Stored only in the history; never in a log or audit row |
| D2 (default) | Manual targets | `qualified`, `interested` and `follow_up` from any open stage before `application_enrollment` (any direction, not the same stage). Closed outcomes from any open stage except `converted` |
| D3 (default) | Closed leads | The only person move is the reopen → `follow_up`, by a manager or an admin. A telecaller gets 403. Any other target gets 422. An event on a closed lead is a no-op (the stage doesn't move; tel-015's timeline shows the underlying record) |
| D4 (default) | Telecaller UI | tel-004 ships the API. The lead-detail stage badge and control for telecallers come with tel-008's workspace (no telecaller lead screen exists yet). The admin lead panel gets the stage control and history now |

## 2. Stage catalogue (`app/lead_stages.py`)

Ordered open stages: `new` New Lead · `assigned` Assigned · `first_call_pending` First Call Pending · `contacted` Contacted · `qualified`
Qualified · `interested` Interested · `follow_up` Follow-up · `counselling_scheduled` Counselling Scheduled · `counselling_completed`
Counselling Completed · `application_enrollment` Application/Enrollment · `converted` Converted.
Closed: `not_interested` Not Interested · `not_eligible` Not Eligible · `wrong_number` Wrong Number · `no_response` No Response · `lost` Lost.

`MANUAL = {qualified, interested, follow_up}`, `CLOSED` = the five above, `REOPEN_TO = follow_up`.

System events (frozen API; callers in tel-007/010/016/018 only fire them):

| Event | From | To | Fired by |
|---|---|---|---|
| `assigned` | `new` | `assigned` | tel-007 |
| `call_unconnected` | `new`, `assigned` | `first_call_pending` | tel-010 |
| `call_connected` | `new`, `assigned`, `first_call_pending` | `contacted` | tel-010 |
| `appointment_booked` | `new` … `follow_up` | `counselling_scheduled` | tel-016 |
| `appointment_completed` | `new` … `counselling_scheduled` | `counselling_completed` | tel-016 |
| `student_linked` | `new` … `counselling_completed` | `application_enrollment` | admin link now; tel-018 |
| `student_unlinked` | `application_enrollment` | `follow_up` | admin unlink now; tel-018 |
| `converted` | `application_enrollment` | `converted` | tel-018 |

Any other from-stage → no move (returns `False`, no history). This makes each automatic transition fire exactly once (AC1): a repeat finds
the lead already past its from-set.

## 3. Data model (migration `0079_lead_stage_pipeline`)

`lead_stage_history`: `id` uuid PK; `lead_id` FK `enquiries.id` ON DELETE RESTRICT; `from_stage` varchar(40) NOT NULL; `to_stage`
varchar(40) NOT NULL; `event` varchar(30) NOT NULL (an event name, `manual`, `reopen` or `legacy_mapping`); `actor_user_id` FK `users.id`
ON DELETE RESTRICT NULL (NULL = system); `reason` varchar(500) NULL; `position` bigint identity (orders rows inside one transaction);
`created_at` timestamptz default now(). Index `(lead_id, position)`. There is no stage CHECK, so history survives a catalogue change
(the bdm-004 idiom).

`enquiries`: CHECK `ck_enquiries_status`: `status IN (16 stages)`. `stage_changed_at` is set on every move.

Upgrade (guarded: skip if the table exists, because 0001's `create_all` builds a fresh database): create the table → PL1 history rows
(INSERT … SELECT) → `metadata_json.legacy_status` + new `status` + `stage_changed_at = now()` for changed rows → the CHECK. The migration
keeps a frozen copy of the stage list, and a test asserts it equals `lead_stages.STAGES`.
Downgrade refuses while any non-`legacy_mapping` history row exists. Otherwise it drops the CHECK, restores `status` from
`legacy_status`, and drops the table.

## 4. Service (`app/services/lead_pipeline.py`) — the only writer of `enquiries.status` after creation

Nothing in it commits; the route owns the transaction.
- `locked_lead(db, lead_id)`: `SELECT … FOR UPDATE` (`populate_existing`), or 404. Concurrent changes serialise on the row.
- `apply_event(db, lead, event, actor=None) -> bool`: the §2 table. On a move it sets `status` and `stage_changed_at`, then adds a history row.
- `person_move(db, lead, actor, kind, to_stage, reason)`: `kind` ∈ `telecaller` / `manager` (manager, super_admin on the telecaller route,
  and every admin on the admin route). Order of checks: unknown stage → 422; same stage → 422; lead closed → telecaller 403, target
  ≠ `follow_up` 422, reason missing 422, else reopen; target not manual/closed (system stage, `converted`) → 422; closed target on
  `converted` or manual target at/after `application_enrollment` → 422; closed target or reopen without a reason → 422.
- `history_page(db, lead_id, limit, offset)`: oldest first (`position`), with the actor `{id, full_name}` or null (System) and labels.
- `telecaller_scope(user)`: SQL filters. Telecaller → `telecaller_user_id = me`. Manager → telecaller is a direct report, or unassigned
  in a team of their direct reports (T23). super_admin → all. Other roles → 403. Out of scope → 404 (same as missing).
- Log `lead_stage_changed` with ids, stages and the event only.

## 5. API (`API_CONTRACT.md` §12G)

- `POST /telecaller/leads/{id}/stage` `{to_stage, reason?}` (extra keys → 422) → `{id, status, status_label, stage_changed_at}`.
- `GET /telecaller/leads/{id}/stage-history?limit&offset` → `{items, total, limit, offset}`.
- `PATCH /admin/leads/{id}`: `status` now runs through `person_move` as an admin (`reason` accepted). A `status` equal to the current
  stage is a no-op (back-compat for clients that resend it with `owner_id`). `owner_id` is unchanged. Response
  still `{ok: true}`. The audit metadata no longer copies the raw payload: it holds `status` / `owner_id` only, never `reason`.
- `GET /admin/leads/{id}/stage-history`: the same division scope as the other admin lead routes (404 / 403).
- `POST /admin/leads/{id}/conversion` fires `student_linked` instead of setting `converted`; `DELETE` fires `student_unlinked`.
- Admin lead rows add `status_label`.

## 6. Frontend

- `lib/leadStages.ts`: keys, labels, `isClosed`, `personTargets(current, canReopen)` (mirrors §4; the API stays authoritative).
- `AdminLeadFilters`: the Stage filter lists the 16 stages by label.
- `AdminLeadManagementPanel`: the Status column shows the stage label. The bare status `<select>` becomes "Change stage". It opens an inline
  form with only the valid targets (reopen → "Reopen to Follow-up" on a closed lead), plus a reason box that is required for closed outcomes
  and reopen, Save, and Cancel. Server errors show inline, and success updates the row. A "History" toggle lists the changes: from → to, by
  whom (or System), when, and the reason.

## 7. Acceptance criteria (testable)

1. AC1: each event moves only from its from-set, once; a repeat is a no-op with no history.
2. AC2: a telecaller choosing `counselling_completed`, `application_enrollment` or `converted` → 422.
3. AC3: a closed outcome without a reason → 422.
4. AC4: only a manager or an admin reopens. A telecaller reopening gets 403. Reopen lands on `follow_up`.
5. AC5: the history lists every change in order, with actor (or System) and reason.
6. Admin PATCH accepts only valid transitions. bdm-017's link and unlink move the stage per PL4.
7. The migration maps the legacy values per PL1. The CHECK refuses any value outside the stage list. Downgrade refuses after real moves.

## 8. Security

AuthZ is per route: the telecaller roles plus SQL scope (out-of-scope → 404), and the admin division scope. A telecaller can't reopen
(403). Nobody can choose `converted`. Pydantic forbids extra keys, so a client can't send `actor` or `event`. Reasons are stored as
text, React escapes them, and they are never logged or audited. ORM-bound queries only. Row lock against races.

## 9. Regression risk

High: the admin status editor (`test_adm_002`, `AdminLeadManagementPanel.test`), bdm-017 conversion (`test_bdm_017_conversion`,
`bdm-017` e2e), seed/fixture status values, counselor My Leads and the dashboard "new" counts (unchanged keys), and RPT-001.

## 10. Browser QA (2026-10-06, isolated stack `tel004` web :3074 / API :8074, Edge via CDP :9374 + Playwright)

Independent pass as `it_admin`, `overseas_admin`, `counselor` and signed out, at 1280 / 820 / 390 / 320 px.

| ID | Severity | Page | Finding | Fix |
|---|---|---|---|---|
| QA-01 | Minor (a11y) | Admin lead panel | After Save or Cancel the stage form unmounted and keyboard focus fell to `<body>` | Focus returns to "Change stage" (`AdminLeadStage.tsx`); vitest asserts it after Save and after Cancel |
| QA-02 | Minor | Admin "Leads" workspace table; counselor My Leads / dashboard | Raw stage keys (`follow_up`, `first_call_pending`) under a "Status" header | `services/portal.py` shows the label under "Stage"; `test_tel_004_portal_stages.py` |
| QA-03 | Minor (mobile) | Admin lead panel ≤ 390 px | The sticky Name column covered the left of the stage form (390 px: 47 px; 320 px: Save hidden) | Form min-width 12rem → 9rem (fits at 390); below 360 px the panel's Name column is not sticky (`globals.css`). Re-measured: form clear at 390 / 320 / 820, no page overflow |

Passed with no finding: only valid targets offered (no system stages, no Converted); "Choose a stage." and reason-required messages before
any request; Cancel; double-click Save (one history row); offline Save ("The request did not complete…", reason kept) then online retry;
reopen to Follow-up with a reason; history order with actor and reason; refresh keeps the stage; overseas admin → IT lead history and
PATCH 403; counselor → telecaller stage API 403, and the admin page shows "Access unavailable"; signed out → API 401 and redirect to
login; no console errors; no page overflow at any width.
