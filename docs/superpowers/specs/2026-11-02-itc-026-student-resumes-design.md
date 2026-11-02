# itc-026 — Student resume upload with versions, staff upload and access log (design)

`DEC-SCOPE-350`. Source: `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` itc-026 (PDF §5 upload rules step 1, §4 "Resume & documents",
§10 "Secure file storage … log access", §12 AC3; PDF classified `UNVERIFIED`). Owner Q-01 (2026-11-01): all phases approved for build
in waves. Dependency itc-003 merged (PR #410). The owner said to proceed with the recommended answers, so every call below marked R* is
the builder's (`NEEDS_CONFIRMATION`).

## Intent

Give each IT student one resume with history: the student — or their IT counselor / the IT Admin on their behalf — uploads a PDF, DOC or
DOCX; each upload is a new version (the latest is current) recording who uploaded it and whether HR may see it; every download by
anyone is written to the audit log. itc-027 (HR review task) builds on it.

## Non-goals

- HR review task, assignment rule, HR stages (itc-027). Field visibility framework (itc-028).
- Malware scanning (R2). Resume text extraction / search for students.
- Changing `ProfileDocument` (STU-011) or the nehn-017 HR document routes — both stay exactly as they are.

## Decisions (builder's calls)

- **R1 — Q-22:** a separate `student_resumes` table, not `CandidateResume`. The recruiter pool is opt-in by the student (rec-010);
  sharing one table would put a student's resume in front of recruiters without that opt-in. A later link stays possible.
- **R2 — Q-23:** malware scanning is deferred (no scanner exists; the PDF says "where supported"). Mitigations: type decided by the
  bytes, downloads always `attachment` with `nosniff` and `CSP: default-src 'none'; sandbox`, private storage only.
- **R3 — types by bytes, never by name or client Content-Type:** PDF (`%PDF-`), DOC (OLE2 signature, legacy binary), DOCX (ZIP holding
  `word/document.xml`; only the central directory is read). Anything else → 415 and nothing stored. A `.exe` renamed `.pdf` → 415.
- **R4 — configurable limit:** `student_resume_settings`, one row (`id = 1`), `max_bytes`; no row = 5 MB default. The IT Admin sets it
  in whole MB from 1 to 10 (hard ceiling, below the global 20 MB upload cap). Over-limit → 413 "The resume must be at most N MB".
  Lowering the limit never touches stored versions.
- **R5 — versions:** append-only, `unique(student_user_id, version)`. The upload locks the student's user row, takes max+1, inserts.
  The file is stored first (server-generated key `student-resumes/<hex>`) and deleted again when the transaction fails.
- **R6 — visibility:** recorded per version at upload, `hr` (default: HR may open it) or `private` (student, counselor and IT Admin
  only). Immutable — to change it, upload a new version.
- **R7 — downloads:** streamed by the API as an attachment (rec-009 idiom). The audit row `it.resume.download` (version, reader role) is
  committed before any byte is returned — the access log (AC4). Uploads write `it.resume.upload` (version, size, type, visibility,
  uploader role). No file name or content is logged anywhere.
- **R8 — who (everyone else 403; out of scope 404, no disclosure):**
  - IT student: own resumes, `/it/me/resumes`.
  - IT counselor: linked students only (itc-003), `/counselor/it/students/{id}/resumes` (reuses `it_student_profiles.staff_student`).
  - IT Admin: any IT student, `/admin/it/students/{id}/resumes`.
  - HR (`hr_team`, or `super_admin` as in nehn-017): read and download only, students in the nehn-017 HR population, `hr` versions only,
    with the `student_documents.view` / `student_documents.download` grants; `/hr/students/{id}/resumes`. HR uploads nothing.
- **R9 — limit settings:** `GET/PUT /admin/it/resume-settings` (IT Admin only). Every list response carries `max_bytes`, so each upload
  form shows the current limit.
- **R10 — UI:** one client component `StudentResumeCard` (versions newest first, "Current" badge, size, date, uploader, visibility; an
  upload form with a "Share with HR" checkbox where allowed). It appears on the student's Profile section, on the counselor/admin
  student record page (itc-012), and read-only on the HR student page. The IT Admin's Students section gains `ResumeLimitPanel`.

## API (§12IV)

- Version `{version, file_name, content_type, size_bytes, visibility, uploaded_by: {id, full_name} | null, uploaded_by_role, created_at}`.
- `GET …/resumes` → `{items: Version[] (newest first), max_bytes, can_upload}`.
- `POST …/resumes` multipart `file`, form `visibility` (`hr` | `private`, default `hr`) → **201** Version. 413 over limit or empty is
  422; 415 wrong type; 422 bad visibility.
- `GET …/resumes/{version}/file` → **200** the bytes as an attachment; 404 unknown version or file gone.
- `GET /admin/it/resume-settings` → `{max_mb, max_bytes, min_mb: 1, max_mb_ceiling: 10}`; `PUT` `{max_mb: 1..10}` → same; audited
  `it.resume.settings_update` (before/after).

## Data

Migration `0235_student_resumes` (on `0234_it_student_notes`): `student_resumes` (id, student_user_id FK users,
version, storage_key, content_type, file_name, size_bytes, visibility CHECK, uploaded_by_user_id FK users, created_at; unique pair;
index student/version) and `student_resume_settings` (id CHECK = 1, max_bytes CHECK 1 MB..10 MB, updated_by_user_id, timestamps).
Downgrade refuses while resumes exist (their files would be orphaned). No existing data changes.

## Acceptance (from the backlog, made testable)

1. A `.exe` (MZ bytes) named `cv.pdf` with `application/pdf` → 415, no row, no file.
2. A file over the configured limit → 413 whose message names the limit in MB; after the admin lowers the limit, older bigger versions
   still list and download.
3. Uploading v2 keeps v1 listed and downloadable; v2 is current.
4. Each download (student, counselor, admin, HR) writes one `it.resume.download` audit row.
5. **+** a linked counselor uploads v2 for a student; `uploaded_by` is the counselor.
6. **−** another student, an unlinked counselor or HR outside the population get 404; a trainer gets 403; HR never sees `private`.
7. **E** a legacy `.doc` (OLE2) is accepted as `application/msword`.

## Risks

`ProfileDocument` / nehn-017 HR document access are untouched (regression risk only through shared imports). Memory: a version is read
into memory on download (≤10 MB, same as rec-009).
