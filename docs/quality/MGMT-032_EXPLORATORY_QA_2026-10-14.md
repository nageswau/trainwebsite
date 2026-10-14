# mgmt-032 — Monthly Business Review: exploratory QA (2026-10-14)

- **Build:** `feature/mgmt-032`. Isolated stack `mgmt032` (web `localhost:13132`, api `127.0.0.1:18132`), seeded demo accounts;
  api, web, worker and beat images rebuilt from the branch. The shared test DB also holds reviews drafted by the pytest runs
  (random months 2001–2025).
- **Method:** Playwright (Chromium) scripts acting as partner, super_admin and accountant; the beat task triggered through the real
  Celery worker (`celery call app.worker.draft_monthly_review_task`). The script captured console errors, page errors, HTTP ≥ 500 and
  failed requests, and checked horizontal overflow at 1280×900, 820×1180, 375×812 and 320×640. Screenshots and the downloaded PDF
  were reviewed (PDF text extracted with pypdf). First pass with no code changes.

## First pass — results

| Check | Result |
|---|---|
| Beat task in the real worker (AC1) | **Failed** — `ImportError` (circular import), see QA32-01 |
| Signed out `/management/reviews` | → `/admin/login` |
| Nav: "Monthly business review" | partner: live (BI pillar + sidebar); super_admin, accountant: absent |
| List, Generate form | months newest first, status pills; the form offers the last 24 finished months without a review |
| Duplicate submission (double-click Generate) | 1 POST, opens the month |
| Sections | 1–10 as regions, in §32 order; "Attendance: Not tracked" |
| Finalise with Problems unanswered | "Answer every Problems question before finalising: …" (no request) |
| Save with no change | "No changes to save." |
| Answer > 4,000 characters | the textarea stops at 4,000 (API also 422s) |
| Markup / newlines in an answer | stored and shown verbatim (`Fees <b>late</b> & <script>…`), newline kept; escaped in the PDF |
| Save on a server error (500 injected) | "Something went wrong.", typed text kept |
| Regenerate figures | "Figures regenerated …", answers kept |
| Finalise: confirm dismissed / accepted | stays a draft / "Review finalised. Partners have been sent a link.", editor becomes read-only, unsaved answer saved first |
| `PATCH` a final review | 409 "This review is final and cannot change" |
| PDF (draft and final) | downloads `monthly-review-YYYY-MM.pdf`, "Report downloaded."; 3 pages, the same figures and answers |
| Refresh / Back / Forward on a review | re-renders; Back to the list after generating: **stale**, see QA32-02 |
| Bad months | `2026-13`, `abc` → "That is not a month"; `2030-01`, `2026-10` → "There is no review for … yet"; API generate of the current month → 422 |
| Keyboard | Tab moves answer to answer in order |
| super_admin / accountant | "Access unavailable", no ₹ in `main`; PDF API 403 |
| Overflow at 4 viewports | none — but values hidden on phones, see QA32-03 |
| Console errors / failed requests | none besides the injected 500 |

## Issues found

| ID | Severity | Role | Page | Steps | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA32-01 | High | (beat) | worker | `celery call app.worker.draft_monthly_review_task` | September 2026 drafted | Task failed: `ImportError: cannot import name 'FIRST_CALL' from partially initialized module 'app.services.telecaller_metrics'`; no review. `app.services.ledger` cannot be imported standalone (it only works after `app.main` has loaded the services in the API's order); pytest hid it because conftest imports `app.main` | worker log 10:03:40 UTC |
| QA32-02 | Low | partner | `/management/reviews` | Generate a month, then browser Back | The list shows the new month; the form no longer offers it | Next restores the list from its router cache as it was before; the month is missing and still offered (choosing it again only re-opens the draft) | qa032.js "after back, list has month: 0" |
| QA32-03 | High | partner | `/management/reviews/{month}` at 375 / 320 px | Open a review on a phone | Every figure readable | The label/value tables inherit the shared `.table` `min-width: 650px`: only the labels are on screen, the values sit off to the right (uppercase header styling also hurt reading) | `review-draft-mobile.png` |

## Fixes (Phase 6) and re-verification

| ID | Fix | Test (RED → GREEN) | Browser re-check |
|---|---|---|---|
| QA32-01 | The task imports `app.main` first, so the services load in the API's order (no change to the telecaller modules) | `test_the_beat_task_runs_in_a_fresh_worker_process` (fresh interpreter, `apply()`) failed with the ImportError, then passed | Real worker: `draft_monthly_review_task … succeeded`; September 2026 draft, `updated_by_user_id` null (AC1) |
| QA32-02 | The Generate form re-reads the list (`router.refresh()`) whenever it is shown, and a month reviewed meanwhile drops out of its choice | `re-reads the list when it is shown again …` failed, then passed. A first attempt (refresh before `push`) did not fix it in the browser and was removed | After Back: the new month is listed (1) and not offered (0) |
| QA32-03 | Figure tables use the existing `.table.compact` (the QA18-04 fix) plus `.table.figures` row-label styling | `sizes the two-column figure tables to their content …` failed, then passed | 375 / 320 / 820: the total's value inside the viewport, no overflow; `fixed-mobile.png` |

After the fixes: Playwright `mgmt-032-review.spec.ts` (2) and `mgmt-031-home.spec.ts` (3) pass; no console errors.
