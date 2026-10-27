# nehn-027 — Trainer learning materials: file upload and manage (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-027` (§10 "Upload course materials", "Upload
documents/videos/links", "Manage batch-specific resources", "Manage learning resources", L223-225, L230; `UNVERIFIED` backlog).
Decision: `DEC-SCOPE-294`. Depends on nehn-003 (`DEC-SCOPE-279`, merged): `POST /files/upload?purpose=`, `stored_files`, the
`learning_material` policy (PDF, DOC, DOCX, XLSX, PPTX, JPEG, PNG — 20 MB, sniffed). The owner pre-authorised the recommended answers;
open questions are recorded as `NEEDS_CONFIRMATION`, not resolved.

## Intent

A trainer publishes course materials for a batch either as an uploaded file (weekly notes, slides) or as a link (YouTube/Drive videos,
provider recordings), and then manages them: lists, edits, reorders and removes them. Enrolled students of that batch download files
through a route that checks they may; nobody else sees them.

## Current state (verified 2026-10-27)

- `LearningResource` (`learning_resources`): `batch_id`, `title`, `resource_type`, `url` (String 500, NOT NULL), `metadata_json`.
- `POST /workflows/it/trainer/materials` creates a link resource (trainer: own batch, else 403; it_admin: any). No list/edit/delete.
- Read surfaces: student portal `downloads` section and `GET /workflows/it/student/learning` (enrolled batches); trainer portal
  `materials` section (own batches); admin portal `resources` section (ADM-009, every batch). URLs are shown as plain text.

## Design (builder's calls)

| # | Call | Why |
|---|---|---|
| M1 | Migration `0202_learning_resource_files`: `learning_resources` gains `stored_file_id` (FK `stored_files` ON DELETE SET NULL, nullable, unique), `sort_order` (int, default 0), `deleted_at` (timestamptz, nullable); `url` becomes nullable. Filename, size and MIME come from the `stored_files` row instead of the backlog's `storage_key/filename/size/mime` columns. | nehn-024 precedent: no duplication of `stored_files`. Existing rows keep their `url` and get `sort_order` 0. |
| M2 | Create accepts **exactly one** of `url` or `file_id` (else 422). `file_id` must be the caller's own `learning_material` upload, not attached to another resource; otherwise one 422 "This file cannot be attached to a material". | Upload authorization; nothing about other users' files is confirmed. |
| M3 | **Video stays link-only** (`NEEDS_CONFIRMATION`): `resource_type` `video`/`recording` with a `file_id` → 422 "Upload videos to YouTube or Google Drive and add the link". The policy already refuses video MIME types (415) and >20 MB (413); the trainer UI states the 20 MB limit and the link guidance up front. | Backlog "keep video as links only"; no object-storage video budget is approved. |
| M4 | `GET /workflows/it/trainer/materials?batch_id=` lists live (not deleted) resources: trainer → own batches only, it_admin → all. Ordered `sort_order`, then newest first. Each row: `id, batch_id, batch, title, resource_type, url, sort_order, file: {filename, content_type, size} | null, created_at`. For a file resource `url` is the authorised download route. | Manage list. |
| M5 | `PATCH /workflows/it/trainer/materials/{id}`: `title`, `resource_type`, `url` (link resources only), `sort_order` — all optional, at least one. Same type rule as M3. Trainer must own the batch (403); unknown or deleted → 404. | Edit + reorder. "Visibility" in the backlog has no existing field; a visibility flag is `NEEDS_CONFIRMATION` and not built. |
| M6 | `DELETE /workflows/it/trainer/materials/{id}` → 204, sets `deleted_at` (soft). Repeat → 404. The stored file stays (owner-only via `GET /files/{id}`). | Backlog "delete (soft)". |
| M7 | `GET /workflows/it/materials/{id}/file`: an it_student **enrolled in the resource's batch**, the batch's trainer, it_admin, super_admin → the file (nehn-003 `serve_stored_file`: attachment + nosniff, or 307 presigned in S3 mode). Any other signed-in user, a deleted resource, a link resource or an unknown id → **404** (AC4); anonymous → 401. | Download authorization; 404 so another batch's materials are not confirmed to exist. |
| M8 | Every read surface (student downloads, student learning, trainer materials section, admin resources) hides `deleted_at` rows and shows the download route for file resources. The student downloads table renders the URL column as an "Open" link (new `DataTable` column type `link`). | AC2 "disappears for students"; a plain-text URL is not usable. |
| M9 | Audit: `learning_resource.create` metadata gains `kind` (`file`/`link`); new `learning_resource.update` (changed field names) and `learning_resource.delete`. | Audit trail. |
| M10 | Trainer UI (`CourseMaterialsPanel`, mounted in the trainer `materials` section): publish form with a **File / Link** choice (file input with `accept` matching the policy; browser refuses >20 MB or other types with a named message before upload), then a "Your materials" list filtered by batch with Edit (title, type, link), Move up/down (swaps `sort_order`), and Delete (confirm). Loading, empty and error states. | Reuses `uploadStoredFile` (nehn-024) and LiveSessionManagePanel's card/feedback idiom. |
| M11 | A trainer reassigned away from a batch loses manage and download access immediately (checks read `batches.trainer_id` per request). Sharing one resource across batches is `NEEDS_CONFIRMATION`; today a trainer publishes it per batch (a file must be uploaded again per batch, M2's "not attached elsewhere"). | Edge cases from the backlog. |

**Not in scope:** payment-gated downloads (nehn-018), video hosting, AV scanning (nehn-003 PS8), a link allow-list (optional in the
backlog), presigned direct-to-bucket upload (files ≤ 20 MB go through the API as nehn-024 does).

**Alternatives rejected:** a join table like `submission_files` (a resource has exactly one file); the backlog's
`/it/batches/{id}/resources/{rid}` paths (the existing create lives at `/it/trainer/materials`, so the manage routes sit beside it and
the existing contract is unchanged); hard delete (backlog says soft).

## Acceptance (testable)

1. The trainer uploads a PDF to batch A; batch A's enrolled student sees it in Downloads and downloads it via M7 (200, same bytes).
2. The trainer edits the title and soft-deletes it; the student no longer sees it and M7 returns 404.
3. A link resource is still created, listed and shown to students (existing TRN-004 behaviour).
4. A student in batch B gets 404 on M7; another trainer gets 403 on PATCH/DELETE; anonymous gets 401.
5. A video file / file over 20 MB is refused with guidance to use a link.
6. Reordering changes the order the student sees.

## Regression risks

`test_trn_004_recordings_and_resources.py`, `test_adm_009_resources_oversight.py`, the student Downloads section, `seed.py` link rows.
