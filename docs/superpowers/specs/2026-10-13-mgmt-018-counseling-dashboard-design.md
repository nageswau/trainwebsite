# mgmt-018 — Counseling dashboard (design)

**Source:** `EVID-017` §13 "COUNSELING" (lines 513–535, `DERIVED_BLUEPRINT`): *Leads → Counseling → Conversion*; KPIs Leads assigned,
Calls, Counseling sessions, Follow-ups, Conversions, Revenue, Conversion %, Counselor-wise performance. Backlog
`MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-018 (depends on mgmt-003, merged). Open question Q-20.

**Authority:** every CS answer below is a **recommended default, `UNVERIFIED`**, taken on the owner's standing instruction to proceed
with recommended answers. CS4/CS6/CS8 answer Q-20. Registered as `DEC-SCOPE-203` (provisional numbering).

## Decisions (CS1–CS12)

| # | Point | Answer |
|---|---|---|
| CS1 | Counselors | Every user with role `counselor`, active or not, one row each, ordered by division then name. A counselor account has one division (`User.division`); figures are credited to the person, never split, so the "counselor in both divisions" edge case cannot double count: division subtotals group by the counselor's division and the grand total is the sum of the rows |
| CS2 | Period | `from` / `to`, inclusive IST dates, default this IST month; start after end or > 366 days → 422 (bdm-024 P2, as mgmt-020 BD2) |
| CS3 | Leads assigned | Distinct leads handed over to the counselor in the period (tel-018 `lead.handover` audit rows naming them) |
| CS4 | Calls | **Not tracked** (`null`): tel-010 calls are logged by telecallers only; counselors have no call log |
| CS5 | Counseling sessions | Completed appointments with the counselor as staff, scheduled in the period — lead (tel-016) and student (overseas flow) appointments alike |
| CS6 | Follow-ups | Follow-up sessions: those CS5 sessions that are not the counselor's first completed session with that lead or student |
| CS7 | Conversions (AC) | The telecaller T5/D13 rule: leads still Converted whose conversion was first recorded in the period, credited to the lead's counselor (`Enquiry.owner_id`; a lead past Application/Enrollment cannot be handed over or returned, so the counselor at conversion is the current one). Same `first conversion` subquery as `telecaller_metrics.conversions_by_user` |
| CS8 | Revenue | Counted rupee payment lines of the management ledger (mgmt-005 `ledger.lines()`, source `payment`) dated in the period and paid by a student linked to one of the counselor's converted leads. Money is **finance tier**: only a partner gets it; super_admin's read has `revenue: null`, `revenue_visible: false` (mgmt-008 RR9 precedent) |
| CS9 | Conversion % | Of the leads handed to the counselor in the period (CS3), the share Converted now with that counselor, one decimal; `null` when none were assigned. Group rows use their summed numerator / denominator |
| CS10 | Shape | `figures` (key, label, definition, tracked) in §13 order, `total`, `divisions` (it, overseas, then any other), `counselors` |
| CS11 | Access | Operational tier (partner, super_admin); accountant 403 "Operational access required"; other roles 403 "Management access required"; signed out 401 |
| CS12 | Nav | Command Center "Counseling" (Students) and "Counselors" (People) entries go live → `/management/counseling` (`#counselors` for People); super admin sidebar "Management counseling figures" |

## Architecture

- `services/management_counseling.py` — `FIGURES`, `dashboard(db, user, start, end, now)`. Grouped queries, one per figure, over the
  counselor id list (fixed query count, not per counselor). Read-only.
- `services/telecaller_metrics.py` — extract the first-conversion subquery into `first_conversions()` so tel-021 and mgmt-018 share one
  T5 definition (behaviour unchanged).
- `api/management.py` — `GET /management/counseling?from&to`, `_operational(user)` then `period()`.
- `schemas.py` — `ManagementCounselingOut` (+ figure / row / group models).
- Web: `lib/managementCounseling.ts`, `components/ManagementCounseling.tsx`, `app/management/counseling/page.tsx` (server-rendered,
  period form as mgmt-020), `lib/management.ts`, `lib/navigation.ts`.

## UI

Period form → note (period, IST, counselor count) → "Leads → Counseling → Conversion" tiles (7 KPIs, Calls "Not tracked", Revenue
"Partners only" for the super admin) → "Counselor-wise performance" table (scrolls on a phone, sticky name column) with division and
all-counselor totals in the footer. Empty state when there are no counselors. 422 message shown; 401/403 → access card.

## Testing

Backend (`test_mgmt_018_counseling.py`): access matrix; period defaults/422; per-counselor exact figures over a fixed past period with
fresh counselors (shared DB); follow-up rule; T5 AC — the counselor's conversions equal the leads `conversions_by_user` counts for the
same range; revenue only for the partner; totals = sum of rows. Web: vitest for lib + component; Playwright e2e for the page.
