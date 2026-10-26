# nehn-003 — Private, S3-compatible file storage with per-feature upload policy (design)

Backlog: `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-003` (source §9 L191-198, §24 "Storage"; `DEC-INFRA-002` ID4;
`psb-017`). Decision: `DEC-SCOPE-279`. Migration `0194_stored_files`. API §12GE, RBAC §2.193.
Dependencies: none on another feature. The backlog's "infra decision (Spaces vs Volume)" is answered here by the recommended default
PS1 — the Volume stays (`DEC-INFRA-002` ID4, `CONFIRMED_CURRENT` topology); this feature only makes the code S3-compatible, so Spaces
becomes a configuration switch. No provider infrastructure is created (`DEC-INFRA-001` gate respected).

## What exists (verified on `main` @ `d0a169a4`)

- `StorageService` (`services/storage.py`) uses boto3 when `AWS_S3_BUCKET` is set, otherwise `/data/uploads`. No `endpoint_url`;
  every `put_object` sends `ServerSideEncryption="AES256"`.
- `main.py` mounts `/local-files` as a public `StaticFiles` over the whole upload directory; only `agent-kyc/` is refused (AGN-024).
  `presign_download` in local mode returns that public `/local-files/<key>` path, so every "authorised" download route (certificates,
  receipts, invoices, profile and overseas documents, data exports) hands out a link anyone can open, forever.
- `files.py` `local-upload` writes directly (not through `StorageService`), reads the whole body into memory and trusts the client's
  content-type. One global 20 MB limit.
- `certificates.py`, `billing_documents.py` and `public.py` `career-upload` each build their own boto3 client / write the disk directly.
- Public images already stream through their own routes (testimonial photos `/public/testimonials/{id}/photo`), so nothing that must
  stay public depends on `/local-files`.

## Decisions (recommended defaults, `NEEDS_CONFIRMATION` unless stated)

| # | Decision |
|---|---|
| PS1 | Storage stays on the Volume (ID4). New settings `S3_ENDPOINT_URL` (Spaces/MinIO) and `S3_SSE` (default `AES256`; empty disables SSE, for providers that reject it) feed one boto3 client in `StorageService`; `AWS_REGION` is reused. The one-off "move local files to object storage" script is deferred until the owner chooses Spaces (backlog item 6 is conditional). |
| PS2 | In local mode `presign_download(key)` returns a short-lived signed link `/api/v1/files/signed/<token>` — a JWT (`type="download"`, `sub=key`, 900 s, the app secret) — streamed by the API. The same 900 s TTL as the S3 presign it mirrors. The token is useless as a session (`get_current_user` accepts only `type="access"`). |
| PS3 | `/local-files/<key>` is no longer a public mount. A key under `public/` is served to anyone (explicit public prefix, empty today). Any other key: **no session → 404** (AC1; 404, not 401, so existence is not revealed); signed in → served under the existing `/files/download` rules (KYC and overseas-document keys 404). This is the compatibility route for URLs already stored in rows (AC6) and does not widen today's signed-in access. |
| PS4 | Upload policies (`services/upload_policy.py`), each max bytes + allowed types, checked against the client content-type **and** the sniffed magic bytes: `default` (today's list, 20 MB), `assignment_submission` (PDF, DOC, DOCX, JPEG, PNG, HEIC — 5 MB), `learning_material` (PDF, DOC, DOCX, XLSX, PPTX, JPEG, PNG — 20 MB), `signature` (PNG, 1 MB), `university_logo` (PNG, WebP, JPEG — 1 MB; SVG not allowed), `career_resume` (PDF, DOC, DOCX — 5 MB). |
| PS5 | `stored_files` (key, purpose, owner, filename, content type, size, sha256) backs the new `POST /files/upload?purpose=` (201) and `GET /files/{id}` (owner or super_admin → the file; anyone else signed in → 403; no session → 401; unknown → 404). Record-specific access (trainer of a batch, …) belongs to the consuming routes (nehn-024, 027, 032, 035). |
| PS6 | `local-upload` and `career-upload` keep their response shapes but go through the `default` / `career_resume` policy (sniffed) and `StorageService.write_stream`. Starlette spools a multipart file to disk past 1 MB, so the upload is copied in chunks, never read whole into memory. |
| PS7 | Certificates, receipts and invoices are written through `StorageService.write_bytes`; their returned/stored URL strings are unchanged. |
| PS8 | No AV scanning (not in the source). No change to the S3 presigned-PUT flow (a direct-to-bucket PUT cannot be sniffed; S3 mode is not used today). |
| PS9 | Callers' `expires_in` stays as is (`900` in S3 mode, `None` locally) — no response contract changes. |

## Changes

- `core/config.py`: `s3_endpoint_url`, `s3_sse`.
- `services/storage.py`: `_client()`, configurable SSE, `write_stream`, `local_file`, signed local `presign_download`, `signed_key`.
- `services/upload_policy.py` (new): `POLICIES`, `sniff(head)`, `check(purpose, content_type, size, head)` → `PolicyError(status, msg)`.
- `models.py` `StoredFile`; migration `0194_stored_files`.
- `api/files.py`: `POST /files/upload`, `GET /files/{id}`, `GET /files/signed/{token}`, `local_router` `GET /local-files/{key:path}`,
  `local-upload` through policy + storage.
- `main.py`: the `StaticFiles` mount is replaced by `files.local_router`.
- `services/certificates.py`, `services/billing_documents.py`, `api/public.py`: through `StorageService`.
- Frontend: the Next `/local-files/[...path]` and `/api/[...path]` proxies already forward the session cookie. The three inline
  upload flows (`ProfileDocumentUpload`, `WorkflowPanel` ×2) become one `lib/uploadFile.ts`, which falls back to the presigned PUT only
  on local-upload's S3-mode 400 and otherwise shows the server's refusal (QA-02: a sniffing 415 surfaced as "Object storage upload failed").

## QA (Phase 5)

| ID | Severity | Finding | Fix |
|---|---|---|---|
| QA-01 | Medium | A `.txt` profile document downloaded instead of opening in its tab (inline allow-list lacked `text/plain`) | `text/plain` inline (inert under `nosniff`); `test_plain_text_opens_inline_but_markup_is_only_ever_an_attachment` |
| QA-02 | Medium | A content-spoofed upload showed "Object storage upload failed" after a stray PUT (405) | `lib/uploadFile.ts`; `tests/lib/uploadFile.test.ts` |
| — | n/a | `stu-007` e2e posts `override` without the ADM-006 reason (422) — predates nehn-003; `pay-001 @external` needs live Razorpay keys | not changed (out of scope) |

## Review notes (Phase 3)

- **API:** no existing response shape changes; new routes follow `/files` conventions; 413 size / 415 type / 422 unknown purpose.
- **Security:** closes anonymous access to every private key (the production exposure); signed links are scoped to one key and expire;
  path traversal still guarded by `_local_path`; filenames are sanitised and keys are random; sniffing blocks a renamed `.exe`;
  `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff` on streamed files so an uploaded HTML/SVG cannot run in-origin.
- **Residual risk:** a signed-in user holding a legacy `uploads/` key can still fetch it (unchanged from today's `/files/download`);
  per-record checks on legacy keys stay with the record routes.
- **Concurrency/transactions:** `/files/upload` writes the object, then the row; if the commit fails the object is deleted.
