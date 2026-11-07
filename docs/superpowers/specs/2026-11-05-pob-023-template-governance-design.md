# pob-023 — Template library governance and the composer everywhere (design)

**Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` `pob-023` (§14 categories, §14.1 features, §14.2 workflow; §12 interview
confirmation template; §18 AC). The source DOCX is classified `UNVERIFIED` and is not in the repo, so the full §14.1 placeholder list is
not inspectable. The owner assigned pob-023 on 2026-11-05 and said to proceed with the recommended answers. G1–G12 below are therefore
**the builder's calls (`NEEDS_CONFIRMATION`)**. Dependency pob-001 (`DEC-SCOPE-403`) is merged. Decision `DEC-SCOPE-408`.

## Intent
Recruiters and Placement Officers work from one governed library: they add and edit templates, a Team Lead approves them, and everyone
reuses them from every screen where they contact someone. The work also covers LinkedIn and calling, which have no send API, so they get
a logged copy-to-clipboard mode.

## Today (rec-026, DEC-SCOPE-135)
- `recruiter_message_templates`: WhatsApp/email, 12 kinds, `{name}` `{company}` `{recruiter}`, an `active` flag. Only the manager
  writes.
- Render with real data, a missing-placeholder note, and a `recruiter_messages` log per send.
- The composer is on the company and candidate pages only. `RecruiterTemplatesPanel`, `WhatsAppComposer`, `EmailComposer` and
  `MessagesSection` are shared with upc-012 / ccrm (**high regression risk**: those libraries must not change).

## Builder's calls
- **G1 Channels:** `whatsapp`, `email`, `linkedin`, `call` (calling script). SMS is not built: there is no SMS integration (optional in
  the source). The existing kinds stay for WhatsApp and email. LinkedIn and call have no kind (`kind` is null); the `purpose` text says
  what they are for.
- **G2 Categories (§14):** `company`, `linkedin`, `whatsapp`, `calling`, `college_tpo`, `candidate`. Required on create. Existing rows are
  backfilled from their kind: WhatsApp → `whatsapp`; email interview confirmation, offer follow-up and joining confirmation → `candidate`;
  other email → `company`.
- **G3 Metadata:** `purpose` (≤ 200), `language` (≤ 40, default "English"), `department`, `industry`, `role_type` (≤ 80 each). All are
  optional except language.
- **G4 Status:** `draft` → `approved` → `archived`, stored in `status`; `active` becomes "status is approved". The column is replaced, but
  the API field and the `active` PATCH/filter stay: true = approve, false = archive. Restore takes an archived template back to `draft`.
- **G5 Visibility:** `owner_user_id` null = **shared**, set = **personal**. It is fixed at create.
  - Personal templates are seen, edited and used only by their author: never by a manager or super_admin, and never approved.
  - A shared template created by a manager or super_admin is approved at once (the approver is creating it).
  - A shared template created by a recruiter starts as a draft. Only the author and the managers see it until it is approved.
- **G6 Who does what:**
  - Readers and writers are `placement_team`, `placement_manager` and `super_admin`. rec-026 allowed only managers to write; the source
    §18 says users add and edit templates.
  - Approve: manager or super_admin, shared drafts only.
  - Edit: the manager edits any shared template that is not archived. The author edits their own shared draft or their own personal
    template.
  - Archive and restore: the manager for shared templates, the author for their own personal template or their own shared draft.
  - An archived template cannot be edited (409).
  - A template the caller cannot see is 404.
- **G7 Versions:** `recruiter_template_versions` gets one row at create (v1) and one per content change. Content means the name,
  subject, body, steps, kind, category or metadata. A status change is not a version. The template carries `version`,
  `created_by_user_id`, `updated_by_user_id` and `last_used_at`. Legacy rows have v1 written by the migration, with a null author.
- **G8 Placeholders:** a fixed allow-list in the existing `{snake_case}` syntax, one pass, no field access:
  - `name`, `company`, `recruiter`, `designation` (the contact's)
  - `job_title`, `job_location`, `package_range`
  - `candidate`, `interview_date`, `interview_time`, `interview_mode`, `interview_link`

  Values come from the party plus an optional context: `job_id` or `interview_id` on render. The source's `{{PackageRange}}` is
  `{package_range}`. It needs `commercials.client.view` (pob-001's only client-compensation grant) and renders empty without it.
- **G9 Context scope:** `job_id` goes through the requirement scope (404). For a contact, the job must be at the contact's company (404).
  `interview_id` goes through the application scope (404). It must be the candidate's own interview, or one at the contact's company.
- **G10 Copy mode:** LinkedIn and call templates are not sent. `POST /recruiter/messages/copies` records a copy and needs write on the
  party: the same lock, scope, inactive and (pob-005 D6) Do Not Contact rules as a send. It writes an audit row `recruiter_template.copy` (ids only, never the text)
  and bumps `last_used_at`. Copies are not messages, so they never change last-contacted or the caps.
- **G11 Human review:** the composer renders the text into an editable preview first. Send, Open WhatsApp and Copy exist only once a
  preview is shown; the existing composers already work this way, and the new copy composer follows. The server cannot check this.
- **G12 Composer everywhere:**
  - Company page: the contact picker, which covers the contact screen.
  - Candidate page.
  - Requirement page: contacts at its company, with `job_id` context. This also covers the submissions listed there. The section follows the company: hidden for a caller outside the company's scope (an assignee or backup owner), and writing needs the company's `can_edit`.
  - Interview item: the candidate, with `interview_id` context.
  - LinkedIn and calling buttons appear only in the recruiter sections; the shared `MessagesSection` gets an opt-in prop.

## API (additive)
- `GET /recruiter/templates`:
  - New filters `category`, `status`, `language`, `mine`, and `usable=true` (what the caller may use in a composer).
  - `channel` accepts the new channels. `q` also matches `purpose`.
  - New fields: `category`, metadata, `status`, `visibility`, `steps`, `version`, `created_by`, `updated_by`, `created_at`, `updated_at`,
    `last_used_at`, `can_edit`, `can_approve`, `can_archive`.
- `POST /recruiter/templates`: new fields, `visibility` ("shared" default / "personal"), and `steps` (a call needs 1–20 steps of ≤ 500
  characters; no other channel may have steps).
- `PATCH /recruiter/templates/{id}`: the G6 rules; channel and visibility are fixed.
- New routes:
  - `POST /recruiter/templates/{id}/approve | archive | restore`
  - `GET /recruiter/templates/{id}/versions`
- `GET /recruiter/messages/render`: adds `job_id` / `interview_id`, and `steps` in the response.
- `POST /recruiter/messages` (send): accepts approved shared templates plus the sender's own non-archived personal ones, and bumps
  `last_used_at`.

## Non-goals
- SMS.
- Merging with the UPC/overseas libraries (they stay separate and unchanged).
- Delivery tracking for LinkedIn.
- Automated sends (pob-022/027).
- Template deletion.

## Risks
- rec-026 tests: a recruiter's create is now 201 (draft), and the model's check constraints change.
- Shared composers: their default behaviour is unchanged, and the new props are opt-in.
- Migration data: `active` → `status` is lossless; the downgrade restores `active` from `status`.
