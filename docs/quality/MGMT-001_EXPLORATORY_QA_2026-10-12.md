# mgmt-001 — exploratory QA (2026-10-12)

Stack: Docker Compose project `mgmt001` (web `localhost:13401`, api `127.0.0.1:18401`), fresh seed (`partner.one@`, `partner.two@`,
`accountant@edusphere.local`). Browser: Playwright Chromium (headless), desktop 1366×900, tablet 820×1180, mobile 375×812.
Independent pass first (no code changes), scripted in the session scratchpad (`qa001.js`); then `tests/e2e/mgmt-001-command-center.spec.ts`.

## Result

43 checks, 42 passed. The one "failure" was the script's text expectation; the behaviour it found is the pre-existing QA-01 below.

| Area | Checked | Result |
|---|---|---|
| Happy path | Partner signs in at `/admin/login` → `/management`; six pillars; role label "Partner"; name in header | Pass (all 3 viewports) |
| Second partner | Partner 2 signs in separately, same Command Center, own name | Pass |
| Accountant | Lands on `/management`; Sales/Finance/People only; no Investments/capital; label "Accountant" | Pass |
| Super admin | "Management Command Center" sidebar link; operational pillars only; no Finance, no partner-only entries | Pass |
| Wrong role | IT admin, BDM manager → "Access unavailable / Management access required", link to their own dashboard | Pass |
| Signed out | `/management?x=1` → `/admin/login?next=%2Fmanagement%3Fx%3D1`; sign-in follows `next` | Pass |
| Wrong portal | Partner at `/it/login` → "sign in at /admin/login" | Pass |
| Refresh / back | Reload keeps the page; Back from an admin page returns to `/management` | Pass |
| Unknown sub-path | `/management/unknown` → 404 | Pass |
| Layout | No horizontal overflow at 1366/820/375; mobile menu holds "Command Center"; no broken images | Pass |
| Console / network | No console errors, no failed requests, no 5xx (all viewports, all roles) | Pass |
| Users form | Role list offers partner + accountant; duplicate email → "Email already exists" (no second account) | Pass |
| e2e | `mgmt-001-command-center.spec.ts` 3/3, `tel-001-telecaller-roles.spec.ts` 4/4 (sign-in copy updated) | Pass |

## Issues

| ID | Severity | Role | Page | Steps | Expected | Actual | Disposition |
|---|---|---|---|---|---|---|---|
| QA01-01 | Low | partner (any non-super-admin global role) | `/admin/users` | Sign in as a partner, open `/admin/users` | Refusal with a way back to the user's dashboard | Bare "Super Administrator access required" card, no link (`app/admin/[module]/page.tsx:82`) | **Pre-existing**, same for BDM / telecaller / placement managers and partnership heads. Not caused by mgmt-001; not fixed (out of scope). The API refuses correctly (403) |
| QA01-02 | Info | super_admin | `/admin/users` create form | Choose Division "IT", Role "partner" | Only valid roles offered | The super admin's role list is the union of all divisions (pre-existing, as for `partnership_head`); the server refuses with 422 "Role is not valid for the selected division" | Pre-existing design; no change |
| QA01-03 | Info | partner | `/admin/login` while signed in | Visit the sign-in page while signed in | — | The sign-in form shows (same for every role) | Pre-existing; no change |

No issue was caused by mgmt-001, so Phase 6 had nothing in scope to fix.

Screenshots (session scratchpad, not committed): `partner-{desktop,tablet,mobile}.png`, `partner-mobile-menu.png`, `accountant-desktop.png`,
`super-admin.png`, `it-admin-refused.png`, `bdm-manager-refused.png`, `partner-admin-users.png`, `users-form.png`.
