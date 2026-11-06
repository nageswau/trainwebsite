# hrc-032 — Recruitment notification rules and delivery exceptions (design)

**Decision:** `DEC-SCOPE-413` (builder's calls N1–N12, `NEEDS_CONFIRMATION`). **Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md`
hrc-032 (PDF §10.2 "Record notification delivery status and provide a retry mechanism"; §12 notify owners; §13 trigger table; §16
"integration logs and retry queues"; §17 QA "Failed … notifications are visible and retryable"; PDF classified `UNVERIFIED`). Scope approved
by the owner 2026-11-01 (backlog Q-00); the owner said to proceed with the recommended answers. Dependencies itc-002 (`DEC-SCOPE-336`),
hrc-009 (`DEC-SCOPE-390`), hrc-026 and hrc-030 (`DEC-SCOPE-409`) are merged.

## Intent
Recruitment notices today are a mix: some §13 triggers notify nobody, some put a status or a result into an email/WhatsApp/SMS preview, and a
delivery that exhausted its automatic retries is invisible. hrc-032 sends every missing §13 trigger through the itc-002 catalogue (fixed,
preview-safe text), and gives a `notifications.retry` holder a **Delivery exceptions** page listing failed deliveries with a **Retry**.

**Non-goals:** a platform-wide notification console (fee, course and overseas notices stay out); configurable notice rules; a new provider;
per-candidate alert preferences beyond the existing opt-ins.
**Anti-goal:** a result, status word or feedback text in any preview; a notice to a candidate for an internal stage; one trigger producing
two notices.

## §13 trigger map
| §13 trigger | Recipient | Event type | State before | hrc-032 |
|---|---|---|---|---|
| Registration, unassigned | recruiter / managers | `it.candidate.assigned`, `it.candidate.unassigned` | hrc-024 | exceptions only |
| Vacancy eligibility changed | owners | `it.requirement.review_needed` | hrc-009 | exceptions only |
| **Vacancy changed** | owners but the editor | `it.requirement.changed` | missing | new (N3) |
| **Candidate applies** | application owner + vacancy owners | `it.application.new` | missing | new (N2) |
| Candidate applies | candidate | `it.application.received` | hrc-026 receipt | tagged (N5) |
| Candidate-visible status change | candidate | `it.application.updated` | text named the status | fixed text (N5) |
| Interview scheduled/updated/rescheduled/cancelled | candidate | `it.interview.<kind>` | hrc-028 | tagged (N5) |
| Interviewer assigned | panel member | `it.interview.assigned` | hrc-029 | tagged (N5) |
| **Feedback overdue** | panel members without feedback, application owner | `it.interview.feedback_overdue` | missing | new (N6) |
| Result published | candidate | `it.interview.result_published` | text was the result | fixed text (N4) |
| **New matching vacancy** | matching opted-in portal candidates | `it.job.new_match` | missing | new (N7) |
| Delivery failed | `notifications.retry` holders | the exceptions page | invisible | new (N8–N10) |

## Builder's calls
- **N1 Catalogue.** The new types live in `notifications/events.py`'s `EVENTS` with fixed text; `RECRUITMENT_EVENTS` there names every
  recruitment type with a label, for the page's filter and scope.
- **N2 Applied → staff.** `applications.send_receipt` is reached only by a candidate's own application (student portal, candidate portal),
  so it also notifies the application's owner and the vacancy's owners. A recruiter-added application notifies nobody (the recruiter did it).
- **N3 Vacancy changed.** Any save that changed something (fields, skills, weights, status, employer and legacy edits) notifies the owners
  but the actor. When the same save already flagged applications for review (hrc-009), the owners get only that notice (one trigger, one
  notice). The owners are the primary and the `job_assignments` rows, hrc-009's set. This also closes the two owner notices the hrc-006 and
  hrc-007 entries deferred to hrc-032: a new owner hears `it.requirement.assigned`, and HR Managers hear `it.requirement.approval_needed` on a
  submit; an approve or reject reaches the owners as `it.requirement.changed`.
- **N4 Result published.** The candidate-facing message stays in "My results", no longer in the notice: the notice is fixed text (backlog
  Security line, and `Rejected` / `Congratulations` must not sit on a lock screen). This revises hrc-030 R6's "the notice carries the message"
  for portal users. A candidate with no portal login keeps hrc-030's direct email: they have nowhere else to read it.
- **N5 Status notice.** `Your application status is now <X>` names a result (`Rejected`, `Selected`), so it becomes fixed text under the same
  title; the hrc-026 A4 visible-stage rule is unchanged. The receipt keeps its text (Application ID, role, company: no result) and is tagged.
- **N6 Feedback overdue.** An interview is overdue when it is scheduled/rescheduled/completed (not decided or cancelled), its end
  (`ends_at`, else `scheduled_at`) passed more than `FEEDBACK_GRACE_HOURS` = 24 ago (`NEEDS_CONFIRMATION`), and it has no `interview_feedback`
  row. The hourly `hrc032-feedback-overdue` beat job takes at most `SWEEP_LIMIT` = 200, oldest first, `FOR UPDATE SKIP LOCKED`, sets
  `interviews.overdue_notified_at` in the same transaction and notifies once. Recipients: panel members without their own panel feedback, and
  the application's owner. The migration stamps interviews already past the grace period, so the first run does not send a backlog.
- **N7 New match.** The hourly `hrc032-new-matches` beat job takes at most `MATCH_JOBS_LIMIT` = 20 open, visible jobs with
  `jobs.match_notified_at IS NULL`, and notifies portal candidates in the opted-in pool with a score of at least hrc-027's
  `RECOMMENDED_MIN_SCORE` who pass the hard filters, can see the job (hrc-008) and have not applied, at most `MATCH_RECIPIENTS_LIMIT` = 200
  per job, best first. The marker makes it once per job, so a re-opened job does not notify again. The migration stamps today's open jobs. It
  runs in the beat job, not on the writer's request: scoring the pool must not slow a save or fail it.
- **N8 Exceptions list.** `GET /recruiter/notification-exceptions`: failed `notification_deliveries` of recruitment events and failed
  `recruiter_messages` emails (rec-026; interview notices to candidates with no login and to client contacts are these), newest failure
  first, with type and channel filters. Shows the type, recipient's name, channel, error and attempts; never the body or subject. `skipped`
  (opted out, inactive) and `not_configured` are not failures.
- **Safe error.** A webhook's stored error quotes its URL, which can carry a token, so every `http(s)://` run is masked on read. Someone who must
  not be written to any more (an anonymised candidate, a do-not-contact contact) is neither listed nor retried.
- **N9 Retry.** `POST /recruiter/notification-exceptions/{source}/{id}/retry`. One atomic `failed → queued` with `attempt_count = 0` (a fresh
  automatic cycle), audited (`notification.retry`, ids only), published after commit. Not failed any more: 409, so a double click sends once.
  Unknown or out-of-scope: 404. A delivery that is not a recruitment event is out of scope.
- **N10 Grant.** New catalogue key `notifications.retry`, seeded for `hr_manager` and `placement_manager`; super_admin holds all. Reading the
  page takes the same grant (it exists to act), so there is no second key.
- **N11 Recruiter inbox.** Recruiters, officers and managers have no page for their in-app notices. `/recruiter/notifications` mounts the shared
  `SchoolNotificationList`, whose Type filter (itc-002) is the backlog's "notification type filters" for a typed notice; no API change.
- **N12 Consent.** WhatsApp and SMS stay opt-in through `allowed_channels`, for every new type. `it.job.new_match` only goes to candidates in
  the opted-in pool (hrc-035's gate); deactivated users are skipped by `notify`.

## Error and race handling
- Everything uses `notify`'s post-commit publish; a rollback sends nothing. A broker outage leaves rows queued for the existing sweeper.
- Sweeps commit per batch (feedback) or per job (matches), so one failure loses at most that unit; `SKIP LOCKED` lets a second beat run skip.
- Marker and notice share a transaction: both or neither.
- `deliver` already claims atomically, so a retried row published twice sends once.

## Acceptance (from the backlog)
1. Each trigger produces its notice exactly once (applied, vacancy changed, overdue, new match, result, status; reruns add nothing).
2. Internal stage changes send nothing to the candidate.
3. A failed delivery appears on the exceptions page and its retry succeeds; provider down for an hour (retries exhausted) → appears.
4. Previews are safe: no catalogue text or new notice names a result, feedback, or status word.
5. Only `notifications.retry` holders read or retry (403 otherwise).

## Tests
`apps/api/tests/test_hrc_032_notifications.py` (triggers, once-only, consent, sweep bounds), `test_hrc_032_exceptions.py` (list, filters, retry,
409/403/404, exhausted retries), `test_hrc_032_migration.py`; vitest for the page, inbox filter and navigation; Playwright
`apps/web/tests/e2e/hrc-032-*.spec.ts`. Pinned text in `test_rec_017_tracking`, `test_rec_018_screening`, `test_hrc_026_application_record` and
`test_hrc_030_results` moves to the fixed text.

## Regression risks
Tests pinning notice bodies (above); `test_hrc_002_roles` catalogue test; `navigation.recruiter.test` exact menus; rec-038 route coverage (new
routes need rows); enh014/rec026 delivery tests (the delivery paths themselves are untouched).
