# ccrm-045 — Counselor uploads student documents (incl. offer letter) without an application — design

Source: `docs/delivery/COUNSELOR_CRM_BACKLOG_2.md` `ccrm-045` (owner request 2026-10-28, `MEETING_TRANSCRIPT_REQUEST`-equivalent).
The owner pre-authorised the backlog's recommended defaults for this session; every default below is the builder's call and stays
`NEEDS_CONFIRMATION` in `DEC-SCOPE-316`.

## Intent

"Documents can also be uploaded by the counsellor on behalf of student and they are visible to students. It also includes offer letter."
Today a counselor cannot upload for a walk-in student (the generic route needs an application they own) and an offer letter can only be
uploaded inside an application's evaluation panel. The student's "Offer Letters" page reads only the legacy `offer_letter_url`.

## Design

### Backend
1. **`POST /api/v1/counselor/students/{student_id}/documents`** (multipart) in `api/counselor_students.py`.
   Form fields: `document_type` (`AgentUploadDocumentType`: the checklist types + "Offer letter"), `document_label` (only for "Other",
   2-80 chars, `agent_documents.clean_label`), `application_id` (optional), `file`.
   Order of checks (no disclosure before the scope gate):
   - `student_profiles.staff_student` — overseas counselor with the student in caseload (`is_visible_student`) or the Overseas Admin;
     another role **403**, a student outside the caseload **404**.
   - archived student **409** (`student_archive.is_archived`, ccrm-040).
   - label rule **422**; "Offer letter" without an application **422** (same rule as AGN-010 O3).
   - application: missing or of another student **422**; a counselor naming another counselor's application **403** (the Admin any);
     a withdrawn / terminally decided application **409** (`outcomes.refuse_closed`, as the offer-letter upload).
   - `agent_documents.read_upload` (bytes sniffed: PDF/JPEG/PNG else **415**; > 20 MB **413**; EXIF stripped) → `store` (server key).
   - one transaction: `StudentDocument(student_id, application_id?, uploaded_by_user_id, verification_status="pending")`, `add_event
     ("uploaded")`, audit `document.upload` `{document_type, application_id}`; any failure → rollback + `discard(key)`.
   - **201** `{"document": {id, name, document_type, application_id, status}}`; `logger.info("counselor_document_uploaded")`.
2. **Download** (`GET /workflows/overseas/documents/{id}/download`): a counselor's document **without an application** follows the
   caseload (`is_visible_student`) instead of "has one of the student's applications" (a superset — nobody loses access). Application-bound
   documents keep `_assigned_application`. ccrm-022 sensitivity rule unchanged.
3. **360 documents** `can_download`: an unattached document is downloadable for the counselor (the tab's gate already proved caseload).
4. **Student portal "Offer Letters"**: an application also appears when it has a current "Offer letter" document; the "Offer letter"
   column shows the legacy URL or the document's name.

### Frontend
- `CounselorDocumentUpload` (new client component) on the 360 Documents tab, between the requests card and the list: type, name (Other),
  application (the reader's open applications — same list the requests form uses; required for Offer letter), file (`FILE_ACCEPT`).
  One upload at a time; success/error message; `router.refresh()` so the list shows the new row; form reset on success.
- `DocumentDownloadPanel` takes an optional `type` + `title`; the student's Offer Letters page shows it filtered to "Offer letter" so the
  letter can be downloaded there.

### Builder's calls (`NEEDS_CONFIRMATION`)
U1 Overseas Admin gets the same control. U2 agency applications of the student may be chosen (CC4). U3 no email/notification to the student
(the document is visible in Documents immediately). U4 no throttle (staff route; size cap only). U5 a new upload is pending and not
auto-linked to a checklist item (linking stays with ccrm-019's panel; a pending document never completes a checklist, so no sync is
needed). U6 no antivirus scan (platform-wide residual risk). U7 Offer letter requires an application.

### Non-goals
No migration, no visibility flag, no change to the generic `POST /overseas/documents`, the agency upload or the evaluation-panel upload.

## Acceptance → tests
| AC | Test |
| --- | --- |
| AC1 walk-in, no application → 201, student sees it | pytest upload + `/portal/overseas/student/documents`; e2e |
| AC2 offer letter against an application → student's Offer Letters | pytest portal section; e2e |
| AC3 non-PDF/image → 415, > 20 MB → 413 | pytest |
| AC4 other counselor's student → 404, other roles 403 | pytest + ccrm-041 matrix row |
| AC5 counselor downloads what they uploaded | pytest download (unattached + application) |
| AC6 history records the uploader | pytest `/history` actor |
| edge: archived 409, other student's application 422, other counselor's application 403, DB failure → file discarded | pytest |

## Plan
1. RED/GREEN backend upload route (tests file `tests/test_ccrm_045_counselor_upload.py`).
2. RED/GREEN download + 360 `can_download` change (update ccrm-009 expectation comment only if needed).
3. RED/GREEN portal Offer Letters.
4. Matrix row in `test_ccrm_041_matrix.py`.
5. Frontend: vitest for `CounselorDocumentUpload` and `DocumentDownloadPanel` filter; wire into the 360 page and WorkflowPanel.
6. Playwright e2e `ccrm-045-counselor-upload.spec.ts`.
7. Docs: DEC-SCOPE-316, API §12HN, RBAC §2.224, backlog status line.
