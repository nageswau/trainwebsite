# tel-014 — Email to lead (SMTP) + send log (design)

- **Backlog:** `docs/delivery/TELECALLER_CRM_BACKLOG.md` § tel-014 (EVID-019 §12, L454–L472; T9). Dependencies tel-008 (PR #85), tel-012
  (PR #83) and tel-013 (PR #112) are merged. It writes to tel-013's `lead_messages`.
- **Decision:** `DEC-SCOPE-106` (EM1–EM4 owner answers 2026-10-07; E1–E10 defaults). Migration `0097_lead_message_email`, API contract
  §12Y, RBAC §2.31. The item was drafted as `0096` / `DEC-SCOPE-102` / §12W / 2.29. Four items merged first:
  - tel-018: `DEC-SCOPE-101` / §12V / 2.28, no migration.
  - bdm-012: `DEC-SCOPE-102`.
  - bdm-016: `0096_bdm_targets` / `DEC-SCOPE-103` / §12W / 2.29.
  - tel-021: `DEC-SCOPE-105` / §12X / 2.30, no migration.

  tel-025 holds `DEC-SCOPE-104`. So the item is renumbered to `0097` after `0096_bdm_targets`, and to `DEC-SCOPE-106`.

## 1. Decisions

| ID | Topic | Answer |
|---|---|---|
| EM1 (Q-16) | Sender identity | From `"<telecaller name> via EduSphere" <SMTP_FROM_EMAIL>` (the technical sender must be the verified SMTP account), Reply-To the telecaller's login email. Replies reach the telecaller's inbox and are not tracked |
| EM2 | Undo | An email row can never be deleted (it records a real system send, not a self-report): `can_delete` is false and `DELETE` → 409. WhatsApp keeps WA3 |
| EM3 | Daily cap | 100 emails per sender per IST day → **429** "You've sent 100 emails today". Every email row counts, failed included. The WhatsApp cap (300, 409) now counts WhatsApp rows only, so its behaviour is unchanged |
| EM4 | Template | Optional, as WA4. A template fills the subject and body, both editable; a free email is labelled "Custom message" |
| E1 | Who / which leads | As WA2: only the lead's telecaller, before handover (403), open lead (closed → 409). Read: the lead's scope |
| E2 | No address | The composer's action is disabled with a reason (AC3); the API refuses with 409 "This lead has no email address" |
| E3 | SMTP not configured | `SMTP_HOST` or `SMTP_FROM_EMAIL` unset → **503** "Email is not set up. Ask an administrator to configure SMTP." Nothing is stored |
| E4 | Asynchronous send | The request stores the row as `queued` and publishes `deliver_lead_email_task` after the commit; the request never waits on SMTP. A broker outage leaves the row queued for the sweeper |
| E5 | Delivery states | `queued` → `sending` → `sent` \| `retrying` \| `failed`. The atomic claim (`queued`/`retrying` → `sending`) lets exactly one worker send (ENH-014 pattern). A transient failure (connection, timeout, SMTP 4xx) retries after 60 s, 5 min and 25 min (4 attempts in all). A permanent failure (SMTP 5xx, a refused recipient, a malformed address, SMTP unset at send time, the lead's address removed) → `failed`. The sweeper republishes stale `queued`/`retrying` rows (30 min) and fails rows stuck in `sending` (15 min), never resending them |
| E6 | Content | Plain text plus an HTML alternative. In the HTML the subject, body and sender name are escaped, `http(s)` links become anchors (the brochure link), and newlines are kept. The subject's CR/LF become spaces on input (header injection). Subject 1–200 characters, body 1–5000 (tel-012's email limits) |
| E7 | Recipient | The lead's current `email`, read at send time |
| E8 | Template rules | Active email templates only (inactive, WhatsApp or unknown → 422 on `template_id`). Another product's template is a warning (D4) |
| E9 | Pipeline | No stage effect (D7). tel-015 shows the rows on the timeline; tel-021 counts them |
| E10 | Logs / audit | Logs and audit carry ids, the channel, the status and the error type, never an address, subject or body (WA1) |

## 2. Data — migration `0097_lead_message_email`

- `lead_messages.attempt_count` int NOT NULL, default 0.
- Check `ck_lead_messages_email`:
  `channel <> 'email' OR (subject IS NOT NULL AND delivery_status IS NOT NULL AND delivery_status IN ('queued', 'sending', 'retrying', 'sent', 'failed'))`.
- Guarded like 0095: 0001 builds a fresh database from the current models, so the upgrade skips when the column already exists.
- Existing rows are WhatsApp, so the default 0 is correct and the new check holds.
- `models.LEAD_MESSAGE_CHECKS` stays the 0095 set. The new check is `LEAD_MESSAGE_EMAIL_CHECK`, repeated by 0097, and a test asserts the two
  are identical.

## 3. API (§12Y)

| Route | Change |
|---|---|
| `POST /telecaller/leads/{id}/messages` | Body is a union on `channel`. WhatsApp is unchanged. Email: `{channel: "email", template_id?, subject, body}`. Order: scope 404 → lead lock → telecaller 403 → handover 403 → closed 409 → SMTP 503 → no address 409 → template 422 → cap 429 → insert `queued` → audit → commit → publish. 201 is the item with `delivery_status: "queued"` |
| `GET /telecaller/leads/{id}/messages` | Items gain `delivery_status` (null for WhatsApp), an additive field. `can_delete` is false for email |
| `DELETE /telecaller/messages/{id}` | Email → 409 "A sent email can't be deleted" (after scope, sender and handover) |
| `GET /telecaller/leads/{id}/render` | Unchanged (it already renders email subject and body) |

## 4. Backend units

- `schemas.LeadWhatsAppCreate` / `LeadEmailCreate`; `LeadMessageCreate` is the discriminated union.
- `services/lead_messages.create` gains the email branch and the per-channel caps. `can_delete` checks the channel. `load_for_delete` gains
  the email 409. `out` gains `delivery_status`.
- `services/mailer.lead_email_message(...) -> EmailMessage`: a pure builder (EM1 headers via `formataddr`, E6 escaping).
- `notifications/lead_email.py`: `deliver_lead_email(message_id)` (claim, snapshot, send through `mailer._send_sync` in a thread,
  classify, record, re-enqueue) and `sweep_stale_lead_emails()`.
- `notifications/dispatch.enqueue_lead_email(id, countdown)`: shares `enqueue`'s bounded wait and back-off. `_publish_lead_email` is
  replaced in tests by an autouse fixture.
- `worker.deliver_lead_email_task` and `sweep_stale_lead_emails_task`, with a 5-minute beat entry.

## 5. Web

- `lib/telecallerMessages.ts`: `delivery_status` on the type; `EMAIL_BODY_MAX` 5000 and `SUBJECT_MAX` 200. `activeTemplates(channel)`
  generalises the WhatsApp picker loader. `messageTitle(message)` gives "WhatsApp sent – 13 Sept 2026 – 10:35 AM" (unchanged), or "Email
  sent / sending / will retry / failed – …".
- `EmailComposer`: template picker ("Custom message" default), subject input with a 200 limit, body textarea with a counter out of 5000,
  "Send email" (with a double-submit guard) and Cancel. It shows the product-mismatch warning, the render loading and failure states, and
  API errors (503 / 409 / 422 / 429) in place. A refusal keeps the text.
- `LeadMessages`: a "Send email" button sits beside "Send WhatsApp", disabled with "No email address on this lead." (AC3). It opens one
  composer at a time. An email row shows its subject and status, and failed is shown as an error line (AC2). While any row on the page is
  `queued` or `sending`, the list refreshes every 5 s. `retrying` doesn't poll, because its retries take minutes.
- `LeadDetailPanel`: an "Email" header button next to "WhatsApp" opens the email composer (`emailSignal`).

## 6. Reviews (phase 3)

- **API:** The union keeps the WhatsApp contract, and the response fields are additive. 503 and 429 have their usual meanings. One
  transaction holds the lead lock, the cap count and the insert, and the publish happens only after the commit. A lost publish is recovered
  by the sweeper, and a duplicate publish by the claim.
- **Security:**
  - Authorization reuses tel-013's gate: scope 404 (no IDOR), role 403 and handover 403.
  - Header injection: the subject's CR/LF are stripped on input, and display names go through `formataddr`.
  - HTML: all text is escaped before linkification, so a link can never inject markup. Linkification matches only `https?://` followed by
    non-space, non-`<`, non-quote characters, applied after escaping.
  - The recipient comes only from the lead, never from the request, so there is no open relay.
  - Abuse is bounded by the cap. Logs carry no PII, and the SMTP password is never logged.
  - CSRF uses the app's existing cookie and same-origin proxy; nothing new.
- **Frontend:** existing patterns (`action-card`, `field`, `form-error`, `role=status`/`alert`), focus moves to the picker on open and
  back to the button on close (QA-02/QA-04 precedents), and controls wrap on mobile.

## 7. Tests (TDD)

- **API (`test_tel_014_email.py`):**
  - Send happy path: the row is queued, the publish is captured, and there is an audit row with no text.
  - 503 when not configured (no row). No address → 409. Closed → 409. Manager → 403. Handed over → 403. Other telecaller → 404.
  - Templates: inactive, WhatsApp or unknown → 422.
  - Subject: CRLF stripped; empty or too long → 422. Body too long → 422.
  - Cap: email cap 429, and WhatsApp's cap ignores email rows.
  - Email delete → 409, and `can_delete` is false. The list carries `delivery_status`.
- **Worker (`test_tel_014_delivery.py`):**
  - The claim sends once, and a second deliver is a no-op.
  - Sent and failed outcomes, including a transient retry with its countdown and the last attempt failing.
  - Headers (From display name, Reply-To, To, Subject) and HTML escaping and linkify.
  - SMTP unset at send time → failed. Lead address removed → failed.
  - The sweeper republishes queued rows and fails `sending` rows.
- **Migration (`test_tel_014_migration.py`):** chain and head; the check and column round trip in a throwaway database.
- **Web (vitest):** `messageTitle`; `EmailComposer` (render fills subject and body, send posts, refusal keeps the text, double-click sends
  once); `LeadMessages` (disabled without an email, failed status shown).
- **Playwright `tel-014-email.spec.ts`:** pick a template, send, and the row appears and reaches "Email sent" (worker + Mailpit in the QA
  stack).

## 8. Implementation plan

1. Migration 0097, the model column and check, and the migration test.
2. Schemas union and the service email branch, with the API tests (RED → GREEN).
3. Mailer builder, `lead_email.py` worker, dispatch, worker task and beat, with the worker tests.
4. Web lib, `EmailComposer`, `LeadMessages`, `LeadDetailPanel`, with the vitest tests.
5. Playwright spec; QA in a `tel014` stack with Mailpit.
6. Docs: DEC-SCOPE-106, API §12Y, RBAC §2.31, backlog status, QA report.
