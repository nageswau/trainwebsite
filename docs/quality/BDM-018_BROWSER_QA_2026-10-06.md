# bdm-018 — browser QA log (2026-10-06)

**Feature:** School onboarding handover + `schools` link (`DEC-SCOPE-083`, migration `0083_bdm_onboarding`).
**Environment:** isolated compose project `bdm018` (web :13018, API :18018); isolated Playwright Chromium in the `bdm018` web-test
container (Browser Use is not installed in this environment). Script: an exploratory Playwright pass driven as a QA engineer (roles,
states, errors, layouts), screenshots under `artifacts/ci/qa/` (not committed).

## Pass 1 — independent exploratory QA (no code changes)

Covered: the happy path (request → create from the request → linked organization); states before and after the MoU; a 500 and a dropped
network on the request; the note cap (1000); duplicate submission (double-click on Send and on Create); refresh; Back; peer BDM, manager,
College BDM, School BDM on admin pages and `/school/*`; the admin queue's loading, reject (empty, spaces, reason), link (unknown code),
Cancel focus, Use-for-new-school prefill and focus, Clear; the edit panel's linked BDM; the BDM's notices; 320 / 375 / 768 / 1366 px.

Results: no page errors; console errors only for the deliberately triggered 4xx / 5xx responses; no horizontal overflow at any width;
double-click made one request and one School; every refused role got 403 / 404 as designed.

| ID | Severity | Role / page | Steps | Expected | Actual | Outcome |
|---|---|---|---|---|---|---|
| QA18-01 | Medium | School BDM, organization page; Overseas Admin, queue | Request (or reject / link) while the server answers 500 | Says the outcome is unknown and to reload before retrying | "Something went wrong." | **Fixed** (test-first): "The request could not be confirmed. Reload the page to check before trying again." |
| QA18-02 | Low | Overseas Admin, `/overseas/admin/schools` | 75+ pending requests, Show more × 4 | The create form stays usable beside the queue | The page grew very tall | **Fixed** (test-first): the list scrolls in its own keyboard-reachable region (`min(70vh, 720px)`) |
| QA18-03 | Low | School BDM, notifications | Create the School from the request with the prefilled name | Readable notice | "St Mary is now linked to St Mary (CODE)" | **Fixed** (test-first): "ORG-… · St Mary is now onboarded (School ID CODE)." (the School is named only when it differs) |

## Pass 2 — re-verification on the merged HEAD (main @ `a38955d5` merged)

QA18-01: the 500 message reads as fixed. QA18-02: 120 rows, list height 630 px, scrolls; PageDown scrolls it from the keyboard. QA18-03:
the notice reads "… is now onboarded (School ID …)". The full pass-1 scenario set repeated with the same results; Playwright
`bdm-018-school-handover.spec.ts` passed.
