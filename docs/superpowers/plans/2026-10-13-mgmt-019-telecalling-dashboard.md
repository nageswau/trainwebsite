# mgmt-019 — Telecalling dashboard: implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-019-telecalling-dashboard-design.md` (TC1–TC16). TDD for every task; focused tests only.

1. **Service + route + schema (pytest first).** `tests/test_mgmt_019_telecalling.py` RED → `services/management_telecalling.py`
   (`dashboard()`), `schemas.TelecallingOut`, `GET /management/telecalling` in `api/management.py` (appended) → GREEN. Covers TC1–TC13,
   AC1 (totals = tel-023 `performance()` totals).
2. **Web lib (vitest first).** `tests/lib/managementTelecalling.test.ts` → `lib/managementTelecalling.ts` (filters, urls, percent text).
3. **Component (vitest first).** `tests/components/ManagementTelecalling.test.tsx` → `components/ManagementTelecalling.tsx` (form, tiles,
   chain, team + telecaller tables, empty/error states).
4. **Page + nav.** `app/management/telecalling/page.tsx` (snapshot/applications page pattern); `lib/management.ts` hrefs for the two
   mgmt-019 entries; nav test update if a pinned list breaks.
5. **E2E.** `tests/e2e/mgmt-019-telecalling.spec.ts`: partner opens the page from the Command Center, applies a range, refresh keeps it;
   accountant gets the access card.
6. **Docs.** DEC-SCOPE (TC1–TC16), API §12, RBAC §2, backlog status line, QA report.

Review notes (Phase 3): read-only GET, no transaction; inputs are two `date` query params (FastAPI 422 on malformed, tel-023 range rules);
authorization order `require_management` → operational tier before any read; output is staff names + counts only (no lead PII); React
escapes names (no XSS); GET only (no CSRF surface); ORM-built SQL; range ≤ 366 days bounds the cost.
