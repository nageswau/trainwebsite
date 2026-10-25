# ccrm-020 — Document requests for direct students (design)

Feature: `ccrm-020` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`), supersedes `nehn-037` part 1. Decision `DEC-SCOPE-265`, migration
`0187_student_document_requests`, API §12FR, RBAC §2.179. Branch `feature/ccrm-020` (worktree `worktree-ccrm-020`), cut from main
@475269c6.

## 1. Requirement (backlog, UNVERIFIED source — counselor CRM spec PDF §11, nehn-037 #1)

The counselor requests a document type (due date, note) from a direct student, optionally tied to an application / checklist item; the
student is notified, sees it, uploads against it; the counselor accepts or rejects; a cancel is possible. Overdue requests feed ccrm-030.
Acceptance (nehn-037): counselor requests "IELTS scorecard"; student sees the due date, uploads; counselor accepts; it clears from missing
documents. Regression: AGN-009 agency requests unchanged.

## 2. Discovery (graphify + code, main @475269c6)

- `DocumentRequest` (`models.py`, AGN-009) requires `agent_student_id`; statuses `open | fulfilled | cancelled`; a document fulfils at most
  one request (`uq_student_documents_fulfils_request_id`). Agency routes `api/agent_documents.py`, service `services/agent_documents.py`
  (`request_scope` = agency students, `close_request`, `add_event`, `read_upload` (magic bytes), `store` / `discard`).
- Direct students upload today through `POST /workflows/overseas/documents` with a client-supplied `file_url` (OVS-005).
- Counselor review: `PATCH /workflows/overseas/documents/{id}/verify` (counselor/admin path + AGN-003 agent path), statuses from ccrm-021
  (`incomplete`, `reupload_required` are the "rejections"; legacy `rejected` / `changes_required` map to them).
- Counselor scope: `student_profiles.staff_student` (csc-001 visible students or Overseas Admin; else 404). Application writes:
  `application_offers._writable` (scope, row lock, closed / archived refusals).
- ccrm-019 checklist: `services/application_checklists` (`set_mark`, `link` clears the mark, `sync_completion`). Item status "Requested"
  comes from the counselor mark.
- UI: counselor student 360 Documents tab (`OverseasStudent360Page.tsx`), checklist rows (`ApplicationChecklistPanel.tsx`), student
  Documents section (`WorkflowPanel.tsx` `DocumentUpload` / `DocumentDownloadPanel`).
- Dependency `nehn-003` (private storage) is **not built**; owner chose to proceed (2026-10-25). The new student upload is server-side
  multipart with byte sniffing and a server-generated key (AGN-009 `read_upload`/`store`), so it adds no new client-named path.

Classification: MUST CHANGE — `models.py` (DocumentRequest), new migration, new service + router, `workflows.py` verify paths (reopen),
student 360 Documents tab, checklist row, student Documents section. MAY CHANGE — `schemas.py`, `main.py` router list, docs.
SHOULD NOT CHANGE — agency request routes and scope, OVS-005 upload route, ccrm-021 statuses. HIGH REGRESSION RISK — agency request list
(`requests_stmt` inner-joins `AgentStudent`; NULL `agent_student_id` must never leak), document review paths.

## 3. Decisions

Owner (2026-10-25):
- **R1** a rejection (`incomplete` / `reupload_required`, incl. legacy inputs) of a document that fulfils a direct-student request
  reopens the request: status back to `open`, the rejected document keeps its file and history but no longer fulfils it, so the student
  uploads again against the same request. Verified leaves it fulfilled.
- **R2** a request made from a checklist item marks the item `requested` (when the item allows it); the student's upload is attached to
  that application and auto-linked to the item (the link clears the mark → Pending review); verifying makes it Verified so it leaves
  "missing". Cancelling clears a still-`requested` mark.

Defaults (`NEEDS_CONFIRMATION`):
- **R3** counselor (overseas, csc-001 scope) and Overseas Admin create / cancel; any of them in scope may cancel, not only the requester.
- **R4** `due_date` required, today (IST) or later; note optional ≤1000; type from the AGN-009 request list (no Offer letter), "Other"
  needs a label (2-80). A checklist-item request takes the item's type and label.
- **R5** one open request per student + application + type + label (409), the AGN-009 rule widened by application.
- **R6** notifications: student in-app + opted-in channels on create and cancel ("Document requested: {type}, due {date}"), never the
  note in the channel text; the requester (in-app + channels) when the student uploads. The review notice already covers reject/accept.
- **R7** the student uploads with the AGN-009 byte rules (PDF/JPEG/PNG, global size limit, metadata stripped), optional expiry date.
- **R8** `overdue` = open and due date before today (IST), computed in every list; a partial index on open due dates serves ccrm-030.
- **R9** the request needs a student login (`student_user_id`); agency-only records keep AGN-009.

## 4. Data (migration 0187)

`document_requests`: `agent_student_id` → nullable; new `student_user_id` (FK users), `application_id` (FK overseas_applications),
`checklist_item_id` (FK application_checklist_items, ON DELETE SET NULL), `due_date` (date). CHECK `ck_document_requests_owner`:
exactly one of `agent_student_id` / `student_user_id`. Indexes `ix_document_requests_student_user_status (student_user_id, status)`,
partial `ix_document_requests_open_due (due_date) WHERE status = 'open' AND due_date IS NOT NULL`. Each step only when missing (0001
builds from models). Downgrade (lossy): delete direct-student requests (their events, unlink documents), restore NOT NULL. No new
event code: a reopen is a `requested` event `fulfilled → open` with the review note.

## 5. API (§12FR)

| Route | Who | Notes |
|---|---|---|
| `GET /counselor/students/{id}/document-requests?status=open\|all&limit&offset` | counselor in scope, Overseas Admin | newest first, `overdue`, fulfilling document + its status |
| `POST /counselor/students/{id}/document-requests` | same | body `document_type?`, `document_label?`, `due_date`, `note?`, `application_id?`, `checklist_item_id?` → 201 `{request}` |
| `POST /counselor/students/{id}/document-requests/{rid}/cancel` | same | 409 when not open |
| `GET /overseas/me/document-requests?status=open\|all` | overseas student (own) | no requester-internal fields beyond name |
| `POST /overseas/me/document-requests/{rid}/upload` (multipart `file`, `expiry_date?`) | overseas student (own, open) | 201 `{request, document_id}` |

Errors: other student / role → 404 / 403 (staff_student, require_student); application not the student's → 422; checklist item not on
the application → 404; closed application → 409 (`_writable`); duplicate → 409; closed request → 409. Writes lock the request row (and
the application when tied) and commit once with the audit row (`document_request.create` / `.cancel`, `document.upload`).

## 6. UI

- Counselor student 360 → Documents tab: "Document requests" panel (list with due date, overdue badge, status, uploaded document status,
  Cancel) and a "Request a document" form (type, name for Other, due date, application (optional), note).
- Checklist row (counselor, not read-only, item not complete): "Request from student" → due date + note → creates a tied request.
- Student Documents section: "Requested documents" panel — open requests (type, due date, overdue, counselor note, upload form) and the
  last closed ones; loading / empty / error states, one submit at a time.

## 7. Tests

Backend `tests/test_ccrm_020_requests.py` (create/list/cancel/upload/reopen/checklist tie/scope/agency regression) and
`tests/test_ccrm_020_migration.py`; vitest for the two panels; Playwright `ccrm-020-document-requests.spec.ts` (request → student
uploads → counselor verifies → checklist Verified). Lite regression: `test_agn_009_requests.py`, `test_agn_009_migration.py`,
`test_ccrm_019_*`, `test_ccrm_021_*`.

## 8. Browser QA (2026-10-25, stack `ccrm020`, demo counselor / student)

- QA-01 (medium, fixed): a reopened request did not say why — lists now carry `review_note` (the rejection note), shown to the counselor
  ("Reopened after review: …") and the student ("Please upload a new file: …").
- QA-02 (low, fixed): the staff list put a newer cancelled request above an older open one — open first by due date, then newest.
- QA-03 (low, fixed): more than 20 requests gave no hint — "Showing the latest N of M requests."
- Not changed: "Clear mark" on a requested checklist item leaves the open request (cancel it on the student 360); the generic `main`
  conflict-marker lines left by the ccrm-024 merge in four docs were removed while appending this feature's entries.

## 9. Plan

1. Migration + model (RED migration test → GREEN).
2. Service `services/student_document_requests.py` + schemas + routes (counselor router in `api/counselor_students.py`, student router
   on `student_profiles.me_router` prefix) — TDD per behaviour.
3. Reopen hook in both verify paths.
4. Web: `lib/documentRequests.ts`, `CounselorDocumentRequestsPanel`, `StudentDocumentRequestsPanel`, checklist row action — vitest.
5. Docs: decision register, API contract, RBAC, data model, RTM, backlog status.
6. Browser QA + e2e.
