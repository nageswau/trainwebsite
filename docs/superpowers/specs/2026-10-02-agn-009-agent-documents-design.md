# AGN-009 — Agent documents: upload, download, verify, reject, request additional, history (design)

- **Feature:** `AGN-009` = backlog `ang-009` (`docs/delivery/AGENT_CRM_BACKLOG.md` §ang-009).
- **Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 Documents, §4 Staff sidebar (Documents →
  Pending / Uploaded / Additional Documents), §5 Step 4 document types, §6 (Upload ✅/✅, Verify ✅/⚠️ Optional, Reject ✅/❌).
- **Decision:** `DEC-SCOPE-051` (provisional number; owner answers in-session 2026-10-02, recorded in
  `PRODUCT_DECISION_REGISTER.md`). Builds on `DEC-SCOPE-042` G4 (staff: assigned students only), `DEC-SCOPE-044` P1/P5/P6
  (Verify toggle; agents decide `pending` only; staff verify only), `DEC-SCOPE-050` (agency record ownership pattern).
- **Method:** graphify (graph refreshed 2026-10-02) then source reading; impact analysis in the session that cut this branch.

## 1. Acceptance criteria (owner statement) and how each is met

| AC | Met by |
|---|---|
| AC1 upload → pending | `POST /agent/crm/documents` stores the row `pending` (§4.2) |
| AC2 verify/reject per role matrix | existing agent review branch: Master verified/rejected/changes_required; Staff verified only and only with `can_verify_documents` (P1/P6, unchanged) |
| AC3 reject without a reason → 422 | agent branch: `rejected`/`changes_required` with blank notes → 422 (Q1: agents only) |
| AC4 a request shows under "Additional" until fulfilled | `document_requests.status='open'` listed by `GET /agent/crm/document-requests?status=open`; an upload with `request_id` fulfils it (Q5) |
| AC5 history lists every event in order | `document_events`, ordered by an identity `seq` |
| AC6 out-of-scope download → 404/403 | existing download route (403, unchanged code) now scope-checks NULL-`student_id` documents; new routes 404 |
| AC7 existing student/counselor flows unchanged | counselor/admin/student branches keep responses, codes and rules; they only gain additive event rows |

## 2. Owner answers (2026-10-02)

- **Q1** reason required on reject → **agents only**; counselor/admin path unchanged.
- **Q2** `changes_required` → **kept** for agents (Master only) and also needs a reason.
- **Q3** types → **fixed list + Other** for agent uploads only; other paths keep free text.
- **Q4** requests → **Master and Staff** create and cancel (no toggle).
- **Q5** fulfilment → **upload against the request** (explicit; a type mismatch is the uploader's choice).
- **Q6** replace → **new file on the same row**, status back to `pending`, old key kept in history.
- **Q7** file gaps → **agent path only**: server-generated keys, no `file_url` in agent lists; `/files/download` and
  `/local-files` recorded in RAID, not changed.
- **Q8** files → **PDF, JPEG, PNG**, decided from bytes.
- Assumptions accepted: "Uploaded" = every in-scope document; download events are written for every role.

## 3. Data model — migration `0058_agent_documents`

`student_documents` (additive; no existing row rewritten):
- `student_id` → nullable.
- `agent_student_id` UUID FK `agent_students.id`, nullable, indexed.
- `document_label` String(80) nullable (the "Other" label).
- `uploaded_by_user_id` UUID FK `users.id`, nullable (unknown for older rows).
- `fulfils_request_id` UUID FK `document_requests.id`, nullable, **unique** (one document fulfils a request — a DB-level race guard).
- CHECK `ck_student_documents_owner`: `student_id IS NOT NULL OR agent_student_id IS NOT NULL` (every existing row passes).
- An agent upload sets `agent_student_id`, plus `student_id` when the record has a login (AGN-008 pattern), so a linked student
  still sees it on their own Documents page and the visa checklist.

`document_requests` (new): `id`, `agent_student_id` (FK, not null), `document_type` String(80), `document_label` String(80)
null, `note` Text null, `status` String(20) CHECK `open|fulfilled|cancelled`, `requested_by_user_id` FK, `closed_by_user_id` FK
null, `closed_at` null, timestamps. Index (`agent_student_id`, `status`).

`document_events` (new): `id` UUID, `seq` BigInteger identity (ordering — events written in one transaction share `now()`),
`document_id` FK null, `request_id` FK null, CHECK at least one, `event` String(30) CHECK in
`uploaded|replaced|verified|rejected|changes_required|requested|fulfilled|cancelled|downloaded`, `actor_user_id` FK null,
`from_status`/`to_status` String(40) null, `notes` Text null, `file_key` String(500) null (old key on replace; never returned by
the API), `created_at`. Indexes on `document_id` and `request_id`.

Downgrade refuses while agency-only documents, requests or events exist (no silent data loss), else drops the new objects and
restores NOT NULL. Every add is guarded (0001 builds a fresh database from the models).

Document types (`DOCUMENT_TYPES`, stored as written, matching the existing free-text style the visa checklist compares):
`Passport`, `Academic certificates`, `Transcripts`, `English test`, `CV`, `SOP`, `LOR`, `Financial documents`, `Other`
(`Other` requires `document_label`, 2–80 chars; any other type refuses a label).

## 4. API

### 4.1 Scope — `services/agent_documents.document_scope(user)`

A document is in scope if its `agent_student_id` is one of the caller's scoped records, or its `student_id` is one of the
caller's visible linked students, or its `application_id` is one of the caller's scoped applications (`student_scope`,
`visible_student_user_ids`, `application_scope` — the three paths the AGN-003 review and download use today, in one place, safe
for NULL `student_id`). Staff therefore reach only their assigned students (G4). New routes return 404 outside scope; the
existing routes keep their 403.

### 4.2 New routes — `api/agent_documents.py`, prefix `/workflows/overseas/agent/crm`

All: `_gate` (active-agency agents; Masters and Staff; Super Admin refused). Pages are `{items,total,limit,offset}`,
`limit` 1–100 (default 20).

| Route | Behaviour | Errors |
|---|---|---|
| `GET /documents?view=pending\|uploaded&student=` | in-scope documents (pending: `verification_status='pending'`), newest first. Items carry no `file_url` | 404 unknown `student` |
| `POST /documents` multipart `agent_student_id, document_type, document_label?, application_id?, request_id?, file` | stores `pending`; with `request_id` the request → `fulfilled` | 404 student/application/request out of scope · 409 archived, request not open · 413 · 415 · 422 · 429 |
| `PUT /documents/{id}/file` multipart `file` | new key, status → `pending`, reviewer fields cleared, old key in the `replaced` event (old object kept) | 404 · 409 not an agency document / archived / decided by a counselor or Overseas Admin (P5) · 413/415/422/429 |
| `GET /documents/{id}/history` | the document's events, plus the fulfilled request's events, by `seq` | 404 |
| `GET /document-requests?status=open\|all&student=` | the "Additional" list | 404 unknown `student` |
| `POST /document-requests` JSON `agent_student_id, document_type, document_label?, note?` | `open` request | 404 · 409 archived / an open request of the same type+label exists · 422 · 429 |
| `POST /document-requests/{id}/cancel` | `open → cancelled` | 404 · 409 not open / archived |

### 4.3 Existing routes (response shapes unchanged)

- `PATCH /workflows/overseas/documents/{id}/verify`, agent branch (order): Verify permission → 403; body schema → 422; staff
  outcome other than `verified` → 403; `rejected`/`changes_required` with blank notes → **422**; scope (`document_scope`) →
  403; not `pending` → 409. Writes the event; notifies the student only when `student_id` is set. Counselor/admin branch: one
  additive event row; otherwise unchanged.
- `GET /workflows/overseas/documents/{id}/download`: agent branch uses `document_scope` (403 outside). Every role: a
  `downloaded` event and a `document.download` audit row are committed before the URL is returned.
- `POST /workflows/overseas/documents`: one additive `uploaded` event (and `uploaded_by_user_id`).
- `/portal/overseas/agent/documents` payload unchanged (the new page does not read it).

### 4.4 Transactions and concurrency

Lock order: organisation (`lock_active_org`) → agent student → request → document (`FOR UPDATE`). Storage then database
(ENH-025): validate bytes → `storage.write_bytes("agent-documents/<uuid4>")` → stage rows → one commit; a failed commit deletes
the new object. Results: two reviews → second 409 (kept); two uploads fulfilling one request → second 409 (lock + unique
`fulfils_request_id`); replace vs review → the later one sees the new state; duplicate open requests checked under the lock.

### 4.5 Security

| Concern | Control |
|---|---|
| AuthN | `get_current_user` (httpOnly, SameSite=Lax session cookie) |
| AuthZ / escalation | `_gate`; staff never reject/request changes; Verify toggle read per request |
| IDOR | scope in the WHERE clause on every id; linked `application_id`/`request_id` must belong to the same student and be in scope; tests for staff (other staff's student) and cross-agency |
| Client-supplied paths | none on the agent path (server key). RAID entry for `/files/download` and `/local-files` |
| Upload validation | bytes: `%PDF-`, JPEG, PNG; images through `strip_metadata`; empty 422, > `settings.max_upload_bytes` 413, else 415; filename = base name ≤ 255, display only |
| XSS | React text rendering only |
| CSRF | SameSite=Lax: not sent on cross-site POST/PUT/PATCH (incl. multipart) |
| Rate limiting | uploads+replaces 500 / agency / rolling 24 h; requests 200 / agency / rolling 24 h (changed during implementation from 60 / 10 min, to reuse the existing `THROTTLE_WINDOW` + `retry_after` rather than add a second window); counted from audit rows under the org lock (AGN-008 `retry_after`) → 429 `Retry-After` |
| Audit | `document.upload`, `document.replace`, `document.verify` (existing), `document.download`, `document_request.create`, `document_request.cancel` — ids/types/statuses only |
| Logs | ids only; no filenames, labels, notes or names |

## 5. Frontend

- **Nav:** Documents gains children Pending / Uploaded / Additional (`/overseas/agent/documents?view=…`), like Applications.
- **Page:** `PortalPage` routes `overseas/agent` + `documents` to `AgentDocumentsSection` (client), as AGN-008 does for
  Applications. `WorkflowPanel` stops rendering the generic upload form and the AGN-003 review queue for agents on that page
  (the new section replaces both); student and counselor rendering is unchanged.
- **Section:** intro (Master vs Staff wording) → `AgentDocumentUploadForm` (student picker = AGN-008's server search; type
  select; "Other" label; optional application and open-request selects narrowed to the student; file) and
  `AgentDocumentRequestForm` → the list for `?view=`: `AgentDocumentsPanel` (pending/uploaded) or `AgentDocumentRequestsPanel`
  (additional).
- **Document card:** student (+ "no login"), type/label, status as words (badge + text, never colour alone), application,
  uploader, date; actions: Download (existing route), Review (Master: three outcomes with a required reason for
  reject/changes; Staff with Verify: Verify only; hidden otherwise), Replace (agency documents not decided by a counselor/admin),
  History (inline region, ordered list).
- **States:** loading text with `aria-busy`; previous page dimmed while the next loads; empty text per view with a link to the
  other view; load error `role="alert"` + Retry; per-action busy labels; server `detail` messages; 409 reloads the list; success
  `role="status"`; focus returns to the triggering button (`useFocusAfterRender`).
- **Responsive / a11y:** existing `action-grid`, `card-stack`, `card`, `form-grid`, `badge`, `btn` classes; labelled inputs;
  buttons with accessible names naming the document; keyboard only.

## 6. Tests (lite sets run per task; the owner runs full regression)

- Backend new: `test_agn_009_migration.py`, `test_agn_009_upload.py`, `test_agn_009_review.py`, `test_agn_009_requests.py`,
  `test_agn_009_history.py`, `test_agn_009_scope.py` (IDOR/staff/cross-agency/download), `test_agn_009_concurrency.py`.
- Backend regression lite set: `test_ovs_005_documents.py`, `test_agn_003_verify.py`, `test_agn_003_matrix.py`,
  `test_visa_001_checklist.py`, `test_agn_008_null_owner.py`.
- Web: vitest for the new components and `navigation.agent.test.ts`, `WorkflowPanel.agentDocuments.test.tsx`; Playwright spec
  `agn-009-agent-documents.spec.ts` written, run by the owner with browser validation.

## 7. Out of scope

`/files/download` + `/local-files` hardening (RAID), offer/visa documents (AGN-010/012), deleting documents, notifications
for no-login students, backfilling history for documents made before 0058.
