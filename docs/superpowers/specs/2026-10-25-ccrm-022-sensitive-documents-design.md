# ccrm-022 — Sensitive documents and access logging (design)

Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` ccrm-022 (source §2, §8 secure access, §16, AC 10 — UNVERIFIED spec, owner request).
Decision: `DEC-SCOPE-262`. Migration `0184_document_sensitivity` (after ccrm-024's 0183). API §12FO, RBAC §2.176.
Dependency ccrm-021 is merged (PR #313). Relates: nehn-003 (not built) — see SD8.

## What exists (verified on `origin/main` @ `475269c6`)

- `GET /workflows/overseas/documents/{id}/download` already admits only the owning student, the application's counselor, the agency in
  `document_scope`, Overseas Admin and super_admin; every call writes a `downloaded` event and a `document.download` audit row.
- `GET /files/download?key=` presigns **any** key for **any** signed-in user and writes nothing (only `agent-kyc/` is refused).
- The university_rep's portal Documents section lists every document of its university's applications (type, status, notes).
- The student's Downloads section returns each verified document's stored `file_url`; the agent's legacy portal Documents section
  returns `file`: the stored `file_url`.
- Document types are the AGN-009 list (`Passport`, `Financial documents`, …) on agency/template routes and free text on the student /
  counselor upload route. Nothing carries a sensitivity class.

## Decisions

| # | Decision | Authority |
|---|---|---|
| SD1 | Classes `standard`, `identity`, `financial`. A type is classed by whole words (the ccrm-021 `_named` rule): identity = passport, aadhaar/aadhar, national id, identity, id card, birth certificate; financial = financial, finance, bank, sponsor(ship), loan, income, salary, tax, itr, affidavit. Everything else is standard. So `Passport` → identity and `Financial documents` → financial. | Backlog (classes); word lists recommended, NEEDS_CONFIRMATION |
| SD2 | Checklist template items and application checklist items carry `sensitivity` (Overseas Admin sets it on the template; an application item copies it; a counselor-added item takes the class of its type unless one is sent). Omitted → the type's class. A document's class is the highest of its type's class and every checklist item it is linked to — an item can raise a document, never lower a passport. | Backlog (DB); max rule recommended |
| SD3 | Identity/financial documents are visible to the owning student, the application's counselor (the existing download rule), the agency in `document_scope`, Overseas Admin and super_admin (platform administrator, existing access). **university_rep never** — the rows are left out of its Documents list and the download route stays closed to it. | Backlog; university_rep + super_admin answers recommended, NEEDS_CONFIRMATION (backlog open question) |
| SD4 | Every download is audited (already); the audit row now carries `sensitivity`. A refused download of an identity/financial document is audited too (`document.download`, outcome `denied`) before the 403. | Backlog "downloads always audited" |
| SD5 | `/files/download` refuses (404, like KYC) any key of an overseas student document — a current or archived row's `file_url` in either stored shape, a replaced file's `document_events.file_key`, or the `agent-documents/` prefix. Those files are reachable only through the audited, scope-checked route. | Backlog "close the /files/download audit gap" |
| SD6 | List endpoints never return file keys: the student Downloads section shows its documents without the key (the Download button is on the Documents page); the agent portal Documents section drops the `file` column. Offer-letter URLs are unchanged (not a document key list; out of scope). | Backlog |
| SD7 | There is no inline view route; the download route is the only way a file is handed out, so `document.download` covers "view/download". No `document.view` route is invented. | Recommended |
| SD8 | The `/local-files` public mount (local storage mode) is unchanged — it is nehn-003's scope (private storage). Residual risk: in local mode a handed-out link stays reachable to anyone holding it. | Backlog (nehn-003) |

## Changes

- `app/document_checklists.py`: `SENSITIVITY_CLASSES`, `type_sensitivity(document_type)`, `highest(classes)`.
- `app/services/document_access.py` (new, the central check): `sensitivities(db, documents)` (type ∪ linked items), `may_see(user, cls)`.
- Model + migration 0184: `sensitivity` String(20) NOT NULL on `document_checklist_template_items` and `application_checklist_items`,
  CHECK IN classes, backfilled from the type/label words (SQL `~*`), server default `standard`.
- `ChecklistTemplateItemIn.sensitivity` optional; template + application checklist views return it.
- Download route: role/scope check moved into `document_access.authorize_download`; audit metadata `sensitivity`; denied audit.
- `/files/download`: SD5 lookup.
- `portal.py`: university_rep filter, the counselor/admin queue rows carry `sensitivity`, SD6.
- Web: template editor Sensitivity select; a "Sensitive · Identity/Financial" badge on the counselor document queue and checklist items.

## Reviews (Phase 3)

- **API:** additive fields only; `sensitivity` input validated by `Literal`; existing responses keep every key. `/files/download` now
  404s for document keys (no web caller uses it — verified by grep; agency/student UIs use the id routes).
- **Security:** no new readable surface. The denied-download audit is committed before raising. The SD5 lookup is parameterised
  (no SQL from the key) and keeps the existing `..`/absolute-path refusal. No file names or keys in logs.
- **Frontend:** reuses `badge` styles and the existing select pattern of the template editor; no new component.

## Tests

`tests/test_ccrm_022_sensitive_documents.py`: classifier; item sensitivity (template, copy, counselor item, max rule); university_rep
list + download refused + denied audit; audited download carries sensitivity; `/files/download` refusals (both shapes, archived,
replaced key, prefix) and an unrelated key still works; SD6 lists have no keys. `tests/test_ccrm_022_migration.py`: chain, constants,
backfill, round trip. Vitest for the editor select and badges; e2e `ccrm-022-sensitive-documents.spec.ts`.
