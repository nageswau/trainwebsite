# upc-018 — Student opportunity funnel + university performance — design

- **Feature:** upc-018 (`docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-018; Appendix B F1–F9; EVID-020 §17 L581–L619 and
  §18 L621–L637)
- **Decision:** `DEC-SCOPE-152`. **No migration.** API §12BT; RBAC §2.78. These numbers are provisional until merge, as with earlier items.
- **Branch:** `feature/upc-018` from `origin/main` @ `365fdd97`.
- **Dependencies:** upc-003 (University Master, scope) and upc-017 (course master) are both merged. upc-019 (commission ledger) is **not
  built**, so F10/F11 (Commission Expected / Received) are not in this item. upc-019 adds them behind `strip_commission`.
- **Evidence:**
  - EVID-020 §17/§18 (`DERIVED_BLUEPRINT`). The numbers in the source (45, 20, 12 … / 120, 75, 40 …) are illustrative.
  - Backlog U8 (`EXPLICIT_APPROVAL`): computed from existing FKs only, and Leads / Counselling / Eligible are "not tracked".
  - U2 / U4: commission is restricted.
  - Appendix B F1–F11.
- **Status of answers:** the owner told this session to proceed with the recommended answers. PF1–PF10 below are those recommendations.
  They are `NEEDS_CONFIRMATION` at sign-off, not `EXPLICIT_APPROVAL`.

## 1. Understanding

**Student Opportunities** shows the funnel for a period across every university in the caller's scope (§17). It can be narrowed to
one university to reproduce the source's "ABC University" example.

**University Performance** ranks the same universities by enrolments (§18), with the per-step counts.

Each university's page gets a **Student opportunities** card with this month's funnel. Every figure is a count computed live from
existing tables. Nothing is stored, and no student is named.

## 2. Recommendations (PF1–PF10)

| # | Question | Recommended answer (used) |
|---|---|---|
| PF1 | Period | `from` / `to` as `YYYY-MM-DD`, inclusive IST days, half-open instants `[from 00:00 IST, to+1 00:00 IST)`. Default: the 1st of the current IST month to today (IST). `from > to` → 422. A span over 366 days → 422. |
| PF2 | Step catalogue (source order) | `leads` (F1, not tracked), `counselling` (F2, not tracked), `interested` (F3), `eligible` (F4, not tracked), `applications` (F5), `offers` (F6), `deposits` (F7), `visas` (F8), `enrolled` (F9). A not-tracked step returns `null` and is shown as "Not tracked". |
| PF3 | Counting: a step counts in the period in which it was **reached** (Appendix B is event-based) | **F3:** distinct agency students with a shortlist entry for the university created in the period. **F5:** applications created in the period, except those withdrawn before submission (`status = withdrawn AND submitted_on IS NULL`). **F6:** applications whose offer was reached in the period. The time is `offer_date` when recorded (AGN-010), else the first status-history entry into an offer-or-later status (`OFFER_COUNTED_STATUSES`). **F7:** deposits with `paid_at` in the period (a later remittance or refund does not un-count it). **F8:** distinct applications with a visa case `decision = approved` and `decided_at` in the period. **F9:** applications now `enrolled`, timed by their first status-history entry into `enrolled`, else `enrollment_confirmed_at`. All owners count: agency, student self-service and School-bridged. |
| PF4 | Withdrawn applications (edge case) | Counted at every step they reached before withdrawal, and never at a later step (an application withdrawn after its offer stays in Offers, the O5 idiom). |
| PF5 | Readers | The University Master readers: `partnership_manager` (with a profile), `partnership_head`, `overseas_admin` (overseas division) and `super_admin`. Every other role → 403 "University performance access required" (BDM → 403 is the backlog's negative scenario). The counselor's slice (U14) is the upc-030 360 view and is not opened here. |
| PF6 | Scope of the lists (Appendix B) | Manager: universities where they are primary or backup. Head: their team's and unowned universities. `super_admin` / `overseas_admin`: all. The per-university read follows the University Master's read rule (every reader reads every university, upc-003), and an unknown id → 404. |
| PF7 | Which universities are ranked | Active (non-deactivated) universities in scope that are partners (stage group G1) **or** have any counted step in the period. Order: enrolled ↓, applications ↓, name, id. Paged `{items, total, limit, offset}` (limit 1–100, default 25). `totals` = Σ over every ranked row, not just the page. |
| PF8 | Totals across universities | The sum of per-university figures. F3 can count one student under two universities, so the label says "per university". |
| PF9 | Commission (F10/F11) | Not in this item. No commission field is returned by these endpoints. upc-019 adds them for the U2 roles through `strip_commission`. |
| PF10 | Privacy | Counts only. No student id, name or application reference in any response, log or audit. Reads are not audited (as with the other partnership dashboards). |

## 3. Data

No schema change. Every figure is read from `overseas_applications`, `application_status_history`, `application_deposits`, `visa_cases`
and `agent_student_shortlist_entries`, joined to `universities`.

## 4. API (`app/api/partnership_performance.py`)

| Method | Path | Who | Result |
|---|---|---|---|
| GET | `/partnership/performance?from=&to=&limit=&offset=` | PF5 readers, PF6 scope | `UniversityPerformancePage` `{from, to, steps:[{key,label,tracked}], totals:{step:int\|null}, items:[{rank, university{id,university_code,name,country,stage_label,partner}, counts{step:int\|null}}], total, limit, offset}` |
| GET | `/partnership/universities/{id}/performance?from=&to=` | PF5 readers | `UniversityPerformance` `{from, to, steps, university{…}, counts}`. Unknown id → 404 |

**Errors:**
- Malformed date → 422 (Query pattern).
- `from > to` or a span over 366 days → 422.
- A role without access → 403.
- An unknown university → 404.

**Query count** is constant whatever the data size: the in-scope universities, one grouped query per tracked step (6), and the
current IST date.

## 5. Frontend

- `lib/partnershipPerformance.ts` holds the types, URLs, the `PERFORMANCE_READERS` set, a default period and a period chooser that
  falls back on a malformed URL value with a note.
- `components/PartnershipFunnel.tsx` is data-only and server-rendered. It is an ordered list of the 9 steps with a count and a
  proportional bar (CSS width, no chart dependency). A not-tracked step reads "Not tracked".
- `/partnership/opportunities[?university_id=&from=&to=]` shows the funnel for the scope totals, or for one university when one is chosen.
- `/partnership/performance[?from=&to=&offset=]` shows the ranking table (rank, university link, country, stage, 6 tracked counts) with
  a Total row and a pager.
- On the university page, the "Student opportunities" card shows this month's funnel for readers, with a link to the opportunities page
  for that university.
- The menu: "Student Opportunities" and "University Performance" become `live`. They are also added to the head nav and the super_admin
  nav.
- Empty state: "No student activity for these universities in this period." Errors use `accessUnavailable` / `accessDenied`, as on
  the other pages.

## 6. Acceptance criteria (testable)

1. AC1: Counts equal Appendix B F3/F5–F9 (PF3) in fixtures that include agency, self-service and School-bridged applications.
2. AC2: Leads, Counselling and Profiles eligible are returned as `null` / not tracked and shown as "Not tracked".
3. AC3: The source's ABC example (45 interested → 12 applications → 8 offers → 5 visa approvals → 4 enrolled) is reproduced from
   fixtures.
4. AC4: A withdrawn application counts only at the steps it reached (PF4). A withdrawn-before-submission application is not an
   application.
5. AC5: Events outside the period are not counted, and an IST day boundary is respected.
6. AC6: A BDM, a counselor or a student → 403. An unknown university → 404. A bad period → 422.
7. AC7: Manager / head / super_admin list scope per PF6. The ranking order and totals follow PF7 / PF8.
8. AC8: No commission field and no student identifier in either response.
9. AC9: The query count is constant (it does not grow with universities or applications).
10. AC10: The pages work for manager, head and super_admin at desktop, tablet and mobile widths, with keyboard access, and have
    loading, empty and error states.

## 7. Testing

- Backend:
  - `tests/test_upc_018_funnel.py` covers the metric definitions, the period, withdrawn handling, the ABC example and the query count.
  - `tests/test_upc_018_performance_api.py` covers roles, scope, ranking, totals, 404 / 422 and that no commission or PII is returned.
- Vitest: `PartnershipFunnel.test.tsx` and `PartnershipPerformance*.test.tsx` (page states). Also a stub for the new read in
  `UniversityDetailPage.test.tsx`.
- Playwright: `e2e/upc-018-partnership-performance.spec.ts`.

## 8. Regression risks

- The shared university detail page. Its new section must not add an always-present `role=status` (upc-012 note), and its unit test
  stubs `serverApi`.
- `lib/navigation.ts` menu counts (`PartnershipMenuCard` tests).
- `services/partnership_metrics.py` is shared with upc-021. The new functions are additive and `target_actuals` is untouched.

## 9. Implementation plan (TDD, one slice at a time)

1. `partnership_metrics.funnel_counts(db, university_ids, start, end)`: RED tests F3/F5–F9, PF4, period and ABC, then GREEN.
2. `partnership_metrics.period` parsing plus the `api/partnership_performance.py` routes and schemas: RED role/scope/order/422/404
   tests, then GREEN. Register the router in `main.py`.
3. Web: lib, `PartnershipFunnel`, the two pages, the university card and the nav, with vitest first.
4. Playwright e2e. Docs: DEC-SCOPE-152, API §12BT, RBAC §2.78, SCREEN_CATALOG and the backlog status.
