# upc-012 — University calls, message templates, WhatsApp and email (design)

- **Feature:** upc-012 (`docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §upc-012), EVID-020 §12 "Every email/call/WhatsApp/meeting
  should be stored against the university" (L437–451), backlog decision U10 (telecaller pattern; templates maintained by
  `partnership_head`).
- **Decision:** `DEC-SCOPE-140`. UC1–UC10 are recommended defaults and are **UNVERIFIED**. The owner said "proceed with recommended
  answers".
- **Numbering (re-chained on `origin/main` @ `e91932a3`, after rec-010 took 0123 / DEC-SCOPE-138 / §12BF / §2.64 and upc-026 took 0124 / DEC-SCOPE-139 / §12BG / §2.65):** migration `0125_university_comms` (down `0124_university_documents`), API §12BH,
  RBAC §2.66.
- **Dependency:** upc-006 (university contacts) is MERGED.

## Understanding

Partnership managers phone, WhatsApp and email the people at a university (upc-006 contacts). Every interaction must stay on the
university so the history is never lost (§12); upc-013 later shows it as one timeline. The head keeps a library of WhatsApp and email
templates. A manager picks a template, the contact's values are filled in, edits the text and sends:
- **Call:** a manual log beside a `tel:` link — contact, outcome, notes and an optional next follow-up date.
- **WhatsApp:** opens wa.me; the send is logged only when the manager confirms it was sent.
- **Email:** queued and delivered by the worker over the existing SMTP account, reply-to the manager; its delivery status is shown.

The contact's "last interaction" reflects the latest call or message. This is the rec-025/rec-026 engine (itself tel-010/012/013/014),
copied rather than shared: `recruiter_messages` and `recruiter_calls` are FK-bound to companies and candidates.

**Success criteria (backlog):**
- **AC1:** a sent email is visible with its delivery status.
- **AC2:** WhatsApp is logged only on confirm.
- **AC3:** a call updates last interaction.
- **Positive:** a proposal email from a template.
- **Negative:** an unknown template placeholder → 422.
- **Edge:** a contact without an email.

## 1. Decisions (UNVERIFIED defaults)

| ID | Decision |
|---|---|
| UC1 | **Calls.** A call is on one university contact (required on create); the university is read from the contact, never from the client. Outcomes, direction, duration (0–14400 s), notes (≤ 2000) and the time rules (default now; ≤ 60 s in the future; ≤ 7 days back) are rec-025's CA1/CA5/CA8, reused. `next_follow_up_on` is an optional date, today…today + 365 (IST), stored on the call; upc-020 turns it into tasks. A call is **permanent** (the backlog API has no edit or delete). Cap: 300 calls per caller per IST day. |
| UC2 | **Contact delete.** upc-006 lets a contact be deleted (PII, CT7). `contact_id` on calls and messages is `ON DELETE SET NULL`, so the delete still works and the history stays on the university (shown as "a removed contact"). A queued email to a deleted contact fails with `no_address`. |
| UC3 | **Who.** Reads follow upc-006's full contact view: `partnership_manager` (with a profile), `partnership_head` and `super_admin` read any university's calls and messages; `overseas_admin` and every other role → 403 (U14 keeps internal history from other roles). Writes need the university's `can_edit_contacts` (the owning manager, the head of the owning team, `super_admin`) → 403; an inactive university → 409. |
| UC4 | **Templates.** One global library, maintained by `partnership_head` and `super_admin` (create, edit, deactivate, reactivate; never deleted). Managers read the active ones. Fields: channel (`whatsapp`/`email`), name (≤ 160, unique per channel case-insensitively → 409), subject (email only, ≤ 200), body (1000 WhatsApp / 5000 email), active. **No kind and no seeded rows**: the source names no template kinds, so the head writes them. |
| UC5 | **Placeholders** are `{name}` (the contact), `{university}` (the university's name) and `{manager}` (the sender). Any other `{...}` → 422 on save (tel-012's rule; a lone brace is text). A render reports the placeholders that had no value. |
| UC6 | **WhatsApp** uses `https://wa.me/<digits>?text=…`. The number is the contact's WhatsApp, else their phone, normalised to E.164 (`wa_number`). The contact output carries it as `whatsapp_to`. No usable number → 409. The row is written only on "Yes, record as sent". |
| UC7 | **Email** is stored `queued` and published after the commit. The worker claims it atomically and sends it with `mailer.lead_email_message` (From "<manager> via EduSphere", Reply-To the manager), then records `sent`, `retrying` (ENH-014 back-off, 5 attempts) or `failed`. A beat sweep republishes stale rows and fails a stuck `sending`. The address is the contact's **at delivery**. No address → 409; SMTP unset → 503. |
| UC8 | **Caps** per sender per IST day: 300 WhatsApp (409) and 100 email (429), as rec-026 MS8. |
| UC9 | **A message is permanent.** Audit and logs carry ids, the channel and the template id — never the text, a subject, a number or an address. |
| UC10 | **Last interaction** of a contact is the later of its latest call `occurred_at` and its latest message `sent_at` (failed emails excluded), computed on read in grouped queries, on the contact list and the contact detail. upc-009 meetings join later. |

## 2. Data (migration 0125)

### `partnership_message_templates`
`id`, `channel`, `name` (160), `subject` (200, nullable), `body` (Text), `active`, `created_at`, `updated_at`.
Checks: the channel; `(channel = 'email') = (subject IS NOT NULL)`. Unique index on `(channel, lower(name))`.

### `university_calls`
`id`, `university_id` (FK RESTRICT), `contact_id` (FK SET NULL, nullable), `caller_user_id` (FK RESTRICT), `occurred_at`,
`duration_seconds` (nullable), `direction`, `outcome`, `notes` (nullable), `next_follow_up_on` (date, nullable), `created_at`, `updated_at`.
Checks: direction, outcome, duration range. Indexes `(university_id, occurred_at)`, `(contact_id, occurred_at)`, `(caller_user_id, occurred_at)`.

### `university_messages`
`id`, `university_id` (FK RESTRICT), `contact_id` (FK SET NULL, nullable), `sender_user_id` (FK RESTRICT), `channel`, `template_id`
(FK RESTRICT, nullable), `template_name`, `subject`, `body`, `delivery_status`, `attempt_count`, `sent_at`, `created_at`, `updated_at`.
Checks: channel; `(channel='email') = (delivery_status IS NOT NULL) AND (channel='email') = (subject IS NOT NULL)`; the status list.
Indexes `(university_id, sent_at)`, `(contact_id, sent_at)`, `(sender_user_id, sent_at)`.

The upgrade is guarded (0110's idiom). The downgrade refuses while any call or message exists.

## 3. API (§12BH)

| Method | Path | Notes |
|---|---|---|
| GET | `/partnership/templates` | `channel?`, `active?`, `q?`, paged. Readers (UC3 roles). Managers see active rows only. |
| POST | `/partnership/templates` | Head or `super_admin`. UC4/UC5 checks; a duplicate name → 409. |
| PATCH | `/partnership/templates/{id}` | Merged row re-checked; the channel is fixed (422); `active` toggles. |
| GET | `/partnership/templates/{id}/preview` | Sample values: Priya Sharma, University of Example and the caller's name. |
| GET | `/partnership/messages/render?template_id=&contact_id=` | Contact readable (404), then an active template (404). `{template, subject, body, missing}`. |
| POST | `/partnership/messages` | `contact_id`, `channel`, `template_id?`, `subject` (email), `body`. 201 with the message. Not idempotent. |
| GET | `/partnership/universities/{id}/messages` | Newest first, paged. |
| POST | `/partnership/calls` | `contact_id`, `occurred_at?`, `duration_seconds?`, `direction`, `outcome`, `notes?`, `next_follow_up_on?`. 201 with the call. Not idempotent. |
| GET | `/partnership/universities/{id}/calls` | Newest first, paged. |

Error order on a write: role (403) → the contact exists (404) → lock the university → `can_edit_contacts` (403) / inactive (409) →
(email) SMTP unset (503) → no number / address (409) → template (422) → validation (422) → cap (409 / 429) → insert, audit, commit,
enqueue (email), log.

Additive output: `whatsapp_to` and `last_interaction_at` on `UniversityContactOut`.

## 4. Worker

`notifications/university_email.py` (`deliver_university_email`, `sweep_stale_university_emails`) copies rec-026's
`recruiter_email.py` on the new table and reuses `lead_email._send` and ENH-014's constants. `dispatch.enqueue_university_email`;
`worker.py` adds the two tasks and a 5-minute beat entry. tel-014 and rec-026 code is unchanged.

## 5. Web

- **`lib/partnershipComms.ts`:** types, URLs, placeholders, the composer target (`ComposerTarget`) for a contact, the templates library
  config.
- **University page:** for UC3 readers, a **Calls** section (`UniversityCalls`, with `UniversityCallForm`: contact, outcome, time,
  direction, duration, notes, next follow-up date; a `tel:` link for the chosen contact) and a **Messages** section (`UniversityMessages`:
  contact picker, Send WhatsApp / Send email reusing `WhatsAppComposer` / `EmailComposer`, pending emails polled every 5 s). Write
  controls only with `can_edit_contacts`. Loading, empty and error (Retry) states. Each change refreshes the page so the contacts'
  "Last interaction" updates.
- **Contacts:** `UniversityContacts` shows "Last interaction".
- **Templates admin:** `/partnership/head/templates` renders the rec-026 templates panel with a `library` prop (URL, kinds = none,
  placeholder hint, sample note). "Message templates" is added to `PARTNERSHIP_HEAD_NAV`.

## 6. Tests

- **pytest `test_upc_012_comms.py`:** template role matrix; unknown placeholder → 422; duplicate name → 409; channel fixed; managers see
  active only; render; WhatsApp logged (AC2); email queued and published after the commit (AC1); a contact with no email → 409; no number
  → 409; SMTP unset → 503; a call (AC3) and last interaction (calls and messages; failed emails excluded); out-of-scope manager → 403;
  overseas_admin → 403; inactive university → 409; caps; audit carries no body; a deleted contact keeps the history.
- **pytest `test_upc_012_delivery.py`:** `deliver_university_email` gives `sent` / `retrying` / `failed`; the sweep.
- **pytest `test_upc_012_migration.py`:** checks equal the models'; single head.
- **vitest:** the lib, `UniversityCalls`, `UniversityMessages`, the templates panel with the partnership library.
- **Playwright `upc-012-university-comms.spec.ts`:** the head creates a template; a manager logs a call (last interaction shows), sends a
  WhatsApp (confirm) and an email from the template (status shown).

## 7. Engineering review (Phase 3)

- **API:** no client-supplied university id on a write — the university is read from the contact (no IDOR). Lists are the only paged
  endpoints. `POST` returns 201 and is documented as not idempotent (the daily caps bound retries). Template PATCH re-checks the merged
  row. Additive output fields only; upc-006's contact contract is unchanged otherwise.
- **Transactions / races:** every write locks the university row (`FOR UPDATE`) and then reads the contact, exactly as upc-006's
  edit/delete do, so a concurrent contact delete is a clean 404 and an inactive university is seen consistently. The per-sender cap is
  counted under that lock; two parallel sends to *different* universities may exceed a cap by one (an abuse bound, accepted as rec-026).
  The email is published only after the commit; the worker claims rows atomically, so a duplicate task never sends twice.
- **Security:** bodies are rendered as React text (no HTML); the mailer escapes the HTML part; the subject is one line (header-injection
  guard, `_one_line` + the mailer's own check); `wa.me` text is `encodeURIComponent`-ed. Audit/logs carry no text, number or address.
  Role checks precede body parsing on template writes. Cookie auth and CSRF follow the existing app (same as rec-026). No new secrets.
- **Frontend:** reuse `WhatsAppComposer`/`EmailComposer` (focus management, confirm step, double-submit guards), the templates panel and
  the existing `action-card`/`form-grid` styles. Each section has loading, empty and error-with-Retry states; buttons disabled with a
  stated reason when the contact has no number/address; form errors placed on fields; the form grid wraps on phones.

## 8. Risks

- The templates panel gains a `library` prop; rec-026's panel tests are rerun.
- `UniversityContactOut` gains fields; upc-006 tests are rerun.
- Route-inventory and RBAC tests need rows for the new routes.
- Parallel sessions race for 0125 / DEC-SCOPE-140 / §12BH / §2.66; renumber in Phase 9 if main moved.
