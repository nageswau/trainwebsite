# hrc-015 — Resume and document handling completion (design)

**Decision:** DEC-SCOPE-379 (builder's calls D1–D12 are `NEEDS_CONFIRMATION`; the owner said to proceed with the recommended answers).
**Source:** `docs/delivery/HR_RECRUITMENT_CRM_BACKLOG.md` `hrc-015` (PDF §5.1, §5 Documents, §11 Documents, §15; PDF classified
`UNVERIFIED`; scope approved by the owner 2026-11-01, backlog Q-00). Dependency hrc-001 (DEC-SCOPE-371) merged.
**Numbering:** migration `0255_candidate_documents`; API §12JX; RBAC §2.277 (siblings hrc-002/004/032 run in parallel and may take the
numbers in between; renumber at merge time if needed).

## Intent

Recruiters can already upload versioned PDF/DOCX resumes and download them through an authenticated, audited route. The source asks for
DOC support, in-browser preview, certificates, requested documents with tracked completion, and controlled (short-lived) download links.

## Acceptance criteria (backlog)

1. A DOC file uploads and previews.
2. A requested document shows pending, then received.
3. Download links expire.
Edge: a password-protected PDF (uploads and downloads; the preview is the browser's own viewer; extraction already says it is protected).

## Builder's calls

- **D1 (Q-15) converter approved as recommended.** LibreOffice Writer (headless) is installed in the API image (shared by api, worker and
  beat). A Celery task converts a DOC/DOCX resume or document to a PDF rendition in a throw-away directory with its own profile and a 60 s
  timeout. The rendition is stored under `candidate-previews/`. When `soffice` is missing or the conversion fails, the status is `failed`:
  the file still downloads, the preview says it is not available.
- **D2 DOC by byte-sniff.** An OLE2 compound file (`D0 CF 11 E0 A1 B1 1A E1`) whose directory names the `WordDocument` stream (UTF-16LE).
  `application/msword`, `.doc`. Resumes and candidate documents only; the rec-008 JD upload stays PDF/DOCX.
- **D3 preview.** PDF → the original, inline. PNG/JPEG (documents only) → the original, inline. DOC/DOCX → the PDF rendition when
  `preview_status = 'ready'`; `pending` answers 409 ("still being prepared"), `failed` 422 ("not available; download instead").
  Columns `preview_key`, `preview_status` on `candidate_resumes` and `candidate_documents` (null for PDF/images).
- **D4 signed links.** Every resume/document download and preview goes through
  `GET …/link?mode=download|preview` → `{url, expires_in}`: a link valid for **300 s** (S3 presigned URL, or the local
  `/files/signed/{token}` route whose token now also carries file name, content type and disposition). Issuing a link is audited
  (`…_link`, with mode) and `no-store`. The old authenticated resume route stays for compatibility; the UI no longer uses it.
- **D5 DOC text.** Extraction of a DOC resume reads the rendition's text; before it is ready the extract route answers 409.
- **D6 candidate documents.** New table `candidate_documents`: type (fixed list: certificate, education, experience_letter,
  relieving_letter, payslip, id_proof, other), optional title (required for `other`, ≤ 120), file (PDF, DOC, DOCX, PNG, JPEG by bytes,
  ≤ 5 MB), uploader, and the request it fulfils. Append-only (no delete in this item).
- **D7 document requests.** New table `candidate_document_requests`: type, note (≤ 500, shown to the candidate), optional due date (not
  in the past, IST), status `pending → received | cancelled`. One pending request per type per candidate (409). The first upload against
  it (by the candidate or by staff for them) marks it `received` in the same transaction (unique `request_id` on documents; row lock on
  the request). Staff cancel only a pending request.
- **D8 candidate side.** External candidates have no login yet (hrc-022), so staff upload for them. An IT student whose candidate row is
  opted in uses `/account/candidate-documents` (list, upload, link) from the student portal. They see their own requests and documents,
  never staff names (the uploader reads "You" or "Placement team").
- **D9 authorisation.** Staff: `candidates.READERS` read and get links; `candidates.WRITERS` upload, request and cancel; a candidate
  outside the pool is 404 (existing `pool_filter`); archived → 409 on writes. Student: `placement_pool.require_student`, own candidate only;
  not in the pool → GET says `available: false`, writes 409.
- **D10 audit/logs.** Audit actions `candidate.document_upload`, `candidate.document_request`, `candidate.document_request_cancel`,
  `candidate.document_link`, `candidate.resume_link`. Logs carry ids and type, never file names.
- **D11 out of scope:** malware scanning (open question shared with itc-033), deleting documents, reminders for overdue requests,
  external-candidate portal (hrc-022).
- **D12** `/files/download` and `/local-files` withhold the `candidate-documents/` and `candidate-previews/` prefixes (hrc-001 H4).

## API (§12JX)

Staff (`/recruiter/candidates/{id}` …):
- `GET /resume/{version}/link?mode=` → `{url, expires_in}`.
- `GET /documents` → `{documents: [...], requests: [...]}`.
- `POST /documents` multipart `document_type`, `title?`, `request_id?`, `file` → 201 document.
- `GET /documents/{doc_id}/link?mode=`.
- `POST /document-requests` JSON `{document_type, note?, due_date?}` → 201.
- `POST /document-requests/{req_id}/cancel` → 200.
Candidate: `GET /account/candidate-documents`, `POST /account/candidate-documents` (multipart), `GET /account/candidate-documents/{doc_id}/link?mode=`.
Resume output gains `preview_status`.

## UI

- Candidate page: the Resume card accepts DOC; each version has **Preview** and **Download**. A shared `DocumentPreview` pane shows a
  PDF in an iframe or an image, with loading, "being prepared — check again", unavailable and error states.
- Candidate page: a new **Documents** card: requests (type, note, due, status badge, Cancel) with a request form, and documents (type,
  title, file, uploader, date, Preview/Download) with an upload form (type, title, "fulfils request", file).
- Student portal (placement section): **Documents for placement** card: pending requests each with an upload, a certificate upload, and
  the student's own documents with Preview/Download.

## Regression risks

rec-009 resume tests (upload/download kept), rec-012 extraction (DOC path new), hrc-001 withheld-key tests, nehn-003 signed route
(default token shape still served), WorkflowPanel student tests.

## Review notes (Phase 3) and plan

Security: request ids must belong to the same candidate (404 otherwise); the file type is decided by bytes only (no SVG/HTML ever
inline; nosniff on every response); `Content-Disposition` names are built from the candidate code and type, never the upload name; the
student routes take no candidate id (only the caller's own row); tokens are bound to one key, a disposition and 300 s.
API: links are GET + `Cache-Control: no-store`; 409/422 distinguish "preparing" and "unavailable" previews; existing routes unchanged.
Frontend: reuse `sendRequest`, `FormMessage`, `LocalTime`, `.action-card`/`.field`/`.btn` styles; buttons disabled while busy; one ref
guard against double submit; the preview pane is keyboard-closable and labelled.

Tasks (TDD each): 1 DOC sniff + resume accept; 2 signed-link options in storage + `/files/signed`; 3 resume link route + preview status;
4 migration + models; 5 conversion service + Celery task + enqueue; 6 documents/requests staff API; 7 student API; 8 withheld prefixes;
9 web lib + DocumentPreview; 10 resume card; 11 documents card; 12 student card; 13 Dockerfile LibreOffice; 14 docs (DEC, API, RBAC,
backlog); 15 e2e spec.
