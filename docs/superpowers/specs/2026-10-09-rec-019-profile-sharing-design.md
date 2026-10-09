# rec-019 — Profile sharing (Email / WhatsApp / Portal / Other) + response tracking (design)

- **Feature:** rec-019 (`docs/delivery/RECRUITER_CRM_BACKLOG.md`). Source: EVID-018 §11 (lines 500–530), R8, R13.
- **Decision:** `DEC-SCOPE-159` (S1–S14 below are **recommended defaults, UNVERIFIED**; the owner said "proceed with recommended answers"
  and had not answered Q-19). Migration `0141_profile_shares`, API §12CA, RBAC §2.85.
- **Dependencies (all merged):** rec-004 (PR #160), rec-017 (PR #178), rec-026 (PR #176).

## 1. Decisions (Q-19 and item-level; UNVERIFIED)

| # | Decision |
|---|---|
| S1 | **One share = one requirement, one company, one channel, 1–20 candidates.** Started from the requirement's Candidates board, its Matching section, or Find Candidates (which first asks for the requirement). |
| S2 | **Channels.** *Email*: to one active contact of the requirement's company with an email; SMTP must be configured (503); one `recruiter_messages` email row, queued and delivered by the rec-026 worker. *WhatsApp*: to one active contact with a mobile; one `recruiter_messages` WhatsApp row; the response carries the `wa.me` URL. The row is written when the recruiter confirms the dialog ("Record and open WhatsApp"), because the resume links only exist once the share does. *Portal*: shown to every employer-portal user of the company (409 when the company has none); a contact is optional. *Other*: log only; a contact is optional. The rec-026 daily caps (300 WhatsApp / 100 email per sender) apply. |
| S3 | **The contact** must be an active contact of the requirement's company (another company's contact → 422; an inactive contact → 409). |
| S4 | **Candidates** must be active pool members (rec-009 `pool_filter`, not archived), else 422 naming them. A candidate not yet on the requirement is added at **Profile Shared** (rec-017 `create`, with history). One already on it moves to Profile Shared from Sourced, Screened or Shortlisted; at Profile Shared or a later open stage (Interview, Selected) it stays where it is. A Rejected, Withdrawn or Joined application is refused (422 naming them). |
| S5 | **Repeat share.** A candidate already shared for the same requirement (any channel) → 409 `{message, duplicates: [{id, name, code}]}` unless the request sets `repeat: true`; the dialog lists them and offers "Share again". |
| S6 | **What is shared** (R8, server-side): code, name, qualification, college, passing year, experience, current company, location, preferred locations, preferred role, notice period and skill names (up to 10). **Never** phone, email, LinkedIn or salary (rec-018 SC8: salary never leaves the recruiter module). |
| S7 | **Resume link (Q-19a).** Each item of an Email or WhatsApp share gets an opaque random token (`secrets.token_urlsafe(32)`, only its SHA-256 stored) valid for **7 days** (the tel-012 C1 period). It serves the resume version that was current at share time. A candidate with no resume gets no link ("Resume on request"). `GET /public/shared-resume/{token}` needs no session. Every failure (unknown, expired, archived candidate, unreadable file) is the same 404. Every download writes an audit row (`profile_share.resume_download`, item id only). |
| S8 | **Portal visibility (Q-19b).** Every employer user of the company sees the company's **Portal-channel** shares only (an email or WhatsApp went to a person, not the portal). The portal downloads the resume through an authenticated, audited route. |
| S9 | **Response (Q-19c): both.** The recruiter records a response and feedback on any item. An employer user records a response on a Portal item. Values: `pending` (default), `interested`, `not_interested`, `interview_requested`. `responded_by` and `responded_at` are kept; the last write wins. A response never moves the application (the recruiter schedules the interview, rec-020). |
| S10 | **Who.** Share and record a response or feedback: the requirement's writers (rec-007 `can_edit`, i.e. the recruiter in scope and `super_admin`), not on a closed or cancelled requirement (409). Read the share lists: the requirement's scope readers (manager, assigned BDM read). Other roles 403; out of scope 404. |
| S11 | **Company pipeline.** A share fires rec-005's reserved `profiles_shared` event (forward only). The requirement's own status stays manual. |
| S12 | **Note.** An optional note (≤ 500) on the share. It is shown to the recruiter side only and never sent. |
| S13 | **Shares are permanent** (no edit or delete). Revoking a link is out of scope; links expire. |
| S14 | **Lists.** "Shares" sections on the requirement page and the company page, newest first, 20 per page, each share with its items. The employer dashboard gets a "Shared with you" panel. |

## 2. Data model (migration `0141_profile_shares`, down `0140_joining_management`)

- `profile_shares`: `id`, `job_id` FK jobs, `company_id` FK companies, `contact_id` FK company_contacts NULL, `channel` CHECK
  (`email`,`whatsapp`,`portal`,`other`), `note` ≤ 500 NULL, `message_id` FK recruiter_messages NULL, `shared_by_user_id` FK users,
  `created_at`/`updated_at`. CHECKs: email/whatsapp ⇒ contact and message present; portal/other ⇒ no message. Indexes on
  (`job_id`, `created_at`) and (`company_id`, `created_at`).
- `profile_share_items`: `id`, `share_id` FK (CASCADE never needed: shares are never deleted), `candidate_id`, `application_id`,
  `resume_id` NULL, `token_hash` (char 64, unique, NULL), `token_expires_at` NULL, `response` CHECK default `pending`, `feedback` ≤ 1000 NULL,
  `responded_by_user_id` NULL, `responded_at` NULL, timestamps. UNIQUE(`share_id`, `candidate_id`); index (`candidate_id`).
  CHECK: the token hash and its expiry are both set or both NULL.

## 3. API

- `POST /api/v1/recruiter/shares` `{requirement_id, candidate_ids[1..20], channel, contact_id?, note?, repeat?}` → 201
  `{share, whatsapp_url?}`. Error order: role/scope (403/404), requirement lock, writer (403), ended (409), contact (422/409), channel
  preconditions (503 SMTP, 409 no email/mobile/portal users), candidates (422), repeat (409), cap (409/429).
- `GET /api/v1/recruiter/requirements/{id}/shares` and `GET /api/v1/recruiter/companies/{id}/shares` → page of shares with items.
- `PATCH /api/v1/recruiter/shares/{id}/items/{item_id}` `{response?, feedback?}` → the item.
- `GET /api/v1/employer/shared-profiles` → the company's portal items (summary only); `PATCH /api/v1/employer/shared-profiles/{item_id}`
  `{response}`; `GET /api/v1/employer/shared-profiles/{item_id}/resume`.
- `GET /api/v1/public/shared-resume/{token}`.

## 4. Backend

- `services/profile_sharing.py`: the rules, the summary (S6), the email and WhatsApp text, tokens, the lists and the outputs.
- `api/recruiter_shares.py` (recruiter routes plus the public router); `api/employer.py` gets the three employer routes.
- Reuse: rec-026 `recruiter_messages.load_party`-style contact checks and the caps (a small shared helper `check_cap`),
  `enqueue_recruiter_email` after the commit, rec-017 `applications.create` / `change_status`, rec-005 `company_pipeline.apply_event`, and
  `telecaller_content.download_headers`.

## 5. Web

- `lib/recruiterShares.ts`: types, guards, URLs, labels.
- `components/RecruiterShareDialog.tsx`: channel, contact, note, the repeat warning, the result (and the WhatsApp link).
- Multi-select: checkboxes on the Candidates board, the Matching rows and the Find Candidates cards, plus a "Share N selected" action.
- `components/RecruiterShares.tsx`: the Shares section (requirement and company pages), with the response and feedback form.
- `components/EmployerSharedProfilesPanel.tsx`: the "Shared with you" panel on the employer dashboard.

## 6. Tests

- **API (`test_rec_019_shares.py`, `test_rec_019_migration.py`):**
  - AC1: 3 candidates by email → 3 items and one email.
  - AC2: no phone or email in the email, the WhatsApp text or the portal view.
  - AC3: the link works, then expires; an unknown token is 404; downloads are audited.
  - AC4: applications move to Profile Shared.
  - Other cases: another company's contact 422, a non-opted-in student 422, repeat 409 and `repeat`, roles 403/404, an ended requirement 409, portal without users 409, SMTP off 503.
  - Employer: sees only own-company portal shares and responds; another company's item is 404.
- **Web:** vitest for the dialog, the Shares section and the employer panel. Playwright e2e for the share-by-email happy path, the portal response and mobile.
