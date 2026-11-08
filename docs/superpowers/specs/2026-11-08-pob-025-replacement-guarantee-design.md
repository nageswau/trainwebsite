# pob-025 — Replacement guarantee, early dropouts and expiry alerts (design + plan)

Source: `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` §pob-025 (DERIVED_BLUEPRINT, `UNVERIFIED`). Dependency pob-024
(`DEC-SCOPE-432`) is built. The owner asked for the recommended answers without a question round, so every call below is the builder's
(`NEEDS_CONFIRMATION`), recorded as `DEC-SCOPE-436`. It answers recruiter Q-22 ("replacement guarantee out of scope") for this item only.

## Intent
Today the replacement policy is free text on the contract (and the requirement), nothing records when a placed candidate leaves early,
and nobody is told when a guarantee is about to run out. pob-025 makes the guarantee period structured (`guarantee_days`), gives each
joined placement a `guarantee_end_date`, records an early dropout, links an owed replacement to a requirement (the replacement hire
carries no new fee) and alerts the owners once, shortly before the guarantee ends.

## Goals (AC)
1. The end date is computed from the joining date (actual joining date + the guarantee days).
2. A dropout inside the guarantee opens a replacement.
3. The expiry alert fires once.
Edge: a dropout after the guarantee ends records the dropout but owes no replacement.

## Non-goals / anti-goals
No credit note or invoice change on a dropout (the fee stays as invoiced: G12), no automatic requirement creation or reopening (the PO
uses the existing requirement screens), no client-facing notice, no reporting roll-up (pob-029). Anti-goals: a second replacement for one
dropout; a fee or an invoice draft on a replacement hire; an alert for a guarantee that already ended or after a dropout.

## Builder's calls (G1–G12)
- **G1 Terms.** `guarantee_days` (whole days 1–365, optional) on the contract and on the requirement. On the requirement a null inherits
  the company's current client contract (the pob-002 R7 rule, shown as "inherited"). Both are client commercial terms: read and written
  behind pob-001 `commercials.client` exactly like the replacement policy / replacement terms (contract `TERMS`, requirement
  `REC_REQUIREMENT_TERMS`, revisions `COMMERCIAL_KEYS`, history redaction).
- **G2 Snapshot on joining.** When the offer moves to Joined, the placement stores `guarantee_days` (the requirement's, else the current
  contract's) and `guarantee_end_date = actual_joining_date + guarantee_days`. No days → no guarantee (both null). Set once; later term
  edits do not move it (the joining itself is final).
- **G3 Guarantee status** (derived, never stored): `none` "No guarantee", `active` "In guarantee", `ended` "Guarantee ended",
  `dropped_out` "Dropped out". `days_left` while active.
- **G4 Early dropout.** `POST /placements/{id}/dropout {dropout_on, reason}` — the writers (`applications.WRITERS`); the placement must
  be Joined (409) and have no dropout yet (409, recorded once); `actual joining date ≤ dropout_on ≤ today (IST)` (422 on `dropout_on`);
  reason 2–500 characters. The offer, application and requirement are unchanged.
- **G5 Replacement owed** = a dropout on or before `guarantee_end_date`. A dropout after it (or with no guarantee) owes nothing (the edge).
- **G6 Replacement request.** `POST /placements/{id}/replacement {job_id}` — the writers; the placement must owe a replacement not yet
  filled (409). The requirement is one of the same client's requirements in the caller's requirement scope and not ended (422 on
  `job_id`: "Choose an open requirement of this client"; reopen or create it first on the requirement screens). It may be the original
  (reopened) requirement or a new one, and can be changed until filled.
- **G7 Fill.** The next placement created on the linked requirement (its offer is Accepted) while the request is unfilled becomes the
  replacement: the original gets `replaced_by_placement_id` (oldest dropout first; the row is locked and rechecked, the unique column is
  the backstop) and the new placement records `expected_fee = 0`. A replacement placement gets no invoice draft on joining.
  ⚠ On a multi-vacancy requirement the next accepted offer is taken as the replacement (NEEDS_CONFIRMATION).
- **G8 Replacement did not join.** The link is cleared, so the original is again "in progress" on the same requirement.
- **G9 The replacement's own guarantee** follows G2 like any placement (NEEDS_CONFIRMATION: some clients give only the remainder).
- **G10 Expiry alert.** A daily beat sweep (09:15 IST) sends `it.recruitment.guarantee_expiring` once (`guarantee_alerted_at`) to a
  Joined placement with no dropout whose end date is today or within `GUARANTEE_ALERT_DAYS = 7` days. A guarantee already past is never
  alerted. Recipients are pob-024's (recruiter owner, PO owner, their Team Leads; every active Team Lead when none). Fixed preview-safe
  text (no name, no date). Bounded `FOR UPDATE SKIP LOCKED` batches; the marker is written in the notice's transaction.
- **G11 Read.** `GET /placements/{id}` gains `guarantee` (any placement reader, P14 scope): `{days, end_date, status, status_label,
  days_left, dropout: {on, reason} | null, replacement: {status, status_label, requirement, placement} | null, replaces: {id, code} | null}`
  and `permissions.can_record_dropout` / `can_request_replacement`. Replacement status: `open` "Replacement owed", `requested`
  "Replacement in progress", `filled` "Replaced". The list gains a `replacements` view (owed and not yet filled).
- **G12 Commercials.** The dropout does not change the invoice or the draft; the replacement's zero fee shows as "No fee (replacement)".
  Audit rows carry ids, dates and flags only — never the reason.

## API (`/api/v1/recruiter`)
- `GET /placements?view=…|replacements` — the new view and its count.
- `GET /placements/{id}` — `guarantee` and two permissions.
- `POST /placements/{id}/dropout` — `{dropout_on, reason}` → 200 with the placement.
- `POST /placements/{id}/replacement` — `{job_id}` → 200 with the placement.
- Contracts: `guarantee_days` in create / update / read (behind `commercials.client`).
- Requirements: `guarantee_days` in create / update; `commercial_terms.guarantee_days = {value, inherited}`.

## DB — migration `0318_placement_guarantee` (guarded, additive; after `0317_intake_automation`)
- `recruiter_contracts.guarantee_days` int null, CHECK 1–365.
- `jobs.guarantee_days` int null, CHECK 1–365.
- `placements`: `guarantee_days`, `guarantee_end_date`, `guarantee_alerted_at`, `dropout_on`, `dropout_reason` (500),
  `replacement_job_id` (FK jobs), `replaced_by_placement_id` (FK placements, unique). CHECKs: days 1–365; days ⇔ end date;
  dropout date ⇔ reason; a requirement or a fill only after a dropout; never replaced by itself. Indexes: `guarantee_end_date`,
  `replacement_job_id`. No backfill (existing placements have no structured guarantee).

## Web
- Contract form and card: "Guarantee (days)". Requirement form: "Guarantee (days)" with the inherited hint; requirement detail shows it.
- Placement page: a "Replacement guarantee" panel — the status badge, days, end date and days left; "Record dropout" (date + reason);
  when a replacement is owed, "Link replacement requirement" (a select of the client's open requirements); the replacement placement link,
  and on a replacement hire "Replacement for …". Placements list: a "Replacements" tab.

## Plan (TDD, focused tests)
1. Model + migration + `test_pob_025_migration.py` (frozen checks, guarded, single head, round trip).
2. Terms: contract + requirement `guarantee_days` (schemas, FIELDS/TERMS, commercial_terms, revisions, history); tests.
3. `placements.py`: snapshot on joining (AC1), dropout + owed (AC2, edge), replacement request, fill on accept, clear on did-not-join,
   no draft for a replacement; `out` / list view; tests.
4. Sweep + event + beat + worker task (AC3: run twice → one alert; past/dropped → none); fresh-interpreter import test.
5. rec-038 route matrix rows for the two routes.
6. Web: types, guarantee panel, list tab, contract and requirement fields; vitest; e2e spec.
7. Docs: DEC-SCOPE-436, API §12MC, RBAC §2.327, DATA_MODEL, RTM, backlog status.

Regression risks: pob-024 placement tests (on_joined order), rec-022/023 offer/joining tests, pob-001/002 terms tests and vitest, rec-030
contract tests, rec-038 route matrix, job revision snapshot tests, single-head migration tests.
