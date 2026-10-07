# tel-026 — exploratory QA (2026-10-07)

Feature: §22 permission matrix + cross-role sweep (`DEC-SCOPE-115`). Stack: isolated compose project `tel026` (web :3066, API :8066,
seeded with `app.seed`), SMTP blanked. Browser: an isolated Edge profile driven over CDP (browser-use), plus Playwright in `web-test`.
Accounts: a QA telecaller manager, an IT telecaller reporting to them with one assigned lead, an IT counselor (created through
`/admin/users` and activated with the development welcome token).

## Scenarios run

| # | Role | Scenario | Result |
|---|---|---|---|
| 1 | telecaller | Sign in at `/it/login` → lands on `/telecaller/dashboard`; sidebar = Dashboard, My Leads, Follow-ups, BDM requests, Notifications, Profile | Pass |
| 2 | telecaller | Open `/telecaller/manager/reports`, `/targets`, `/performance`, `/leads`, `/assignment`, `/products` | Pass: "Access unavailable" card each time, no data |
| 3 | telecaller | Open `/admin/telecallers`, `/it/admin/telecallers` | Pass: access card ("Super Administrator / IT Administrator role required") |
| 4 | telecaller | Open own lead `/telecaller/leads/{id}` | Pass: lead detail with Call / WhatsApp / Change stage / Assign to counselor |
| 5 | telecaller | Access card at desktop 1366, tablet 820, phone 390 | Pass: no horizontal scroll; "Go to your dashboard" returns to `/telecaller/dashboard` |
| 6 | manager | `/telecaller/manager/team`, the report's lead, `/telecaller/manager/reports` | Pass: data shown; sidebar holds Targets, Performance, Reports |
| 7 | manager | `/telecaller/dashboard`, `/telecaller/leads` | Pass: "Telecaller role required" |
| 8 | IT counselor | The telecaller's lead URL, `/telecaller/leads`, `/telecaller/manager/team` | Pass: access card; own `/it/counselor/leads` loads |
| 9 | signed out | `/telecaller/manager/reports`, `/telecaller/dashboard` | Pass: redirected to `/admin/login?next=…` and `/telecaller/sign-in?next=…` |
| 10 | all | Console errors during the Playwright run (403s of refused pages excluded) | Pass: none |

API side: `test_tel_026_matrix.py` — 106 routes in 108 rows × 11 roles, the 21 §22 denied calls and the no-delete checks.

## Findings

| ID | Severity | Role / page | Finding | Disposition |
|---|---|---|---|---|
| QA26-01 | Cosmetic | telecaller on `/telecaller/manager/reports` and `/performance` vs `/targets`, `/leads` | The access card reads "Telecaller **Manager** role required" on the tel-023/tel-024 pages and "Telecaller **manager** role required" on the others | Pre-existing (tel-023 / tel-024 page props), not caused by tel-026; left unchanged — not in this item's scope |

No in-scope defect: nothing to fix in Phase 6.

## As-built observations recorded in RBAC §2.41 (not defects)

- `POST /telecaller/leads/{id}/enquiries` accepts any lead for a telecaller or manager (tel-005 I5, append-only, grants no read).
- A manager's counselling booking is `403` on the role before the scope (tel-016 §2.23).
- A manager's import report list is their own uploads (tel-006 R11).

## Test-data note

The first run of the new fixture wrote tel-012 scripts whose steps carried an unknown `body` key, which made `GET /telecaller/scripts` fail
response validation for every later test in the shared `tel026` test database. The fixture now writes `{"title", "notes"}` and the 858
rows were repaired in that isolated database (`UPDATE tel_scripts … WHERE name LIKE 'T26 script %'`); tel-012's scripts tests pass after it.
