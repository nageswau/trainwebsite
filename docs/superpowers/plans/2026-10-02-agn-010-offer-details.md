# AGN-010 Offer details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent Master/Staff record a conditional or unconditional offer (date, deadline, conditions, offer letter) on an
agency application; the stage syncs to `offer`; changes are in the status history; the agent Offers counts are correct.

**Architecture:** Four nullable columns on `overseas_applications`; one `PUT …/{id}/offer` in the existing AGN-008 router using
its lock → refuse → validate → history → audit → single-commit pattern; offer rules live in `services/agent_applications.py`;
the web adds one display block and one form inside `AgentApplicationDetail`.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic 2, Alembic, PostgreSQL 16; Next.js + TypeScript; pytest; vitest; Playwright.

**Spec:** `docs/superpowers/specs/2026-10-02-agn-010-offer-details-design.md`

## Global Constraints

- Error body is FastAPI `{"detail": …}`; 422 messages exactly as in spec §4.1/§4.4.
- No new dependency. No change to `offer_letter_url`, `/status`, the list, counselor/university/admin routes.
- Every write: org lock → application row lock → checks → history + audit → one commit → `_log`. Nothing written on a no-op.
- Audit and logs carry ids and field names only — never the conditions text, never a storage key.
- Lite tests only in this session (the owner runs the full suites separately). Backend command (own compose project):

```bash
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn010 --profile ci run --rm \
  -v "$PWD/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <files>"
```

  Web: `cd apps/web && npx vitest run <files>`, `npx tsc --noEmit`, `npx eslint <files>`.

## Review Focus

1. A document re-attached or deleted after it was linked → the offer shows *Not attached* (FK `SET NULL`), never a 500.
2. A legacy free-text status (`offer_received`) → recording an offer normalises the stage to `offer` (index −1 rule).
3. PATCH clearing `offer_deadline` (null) while an offer exists → allowed (the deadline is optional).
4. An `enrolled` application → the offer can still be corrected; the stage never moves backwards.
5. Unknown JSON key or `offer_type: "maybe"` → 422, nothing written.

Each is pinned by a test in Task 2 or Task 3.

---

### Task 1: Columns, constraints, migration

**Files:** Modify `apps/api/app/models.py` (OverseasApplication); Create `apps/api/alembic/versions/0060_agent_offer_details.py`;
Test `apps/api/tests/test_agn_010_migration.py`.

**Produces:** `OverseasApplication.offer_type: str|None`, `offer_date: date|None`, `offer_conditions: str|None`,
`offer_document_id: UUID|None`.

- [ ] RED: test that the four columns exist (inspector), that `offer_type='maybe'` and `offer_type` without `offer_date` raise
  `IntegrityError`, and that deleting the linked `StudentDocument` sets `offer_document_id` to NULL. Run → fails (no columns).
- [ ] GREEN: model columns (FK `use_alter=True`, `name="fk_overseas_applications_offer_document_id"`, `ondelete="SET NULL"`,
  two `CheckConstraint`s in `__table_args__`); migration with guarded adds (0057 idiom), downgrade refusing while
  `offer_type IS NOT NULL`. Run → passes.
- [ ] Commit `feat(agn-010): offer columns and migration 0060`.

### Task 2: Offer schema, rules and the PUT route

**Files:** Modify `apps/api/app/schemas.py` (`AgentApplicationOffer`), `apps/api/app/services/agent_applications.py`
(`OFFER_COUNTED_STATUSES`, `counts_as_offer`, `offer_view`, `offer_letters`, `offer_change_notes`, `check_offer_deadline`,
`detail` additions), `apps/api/app/api/agent_applications.py` (`record_offer`, PATCH cross-check);
Test `apps/api/tests/agn010_helpers.py`, `test_agn_010_offer.py`, `test_agn_010_security.py`.

**Interfaces produced:**
- `AgentApplicationOffer(offer_type: Literal["conditional","unconditional"], offer_date: date, offer_deadline: date|None,
  conditions: str|None, offer_document_id: UUID|None, expected_status: str|None)`
- `check_offer_deadline(offer_date: date|None, offer_deadline: date|None) -> None` (raises 422 `OFFER_DEADLINE_BEFORE`)
- `offer_change_notes(app, new: dict) -> str|None` (None = no change)
- `counts_as_offer(app) -> bool`

- [ ] RED (`test_agn_010_offer.py`): AC01 (PUT + PATCH, same day OK, PATCH null deadline OK), AC02, AC03, AC04 (pre-offer,
  legacy `offer_received`, `visa_documentation`, `enrolled`, withdrawn, archived, stale), AC07, detail shape (`offer`,
  `offer_letters` without `file_url`), audit `overseas.application.offer` metadata without conditions. Run → 404/405 failures.
- [ ] RED (`test_agn_010_security.py`): AC06 — other agency 404, unassigned staff 404, other application's document 422,
  other agency's document 404, wrong type 422, super_admin refused, unknown key 422.
- [ ] GREEN: schema validators (`model_validator` for deadline/conditions; `PydanticCustomError` messages); service helpers;
  route following `change_status`; PATCH calls `check_offer_deadline(item.offer_date, resulting deadline)`. Run → passes.
- [ ] REFACTOR: share the offer field comparison between notes and no-op detection; rerun.
- [ ] Commit `feat(agn-010): record an offer on an agency application`.

### Task 3: Offer letter document type

**Files:** Modify `apps/api/app/schemas.py` (`AgentUploadDocumentType`), `apps/api/app/api/agent_documents.py` (upload);
Test `apps/api/tests/test_agn_010_documents.py`.

- [ ] RED: upload `Offer letter` with an application → 201; without → 422 `Choose the application this offer letter belongs to`;
  document request with `Offer letter` → 422. Run → first fails (422 Literal).
- [ ] GREEN: `AgentUploadDocumentType = Literal[*AgentDocumentType.__args__, "Offer letter"]`; upload uses it and checks the
  application. Run → passes. Commit `feat(agn-010): Offer letter upload type`.

### Task 4: Offers counts on the agent pages

**Files:** Modify `apps/api/app/services/portal.py` (`_agent` dashboard + reports); Test `apps/api/tests/test_agn_010_counts.py`.

- [ ] RED: fixture of offer, visa_documentation, enrolled, legacy offer_received, withdrawn-with-offer, withdrawn-without,
  enquiry; Master dashboard `Offers` and Reports `Offers` == 5; staff sees only their students. Run → fails.
- [ ] GREEN: `sum(1 for a, _, _ in applications if counts_as_offer(a))` in both places; dashboard metric after Applications.
  Run → passes. Commit `fix(agn-010): agent Offers count by stage or offer record`.

### Task 5: Activity, permission matrix rows

**Files:** Modify `apps/api/app/services/staff_activity.py`, `apps/web/lib/agentStaff.ts`, `apps/api/tests/test_agn_003_matrix.py`
(`BOTH_ALLOWED` row for the offer PUT). Test: the matrix row + `apps/web/tests/lib/agentApplications.test.ts` label case.

- [ ] RED → GREEN → commit `feat(agn-010): offer in staff activity and the permission matrix`.

### Task 6: Web — offer block and form

**Files:** Create `apps/web/components/AgentApplicationOffer.tsx`, `apps/web/components/AgentApplicationOfferForm.tsx`;
Modify `apps/web/components/AgentApplicationDetail.tsx`, `apps/web/lib/agentApplications.ts` (types `AgentOffer`,
`OfferLetterOption`, `offerUrl(id)`), `apps/web/lib/agentDocuments.ts` (`UPLOAD_DOCUMENT_TYPES`),
`apps/web/components/AgentDocumentUploadForm.tsx`, `apps/web/components/AgentDocumentTypeField.tsx` (type list prop);
Test `apps/web/tests/components/AgentApplicationOffer.test.tsx`, update `AgentDocuments.test.tsx` if the type list is asserted.

- [ ] RED: empty state + Record offer; conditions only for conditional; client 422-equivalents; PUT body; 422 keeps input and
  focuses the notice; success notice; read-only hides buttons; offer letter Download link; no-options hint.
- [ ] GREEN → `npx vitest run` on the new/changed tests, `npx tsc --noEmit`, `npx eslint` on changed files.
- [ ] Commit `feat(agn-010): offer form on the agent application`.

### Task 7: E2E spec and docs

**Files:** Create `apps/web/tests/e2e/agn-010-offer-details.spec.ts` (written, run in the owner's full session / browser QA);
Modify `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-054`), `docs/architecture/API_CONTRACT.md`,
`DATA_MODEL.md`, `RBAC_MATRIX.md`, `docs/quality/RTM.md`, `docs/ux/SCREEN_CATALOG.md`, `docs/delivery/RAID.md`
(non-agent stale offer counts → ang-018), `docs/delivery/AGENT_CRM_BACKLOG.md` status, `docs/delivery/ENHANCEMENT_BACKLOG.md`.

- [ ] Commit `docs+test(agn-010): E2E spec, DEC-SCOPE-054, contract/data/RBAC/RTM/RAID entries`.
