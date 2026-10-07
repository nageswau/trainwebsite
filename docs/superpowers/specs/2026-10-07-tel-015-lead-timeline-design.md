# tel-015 — Lead timeline (design)

Status: draft for DEC-SCOPE-114 · API §12AH · RBAC 2.40 · **no migration**. Branch `feature/tel-015` (worktree `tel-015`), cut from
main @ `cca01447`.

## 1. Evidence and intent

- **Source:** EVID-019 §13 (L474–L496, backlog Appendix A): "Each student should have a complete history" — Lead Created, Assigned to
  Telecaller, Call Made, WhatsApp Sent, Follow-up Scheduled, Counselling Appointment, Counselor Assigned, Application/Enrollment,
  Converted; "This prevents information from being lost when staff changes."
- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` §tel-015. AC1 every event kind appears with actor and time; AC2 a reassigned lead
  keeps the previous telecaller's events; AC3 the order is stable for equal timestamps. Negative: out-of-scope id → 404. Edge: system
  events show "System".
- **Existing behaviour (verified in code):** tel-008 W1 shipped `GET /telecaller/leads/{id}/timeline` (`telecaller_leads.timeline_page`):
  stage changes + priority changes, and tel-005 added repeat enquiries; tel-018 added the counselor route
  `GET /counselor/leads/{id}/timeline` on the same service. Telecaller/manager and counselor lead pages render it as "Activity".
  Division admins only see stage history (`GET /admin/leads/{id}/stage-history`, the "History" toggle).
- **Dependencies:** tel-010, tel-011, tel-013, tel-014, tel-016 — all merged on main.

## 2. Owner answers (2026-10-07, all recommended)

- **TM1 — admins:** add `GET /admin/leads/{id}/timeline` (same 404 / 403 division rule as `stage-history`); the admin "History" toggle shows
  the merged timeline. `stage-history` stays unchanged (API compatibility).
- **TM2 — content:** summary + excerpt. Calls: type, outcome, duration, remarks excerpt. Messages: channel, template name (or "Custom
  message"), email subject + delivery status, body excerpt. Follow-up notes, cancel reasons and appointment reasons likewise. Excerpt =
  first 200 characters; the full text stays in the Calls / Messages / Follow-ups sections.
- **TM3 — downstream milestones:** once a student is linked, each IT enrolment / overseas application / visa case appears at its creation
  time as a "System" entry with its current status; read live, so an unlink removes them.

## 3. Design decisions (D1–D8)

- **D1 — one service, three routes.** `telecaller_leads.timeline_page` stays the only reader; each route applies its own scope first
  (telecaller/manager `lead_pipeline.scope`, counselor `counselor_scope`, admin division). The service only sees a lead id.
- **D2 — derived, no new table.** A `UNION ALL` over the existing event tables, counted and paged in SQL (`limit` ≤ 100, `offset`).
  Every branch filters on an indexed lead column (or `audit_logs (entity_type, entity_id, created_at)`).
- **D3 — event catalogue.**

  | kind | source | at | actor | from / to | other |
  |---|---|---|---|---|---|
  | `created` | `enquiries` | `created_at` | `lead.create` audit user, else the BDM, else none | source / subject | — |
  | `enquiry` | `lead_enquiries` (tel-005) | `created_at` | creator | source / subject | reason = message |
  | `stage` | `lead_stage_history` | `created_at` | actor or System | stage keys + labels | event (e.g. `returned`, `converted`) |
  | `priority` | audit `lead.priority_change` | `created_at` | user | priority | — |
  | `assignment` | audit `lead.assign` | `created_at` | user or System (round robin) | previous / new telecaller (id, name; `""` = unassigned) | event = method |
  | `handover` | audit `lead.handover` | `created_at` | user | previous / new counselor | — |
  | `student_link` | audit `lead.convert` / `lead.unconvert` | `created_at` | user | — / student (id, name) | event = `linked` / `unlinked` |
  | `call` | `lead_calls` | `occurred_at` | caller | call type / outcome | duration_seconds, reason = remarks excerpt |
  | `message` | `lead_messages` | `sent_at` | sender | channel / template name (`""` = custom) | subject, status = delivery status, reason = body excerpt |
  | `follow_up` | `lead_follow_ups` ×3 | created / completed / cancelled at | creator / completer / `lead_follow_up.cancel` audit user, else System | reason key / — | event = `scheduled` / `done` / `cancelled`; scheduled_for = due; reason = notes or cancel reason excerpt |
  | `appointment` | `appointment_events` ⋈ `appointments` | event `created_at` | actor | from / to status | event = appointment type, subject = CAP code, scheduled_for, reason excerpt |
  | `milestone` | `enrollments` / `overseas_applications` / `visa_cases` of `converted_user_id` | `created_at` | System | — / batch or university name | event = `enrollment` / `application` / `visa`, status, subject = reference |

  The return keeps its tel-018 stage row (`event = returned`, with the reason); the computed conversion is the stage row
  `event = converted`. No separate rows for `lead.return` (it would duplicate). An assignment shows both its audit row ("Assigned to
  Priya") and the system stage move it caused — each is a separate fact.
- **D4 — stable order (AC3).** `ORDER BY at DESC, rank DESC, seq DESC, id DESC`. `rank` puts one transaction's rows in causal order
  (created 0 < enquiry 1 < assignment / handover / student link 2 < call / message / follow-up / appointment / priority / milestone 3 <
  stage 4), so a stage move shows above the action that caused it; `seq` is the stage / appointment-event `position`; `id` makes the
  order total.
- **D5 — backward-compatible row.** `LeadTimelineRow` keeps every W1 field; `kind` widens; new optional fields `subject`, `status`,
  `duration_seconds`, `scheduled_for` (null when not applicable). Keys only for calls / follow-ups / appointments / messages — the web
  client owns those labels (project convention); stage and priority labels stay server-side as today.
- **D6 — AC2.** Events are keyed by lead and keep their own actor, so a reassignment or deactivation (tel-025) changes nothing already
  shown. Deleted calls / WhatsApp rows (CL4 / WA3 same-day delete) are gone from the timeline as from their sections.
- **D7 — privacy.** Only the lead's readers reach the timeline (D1). Free text is excerpted (TM2). Logs keep ids only; the timeline
  writes nothing.
- **D8 — web.** One `LeadTimeline` component (the `.jtl` CSS timeline) used by the telecaller/manager detail, the counselor detail and the
  admin History panel: loading, empty and error states, "Show older" paging (offset), refresh on a `version` change. Titles and detail
  lines come from `lib/leadTimeline.ts` (`timelineEntry`), which replaces `activityTitle`.

## 4. Error handling

404 out of scope / unknown id (all three routes, before the query); admin other division 403 (as `stage-history`); `limit`/`offset`
validated by the existing `LIMIT` / `OFFSET` (422). The web shows "Unable to load the activity." with a Retry button and keeps the rows
it already has when "Show older" fails.

## 5. Testing

- API (`tests/test_tel_015_timeline.py`): every kind with actor + time on one lead (the §13 chain); AC2 reassignment keeps the old
  telecaller's call / message; AC3 equal timestamps in a stable, causal order across two reads and across page boundaries; system
  events actor null; excerpt ≤ 200; out-of-scope telecaller 404, counselor not assigned 404, admin other division 403, super_admin ok;
  milestones appear after a link and vanish after an unlink; paging totals.
- Regression: `test_tel_008_workspace`, `test_tel_005_intake`, `test_tel_018_handover`, `test_tel_018_return` (existing timeline asserts).
- Web (vitest): `LeadTimeline` titles per kind, System / Website actors, Show older, error + retry; updated `LeadDetailPanel`,
  `CounselorLeadDetail`, `AdminLeadStage` tests.
- e2e (`tel-015-timeline.spec.ts`): a seeded lead's chain visible to telecaller, counselor and admin; mobile width.
