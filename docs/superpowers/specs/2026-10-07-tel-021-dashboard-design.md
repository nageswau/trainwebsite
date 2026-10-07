# tel-021 — Telecaller dashboard + daily activity (design)

Status: design for `feature/tel-021` (2026-10-07). Decision `DEC-SCOPE-103` (tel-014 holds 102 unmerged), API §12X, RBAC §2.30.
No migration. Source: `docs/delivery/TELECALLER_CRM_BACKLOG.md` tel-021, Appendix B (B1–B10, D1–D13, K1–K6), T5, T24, T27.

## 1. Owner answers (2026-10-07)

- **DB1 (B9 threshold):** tel-020 has no "not contacted" threshold yet. Until it lands, a lead counts as not-contacted overdue when it
  has sat in `first_call_pending` for more than **24 hours** (`stage_changed_at < now − 24h`). tel-020 replaces the constant.
- **DB2 (Q-18 part 1, conversion credit):** a conversion is credited to the lead's telecaller **at the moment conversion was first
  recorded** (the first `lead_stage_history` row to `converted`). A later reassignment does not move it. Per tel-018 HO2, a lead an
  admin has unlinked (no longer `converted`) no longer counts.

Defaults taken without a question (recorded in DEC-SCOPE-103):

- **DB3:** the dashboard tiles are always "today" (IST). The daily activity panel takes `?date=` for any IST day up to today; a
  future day → 422. The backlog's `GET /telecaller/dashboard?date=` is dropped: tiles such as Overdue are "now" figures.
- **DB4:** point-in-time counts (D1, D6, D12) are reconstructed **as of the end of the day** (or now, for today) from history:
  owner from `lead.assign` audit rows, stage from `lead_stage_history`, priority from `lead.priority_change` audit rows, follow-up
  state from its `created_at` / `completed_at` / `cancelled_at`. Rule for each: the last change at or before T gives the "to" value;
  else the first change after T gives the "from" value; else the current value. Leads created after T are excluded.
- **DB5:** "open" = not in a closed stage (`CLOSED`). Tiles B2/B4/B9 also exclude handed-over leads (`owner_id` set), since the
  telecaller no longer works them (T19).
- **DB6:** a manager (`telecaller_manager`: direct reports; `super_admin`: any telecaller) sees a report's daily activity at
  `/telecaller/manager/team/{id}/activity`, linked from the Team table. Out-of-scope user → 404 (tel-022 `telecaller_in_scope`). A
  telecaller naming another user → 403. Division admins are out of scope here (tel-023/024 own T24's admin views).
- **DB7:** B5 / today's appointment list excludes `cancelled` rows. Counselor appointments count by `booked_by_user_id`; BDM
  meetings are my `accepted` requests whose `bdm_appointments.starts_at` is today.
- **DB8:** B1 New Leads = distinct leads that became mine today (a `lead.assign` audit row to me, or a lead I created already
  assigned to myself — `lead.create` with `assigned=true`) and are still mine.

## 2. Metric definitions (implemented in `services/telecaller_metrics.py`)

Flow counts take an instant range `[start, end)` so tel-023 can sum a date range in one query. u = the telecaller.

| Key | Definition |
|---|---|
| D2 calls | `lead_calls.caller_user_id = u`, `occurred_at` in range |
| D3 connected / D4 not_connected | D2 split by `lead_calls.NOT_CONNECTED` (same rule as tel-010 day counts) |
| D5 follow_ups_completed | `lead_follow_ups.completed_by_user_id = u`, `completed_at` in range |
| D8 counselor_appointments | lead appointments `booked_by_user_id = u`, `created_at` in range |
| D9 bdm_appointments | `bdm_meeting_requests.requester_user_id = u`, `created_at` in range |
| D7 new_appointments | D8 + D9 |
| D10 whatsapp_messages | `lead_messages` channel `whatsapp`, `sender_user_id = u`, `sent_at` in range |
| D11 qualified_leads | `lead_stage_history.to_stage = 'qualified'`, `actor_user_id = u`, `created_at` in range |
| D13 converted_leads | leads still `converted` whose first `converted` history row is in range and whose owner at that instant was u (DB2) |
| D1 leads_assigned | leads owned by u at T whose stage at T is open (DB4/DB5) |
| D6 follow_ups_pending | follow-ups open at T, `due_at < end of day`, on leads owned by u at T |
| D12 hot_leads | D1 leads whose priority at T is `hot` |

Tiles (today, now = DB clock): B1 (DB8); B2 `{done: D2, to_do: open own not-handed-over leads in assigned/first_call_pending +
own open follow-ups due today}`; B3 own open follow-ups due today; B4 own open not-handed-over hot leads; B5 (DB7); B6 D3; B7 D4;
B8 D13; B9 own open follow-ups with `due_at < now` + own not-handed-over `first_call_pending` leads older than 24h (DB1);
B10 `{achieved: D2, target: effective daily calls}`.

Target progress: K1–K6 = D2, D3, D11, D5, D8, D13; daily = today, monthly = 1st of month → now; targets from
`telecaller_targets.effective_targets` (tel-022).

## 3. API (§12X)

- `GET /api/v1/telecaller/dashboard` — telecaller only (others 403). `{day, tiles, targets: {daily: [{kpi, achieved, target}],
  monthly: [...]}, appointments: [{kind, id, code, title, scheduled_at, status, lead_id}]}`.
- `GET /api/v1/telecaller/activity?date=&user_id=` — `{day, user: {id, full_name}, counts: {D1..D13 keys}, targets: [{kpi,
  achieved, target}]}` (targets = that day's daily targets). Telecaller: own only (`user_id` other than self → 403). Manager /
  super_admin: `user_id` required (422 if missing), scope per DB6 (404). Other roles 403. Future date → 422.

## 4. Web

- `/telecaller/dashboard`: 10-tile `metric-grid`, existing Today's follow-ups card, a Today's appointments card, the targets card now
  showing `achieved / target` for today and month to date, and the Daily activity panel with a GET date form (`?date=`, no client JS).
  Each fetch fails soft (a note in its card), as tel-022 G4.
- `/telecaller/manager/team/[id]/activity`: the same activity panel for a report; Team table gains an "Activity" link per row.
- Zero activity shows zeros (edge case), never "no data".

## 5. Testing

Backend `tests/test_tel_021_metrics.py` (each definition on fixture data incl. IST boundaries, reassignment, point-in-time, unlinked
conversion) and `tests/test_tel_021_routes.py` (403/404/422, shape). Vitest for the new components; Playwright e2e for the
dashboard and the manager activity page.
