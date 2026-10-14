# mgmt-031 — Partner home dashboard (implementation plan)

Spec: `docs/superpowers/specs/2026-10-14-mgmt-031-partner-home-design.md` (`DEC-SCOPE-219`, HM1–HM14). Branch `feature/mgmt-031`.
TDD per task: write the test, watch it fail for the expected reason, implement the minimum, rerun.

1. **API access + shape.** `tests/test_mgmt_031_home.py`: 401 signed out; 403 for the accountant ("Operational access required"),
   it_admin and counselor; partner 200 `scope: business` with all keys; super_admin 200 `scope: operational` with no `money`,
   `financial_position`, or money snapshot keys. Then add `ManagementHomeOut` to `schemas.py`, `services/management_home.py`, and the
   route.
2. **Snapshot parity (HM4).** Tests compare against `/management/pnl`, `/management/accounts`, `/management/snapshot`,
   `/management/applications?date_from&date_to`, and `/management/health?month=this` (Enrollment current). Then implement.
3. **Panels parity (HM5–HM13).** Tests: a pending decision with a past deadline is in the pending panel and counts as an urgent
   issue; an overdue task owned by the partner is in My tasks and is urgent; today's meeting is listed; the plan progress equals
   `/management/plans/{month}/progress`; the next-month plan summary; recent discussions equal the discussions page's first 5;
   growth equals `/management/health`. Then implement.
4. **Web lib.** `lib/managementHome.ts` (types, `greeting(hour)`, `HOME_URL`). `tests/lib/managementHome.test.ts`.
5. **Web component.** `components/ManagementHome.tsx` + `tests/components/ManagementHome.test.tsx` (partner, operational with no ₹,
   empty states, links).
6. **Page + nav.** `app/management/page.tsx` fetches home for the operational tier; the "This month's performance" entry becomes
   live at `/management#this-month`. Update `ManagementCommandCenter.test.tsx` if the nav or entry assertions change.
7. **e2e.** `tests/e2e/mgmt-031-home.spec.ts`: partner, super_admin (no money), accountant (no home).
8. **Docs.** DEC-SCOPE-219, API §12EG, RBAC §2.144, backlog status, QA evidence.
