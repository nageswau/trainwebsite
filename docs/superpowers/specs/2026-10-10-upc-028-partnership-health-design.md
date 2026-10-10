# upc-028 — Partnership health score — design

- **Feature:** `upc-028` (`UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-028; Appendix B "Health score"; EVID-020 §30 L970–L1002).
- **Evidence:** EVID-020 §30 (`DERIVED_BLUEPRINT`; "92/100 – Excellent" and "48/100 – Needs Attention" are illustrative); backlog §3.1 **U2**
  (commission restricted) and **U8** (funnel from existing FKs), both `EXPLICIT_APPROVAL`; §3.2 **Q-24** (`NEEDS_CONFIRMATION`); Appendix B
  F5/F6/F8/F9 (upc-018), F10/F11 + CL1–CL8 (upc-019), D7 meetings (upc-009/021), AG4 effective agreement status (upc-014).
- **Dependencies:** upc-009, upc-013, upc-014, upc-018 and upc-019 are all merged on `main`.
- **Decision:** `DEC-SCOPE-170`. **No migration.** **API:** §12CL. **RBAC:** §2.96. The numbers are provisional until merge, as with
  earlier items.
- **Status:** HS1–HS12 below are recommended answers, applied under the owner's standing instruction for the build session ("proceed
  with the recommended answers; ask only if genuinely blocking"). They are **not** separately confirmed: `NEEDS_CONFIRMATION` at sign-off.

## 1. Understanding

Every active partner gets a 0–100 score and a band. The purpose is to help management spot partnerships that are becoming inactive
(§30 L1002). The score is computed when it is read. Nothing is stored. It appears in the two upc-018 performance responses
(backlog: "API impact: in the performance responses"), as a badge on the University Performance ranking, and as a badge with a
breakdown on the university page.

## 2. Decisions (recommended answers)

| # | Question | Answer |
|---|---|---|
| HS1 | Which universities are scored | Active (not deactivated) universities whose stage is in group G1 (Partner Activated or later) and that are not lost: the upc-018 `partner` flag. Any other university gets `health: null` |
| HS2 | As of when | **Today (IST)**, using trailing windows. The score ignores the page's `from`/`to`, because a health score describes the partnership now, not a past period. The response carries `as_of` |
| HS3 | Factors, weights (Σ 100), normalised 0–1 (Q-24) | **Applications** 15: F5 in the last 365 days ÷ 20, capped at 1. **Offers** 10: F6 ÷ F5 over the same 365 days, capped at 1 (no applications = no data). **Visa success** 10: visa cases approved ÷ (approved + refused) decided in the 365 days (withdrawn is excluded; no decisions = no data). **Enrolments** 15: F9 in the 365 days ÷ 10, capped at 1. **Commission** 10: the collection rate, all time, i.e. the mean over currencies of min(received ÷ expected, 1), using upc-019 Expected (counted rows) and receipts with no FX (no expected = no data). **Response time** 10: see HS4. **Meeting frequency** 15: meetings completed in the last 90 days ÷ 3, capped at 1. **Agreement status** 15: the best effective status (AG4) among the university's agreements: active or signed (not expiring) = 1, expiring = 0.5, anything else or none = 0. **Student satisfaction**: not tracked (Q-24). It is excluded, has weight 0 and is listed as "Not tracked" |
| HS4 | "Response time" (Q-24) | Covers every WhatsApp or email to the university sent in the last 90 days, except failed emails (the upc-012 rule). Each message's wait runs until the contact's next logged interaction after it was sent: an incoming call, a connected outgoing call, or a completed meeting. A message with no reply waits until now. The factor is the **median** wait in days: ≤ 2 days = 1, ≥ 14 days = 0, linear in between. No messages = no data |
| HS5 | A factor with no data | It is left out, and its weight is shared out across the factors that have data. This way a missing ratio is neither rewarded nor punished. A count of zero (no applications, no meetings, no agreement) **is** data and scores 0 |
| HS6 | Score and the "breakdown sums to the score" (AC) | score = round(Σ weightᵢ × valueᵢ ÷ Σ weightᵢ with data × 100). Each factor's **points** are its share of that, rounded by the largest-remainder method, so the points always add up to the score exactly |
| HS7 | Bands (Q-24, Appendix B) | **Excellent** ≥ 80, **Good** 60–79, **Needs attention** < 60. The source's 92 and 48 fall into Excellent and Needs attention |
| HS8 | "Insufficient data" (backlog edge case: a new partner with no data) | When there is no evidence in any factor: no application, offer, visa decision or enrolment in the 365 days; no completed meeting and no message in the 90 days; no agreement that is or was in force (stored `signed`, `active` or `renewed`); and no expected commission. The score is then `null` and the band is `insufficient_data` ("Insufficient data"). A long-standing partner that has gone quiet still has its agreement on record, so it scores low instead, which is the point of §30 |
| HS9 | Who sees what (U2; backlog: "the commission factor must not be reverse-engineerable by other roles") | The performance readers (PF5) see the score and the band. **Only the commission roles** (`can_see_commission`: super_admin, partnership_manager, partnership_head) get `factors`, the breakdown. For everyone else (overseas_admin) the key is left out entirely (`response_model_exclude_unset`, the CL13 idiom). The score stays a single rounded integer |
| HS10 | Cost | The list scores only the partner rows on the **current page** (≤ 100). This uses a constant number of grouped queries, whatever the number of universities. The Total row has no health |
| HS11 | Privacy / audit | Counts and ratios only: no student, contact or message content in the response. Reads are not audited, as with the other partnership dashboards. Nothing is logged per read |
| HS12 | Ranking | The upc-018 ranking order (PF7) is unchanged. Health is an extra column, not a sort key |

## 3. API (§12CL) — additive

Both `GET /partnership/performance` (on each `items[]` row) and `GET /partnership/universities/{id}/performance` gain:

```
health: null | {
  as_of: "YYYY-MM-DD",
  score: int | null,                        // null when insufficient_data
  band: "excellent" | "good" | "needs_attention" | "insufficient_data",
  band_label: "Excellent" | "Good" | "Needs attention" | "Insufficient data",
  factors?: [                               // commission roles only (HS9); in a fixed order, satisfaction last
    {key, label, tracked: bool, has_data: bool, measure: str | null, weight: int, points: int | null}
  ]
}
```

`weight` is the configured weight (HS3). `points` is null when the factor is not tracked or has no data. When the score is not null,
Σ points = score. Nothing else in either response changes. Errors are unchanged (401, 403, 404, 422).

## 4. Backend

- `services/partnership_metrics.py` gains `HEALTH_FACTORS` (key, label, weight), `BANDS`, `band(score)`, a pure
  `score(values: dict[str, float | None]) -> (score, points)` that does the HS5/HS6 maths, and `async health(db, university_ids, today)
  -> dict[UUID, dict]`, which batches the reads. It reuses `funnel_counts` (365 days), `university_commission.expected_rows` /
  `received_sums`, and `university_agreements.effective_status`.
- `api/partnership_performance.py` attaches `health` to the page's partner rows (and to the single university when it is a partner),
  and drops `factors` for non-commission roles.
- `schemas.py`: `PerformanceHealthFactor` and `PerformanceHealth`. `health: PerformanceHealth | None = None` on
  `UniversityPerformanceRow` and `UniversityPerformance`. `factors: list[...] | None = None`, so it disappears when unset.

## 5. Frontend

- `lib/partnershipPerformance.ts`: the `PerformanceHealth` type and `healthText(h)` ("92/100 · Excellent", "Insufficient data").
- `components/PartnershipHealth.tsx` (data only, server-rendered) has two parts. `HealthBadge` uses the existing `.status` (Excellent),
  `.badge` (Good), `.status.error` (Needs attention) and a muted badge (Insufficient data). `HealthBreakdown` is a table with Factor,
  Measure, Weight and Points columns and a Total row. It is shown only when `factors` is present.
- University Performance: a "Health" column (badge, or "—" for a non-partner). Its footnote explains "health is as of today".
- University page: a "Partnership health" card for performance readers when the university is a partner. It shows the badge, the
  breakdown for commission roles, and a one-line note of how the score is built. There is no always-present `role="status"`
  (upc-012 note).

## 6. Acceptance criteria (testable)

1. AC1: When the score is not null, the points of the breakdown add up to the score.
2. AC2: Bands: 80 → Excellent, 79 → Good, 60 → Good, 59 → Needs attention. The source's 92 and 48 map to Excellent and Needs attention.
3. AC3: Each factor normalises as HS3/HS4. A no-data factor is left out and its weight shared out (HS5).
4. AC4: A partner with no data → `score: null`, `insufficient_data` (HS8).
5. AC5: A non-partner → `health: null`.
6. AC6: overseas_admin gets `score` and `band` but no `factors` key, and no commission figure anywhere. The commission roles get
   `factors`, including commission.
7. AC7: The query count of `health()` is constant (1 vs 4 universities).
8. AC8: The existing performance contract and ranking are unchanged (the existing upc-018 and upc-019 tests still pass).
9. AC9: The UI shows the badge on the ranking and the card on the university page with its breakdown for commission roles. It works
   at desktop, tablet and phone widths with keyboard access.

## 7. Testing

- `tests/test_upc_028_health.py` (service): the pure maths (AC1–AC3, rounding), each factor from fixtures, response time median and
  unanswered, insufficient data, query count.
- `tests/test_upc_028_health_api.py`: AC4–AC6 and AC8 on both endpoints.
- Vitest: `PartnershipHealth.test.tsx`, the performance page column, and a university page stub/card.
- Playwright: `e2e/upc-028-partnership-health.spec.ts`.

## 8. Regression risks

- The shared university page (e2e strict `role=status`) and its unit-test `serverApi` stubs.
- `/partnership/performance` is consumed by the upc-018 and upc-019 pages and tests. The change is additive only.
- Commission leakage to overseas_admin is covered by an explicit test.

## 9. Implementation plan (TDD, one slice at a time)

1. Pure maths: `HEALTH_FACTORS`, `band` and `score` (largest remainder, weight sharing). RED (AC1–AC3), then GREEN.
2. `health(db, ids, today)`: factor values from fixtures, response time, insufficient data and the query count. RED, then GREEN.
3. Schemas and routes: attach `health` to the partner rows and to one university, and strip `factors` for non-commission roles. RED
   API tests, then GREEN. Re-run the upc-018 and upc-019 performance tests.
4. Web: the types and `healthText`, the `PartnershipHealth` component, the ranking column and the university card, with vitest first.
5. Playwright e2e. Docs: DEC-SCOPE-170, API §12CL, RBAC §2.96, SCREEN_CATALOG and the backlog status.

## 10. Phase 3 reviews (applied above)

- **API:** GET only and additive (`health`, plus `factors` behind a role). No new query parameter. The health score ignores the period
  on purpose (HS2), and `as_of` makes that explicit. No ETag or idempotency is assumed. A non-partner gets an explicit `health: null`,
  not a missing key, so clients can tell "not scored" from "not sent".
- **Security:**
  - Role first (`require_reader`, 403), then the existing scope; health reveals nothing about a university that its performance row
    does not already list.
  - Commission: the breakdown and its measure ("62% collected") go to the commission roles only (U2). A non-commission reader sees one
    rounded integer. That reader could, in theory, rebuild every other factor exactly and back out a ±0.1-coarse collection *ratio*,
    but never an amount. The backlog accepts this risk ("they don't see the score breakdown"), and it is recorded here as a residual
    risk (`NEEDS_CONFIRMATION`).
  - ORM-bound queries only. No PII, no message bodies, no logging per read. CSRF does not apply.
- **Frontend:** reuses the `.status` / `.badge` pills and the table / `table-scroll` idioms. The badge text carries the band, so the
  meaning is not conveyed by colour alone. The breakdown table has a caption, and the component is data-only (the upc-021 lesson).

## 11. QA evidence (2026-10-10, Docker stack `upc028`, Chromium via Playwright)

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA28-01 | Low | Commission roles: the university page at 375 px | Open a partner's health card on a phone | Factor, measure, weight and points are readable without side-scrolling | The generic `.table` 650 px minimum pushed Weight and Points off screen inside the scroll region | **Fixed:** `.table.health-breakdown { min-width: 0 }` and tighter cell padding under 480 px. Unit test added; re-checked at 375 / 820 / 1366 px (the Points header is on screen) |

**Exploratory pass (33 checks, all as expected after the fix):**
- **API:**
  - super_admin's year ranking: 19 partners scored out of 31 rows. Non-partners get `null`, every breakdown adds up to its score, and
    the bands match the thresholds.
  - Non-UUID `422`; unknown id `404`; POST `405`. Health is identical for two different periods (HS2).
- **Layout:** no page side-scroll on the ranking or the university page at 1366, 820 and 375 px. The badge never wraps.
- **Keyboard:** the breakdown region takes focus.
- **Navigation:** refresh keeps the Health column; back returns to the ranking.
- **Roles:**
  - overseas_admin sees the card's band but no table, and its list response has no `factors` / `commission`.
  - Signed out → `/overseas/login?next=…`. A counselor sees "University performance access required"; a student gets API `403`.
- **Browser health:** no console errors, and no unexpected 4xx/5xx on page loads.
- **Regression e2e:** the upc-018 and upc-019 specs pass. The upc-018 spec now reads Applications one cell later, after the new Health
  column.
