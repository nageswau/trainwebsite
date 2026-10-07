# bdm-014 — Browser QA: My Day (2026-10-07)

**Build under test:** `worktree-bdm-014` @ `dabc1e8b` (web/API images built from it), compose project `bdm014` (web `localhost:3214`, API
`localhost:8214`, DB at `0091_lead_appointments` — bdm-014 adds no migration — seeded).
**Tools:** Browser Use is not installed on this machine (as for bdm-007/008/011/013). The independent pass used throwaway Playwright
scripts (kept outside the repository) in the `web-test` container: an isolated headless Chromium context per role, recording console
errors, page errors, 4xx/5xx responses, horizontal overflow, clipped elements and broken images, plus full-page screenshots. The repo spec
`tests/e2e/bdm-014-my-day.spec.ts` ran with `bdm-001` and `bdm-013` in the same container.
**Accounts:** throwaway users created through the admin API: a College, a School and an Agent BDM, their BDM manager, and super_admin.

## Coverage (20 requested areas)

| # | Area | Result |
|---|---|---|
| 1 | Happy path | College BDM with data: "Today's appointments: 1" with "10:45 AM — ABC College…"; Upcoming travel "11 Oct — Hyderabad → Vijayawada / 1 appointment scheduled", "15 Oct — Hyderabad → Bangalore / 1 appointment scheduled", "All travel (2)"; Follow-ups "3 College follow-ups", "2 Agent follow-ups", "1 follow-up without an organization"; tiles College meetings 1, Placement-cell 1, Student leads 1, MoU follow-ups "Not tracked yet" |
| 2 | Invalid inputs | No inputs on the page (no query parameters, read-only GET). API: no parameters accepted beyond the session |
| 3 | Empty states | New College / School / Agent BDMs: "No appointments today." + Book an appointment, "No upcoming travel." + Plan a trip, "No follow-ups due." + View follow-ups; tiles show 0, untracked ones labelled |
| 4 | Server errors | A failed `/bdm/my-day` read after the profile gate shows "Unable to load your day." + Try again (unit test `BdmPages.test.tsx`); not forced in the browser — the API can't be made to fail for one route without code changes |
| 5 | Loading states | `loading.tsx` skeleton shown during navigation (seen in the first screenshots); content in 354–412 ms |
| 6 | Cancel / back | Appointment link → `/bdm/appointments/{id}`; Back → `/bdm/my-day` |
| 7 | Refresh | Reload at every width re-renders the same data |
| 8 | Duplicate submission | Not applicable — no form or write on My Day |
| 9 | Unauthorized user | Signed out → `/bdm/sign-in?next=%2Fbdm%2Fmy-day` |
| 10 | Incorrect role | BDM manager → redirected to `/bdm/manager/dashboard` (no error shown); super_admin → "Access unavailable" card with Go to your dashboard. API: manager `403` "BDM role required", no profile `403`, signed out `401` (pytest) |
| 11 | Desktop layout | 1440 / 1024: three cards side by side, overview tiles 4 per row; overflow 0, nothing clipped |
| 12 | Tablet layout | 768: cards reflow, tiles 2 per row; overflow 0 |
| 13 | Mobile layout | 375 / 320: one column, a long organization name wraps; overflow 0, nothing clipped |
| 14 | Navigation | Sidebar "My Day" current; appointment, trip, All travel and View follow-ups links reach their pages; View profile → `/bdm/profile` |
| 15 | Success messages | Not applicable (read-only) |
| 16 | Error messages | Inline load error (unit-tested); role refusals as in #10 |
| 17 | Broken images | 0 on every page checked |
| 18 | Console errors | 0 (BDMs, manager after redirect, super_admin, signed out) |
| 19 | Failed network calls | 0 besides the expected `403` from `/bdm/me` behind the manager redirect and the super_admin card |
| 20 | Unexpected redirects | None; the only redirects are the manager → dashboard and signed out → sign-in |

Keyboard: Tab order is sidebar → View profile → each appointment link → each trip link → All travel → View follow-ups, the same pattern as
the calendar page; every control is a real link.

Each BDM type showed exactly its eight tiles in source order (Agent T-A1…T-A8 with "Agents awaiting onboarding" untracked; School
T-S1…T-S8, all tracked; College T-K1…T-K8 with "MoU follow-ups" untracked).

## Issues

None caused by bdm-014. Two observations, both tooling artifacts and not defects:

- **QA14-OBS-1** — the first script read the URL right after clicking a trip link and saw `/bdm/my-day`; a re-run waiting for the URL
  showed the link reaches `/bdm/travel/{id}` ("Hyderabad → Vijayawada").
- **QA14-OBS-2** — the first screenshots caught the `loading.tsx` skeleton (the script waited for network idle, not for content); the
  re-run waited for the "Today's appointments" heading and measured overflow on the rendered page (0 at all five widths).

## Repository specs

`bdm-014-my-day`, `bdm-001-bdm-profile`, `bdm-013-calendar`: 9 passed (the bdm-014 spec's first run failed on its own two meetings
30 minutes apart tripping the 60-minute overlap guard; the spec now spaces them 90 minutes apart).
