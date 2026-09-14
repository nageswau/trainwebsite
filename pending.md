# EduSphere — Session Handoff (2026-09-03)

> ### ▶ NEXT ACTION
> **Ad hoc, out-of-loop fix, 2026-09-05:** the user shared raw UAT/tester feedback (a
> WhatsApp message covering University Representative, Administrator, Education Agent,
> Students, HR, Trainer) rather than naming a Feature ID. Logged every item first
> (`RAID.md` I-12–I-16, `PRD_OPEN_ITEMS.md` items 56–60) before touching any code, per
> `CLAUDE.md` NO-ASSUMPTION MODE, then the user said "proceed with first one" (`I-12`,
> University Rep / `UNI-001`). Reproduced directly against the running app (not assumed
> from the report alone): "Offer Letters" rendered the exact same unfiltered
> "Application Tracking" table as "Applications"/"Admission Updates" — confirmed and
> fixed with a dedicated filtered view mirroring the Student role's own existing
> "offer-letters" precedent (`services/portal.py`). "Admission Updates" has the same
> mislabeling but was **not** fixed — no data model exists for a queryable update feed,
> and building one would be unconfirmed new scope. "Personal details" was confirmed
> **absent codebase-wide for every staff role** (not `UNI-001`-specific) — logged as
> `PRD_OPEN_ITEMS.md` item 60, not built. Tested: 2 new backend pytest cases + the 4
> other files sharing this code path re-run clean (26/26 total), 1 new Playwright E2E
> case (5/5 in `uni-001-university-rep-portal.spec.ts`). Full regression not re-run
> (narrow single-branch change).
>
> **`I-13` closed next, same session, 2026-09-05:** HR Team's "add the close date on job
> requirements" (`ADM-008`). Confirmed directly: `Job.closes_on` was already collected by
> the "Create job requirement" form and already enforced server-side (`EMP-002-AC02`),
> but the Job Requirements table never showed it back, and no "Update" action existed at
> all — only "Create" — even though the backend (`PATCH /it/jobs/{id}`) already accepted
> `closes_on` for this role. Pure frontend gap: added the `closes_on` column
> (`services/portal.py`) and a real "Update job requirement" form
> (`WorkflowPanel.tsx`, `PATCH /api/v1/workflows/it/jobs/:job_id`). Tested: 2 new backend
> pytest cases (8/8 `test_adm_008_hr_shortlists.py`; 23/23 across the 3 other files
> sharing this code path), 1 new Playwright E2E case (3/3 `adm-008-hr-shortlists.spec.ts`)
> — confirmed live in a real browser that a created requirement's closing date renders
> and can be changed through the new form. Full regression not re-run (narrow, additive
> change).
>
> **`I-14` closed next, same session, 2026-09-05:** Administrator's "reports not
> working" (role ambiguous in the raw report). Rather than waiting on the reporter,
> checked every candidate Administrator role directly against the running app: IT
> Admin's/Placement Team's own Reports (`RPT-001`) both already worked with real data.
> Overseas Admin's own "Reports" link showed "Access unavailable — Workspace not
> found" — `RPT-002` (the feature that owns this role's own report) was `NOT_STARTED`
> in the catalog, not a regression, but already an approved Feature ID with confirmed
> AC/RBAC/dependencies (`AGT-003` complete, `OVS-004` complete for the read side
> needed) — so it was safe to build under the normal feature loop, not new/unconfirmed
> scope. Built `services/portal.py`'s `overseas_admin` "reports" handler: application
> funnel by stage as `metrics` (all 7 confirmed stages, honest zeros — `RPT-002-AC02`),
> visa-status aging as the primary table, agent commission summary as a `panels` list
> (kept separate from the existing "commissions" nav section rather than duplicating
> it). RBAC strictly `overseas_admin` per `RPT-002-AC03`, not extended to Counselor.
> Also updated `test_rpt_001_reporting.py`'s own test that asserted Overseas Admin's
> Reports link "still 404s deliberately" — that boundary is exactly what this feature
> supersedes, so the test was corrected rather than left contradicting the fix. Tested:
> 6 new backend pytest cases (`test_rpt_002_overseas_reporting.py` — the shared dev
> DB's lack of test isolation and a non-unique default test `full_name` both required
> uuid-suffixed names and presence/delta assertions rather than exact counts), 35/35
> across the 5 other files sharing this code path, 3 new Playwright E2E cases (7/7),
> confirmed live in a real browser. Full regression not re-run (additive new-role
> branch, narrow blast radius).
>
> **`I-15` closed next, same session, 2026-09-05:** Trainer's "on DASHBOARD one table
> was coming outside from alignment" (`TRN-001`). Reproduced directly at a 390px
> viewport rather than waiting on a screenshot: not the `DataTable` itself (its own
> `.table-wrap{overflow:auto}` correctly contains its scroll, confirmed zero body-level
> overflow at every tested width) but the shared `PortalShell.tsx` sidebar nav, which
> becomes a fixed bottom bar below 640px with horizontal scroll and no visible
> affordance — Trainer's own 9-item nav truncated mid-word at "Mate[rials]" with a hard
> clipped edge. `RESPONSIVE_RULES.md`'s baseline rule (`NFR-RESP-001`,
> `CONFIRMED_CURRENT`) requires "Primary action always reachable without horizontal
> scroll... collapses behind a toggle" — this violated it directly, so the fix was
> confirmed scope, not new. Fixed by generalizing `MobileNavToggle.tsx` (the already-
> proven public-site mobile nav pattern: toggle button + vertical dropdown panel) with
> optional `buttonClassName`/`panelClassName`/`panelId` props, defaults unchanged so the
> public site's own usage is unaffected (confirmed live) — reused rather than invented.
> `PortalShell.tsx` now renders it instead of the old fixed bottom bar; this is a shared
> layout component used by every role's portal, so the fix applies everywhere, not just
> Trainer. Tested: 3 new Playwright E2E cases (`trn-001-mobile-nav.spec.ts` — full nav
> reachable via toggle at 390px with zero overflow, panel closes after navigating,
> desktop sidebar unaffected above the breakpoint), `stu-002-dashboard.spec.ts`'s own
> 375px responsive case and `trn-001-my-batches.spec.ts` re-run clean. One unrelated
> pre-existing failure hit during this check: `stu-002-dashboard.spec.ts`'s "shows
> upcoming assignments" case failed even in isolation — confirmed by symptom match as
> the already-documented `RAID.md` I-03 (accumulated overdue E2E `Assignment` junk
> crowding the widget), not caused by this change, not fixed here (out of scope). Pure
> frontend/CSS, no backend change, no rebuild needed for `api`. **New finding, not
> fixed, logged as `RAID.md` I-17:** the same sidebar has a second, distinct gap in the
> 640–980px tablet range — every nav item renders as an identical unlabeled bullet
> ("•"), indistinguishable from each other, also against `RESPONSIVE_RULES.md`'s
> confirmed guidance. Different breakpoint, different defect, deliberately left for its
> own separate fix rather than folded in here.
>
> **New session, 2026-09-09 — separate bug-fix pass, not a continuation of the feedback
> batch above.** The user asked for a prioritized punch-list of unfixed real bugs, then
> worked through it one at a time. Full detail lives in `RAID.md`; summarized here so a
> fresh session doesn't have to re-derive it:
>
> - **`I-18` (all three sub-items) — CLOSED.** The Trainer assessment-grading bugs that
>   were built once, then explicitly reverted by the user alongside an unrelated design
>   discussion (see the older "built, then reverted" note further down this file), are
>   now fixed for real: (1) blind grading — added `GET
>   /workflows/it/trainer/assessment-attempts/{id}` and rebuilt "Grade written attempt"
>   as a per-question review pane, reusing `TRN-007`'s own `.qa-item` pattern and
>   activating the previously-dormant `.status`/`.status.pending` badge classes already
>   sitting unused in `globals.css`; (2) file-response questions unanswerable — added a
>   real `<input type="file">` to `AssessmentForm` (was falling through to a plain
>   textarea) with a new shared `uploadFile()` helper; (3) no lock against adding a
>   question after a student started an attempt — added `_assert_no_attempts_yet()`,
>   enforced server-side (`409`) and reflected client-side (a real `attempt_count` per
>   assessment disables the picker option). Verified per sub-item with real backend
>   tests, full backend regression, new Playwright E2E cases, and live browser runs at
>   each step (see `RAID.md` I-18 for the exact file/test names and counts).
> - **`I-05` — CLOSED.** The `event.currentTarget`-after-`await` crash pattern (fixed
>   once already for `WorkflowPanel.tsx`'s `ActionForm`/`DocumentUpload` and
>   `WebinarRegisterForm.tsx`) is now fixed in the three files it was still confirmed
>   present in: `EnquiryForm.tsx`, `AdminBatchCreatePanel.tsx`, `TrainerWorkflowForm.tsx`
>   (the last of which turned out to be dead code — fixed anyway, since it's still a real
>   bug in the source). Re-audited the rest of `apps/web/components` for the same pattern
>   first — no other live instance exists.
> - **`I-17` — CLOSED.** The tablet-range (640–980px) unlabeled-bullet sidebar nav is
>   fixed — extended the already-proven `MobileNavToggle` drawer pattern (`I-15`'s own
>   fix) up from its 640px breakpoint to the existing 980px one, and deleted the
>   icon-only-strip CSS rules that produced the bullets, rather than inventing an icon
>   set for a nav that never had one.
> - **`I-16` — split and triaged before touching any code.** Most of the tester's
>   bundled report ("counselor chat," "meeting notification," a dedicated "documents"
>   page) doesn't match anything on `STU-011` (IT Student) at all — it matches the
>   **Overseas Student** portal's own nav almost verbatim. Flagged that likely
>   misattribution in `RAID.md` rather than silently correcting it. Of the seven named
>   sub-items, exactly one was a confirmed, fixable bug on `STU-011` itself: the document
>   list rendered as inert plain text with no download action at all. **Fixed**: added
>   `GET /workflows/it/student/profile/documents/{id}/download` (self-scoped, same
>   signed-URL pattern as `STU-007`/`OVS-005`) and a real "Download" button per row. The
>   rest are either resolved as a side effect (documents were always listed, just
>   inert), confirmed-absent new scope not built (profile picture), not actually a gap as
>   reported (personal information), still unspecifiable (hover option), or out of
>   `STU-011`'s scope entirely (counselor chat / meeting notification).
> - **`I-19` (new, found investigating `I-16`) — CLOSED same session.** The Overseas
>   Student's "Counselor Chat" page was read-only, and the Counselor role had no way to
>   see or reply at all (no nav entry existed). `ROLE_ACTION_MATRIX.md`'s own confirmed
>   base action for the Student is "counselor-chat (**direct messaging**...)" — a
>   one-sided send would not have satisfied that, so both sides were fixed together, not
>   scope creep. Added `POST /workflows/overseas/student/counselor-chat` (resolves the
>   assigned counselor server-side, no picker needed) for the Student; added the missing
>   `counselor-chat` nav entry/portal section plus a new `CounselorChatPanel.tsx` (real
>   assigned-student picker, added `student_id` to the existing `applications` payload)
>   for the Counselor — both sides reuse the already-existing, unchanged generic
>   `GET`/`POST /communications/messages...` endpoints, no backend change needed there.
>   Verified: 8 new backend pytest cases, full backend regression 484/484 clean, 1 new
>   Playwright E2E case, plus a live browser run confirming the full round trip.
>
> Backend regression after this whole pass: **484/484 clean.** Each fix's own targeted
> Playwright specs were re-run clean; the full Playwright suite was not re-run this pass
> (narrow, additive changes across unrelated pages — same batching-cadence convention as
> the rest of this file).
>
> **Separately, same session: `I-20` — real Zoho Meeting credentials verified working
> (`RAID.md` I-20).** Real credentials had landed in `.env` at some point (like Razorpay's
> own earlier unblock) but nobody had ever verified them. Checked on request: OAuth refresh
> worked, but the actual Meeting-session-creation call failed with a real `401
> INVALID_OAUTHTOKEN` — `ZOHO_MEETING_BASE_URL` was pointed at `.com` while this account's
> tokens are issued by `accounts.zoho.in`, exactly the region-mismatch risk
> `PENDING_ZOHO_LIVE_CLASSES.md` §3.A had already flagged as unconfirmed. Fixed the `.env`
> value to `https://meeting.zoho.in`; `create_provider_meeting("zoho_meeting", ...)` now
> succeeds end to end (verified through the real API, the real application code path, and a
> live browser run scheduling a session through the actual UI). 3 new backend pytest cases
> against the real live API, full backend regression **487/487 clean**. **Scope note:** this
> only verifies the base one-off Zoho Meeting provider already used by live-class scheduling
> — the separate recurring/auto-invite/auto-attendance initiative in
> `PENDING_ZOHO_LIVE_CLASSES.md` remains fully unbuilt, still blocked on its own 11
> unanswered capability questions (real credentials don't answer those).
>
> **One real side effect to know about:** verifying this created a small number of real,
> harmless test sessions on the live Zoho account (titles like "EduSphere Zoho Verification
> Test", "Zoho E2E verification session", "Zoho Live Browser Verification", scheduled for
> future dates that will never be joined) — delete them from the Zoho account's own session
> list if that matters, they're otherwise inert.
>
> **Separately, same session: `I-21` — user-requested join-experience fix
> (`RAID.md` I-21, `PENDING_ZOHO_LIVE_CLASSES.md` §1b), screenshot-driven.** Six items
> requested together off the trainer's own "Live Sessions" table; split before touching
> code. **(a)/(b)/(c)/(e) fixed**: Join is now a real `<button>` (new shared
> `JoinSessionButton.tsx`, wired into both the generic `DataTable` via a new
> server-declared `type: "join"` column kind and `LiveClassesPanel.tsx`), gated on a
> 15-minute early window and the session's end time (pop-ups either side), with a
> joining student asked to confirm their own already-known identity before the real link
> opens (never the host). **(f) closed as impossible**: checked directly against Zoho's
> own public API docs on request — the Meeting API has no mute/audio/participant-
> permission field anywhere; "mute all"/"control who can unmute" exist only as a live,
> in-meeting host action inside Zoho's own client, never schedulable via the API. **(d)
> deliberately moved to pending at the user's own request** — see "Pending items" below.
> Verified: 4 new backend pytest cases, full backend regression 491/491 clean, 3 new
> Playwright E2E cases, plus a live browser run matching the user's own screenshot.
>
> **Separately, same session: `I-25` — user-spotted, screenshot-driven duplicate-batch
> cleanup (`RAID.md` I-25).** User shared a screenshot of the student "Book a slot"
> picker showing many near-identical duplicate batch cards, and asked (1) why, (2)
> whether one booking should cover the whole recurring batch (already true —
> `create_enrollment` already 409s on a repeat `student_id`+`batch_id`, no fix needed),
> and (3) whether multi-course registration is allowed (already true, no fix needed).
> Root cause of the duplicates: `test_rpt_001_reporting.py` and
> `test_trn_002_batch_roster.py` each uuid-suffixed only `slug` (the machine key), not
> `title`/`name` (the fields actually rendered on this page) — the same gap already
> documented once for `AGT-002` (`I-09`). Separately, `available_batches` never excluded
> a batch whose own `end_date` had already passed. Measuring the actual scale found
> **5,313 duplicate/debris batch rows** in the shared dev DB — `I-06`'s already-known
> test-DB-isolation gap, now visible to a real student. **Fixed**: uniquified every
> human-readable fixture field in both files, added an `end_date >= today` filter to
> `available_batches` (2 new backend pytest cases). These only stop future growth, so
> given the scale and product-visibility, the user chose to recreate the
> `postgres_data` volume and reseed fresh rather than write a one-off cleanup script —
> user ran the volume removal directly (a destructive action outside what this session
> could do unprompted), then the stack was brought back up (`docker compose up -d`) and
> reseeded (`python -m app.seed`). Verified directly: `SELECT count(*) FROM batches`
> now returns **1** (zero duplicates by name), and a live browser login as the seeded
> student confirmed the slot picker shows exactly one clean "Python Full Stack" card.
> Full backend regression re-run against the fresh database: **493/493 clean.**
>
> **Same session, immediately after — the broader fixture-naming sweep, at the user's
> explicit request ("fix the fixture-naming gap in the other 24 files").** Found 26 test
> files (not 24) with the same "only a machine key like `slug` was uuid-suffixed, not
> the human-readable `title`/`name` field actually rendered on a real page" gap, across
> `Program.title`, `Batch.name`, `Agreement.title`, `Job.title`, `LiveSession.title`,
> `Assessment.title`, and `Assignment.title`. Fixed all 26 with the same one-line pattern
> (append `{uuid.uuid4().hex[:6]}` to the literal); 2 of the 26 needed a small extra
> touch because an assertion checked the literal by exact string equality rather than by
> id (`test_emp_003_candidate_search.py`, `test_trn_006_assessments.py`) — both updated
> to compare against the actual generated value instead of a hardcoded copy. Full
> backend regression re-run: **493/493 clean** (same count as before the sweep). This
> closes out `RAID.md` I-25 completely — no known instances of this fixture-naming
> pattern remain anywhere in the backend test suite.
>
> **Same session, `I-26` — the rest of the duplicate-batch-picker fix (`RAID.md` I-26).**
> User asked for design options for the "many cards, lots of scrolling" problem, then
> approved all four: (1) `available_batches` now excludes any batch the caller already
> booked (any status), matching `create_enrollment`'s own 409 rule — the original "no
> error on a duplicate click" complaint turned out to be the error rendering below a
> long scrollable list, not missing error-handling; (2) `BatchSlotPicker.tsx` now
> renders a compact searchable table instead of a card grid, and the error message
> moved above the list so it's visible regardless of scroll position; (3) batches are
> grouped by program in collapsed `<details>` sections, auto-expanded only when one
> group remains; (4) a program filter `<select>` narrows the view to one program.
> Verified live (`docker compose build web` + a real browser check). **Found doing that
> live check, not yet actioned**: the shared dev DB has regrown to **239 batches / 279
> programs / 159 enrollments** of fresh test debris — the same `RAID.md` I-06 root
> cause, regenerated by this session's own full-regression reruns after the `I-25`
> cleanup. Offered another volume recreate + reseed; user hasn't said yet.
>
> **Same session, `I-27` — certificate template redesign (`RAID.md` I-27).** User asked
> for "a fixed template, generate dynamically after completion, and a button" — all
> three already existed (`services/certificates.py`'s `generate_certificate_pdf()`,
> issuance-time generation, `CertificateDownloadPanel.tsx`'s download button). Real gap
> found: the certificate's own `verification_code` (which already has a working public
> lookup, `GET /public/certificates/{verification_code}`) was never printed on the PDF
> itself. Redesigned the template (ink-navy gutter with a vertical wordmark, Times-Bold
> headline/name with a signal-green underline, a Courier "terminal" verification block
> in the footer) and fixed the verification-code gap as part of it — same fix, not two.
> Iterated once after rendering a real preview (PyMuPDF) to fix an unbalanced layout gap.
> `generate_certificate_pdf()` gained a required `verification_code` param; its one call
> site updated. 19 targeted backend tests clean.
>
> **Same session, `I-28` — auto-billed enrolment fee, admin discount, and a real
> Razorpay-payment-confirmation bug (`RAID.md` I-28).** User asked "where does the fee
> get updated" after enrolling — traced directly: it didn't. `create_enrollment` never
> read `Program.fees`, and "Fees" is a plain read of the `Payment` table — nothing
> appeared there until an Admin separately remembered to create one by hand. Fixed:
> enrolling now auto-creates a pending `Payment` (+ invoice) for the program's own
> listed fee, skipped only for genuinely free programs. Added `POST
> /admin/payments/{id}/discount` (amount + required written reason, same
> never-silent-discretion pattern as `ADM-006`/`AGT-003`) — only lowers an unpaid
> amount, regenerates the stale invoice. **Separately, a screenshot showed a real bug**:
> after a real Razorpay test payment succeeded, "Pay Now" stayed forever with no
> receipt and only a generic "submitted" message — the webhook (the only thing that
> ever marked a payment paid) can never reach `localhost` in a local dev environment.
> Added `POST /payments/{id}/verify` (Razorpay's own documented client-side HMAC
> confirmation step, `order_id|payment_id` signed under the key secret) wired into
> `FeePaymentPanel.tsx`'s success handler — a successful payment now marks itself paid
> and generates a receipt immediately, independent of the webhook. Verified live: a
> fresh student's enrollment in "Python Full Stack" produced a real ₹65,000 pending fee
> on the Fees page; a real discount through the Super Admin console took it to ₹55,000.
> The Razorpay iframe itself was confirmed to open for real, but a full click-through
> of their own hosted checkout UI was deliberately not attempted (`RAID.md` I-23's own
> established "that's testing their frontend, not ours" boundary) — the verify
> endpoint's signature logic is instead fully covered by 5 real backend tests. 46
> targeted backend tests clean total across all three fixes; `docker compose build
> api`/`web` clean.
>
> **Same session, immediately after — the shared dev DB volume recreate + reseed, at
> the user's explicit request.** `docker compose down`, `docker volume rm
> edusphere_postgres_data`, `docker compose up -d`, `python -m app.seed` — cleared the
> 239 batches/279 programs/159 enrollments of test debris down to real seed data only
> (1 batch, 20 programs, 1 enrollment). Ran the full backend regression once to
> confirm the fresh baseline (**510/510 passed**, up from 493 — the 17 new tests are
> today's fee/discount/payment-verify/fixture-naming work), then noticed live — via a
> browser check that happened to run while the regression suite was still
> mid-execution — that the regression run itself was actively recreating fresh test
> debris in the *same* shared dev DB in real time (`RAID.md` I-06's exact mechanism,
> caught happening live rather than just described). So the whole
> down/rm-volume/up/reseed cycle was repeated a second time, **after** the regression
> run finished, with no test suite run afterward — that second cycle is the one that
> actually left the environment clean. **Lesson for next time**: running the full
> backend regression against this shared dev DB will always repopulate it with fresh
> debris regardless of how clean it was beforehand; if the goal is a demo-clean
> environment, the reseed needs to be the last thing done, with no full-suite test run
> after it.
>
> **Same session, `I-29` — found from the app's own request logs, at the user's
> request (`RAID.md` I-29).** Asked to check the latest certificate-issue errors —
> pulled 5 real 409/422s across 4 enrollments from the `api` container's own request
> logs. Every 422 traced to one cause: the Trainer's own "Issue certificate" card
> (`TeacherWorkspaceActions.tsx` — a separate component from `AdminCertificatePanel.tsx`)
> sent `{override: true}` with no `override_reason` field at all, so ticking "Override
> unmet criteria" could never succeed against a genuinely ineligible learner. Fixed:
> added a controlled checkbox state + a conditional required "Override reason" textarea,
> matching the Admin panel's own existing pattern. Verified live: a real certificate was
> issued through the trainer UI with the reason text confirmed stored in the database.
> Added 1 new Playwright E2E case — caught and fixed two of my own test-assertion
> mistakes first (this page's success message is a shared banner, not scoped to the
> card, and is a fixed literal string, not one interpolated with the certificate
> number like the Admin panel's) before landing on a real pass.
>
> **Same session, `I-30` — asked to check Assignments and Assessments too
> (`RAID.md` I-30).** Verified both end to end with real actions: submitted and graded
> a real assignment (clean, no bugs). Assessments also worked functionally end to end
> (real attempt, auto-grade, manual grade, correct final percentage), but "Take
> assessment" made the student type the assessment's raw UUID into a bare text box —
> the same "raw ID typed by hand" gap already fixed almost everywhere else in this app.
> Fixed: `AssessmentForm` now fetches the student's own examinations list and renders a
> real picker of startable assessments, filtered to the statuses the backend itself
> accepts. Verified live: picking from the dropdown correctly hit the backend's genuine
> attempt-limit check. Updating the one E2E spec exercising this form (which typed the
> raw id) surfaced a second, unrelated, pre-existing test fragility in the same spec —
> it grabbed the trainer's first batch blindly, but the trainer now has two batches and
> index 0 isn't reliably the seeded demo student's own — fixed by matching the batch by
> name instead. Both affected E2E specs re-run clean.
>
> **Reminder for a fresh session: both `api` and `web` are built from Dockerfiles with no
> code bind-mount** (`docker-compose.yml`'s only volume on either service is
> `uploads:/data/uploads` on `api`) — every Python or TypeScript edit needs
> `docker compose build <service>` then `docker compose up -d <service>` before it's
> live in the running container, even for `docker compose exec` commands (they run
> against the image, not the host files). This tripped things up mid-session today:
> running `python -m pytest`/generating a certificate against a stale `api` container
> silently used old code with no error, until rebuilding made the difference obvious.
>
> - **Zoho account override per session** (`RAID.md` I-21 item d, `PENDING_ZOHO_LIVE_CLASSES.md`
>   §1b item d / §3.B / §5). A per-trainer "connect your own Zoho account" OAuth flow so a
>   specific session can use a different presenter than the shared default
>   `ZOHO_PRESENTER_ID`. Real new infrastructure, not a small fix: a new `TrainerZohoAccount`
>   table (encrypted `zoho_refresh_token` per trainer), new OAuth authorize/callback
>   endpoints, and a "Connect Zoho account" UI action. Moved here explicitly at the user's
>   request on 2026-09-09 rather than built immediately after the rest of `I-21` landed.
>
> **Same session, `I-22` — resolved 6 of `PENDING_ZOHO_LIVE_CLASSES.md` §2's remaining 11
> Zoho capability questions on request, against public docs (research, not code).** Most
> notable: Zoho's Participant Report API really does expose per-participant join/leave/
> duration data, so `DEC-ATT-001`'s auto-attendance rule is technically feasible — but as a
> pull/report endpoint, not a webhook, so any future build should assume polling (matching
> `§7`'s own already-proposed Beat-task design). Recurrence, auto-invite-email, timezone
> format, and the OAuth-token-has-no-presenter-ID question are also now answered. 4
> questions (concurrent-session limits, shared-vs-per-trainer seats, rate limits, actual
> plan/tier) remain genuinely unanswerable from public docs — full detail and sources in
> `PENDING_ZOHO_LIVE_CLASSES.md` §2 and `RAID.md` I-22.
>
> **Remaining items from the 2026-09-05 feedback batch above, not yet started:** the five
> new-scope/ambiguous `PRD_OPEN_ITEMS` (56–60: dark mode, hover, job references,
> Education Agent role ambiguity, and staff personal-details editing — item 60 was
> surfaced by `I-12`'s reproduction but deliberately left unbuilt as new scope, not
> closed). Say which one to pick up next, or "proceed with next one"; the pre-existing
> Wave 4 queue (`ADM-013` next) below is still waiting either way.
>

> `STU-010`/`PAY-001` (Fee payment/EMI/invoices/receipts + payment gateway integration) are
> **done as of 2026-09-03** — real Razorpay TEST-mode credentials landed in `.env`,
> unblocking both; built out of Wave-4 order since the user specifically asked for payment
> gateway testing/completion this turn (see "Completed this session" for the full writeup).
> `ADM-012` (Roles/permission administration) is **also done as of 2026-09-03** — **PARTIAL
> scope, deliberately**: the confirmed requirement it traces to (`PRD-ADM-013`) is view-only
> ("whether permissions need to be admin-configurable at runtime... was never asked");
> built a real, live `roles` view (per-role permission bundle straight from `core/rbac.py`
> + active-user counts, IT Admin/Super Admin only) and left runtime editing as an explicit
> open item (`PRD_OPEN_ITEMS.md` item 42) rather than inventing a permissions engine on an
> unconfirmed requirement. Say **"proceed with next one"** → next feature is **`ADM-013`**
> (Operational-tooling cluster, Super Admin ownership). The user went through the former
> `Unscheduled/BLOCKED group` one item at a time (2026-09-03, `DEC-SCOPE-008` +
> `DEC-NOT-001`'s extension) and promoted 8 of the 9 items into current scope; only
> `LMS-001` stays deferred (no specific extension named). `ADM-009`, `ADM-010`, `ADM-012`
> (first three in the queue) are now done. Full Wave 4 queue and order under "Next feature"
> below. **Regression checkpoint after `STU-010`/`PAY-001` (2026-09-03, run because the
> change touched the shared `Payment` model and `WorkflowPanel.tsx`):** backend **445/445
> clean** (up from 418, +27 new: 17 pytest + no other file added tests this pass). Full
> Playwright run showed 28 failures; reran all 22 distinct failing spec files with
> `--workers=1` and 19 cleared immediately (pure contention, `RAID.md` I-04/I-06). The 3
> that didn't are all already-documented, pre-existing, unrelated issues, reconfirmed by
> symptom match rather than assumed: `adm-007-placement.spec.ts` (I-07, `DataTable`
> pagination trap), `stu-002-dashboard.spec.ts` "shows upcoming assignments" (I-03,
> accumulated overdue E2E `Assignment` junk), `trn-003-upcoming-sessions.spec.ts` (I-10,
> the seeded `LiveSession` has drifted further into the past as the session date has
> advanced). New `pay-001-stu-010-fee-payments.spec.ts`'s own 3 cases all passed cleanly in
> the `--workers=1` rerun — the one full-run failure in that file was contention, not real.
> Also worth knowing: the shared dev DB now has **5,573+ synthetic `it_student` rows**
> (measured directly building `ADM-010`) — any new capped admin-list query must sort by
> `created_at.desc()`, never alphabetically (`RAID.md` I-06 addendum) — and a full
> `postgres` volume recreate + reseed is a reasonable thing to do if this keeps growing.
> `ADM-012` itself only needed targeted tests (no model/migration change, `services/
> portal.py` + `navigation.ts` only) — 36 targeted backend pytest cases clean, 4 targeted
> Playwright cases clean (this feature's own 2 + `ADM-009`/`010`'s, to confirm no
> `PORTAL_NAV`/dispatcher regression). Full regression not re-run for this feature per the
> batching cadence — next full checkpoint due after 2-3 more Wave 4 features.
>
> **Ad hoc, out-of-loop fix — built, then reverted, 2026-09-03:** the user reported real
> usability/correctness problems directly against the live `/it/trainer/assessments` page
> (via `/frontend-design`) — the trainer's grading UI never showed a student's actual
> written/file answer, a "file response" question wasn't actually answerable with a file,
> and a question could still be added after a student had already started the assessment.
> All three were confirmed and fixed (new `GET .../assessment-attempts/{id}` detail
> endpoint, a real file `<input>` on the student side, a 409 lock guard, and a rebuilt
> `TrainerAssessmentsPanel.tsx`), tested (6 backend + 1 E2E case, full regression
> 458/458), and shipped — then the user separately asked for design critique on an
> unrelated AI-generated mockup of the same page, and after that discussion asked to
> **revert the assessment changes entirely**, explicitly choosing "everything" (including
> the bug fixes, not just the new look) after being told the tradeoff. Reverted in full:
> `workflows.py`'s new endpoint/guards removed, `WorkflowPanel.tsx`'s `AssessmentForm`
> restored to a plain textarea for every question type, `TeacherWorkspaceActions.tsx`'s
> assessments section restored to the original four dropdown-based cards,
> `TrainerAssessmentsPanel.tsx` deleted, the new backend/E2E test files deleted,
> `trn-006-assessments.spec.ts` restored, and the `RAID.md`/`MASTER_FEATURE_CATALOG.md`
> entries describing the fix removed. **The three original bugs are real and are back**:
> grading is blind again (no answer shown), file-response questions silently don't work,
> and a question can be added mid-attempt. Kept, deliberately, as a separate and smaller
> fix that was never part of what was reverted: the "Grade submission" (assignments, not
> assessments) card now previews the student's real answer/file before grading — see
> `TRN-007`'s own catalog entry. If the user wants the assessment fixes back, the design
> discussion in this session's transcript (color/status-system proposal, generalizing the
> review-pane pattern) is the intended starting point for redoing it, not a plain re-apply
> of the reverted code.

Status snapshot for resuming in a **new session**. Governed by `CLAUDE.md` (NO-ASSUMPTION
MODE) and `prompts/13_FEATURE_LOOP.md`. This file is self-contained — a fresh session
should be able to read only this file and continue without re-deriving prior context.
Process features **one at a time**: read "Next feature" below, follow
`prompts/13_FEATURE_LOOP.md`'s before-code report format, implement, test, update the
docs this file itself points at, then update this file's own "Next feature"/"Completed
this session" sections before ending the turn — the same loop this file's whole
"Completed this session" history below was produced by.

Wave 3 is now fully done (`VISA-002` closed it out), and Wave 4 is open (see "Next
feature" below). The user gave a standing instruction this session: **don't run the
full backend/E2E regression after every single feature — batch it every 3-4 features
instead**, checking targeted test files (the new feature's own + any sharing its code
path) in between. Apply this going forward. The last batch checkpoint (after `OVS-006`/
`OVS-007`/`VISA-002`) has already been run — see the confirmed numbers above/in
"Startup" below. The next one is due after 3-4 more Wave 4 features land.

## Startup (do this first, every new session)

1. `docker compose up -d` (postgres, redis, api, worker, beat, web).
2. `docker compose exec api python -m app.seed` — reseed demo data (idempotent; safe to
   rerun). See "Known test-infrastructure issues" below for why this sometimes matters.
3. Confirm the regression baseline:
   - `docker compose exec api python -m pytest -q` → **last confirmed: 510/510 passed**
     (a full run, confirmed 2026-09-09 after `I-28`). The `postgres_data` volume was
     recreated + reseeded a second time immediately after this run, since the run
     itself repopulates the shared dev DB with fresh test debris (`RAID.md` I-06) — so
     the database is clean right now, but running this full command again will
     re-pollute it exactly as before; that's expected, not a regression. Note:
     `test_zoho_meeting_integration.py` (`I-20`) calls the real live Zoho API on every
     run, not a mock — if Zoho credentials are ever revoked/rotated without updating
     `.env`, this specific file (not the rest of the suite) will start failing for that
     reason, not a code regression.
   - `cd apps/web && npx playwright test` → **last *full-suite* run confirmed 2026-09-03
     after `VISA-002`: 161/176 passed, 15 failed** — this number predates all of Wave 4
     and this session's fixes; nobody has re-run the full Playwright suite since, so its
     current exact pass count is genuinely unknown until one is done. Every individual
     fix in this session and in Wave 4 was verified with its own targeted spec(s) re-run
     clean, just not a fresh full-suite count. Rerunning all 15 failing spec files with
     `--workers=1` cleared 14 of them immediately (pure parallel-worker contention,
     `RAID.md` I-04/I-06 — every one of these has always passed cleanly in isolation this
     session). The 15th, `trn-003-upcoming-sessions.spec.ts`, is a genuinely new,
     reproducible-in-isolation failure — **not** a flake and **not** caused by
     `VISA-002` or any other feature's own code: the seeded `LiveSession` its assertion
     depends on has a `starts_at` fixed relative to whenever it was first seeded (very
     early in this long session) and has now drifted into the past, so "Upcoming
     sessions" correctly excludes it. See `RAID.md` I-10 — needs `TRN-003`'s own
     seed/spec touched to fix, not a regression to chase in a future feature's own code.
     Individual specs were added throughout the session, including this session's 33
     new `agt-002-referrals.spec.ts`/
     `agt-003-commission-accrual.spec.ts`/`agt-004-commission-payout.spec.ts`/
     `adm-014-super-admin-console.spec.ts`/`pub-005-gallery-management.spec.ts`/
     `uni-001-university-rep-portal.spec.ts`/`rpt-001-reporting.spec.ts`/
     `emp-005-interview-list.spec.ts`/`ovs-006-scholarships.spec.ts`/
     `ovs-007-events.spec.ts`/`visa-002-interview-prep.spec.ts` cases (`SEC-001` added no
     new E2E spec, per its own catalog scope) sum to the 176 total confirmed above. A
     first run right after
     a `web`
     rebuild often shows 1-3 transient failures on public-content pages (Next.js
     fetch-cache warm-up) — rerun once before treating it as real, reconfirmed directly
     this session (`pub-001-content.spec.ts` failed 3 specs then passed clean on an
     immediate rerun, unrelated to that turn's own `PUB-005` changes; and again on
     `OVS-006`/`OVS-007`, where the warm-up state persisted stale/empty page output
     across two full reruns of the same web process before a third attempt came back
     clean — if a rerun doesn't clear it immediately, try a couple more before assuming
     something is actually broken). A hardcoded,
     non-unique date/time in an E2E spec that schedules a real record against a seeded
     identity can collide with that same spec's own leftover row from an earlier run
     (no test-DB isolation, `RAID.md` I-06) — reconfirmed directly this session and fixed
     in `emp-004-interview-scheduling.spec.ts`/`emp-005-interview-list.spec.ts` (both now
     vary the minute per run) — if a similar spec starts failing on a "conflict"/409 that
     passes with a fresh instant, this is why. A `DataTable` **or `CollectionExplorer`**
     assertion (the latter used by most public catalogue pages, e.g. `/overseas/events`,
     `/overseas/scholarships`, program/university listings — same client-side-pagination
     shape, confirmed this session building `OVS-007`) that doesn't first search/filter
     to a unique value can also intermittently fail once the shared dev DB has
     accumulated enough rows to push a fresh row past page 1 (`RAID.md` I-07) —
     reconfirmed directly this session (`adm-007-placement.spec.ts` failed once under
     full-suite contention, passed clean in isolation, unrelated to that turn's own
     `RPT-001` changes). A *full-suite*
     parallel-worker run may also intermittently time out a handful of unrelated specs
     under contention (see `RAID.md` I-04/I-06 below) — every one of these has always
     passed cleanly in isolation; reseed/cleanup and rerun before worrying.
   - `cd apps/web && npm test -- --run` → expect **2 passed**.
4. If baseline numbers don't match, don't assume something is broken — check whether
   it's one of the known, already-documented flake patterns below first (I-03/I-04/
   I-06/I-07), and reseed/recreate the DB volume if the shared dev DB has accumulated
   too much test debris (see below).

**Not yet committed to git** — this repo has no commits yet (`git status` showed "No
commits yet" all session). All work described below exists only as uncommitted
working-tree changes. Nothing has been pushed anywhere. Don't assume this has changed —
check `git log` if it matters before doing anything git-related.

## Next feature

**`ADM-013` — Operational-tooling cluster** (Wave 4, Admin (IT) module, `Could`).
Owner: Super Admin (`DEC-SCOPE-008` resolved the IT Admin/Super Admin ownership ambiguity).
Scope per `ADM-013-AC01`: system settings, audit logs, data import/export, backup/restore
status, system health, background-job monitoring. `AC02` requires a failed/in-progress
background job or backup to show its *real* status, never a fabricated "success" — check
what real, honest data actually exists to back each of these six sub-areas before building
(e.g. audit logs already exist via `SEC-001`/`ADM-014`'s `AuditLog`; background jobs run via
Celery/`worker`/`beat` — is there any real job-status table, or would "background-job
monitoring" require fabricating status where none is tracked?). Per `PRD_OPEN_ITEMS.md` item
46, this whole cluster's PRD backing (`PRD-ADM-012`) is blueprint-only self-description with
no independent confirmation, and several sub-items (backup/restore, system health) may be
Architecture/Operations concerns rather than product-level Admin UI — same "build only what
maps to something real, flag the rest" treatment `ADM-012` just got, likely needed again
here rather than inventing fabricated status for sub-areas with nothing real to show. Read
`docs/features/FEATURE_ACCEPTANCE_CRITERIA.md#adm-013` before starting.

**Wave 4 queue** (all promoted from `Unscheduled/BLOCKED` on 2026-09-03 via `DEC-SCOPE-008`
+ `DEC-NOT-001`'s extension — see `docs/decisions/PRODUCT_DECISION_REGISTER.md` Group 11
for the full per-item resolution). No dependency ordering constraint between them — this
is just the order to work through them in:

1. ~~`ADM-009` — Resources/recordings oversight~~ **done** (2026-09-03)
2. ~~`ADM-010` — Agreement/consent oversight~~ **done** (2026-09-03)
3. ~~`ADM-012` — Roles/permission administration~~ **done, PARTIAL scope** (2026-09-03) —
   view-only per its confirmed requirement (`PRD-ADM-013`); runtime permission editing
   stays an open item (`PRD_OPEN_ITEMS.md` item 42), not built
4. `ADM-013` — Operational-tooling cluster (Super Admin ownership, per `DEC-SCOPE-008`) (next)
5. `ADM-011` — Notification template management (**email channel only** — WhatsApp/SMS
   stays out until `NOT-002`/`NOT-003` unblock; build extensibly, not email-hardcoded)
6. `EMP-006` — Placement status tracking (offer/accepted/joined per interviewed candidate)
7. `RPT-002` — Overseas reporting (application funnel, agent commission report,
   visa-status aging — mirrors `RPT-001`'s already-built reporting pattern)
8. `PUB-010` — Site search, FAQ, and legal pages (**split scope** — search/FAQ real;
   Privacy/Terms/Cookie pages ship as explicitly-labeled non-final placeholder content
   only, real legal sign-off is `DEC-PRIV-001`, still open)

**Not in this batch:** `LMS-001` stays deferred — `DEC-LMS-001`'s native-vs-external
question was already resolved (native-only, 2026-09-01), but no specific extension
capability was named when re-asked (2026-09-03), so there's still nothing concrete to
build. Becomes schedulable the moment the user names a specific native-LMS capability.
`AUTH-003` (Google OAuth) also stays blocked — provider decision, not addressed in this
review. The 5 credential-blocked items (below) remain available if credentials arrive.

Remember the batching cadence: don't run full backend/E2E regression after every one of
these — targeted tests per feature, full regression every 3-4.

## Completed this session (67 features — all gates green: unit/API, E2E, RBAC, RTM)

Each has real evidence in `docs/quality/RTM.md` and
`docs/features/MASTER_FEATURE_CATALOG.md` (implementation + test status, with the
specific gap found and fixed, or "no code change needed" where the inherited codebase
already satisfied the feature).

| Feature | Name and summary |
|---|---|
| `FND-001` | Reference-implementation extension baseline |
| `FND-002` | Division-aware RBAC & identity framework |
| `AUTH-001` | Division-aware authenticated login |
| `AUTH-002` | Role-based access control enforcement (UI) |
| `PUB-001` | Career paths / real projects / success stories / business services |
| `PUB-002` | Enquiry → CRM sync (outbox pattern, async retry) |
| `PUB-003` | Program catalogue search/filter + per-page SEO |
| `STU-001` | Trainer/batch slot enrolment |
| `STU-002` | Student dashboard (with per-widget fault isolation) |
| `STU-003` | Live class access |
| `STU-004` | Assignment submission (on-time/late flag) |
| `STU-009` | Digital agreement / consent (enrolment gated on consent) |
| `TRN-001` | My Batches |
| `TRN-002` | Batch detail (roster and schedule) |
| `TRN-003` | Upcoming sessions and live-class join |
| `TRN-005` | Assignment create/edit (create existed; added the entire edit half) |
| `TRN-007` | Submission review and grading (already implemented; added test coverage) |
| `TRN-008` | Attendance marking (already implemented; added test coverage) |
| `ADM-001` | User/course/batch administration (fixed a real AC02 gap; added deactivate/reactivate UI) |
| `ADM-002` | CRM-linked enquiry/lead management (already implemented; replaced raw-ID form with a real picker) |
| `ADM-003` | Batch creation and trainer assignment (fixed a real AC02 gap: capacity allowed up to 500, not ≤20; added pickers) |
| `ADM-005` | Enrolment review and approval (added the contract-specified approve/reject endpoints and admin UI from scratch) |
| `PUB-004` | Webinar listing and registration — Wave 2's first feature. Reused `Event` for listing; built net-new `WebinarRegistration` (in-app registration capture genuinely didn't exist before) |
| `STU-005` | Support ticket — student side already worked; added the missing staff side (`assigned_to_user_id`/`resolution_note` fields, `PATCH /workflows/support/{id}`, Trainer+Admin "support" workspace). Also found+fixed a real `event.currentTarget`-after-`await` bug (`RAID.md` I-05) |
| `STU-006` | Attendance and progress view — the session list + self-scoped RBAC already existed and was already tested (incidentally, via `TRN-008`); the real gap was PRD-STU-007 (folded into this feature): course-progress % and outstanding-blockers (unfinished assignments) were never shown |
| `STU-007` | Certificate download — issuance and the read-only listing already existed; the real gap was the "signed, short-lived URL... never a public object link" contract requirement. Added a self-scoped `GET /workflows/it/certificates/{id}/download` and `CertificateDownloadPanel.tsx`. Also fixed a local-storage download-URL proxy bug (`apps/web/app/local-files/[...path]/route.ts`) |
| `STU-008` | Feedback submission — genuinely net-new: `CourseFeedback` never existed despite `DATA_MODEL.md` saying "carries over". Added the model (alembic `0011`), `POST /workflows/it/student/feedback`, `FeedbackSubmissionPanel.tsx`. Anonymous-submission is an open item, deliberately not built |
| `STU-011` | Profile and document management — profile editing already existed untested; document management genuinely didn't exist. Added `ProfileDocument` model (alembic `0012`), upload endpoint, `ProfileDocumentUpload.tsx` |
| `TRN-004` | Recording list and resource upload — no code change needed (like `TRN-001`/`007`/`008`), just missing test evidence |
| `TRN-006` | Assessment create and edit — create existed, edit half missing. Also fixed a real `TRN-006-AC02` violation: Draft assessments were fully visible to enrolled students |
| `TRN-009` | Q&A response — genuinely net-new: `QuestionThread`/`QuestionReply` (alembic `0013`), full raise/list/reply flow, `QuestionAskPanel.tsx` |
| `ADM-004` | Directory management — replaced an unfiltered "everyone" list with role-scoped filtering + an "Edit details" action. Surfaced RAID I-06 (test-DB isolation gap) |
| `ADM-006` | Certificate administration — enforced the `override_reason` contract requirement, added `AdminCertificatePanel.tsx`. Fixed a real 500-instead-of-409 bug (UUID not JSON-serializable in `HTTPException.detail`) |
| `ADM-007` | Placement Team workspace — added `PlacementProfile.withdrawn` (alembic `0014`, a real `ADM-007-AC02` gap), real picker + withdraw/reinstate control |
| `ADM-008` | HR Team workspace — added the missing per-requirement shortlist view (`GET /workflows/it/jobs/{id}/shortlist`), `HrShortlistPanel.tsx` |
| `NOT-001` | Email notifications — fixed `send_notification` silently swallowing failure reasons (a literal `AC02` violation); added `NotificationDelivery.attempt_count` (alembic `0015`) |
| `SEC-002` | GDPR consent capture and self-service export/delete — net-new `DataSubjectRequest` (alembic `0016`), export/delete endpoints, retention-hold check |
| `EMP-001` | Employer registration — fully net-new. Extended `Company` (alembic `0017`, `owner_type`/`employer_user_id`), net-new `EmployerProfile`. `POST /employer/register` atomic, no invented approval gate |
| `OVS-001` | Destination/university/course discovery — carried-over models/endpoints already worked. Found+fixed a real defect: `/public/overseas-courses` 500'd unconditionally (ambiguous SQLAlchemy join) |
| `OVS-002` | Overseas application submission — fixed two real gaps: no duplicate-prevention (`OVS-002-AC02`), and initial status predating the contract-fixed enum. Real picker, `OverseasApplyPanel.tsx` |
| `OVS-003` | Eligibility evaluation — the generic PATCH let a Counselor set `status` to any value including unsupported exception outcomes (a confirmed gap — the old dropdown literally offered "rejected"). Added a forward-only, enum-validated `/advance` endpoint |
| `OVS-005` | Document upload against checklist — fixed a real security gap: raw permanently-public `file_url` exposed directly; Counselor queue had no way to view a document before verifying it |
| `VISA-001` | Visa checklist and documentation — no Student-facing read path existed at all; `status` had no enum validation. Added `GET .../visa-checklist` + enum/all-verified gate |
| `VISA-003` | Visa approval status tracking — dedicated `GET .../visa-status` endpoint didn't exist. Added it with a fixed compliance disclaimer (`VISA-003-AC02`) |
| `CNS-001` | Counselor workspace `[base]` — "Leads"/"Reports" nav sections 404'd (confirmed directly). Fixed a real `CNS-001-AC02` violation: appointment scheduling let a Counselor act on any student, not just their assigned ones |
| `EMP-002` | Job posting — fully net-new. **Self-caught mid-session correction**: initial pass shipped jobs as immediately `"open"`, missing the contract's `"draft"`-first requirement — fixed before moving on. Also fixed a real, pre-existing gap: `closes_on` was never checked in any of 4 listing/apply call sites |
| `EMP-003` | Candidate profile search — fully net-new `GET /employer/candidates`, conservative allowlist (name/course/skills/availability), never raw contact info |
| `EMP-004` | Interview scheduling and shortlist — fully net-new. No `duration` field exists on `Interview`, so same-instant collision is the only honestly-detectable scheduling conflict — flagged 409 |
| `OVS-004` | Application status tracking and notifications (**PARTIAL — email channel only**, Twilio SMS/WhatsApp stay credential-blocked under `NOT-002`) — notification dispatch already existed and was already exception-safe; added the dedicated `GET .../status` tracking-view endpoint the contract names |
| `AGT-001` | Agent self-registration and approval gate (first Wave 3 feature) — **significant cross-cutting gap found and fixed**: `core/rbac.py`'s deny-by-default machinery already existed but no route in the codebase actually used it — a Pending Agent could reach every agent-scoped endpoint immediately after self-registering. Added `agent_is_approved()` and wired it into `workflows.py`'s shared `_require` and `portal.py`'s dispatcher (fixes every agent-gated route at once). Added the missing approve/reject actions. Ran the full backend regression given the shared blast radius |
| `AGT-002` | Referred-student roster and status (2026-09-03) — roster + applications endpoints already existed, self-scoped, already denied Pending/Rejected agents. Real gap: the roster showed only the referral-link status, never the referred student's actual application status. Joined it in (`services/portal.py`, no schema change). Along the way, found+fixed a real seed-data defect: the demo `agent@edusphere.local` account had no approved `UserRoleAssignment` row — `auth._sync_role_assignment` lazily creates a *pending* one on first login and never overwrites it, so the demo persona was silently stuck 403 on its own dashboard. `seed.py` now self-heals this idempotently. Ran the full backend regression given the shared demo-seed blast radius (336/337 — the 1 failure a known I-04/I-06 flake, clean in isolation) |
| `AGT-003` | Commission accrual, automatic trigger (2026-09-03) — implemented `DATA_MODEL.md` §6.3's confirmed trigger exactly: an `ApplicationStatusHistory` row reaching `to_status='enrolled'` on an application with an `agent_id` auto-creates an `AgentCommission(status="estimated", amount=0, created_by="system_trigger")` (no fixed rate is confirmed, so amount can't be known yet) — one shared helper hooked into both existing status-write endpoints. New migration `0018` (`AgentCommission.created_by`). Found+fixed two real gaps in the base codebase's manual-commission path: it never checked the application had reached `enrolled` (now 409s, `AGT-003-AC03`), and no endpoint existed anywhere for an Admin to set/adjust a commission's amount (`AGT-003-AC02` — added `PATCH .../commissions/{id}`, locked once claimed). Also built the missing Overseas Admin "Commissions" portal section from scratch (didn't exist at all). Ran the full backend regression given the shared status-write-path change (348/348 clean). Along the way, found+fixed a real test-hygiene bug in this session's own `AGT-002` fixtures: `_make_university()`'s display name wasn't uniquified per run, so it leaked into the public catalog and an E2E helper picked one and mutated the shared seeded demo student's application, colliding with `AGT-002`'s own E2E assertion — fixed in both test files, stray rows cleaned up (`RAID.md` I-09) |
| `AGT-004` | Commission payout request and approval (2026-09-03, closes the Agent stream) — net-new `POST /overseas-admin/commissions/{id}/approve-payout`, no equivalent existed in the base codebase. Implements `PRD.md` §6.4's confirmed state machine exactly (Payout Requested → Overseas Admin Approval → Paid), requiring only `status=="claimed"` (the Agent's existing, unchanged claim action) — no invented third agent action. Honors "claimed can never transition directly to paid" by writing the commission through `payout_pending` (own `AuditLog` row) before `paid`, within the one approval request. New migration `0019` (`payout_approved_by_user_id`/`payout_approved_at`). Implemented the two-gate same-actor rule for `admin_manual`-created commissions (creating Admin found via the `agent.commission_create` audit row, 403'd from approving their own). **Deliberate, documented open item**: the confirmed rule is textually scoped to creation-mode only — a `system_trigger`-created commission whose amount an Admin later set via `AGT-003`'s PATCH is exempt from the two-gate check even if that same Admin then approves its own payout; flagged in code/tests/`PRD_OPEN_ITEMS.md` item 53, not silently patched with an invented stricter rule. Ran the full backend regression given the shared model/migration change (358/358 clean) |
| `SEC-001` | Approval-gate audit trail (2026-09-03, unblocked by `AGT-001`+`AGT-004`) — `AGT-001`/`AGT-004`'s audit writes already shared one transaction with their privileged write (fail-closed by construction, now proven with a forced-failure test, not just asserted). Real gap: `AuditLog` had no `outcome` field despite `DATA_MODEL.md` §7.3 and this feature's own catalog description both naming it. Added it (migration `0020`), set to a real value at `AGT-001`/`AGT-004`'s call sites only (deliberate scope boundary — other call sites keep a neutral "recorded" default). Verified (not modified) GDPR fulfil/reject and the certificate-issue override already satisfy the same pattern. Found "Super Admin security-log export" (named in `RBAC_MATRIX.md` §3) has no distinct write action anywhere — only a read-only view — so nothing to audit-log there; flagged as `ADM-014`'s likely real gap instead of inventing it here. Ran the full backend regression given the shared model change (365/365 clean) |
| `ADM-014` | Super Admin cross-division console (2026-09-03) — the console itself already existed (`apps/web/app/admin/[module]/page.tsx` + `SUPER_ADMIN_NAV`), and `/admin/users`'s division-scoping already satisfied the cross-division AC (confirmed with a dedicated test per role, not assumed). Real gap, named explicitly in this feature's own AC02: no "security-log export" action existed anywhere — only the read-only `/admin/audit` view (the exact gap flagged during `SEC-001`). Added `POST /admin/audit/export` (Super-Admin-only, stricter than the read view's broader `ensure_admin` gate), same `storage`-service download pattern as `SEC-002`'s GDPR export, self-audit-logged in the same transaction. Added `AuditExportPanel.tsx` to the existing Security & Audit Logs page. Ran the full backend regression given the shared `admin.py` change (372/372 clean) |
| `PUB-005` | News and gallery, CMS-managed (2026-09-03) — News (`BlogPost`) already had full admin CRUD and a working public page with an honest empty state, no gap. Real gap: `GalleryItem` had zero write/manage endpoints anywhere — only the public read and seed-time direct DB inserts existed, so an Admin could not publish a gallery item at all. Added `GET /cms/manage/gallery`, `POST /cms/gallery`, `PATCH /cms/gallery/{id}`, mirroring the existing `posts` pattern exactly (no schema change needed). Added the missing "Gallery Management" Admin console section from scratch (nav, table, forms). Deliberately did not assert a freshly-published item appears on the public page within the same E2E run — `publicApi()`'s 60s ISR cache makes that non-deterministic, reconfirmed directly this session when an unrelated public-content spec failed-then-passed on an immediate rerun. Ran the full backend regression given the shared `cms.py` change (381/381 clean) |
| `UNI-001` | University Representative portal (2026-09-03) — dashboard/applications/offer-letters/admission-updates were already correctly scoped to the Rep's own institution via `User.profile["university_id"]` (confirmed directly, contrary to `DATA_MODEL.md` §6.10 describing that field as still needing to be built — it was already added as a byproduct of earlier `OVS-003`/`CNS-001` work). Two real gaps: "Reports" 404'd for this role (same bug class `CNS-001` found for Counselor's own Leads/Reports, never carried over) — added a Rep-specific aggregate. No endpoint existed for `API_CONTRACT.md`'s explicitly-named "post an admission update visible to Counselor/Student" action — added it, reusing the existing `_notify_user` mechanism (no new model), verified a Rep is denied even via a spoofed cross-institution application ID. Ran the full backend regression given the shared `portal.py`/`workflows.py` change (388/388 clean) |
| `RPT-001` | Domestic/Employer reporting (2026-09-03) — neither the existing `/admin/reports/summary` (users/leads/revenue only) nor the portal dispatcher covered this feature's named scope at all; `PORTAL_NAV` listed "Reports" for IT Admin and Placement Team but neither had a handler (same 404 bug class as `CNS-001`/`UNI-001`, never caught here). Added two real handlers: IT Admin gets an enrolment funnel (Enquiry→Enrollment→Certificate) + per-course progress figures; Placement Team gets employer job activity + placement outcomes from real Job/JobApplication/JobOffer rows. Deliberately excluded Overseas Admin (that's `RPT-002`'s unscheduled scope) and HR Team (not named in AC03) — both confirmed still 404/excluded, not silently widened. No frontend code needed — the existing generic portal page already renders whatever the backend returns. Ran the full backend regression given the shared `portal.py` change (396/396 clean) |
| `EMP-005` | Interview list and status (2026-09-03) — the list and its RBAC scoping already existed (`EMP-004`); the real gap was the UI never displaying an interview's `result` at all, so a cancelled interview — never actually filtered out at the data layer — was indistinguishable from any other in the list. Added a status badge (real result, or an honest "Awaiting outcome"). While regression-testing, found and fixed a real, reproducible (not flaky) bug in `EMP-004`'s own E2E spec: a hardcoded interview time collided with the same seeded candidate's leftover interview from an earlier run, tripping the backend's own legitimate same-instant conflict check — fixed by varying the minute per run in both specs. Ran the full backend regression given the shared model exercised (400/400 clean) |
| `OVS-006` | Scholarship listing and application (2026-09-03) — `POST /overseas/scholarships/{id}/apply` and `GET /public/scholarships` already existed and were already correct (self-scoped, duplicate-blocked, active-only). Real gap was entirely frontend: `/overseas/scholarships` only ever said "Sign in to apply," with no apply action anywhere, even after login. Added a `scholarships` portal section (`services/portal.py`, self-scoped read of the student's own applications) and `ScholarshipApplyPanel.tsx`. Ran the full backend regression given the shared `portal.py` change, jointly with `OVS-007` (411/411 clean) |
| `OVS-007` | Events and workshops (2026-09-03) — `GET/POST /public/webinars/{id}[/register]` (built generically by `PUB-004` over any `Event`, division-agnostic, no auth) already worked here — confirmed by reading the handlers and closed with a dedicated test against an overseas-division event. Real gap was entirely frontend: `/overseas/events` cards linked to `event.registration_url` (a field the underlying list endpoint never actually returns — always dead) or fell back to a "Register interest" link to `/overseas/contact`. Added `apps/web/app/overseas/events/[id]/page.tsx` (mirrors the IT webinar detail page) and pointed listing cards at it. Along the way, confirmed `CollectionExplorer` (used by most public catalogue pages, not just `DataTable`) shares I-07's client-side-pagination E2E trap — addendum added to `RAID.md` I-07 |
| `VISA-002` | Visa interview preparation (2026-09-03, closes Wave 3's last named item) — no endpoint existed at all; the catalog's own `api: N` flag was stale — `API_CONTRACT.md` names `GET /overseas/visa/interview-prep` distinctly from its `visa-checklist`/`visa-status` siblings (Self only, no Counselor; not scoped to one application — one entry per the student's own visa cases). The actual prep content is a confirmed open item (`DEC-DATA-001`/`DEC-SCOPE-006`), so added a nullable `Country.interview_prep` column (migration `0021`) and seeded illustrative content for exactly `usa`/`united-kingdom`, leaving the rest empty so the "explicit fallback, not a 500" path is genuinely exercised. Never exposed through the public country endpoint (`CountryOut`'s explicit allowlist). Folded into the existing `VisaChecklistPanel.tsx`. Along the way, found (not fixed — cross-cutting, same root cause as `RAID.md` I-06) that the shared seeded counselor account has accumulated enough test-assigned applications that `CounselorVisaPanel.tsx`'s per-row fetches can intermittently miss a spec's assertion window under contention — confirmed passing cleanly in isolation, documented as an I-06 addendum |
| `ADM-009` | Resources/recordings oversight (2026-09-03, first Wave 4 feature — promoted from `Unscheduled/BLOCKED` via `DEC-SCOPE-008`) — `TRN-004`'s own `LearningResource` model and Trainer-scoped "materials" portal section already existed and worked; no cross-trainer Admin oversight existed anywhere. Added a `resources` section to the existing `it_admin`/`super_admin` portal dispatcher, reusing the same `LearningResource`+`Batch` join as the Trainer's own section but unscoped across every batch/trainer, with a trainer-name column added. No migration — confirmed `overseas_admin` correctly 404s requesting this section (Batches are an IT-only concept) rather than assuming it |
| `ADM-010` | Agreement/consent oversight (2026-09-03, promoted via `DEC-SCOPE-008`) — `STU-009`'s self-scoped agreement/consent flow already existed and worked; no cross-student Admin oversight existed anywhere. Added a `consent` section to the existing `it_admin`/`super_admin` portal dispatcher, reusing `Agreement`/`ConsentRecord` directly, no migration. Measured the shared dev DB directly and found **5,573** synthetic `it_student` rows — fixed an alphabetical sort that would have made a freshly created row essentially unfindable at that volume (switched to `created_at.desc()`, `RAID.md` I-06 addendum); also fixed a real "vv1" string-formatting bug in the subtitle. Found (not fixed) that the same debris has silently made the real seeded demo student's "current agreement" an arbitrary leftover test row — worked around in this feature's own E2E spec by registering a fresh throwaway student instead of touching the polluted seeded one |
| `STU-010`+`PAY-001` | Fee payment/EMI/invoices/receipts + payment gateway integration (2026-09-03, built together, out of Wave-4 order at the user's specific request) — unblocked by real Razorpay TEST-mode credentials (`rzp_test_...`) landing in `.env`. The checkout/webhook mechanics already existed (`api/payments.py`); the real gaps were `DATA_MODEL.md` §7.2's four named models that never actually existed in code (`Invoice`/`Receipt`/`EMISchedule`/`PaymentWebhookEvent` — mislabeled "carries over" there, corrected), plus `API_CONTRACT.md` §0.2's `Idempotency-Key` gate. Added all four (migration `0022`), invoice/receipt PDF generation+signed download (STU-007's pattern), an admin-discretionary EMI-schedule endpoint (no fixed amortization policy is confirmed anywhere), and `FeePaymentPanel.tsx` (replacing the raw-UUID generic checkout form). Found+fixed three real defects: (1) any admin role could trigger checkout on another user's payment (`STU-010-AC04` — Admin's scope is view, not act); (2) the inherited webhook handler matched a payment via a Razorpay Payment-entity field (`receipt`/`notes.reference`) that doesn't reliably exist on that entity (verified against Razorpay's own API docs) — replaced with matching on this app's own `checkout_provider_order_id` (`RAID.md` I-11); (3) `WorkflowPanel.tsx`'s single early-return guard was never updated with the new `showFeePayment` flag, silently hiding the entire new panel — caught only by real browser (Playwright) testing, not by the passing backend suite or a manual glance at the diff. Also found+fixed a stale `.env` leftover (comment + two empty `STRIPE_*` vars) from the superseded 2026-09-01 Stripe decision that `DEC-PAY-001`'s 2026-09-03 re-resolution had already named for removal but never actually got removed. Ran the full backend regression given the shared `Payment` model change (445/445 clean) and a full Playwright run (28 failures, 19 cleared on an isolated `--workers=1` rerun as known contention, remaining 3 are pre-existing documented issues unrelated to this feature — see the top-of-file regression checkpoint note) |
| `ADM-012` | Roles/permission administration (2026-09-03, Wave 4, promoted via `DEC-SCOPE-008`) — **PARTIAL scope, deliberately**: `AC01` calls for "views and adjusts", but the confirmed requirement this feature traces to (`PRD-ADM-013`, distinct from `PRD.md`'s differently-numbered `PRD-ADM-012` heading) is explicitly view-only — "whether permissions need to be admin-configurable at runtime... was never asked." `core/rbac.py`'s `PERMISSIONS` is a static code table, not a DB-backed model. Building live editing would mean inventing a security-critical runtime permissions engine on an unconfirmed requirement, not extending a confirmed one — not attempted; flagged in `PRD_OPEN_ITEMS.md` item 42 instead. Built the confirmed half: a `roles` section on the existing `it_admin`/`super_admin` portal dispatcher (`services/portal.py`), rendering the real, live per-role permission bundle straight from `core/rbac.py` (never a hand-copied duplicate) plus a real active-user count per role. No migration. `AC02` (reject a bad permission removal) is vacuously satisfied — confirmed directly that no write endpoint exists to guard. Targeted regression only (no model/migration change): 36 backend + 4 E2E cases clean, full suite not re-run per the batching cadence |

## Blocked — need real external credentials, do not fake (6)

Corrected 2026-09-03: this table previously listed only 5 rows; `NOT-003` was always
credential-blocked identically to `NOT-002` (same Twilio dependency) but had only ever
been mentioned in prose elsewhere in this file, never counted here. Verified against
`docs/features/feature_catalog.json` directly (`node -e` querying `scope`/`release`
fields) rather than assumed — the file's own running counts were quietly off by one for
this reason before this correction.

| Feature | Name | Blocker |
|---|---|---|
| `OPS-001` | DigitalOcean deployment | No DO account/credentials |
| `OPS-002` | DB migration execution on DO + seed-data decision | Depends on `OPS-001` |
| `NOT-002` | WhatsApp notifications (Twilio) | `DEC-NOT-001` confirms Twilio specifically (unlike `NOT-001`'s unnamed email provider) — real Account SID/Auth Token + real status-callback signature verification required (`INTEGRATION_CONTRACTS.md` §4); no Twilio credentials exist anywhere in this repo |
| `NOT-003` | SMS notifications (Twilio) | Same Twilio credential gap as `NOT-002` — no SMS-specific decision blocks it, purely credentials |

**`STU-010`/`PAY-001` unblocked and done (2026-09-03):** real Razorpay TEST-mode credentials
(`rzp_test_...`) landed in `.env`. Built both together — see "Completed this session" below.
Live-mode credentials for a real production go-live remain a separate, still-open item
(`DEC-ENV-001`'s test/live separation), not tracked here as a blocker on further feature work.

If the user has since supplied any of these, say **"proceed with next one"** for
whichever is now unblocked.

## Full scope picture

- **Wave 1** (26-feature M1 milestone): complete except the 2 truly-blocked items above
  (`OPS-001`/`002`) — `STU-010`/`PAY-001` (also Wave 1) are now done, unblocked 2026-09-03.
- **Wave 2** (29 features, `docs/delivery/RELEASE_BACKLOG.md` §3, three parallel
  streams): domestic-depth stream — done/blocked, all accounted for above; Employer
  stream (`EMP-001`–`004`) — **fully done**; Overseas/Visa core stream (`OVS-001`–`005`,
  `VISA-001`, `VISA-003`, `CNS-001`) — **fully done**, including `OVS-004` (PARTIAL,
  email only). `SEC-001` also now done. `NOT-003` (Twilio SMS) is the only Wave 2 item
  left, credential-blocked (see "Blocked" section below).
- **Wave 3: fully done.** The entire Agent stream (`AGT-001`–`004`), every
  `Should`-priority item (`ADM-014`, `PUB-005`, `UNI-001`, `RPT-001`), `EMP-005`,
  `OVS-006`–`007`, and now `VISA-002` are all complete. Nothing left in Wave 3.
- **Wave 4** (opened 2026-09-03 via `DEC-SCOPE-008` + `DEC-NOT-001`'s extension — see
  "Next feature" above for the queue and order): `ADM-009`, `ADM-010` **done**; `ADM-012`
  **done (PARTIAL — view-only, runtime editing an open item)**; `ADM-011` (email-channel
  scope only), `ADM-013` (Super Admin ownership), `EMP-006`, `RPT-002`, `PUB-010` (split —
  search/FAQ real, legal pages placeholder-only) remaining.
- **Remaining truly unscheduled/blocked:** `LMS-001` (no specific extension named —
  see `DEC-LMS-001`'s 2026-09-03 extension) and `AUTH-003` (Google OAuth, provider
  decision never revisited this round).

**Full-catalog count** (`docs/features/feature_catalog.json`, 78 features total,
verified directly with `node -e` against `scope`/`release` fields, not estimated): **67
done** (`OVS-004` counted for its unblocked/email scope only, `ADM-012` counted for its
confirmed view-only scope only; includes `ADM-009`/`010` and `STU-010`/`PAY-001`), **4
credential-blocked** (`OPS-001`/`002`, `NOT-002`/`003` — see corrected "Blocked" table
above), **5 scheduled but not started** (the remaining Wave 4 queue above), **2 still
genuinely unscheduled/blocked** (`LMS-001`, `AUTH-003`). 67+4+5+2 = 78.
66+4+6+2 = 78.

## Known test-infrastructure issues (tracked in `docs/delivery/RAID.md`, not urgent)

**I-06**: `apps/api/tests/conftest.py` has no test-database isolation — `db_session`
opens a session against the exact same Postgres database the live `docker compose`
stack and `python -m app.seed` use, with no per-test rollback and no separate test DB.
Every pytest run all session has left real, permanent rows in the shared dev database.
This measurably slows full-suite Playwright runs and causes I-04-style contention
timeouts (see below) that get more frequent as the DB accumulates more test rows. Not
fixed this session — real fix (a per-test transaction-rollback fixture, or a genuinely
separate test database) touches all 300+ existing backend tests' assumptions and is too
large for a single feature's loop. Mitigation: periodically delete synthetic rows
(`WHERE email LIKE '%@example.local'` matches nearly all synthetic users) or recreate
the `postgres` volume and reseed from scratch if things get slow/disruptive. **Caveat
found late in the session**: manual cleanup of synthetic `User` rows is itself often
blocked by FK cascades (`audit_logs`, `user_role_assignments`, etc. reference
`users.id` with no `ON DELETE CASCADE`) — a plain `DELETE FROM users WHERE ...` fails
with a `ForeignKeyViolationError` unless every referencing table is cleaned first, in
dependency order. Non-`User` synthetic rows (e.g. `Country`/`University`/
`OverseasApplication`) are more tractable this way. Full recreate-and-reseed remains the
reliably simple option once this gets disruptive.

**I-04**: A full-suite parallel-worker Playwright run intermittently times out a handful
of unrelated specs purely under connection/DB contention (varies which spec(s) each
run — many different specs have each been hit at least once over the session). Not
specific to any one feature's code. Every one of these has always passed cleanly when
rerun in isolation or with fewer workers — confirm that before treating it as a real
regression.

**I-07**: A direct consequence of I-06, and a real E2E-*test* bug in its own right (not
a product defect): the generic `DataTable` component paginates client-side at **10 rows
per page**. A bare `page.locator("table")).toContainText(uniqueTitle)` assertion only
ever sees the currently-rendered page — once a list's row count passes 10, a freshly-
created, correctly-saved row can legitimately sit on page 2+ and never appear in that
locator's text, no matter how long you retry (longer timeouts do not help — the data
isn't missing, it's off-screen). If a new E2E spec fails on a `DataTable` assertion in a
way that looks like a timing bug but never clears with longer timeouts, check row count/
pagination first. Fix is mechanical: use the table's own "Search records" box to filter
to the run's unique text before asserting.

**I-03**: `stu-004-submissions.spec.ts` creates a real, uniquely-titled `Assignment` per
E2E run against the seeded demo student's batch. No delete endpoint exists for
Assignments (no evidence ever called for one), so these accumulate and can eventually
crowd `STU-002`'s "Upcoming work" dashboard widget, intermittently failing that one
dashboard case. Not a product defect — reseed clears it. Cleanup snippet:

```python
# docker compose exec -T api python - <<'EOF'  (paste the body below)
import asyncio
from app.core.database import SessionLocal
from sqlalchemy import select, delete
from app.models import Assignment, Submission

async def main():
    async with SessionLocal() as db:
        junk = (await db.execute(
            select(Assignment).where(Assignment.title.like("Overdue E2E Assignment%") | Assignment.title.like("On-Time E2E Assignment%") | Assignment.title.like("E2E Assignment%"))
        )).scalars().all()
        ids = [a.id for a in junk]
        if ids:
            await db.execute(delete(Submission).where(Submission.assignment_id.in_(ids)))
            await db.execute(delete(Assignment).where(Assignment.id.in_(ids)))
            await db.commit()

asyncio.run(main())
```

Then `docker compose exec api python -m app.seed`.

**I-05**: the `event.currentTarget`-after-`await` bug pattern (throws `TypeError:
Cannot read properties of null` intermittently after a successful submit — the DOM
nulls a synthetic event's `currentTarget` once dispatch finishes) is fixed in
`WorkflowPanel.tsx` (`ActionForm`, `DocumentUpload`) and `WebinarRegisterForm.tsx`, but
still present in `EnquiryForm.tsx`, `AdminBatchCreatePanel.tsx`,
`TrainerWorkflowForm.tsx` — fix opportunistically if a future feature touches those
files, or dedicate a pass to it later. Mechanical fix: capture the form element into a
local variable before the first `await`, use that instead of `event.currentTarget`
afterward (see `TeacherWorkspaceActions.tsx`'s `submit` helper for the correct pattern).

**I-08** (found and fixed this session, `AGT-002`): `auth._sync_role_assignment` lazily
creates a `UserRoleAssignment` row for any user on their first-ever login if one doesn't
already exist yet — and for `role="agent"` specifically, it creates it as
`approval_status="pending"`, by design, then never overwrites it on any later login. This
means any `role="agent"` demo/seed account that gets logged into *before* a seed step has
explicitly granted it an approved assignment row will get silently, permanently stuck
pending — `app/seed.py` now explicitly (re-)approves the demo `agent@edusphere.local`
account for exactly this reason (self-healing: it fixes an already-pending row, not just
a missing one). If a future feature adds another agent-like gated role with its own demo
account, apply the same seed-time approval, don't assume "the seed script creates the
user" is sufficient.

**I-09** (found and fixed this session, `AGT-003`): a pytest fixture's `_make_university()`
helper (copy-pasted across several test files this session, e.g. `test_agt_002_
referrals.py`, `test_agt_003_commission_accrual.py`) uuid-suffixes the `slug` field to
keep it unique per test run, but historically left the display `name` field as a plain
hardcoded string (e.g. `"AGT-002 Test University"`). Since `apps/api/tests/conftest.py`
has no test-DB isolation (`I-06`), every test run leaves a new `University` row with that
same non-unique name in the *real*, shared catalog — which any E2E spec's "pick any
available/unapplied university" helper can and eventually will pick, potentially applying
a real seeded account (even the shared demo student) to a throwaway pytest fixture
university and mutating a record another spec asserts a specific state about. Caught
exactly this way: `agt-003-commission-accrual.spec.ts`'s first draft picked one of
`test_agt_002_referrals.py`'s leftover universities for the seeded demo student, silently
breaking `agt-002-referrals.spec.ts`'s assertion about her application status. Fixed by
uuid-suffixing the `name` field too in both files, and cleaning up the ~30 stray
`University` rows (and their cascaded `OverseasApplication`/`AgentCommission` rows) this
had already accumulated. **When writing a new test fixture that creates a `University`
(or any entity an E2E "pick any available X" helper might select), uuid-suffix every
human-readable identifying field, not just the machine key (`slug`) — a duplicate display
name is just as much a collision risk as a duplicate slug, since nothing else in the
system enforces name uniqueness.**

## Established conventions (don't relearn these)

- **Docker has no bind mount** for `api`/`web` — any code or test-file change (including
  test files) requires `docker compose build <service>` + `docker compose up -d
  --force-recreate <service>` before it's visible in the container. `worker`/`beat` too,
  if `api` changed.
- Alembic migrations run automatically via each `api` container's own start command
  (`alembic upgrade head && uvicorn ...`) — no separate manual migration step needed.
- **Before-code checklist** per `prompts/13`: Requirement IDs, Acceptance Criteria,
  Dependencies, RBAC, DB/API/UI impact, exact Tests, Blockers. Check what the
  *inherited* codebase already does first — many features this session needed zero or
  near-zero code changes, because the real gap was missing test evidence or a narrow,
  confirmable defect, not missing implementation.
- **After-code checklist**: unit/API tests, E2E tests, RBAC verified at the API layer
  (not just hidden in UI), RTM + catalogue updated with honest evidence.
- **Test-run discipline** (a correction from the user mid-session, apply going
  forward): do **not** run the full backend/E2E regression suite after every single
  feature. Follow `prompts/13`'s own test-escalation order — changed unit tests →
  module tests → impacted API/integration → impacted UI/E2E → full regression **only at
  a merge/release gate** (or when the change's own blast radius is genuinely
  cross-cutting, like `AGT-001`'s shared-RBAC-helper fix this session, which
  legitimately warranted a full run). Prefer running just the new test file, plus the
  specific other test files that plausibly touch the same code path.
- A first Playwright run right after a `web` rebuild often shows 1-3 transient failures
  on public-content pages (Next.js fetch-cache warm-up) — rerun once before treating it
  as real.
- Test-data hygiene: E2E specs that create real backend records accumulate in the
  shared dev DB across repeated runs (see I-06 above). Use unique, timestamped/uuid'd
  titles for anything you assert against by name/title, so leftover debris from earlier
  runs in the *same* session never collides with a fresh assertion (this bit a fixed
  test once this session — a leftover "open"-status job from an earlier, pre-fix test
  run collided by name with a new test's own fresh job).
- E2E specs that act on the shared seeded demo student/counselor/admin accounts must
  target a *specific* record they themselves created (by unique title, or by the id
  returned from creating it) — never "the first/any pending item" for that identity.
  Multiple specs can run concurrently against the same seeded identity.
- Never let an E2E spec run a *mutating* action against a shared *seeded* record another
  spec asserts a specific state about — create your own throwaway record instead (found
  and fixed at least twice this session, e.g. `TRN-004`).
- `storage.presign_download()`'s local-storage fallback returns a path relative to the
  **API** container (`/local-files/...`), not the web app. `apps/web/app/local-files/
  [...path]/route.ts` (added by `STU-007`) already proxies this generally — any future
  feature handing out a `storage.presign_download()` link in local/dev mode is already
  covered, no repeat fix needed (S3 mode returns an absolute URL and is unaffected).
- Independently-fetching client panels on the same page (e.g. `EmployerJobsPanel` and
  `EmployerInterviewsPanel` on the employer dashboard) don't share state — creating a
  record in one panel doesn't refresh another panel's own list until it remounts/
  refetches. Not a bug, just something to account for in E2E specs that span two panels
  (reload the page between the two steps).
- If `docker ps`/`docker compose` commands fail with `failed to connect to the docker
  API at npipe:////./pipe/dockerDesktopLinuxEngine`, Docker Desktop itself has stopped
  running — ask the user to start it rather than hunting for install paths.
- **`WorkflowPanel.tsx` has one big early-return guard** (`if (!specs.length && !showX &&
  !showY && ... ) return null;`) near its top, separate from the JSX that actually renders
  each `show*` panel. Adding a new `show*` flag for a new dedicated panel (the
  `ScholarshipApplyPanel`/`OverseasApplyPanel`/etc. pattern) and wiring it into the JSX is
  not enough on its own — if the new flag isn't also added to that guard's OR-chain, the
  component silently returns `null` for that section whenever no *other* flag or spec
  happens to be true, and the entire panel silently never renders. Found building
  `STU-010`'s `FeePaymentPanel` (2026-09-03): the panel worked in every unit-level sense
  (correct API calls, correct conditional JSX) but was invisible in the actual app — caught
  only by real Playwright browser testing, not by the backend test suite passing or a
  visual diff of the JSX change itself. Always grep for the guard line and add the new flag
  there too, and always exercise a new `WorkflowPanel` section via a real browser (not just
  "the build succeeded" or "the API test passed") before calling it done.
