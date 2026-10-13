# mgmt-021 — Agent network dashboard: implementation plan

Spec: `docs/superpowers/specs/2026-10-13-mgmt-021-agent-network-dashboard-design.md` (AN1–AN14). Every task is TDD, with focused tests only.

1. **Service, route and schema (pytest first).**
   - RED: `tests/test_mgmt_021_agents.py`.
   - Then `services/management_agents.py` (`FIGURES`, `dashboard()`), `schemas.ManagementAgentsOut`, and `GET /management/agents`
     appended to `api/management.py`. Then GREEN.
   - Covers AN1–AN14. The AC: rows sum to the totals, super_admin money is null, and an agency row equals the mgmt-024 funnel filtered by
     that agency.
2. **Web lib (vitest first).** `tests/lib/managementAgents.test.ts`, then `lib/managementAgents.ts` (query, url).
3. **Component (vitest first).**
   - Test: `tests/components/ManagementAgents.test.tsx`.
   - Then `components/ManagementAgents.tsx`: the form, tiles, chain and ranking table, plus the empty, error and suspended states.
4. **Page and nav.**
   - `app/management/agents/page.tsx`, on the counseling page pattern.
   - The `lib/management.ts` Agents href.
   - A `SUPER_ADMIN_NAV` link, "Management agent figures".
5. **E2E.** `tests/e2e/mgmt-021-agents.spec.ts`: the partner sees money, the super admin sees none, the accountant is refused, and a
   chosen period survives a reload.
6. **Docs.** DEC-SCOPE (AN1–AN14), API §12, RBAC §2, the backlog status line and the QA report.

## Phase 3 review notes

**API**
- A read-only GET with no transaction or lock.
- Two `date` params, validated by `period()`. A malformed date is a FastAPI 422.
- Authorization runs `require_management`, then the operational tier, before any read.
- Response keys are additive, and no existing contract changes.

**Security**
- No agency-scope bypass: the agency CRM routes are untouched.
- The response holds agency names, prefixes and counts only: no student, staff or contact data, and no code or email of a member.
- Money is computed only when `can_view_finance`, so the super admin's request never touches the ledger.
- Queries are built by the ORM, there is no XSS (React escapes), and a GET has no CSRF surface.
- The 366-day cap bounds the cost.
- No audit row is written: the read holds counts only, consistent with mgmt-018/019/020.

**Frontend**
- It reuses `.analytics-form`, `.metric-grid`, `.table-scroll`, `.table` and the AccessUnavailable card.
- The table is a labelled region with `tabIndex=0`, so it can scroll by keyboard on mobile.
- Money columns are absent (not blank) for the super admin.
- The error alert appears on a 5xx or 422.
