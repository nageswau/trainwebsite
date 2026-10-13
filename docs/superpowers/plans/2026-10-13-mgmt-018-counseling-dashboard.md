# mgmt-018 — Counseling dashboard (plan)

Spec: `docs/superpowers/specs/2026-10-13-mgmt-018-counseling-dashboard-design.md`. TDD per task; focused tests only.

1. **RED/GREEN** `test_mgmt_018_counseling.py` access + period (CS2, CS11) → route + schema + empty service.
2. **RED/GREEN** per-counselor figures CS3, CS5, CS6 over 2024-06 with fresh counselors → grouped queries.
3. **Refactor** `telecaller_metrics.first_conversions()`; tel-021/024 tests stay green.
4. **RED/GREEN** CS7 conversions (AC vs `conversions_by_user`) and CS9 conversion %.
5. **RED/GREEN** CS8 revenue: partner sees it, super_admin `null`; totals/divisions = sums (CS1, CS10).
6. **RED/GREEN** web lib (`managementCounseling.test.ts`) and component (`ManagementCounseling.test.tsx`): tiles, Not tracked,
   partners-only revenue, table + totals, empty, error.
7. Page `/management/counseling`, Command Center entries, super admin link (CS12); `ManagementCommandCenter` test updated.
8. Playwright `mgmt-018-counseling.spec.ts`; browser QA on the isolated stack (desktop / tablet / phone, partner / super_admin /
   accountant).
9. Docs: `DEC-SCOPE-202`, API §12DP, RBAC §2.127, backlog status, QA report.
