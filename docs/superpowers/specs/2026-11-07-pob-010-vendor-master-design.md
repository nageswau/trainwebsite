# pob-010 — Vendor and staffing-partner master, onboarding and agreements (DEC-SCOPE-420)

**Evidence:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-010 (`UNVERIFIED` requirements draft). V1–V12 are the builder's calls on
Q-08 and are `NEEDS_CONFIRMATION`.

**Non-goals:** requirements via a vendor, submissions to vendors and the NDA gate on sharing (pob-011); vendor fees' payables and
performance (pob-012); the `vendor_registration` pipeline stage (pob-004); merging vendor records.

## Decisions

- **V1 Vendor = Company (Q-08).** Reuses contacts, timeline, follow-ups, meetings, messages, documents and contracts. Scope and write
  permissions are the company's.
- **V2 Both (Q-08).** `partner_type` is `recruiter` | `employer` | `vendor` | `vendor_client`, with a CHECK. `companies.name` is unique, so a
  second row is not an option: `vendor_client` is one company in both relationships. `recruiter` and `employer` keep their meaning (clients).
- **V3 Vendor fields.** `vendor_specialisations`, `vendor_service_categories`, `vendor_locations` (lists, pob-003's validator) and
  `vendor_status`. Sending vendor lists for a non-vendor is 422. A CHECK ties `vendor_status` to the vendor types.
- **V4 Changing the relationship.** PATCH `partner_type`. An employer-owned company cannot change (409). Becoming vendor-only is 409 while the
  company has requirements, drives or a client contract. Leaving the vendor relationship is 409 once it has a vendor agreement. Becoming a
  vendor starts at `prospect`; leaving clears the status and lists are kept off the output.
- **V5 Onboarding.** `POST /recruiter/companies/{id}/vendor-status {status, from_status, reason?}`:
  prospect → registration_submitted → approved → active ⇄ suspended; registration_submitted → prospect (returned); approved → suspended.
  - The assigned recruiter or a manager/super_admin: submit (needs a `vendor_onboarding_form` document) and activate from approved (needs a
    current vendor agreement reading Signed or Active).
  - Manager/super_admin only: approve (needs an `nda` document), return, suspend, reinstate. Return and suspend need a reason.
  - A stale `from_status` is 409. Reinstating re-checks the agreement.
  - An expired agreement does not suspend a vendor automatically (pob-011 reads the agreement itself).
- **V6 History.** `company_vendor_status_history`, append-only, shown on the vendor card; an audit row carries ids and status keys only (never
  the reason).
- **V7 Documents.** A new `nda` document kind. The onboarding form and NDA are not commercial terms, so they are not grant-gated.
- **V8 Vendor agreements.** `recruiter_contracts.party` (`client` | `vendor`, default client) with `direction` (`vendor_pays_us` | `we_pay_vendor`)
  and `confidentiality_terms`, both vendor-only by CHECK. One current row per company **per party**. Routes take `?party=`; the default is
  the only party a vendor-only company has, else client (today's callers are unchanged). The wrong party for the company is 422. Direction is
  required from Signed on.
- **V9 Commercials.** A vendor agreement's fee, terms, direction, confidentiality and documents need `commercials.vendor.*` (pob-001); default
  holders `placement_team` and `placement_manager` (the people who contract vendors; migration seeds it; removable per role or user). BDM and
  others hold none.
- **V10 Client-only views (AC2).** A vendor-only company is left out of: the default company list (`relationship=client`; `vendor` and `all`
  opt in), the pipeline board, the requirement and drive company pickers (they read that list) and their create routes (422), the legacy
  `/workflows/it/jobs` create, the public home partners, and the lead counts on recruiter dashboards and performance. Client terms lookups
  (revenue, fee resolution) read `party='client'` only. A `vendor_client` company appears in both.
- **V11 Merge.** Merging a company in a vendor relationship is refused (409): merge has no rule for two agreement parties. Follow-up.
- **V12 Migration.** Guarded (0001 builds from today's models). Any `partner_type` outside the known set is normalised to `recruiter`, logged
  with the count: no code path has written another value.

## Security review

IDOR: every route resolves through `load_scoped` (out of scope 404). Role escalation: V5's manager steps are checked server-side; `partner_type`
`employer` is not accepted from a client. Commercials: terms are omitted from output without the vendor grant and writes are 403, logged without
the value. XSS: React escapes; lists use the existing control-character validator. CSRF/session: unchanged cookies. No secrets logged.

## Tests

`test_pob_010_vendors.py`, `test_pob_010_migration.py`, `RecruiterCompanyVendor.test.tsx`, `pob-010-vendors.spec.ts`.

## Regression risks

Metrics and pipeline queries (V10), contract routes (V8), the grant catalogue tests (V9), the document-kind tests (V7).
