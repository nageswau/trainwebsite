# upc-023 — Expected partnerships + probability + weighted forecast (design)

**Feature:** `upc-023` · **Decision:** `DEC-SCOPE-161` · **Migration:** `0143_university_probability` · **API:** §12CC · **RBAC:** §2.87
**Evidence:** `EVID-020` §23 (L754–L780) and §24 (L782–L808), traced in `UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` (§4 upc-023, §3.2 Q-09,
Appendix B P and E1–E4). **Dependencies:** upc-007 (stage engine, merged), upc-008 (`expected_agreement_date`, merged).
**Status of answers:** EX1–EX12 are recommended answers applied under the owner's standing instruction ("proceed with the recommended
answers; ask only if genuinely blocking"). They are **not** separately confirmed: `NEEDS_CONFIRMATION` at sign-off.

## 1. Understanding

- §23 asks for a dedicated "Expected University Partnerships" screen with columns University, Country, Stage, Expected Date, Owner,
  Probability, and three figures: expected this month, next month and this quarter.
- §24 lists seven probability bands by stage and asks the CRM to compute a weighted forecast (10 universities × 80% = 8).
- Success: AC1 (10 at 80% → 8 expected), AC2 (windows use IST months / calendar quarters), override outside 0–100 → 422, and universities
  with no expected date are excluded from the windows and listed separately.
- Source table rows (ABC/XYZ/DEF, the 8 / 12 / 25 figures) are illustrative only.

## 2. Answers (EX1–EX12, `NEEDS_CONFIRMATION`)

| # | Question | Answer |
|---|---|---|
| EX1 | Probability per stage (Q-09) | Appendix B P, already in `app/partnership_stages.py`: the §24 bands, plus Researching / Contact Identified 10%, Meeting Scheduled 40%, Commercial Discussion / Documents Shared 75%, every Signed-or-later stage 100%. Lost/Closed = 0% |
| EX2 | Manual override (Q-09) | Allowed: a whole number 0–100 with a required reason (≤ 500 chars). Stored on the university (`probability_override`, `probability_override_reason`). Clearing it (null) returns to the stage probability. Outside 0–100, a missing reason, or a reason without a value → 422 |
| EX3 | Does an override survive a stage move? | Yes, until cleared: the screen always shows the stage probability next to an override, so a stale one is visible. Auto-clearing would make the stage engine (single writer) also own this field |
| EX4 | Who overrides | The stage rule (`can_move_stage`: the university's managers, their head, `super_admin`); another team → 403; inactive → 409. Audited (`probability_overridden`, old/new value, reason flag) |
| EX5 | Who reads the screen | `partnership_manager` (with a profile), `partnership_head`, `super_admin` (backlog: "partnership roles, super_admin"; the Targets & Forecast page's readers, TG7). Every other role, including `overseas_admin`, → 403 |
| EX6 | Scope | upc-018 PF6: manager = universities where they are primary or backup; head = their team's + unowned; `super_admin` = all. Active universities only |
| EX7 | "Not yet signed" | Stage before Agreement Signed, not lost, active |
| EX8 | Expected date | `expected_agreement_date` (upc-008 §5) — the backlog's "drives upc-023" |
| EX9 | Windows | IST today (DB clock). `this_month`, `next_month`, `this_quarter` (calendar quarter), and `all` (every dated row, including overdue ones, i.e. expected date before today); `undated` lists the not-yet-signed universities with no expected date (excluded from every window) |
| EX10 | Figures | Per window: raw `count` and `weighted` = Σ probability / 100, rounded to 1 decimal (E4). Returned for all three windows on every call (forecast cards), plus `undated_count` |
| EX11 | Owner | The primary manager; none → "Unassigned" |
| EX12 | List order and paging | Expected date, then name; `limit` 1–100 (default 25), `offset`; `total` counts the whole window |

## 3. Data (migration `0143_university_probability`)

`universities` gains `probability_override SMALLINT NULL` and `probability_override_reason VARCHAR(500) NULL`, with checks
`ck_universities_probability_override` (`probability_override IS NULL OR probability_override BETWEEN 0 AND 100`) and
`ck_universities_probability_reason` (`(probability_override IS NULL) = (probability_override_reason IS NULL)`). Guarded steps (0001 builds
from the models). No backfill. `downgrade()` refuses while any override exists.

## 4. API

- `GET /partnership/expected?window=all|this_month|next_month|this_quarter|undated&limit&offset` →
  `{ today, window, windows: [{key, label, from, to, count, weighted}] ×3, undated_count, total, limit, offset, items: [{university: {id,
  university_code, name}, country, stage, stage_label, expected_agreement_date, owner: PersonRef|null, probability, stage_probability,
  override_reason}] }`. 401 signed out; 403 per EX5; 422 for an unknown window or bad paging. Read-only, nothing audited. Constant query
  count: the clock, one rows query (the windows are folded in Python over the scoped rows).
- `PUT /partnership/universities/{id}/probability` body `{probability: int|null, reason: str|null}` (extra fields forbidden) →
  `UniversityEnvelope`. One transaction: row lock, `can_move_stage`, change, audit only when changed, commit, structured log (ids only).
- The university detail gains `probability: {stage, override, reason, effective}` (additive).

## 5. UI

- New page `/partnership/expected` (server-rendered, `window` in the URL): three forecast cards (count + weighted, each a link to its
  window), window tabs (All dated / This month / Next month / This quarter / No expected date), the §23 table, previous/next paging, empty
  states per window. Owner "Unassigned"; an override reads "70% (override; stage 40%)" with the reason as text.
- The Targets & Forecast page (`/partnership/targets`) gains the forecast half: the same three cards and a link to the full list. A failure to
  load the forecast shows a note; the targets still render.
- The university detail "Partnership timeline" section shows "Partnership probability" and, for those who may move the stage, an
  "Override probability" form (value + reason, Clear override).
- No new menu entry: "Targets & Forecast" is already live (upc-021).

## 6. Tests

- API (pytest): roles (401/403/manager without profile 403), scope (manager/head/super_admin), AC1 (10 × 80% → 8.0), windows in IST
  incl. a quarter boundary, signed/lost/inactive excluded, undated listed separately, override 0–100/422s/audit/403/409, detail field,
  migration parity/head/round-trip.
- Web (vitest): lib helpers (window labels, probability text), page rendering (cards, empty state, override text), timeline override form.
- E2E (Playwright): a head sets an expected date and override, sees the row and the cards; a manager sees only their own.

## 7. Risks

- Shared test DB: window counts for super_admin are not isolated — assertions use a fresh manager's scope.
- Detail page: other specs use page-wide `getByRole("status")` — the new notice renders only when shown.
