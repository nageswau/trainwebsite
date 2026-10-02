# AGN-009 Agent Documents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (owner chose in-session execution with TDD,
> 2026-10-02). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** agency Masters and Staff upload, download, review, replace, request and trace documents for their students — with
or without a login — under the §6 matrix, without changing the student/counselor document flows.

**Architecture:** extend `student_documents` (nullable `student_id` + `agent_student_id`), add `document_requests` and
`document_events`; a new router `api/agent_documents.py` + service `services/agent_documents.py` in AGN-008's shape; the
existing verify/download/upload routes keep their contracts and gain events. Web: a client `AgentDocumentsSection` routed from
`PortalPage`, sidebar children, four small components.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, Pydantic 2, pytest + httpx; Next.js 15, React 19, vitest +
Testing Library, Playwright. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-009-agent-documents-design.md` (decision `DEC-SCOPE-051`).

## Global Constraints

- Tests are run for real; lite sets only (the owner runs full regression, browser validation and the Codex review).
- `API_TEST <paths>` = `docker compose -p agn009 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v
  "C:/Users/kunam/Documents/project/trainwebsite/.claude/worktrees/enh-09/apps/api:/app" api-test sh -c "alembic upgrade head
  && python -m pytest -q -p no:cacheprovider <paths>"`. `WEB_TEST <paths>` = `cd apps/web && npx vitest run <paths>`.
- No change to response shapes or status codes of existing routes; counselor/admin/student branches change only by additive
  event rows.
- Logs carry ids only. Audit metadata: ids, types, statuses.
- Document types exactly: `Passport`, `Academic certificates`, `Transcripts`, `English test`, `CV`, `SOP`, `LOR`,
  `Financial documents`, `Other`.
- Throttles: 60 uploads+replaces and 60 requests per agency per 10 minutes.
- No completion claim.

## Review Focus

1. **An agency-only document (`student_id` NULL) on every existing reader** — counselor portal, student portal, staff
   activity, visa checklist, verify/download routes. Expected: skipped or handled, never a crash. Pinned in Task 2
   (`test_existing_readers_survive_an_agency_only_document`).
2. **A linked student shared by two agencies.** Agency B must not see agency A's agency-record documents through the new
   routes. Pinned in Task 6 (`test_other_agency_sees_nothing`).
3. **Commit failure after the file was stored.** Expected: no row, no event, the stored object deleted. Pinned in Task 3
   (`test_failed_commit_removes_the_stored_file`).
4. **Two uploads fulfilling one request concurrently.** Expected: one 201, one 409; the request fulfilled once. Pinned in
   Task 4 (`test_concurrent_fulfilment_has_one_winner`).
5. **Staff rejecting without a reason.** Expected 403 (Staff cannot reject), not 422. Pinned in Task 5
   (`test_staff_reject_without_reason_is_403`).

---

### Task 1: Migration 0058 and models

**Files:** Create `apps/api/alembic/versions/0058_agent_documents.py`; modify `apps/api/app/models.py` (`StudentDocument`,
new `DocumentRequest`, `DocumentEvent`); test `apps/api/tests/test_agn_009_migration.py`.

**Produces:** `StudentDocument.agent_student_id|document_label|uploaded_by_user_id|fulfils_request_id`;
`DocumentRequest(id, agent_student_id, document_type, document_label, note, status, requested_by_user_id, closed_by_user_id,
closed_at)`; `DocumentEvent(id, seq, document_id, request_id, event, actor_user_id, from_status, to_status, notes, file_key,
created_at)`.

- [ ] Test: revision chains after `0057_agent_applications`, single head; model columns nullable as specified;
  `fulfils_request_id` unique; tables/indexes/CHECKs exist in the shared DB; an insert with both owners NULL fails the CHECK; a
  throwaway DB round trip (upgrade → downgrade → upgrade) keeps existing rows; downgrade refuses while an agency-only document
  exists.
- [ ] Run → FAIL (no module/columns). Implement migration (guarded adds) + models. Run → PASS. Commit.

### Task 2: Scope helper and existing routes survive NULL `student_id`

**Files:** Create `apps/api/app/services/agent_documents.py` (`document_scope(user) -> list[ColumnElement]`,
`add_event(db, *, event, actor, document=None, request=None, from_status=None, to_status=None, notes=None, file_key=None)`);
modify `apps/api/app/api/workflows.py` (agent review/download scope via `document_scope`; `db.get(User, None)` guards; events on
upload/verify/download; `document.download` audit); test `apps/api/tests/test_agn_009_existing_routes.py`.

- [ ] Tests: agency-only document — Master downloads (200), staff assigned (200), staff not assigned (403), other agency (403);
  counselor/student/admin downloads write a `downloaded` event + `document.download` audit and return the same shape; old JSON
  upload writes an `uploaded` event and `uploaded_by_user_id`; counselor verify writes an event, response unchanged, reason still
  optional for counselors; `test_existing_readers_survive_an_agency_only_document` (counselor + student + agent portal
  documents, staff activity, visa checklist render 200).
- [ ] Run → FAIL. Implement. Run new + `test_ovs_005_documents.py test_agn_003_verify.py test_visa_001_checklist.py` → PASS.
  Commit.

### Task 3: Upload and replace (`api/agent_documents.py`)

**Files:** Create `apps/api/app/api/agent_documents.py`; register in `apps/api/app/main.py`; schemas in
`apps/api/app/schemas.py` (`DOCUMENT_TYPES`, `AgentDocumentType`); service functions `store_upload(file) -> tuple[key,
content_type, data_len, filename]`, `upload_wait_seconds(db, user)`, `item(row...) -> dict`; test
`apps/api/tests/test_agn_009_upload.py`.

- [ ] Tests: Master uploads a PDF for a no-login record → 201 `pending`, `agent_student_id` set, `student_id` NULL, no
  `file_url` in body, key under `agent-documents/`, `uploaded` event, `document.upload` audit; linked record → `student_id` set
  too; staff for an assigned record → 201, unassigned → 404; archived → 409; type not in list → 422; `Other` without label →
  422; label with a fixed type → 422; empty file → 422; text file → 415; oversize → 413; JPEG metadata stripped; application of
  another student → 422, out of scope → 404; throttle → 429 + `Retry-After`; `test_failed_commit_removes_the_stored_file`.
  Replace: pending/rejected → 200, status `pending`, reviewer fields cleared, `replaced` event with old key and from_status, old
  object still present; counselor-decided → 409; legacy (no `agent_student_id`) → 409; archived → 409; out of scope → 404.
- [ ] Run → FAIL. Implement. Run → PASS. Commit.

### Task 4: Requests and list views

**Files:** modify `api/agent_documents.py`, `services/agent_documents.py`, `schemas.py` (`AgentDocumentRequestCreate`); test
`apps/api/tests/test_agn_009_requests.py`.

- [ ] Tests: create (Master and Staff) → 201 `open` + `requested` event + audit; duplicate open same type+label → 409; archived →
  409; out of scope → 404; `Other` label rules → 422; cancel → `cancelled` + event, cancel again → 409; list `status=open` shows
  it until fulfilled (AC4); upload with `request_id` → request `fulfilled`, `fulfilled` event, gone from open list; upload with a
  request of another student → 422; closed request → 409; `test_concurrent_fulfilment_has_one_winner`. Lists: `view=pending`
  only pending, `view=uploaded` all; `student` filter; staff see assigned only; pages shape.
- [ ] Run → FAIL. Implement. Run → PASS. Commit.

### Task 5: Agent review rules and history

**Files:** modify `apps/api/app/api/workflows.py` (`_agent_document_review`), `api/agent_documents.py` (history); test
`apps/api/tests/test_agn_009_review_history.py`.

- [ ] Tests: Master reject without notes → 422 (AC3), blank notes → 422, with notes → 200 + `rejected` event; `changes_required`
  same; verify without notes → 200; `test_staff_reject_without_reason_is_403`; staff without Verify → 403; agency-only document
  reviewed by Master → 200 (scope fix); history: upload → download → reject → replace → verify listed in that order with actors
  (AC5); a fulfilled request's `requested` event precedes `uploaded`; out of scope → 404.
- [ ] Run → FAIL. Implement. Run new + `test_agn_003_verify.py test_agn_003_matrix.py` → PASS. Commit.

### Task 6: Security / IDOR sweep

**Files:** test `apps/api/tests/test_agn_009_security.py`.

- [ ] Tests: for every id-taking route (download, history, replace, cancel, review), another agency → 404/403 and staff's
  unassigned student → 404/403; `test_other_agency_sees_nothing` (shared linked student: agency B's list excludes agency A's
  agency-record documents); Super Admin and non-agent roles → 403 on new routes; logs carry no filename (caplog).
- [ ] Run; fix any failure in the owning code. Commit.

### Task 7: Web — client library, nav, section routing

**Files:** create `apps/web/lib/agentDocuments.ts` (types, URLs, `DOCUMENT_TYPES`, `parseView`, `statusLabel`); modify
`apps/web/lib/navigation.ts` (Documents children), `apps/web/components/PortalPage.tsx` (route to `AgentDocumentsSection`),
`apps/web/components/WorkflowPanel.tsx` (no generic upload/review for agents on documents); tests
`apps/web/tests/lib/agentDocuments.test.ts`, update `tests/lib/navigation.agent.test.ts`,
`tests/components/WorkflowPanel.agentDocuments.test.tsx`.

- [ ] RED → GREEN → commit.

### Task 8: Web — components

**Files:** create `AgentDocumentsSection.tsx`, `AgentDocumentsPanel.tsx` (list + card actions), `AgentDocumentUploadForm.tsx`,
`AgentDocumentRequestForm.tsx`, `AgentDocumentRequestsPanel.tsx`, `AgentDocumentHistory.tsx`; tests in
`apps/web/tests/components/AgentDocuments*.test.tsx`.

- [ ] Tests: loading/empty/error+Retry states; review form shows three outcomes for Master, Verify only for staff with
  permission, none without; reason required client-side for reject/changes; 409 reloads; upload form "Other" label toggles,
  sends multipart; request cancel; history renders ordered list; accessible names on buttons.
- [ ] RED → GREEN → typecheck/lint on changed files → commit.

### Task 9: E2E spec, docs

**Files:** create `apps/web/tests/e2e/agn-009-agent-documents.spec.ts` (written; run by the owner); update `docs/quality/RTM.md`,
`docs/architecture/API_CONTRACT.md`, `DATA_MODEL.md`, `RBAC_MATRIX.md`, `docs/delivery/RAID.md` (files gap),
`docs/delivery/ENHANCEMENT_BACKLOG.md`, `AGENT_CRM_BACKLOG.md` status table.

- [ ] Write; commit. Report status as "implemented, pending browser validation and Codex review".
