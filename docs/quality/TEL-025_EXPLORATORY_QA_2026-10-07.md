# tel-025 — Exploratory QA (2026-10-07)

**Stack:** isolated compose project `tel025` (web :3125, api :8125, email disabled), branch `feature/tel-025`. Chromium via Playwright in
the `web-test` container. **Data:** seeded throwaway accounts (two runs, prefixes `QA` / `QB`): three telecaller managers; IT telecallers
Anil (5 open leads, 1 closed, 1 converted, 1 open follow-up, 1 open appointment, 1 city rule), Bina and Chetan; an Overseas telecaller,
Olga; an inactive "Legacy" telecaller holding 2 open leads; and Dina, reporting to another manager, with 1 open lead.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Plain `PATCH /admin/users` deactivation of Anil | `422` "This telecaller has 5 open leads. Deactivate them from the Telecallers page, choosing who takes over" ✔ |
| 2 | Deactivate group: loading → "Open work: 5 open leads, with 1 open follow-up and 1 appointment." | ✔ group takes focus |
| 3 | Confirm disabled until a choice (AC3); disabled until a telecaller is picked | ✔ |
| 4 | Picker: only active IT telecallers, never Anil, the Overseas telecaller or the inactive one | ✔ |
| 5 | Escape closes the group; focus returns to Deactivate | ✔ |
| 6 | Tablet 768 / mobile 390 with the group open: no horizontal scroll, the row stacks as a card | ✔ |
| 7 | Double-click on Confirm (duplicate submission) | one deactivation; notice "Deactivated … 5 open leads now with … Bina" ✔ |
| 8 | Anil's existing session after deactivation | `GET /telecaller/me` `401` ✔ (D1) |
| 9 | Inactive row → Reassign open work with nothing left | "has no open leads." + Close ✔ |
| 10 | Legacy inactive → unassigned queue | "2 open leads from … moved to the IT unassigned queue." ✔ (LC4) |
| 11 | Move Dina to Overseas, lead to Chetan | "Moved … to the Overseas team; they sign in again there. 1 open lead now with … Chetan." Row shows Overseas ✔ |
| 12 | Telecaller managers card: Meena "5 telecallers"; confirm disabled until a replacement; Meena not offered | ✔; "5 telecallers now report to … Kiran." |
| 13 | Refresh after the changes | list reloads ✔ |
| 14 | `it_admin` at `/it/admin/telecallers` | no Move team, no Overseas rows, no managers card; `POST …/deactivate` on an Overseas telecaller `403` ✔ |
| 15 | Console errors / unexpected failed API calls | none (the only 4xx are the deliberate 422/403/401 probes) ✔ |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Status |
|---|---|---|---|---|---|---|---|
| QA-T25-01 | Minor | super_admin | Telecallers | Move a telecaller to another team with a new reporting manager | The Telecaller managers card's counts refresh with the list | The card kept its old counts until a page reload (it reloaded only after its own actions) | **Fixed**: the card takes the page's reload counter (`version`); component test added |

Not defects: the manager list shows many test-run managers, because the stack database is shared with the api-test runs. The "IT" and
"Overseas" options seen by the role query belong to the Create form's team select.
