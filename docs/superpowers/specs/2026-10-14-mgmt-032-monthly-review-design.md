# mgmt-032 — Monthly Business Review (design)

- **Feature ID:** `mgmt-032` · **Decision:** `DEC-SCOPE-220` (MR1–MR14, recommended defaults, `UNVERIFIED`; answers backlog Q-31).
- **Evidence:** `EVID-017` §32 (L1241–L1361: "At the end of every month, automatically generate: EDUSPHERE MONTHLY BUSINESS REVIEW",
  10 sections). Scope authority `DEC-SCOPE-186` M12 (`EXPLICIT_APPROVAL`): a beat job on the 1st (IST) drafts the previous month;
  computed sections are frozen as a snapshot; partners add the Problems and Next-Month narrative, then finalise; on screen + PDF
  (`reporting/pdf.py`); emailed to partners on finalise.
- **Backlog:** `MANAGEMENT_COMMAND_CENTER_BACKLOG.md` §mgmt-032. Acceptance: (1) the draft for September is created on 1 October;
  (2) figures are frozen after finalise even if the ledger changes; (3) the PDF matches the screen. Negative: finalising without the
  Problems section → 422. Edge: regenerating a draft (allowed before finalise).
- **Dependency:** mgmt-031 (merged, #278) and every section's source (mgmt-009, 010, 011, 012, 014, 026 — all merged).
- **Approval:** the owner's standing instruction for feature sessions is to proceed with recommended answers, so every MR point is a
  recommended default, `UNVERIFIED` until confirmed.

## Understanding

Once a month the partners want one document that says how the business did: revenue, expenses, profit, sales, partnerships, people,
marketing and investments for the month that just ended, plus their own words on problems and next month. The figures must not drift
after the partners sign the review off, so they are copied into the review when it is drafted (a snapshot), not read live. Only
partners see it: it carries finance and investment figures (partner-only per M2/M13).

## Approaches

1. **Stored snapshot row per month (chosen).** `monthly_reviews` holds the month, the status, the computed sections as JSON and the
   partner-written narrative. The beat job and a partner's "Generate" both call one `services/monthly_review.generate`. The screen
   and the PDF both render the same stored document, so they cannot differ (AC3) and a later ledger change cannot move them (AC2).
2. Live figures with a "finalised at" timestamp and recomputation as of that date. The ledger allows back-dated entries and
   reversals, so a recomputation can change. Fails AC2. Rejected.
3. Store only the PDF bytes. The screen would then need its own rendering of live data, and narrative editing would mean re-rendering
   a file. Rejected.

## Decisions (MR1–MR14, `UNVERIFIED`)

| # | Point | Recommended default |
|---|---|---|
| MR1 | Access | Partner only (M2/M13: it contains finance + investments). super_admin and the accountant `403` "Only partners can open this"; other roles `403` "Management access required"; signed out `401`. The same check on every route, the PDF included |
| MR2 | Storage | `monthly_reviews`: `month` (the 1st, unique), `status` draft/final, `snapshot` JSONB (sections 1–8 + 10's computed parts), `narrative` JSONB (the 9 partner-written answers), `generated_at`, `finalised_at`, `finalised_by_user_id`, `updated_by_user_id` (null when only the beat job wrote it). Migration `0163_monthly_reviews` |
| MR3 | Beat (Q-31 hour) | Daily is not needed: `crontab(day_of_month=1, hour=0, minute=30)` UTC = 06:00 IST on the 1st. It drafts the previous IST month only if no review exists for it (never overwrites a draft's figures or narrative); a rerun or a second beat process is a no-op (unique month) |
| MR4 | Manual generate / regenerate (Q-31) | `POST /management/reviews/{month}/generate`: creates the draft if missing (`201`), or re-snapshots an existing draft (`200`, narrative kept). A final review → `409`. The month must be finished (before the current IST month), else `422` "Only a finished month can be reviewed". This covers a missed beat run and the backlog's "regenerate a draft" edge case |
| MR5 | §1 Revenue | The mgmt-009 P&L for the month (partner view, university commission included per M3): Abroad Education, IT Training, Recruitment, and **Other** = School projects + Other + Shared, then the total |
| MR6 | §2 Expenses | The mgmt-010 expense heads for the month in §32 order: Salaries, Rent, Marketing, **Operations (technology)** = the Technology head (internet, software; §32's "Operations" has no head of its own), Trainers, Travel, Commissions, Other, then the total |
| MR7 | §3 Profitability | The mgmt-009 total: gross revenue, total expense, net profit (contribution), profit margin % (none without revenue) |
| MR8 | §4 Sales | Leads: enquiries created in the month (mgmt-012 K3 total). Students: new IT students (the mgmt-026 PN5 KPI). Applications, Enrollments, Placements: the mgmt-026 PN5 KPIs for the month |
| MR9 | §5 Partnerships | New agents, New schools (school MoUs signed), New universities (moved into a partner stage), New companies (first past Interested): the mgmt-026 PN5 KPIs |
| MR10 | §6 People (Q-31) | Employees: the month's mgmt-011 salary headcount (none if no department entered). Department performance: each entered department's headcount and total cost (mgmt-011 R6). **Attendance: "Not tracked"** (no staff attendance model; Q-31). Productivity: revenue ÷ headcount (none without headcount) |
| MR11 | §7 Marketing | The mgmt-012 K1–K7 totals for the month: budget, spend, leads, customers, conversion %, revenue, ROI % |
| MR12 | §8 Investments | mgmt-014 (cancelled excluded): New investments = count and amount invested in the month; Total investment, Return and ROI = every investment invested on or before the month's last day |
| MR13 | §9 + §10 narrative, finalise | Partners write §9 (What went wrong? What is delayed? What needs management intervention?) and §10 (New initiatives, Hiring, Investments, Partnerships), each up to 4,000 characters, via `PATCH` (draft only). §10 also shows two computed parts: **Targets** = the next month's mgmt-026 KPI targets, **Budget** = the next month's mgmt-012 marketing budget total. `POST …/finalise` needs all three §9 answers (else `422` naming them), freezes the stored snapshot as it is (no recomputation at finalise), records who and when; afterwards every write is `409` "This review is final and cannot change" |
| MR14 | Email, PDF, audit | On finalise every active partner gets an in-app notification + email (`queue_deliveries`, email channel only) with **a link to the review page — no figures, no attachment** (the backlog's security note). `GET …/pdf` renders the stored review (draft PDFs are marked "Draft"), `Cache-Control: no-store`. Audit kind `mgmt.review` (partner-only): generate = create, regenerate / narrative = update (field names only), finalise = complete, PDF = download. Nav: the BI entry "Monthly business review" goes live at `/management/reviews` (partner-only) |

## Architecture

- **Model / migration:** `MonthlyReview` in `models.py`; `0163_monthly_reviews` (guarded create, like 0162; downgrade refuses
  while a final review exists).
- **Service:** `services/monthly_review.py` — `compute(db, month)` (pure composition of the existing service calls, as the partner
  sees them), `generate(db, month, actor)` (insert-or-refresh under a row lock; `IntegrityError` on a concurrent insert re-reads),
  `update_narrative`, `finalise`, `out(review)`, `run_monthly_reviews(today)` for the beat. No new metric definitions.
- **Routes:** `api/management_reviews.py`, prefix `/management/reviews`: `GET ""` (list, newest first), `GET /{month}`,
  `POST /{month}/generate`, `PATCH /{month}`, `POST /{month}/finalise`, `GET /{month}/pdf`. Month path pattern `PLAN_MONTH`.
- **PDF:** `reporting/pdf.render_monthly_review(review)` — pure, from the same dict the screen gets.
- **Worker:** `generate_monthly_review_task` + beat entry `mgmt032-monthly-review`.
- **Web:** `/management/reviews` (list + "Generate a review" month form), `/management/reviews/[month]` (the 10 sections,
  the narrative editor for drafts, regenerate, finalise with confirmation, PDF via `ReportDownloadButton`).
  `lib/managementReviews.ts` (types, labels, formatting); components `ManagementReviews`, `ManagementReview`,
  `ManagementReviewEditor`.

## Error handling, concurrency

- Every write locks the review row (`FOR UPDATE`) before checking its status, so a finalise racing a narrative save serialises and
  the loser sees `409`. Two generates of a new month: the unique month makes one insert fail; it re-reads and refreshes instead.
- Page states: loading via server render; empty list ("No reviews yet"); `404` month → "not generated yet" with a Generate button;
  API failure → `form-error` alert; `401/403` → the access card.

## Testing

- **API (pytest):** access matrix on every route; generate (201 / 200 refresh keeping narrative / 409 final / 422 current month);
  each section equals its source endpoint for the month (P&L, expenses, marketing, salaries, investments, plan KPIs); AC2 (ledger
  entry added after finalise does not move the review); finalise 422 without Problems; PATCH after final 409; the beat run on
  1 October drafts September once (AC1) and is idempotent; partners notified + email delivery queued on finalise; PDF content type
  and that its text carries the screen's figures (AC3); audit rows; migration up/down.
- **Web (vitest):** list states; section rendering (money formatting, "Not tracked", none values); editor save/finalise/validation.
- **e2e (Playwright):** a partner generates, writes the narrative, finalises, downloads the PDF; super_admin and the accountant
  see the access card.
