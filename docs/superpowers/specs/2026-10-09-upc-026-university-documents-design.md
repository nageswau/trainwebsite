# upc-026 — University document centre (design + plan)

**Status:** design written 2026-10-09. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". So the item answers DC1–DC15 (§1) are **recommended defaults accepted under that instruction**
(`NEEDS_CONFIRMATION` as separate per-question approvals) and are registered that way in `DEC-SCOPE-138`.

**Branch:** `feature/upc-026`, cut from `origin/main` @ `f4207d39`.
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-026. Dependency upc-003 (`0105`, `DEC-SCOPE-120`) is merged on
main (PR #151) — verified in code (`University`, `services/partnership_universities.py`, `/partnership/universities/[id]`).
**Source:** `EVID-020` §28 (lines 908–936: 12 document kinds; "Everything related to that university should be in one place"), §13
line 489 (agreement document, stored here for upc-014), §32 menu line 1092 ("Documents"), line 1129 + U2 (commission visibility).
**Numbering:** migration `0123_university_documents`, `DEC-SCOPE-138`, API §12BF, RBAC §2.64 (provisional; re-chained at merge time).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| DC1 | Kinds (AC1) | Exactly the 12 of §28, in source order: `mou` MoU, `partnership_agreement` Partnership agreement, `commission_agreement` Commission agreement, `brochure` University brochure, `course_list` Course list, `fee_structure` Fee structure, `entry_requirements` Entry requirements, `scholarship_information` Scholarship information, `marketing_materials` Marketing materials, `application_guidelines` Application guidelines, `contact_documents` Contact documents, `training_documents` Training documents |
| DC2 | Restricted kind (AC2, U2) | `commission_agreement` is commission data: it is filtered **server-side** from every list, count and download for any role without `can_see_commission` (today overseas_admin; counselors in upc-030 never get it). It can never be shareable (422 + DB CHECK) |
| DC3 | Q-26 shareable default per kind | **Shareable by default:** brochure, course list, fee structure, entry requirements, scholarship information, marketing materials, application guidelines, training documents. **Internal by default:** MoU, partnership agreement, contact documents (PII); commission agreement is always internal. The uploader may override (except DC2) at upload and later |
| DC4 | Q-26 file types | Judged by the **bytes**, never the name or the client's Content-Type: PDF, DOCX, XLSX, PPTX (OOXML zip with its main part; only the central directory is read), JPEG, PNG (image metadata stripped, the AGN-009 G8 rule). Anything else, including executables → **422** "Upload a PDF, Word, Excel, PowerPoint, JPEG or PNG file" (the backlog's negative scenario) |
| DC5 | Q-26 size | `settings.max_upload_bytes` (20 MB, the platform cap; brochures and marketing packs are large). Larger → 413; empty → 422 |
| DC6 | Versions (edge case) | A **document** (kind, title, shareable) has append-only **versions** (file, uploaded by/at). Uploading to an existing document adds version n+1, which becomes current; older versions stay downloadable. ≤ 50 versions per document, ≤ 200 documents per university (409 beyond) |
| DC7 | Who reads | The master readers (`require_reader`): partnership_manager, partnership_head, super_admin read every document (DC2 applies by role); **overseas_admin reads shareable documents only** (U14, the upc-006 CT5 slice). Counselors read via upc-030 (the backlog's U14 slice); no counselor route here |
| DC8 | Who writes | Upload, new version, edit title/shareable: the master's edit scope minus overseas_admin — the same rule as contacts. New permission **`can_manage_documents`** on the university (403 wrong role/team, 409 inactive university) |
| DC9 | Delete | **Not in this item** (not in the backlog API line). A wrong file is superseded by a new version; removal is a follow-up if needed |
| DC10 | "Signed download" | An authenticated, scoped download through the API (`GET …/documents/{doc}/file[?version=n]`), audited **before** any byte leaves, `Cache-Control: private, no-store`, `nosniff`, sandbox CSP, `attachment` (the rec-008/rec-009 pattern). No public URL is ever handed out, so no presigned link can leak |
| DC11 | Title | Required, 2–200 characters after trimming, unique per university + kind case-insensitively (409 — upload a new version instead) |
| DC12 | Menu page | `/partnership/documents`: every document the reader may see across universities, filtered by kind and a title/university search, newest change first, paged (50, the list pages' shared size). Backed by `GET /partnership/documents` |
| DC13 | Audit / logs | `university_document.upload`, `.version`, `.update`, `.download` (entity = the document; ids, kind, version, content type, size, field names only — never titles or file names) |
| DC14 | Storage keys | Server-generated `university-documents/<uuid>`; the file is stored before the row lock and discarded if the write does not commit (rec-008) |
| DC15 | Rate limit | None beyond the size cap: internal authenticated staff only, scoped writes (recorded as a known gap for upc-033) |

## 2. Data model — migration `0123_university_documents`

- `university_documents`: id, university_id FK RESTRICT, kind String(30) CHECK (DC1), title String(200) NOT NULL, shareable bool NOT NULL,
  current_version int NOT NULL CHECK ≥ 1, created_by_user_id FK users, created_at, updated_at. CHECK
  `ck_university_documents_commission_internal` (`kind <> 'commission_agreement' OR NOT shareable`). Unique index
  `uq_university_documents_title` (university_id, kind, lower(title)); index `ix_university_documents_updated` (updated_at).
- `university_document_versions`: id, document_id FK RESTRICT, version int CHECK ≥ 1, storage_key String(300) unique, file_name String(255),
  content_type String(120), size_bytes int CHECK > 0, uploaded_by_user_id FK users, uploaded_at. Unique (document_id, version).
- Created only when missing (0001 builds a fresh DB from models). Downgrade refuses while any document exists.

## 3. Backend

`services/university_documents.py` (functions, no commit) and `api/university_documents.py` (prefix `/partnership`).

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/universities/{id}/documents` | master readers | `{items,total,limit,offset}` by kind order, then title; each item carries its versions (newest first). `kind` filter. Unknown university → 404 |
| `POST /partnership/universities/{id}/documents` | `can_manage_documents` | multipart `kind`, `title`, `shareable?` (omitted → DC3 default), `file` → 201 `{document}` (version 1) |
| `POST /partnership/universities/{id}/documents/{doc}/versions` | same | multipart `file` → 201 `{document}` (version n+1) |
| `PATCH /partnership/universities/{id}/documents/{doc}` | same | JSON `title`, `shareable` (only sent fields; equal = no change) |
| `GET /partnership/universities/{id}/documents/{doc}/file` | readers who can see it | current version, or `?version=n`; audited; invisible → 404 |
| `GET /partnership/documents` | master readers | DC12; `kind`, `q`, `limit` ≤ 50, `offset` |

- Visibility = `university_id` match + (`can_see_commission` or kind ≠ commission) + (full view or `shareable`). Hidden documents are a 404,
  never a 403 (no existence leak).
- Writes: permission checked before a byte is read; file read/sniffed/stored; then university row `FOR UPDATE` (serialises limits, titles,
  version numbers), re-check, insert, audit, one commit; on any failure rollback + discard the stored object. The unique indexes are the
  backstop (a lost race → 409).
- `permissions()` gains `can_manage_documents` (CONTACT_ROLES ∩ edit scope ∩ active).

## 4. Frontend

- `lib/universityDocuments.ts`: kinds + labels + default shareable, types, URLs, accept list, max bytes, list query helpers.
- `components/UniversityDocuments.tsx` (client): the university page's **Documents** section — one table/card list (kind, title, current
  version, size, uploaded by/at, shareable badge, Download); older versions in a `<details>`; upload form (kind select → shareable default,
  title, file); per-document "Upload new version" and "Edit" (title + shareable); double-submit guard; field errors; `role=status` notices;
  client-side size check; `router.refresh()`.
- `[id]/page.tsx`: reads the documents beside the university.
- `app/partnership/documents/page.tsx`: DC12 menu page (GET form filters, table, paging, empty/past-end states).
- `navigation.ts`: Documents goes live in the manager menu; the head nav gains "Documents".

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | All 12 kinds are supported (exact list, labels, upload of each) | `test_upc_026_documents.py`, vitest, e2e |
| AC2 | A non-commission role (overseas_admin now; counselors via upc-030) never sees the commission agreement — list, menu list or download | tests |
| P1 | A fee structure PDF is shared (default shareable) and the shareable slice (overseas_admin) can list + download it | tests, e2e |
| N1 | An executable upload → 422; empty → 422; oversize → 413 | tests |
| E1 | Versions: a second upload is version 2 and current; version 1 still downloads | tests, e2e |
| R1 | Non-owner manager / overseas_admin write → 403; inactive university → 409; unknown university/document → 404; counselor → 403 | tests |
| S1 | Downloads are audited before streaming and carry no-store/nosniff/attachment headers | tests |

## 6. Tasks (TDD, in order)

1. Migration + models + parity/round-trip test (`test_upc_026_migration.py`).
2. Service + routes: read/visibility tests, then upload/version/patch/download/limits tests, then code. `can_manage_documents`.
3. Frontend lib + `UniversityDocuments` + page wiring + menu page + nav, vitest.
4. Playwright `upc-026-university-documents.spec.ts`; docs (DEC-SCOPE-138, API §12BF, RBAC §2.64, DATA_MODEL, SCREEN_CATALOG, backlog).

## 7. Regression set (lite)

`test_upc_003_universities.py`, `test_upc_006_contacts.py`, `test_upc_007_access.py`, the upc-003/006 vitest files
(`UniversityDetailPage.test.tsx`, `UniversityActions.test.tsx`, `navigation.partnership.test.ts`).

## 8. Phase 3 review notes (api-and-interface-design, frontend-ui-engineering, security-and-hardening)

- **API:** order of refusals = 403 role (`require_reader`) → 404 university → 404 document (hidden = not found) → 403 write scope → 409
  inactive / limits / title. Multipart for files, JSON for the metadata PATCH. `version` is `int ≥ 1`; an unknown version is a 404.
  Existing contracts are unchanged; the university detail gains one permission key (additive).
- **Security:** the `Content-Disposition` name is built from the university code, kind and version (`UNV-000012-fee_structure-v2.pdf`),
  never from the uploaded name or title (no header injection); files are served as attachments under a sandbox CSP with `nosniff`;
  OOXML sniffing reads only the zip central directory (no extraction, no zip-bomb exposure); keys are server-generated and resolved
  under the storage root; logs/audit carry ids only. CSRF/session handling is the platform's (same fetch path as every other upload).
- **Frontend:** reuses the contacts card pattern (`.card` blocks inside an `action-card wide`), the `.telecaller-list` responsive table
  for the menu page, `BdmConfirm` is not needed (no destructive action), labelled file inputs with `aria-describedby` errors, `role=alert`
  failures and `role=status` notices, busy-disabled buttons as the double-submit guard.
