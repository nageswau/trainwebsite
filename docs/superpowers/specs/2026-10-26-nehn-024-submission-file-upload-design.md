# nehn-024 — Direct file upload for assignment submissions (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-024` (§9 "File Submission" L188-198; §24 "Assignments";
action 8; `UNVERIFIED` backlog). Decision: `DEC-SCOPE-291`. Depends on nehn-003 (`DEC-SCOPE-279`, merged): `POST /files/upload?purpose=`,
`stored_files`, the `assignment_submission` policy (PDF, DOC, DOCX, JPEG, PNG, HEIC — 5 MB, sniffed). The owner pre-authorised the
recommended answers; open questions are recorded as `NEEDS_CONFIRMATION`, not resolved.

## Intent

Students attach their work (PDF, Word, photos of handwritten pages) directly instead of pasting an external link. The trainer opens the
files from the grading card through a route that checks they may see them. Text answers stay.

## Current state (verified 2026-10-26)

- `Submission.file_url` String(500); `AssignmentSubmissionIn.file_url: str | None`.
- `POST /workflows/it/assignments/{id}/submissions` enforces `submission_type` (text / file / text_or_file) and records lateness.
- `AssignmentSubmissionPanel` has a free-text "File URL (if required)" box; the trainer's grading card (`TeacherWorkspaceActions`)
  links `file_url`.
- `GET /files/{id}` serves a stored file to its owner and super_admin only — a trainer gets 403 there by design (nehn-003 PS5:
  record-specific access belongs to the consuming routes).

## Design (builder's calls)

| # | Call | Why |
|---|---|---|
| F1 | New table `submission_files` (id, submission_id → submissions CASCADE, stored_file_id → stored_files CASCADE, created_at), unique on `stored_file_id`. Filename, size and MIME come from the `stored_files` row (no duplication). | Backlog's table option; a file belongs to one submission. |
| F2 | Up to **5** files per submission. `NEEDS_CONFIRMATION` (1 or N). | Scanned handwriting is often several pages. |
| F3 | `file_url` is **kept** in the API and the panel keeps an optional "Link" field (e.g. a repository). `NEEDS_CONFIRMATION`. | Backward compatible; removing links is irreversible for projects. |
| F4 | Submit accepts `file_ids: list[UUID] | None` (≤ 5, duplicates ignored). Every id must be a `stored_files` row **owned by the caller** with purpose `assignment_submission` and not attached to another submission; otherwise **422** "One or more files cannot be attached to this submission" (one message, so nothing about other users' files is confirmed). | Upload authorization: only the student, only for their own submission. |
| F5 | `file` assignments need `file_ids` or `file_url`; "answer or file" counts `file_ids`. | Existing enforcement extended. |
| F6 | Resubmission: `file_ids` present replaces the attached set; absent keeps it (same rule as `answer`/`file_url`). Replaced `stored_files` rows stay (owner-only). Versioning `NEEDS_CONFIRMATION`. | Matches existing semantics. |
| F7 | `GET /workflows/it/trainer/submissions` rows gain `files: [{id, filename, content_type, size, url}]`; existing keys unchanged. | Review shows the file list. |
| F8 | New `GET /workflows/it/submissions/{submission_id}/files/{file_id}`: the submitting student, the batch's trainer, it_admin (it division), super_admin → the file (attachment for non-inline types, `nosniff`; 307 to a presigned URL in S3 mode). Anyone else signed in → 403; no session → 401; unknown submission or a file not attached to it → 404. | Download authorization from the backlog. Serving reuses `files.py`'s stored-file response. |
| F9 | The student panel gets a file picker (multiple; drag-and-drop zone) and a "Take a photo" input (`accept="image/*" capture="environment"`) for mobile. Files over 5 MB or of other types are refused in the browser with a named message before upload; the server's policy refusal is shown as worded otherwise. On submit each file goes to `POST /files/upload?purpose=assignment_submission`, then the submission is posted with the ids. | AC2 "clear message"; AC5 camera capture. |
| F10 | The student portal assignment rows gain `submission_type` (not a column), so the panel says "File required" / "Text required" / "Text or file". | Avoids a submit-then-422 round trip. |
| F11 | The `assignment.submit` audit metadata gains `file_count`. | Audit trail. |
| F12 | Uploaded-but-never-submitted files stay private to their owner; **no sweep** in this feature (follow-up). | Orphan edge case; no data loss. |

**Not in scope:** AV scanning (nehn-003 PS8), HEIC preview in the browser (HEIC downloads as a file), late-submission blocking (the
existing late flag is unchanged), presigned direct-to-bucket upload.

**Alternatives rejected:** columns on `submissions` (single file only); storing the key/filename on the link row (duplicates
`stored_files`); widening `GET /files/{id}` to trainers (puts record-specific rules in the generic route, against nehn-003 PS5).

## Acceptance (testable)

1. A student uploads a 3 MB PDF and submits a `file` assignment; the batch trainer downloads it via F8 (200, same bytes).
2. A 6 MB file is refused: in the browser before upload with "… is larger than 5 MB", and by the server (413) if posted directly.
3. A `text_or_file` assignment accepts text only, file only, or both.
4. Another student → 403; a trainer of another batch → 403; anonymous → 401; another student's file id at submit → 422.
5. On mobile the "Take a photo" input carries `capture="environment"`; a JPG photo submits.
6. Existing `file_url` submissions and the grading flow behave as before.

## Regression risks

`test_stu_004_submissions.py`, `test_trn_007_grading.py`, `trn-007-grading.spec.ts`, the trainer grading card.
