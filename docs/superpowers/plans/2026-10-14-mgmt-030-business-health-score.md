# mgmt-030 — Business health score (plan)

Spec: `docs/superpowers/specs/2026-10-14-mgmt-030-business-health-score-design.md` (BH1–BH14).

1. **Reuse (no behaviour change):** `partnership_metrics.health_score(values, factors=HEALTH_FACTORS)`. The upc-028 tests must stay
   green.
2. **RED → GREEN, backend:** `tests/test_mgmt_030_health.py`.
   - Tests: the pure scales and RAG bands; access (401; 403 for the accountant and other roles; 200 for the partner and super_admin);
     422 months; the default month = the previous month; the partner gets 12 factors and super_admin 6 with no finance factor;
     Σ points = the score; a far-past month with no data scores null; controlled ledger revenue gives the expected H1 score and H2
     margin.
   - Then add `services/management_health.py`, the schemas, and the route in `api/management.py`.
3. **RED → GREEN, web lib:** `tests/lib/managementHealth.test.ts` → `lib/managementHealth.ts` (query, URL, measure text, RAG label).
4. **RED → GREEN, component:** `tests/components/ManagementHealth.test.tsx` → `components/ManagementHealth.tsx` (overall tile, RAG
   lines, breakdown table whose total = the score, not-available reasons, empty and error states, month form).
5. **Page + nav:**
   - `app/management/health/page.tsx`.
   - `lib/management.ts`: the "Business health score" entry becomes operational with an href.
   - Add the `SUPER_ADMIN_NAV` entry.
   - Update the pinned nav tests.
6. **E2E:** `tests/e2e/mgmt-030-health.spec.ts`. The partner sees 12 factors, super_admin sees 6 and no money, and the accountant is
   refused.
7. **Docs after merging main:** the DEC-SCOPE entry, API §, RBAC §, backlog status and QA evidence.
