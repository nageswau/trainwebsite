# nehn-021 — Discount authority through a finance permission (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-021` (§7 L169-172; §5 recruiter "should not … Discounts",
L112; `UNVERIFIED` backlog). Decision: `DEC-SCOPE-309`. Dependency nehn-005 (`DEC-SCOPE-281`) is merged; nehn-019 is only recommended.
Owner pre-authorised the recommended answers; open questions are recorded as `NEEDS_CONFIRMATION`, not resolved.

## Intent

Only authorised users manage discounts. By default that is IT Admin / Super Admin; a separate financial permission (`discounts.add`)
can be granted to another role, such as the accountant, through the permission matrix.

## Current state (verified 2026-10-28)

- nehn-005 already moved `POST /admin/payments/{id}/discount` from `ensure_admin` to `require_permission("discounts", "add")`, seeded to
  it_admin and overseas_admin (super_admin holds every key). The reason is required and the change is audited (`payment.discount`, with
  the original amount, the new amount and the reason). A new amount at or above the current one is 422.
- nehn-006 hides **Apply discount** in `WorkflowPanel` without `discounts.add` (vitest + e2e AC6).
- **Gap:** the accountant (and every other management role) has `division = "global"`. The route answers 403 "Wrong division" to any
  non-super_admin whose division differs from the payment's, so granting `discounts.add` to the accountant still refuses every
  discount. `GET /admin/payments` likewise lists only `division == "global"` payments (none) to a granted accountant. The accountant
  also has no page that offers the control (`WorkflowPanel.specsFor` returns nothing for them; `/admin/[module]` is super_admin-only).

## Design (builder's calls)

| # | Call | Why |
|---|---|---|
| D1 | The discount route and `GET /admin/payments` treat a `global`-division caller like super_admin: every division. Division staff (it_admin, overseas_admin) keep their own division only. | AC2. A global role has no division to be scoped to; only a holder of the grant reaches the check. |
| D2 | No change to the default grants and no migration. The accountant gets nothing by default; a super admin grants `payments.view` + `discounts.add` in the matrix. | Backlog: "It can be granted". |
| D3 | overseas_admin **keeps** `discounts.add` (OD-12 `NEEDS_CONFIRMATION`). | Removing it changes live behaviour without the client's answer; it is one matrix click to revoke. |
| D4 | New page `/management/payments` in the Management portal: the payments table (from `GET /admin/payments`) plus the **Apply discount** form. A **Payments** nav entry is added for the finance tier, tagged with the `payments` resource, so it shows only to a holder of `payments.view` (nehn-006 `navForPermissions`). | The accountant's only portal is Management; the control must be reachable to be "enabled". |
| D5 | `WorkflowPanel` gives the finance roles (partner, accountant) on `payments` only the **Apply discount** spec (still filtered by `discounts.add`). *Create payment due* / EMI stay division-scoped admin actions. | Scope: discounts only. |
| D6 | Without `payments.view` the page shows the API's refusal in place of the table; without `discounts.add` the form is hidden and the API answers 403. | AC1 for every role. |

**Not built (`NEEDS_CONFIRMATION`):** a discount cap / super-admin approval above a threshold; an IT scholarship concept (scholarships
are overseas-only today). Discounting a paid payment stays out of scope (refund flow).

**Alternatives rejected:** opening `/admin/payments` (the super admin's module page) to granted roles — it carries the Super Admin nav
and role label; a new "finance" division value — a data change for a scope rule; seeding the accountant — the backlog says "can be
granted".

## Acceptance criteria (testable)

1. Without `discounts.add`, the route returns 403 and the control is hidden (trainer, placement_team/recruiter, ungranted accountant).
   *(pytest, vitest, e2e)*
2. Granting `discounts.add` (+ `payments.view`) to the accountant lets them list payments of both divisions and discount an IT or an
   overseas payment from `/management/payments`. *(pytest, e2e)*
3. Every discount is audited with the reason, whoever applies it. *(pytest)*
4. it_admin / overseas_admin are still limited to their own division (403 "Wrong division"). *(pytest)*
5. A new amount at or above the current one is 422 (unchanged). *(existing pytest)*

## Review notes (Phase 3)

- **API:** no new route, no shape change; only who gets 200 vs 403 changes for global-division grant holders.
- **Security:** the grant is still checked first (dependency); the scope widening applies only to `global` users, who are created by a
  super admin only (mgmt-001 MG1). No new IDOR: the payment is still fetched by id and 404s when absent. Audit unchanged.
- **Frontend:** reuses `PortalShell`, `PortalSection`, `WorkflowPanel`, `managementNavFor`; no new state or hooks.
- **Regression risks:** division tests for it_admin/overseas_admin; nehn-006 AC6 e2e; management nav tests.
