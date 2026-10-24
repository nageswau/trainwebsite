# ccrm-019 — Application checklist, readiness summary, Ready-for-Submission gate (design)

Status: design, 2026-10-24. Backlog item `ccrm-019` (`docs/delivery/COUNSELOR_CRM_BACKLOG.md`). Source class: owner request on an
`UNVERIFIED` spec (§8 readiness summary, §14 document readiness, AC 5) plus owner answer CC10. Decision `DEC-SCOPE-257`, migration
`0180_application_checklists`, API §12FJ, RBAC §2.172 (ccrm-013, built in parallel, holds 0179 / DEC-SCOPE-256 / 12FI / 2.171).
Depends on ccrm-014 (sub-status), ccrm-018 (templates, `services/document_checklists.resolve`), ccrm-021 (document status list,
`archived_at`), all merged.

## 1. Owner answers (2026-10-24)

| ID | Question | Answer |
| --- | --- | --- |
| AC1 | How does a checklist item get its status? | **Derived + marks.** The counselor links student documents to an item (auto-linked by matching type when the checklist is created). Item status = the best status among its linked current documents. The counselor can mark an item **Requested** (Appendix B: University A asks again → pending on A only) or **Not required**; linking a document clears the mark. |
| AC2 | `documents_completed_on` (a ccrm-013 field) | **Add the column here** (only if missing — ccrm-013 adds the same column in 0179). Set to today (India) when the last required item becomes complete and the field is empty; cleared when a required item stops being complete. |

Defaults taken without a question (`NEEDS_CONFIRMATION` in the DEC):

- AC3 Only the `admission` template kind feeds this checklist (the visa kind stays for a later visa checklist).
- AC4 The counselor creates the checklist (button); the gate also creates it, under the application lock, when a template matches and
  none exists, so the gate cannot be bypassed by never opening the checklist. No template and no items → the gate has nothing to check
  and passes (today's behaviour).
- AC5 A checklist made without a template (counselor items only) uses gate mode `warn`.
- AC6 The gate runs only when the target sub-status is `ready_for_submission`, on the counselor/admin route and the agency route.
- AC7 Agency members and the student read the checklist (API); the agency detail page shows it read-only. Uploads stay on the existing
  routes; the counselor links them. No student screen in this item (as ccrm-023).
- AC8 Counselor-added items can be removed; template items cannot (mark them Not required instead).
- AC9 A replaced document's links move to the new version (ccrm-021 S3); the expiry job and every review route refresh the
  completion date of the applications whose checklist links the document.

## 2. Existing behaviour (verified on main @ c08aff5d)

- `POST /workflows/overseas/applications/{id}/sub-status` (counselor own apps incl. agency, Overseas Admin) and
  `POST /agent/applications/{id}/sub-status` (agency) both call `services/application_sub_status.change`, which writes one
  `application_status_history` row (`reason` column exists, ccrm-016).
- Templates (`document_checklist_templates` / `_items`) carry `gate_mode`, `version`, items with `document_type`, `label`, `required`,
  `allowed_statuses`, `notes`. Nothing instantiates them yet.
- `student_documents`: owner `student_id` and/or `agent_student_id`, optional `application_id`, `verification_status` in
  `ITEM_STATUSES`, `archived_at` for replaced versions. Direct-student uploads use free-text types; agency uploads the fixed list.
- `overseas_applications.documents_completed_on` does not exist on main.

## 3. Data model (migration `0180_application_checklists`)

`application_checklists` — one per application.

| column | type | notes |
| --- | --- | --- |
| application_id | uuid pk, fk overseas_applications ON DELETE CASCADE | |
| template_id | uuid fk document_checklist_templates, null | null = counselor items only |
| template_version | int null | frozen at creation; CHECK `(template_id IS NULL) = (template_version IS NULL)` |
| gate_mode | varchar(10) | CHECK `block`/`warn`; copied from the template, else `warn` (AC5) |
| created_by_id | uuid fk users, null | |
| created_at / updated_at | timestamps | |

`application_checklist_items`

| column | type | notes |
| --- | --- | --- |
| id | uuid pk | |
| application_id | uuid fk application_checklists ON DELETE CASCADE, index | |
| template_item_id | uuid fk document_checklist_template_items ON DELETE SET NULL, null | null = counselor-added |
| position | int | unique `(application_id, position)` |
| document_type | varchar(80) | |
| label | varchar(80) null | |
| required | bool | |
| allowed_statuses | JSON list | copied; informational |
| notes | text null | |
| mark | varchar(20) null | CHECK `requested`/`not_required` |
| marked_by_id | uuid fk users null; marked_at timestamptz null | |
| created_by_id | uuid fk users null; created_at / updated_at | |

`application_checklist_item_documents` — `(item_id fk items ON DELETE CASCADE, document_id fk student_documents)` primary key, `linked_by_id`,
`created_at`.

`overseas_applications.documents_completed_on` DATE NULL (only if missing).

## 4. Status rules (`app/application_checklists.py`)

- Document rank (best first): `verified`, `approved`, `not_required` (complete) › `under_review`, `review` › `uploaded`, `pending`,
  `draft` › `requested` › `incomplete`, `reupload_required` › `expired`. Archived documents never count.
- Item status = `mark` if set; else the best linked current document's status; else `pending` (missing).
- Complete = status in {`verified`, `approved`, `not_required`}.
- Summary: `required_total`, `required_complete`, `optional_total`, `optional_complete`, `ready` (all required complete),
  `missing` (required items not complete: id, label, status).

Auto-link on creation: each item links the student's current documents (same `student_id`, or same `agent_student_id`) that are
unattached or attached to this application, whose `document_type` equals the item's type case-insensitively (an `Other` item also
matches its label).

## 5. API (router `app/api/application_checklists.py`, prefix `/workflows/overseas/applications`)

| method | path | roles | notes |
| --- | --- | --- | --- |
| GET | `/{id}/checklist` | counselor, overseas_admin, super_admin, agent (scope), overseas_student (own) | `{checklist: null|{…}, template: {id,name,version,gate_mode}|null, documents: […]}`; `template` and `documents` (linkable) for writers only |
| POST | `/{id}/checklist` | counselor, overseas_admin, super_admin | create from the resolved admission template (or empty); 201; 409 if it exists |
| POST | `/{id}/checklist/items` | writers | add `{document_type, label?, required, notes?}`; 201 |
| PATCH | `/{id}/checklist/items/{item_id}` | writers | `{mark?: requested|not_required|null}` (mark must be in `allowed_statuses`, else 422) |
| DELETE | `/{id}/checklist/items/{item_id}` | writers | counselor-added only (409 otherwise); 204 |
| PUT | `/{id}/checklist/items/{item_id}/documents/{document_id}` | writers | link (the student's current document, 422 otherwise); clears the mark; idempotent |
| DELETE | `/{id}/checklist/items/{item_id}/documents/{document_id}` | writers | unlink; 204 |

Every write: the offers routes' entry (role, `_assigned_application`, row lock, counselor re-check, closed 409, archived agency 409; on
hold allowed), then `sync_completion`, audit `overseas.application.checklist.*`, one commit. An item of another application → 404.

**Gate** — `ApplicationSubStatusChange` gains `override_reason` (≤ 1000, cleaned). When the target is `ready_for_submission` and the
application is not already there, `gate(db, app, override_reason)` (after the lock, before `change`):

- ensures the checklist (AC4); no checklist → pass.
- all required complete → pass.
- `block` → 409 `{"message": "…", "gate_mode": "block", "missing": [...]}`.
- `warn` without a reason → 409 `{"message": "…", "gate_mode": "warn", "missing": [...]}`; with a reason → pass and the history row's
  `reason` = `Override: <reason>`; audit carries `checklist_override`.

## 6. Web

- `components/ApplicationChecklistPanel.tsx` (counselor card toggle "Checklist" in `CounselorEvaluationPanel`; read-only on
  `AgentApplicationDetail`): summary line "8 of 10 required complete" + gate mode + completed-on date; items list with status badge,
  required/optional, linked document names (unlink), link select, mark buttons, remove for counselor items; add-item form. Loading,
  empty ("No checklist yet" + Create button naming the template or "without a template") and error states.
- `ApplicationSubStatusForm`: on a 409 whose detail has `missing`, show the list; when `gate_mode` is `warn` show an "Override reason"
  textarea and resend with `override_reason`.
- `lib/applicationChecklist.ts`: types and status labels (re-uses `lib/documentChecklists.ts` labels).

## 7. Security / review notes

- IDOR: every route resolves the application through `_assigned_application`; items and documents are checked against that application
  and its owner (student or agency record) — a document of another student is 422, an item of another application 404.
- Role escalation: agent and student routes are read-only; marks/links/items need counselor/admin. Agency sub-status route keeps its cap.
- Concurrency: writes hold the application row lock; positions are computed under it; link insert is `ON CONFLICT DO NOTHING`.
- Input: `extra=forbid`, free text cleaned (`clean_free_text`), type list for counselor items is `AgentUploadDocumentType`.
- No file URLs in checklist responses (document id, type, label, filename, status only).

## 8. Tests

`tests/test_ccrm_019_migration.py` (columns, checks, downgrade), `tests/test_ccrm_019_checklist.py` (create from template incl.
auto-link, version freeze, empty create, add/remove/mark/link/unlink, status derivation, Appendix B A-only, completion date set/clear,
replace moves links, expiry refresh, scope: other counselor 403, agent read-only, student own read, gate block 409 / warn needs reason /
warn override history reason / no template passes / agency route gated). Web: `ApplicationChecklistPanel.test.tsx`,
`ApplicationSubStatusForm` gate test, e2e `ccrm-019-application-checklist.spec.ts`.
