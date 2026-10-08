# rec-026 — Recruiter message templates, WhatsApp and email (design)

- **Feature:** rec-026 (`docs/delivery/RECRUITER_CRM_BACKLOG.md` §rec-026), EVID-018 §19 "💬 WhatsApp" (5 kinds, L766–776) and
  "📧 Email" (7 kinds, L778–792), R13 (telecaller pattern).
- **Decision:** `DEC-SCOPE-135` (provisional). MS1–MS11 are recommended defaults and are **UNVERIFIED**. The owner said "proceed with
  recommended answers".
- **Numbering (provisional; checked on `origin/main` @ `e055ff91`):** migration `0120_recruiter_messages`, API §12BC, RBAC §2.61. The
  numbers stay clear of rec-025 (`0118` / 133, in flight) and rec-028 (`0118` / 133, in flight; one of the two re-chains to `0119` /
  134). They are re-chained at merge.
- **Dependency:** rec-004 is MERGED (PR #160). rec-009 (candidates) is MERGED (PR #155).

## Understanding

Recruiters message two kinds of people:
- company contacts (HR, TA and hiring managers) about introductions, proposals, JDs and profiles;
- candidates about interviews, offers and joining.

The placement manager keeps a library of WhatsApp and email templates, one or more per source kind. A recruiter picks a template, the
recipient's values are filled in, the recruiter edits the text, and then sends it:
- **WhatsApp** opens wa.me. The send is logged only when the recruiter confirms it was sent.
- **Email** is queued and delivered by the worker through the existing SMTP account, with reply-to set to the recruiter. Its status is
  shown.

Each send is recorded against the contact or the candidate. This is the tel-012/013/014 engine, copied rather than shared, because
`lead_messages` is FK-bound to `enquiries` (backlog §0).

**Success criteria (backlog):**
- **AC1:** the 12 kinds are seeded with placeholders.
- **AC2:** an email send is queued, delivered and its status shown.
- **AC3:** a WhatsApp send is logged only on confirm.
- **Negative:** an unknown placeholder → 422.
- **Edge:** a candidate with no email.

## 1. Decisions (UNVERIFIED defaults)

| ID | Decision |
|---|---|
| MS1 | **Kinds** are fixed in code, in source order. WhatsApp kinds are `candidate_profiles`, `jd_confirmation`, `interview_reminder`, `follow_up` and `requirement_update`. Email kinds are `company_introduction`, `recruitment_proposal`, `candidate_profiles`, `jd_acknowledgement`, `interview_confirmation`, `offer_follow_up` and `joining_confirmation`. The migration seeds **one active template per kind (12)**, each named after its source label. |
| MS2 | **Placeholders** are `{name}` (the recipient), `{company}` (the contact's company; empty for a candidate until rec-017 links applications) and `{recruiter}` (the sender's name). Any other `{...}` is a 422 on save, using tel-012's rule (a lone brace is plain text). A missing value renders empty, and the recruiter edits the text before sending. |
| MS3 | **The library is global.** `placement_manager` and `super_admin` create, edit, deactivate and reactivate templates; nothing is deleted. Recruiters (`placement_team`) read the active ones. A name is unique per channel (case-insensitive). Only email has a subject. Body limits are 1000 characters for WhatsApp and 5000 for email; the subject limit is 200. |
| MS4 | **Party.** A message goes to exactly one company contact or one candidate (`CHECK`). A contact message also stores `company_id`. Any template may be used for either party. |
| MS5 | **Who.** A contact message follows the company, as rec-024 and rec-025 do. It is read by whoever has the company in scope (a manager's team, the assigned BDM, `super_admin`). It is sent by whoever has `can_edit` on the company (the assigned recruiter or `super_admin`). An archived company → 409; an inactive contact → 409. A candidate message follows R11: `candidates.WRITERS` send it and `READERS` (plus `hr_team`) read it. An archived candidate → 409. |
| MS6 | **WhatsApp** uses `https://wa.me/<digits>?text=…`, built from the party's mobile normalised to E.164 (ENH-014's +91 default). The API returns it as `whatsapp_to` on contacts and on candidate detail. The row is written only on "Yes, record as sent" (AC3). No usable number → 409. |
| MS7 | **Email** is stored `queued` and published after the commit. The worker claims it atomically and sends it with `mailer.lead_email_message`: From is the system address shown as "<recruiter> via EduSphere", and Reply-To is the recruiter. The status then moves to `sent`, `retrying` (ENH-014 back-off, 5 attempts) or `failed`. A beat sweep republishes stale rows and fails a stuck `sending`. The address is the party's address **at delivery** (tel-014 E7). No address → 409; SMTP unset → 503. |
| MS8 | **Caps** are per sender per IST day: 300 WhatsApp (409) and 100 email (429), as tel-013/014. |
| MS9 | **A message is permanent.** There is no edit or delete; the WhatsApp confirm step guards against mis-clicks. Audit and logs carry ids, the channel and the template id, never the text or an address. |
| MS10 | **Last contacted** (rec-004 C6) for a contact is the latest `sent_at` of its messages, excluding failed emails. It is computed on read in one grouped query. |
| MS11 | **R8 masking.** No placeholder reads candidate data, so a message to a company contact never carries a candidate's phone or email unless the recruiter types it. |

## 2. Data (migration 0120)

### `recruiter_message_templates`

The columns are:
- `id`
- `channel` (`whatsapp` / `email`)
- `kind`
- `name` (160)
- `subject` (200, nullable)
- `body` (Text)
- `active`
- `created_at` and `updated_at`

The checks are:
- the channel;
- the kind per channel;
- `(channel = 'email') = (subject IS NOT NULL)`.

There is a unique index on `(channel, lower(name))`. The migration seeds 12 rows.

### `recruiter_messages`

The columns are:
- `id`
- `company_id` and `contact_id` (FKs, null together)
- `candidate_id` (FK)
- `sender_user_id`
- `channel`
- `template_id` (FK, nullable) and `template_name` (the name at send time)
- `subject` and `body`
- `delivery_status` (email only) and `attempt_count`
- `sent_at`
- `created_at` and `updated_at`

The checks are:
- the party xor, as rec-025: `(contact_id IS NULL) = (company_id IS NULL) AND (contact_id IS NULL) <> (candidate_id IS NULL)`;
- the channel;
- the email shape: `(channel='email') = (delivery_status IS NOT NULL) AND (channel='email') = (subject IS NOT NULL)`;
- the status list.

The indexes are `(company_id, sent_at)`, `(contact_id, sent_at)`, `(candidate_id, sent_at)` and `(sender_user_id, sent_at)`. All FKs are
`RESTRICT`. The upgrade is guarded (0110's idiom). The downgrade refuses while any message exists.

## 3. API (§12BC)

| Method | Path | Notes |
|---|---|---|
| GET | `/recruiter/templates` | `channel?`, `active?`, `q?`, paged. Readers only (403). Recruiters see active rows only. |
| POST | `/recruiter/templates` | Manager or `super_admin`. MS2/MS3 checks; a duplicate name → 409. |
| PATCH | `/recruiter/templates/{id}` | The merged row is re-checked; the channel is fixed (422). `active` toggles. |
| GET | `/recruiter/templates/{id}/preview` | Sample values: Priya Sharma, Acme Technologies and the caller's name. |
| GET | `/recruiter/messages/render?template_id=&contact_id=\|candidate_id=` | The party's scope (404), then the template (active, 404). Returns `{template, subject, body}`. |
| POST | `/recruiter/messages` | Body: `contact_id` xor `candidate_id`, `channel`, `template_id?`, `subject` (email), `body`. Returns 201 with the message. Not idempotent. |
| GET | `/recruiter/companies/{id}/messages` | The company's contact messages, newest first. |
| GET | `/recruiter/candidates/{id}/messages` | The candidate's messages, newest first. |

The error order on a send is:
1. role (403);
2. the party in scope (404);
3. lock the party (the company row or the candidate row);
4. the write right (403), then archived or inactive (409);
5. SMTP unset (503);
6. no number or address (409);
7. the template (422);
8. the cap (409 / 429);
9. insert, audit, commit, enqueue (email), log.

A message in a response carries:
- `id`, `kind` (`contact` / `candidate`), `company_id`, `contact {id,name}` or null, and `candidate {id,name,code}` or null;
- `channel`, `template {id,name}` or null, `subject`, `body`, `delivery_status`, `sent_at` and `sender {id, full_name}`.

The additive output fields are `whatsapp_to` and `email` on the contact list items (`email` already exists), `whatsapp_to` on
`CandidateDetail`, and `last_contacted_at` now computed (MS10).

## 4. Worker

- `notifications/recruiter_email.py` holds `deliver_recruiter_email` and `sweep_stale_recruiter_emails`. It follows tel-014's
  claim/send/record pattern on the new table and reuses `lead_email._send` and the ENH-014 constants.
- `dispatch.enqueue_recruiter_email` publishes a message.
- `worker.py` adds `deliver_recruiter_email_task`, `sweep_stale_recruiter_emails_task` and a beat entry every 5 minutes.
- The tel-014 code is unchanged.

## 5. Web

- **Composers.** `WhatsAppComposer` and `EmailComposer` take a `target` (`{loadTemplates, renderUrl(templateId), createUrl, payload}`)
  instead of `leadId`. `LeadMessages` passes `leadTarget(leadId)`, so its behaviour is unchanged. The product-mismatch note shows only when
  the render says so.
- **Library.** `lib/recruiterMessages.ts` holds the types, kinds and labels, the URLs, the targets and `messageTitle`.
- **Messages section.** `RecruiterMessages.tsx` is a list section like rec-025's Calls:
  - On the company page, a contact picker (active contacts) offers "Send WhatsApp" and "Send email", each disabled with a reason when
    the contact has no number or address.
  - On the candidate page, the same two buttons appear without a picker.
  - Pending emails are polled every 5 s. The section handles loading, empty and error (Retry) states.
- **Template admin.** `/recruiter/manager/templates` shows `RecruiterTemplatesPanel` (create form, list filtered by channel, inline edit,
  deactivate/reactivate and preview). It reuses `TelecallerContentList` and `useLibraryRow`. It is added to `RECRUITER_MANAGER_NAV` as
  "Message templates".

## 6. Tests

- **pytest** `test_rec_026_messages.py`:
  - AC1: 12 seeds, and their placeholders are valid;
  - the template CRUD role matrix;
  - an unknown placeholder → 422;
  - a duplicate name → 409;
  - render for a contact and for a candidate;
  - AC3: a WhatsApp send is logged;
  - AC2: an email is queued and published after the commit, then delivered by `deliver_recruiter_email` with SMTP mocked, giving
    `sent` / `retrying` / `failed`;
  - a candidate with no email → 409;
  - no number → 409;
  - an inactive contact, an archived company or an archived candidate → 409;
  - scope 404, a manager sending to a contact → 403, and `hr_team` reads candidate messages;
  - the caps;
  - the audit carries no body;
  - last contacted.
- **pytest** `test_rec_026_migration.py`: the checks equal the models', and 12 seeds.
- **vitest:** the lib, the composer target (LeadMessages unchanged), `RecruiterMessages` and the templates panel.
- **Playwright** `rec-026-messages.spec.ts`:
  - the manager edits a template;
  - a recruiter sends a WhatsApp to a contact (confirm) and an email to a candidate (queued → status shown).

## 7. Risks

- The composer prop change touches tel-013/014. It is covered by the existing `LeadMessages` and composer tests, which are rerun.
- `recruiter_contacts.list_out` is also edited by rec-025 (same lines) and rec-028, so the merge is resolved by hand.
- The route-inventory and RBAC tests need rows for the new routes.
