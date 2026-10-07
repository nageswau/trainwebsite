# bdm-019 — Browser QA (2026-10-07)

- **Stack:** compose project `bdm019` (API `127.0.0.1:18019`, web `127.0.0.1:13019`) built from `feature/bdm-019`; database shared with the
  focused pytest run, demo data from `python -m app.seed`.
- **Browser:** isolated Playwright Chromium (Browser Use is not installed in this environment; the same stand-in bdm-005/018/020 recorded).
  Two throwaway exploratory drivers were run and deleted; the committed scenario is `tests/e2e/bdm-019-agent-handover.spec.ts`.

## Pass 1 — independent exploration (no code changed)

| # | Scenario | Role | Result |
|---|---|---|---|
| 1 | Card before the agreement | BDM | "Available once the agreement is signed.", no button; API `422` |
| 2 | Agreement signed (MoU) → ready, Cancel | BDM | "Ready to hand over…"; Cancel returns focus to *Request onboarding* |
| 3 | Request with a note containing `<script>`; double-click Send | BDM | one request; note rendered as text in the admin queue (no element) |
| 4 | Refresh | BDM | pending state and "Agent Onboarding — Current" persist |
| 5 | Manager view | `bdm_manager` | read-only card (0 buttons); request `403`; agent queue `403` |
| 6 | Wrong module | School BDM | organization `404`, "Organization not found" |
| 7 | Admin queue: empty code, unknown code | `overseas_admin` | browser "Please fill out this field."; "No agent organization has that code" (`422`) |
| 8 | Reject with a reason | `overseas_admin` → BDM | notice "Request from ORG-… rejected. The BDM has been told why." (focus moves to it); BDM sees the reason and *Request again* |
| 9 | Link, link again | `overseas_admin` | `200`, then `409` |
| 10 | Approve then suspend the agency | BDM | "Status: Suspended.", agent status **Inactive**; commission "Not shown to BDMs"; no agency owner name on the page; agency students `403` |
| 11 | Server error on request / link (`500` mocked) | BDM / admin | "The request could not be confirmed. Reload the page to check before trying again." |
| 12 | Queue load failure (`500` mocked), Try again | admin | "Unable to load onboarding requests." → list shown after retry |
| 13 | Layout 320 / 375 / 768 / 1280 px | BDM pending, admin Agents page, BDM linked | no horizontal overflow; no broken images |
| 14 | Console / network | all | only the deliberate `422` from #7 |

### Issues

| ID | Severity | Role / page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|
| QA19-01 | — | admin, `/overseas/admin/agents` | Reject, read the status at once | notice | empty in the first driver | **Not reproducible**: the driver read before the response; with a wait the notice is shown (#8) |
| QA19-02 | Low | BDM, organization page | Link an agency to an organization with no agent details entered | "Number of staff" shows the live count (backlog L307) | "No agent details yet." — the live count is hidden; with no entered value it would read "N live (— entered)" | **Fixed** test-first (`Bdm019AgentOnboarding.test.tsx` QA19-02): the details show once linked; "N live", "(M entered)" only when entered. Re-verified in the browser: "0 live" |

## Pass 2 — after the fix

`bdm-019-agent-handover.spec.ts` and `bdm-018-school-handover.spec.ts` (regression): **2 passed** on the rebuilt web image.
