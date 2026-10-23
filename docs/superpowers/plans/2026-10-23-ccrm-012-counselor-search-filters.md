# ccrm-012 — Counselor quick search and list filters (plan)

Spec: `docs/superpowers/specs/2026-10-23-ccrm-012-counselor-search-filters-design.md`. TDD per task; focused tests only.

1. **List filters** — `ApplicationFilters` gains country/university/intake/stage/sub_status/from/to; `parse` validates (422), `apply`
   adds SQL clauses, `payload_part` adds options. `api/portal.py` passes the new params and counts repeats. Test:
   `tests/test_ccrm_012_filters.py` (each filter narrows; options in scope; bad values 422; sub-status/stage mismatch; from>to;
   AGN-023 file still green).
2. **Lead filters** — `GET /counselor/leads` `stage`, `priority`, `from`, `to`; `lead_handover.lead_filters`. Test in
   `tests/test_ccrm_012_lead_filters.py`.
3. **Search** — `services/counselor_search.py` (`search(db, user, q)`), `GET /counselor/search` in a new `api/counselor_search.py`
   router (registered in main). Test `tests/test_ccrm_012_search.py`: by name/email/phone/codes per entity; another counselor's
   student phone → nothing (AC); <3 chars 422; non-counselor 403; IT counselor 403; 31st search 429; audit row has no `q`.
4. **Web** — `ApplicationFilterBar` new selects + date inputs (URL params); `PortalPage` forwards the new keys; `CounselorLeadsPanel`
   filter row; `CounselorQuickSearch.tsx` on the overseas counselor dashboard. Vitest for bar, panel filters, quick search.
5. **Docs** — DEC-SCOPE-246, API §12EY, RBAC §2.161, RTM, backlog status.
6. **E2E** — `tests/e2e/ccrm-012-counselor-search-filters.spec.ts`.
