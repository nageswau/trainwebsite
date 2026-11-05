# pob-001 commercial permissions — implementation plan

Spec: `docs/superpowers/specs/2026-11-05-pob-001-commercial-permissions-design.md` (C1–C9). TDD: each task writes the failing test first.

1. **Catalogue + defaults (C2/C3).** Test `test_pob_001_commercials.py::test_catalogue…` (keys, holders) → `core/rbac.py`.
   Update `test_hrc_002_roles` only if it pins the catalogue size/holders.
2. **Migration 0278 (C3).** Test `test_pob_001_migration.py` (chain, frozen seed == DEFAULT_GRANTS holders, round trip) →
   `alembic/versions/0278_commercial_grants.py`.
3. **Grant helper (C4).** `recruiter_contracts.commercial_access(db, user) -> (view, edit)` via `permissions.user_has_grant`.
4. **Contracts (C5).** Tests: recruiter with role grants revoked → GET has no fee/terms keys; `can_view_terms` false; PATCH fee 403; PATCH
   agreement_type 200; POST with fee 403; document download 403 / upload 403; per-user deny override hides for one recruiter only; default
   recruiter sees + edits (AC5). → `services/recruiter_contracts.py`, `api/recruiter_contracts.py`, `schemas.py` (`RecContractOut` optional
   fields, permissions, `RecCompanyContracts` flags).
5. **Revenue (C6).** Tests: revoked recruiter → requirement/company revenue, invoices list, create invoice 403; manager without edit → fee
   PUT 403 and `can_set_fee` false; manager default → fee PUT 200 (AC3). → `services/recruiter_revenue.py`, `api/recruiter_revenue.py`.
6. **Comparison (C7).** Tests: revoked manager → no `revenue` key in items/totals, `revenue_visible` false; default → present.
   → `services/recruiter_metrics.by_recruiter`, its schema (if any).
7. **Web (C8).** Vitest: contract card hides fee/terms rows without `can_view_terms`; form hides fee/terms inputs without `can_edit_terms`;
   comparison hides the Revenue column when `revenue_visible` is false; navigation tags Receivables. → `lib/recruiterContracts.ts`,
   `RecruiterCompanyContract.tsx`, `RecruiterContractForm.tsx`, `RecruiterContractDocument.tsx`, `lib/recruiterRevenue.ts`
   (`canSeeRevenue(role, permissions)`), the two detail pages, `RecruiterComparisonPanel.tsx`, `lib/navigation.ts`.
8. **e2e** `pob-001-commercials.spec.ts`: super admin revokes `commercials.client.*` from `placement_team`; the recruiter sees no fee on
   the company page and no Revenue section; restore the defaults afterwards.
9. **Docs:** decision register `DEC-SCOPE-402`, API §12KU, RBAC §2.295, RTM rows, backlog status line.
