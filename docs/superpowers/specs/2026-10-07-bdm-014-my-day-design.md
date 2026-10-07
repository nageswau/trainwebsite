# bdm-014 — My Day + type-specific BDM dashboard (design)

- **Feature:** bdm-014 (`docs/delivery/BDM_CRM_BACKLOG.md` §bdm-014; tiles in Appendix B.2 T-C*, T-A*, T-S*, T-K*)
- **Decision:** `DEC-SCOPE-097` (drafted as `096`; renumbered on merging `main`, where tel-010 took `096`)
- **Dependencies (merged on `main`):** bdm-006 (PR #58), bdm-008 (PR #71), bdm-010 (PR #53), bdm-011 (PR #89). Tiles that
  read bdm-005 (MoUs), bdm-009 (activities) and bdm-017 (lead attribution) are all on `main`, so they are live.
- **Migration:** none. **Status:** K1–K12 are agent-recommended defaults pending owner confirmation (the owner asked the session to
  proceed on recommended answers).

## 1. Intent

`/bdm/my-day` is the BDM's landing page. Today it is a shell from bdm-001 (B2). It becomes:

1. **Common section (§15):** today's appointments (time + organization), upcoming travel (date, route, linked-appointment count),
   follow-ups due today or overdue, grouped by organization type (MoU-sourced ones in their own group).
2. **"Today's overview" (§A):** the BDM type's exact eight tiles, each computed from the BDM's own records. A tile with no data
   source says "Not tracked yet" and never shows 0.

Read-only: nothing is written, audited or logged.

## 2. Out of scope

Monthly KPIs and targets (bdm-016); the manager dashboard (bdm-023); the daily report (bdm-015); creating MoU follow-ups (no
feature writes `source = 'mou'` yet); agent onboarding (bdm-019).

## 3. Decisions (K-rows, recommended defaults)

| ID | Question | Decision |
|---|---|---|
| K1 | Endpoint and roles | `GET /api/v1/bdm/my-day`, `bdm` only through `bdm_context` (other roles `403` "BDM role required"; no profile `403`). Managers have their own dashboard (bdm-023), so there is no `bdm_user_id`. |
| K2 | Where tile labels live | In the API response (`key`, `label`, `tracked`, `value`, `note`, the `SchoolKpi` shape), so the page and the definitions can't drift (bdm-021's pattern). |
| K3 | Organization type in "agent / school / college organizations" | The literal `org_type` (`agent`, `school`, `college`). A `university` organization is not a "college organization" for T-K1. |
| K4 | Seminar types | T-S8 and T-K5 also count the common type `seminar_workshop` (it is a seminar or workshop; bdm-013 K5 counts it too). |
| K5 | T-A6 Agents awaiting onboarding | **Not tracked.** Onboarding requests are School-only (`kind IN ('school')`); agent onboarding is bdm-019. |
| K6 | T-K7 MoU follow-ups | **Not tracked.** `source = 'mou'` is reserved but no feature creates such follow-ups yet, so a count would always be a fake 0. T-C03 still shows an "MoU" group whenever one exists. |
| K7 | Archived organizations | MoU-state tiles (T-A5, T-S6, T-S7) leave archived organizations out (they are no longer worked). Appointment, task and activity tiles count the BDM's records as defined; archiving already cancels open items. T-A4 counts organizations created today whatever happened next. |
| K8 | List sizes | Today's appointments: up to 50 (with `truncated`); the count is exact. Upcoming trips: the next 5 by date with an exact `total`. |
| K9 | "Today" | The database clock in IST (`db_now` → `today_ist`), the same as bdm-008 and bdm-013. |
| K10 | Manager visiting `/bdm/my-day` | The page redirects a `bdm_manager` to `/bdm/manager/dashboard` (backlog negative scenario). Any other role keeps the existing "Access unavailable" card. |
| K11 | The bdm-001 profile card | Replaced by a one-line summary under the heading ("Employee ID · territory · View profile"); the full card stays on `/bdm/profile`. |
| K12 | Query count | Fixed: profile gate, clock, one tile SELECT (scalar subqueries), today's appointments, upcoming trips with a correlated appointment count, follow-up groups — six statements whatever the data volume. |

## 4. Tile definitions (Appendix B.2, as implemented)

All "today" (IST), own records. "Open follow-up" = `bdm_tasks` with `kind = 'follow_up'`, `status = 'open'`.

| Tile | Query |
|---|---|
| T-C01 / T-A1 | appointments, `bdm_user_id` = me, status ≠ cancelled, `starts_at` in today |
| T-C02 | trips, me, `travel_date` > today, travel status ≠ cancelled, approval ≠ rejected; each with its non-cancelled linked appointments |
| T-C03 | open follow-ups, me, `due_on` ≤ today; grouped `mou` if `source = 'mou'`, else the organization's `org_type`, else `none` |
| T-A2 | T-C01 with type `agent_meeting` or `agent_visit` |
| T-A3 | distinct `agent` organizations with an open follow-up due ≤ today |
| T-A4 | organizations assigned to me, `org_type = 'agent'`, created today |
| T-A5 | non-archived `agent` organizations assigned to me whose current MoU is `proposal_sent`, `under_negotiation` or `draft_shared` |
| T-A6 | not tracked (K5) |
| T-A7 | open tasks (`kind = 'task'`) on `agent` organizations due ≤ today |
| T-A8 | trips (not cancelled / rejected) with `travel_date` ≤ tomorrow and `return_date` ≥ today |
| T-S1 | T-C01 at `school` organizations |
| T-S2 / T-S3 | T-C01 of type `principal_meeting` / `management_meeting` |
| T-S4 | open follow-ups due ≤ today |
| T-S5 | activities with channel `visit` occurring today |
| T-S6 | non-archived `school` organizations assigned to me whose current MoU is `proposal_sent` |
| T-S7 | the same, current MoU in `discussion_started`, `proposal_sent`, `under_negotiation`, `draft_shared` |
| T-S8 | T-C01 of type `seminar`, `workshop`, `seminar_workshop`, `parent_orientation`, `teacher_orientation`, `career_guidance_presentation`, `psychometric_presentation`, `profile_building_presentation` |
| T-K1 | T-C01 at `college` organizations |
| T-K2 / T-K3 / T-K4 / T-K6 | T-C01 of type `placement_cell_meeting` / `principal_meeting` or `hod_meeting` / `course_promotion` / `internship_discussion` |
| T-K5 | T-C01 of type `student_seminar`, `workshop` or `seminar_workshop` |
| T-K7 | not tracked (K6) |
| T-K8 | `enquiries` with `bdm_user_id` = me created today |

## 5. API

`GET /api/v1/bdm/my-day` → `200`

```
{ today, bdm_type,
  appointments: { count, truncated, items: [{id, code, starts_at, duration_minutes, appointment_type, status,
                                              organization: {id, code, name, org_type, archived}}] },
  trips: { total, items: [{id, code, travel_date, return_date, from_place, to_place, approval_status, travel_status, appointment_count}] },
  follow_ups: { total, groups: [{key, count}] },          // key: an org_type, "mou" or "none"; only non-empty groups
  tiles: [{key, label, tracked, value, note}] }          // exactly the type's eight, in source order; value null when not tracked
```

Implementation: `app/api/bdm_my_day.py` (route, all queries; read-only like `bdm_calendar.py`) and `BdmMyDayOut` in `schemas.py`.

## 6. Web

- `app/bdm/my-day/page.tsx` (server component): `/bdm/me` is the gate (as today); a `403` for a `bdm_manager` session redirects to
  the manager dashboard (K10). The my-day read failing after the gate shows an inline "Unable to load your day" with "Try again".
- `components/BdmMyDay.tsx` (presentational, no client state): three cards (Today's appointments, Upcoming travel, Follow-ups) and
  the "Today's overview" tile grid reusing the `kpi-grid` / `kpi-tile` styles and the "Not tracked yet" badge of `SchoolKpiBoard`.
  Empty states with calls to action: "Book an appointment" (`/bdm/appointments/new`), "Plan a trip" (`/bdm/travel/new`), "View
  follow-ups" (`/bdm/follow-ups`). Items link to the appointment and the trip.
- `lib/bdmMyDay.ts`: types, `MY_DAY_URL`, `isMyDay` guard, the follow-up group label, the "N appointments scheduled" text.
- `loading.tsx` like the calendar's.

## 7. Security

Own scope only, from the session (no id parameter, so no IDOR surface). Read-only GET; no CSRF exposure. No PII beyond what the
BDM's own pages already show (organization names, appointment codes). React escapes every string.

## 8. Testing

- API (`tests/test_bdm_014_my_day.py`): the §15 example (3 appointments, 2 upcoming trips with counts, follow-ups 4/2/1-style
  groups); each type's exact tile key list; not-tracked tiles have `value: null`; every tile's inclusion/exclusion rules (cancelled,
  other BDM, other type, archived, yesterday/tomorrow); roles (manager/other 403, no profile 403); empty BDM; query count equal
  for a small and a larger data set.
- Web (vitest): page renders the sections; manager redirect; inline error; component empty states and "Not tracked yet".
- Playwright `tests/e2e/bdm-014-my-day.spec.ts`: a College BDM with seeded data sees the sections; phone width has no overflow.
