# pob-003 — Company business context, last contact and a document store (design)

- **Source:** `docs/delivery/PLACEMENT_OFFICER_BD_CRM_BACKLOG.md` pob-003 (§3.1 "Business context: products/services, departments hiring,
  likely skill demand, hiring locations and target roles"; "Relationship details: … last contact and next action"; "Documents: company
  profile, vendor onboarding form, recruitment agreement, job descriptions and meeting notes"; "branch locations"). Source classified
  `UNVERIFIED`; Q-00 (owner, 2026-11-01) approved the backlog for build in waves. The owner assigned pob-003 on 2026-11-05 and said to
  proceed with recommended answers, so D1–D9 are **the builder's calls (`NEEDS_CONFIRMATION`)**. Dependency **pob-001** is merged
  (`DEC-SCOPE-403`, PR #471). Decision `DEC-SCOPE-406`.

## Intent
A Placement Officer researching a company needs, on the company record: where it has branches, what it sells and hires for (departments,
skills from the Skills Master, locations, roles), when anyone last contacted it (sortable, so stale accounts surface), and one place for the
company's files (profile, vendor form, agreement, JDs, meeting notes) with an audit trail.

**Non-goals:** BD statuses / relationship stage (pob-004); contact status/decision-maker (pob-005); import/merge (pob-006); vendors (pob-010);
document deletion or versioning; DOCX uploads (D7).
**Anti-goals:** an agreement downloadable without `commercials.client.view`; an upgrade that loses or rewrites existing `branches` text;
"last contact" drifting from the activity it summarises.

## Rules (builder's calls)

**D1 — Branch locations.** New table `company_branches` (company, position, city required, state, country; ≤ 50 per company). Written as a
whole set through `PATCH /recruiter/companies/{id}` `branch_locations: [{city, state, country}]` (omitted = unchanged, `[]` clears).
The legacy free-text `branches` column, its API field and validation stay as they are (relabelled "Branch notes" on screen); nothing is
parsed or migrated out of it.

**D2 — Business-context columns** on `companies`: `products_services` (≤ 2000, multi-line) and three JSON string lists
`departments_hiring`, `hiring_locations`, `target_roles` (≤ 20 items of ≤ 120 chars each; trimmed, blanks dropped, case-insensitive
duplicates dropped, same control-character rules as the other company text). Lists are replaced whole.

**D3 — Likely skill demand.** Table `company_skill_demand` (company, skill, position; PK company+skill; ≤ 30). PATCH `skill_demand_ids`
replaces the set; a newly added skill must exist and be active (422 "Choose an active skill"), a kept since-deactivated one is allowed (the
rec-003 catalogue rule). Output `skill_demand: [{id, name, active}]` in the saved order.

**D4 — Last contact.** `companies.last_contacted_at` (nullable, indexed). It is the latest of the company's contact calls
(`occurred_at`), messages to its contacts (`sent_at`, any channel/delivery state — an outreach attempt) and completed meetings
(`starts_at`). It is **recomputed from those rows** (not max-ed incrementally, because a call can be edited or deleted) by
`recruiter_companies.refresh_last_contact` in the same transaction as every write that changes them: call create/update/delete, message
send, interview-invite email to a contact (hrc-028), profile-share message (rec-019), meeting outcome. The refresh locks the company row
first and then runs the UPDATE as a new statement, so concurrent writers converge. It never bumps `updated_at`. The migration backfills it.
"Next action" on screen is the existing derived next follow-up (rec-024 FU9).

**D5 — Sorting.** `GET /recruiter/companies?sort=name|last_contacted` (default `name`, unchanged). `last_contacted` = most recent first,
never-contacted last, then name. Rows gain `last_contacted_at`.

**D6 — Document store.** Table `company_documents` (company, kind, display name, content type, size, server-generated storage key never
returned, optional meeting, uploader, created_at). Kinds: `company_profile`, `vendor_onboarding_form`, `recruitment_agreement`,
`job_description`, `meeting_notes`. Append-only (no delete/replace in this item). ≤ 200 per company (409).
- `GET /recruiter/companies/{id}/documents?kind=&meeting_id=&limit=&offset=` — company read scope (404); newest first; `{items, total, limit,
  offset, can_upload, can_upload_agreement}`; each item has `can_download`.
- `POST /recruiter/companies/{id}/documents` multipart `kind`, `file`, optional `meeting_id` — `can_edit` on the company (403; archived 409);
  meeting must belong to this company (422); bytes via `agent_documents.read_upload` (PDF/JPEG/PNG by content, metadata stripped,
  global size cap → 413/415/422); 20 uploads per user per rolling hour (429 + Retry-After); a stored object is deleted if the commit fails.
- `GET /recruiter/companies/documents/{document_id}/download` — company read scope (404 as unknown); audit row committed before bytes leave;
  `Content-Disposition: attachment` with a server-built name; `no-store`, `nosniff`, sandbox CSP (the contract-document headers).
- Audit `recruiter_company_document.uploaded|downloaded` (ids, kind, content type, bytes — never file name or key). Logs likewise.

**D7 — Upload types.** PDF, JPEG, PNG only — the same reader the contract/MoU documents use. DOCX/meeting-note text files would need a new
sniffing path; deferred (`NEEDS_CONFIRMATION`).

**D8 — Agreements follow pob-001.** `recruitment_agreement`: listing shows that it exists (name, date, uploader — not a term, pob-001 C5);
download needs `commercials.client.view` (403 "Your role cannot view or change client commercial terms"); upload needs effective
`commercials.client.edit` (403). Other kinds follow company scope/`can_edit` only.

**D9 — Size of oversize error.** The backlog's draft "oversized file returns 422" is answered with **413** (the reused reader's existing,
HTTP-correct status), not changed to fit the draft.

## Web
- Company detail: a **Business context** section (view; Edit for `can_edit`) with branch rows (add/remove), products/services, departments,
  hiring locations and target roles (comma-separated inputs), and skill demand (Skills Master search + removable chips). Details gain
  "Last contact" ("—" when none) and "Branches" becomes "Branch notes". A message send re-reads the company (calls, follow-ups and meetings
  already do), so Last contact updates in place.
- **Documents** section: list (kind, name, meeting, uploader, date, Download when allowed), kind filter, upload form (kind, optional meeting
  for any kind, file) shown with `can_upload`; agreement option only with `can_upload_agreement`; loading, empty, error states.
- Companies list: "Last contact" column and a Sort select (Name / Last contacted).

## Acceptance (testable)
1. Every §3.1 business-context field and branch locations can be saved and read back (create and PATCH); invalid input is 422.
2. `last_contacted_at` updates when a call is logged (and on message, completed meeting; recomputed on call edit/delete); a company with no
   activity shows "—"; the list sorts by it.
3. Each document kind can be uploaded and downloaded, each with an audit row; oversize is 413, wrong type 415.
4. Agreement download/upload follow `commercials.client` grants; out-of-scope company/document is 404; non-owner write 403; archived 409.
5. Existing rec-003 behaviour (legacy `branches`, default sort, payload fields) is unchanged.

## Regression risks
rec-003 tests (payload shape: additive fields only), rec-025/026/028 and hrc-028/rec-019 write paths (one extra UPDATE in their
transaction), rec-038 route matrix (new routes need rows), migration model-match tests, web fixtures for `Company`.

## Numbering
Migration `0283_company_business_context` (siblings hold 0280/0281), `DEC-SCOPE-406`, API §12KZ, RBAC §2.299 — re-checked at merge.
