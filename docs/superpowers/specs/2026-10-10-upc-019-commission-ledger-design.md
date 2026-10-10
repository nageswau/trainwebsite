# upc-019 — Commission expected + received ledger (restricted) — design

- **Feature:** `upc-019` (`UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-019; Appendix B F10/F11).
- **Evidence:** `EVID-020` §15 L517/L541/L543 ("Finance manages actual receipts"), §17 L617 ("University commission generated"), §18 L634–L635
  (Commission Expected / Received), L1129 ("Commissions should not be seen by anyone."); backlog §3.1 **U2, U4** (`EXPLICIT_APPROVAL`,
  2026-10-08); §3.2 Q-18, Q-19, Q-20; `DEC-SCOPE-144` CM1–CM4 (upc-016), `DEC-SCOPE-153` PF9 (upc-018).
- **Dependencies:** upc-016 (terms, merged via PR #192 chain) and upc-018 (funnel, PR #203) are both on `main`.
- **Decision:** `DEC-SCOPE-164`. **Migration:** `0144_commission_receipts`. **API:** §12CF. **RBAC:** §2.90.
- **Status:** CL1–CL14 below are recommended answers applied under the owner's standing instruction for the build session ("proceed with
  the recommended answers; ask only if genuinely blocking"). **Not** separately confirmed: `NEEDS_CONFIRMATION` at sign-off.

## 1. Decisions (recommended answers)

| # | Question | Answer |
|---|---|---|
| CL1 | Q-19: does Expected count only once the trigger is met? | **Yes.** `enrolment`: the application's current status is `enrolled`. `visa_and_enrolment`: enrolled **and** a visa case `approved`. `tuition_paid`: **not tracked** (no tuition-payment record exists in the CRM) — the application is listed as "Trigger not tracked" and adds nothing |
| CL2 | Which applications | `OverseasApplication` rows of the university whose current status is `enrolled` (every owner kind, as F9). An enrolled application cannot be withdrawn (`ENROLLED_NOT_WITHDRAWABLE`), so the backlog edge "withdrawn after enrolment" cannot occur; if the status ever leaves `enrolled` the row simply stops counting (computed live, nothing stored) |
| CL3 | Enrolment day | The IST day of the first status-history entry into `enrolled`, else `enrollment_confirmed_at`, else `enrollment_date` (F9's timing + the agency's recorded date). None of them → "Enrolment date unknown", adds nothing |
| CL4 | Which agreement applies | An agreement of the university that is or was in force — stored status `signed`, `active` or `renewed` — with `start_date ≤ enrolment day ≤ expiry_date` |
| CL5 | Q-18 precedence (CM4) | Among those agreements' terms that cover the application's programme (term `course_ids` empty or containing `course_id`): a term naming the programme beats an all-programmes term. Ties → the newest term (created last). No covering term → "No applicable term" |
| CL6 | Student country (CM4 second half) | The CRM records no student country on an application, so a **country-restricted term never matches**; an all-countries term applies. Recorded as a known limit (`NEEDS_CONFIRMATION`) |
| CL7 | Q-18 per-course commission (upc-017 CO2) | **Not used** for Expected: U4 says "enrolled students × terms". The course field stays reference information (`NEEDS_CONFIRMATION`) |
| CL8 | Amount + currency (Q-18) | Fixed term: the fixed amount in the **term's** currency. Percentage term: course `tuition_amount × % ÷ 100`, rounded half-up to 2 dp, in the **course's** tuition currency. No course or no parsed tuition → "Tuition unknown", adds nothing. **No FX anywhere**: totals per currency |
| CL9 | Q-20 who records | `partnership_head` and `super_admin` record and remove receipts; `partnership_manager` (with a profile) reads. Every other role `403`, anonymous `401` (U2) |
| CL10 | Q-20 receipt shape | A **lump sum per university**: amount (> 0, ≤ 99,999,999.99, 2 dp), currency (project list), date received (not in the future, IST), reference (required, 1–120, unique per university case-insensitively — a remittance reference is recorded once), note (≤ 500), linked applications (optional, ≤ 200, enrolled applications of this university) |
| CL11 | Outstanding | Per currency: Σ Expected − Σ Received (all time, on the university panel). Negative = received more than expected (shown as such, not hidden) |
| CL12 | Corrections | A receipt is never edited; a mistaken one is removed by a recorder (audited) and re-entered |
| CL13 | Performance (F10 / F11) | For the commission roles only, each `/partnership/performance` row, the page itself (summed over every ranked row, like `totals`) and `/partnership/universities/{id}/performance` gain `commission: {expected: [{currency, amount}], received: [...]}`: F10 = Σ Expected of applications whose enrolment day is in the period and trigger met; F11 = Σ receipts with `received_on` in the period. Every other reader (overseas_admin) gets **no** `commission` key (computed only behind `can_see_commission`; the routes exclude unset fields) |
| CL14 | Privacy / audit | No student name or contact in any response; applications are identified by a short id, programme, intake and the university's reference. Audit `university_commission_receipt.create/delete`: ids + currency only, never the amount, reference or note. Reads are not audited. Logs: ids only |

## 2. Data

Table `university_commission_receipts`: `id`, `university_id` (FK RESTRICT), `amount` Numeric(12,2), `currency` String(3), `received_on`
Date, `reference` String(120), `note` Text?, `application_ids` JSON (default `[]`), `created_by_user_id` (FK RESTRICT), timestamps.
CHECKs: amount > 0; currency in the project list; note ≤ 500. Index `(university_id, received_on)`; unique index
`(university_id, lower(reference))`. Additive; the downgrade refuses while any receipt exists (money records are never dropped silently).

## 3. API (§12CF)

- `GET /partnership/universities/{id}/commission` → `{university, totals: [{currency, expected, received, outstanding}],
  applications: [{id, ref, course, intake, enrolled_on, status, status_label, term_id, currency, expected}], receipts: [...],
  permissions: {can_record}}`. 404 unknown university. Applications newest enrolment first (≤ 200 listed, `applications_total` gives the
  count; totals are over all). Receipts newest first (≤ 200 listed, `receipts_total`).
- `POST /partnership/universities/{id}/commission/receipts` → 201 `{receipt}`. 422 invalid values / foreign or non-enrolled application;
  409 duplicate reference; 403 a reader who may not record.
- `DELETE /partnership/universities/{id}/commission/receipts/{receipt_id}` → 204; 404 unknown.
- Writes lock the university row first (`FOR UPDATE`), then insert/delete, one commit, then a structured log.

Statuses per application: `counted`, `awaiting_visa`, `trigger_not_tracked`, `no_term`, `tuition_unknown`, `date_unknown`.

## 4. UI

- University page: a "Commission (Restricted)" section for the commission roles only — the per-currency totals table, the enrolled
  applications with their status and expected amount, the receipts list, and for recorders a "Record a receipt" form (amount, currency,
  date, reference, note, linked applications as checkboxes) and Remove with an inline confirm. Empty / error states follow the page.
- Performance page: "Commission expected" / "Commission received" columns (per-currency text) when the API sent `commission`.

## 5. Tests

- Service: AC1 (15 % × £18,000 = £2,700 at enrolment), triggers (CL1), CL3 timing, CL4 agreement window/status, CL5 precedence and tie,
  CL6, CL8 fixed vs % currencies and rounding, no tuition, constant query count.
- API: AC2 a receipt reduces outstanding; P1 a lump sum for the Jan intake with linked applications; N1 negative amount → 422; the
  validation set; 409 duplicate reference; AC3 every other role 403 on all three routes + no `commission` key in performance for
  overseas_admin; 401 anonymous; audit metadata carries no amount/reference.
- Migration: CHECK strings match the model; downgrade refusal.
- Web: vitest for the section (roles, form validation, empty state) and the performance columns; Playwright e2e for record → outstanding.

## 6. Regression risks

`AgentCommission` untouched (separate concept). upc-018 performance responses unchanged for overseas_admin (no new key). The university
page is shared by many e2e specs: the new section renders `role="status"` only when a notice is shown.
