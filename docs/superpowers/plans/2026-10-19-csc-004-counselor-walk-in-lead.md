# csc-004 — Counselor walk-in lead (plan)

Spec: `docs/superpowers/specs/2026-10-19-csc-004-counselor-walk-in-lead-design.md`. TDD per task.

| # | Task | Test first | Files |
| --- | --- | --- | --- |
| 1 | `create_lead` owner/division for a counselor; `panel` counselor scope | create, distribution, D1, duplicate panel cases | `services/lead_intake.py` |
| 2 | Router: duplicate-check, create, add-enquiry | route + role cases | `api/counselor_walk_in_leads.py`, `main.py` |
| 3 | `NewLeadForm` props (endpoints, initial values, fixed division) | vitest: counselor props post to the counselor URL, source preset, no division select, IT products hidden; telecaller default unchanged | `components/NewLeadForm.tsx` |
| 4 | Counselor page + button | vitest for the button | `app/overseas/counselor/leads/new/page.tsx`, `components/CounselorLeadsPanel.tsx` |
| 5 | Docs | — | DEC-SCOPE-229, API §12EO, RBAC §2.151, RTM, backlog |
| 6 | e2e | `csc-004-walk-in-lead.spec.ts` | web e2e |

Lite regression: `test_tel_005_*`, `test_tel_007_*`, `test_tel_008_*`, `test_tel_018_*`, `test_tel_026_matrix.py`, `test_cns_001_*`;
vitest `NewLeadForm*`, `CounselorLeadsPanel*`; e2e tel-005, tel-018, csc-004.

**Phase 3 review (2026-10-19).** API: POST 201 / GET 200 / 409 duplicate with the existing panel body / 422 / 403 / 401 — the tel-005
contract reused, only the prefix and caller differ. Transactions: the route owns one transaction; distribution runs in tel-007's
SAVEPOINT; CRM sync after commit. Concurrency: tel-005's advisory locks on the person's keys are reused unchanged. Frontend: the shared
form keeps its telecaller defaults (props optional), so telecaller/manager pages render identically; the counselor page uses the same
loading/error/duplicate states. Security: role + division gate; no owner injection (`extra="forbid"`); panel stays PII-free; ids-only
logs. No plan change.
