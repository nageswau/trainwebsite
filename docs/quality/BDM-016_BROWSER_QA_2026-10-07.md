# bdm-016 — Browser QA (2026-10-07)

- **Build:** `worktree-bdm-016`, Docker Compose project `bdm016` (api 127.0.0.1:18016, web 127.0.0.1:13016), migration head
  `0096_bdm_targets`, seeded with `python -m app.seed`.
- **Tool:** isolated Playwright Chromium. Browser Use is not installed on this machine (as in the earlier BDM sessions); the scripted
  exploratory pass stands in for it until the owner accepts or runs it.
- **Accounts:** created and activated through the admin API per run: a manager with a School, an Agent and a College BDM; a manager with
  no team; the seeded super admin.

## Pass 1 — exploratory (no code changed)

| # | Area | Result |
|---|---|---|
| 1 | Happy path: nav "Targets" → team list → Set targets → save | Pass — "Saved 1 target.", achieved and % shown, values kept on reload |
| 2 | Invalid inputs: −3, 100001 | Pass — "Meetings target must be a whole number from 0 to 100000." before any request; focus on the message |
| 3 | Empty states: manager with no team; BDM with no targets | Pass — "No active BDMs report to you yet." / My Day "No targets set for this month yet." |
| 4 | Not tracked | Pass — School 1 (New Agents), Agent 5, College 1 (Internship Students), never 0 |
| 5 | Server errors: aborted PUT, 500 | Pass — "The request did not complete…" / "Something went wrong."; button re-enabled; retry saves and clears the error |
| 6 | Loading state on navigation | **QA16-02** — no loading state |
| 7 | Cancel / Escape on the copy confirm | Pass — back to "Copy last month's targets" |
| 8 | Refresh / Back | Pass — saved values persist; Back returns to the team list |
| 9 | Duplicate submission (double click) | Pass — one PUT |
| 10 | Unchanged save | Pass — "No target changed.", no request |
| 11 | Keyboard: type in an input, Enter | Pass — saves |
| 12 | Wrong role: BDM on the manager page; signed out | Pass — "Access unavailable — This page is for BDM managers."; `/admin/login?next=%2Fbdm%2Fmanager%2Ftargets` |
| 13 | Month URL: `2026-13`, `abc`, `2099-01` | Pass — this month with "That isn't a valid month"; 2099 read-only "Targets can be set up to 12 months ahead." |
| 14 | Member id `not-a-uuid` | **QA16-01** |
| 15 | super_admin past month | Pass — editable, Copy offered (AC4) |
| 16 | Copy with nothing to copy | Pass — "Nothing to copy: every target from September 2026 is already set or there were none." |
| 17 | XSS in a BDM name (`<b>x</b>`, `<i>…</i>`) | Pass — rendered as text |
| 18 | Layout 320 / 375 / 820 / 1366 px (team, member, My Day) | Pass — no horizontal page overflow; the KPI table scrolls inside `.table-scroll`; no broken images |
| 19 | Console / failed network | Only the deliberately aborted / 500 requests; no page errors, no unexpected 4xx/5xx |
| 20 | My Day card | Pass — "Schools Contacted — 0 / 7 (0%) · Proposals — 0 / 5 (0%)" |

### Findings

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA16-01 | Low | bdm_manager | `/bdm/manager/targets/[bdmId]` | open `/bdm/manager/targets/not-a-uuid` | "BDM not found" (the bdm-015 detail page's rule) | "Access unavailable [object Object]" | `GET /api/v1/bdm/manager/targets/not-a-uuid` → 422 (Pydantic detail list) |
| QA16-02 | Low | bdm_manager | `/bdm/manager/targets`, `/[bdmId]` | navigate to either page | the manager portal's loading skeleton (as Activities, MoUs, …) | the previous page stays until the server render finishes | no `loading.tsx` |

## Pass 2 — fixes (TDD) and re-check

| ID | Fix | Test | Browser re-check |
|---|---|---|---|
| QA16-01 | the page checks `isUuid(bdmId)` before calling the API → `accessDenied(user, "BDM not found")` | `BdmTargetsPages.test.tsx` "QA16-01" (red → green) | "Access unavailable — BDM not found" |
| QA16-02 | `loading.tsx` for both pages (`PortalLoading`, manager nav) | `BdmTargetsPages.test.tsx` "QA16-02" (red → green) | "Loading…" skeleton with the manager nav shown during navigation |

Playwright `tests/e2e/bdm-016-targets.spec.ts` re-run after the fixes: 1/1 pass. No open findings.
