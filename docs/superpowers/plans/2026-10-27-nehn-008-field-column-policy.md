# nehn-008 field (column) policy — implementation plan

Spec: `docs/superpowers/specs/2026-10-27-nehn-008-field-column-policy-design.md` (DEC-SCOPE-300).

## Engineering review (Phase 3) folded in

- **API:** no route, parameter or status changes; only the presence of the two commission columns now follows a grant. Additive
  catalogue entry; `/auth/me/permissions` and the matrix pick it up with no web change.
- **Security:** the policy runs inside `build()`, the one function both the JSON and the download call, so no path skips it. It narrows
  only (U2 rule still applies first). Deny-by-default for an unknown class key (catalogue check in `user_has_grant`). No new input.
- **Frontend:** `PartnershipReportView` renders `report.columns`; no change. The matrix shows the new row from the catalogue.
- **DB:** seed-only migration; idempotent; downgrade removes only `field.financial` rows.

## Tasks (TDD)

1. RED: `tests/test_nehn_008_field_policy.py` — catalogue/seed, `strip()` unit behaviour, recruiter/HR lack the key (AC1/AC5).
   GREEN: `rbac.CATALOGUE` + `DEFAULT_GRANTS`; `services/field_policy.py`.
2. RED: partnership performance — revoke/restore and deny-override change JSON + CSV + xlsx together; JSON columns == CSV header ==
   xlsx header for every reader × kind × grant state (AC2-AC4). GREEN: `partnership_reports.FIELD_CLASSES` + `build()`.
3. Migration `0207_field_financial_grant` + `tests/test_nehn_008_migration.py` (chain, seed, round trip).
4. Update pinned catalogue assertion in `test_nehn_005_permissions.py`; run nehn-005/006/007, upc-031, nehn-004 suites.
5. Docs: DEC-SCOPE-300, API §12GX, RBAC §2.211, backlog status, feedback tracker.
6. e2e: `apps/web/tests/e2e/nehn-008-field-policy.spec.ts` — matrix shows Financial columns; partnership performance report shows
   commission for a manager and hides it after a deny.
