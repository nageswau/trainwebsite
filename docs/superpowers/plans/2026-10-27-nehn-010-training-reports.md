# nehn-010 — Training reports pack (plan)

Spec: `docs/superpowers/specs/2026-10-27-nehn-010-training-reports-design.md`. TDD, focused tests only.

1. **Calculator** `services/training_progress.py` — RED: parity test (eligibility endpoint vs calculator on a seat with present/late/
   absent/excused marks, graded/ungraded submissions, passed/failed assessments) → GREEN → switch `_certificate_eligibility` to it;
   run nehn-031/032 + certificate tests.
2. **Reports (a)–(g)** in `services/reports/training.py` — RED: `tests/test_nehn_010_training_reports.py` (catalogue, figures per
   report on a fixture course with two batches/two trainers, filters, trainer scope, revenue field policy, edge cases, xlsx == JSON)
   → GREEN one report at a time.
3. **Web** — no component change (ReportView renders any registered report). Playwright `nehn-010-training-reports.spec.ts`.
4. **Docs** — DEC-SCOPE-305, API §12HC, RBAC §2.216, RTM, tracker, backlog status, user manual.

## Phase 3 review notes (applied)
- API: additive report ids under `/api/v1/reports`; no contract change; ordering 404 → 403 → 422 inherited.
- Security: rows scoped in SQL by `_scope` before filters (no IDOR: filters intersect); revenue `financial` class through
  `field_policy.strip` for JSON and files; downloads keep throttle/cap/audit; values never logged. No new input type.
- Frontend: reuse ReportView/ReportLibraryPage; null → "—" already; numeric cells right-aligned by `cellClass`.
- Transactions: reads only; the export transaction is the framework's.
