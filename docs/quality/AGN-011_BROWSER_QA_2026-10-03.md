# AGN-011 — Agent deposit through Razorpay: Browser QA pass 1 (2026-10-03)

**Scope:** exploratory browser QA of `AGN-011` (`DEC-SCOPE-058`): the Deposit block on the agency application detail (Master, Staff),
the Overseas Admin "Agent deposits" page, the payment paths (checkout, verify, webhook, receipt) and the shared fee page. **No code was
changed during this pass.**

**Environment:** branch `feature/agn-011-deposit-payment` @ `5c1c73e`; compose project `agn011qa` (web http://localhost:13011, API
http://localhost:18011, migration head `0064_application_deposits`), demo seed plus throw-away QA data (two agencies, Master, Staff
assigned/unassigned students, deposits in every state, an Overseas Admin, a super_admin, a counselor). Razorpay **unconfigured** for the
first part (AC6), then **fake** test keys and webhook secret (local `.env` only) to drive the real provider error, verify with a valid
HMAC and the signed webhook. Isolated headless Chrome (own throw-away profile, CDP 9311) driven by the browser-use CLI (`BU_CDP_URL`);
a page probe recorded console errors, page errors, unhandled rejections, failed resources and every `fetch` with its status. Scripts,
data and screenshots lived in the session scratchpad (not committed). Browser clock IST; container clock UTC.

## Checklist

| # | Area | Result |
|---|---|---|
| 1 | Happy path | Pass — record deposit, payment-unavailable notice, verify → paid + receipt (payer and student on the PDF), webhook → paid, remit, refund |
| 2 | Invalid inputs | Pass with findings — client pattern blocks `abc`; server 422s on the field (amount 0, > 8 digits, before-paid date, over-refund); mass-assigned `status`/`currency` → 422. QA11-03, QA11-07 |
| 3 | Empty states | Pass — "No deposit recorded yet."; "No deposits with this status."; QA11-06 |
| 4 | Server errors | Pass — real provider 502 message, list 500 + Retry, 409 "another member is paying" notice, 429 limit message. QA11-04 |
| 5 | Loading states | Pass — "Opening checkout…" (`aria-busy`), "Loading deposits…" (`aria-busy`) |
| 6 | Cancel / back | Pass with finding — Cancel/Escape on the deposit form return focus; admin Escape on the refund confirmation drops focus (QA11-02). Tab changes use `replaceState`, so Back leaves the page (same as Agent Approvals) |
| 7 | Refresh | Pass — deposit state and admin tab (`?tab=`) survive a reload |
| 8 | Duplicate submission | Pass — triple-click Save → 1 PUT; double-click refund confirm → 1 POST |
| 9 | Unauthorized user | Pass — signed out: pages redirect to login with `next`, APIs 401; another agency and unassigned staff: 404 on every deposit route |
| 10 | Incorrect role | Pass — counselor and Staff: "Access unavailable" page and 403; super_admin reads, no actions, remit 403 |
| 11–13 | Desktop / tablet / mobile | Pass — 1440, 820/768, 375, 320 px: no horizontal overflow (agent detail and admin page) |
| 14 | Navigation | Pass — sidebar "Agent deposits", `aria-current`; bogus `?tab`/`?page` fall back to Paid |
| 15–16 | Success / error messages | Pass with findings — QA11-07, QA11-10 |
| 17 | Broken images | None |
| 18 | Console errors | None (page errors, unhandled rejections, failed resources: none) |
| 19 | Failed network calls | Only the intended ones (422/409/429/502/401 under test) |
| 20 | Unexpected redirects | None |

Also verified: AC1 (scope 404s; checkout amount from the stored deposit), AC2 (webhook paid once; same event id → `already_processed`; a
later `payment.failed` leaves it paid; bad signature 401), AC3 (paid → no Pay button; 409 by API), AC4 (only `overseas_admin`; refund ≤
paid → 422), AC5 (receipt PDF text "Billed to: Priya Staff", "Student: Pavan Pending …"), AC6 (unconfigured → notice, no Pay button,
`configuration_required`, nothing paid). `/payments/mine` has no deposit rows; the student fee page renders (only paid rows existed, so
"Pay Now" was not exercised).

## Findings

| ID | Severity | Role | Page | Reproduction | Expected | Actual | Evidence |
|---|---|---|---|---|---|---|---|
| QA11-01 | **Medium** | Overseas Admin | Agent deposits — Record remittance / Record refund | Between 00:00 and 05:30 IST open Record remittance on a paid deposit, keep the default date (today), enter a reference, Save | Saved with today's date | `422 "The date cannot be in the future"`; the form's default and `max` are the browser's local date, the API compares with the server's UTC date | Browser `Sat Oct 03 2026 00:47 IST`, container `Fri Oct 2 19:17 UTC`; `POST /api/v1/overseas-admin/deposits/{id}/remit` → 422; screenshot `31_tz_remit.png` |
| QA11-02 | Medium (a11y) | Overseas Admin | Agent deposits | (a) Save a remittance that fails (422); (b) save one that succeeds; (c) open the refund confirmation and press Escape | Focus on the error / the announced result / the Save button | Focus falls to `<body>` in all three (keyboard and screen-reader users lose their place) | `document.activeElement` = `BODY` after each step |
| QA11-03 | Minor | Overseas Admin | Agent deposits — Record refund | Type `abc` as the refund amount, a reason, Save | Field-level validation before the confirmation | Confirmation reads "Record a refund of ₹NaN for …"; Yes → `422 "Input should be a valid decimal"` (the agent amount field has a pattern; this one has none) | screenshot `33_refund_nan.png` |
| QA11-04 | Low | Master / Staff | Application detail — Deposit | With the provider failing (502), press Pay deposit repeatedly | Failed provider attempts (no order created) do not use up the attempt limit | The 10th attempt answers `429 "Too many payment attempts for this deposit -- try again later"` for up to an hour after nine 502s | checkout statuses `[502 ×9, 429]`; screenshot `43b_429.png` |
| QA11-05 | Minor | All | Deposit block, admin cards, receipt | View a remitted/refunded deposit | One date format | "Paid on 01 Oct 2026, 00:43 IST" beside "Remitted on 2026-10-02" and "₹20,000.00 on 2026-10-02"; the receipt's "Issued" is the server's UTC date (2 Oct) while the UI shows 3 Oct | screenshot `43c_agent_mobile320.png` |
| QA11-06 | Minor | Overseas Admin | Agent deposits | Open `?page=99` (or stay on a later page after deposits move tabs) | The last page, or pagination to go back | "No deposits with this status." with no pagination controls, though deposits exist | `GET …/deposits?status=paid&limit=20&offset=1960` → 0 items |
| QA11-07 | Minor | Master / Staff, Overseas Admin | Deposit form; refund form | Amount `100000000`; refund amount `abc` | Plain wording ("Enter an amount up to ₹99,999,999.99") | Raw validator text: "Decimal input should have no more than 8 digits before the decimal point"; "Input should be a valid decimal" | 422 bodies |
| QA11-08 | Info | Overseas Admin | Agent deposits | Open the page | One "Agent deposits" heading | Page `h2` and card `h3` both read "Agent deposits" (the existing admin-page pattern) | DOM |
| QA11-09 | Info | All | Receipt PDF | Download a deposit receipt | — | "Reference: agent_deposit" shows a raw code (existing receipt format, also `course_fee` etc.) | receipt text |
| QA11-10 | Minor | Master / Staff | Application detail | Save a deposit when the Deposit block is below the fold (desktop) | The success message is visible where the user is | "Deposit saved." is announced (`role=status`) at the top of the detail, off-screen; focus moves to the Deposit heading (the AGN-010 offer pattern) | screenshot `10b_saved.png` (notice not in view) |

No Critical or High findings. Not fixed in this pass (instruction: report only).

## Pass 2 — fixes and re-verification (2026-10-03, at `881f048` + import-order fix)

`main` @ `ff27fa4` (AGN-012) merged first; AGN-011 is now `DEC-SCOPE-058` with migration `0064_application_deposits` after
`0063_agent_visa_details` (one head; the QA database was re-stamped with `alembic stamp --purge 0062_agent_offer_details` and upgraded,
29 deposits kept). Fixes were test-first (red then green); browser re-check on the rebuilt stack at 01:50 IST (inside the QA11-01 window).

| ID | Fix | Test | Browser re-check |
|---|---|---|---|
| QA11-01 | Future-date rule moved into the remit/refund schemas, reusing `_not_future` (UTC + 1 day, the AGN-008/010 rule) | `test_agn_011_admin.py::test_today_east_of_utc_is_accepted`, UTC + 2 still 422 | Default date 3 Oct at 01:50 IST → remit 200; refund on UTC + 1 → 200; UTC + 2 → 422 |
| QA11-02 | Admin form focuses the error after a failed save, Save after leaving the confirmation; panel focuses the announced result after success and the opener after Cancel | `AdminAgentDepositsPanel.test.tsx` (two QA11-02 tests) | Focus on `#agent-deposits-notice`, on the alert, on Save refund, on Record refund — never `<body>` |
| QA11-03 | Refund amount has the agency form's pattern | `AdminAgentDepositsPanel.test.tsx` QA11-03 | `abc` → "Please match the requested format.", no confirmation |
| QA11-04 | Only attempts that opened a Razorpay order count toward the 10-per-hour limit | `test_agn_011_checkout.py::test_failed_provider_attempts_do_not_use_up_the_limit` | (provider outage not re-staged; covered by the API test) |
| QA11-06 | A page past the end loads the last page | `AdminAgentDepositsPanel.test.tsx` QA11-06 | `?page=99` → "Showing 1–4 of 4" |
| QA11-07 | One amount validator with plain messages for the deposit and the refund | `test_agn_011_schemas.py` | "The amount can be at most ₹99,999,999.99" |

Also fixed: the Playwright admin test passed no landing path to `signIn` (test defect) — `agn-011-deposit.spec.ts` 4/4 and `agn-012-visa.spec.ts`
2/2 pass on the merged stack. **Not changed (minor/informational, existing patterns, owner may schedule):** QA11-05 date formats, QA11-08
duplicate heading, QA11-09 receipt reference code, QA11-10 off-screen "Deposit saved." notice (the AGN-010 offer pattern).
