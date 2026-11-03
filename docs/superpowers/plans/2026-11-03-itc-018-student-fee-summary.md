# itc-018 implementation plan

Spec: `docs/superpowers/specs/2026-11-03-itc-018-student-fee-summary-design.md` (DEC-SCOPE-353).

1. **Next due** — `services/fee_accounts.py` `accounts()` adds `next_due` (one grouped read). Test first:
   `tests/test_itc_018_student_fee_summary.py` (partial payment → 25,000 due 10-Dec; fully paid / unbilled / zero row → null;
   fixed query count for many enrolments; balance equals `balance_for`).
2. **Receipt IDOR → 404** — `api/payments.py` `download_receipt`. Test first: other student 404, own 200, missing 404, IT admin 200.
3. **Course details** — `services/portal.py` `_it_student` course rows add `start_date`, `end_date`, `mode`, `room_or_link`
   (timetable slots, no URL). Test first: override wins, offline room, online label, no slots, no `http` in payload.
4. **Frontend** — `FeeAccountSummary.tsx` next-due line. Vitest: `tests/components/itc018FeeSummary.test.tsx`.
5. **Playwright** — `tests/e2e/itc-018-student-fee-summary.spec.ts` (fees card next due, course details columns).
6. **Docs** — DEC-SCOPE-353 register entry, API_CONTRACT section, RBAC_MATRIX note, backlog status line.
