# hrc-011 — Candidate compensation model and normalisation (design)

**Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-011` (PDF §8.3 B; PDF classified `UNVERIFIED`). Scope approved by the
owner 2026-11-01 (backlog Q-00: all phases). Dependency `hrc-001` (DEC-SCOPE-371) is merged on `main`. The owner said to proceed with the
recommended answers, so C1–C9 below are **the builder's calls (`NEEDS_CONFIRMATION`)**. Decision record: DEC-SCOPE-375.

## Intent
Recruiters record pay the way candidates actually state it, for example "₹50,000 a month now, expecting 8 LPA, won't go below 7, negotiable", or
"USD 4,000 a month". Every amount is kept exactly as entered. Next to it the system stores one comparable figure, **annual INR**, which
Find Candidates and talent pools filter on. Who may see or send compensation stays exactly as hrc-001 set it (the
`candidates.compensation.view` grant).

## Acceptance criteria (backlog AC + E cases)
1. ₹50,000 per month normalises to ₹6,00,000 per year.
2. USD values use the admin rate (a placement manager's rate table).
3. The original value (amount, currency, period) is kept and returned.
4. A role without the grant never receives any compensation field (old or new) and cannot send one (403).
5. A negative amount → 422; an unknown currency (no rate, or not three letters) → 422; the pay period "hourly" → 422 (C2).

## Builder's calls
- **C1 (Q-10, FX source):** a manual table `rec_fx_rates` (`currency` CHAR(3) PK, `inr_per_unit` NUMERIC(12,4) with 0 < rate ≤ 10,000,
  `updated_at`, `updated_by_user_id`). INR is implicit (rate 1) and can never be stored. No rates are seeded, because the system does not invent
  exchange rates. Placement managers and super_admin set them. Every role that reads candidates can read them, because the form needs the
  currency list. No delete endpoint, since a currency in use must keep its rate.
- **C2 (Q-10, pay periods):** `year` and `month` (a month is ×12). Hourly, weekly and daily are not supported (422). The spec gives no
  hours-per-year rule, and Indian CTC is quoted per year or per month.
- **C3:** each of current, expected and minimum has its own amount, currency and period, because current pay is often monthly while the
  expectation is in LPA. There is one `salary_negotiable` flag (true, false or null for "not provided").
- **C4 (defaults):** an amount sent without a currency or period takes the stored one, or else INR and year. Clearing an amount (null)
  clears its currency, period and annual INR. Unknown stays null ("Not provided"), never 0.
- **C5 (rate change):** saving a rate recomputes the annual INR of every candidate amount in that currency in the same transaction. Candidate
  writes read the rate `FOR SHARE`, so a concurrent rate change and candidate save serialise and neither leaves a stale figure.
- **C6 (search):** the existing Find Candidates and pool `salary_min`/`salary_max` (already "₹ lakhs a year" in the UI) now compare against
  `expected_annual_inr`. The backfill makes this identical for existing rows. Result cards also return `expected_annual_inr` and show it.
  "Unknown not excluded" and new filter families are out of scope (hrc-019).
- **C7 (grant):** every new key joins `services/candidates.COMPENSATION`, so the hrc-001 omit and 403 rules cover them without new code
  paths. The rate table is not compensation and is not gated by the grant.
- **C8 (rounding):** annual INR = amount × (12 if month else 1) × rate, rounded half-up to 2 dp, stored in NUMERIC(18,2).
- **C9 (API compatibility):** `current_salary` and `expected_salary` keep their names and now mean "the amount as entered". Old clients that
  send only the amount get INR per year, which was the old meaning.

## Data (migration `0251_candidate_compensation`)
On `candidates` the migration adds `current_salary_currency`, `current_salary_period`, `expected_salary_currency`, `expected_salary_period`,
`minimum_salary`, `minimum_salary_currency`, `minimum_salary_period`, `salary_negotiable`, `current_annual_inr`, `expected_annual_inr` and
`minimum_annual_inr`. It adds a check that minimum ≥ 0 and periods are in (year, month), and the index `ix_candidates_expected_annual_inr`.
It creates the new table `rec_fx_rates`. Backfill: each non-null amount gets currency 'INR', period 'year' and annual INR = amount. The
downgrade drops the columns, the index and the table; the original amounts are untouched.

## API
- Candidate create/PATCH accept the new fields. Detail returns them, but only with the grant.
- Search and pool cards add `expected_annual_inr`, again only with the grant.
- New `GET /api/v1/recruiter/catalogue/exchange-rates` lists the rates for candidate readers.
- New `PUT /api/v1/recruiter/catalogue/exchange-rates/{currency}` takes `{inr_per_unit}` for managers and super_admin. It upserts, recomputes, and
  writes the audit action `recruiter.fx_rate_set` (currency, old and new rate, number of rows recomputed).

## UI
- **Candidate form:** a "Compensation" group appears with the grant. For current, expected and minimum it has amount, currency
  (INR + rate currencies) and period (per year / per month), plus Negotiable (Not provided / Yes / No).
- **Detail:** each amount shows as entered, plus "≈ ₹x a year" when it is not already INR per year. Negotiable shows on its own line.
- **Find Candidates card:** shows the annual INR.
- **Catalogues:** a new "Exchange rates" tab for setting a rate per currency.

## Regression risks
The rec-013 salary filter and pools (C6), the hrc-001 leak and 403 tests, the hrc-003 stale-guard field list, and the screening's own
`expected_salary` (unchanged, a separate field).
