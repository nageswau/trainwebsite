# tel-015 — Lead timeline: exploratory browser QA (2026-10-07)

Stack: isolated compose project `tel015` (web `:3015`, API `:8015`), branch `feature/tel-015`. Browser: an isolated Microsoft Edge profile
driven over CDP (browser-use, `BU_CDP_URL`), plus the Playwright specs in the `web-test` container. Data: throwaway accounts and leads made
through the API (`qa015-*@example.local`): a lead with 58 entries (paging), a lead with long / markup-like text, a lead reassigned from one
telecaller to another, a plain lead.

## Scenarios

| # | Scenario | Result |
|---|---|---|
| 1 | Telecaller opens a lead: created, assignment, stage, WhatsApp (long body), follow-up with `<img onerror>` notes | Pass — markup shown as text (0 injected nodes); excerpt cut at 200 with "…"; no console errors |
| 2 | Desktop 1280 / tablet 768 / phone 390 | Pass — no horizontal scroll; rail, badges, wrapped names readable at 390 |
| 3 | 58 entries: first page 50, "Show older entries" | Pass — 58 rows, no duplicates, button gone at the end, "Showing 50 of 58 entries." before |
| 4 | Reassigned lead (AC2): new telecaller | Pass — the previous telecaller's call shown with their name; "Reassigned from A to B" by the manager |
| 5 | Previous telecaller opens the reassigned lead | Pass — "Lead not found" page; timeline API `404` |
| 6 | Counselor without the lead / counselor on the admin route / signed out | Pass — `404` / `403` / `401` |
| 7 | Log a call on the page (e2e) | **QA15-01** — then pass |
| 8 | Telecaller's own lead (e2e) | **QA15-02** — then pass |
| 9 | Email entry | SMTP is not configured on this stack (tel-014 → `503`), so not reproducible in the browser — **QA15-03** |
| 10 | Counselor and IT admin History (e2e `tel-015-timeline.spec.ts`) | Pass |

## Issues

### QA15-01 — a call logged now lists before the lead's creation (Medium, telecaller, lead detail)
- **Steps:** create a lead; on its page Log call → Save call.
- **Expected:** the call is the newest entry. **Actual:** it listed below "Lead created": the form sends the call time to the minute
  (`14:03:00`), seconds before the lead's own `created_at`.
- **Fix (test-first):** a call recorded within the minute of its stated time is placed at its recording time; a call dated earlier (CL4)
  keeps its own time. `test_a_call_logged_at_the_current_minute_lists_after_the_lead_was_created` (RED → GREEN); e2e asserts "Lead created"
  stays last after the call.

### QA15-02 — a telecaller's own lead never says who it was assigned to (Low, telecaller)
- **Steps:** a telecaller creates a lead (tel-005: assigned to themselves, no `lead.assign` row) and opens it.
- **Expected:** EVID-019 L480 "Assigned to Telecaller". **Actual:** only "Stage: New Lead → Assigned".
- **Fix:** the creation entry carries `event = self_assigned` (from the `lead.create` audit's `assigned`), shown as "Assigned to {name}".
  `test_a_telecallers_own_lead_says_it_was_assigned_to_them` (RED → GREEN), `leadTimeline.test.ts`, e2e.

### QA15-03 — email entries not exercised end to end (Low, coverage)
- Covered instead by `test_an_email_entry_carries_its_subject_and_delivery_status` (subject, status, template, excerpt) and the
  `leadTimeline.test.ts` email cases ("Email failed", subject line).

### Test-only
- `tel-015-timeline.spec.ts` used the outcome key's wording; the label is "Connected – Interested".
- `tel-008-lead-workspace.spec.ts` counted entries, which depends on whether tel-007 found a round-robin telecaller; it now checks the
  content and the +2 after priority + stage.

## Not defects
- Console errors seen during scenario 6 are the deliberate 401/403/404 probes.
