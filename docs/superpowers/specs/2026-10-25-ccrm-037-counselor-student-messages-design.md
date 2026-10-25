# ccrm-037 — Counselor communication templates and student/application message log (design)

NO-ASSUMPTION MODE. Source: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` `ccrm-037` (source PDF §11 communication channels: "templates should
be configurable; record outbound and responses against the student and application"; the PDF is `UNVERIFIED` and not in the repository —
only the backlog's wording is used). Dependency ccrm-004 (counselor activity logging, `DEC-SCOPE-259`, PR #322) is merged on `origin/main`.

## Requirement (backlog, verbatim scope)

Overseas-Admin-managed email/WhatsApp templates for counselors with merge fields (student, university, deadline); sends to students logged
against student + application; replies recorded manually (no inbound provider) unless an inbound channel exists. Reuse the tel-013/014 and
rec-026 template services. Existing behaviour: templates exist for telecaller, partnership and recruiter only.

Verified on `origin/main` @ `0219aca4`: there is no inbound channel for student messages (the only inbound route is
`/inbound/university-email`, matched to applications from universities), so replies are recorded manually.

## Alternatives considered

1. **Reuse `tel_message_templates` / `lead_messages`** — rejected: the table is the telecaller manager's library (telecaller kinds,
   products, brochures) and `lead_messages` is bound to `enquiries`; a student is a `users` row and a message needs an application.
2. **One generic message table for every module** — rejected: rec-026 and upc-012 deliberately copied the engine rather than share it;
   a generic table would touch three live features (high regression risk, out of scope).
3. **Chosen:** the upc-012 engine copied onto two new tables (`counselor_message_templates`, `student_messages`, migration `0191`), with
   the frontend's existing shared pieces reused unchanged in behaviour: `RecruiterTemplatesPanel` (library config), `MessagesSection`,
   `WhatsAppComposer`, `EmailComposer` (a `ComposerTarget` carries the application id). The partnership template schemas (no kind) are
   reused as-is.

## Recommended defaults (`NEEDS_CONFIRMATION`; the owner asked for an autonomous run with recommended answers) — `DEC-SCOPE-273`

- **MT1 Template library.** One global library: WhatsApp and email, no kind (the source names none), name unique per channel
  (case-insensitive), subject only on email, body ≤ 1000 (WhatsApp) / 5000 (email), never deleted — deactivated. The Overseas Admin
  (`overseas_admin`, division overseas) and `super_admin` create, edit and deactivate; the overseas counselor reads active templates only.
  Every other role 403.
- **MT2 Merge fields.** `{name}` (the student), `{university}`, `{course}`, `{intake}`, `{application_deadline}`, `{offer_deadline}`
  (from the application the message is about; dates as "14 Sept 2026") and `{counselor}` (the sender). Unknown placeholders are refused on
  save (422). A message about no application renders the application fields empty and the composer lists them as missing.
- **MT3 Recipient.** The student's account email and phone (normalised to a wa.me number); never request fields.
- **MT4 Who sends.** The overseas counselor with the student in csc-001 scope (own applications' and linked students). The message may be
  about one of the student's applications **that is the counselor's own** (ccrm-010 N3); anything else 422. The Overseas Admin reads every
  student's log but does not send. Out-of-scope / unknown student 404; other roles 403; anonymous 401.
- **MT5 Send rules.** Deactivated student 409; no usable number 409; SMTP not configured 503; template must be active and of the channel
  422; caps per sender per IST day — 300 WhatsApp (409), 100 email (429). Not idempotent (each call is one send; caps bound a retry).
- **MT6 Email delivery.** Stored `queued`, published after the commit; the worker claims the row atomically, sends to the student's email
  at send time, retries (ENH-014 constants), and a sweeper republishes stale rows and fails rows stuck in `sending` (upc-012 UC7).
- **MT7 Replies.** Recorded manually by the counselor: WhatsApp or email, optional subject (email only), body, received time (default now;
  not in the future beyond the 5-minute clock tolerance; at most 7 days back — 422), optional own application. 300 replies per recorder per
  IST day (409). A reply has no template and no delivery status.
- **MT8 Permanent.** Messages and replies are never edited or deleted (rec-026 MS9 / upc-012 precedent).
- **MT9 Read.** The student's whole log, newest first, whoever wrote it (history survives a reassignment, ccrm-010 N2), with the
  application label and direction. Shown on the student 360 Activities tab. No student- or agent-facing route returns it.
- **MT10 Audit and logs.** `counselor_template.create|update`, `student_message.create`, `student_message.reply` with ids, channel,
  direction and template id — never the text, a subject, a number or an address.

## API (§12FZ)

- `GET /api/v1/counselor/templates?channel&active&q&limit&offset` — page of `{id, channel, name, subject, body, active}`.
- `POST /api/v1/counselor/templates` / `PATCH /api/v1/counselor/templates/{id}` — upc-012's bodies and rules (channel fixed).
- `GET /api/v1/counselor/templates/{id}/preview` — `{subject, body, missing}` with sample values.
- `GET /api/v1/counselor/students/{id}/messages?limit&offset` — `{items, total, limit, offset, recipient: {name, email, whatsapp_to},
  applications: [{id, label}]}` (applications = those a message may be about: the counselor's own, every one for the admin).
- `GET /api/v1/counselor/students/{id}/messages/render?template_id&application_id` — `{template, subject, body, missing}`.
- `POST /api/v1/counselor/students/{id}/messages` — `{channel, template_id?, subject (email), body, application_id?}` → 201 message.
- `POST /api/v1/counselor/students/{id}/replies` — `{channel, subject?, body, received_at?, application_id?}` → 201 message.

A message = `{id, student_id, application: {id, label} | null, direction: "outbound" | "inbound", channel, template: {id, name} | null,
subject, body, delivery_status, sent_at, sender: {id, full_name}}`.

## Frontend

- `/overseas/admin/message-templates` — `RecruiterTemplatesPanel` with `COUNSELOR_LIBRARY`; sidebar link "Message templates".
- Student 360 Activities tab — a Messages card (`components/StudentMessages.tsx`): "About" select (general or one of the counselor's
  applications), the shared `MessagesSection` (Send WhatsApp / Send email, the list with pending-email polling) and a "Record a reply"
  form. The admin sees the list only. `MessagesSection` gains an optional direction/application line (backward compatible: absent fields
  render exactly as today).

## Security (Phase 3)

Role and division checked before any body is read; scope through `student_profiles.staff_student` (404 on no disclosure); application
ownership re-checked server-side on render, send and reply; the recipient is never taken from the client; caps bound abuse of the shared
SMTP account; SQL through SQLAlchemy with bound parameters; template/message text is plain text (React escapes, the mailer escapes HTML,
wa.me URL-encodes); cookie session with the app's existing CSRF stance; audit and logs carry no text or contact data.

## Tests

Backend `tests/test_ccrm_037_migration.py`, `tests/test_ccrm_037_messages.py`, `tests/test_ccrm_037_delivery.py`; frontend
`tests/components/StudentMessages.test.tsx`, `tests/lib/counselorMessages.test.ts`, e2e `tests/e2e/ccrm-037-student-messages.spec.ts`.

## Regression risks

`MessagesSection` is shared by the recruiter and university pages (only additive optional fields); `worker.py` gains one task pair and
one beat entry; `dispatch.py` gains one publisher. Telecaller, recruiter and partnership libraries are untouched.
