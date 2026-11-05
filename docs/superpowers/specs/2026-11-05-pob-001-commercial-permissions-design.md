# pob-001 — Placement Officer role alignment and commercial-data permissions (design)

- **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-001 (doc header "Primary users", §17 "role-based access for … client
  terms and vendor commercials", §18 AC "Permissions prevent unauthorised users from accessing … commercial information"; source classified
  `UNVERIFIED`). The owner assigned pob-001 for build on 2026-11-05 and said to proceed with the recommended answers, so C1–C9 below are
  **the builder's calls (`NEEDS_CONFIRMATION`)** for Q-01. Dependency **hrc-002** is merged (`DEC-SCOPE-374`, PR #446). Decision
  `DEC-SCOPE-402`.

## Intent
Client commercial terms (a contract's fee, payment terms and replacement policy, a requirement's fee override, and everything priced from
them: revenue, invoices, receivables, the revenue column of the recruiter comparison) are visible today to every recruiter in scope. pob-001
puts them behind a configurable grant, so a super admin can take commercials away from a role or one person, and declares the vendor and
candidate-contact grant keys the later items (pob-010/011/012, pob-030) enforce.

**Non-goals:** vendors (pob-010 builds the concept); hiding candidate phone/email (pob-030's share gate wires `candidates.contact.view`
into every outward path — the backlog's BE list for pob-001 names only the contract, revenue and requirement serializers); the management
money screens (`management_access.can_view_finance`, unchanged); branch/department scope (hrc-002 R5).
**Anti-goal:** an upgrade that silently takes fee visibility away from today's recruiters and managers (backlog edge case "E").

## Rules (builder's calls)

**C1 — Role mapping (Q-01).** Placement Officer / BDM = hrc-002's `placement_officer` (DEC-SCOPE-374 R1; it has no recruiter-CRM access,
so no commercials). Recruitment Team Lead = `placement_manager` (team scope already exists). HR Manager = `hr_manager` (hrc-002). No new role.

**C2 — Catalogue.** New resources: `commercials.client` (`view`, `edit`), `commercials.vendor` (`view`, `edit`), `candidates.contact`
(`view`). No new action (`edit` and `view` exist).

**C3 — Defaults keep today's behaviour (Q-01 "E").** `placement_team` and `placement_manager` hold `commercials.client.view` and
`commercials.client.edit` by default, and `bdm` holds `commercials.client.view` (the assigned BDM reads the company's contract today,
rec-030 R10; it never writes it and revenue stays refused by RV10) (migration `0278_commercial_grants` seeds them; `ON CONFLICT DO NOTHING`; downgrade removes the
resource's grants and overrides). A super admin revokes per role (permission screen / `PUT /admin/roles/{role}/permissions`) or per user
(nehn-007 deny override). `commercials.vendor.*` and `candidates.contact.view` have **no default holder** (super_admin holds all) until
their owning items enforce them (hrc-002 R4 precedent).

**C4 — Effective edit = `edit` and `view`.** Editing what you cannot see is refused: a user with `edit` but not `view` cannot edit.

**C5 — Contracts (rec-030).**
- Without `view`, `fee_basis`, `fee_value`, `payment_terms` and `replacement_policy` are **absent** (not null) from every contract
  (current and previous; `response_model_exclude_unset`).
- `permissions` gains `can_view_terms` and `can_edit_terms`; the company's contracts gain top-level `can_view_terms`/`can_edit_terms` (for a
  first contract). Additive.
- `POST`/`PATCH …/contracts` carrying any of the four fields (any value, `null` included) without effective edit → **403**
  "Your role cannot view or change client commercial terms". Other fields (status, dates, agreement type) stay with `can_edit`.
- The contract and MoU **documents** are the signed terms (pob-003: "agreements follow the commercial grant"): download needs `view` (403),
  upload needs effective edit (403; `can_upload` is false). The document's name/date stay visible (that a file exists is not a term).
- History rows and the timeline already carry field names and statuses only — unchanged.

**C6 — Revenue (rec-031).** Every revenue route (requirement revenue, fee override, invoices, payments, cancel, company revenue, receivables
list) needs `commercials.client.view` after the role gate (RV10) → 403 "Your role cannot view client commercials". The fee override also
needs effective edit on top of the manager role (RV10 unchanged); `permissions.can_set_fee` reflects both. Invoices and payments are
record-keeping, not terms: `view` suffices (as today any revenue reader records them).

**C7 — Recruiter comparison (rec-034).** Without `view`, `revenue` is absent from every row and the total; the response gains
`revenue_visible: bool` (additive) and the screen drops the Revenue column.

**C8 — Web.** The company and requirement pages read `GET /auth/me/permissions` server-side and show the Revenue sections only with
`commercials.client.view` (plus the existing role check). The contract card hides fee and terms rows, the form hides those inputs without
`can_edit_terms`, the document download/upload follow `can_view_terms`/`can_upload`. The Receivables nav item is tagged with the
`commercials.client` resource (nehn-006 `navForPermissions`); the page itself shows the API's 403 message.

**C9 — Audit and logs.** Grant changes are already audited (nehn-005/007). A refused write logs `recruiter_commercials_refused` (actor, role,
route — never a value). No migration beyond the seed.

## Alternatives considered
- No default holders (strict least privilege): every existing recruiter loses fees on upgrade — the backlog's own edge case warns against it.
- `view` only for recruiters, `edit` only for managers: changes who may edit contract fees today (the assigned recruiter) — a behaviour
  change nobody asked for; a super admin can configure it in one step instead.
- Enforce `candidates.contact.view` now: touches ~15 candidate-side modules and the duplicate checks; the backlog assigns outward paths to
  pob-030's share gate.
- Null instead of absent fields: hrc-001 H2 established "absent, not null" for grant-hidden data.

## Acceptance (testable)
1. A recruiter whose role (or own override) lacks `commercials.client.view` sees no fee or terms anywhere: contract (current, previous,
   envelope after a write), contract documents, requirement revenue, company revenue, receivables, the comparison revenue column.
2. A Team Lead (`placement_manager`, default grants) sees the team's commercials (contract fee, requirement revenue, revenue column).
3. **+** A grant holder edits the fee (contract PATCH; manager fee override PUT).
4. **−** A user without the grant PATCHes the fee and gets 403; a PATCH of a non-commercial field still succeeds.
5. **E** After the migration, existing recruiters and managers keep fee visibility (default grants).
6. The catalogue lists the five new keys; vendor/contact keys have no default holder.

## Regression risks
rec-030/031/034 tests (fee fields — default grants keep them green), hrc-002 catalogue test (new keys), nehn-005 permission matrix, rec-038
route matrix (status codes unchanged for default roles), navigation tests (resource tag), web vitest fixtures for the contract/revenue cards.

## Numbering
Migration `0278_commercial_grants` (siblings hold 0274/0275), `DEC-SCOPE-402`, API §12KU, RBAC §2.295 — re-checked at merge.
