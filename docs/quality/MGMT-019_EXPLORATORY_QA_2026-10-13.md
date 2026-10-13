# MGMT-019 — Telecalling dashboard: exploratory QA (2026-10-13)

Stack: isolated Docker Compose project `mgmt019` (web `http://localhost:13019`, api `127.0.0.1:18019`), seeded demo accounts, shared
test DB (125 telecallers incl. backend-test rows). Browser: Playwright Chromium (scripted exploratory pass + `mgmt-019-telecalling.spec.ts`).
Spec: `docs/superpowers/specs/2026-10-13-mgmt-019-telecalling-dashboard-design.md`.

## Coverage

| Area | Result |
|---|---|
| Happy path (partner from Command Center → Sales "Leads & calls"; People "Telecallers" → `#telecallers`) | Pass |
| Desktop 1366 / tablet 820 / mobile 390 | Pass — no page-level horizontal overflow; wide tables scroll inside focusable regions |
| Invalid input (from > to, > 366 days, future end, malformed date in address) | Pass — API wording shown; malformed date dropped |
| Refresh / back / "This month" / duplicate Apply | Pass after QA19-01/02 |
| Roles: partner, super_admin (200); accountant, telecaller_manager (access card); signed out (→ `/admin/login?next=`) | Pass |
| Console errors, failed / 5xx requests, broken images | None |
| AC1 on screen: Company row = IT + Overseas | Pass (e2e) |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual (before fix) | Status |
|---|---|---|---|---|---|---|---|
| QA19-01 | Medium | partner | `/management/telecalling` | Open with no dates in the address | Inputs show the period on screen (1st of month → today) | Both inputs blank (`dd-mm-yyyy`) while the text said 01–13 Oct | Fixed — inputs default to the API's `date_from`/`date_to`; vitest + e2e |
| QA19-02 | Medium | partner | same | Apply a period, then click "This month" or Back | Inputs reset to the shown period | Uncontrolled inputs kept the old dates after the client navigation | Fixed — form keyed on the address; vitest (`rerender`) + e2e |
| QA19-03 | Low | partner | same | Read the chain | Shares that read as conversion | "Counseling 10 — 250% of Interested": bookings are not a subset of Interested moves | Fixed — each later step is a share of Calls (spec TC11 updated); pytest + vitest |
| QA19-04 | Low | partner | same, desktop | Scroll below the chain | Headings spaced from the card | "By team" flush against the chain card | Fixed — `.telecalling-section-title` margin; vitest |

No issue outside mgmt-019 was found or changed.
