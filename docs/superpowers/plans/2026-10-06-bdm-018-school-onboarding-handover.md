# bdm-018 School Onboarding Handover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a School BDM hand a signed school over to Overseas Admin, who creates or links the real School, and show the live post-onboarding stages on the organization.

**Architecture:** A new `bdm_onboarding_requests` table and a unique `bdm_organizations.school_id` link. A service module `services/bdm_onboarding.py` holds the rules, live evidence and output. Two thin routers carry it: BDM (`api/bdm_onboarding.py`, `/bdm` prefix) and admin (same file, `/overseas-admin` prefix). The SCH-003 `create_school` route optionally resolves a request in its own transaction. The School's BDM is derived from the link (H1).

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL; Next.js (client components), vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-06-bdm-018-school-onboarding-handover-design.md`

## Global Constraints

- Migration `0083_bdm_onboarding`, down_revision `0082_bdm_assignment_history`. Additive only, and every create is guarded (the 0079 style). The downgrade refuses while requests or links exist.
- Decision `DEC-SCOPE-083`; owner answers H1–H4 and defaults H5–H11 (spec §1).
- Routes own commits; services never commit. Audit rows ride the same transaction. Logs carry ids and keys only, never names, notes or reasons.
- Out of scope = 404 (`load_scoped`); wrong role on admin routes = 403 "Overseas Admin role required".
- Notices are in-app only: `workflows._notify_user(..., channels=[])`.
- No change to `_provision_school`, `PATCH /overseas-admin/schools/{id}`, the stage-move route, the pipeline view, or `/school/*`.
- Tests run in the `bdm018` compose project: `docker compose -p bdm018 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm -v "$(pwd)/apps/api:/app" api-test python -m pytest -q <files>`.

## Review Focus

1. Two admins resolving one request at once → exactly one wins; the other gets 409 `request_resolved` and no orphan School exists (Task 4 test).
2. A create with a request whose organization was meanwhile linked by another request → 409 before any School or Coordinator is written (Task 4 test).
3. A BDM requesting while the MoU is Expired → 422 (Task 2 test).
4. A School linked elsewhere, offered to Link → 409 `school_linked` (Task 3 test).
5. A manager or BDM calling `/school/*` or the admin queue → 403, and a School coordinator never sees `linked_bdm` (Task 3/5 tests).

---

### Task 1: Model + migration

**Files:** Modify `apps/api/app/models.py` (BdmOrganization gets `school_id`; new `BdmOnboardingRequest` + `BDM_ONBOARDING_CHECKS`). Create `apps/api/alembic/versions/0083_bdm_onboarding.py`. Test: `apps/api/tests/test_bdm_018_migration.py`.

**Produces:** `BdmOnboardingRequest(id, organization_id, kind, status, note, requested_by_user_id, resolved_by_user_id, resolved_at, resolution, school_id, reject_reason, created_at, updated_at)`; `BdmOrganization.school_id`; `BDM_ONBOARDING_CHECKS: dict[str,str]`.

- [ ] Test: the migration's `CHECKS` equal `models.BDM_ONBOARDING_CHECKS`; the table, the indexes `uq_bdm_onboarding_requests_pending` / `ix_bdm_onboarding_requests_status` and the unique constraint `uq_bdm_organizations_school` exist; inserting a second pending row for one organization raises IntegrityError; the CHECKs refuse `completed` without `school_id` and `rejected` without a reason. Run it and confirm it fails.
- [ ] Implement the model:

```python
BDM_ONBOARDING_STATUSES = ("pending", "completed", "rejected")
BDM_ONBOARDING_CHECKS = {  # migration 0083 repeats these strings; test_bdm_018_migration asserts they stay identical
    "ck_bdm_onboarding_requests_kind": "kind IN ('school')",
    "ck_bdm_onboarding_requests_status": _in_list("status", BDM_ONBOARDING_STATUSES),
    "ck_bdm_onboarding_requests_resolution": "resolution IS NULL OR resolution IN ('created', 'linked')",
    "ck_bdm_onboarding_requests_resolved": "(status = 'pending') = (resolved_at IS NULL)",
    "ck_bdm_onboarding_requests_completed": "status <> 'completed' OR (school_id IS NOT NULL AND resolution IS NOT NULL)",
    "ck_bdm_onboarding_requests_rejected": "status <> 'rejected' OR reject_reason IS NOT NULL",
}
```

Add the migration (the guarded create for the table; `add_column` + `create_unique_constraint` for `school_id` only if the column is missing; the downgrade refuses on any request row or any non-null `school_id`). Apply it with `alembic upgrade head` in the compose project.
- [ ] Run the test and confirm it passes. Run `alembic heads` to confirm one head. Commit.

### Task 2: BDM request route + organization output

**Files:** Create `apps/api/app/services/bdm_onboarding.py` and `apps/api/app/api/bdm_onboarding.py` (register both routers in `app/main.py` where `bdm_mous` is). Modify `services/bdm_organizations.organization_out` (`onboarding` key) and `schemas.py` (`BdmOnboardingRequestIn`, `BdmOrgOnboardingOut`, `BdmOrganizationOut.onboarding`). Test: `tests/test_bdm_018_request.py`, helpers `tests/bdm018_helpers.py`.

**Produces:**
- `svc.check_request(db, user, org) -> None` (raises in spec §5.1 order)
- `svc.latest_request(db, org_id) -> BdmOnboardingRequest | None`
- `async svc.org_onboarding_out(db, user, org) -> dict | None`
- `svc.REQUEST_PENDING`, `ALREADY_LINKED`, `REQUEST_RESOLVED`, `SCHOOL_LINKED` (409 detail dicts), `MOU_NOT_SIGNED` (str)
- helpers `school_world(client, db)` → bdm-005 `world("school")` plus a signed MoU, and `request(client, org, **body)`

- [ ] Tests (failing first):
  - 201 for the owner with a Signed MoU; the response's `organization.onboarding` shows the request pending and `can_request` false; an audit row `bdm_organization.onboarding_requested` exists; every active overseas_admin gets one Notification with action_url `/overseas/admin/schools`.
  - 422 with no MoU, with a `proposal_sent` MoU, and with an Expired one (valid_until in the past); 201 with an Active one.
  - 409 `request_pending` on a second request; 409 `organization_lost`; 409 when archived.
  - 403 for a peer BDM and for the manager; 404 for another type's BDM; 422 for an agent organization.
  - `onboarding` is null on college and agent organizations.
- [ ] Implement it. `check_request` uses `bdm_mous.load_current` + `effective_status(…, today()) in ("signed", "active")`. On IntegrityError from the pending index, roll back and return 409. Overseas admins come from `select(User).where(User.role == "overseas_admin", User.active)`.
- [ ] Run until green. Commit.

### Task 3: Admin queue, reject, link

**Files:** `services/bdm_onboarding.py`, `api/bdm_onboarding.py`, schemas (`BdmOnboardingItem`, `BdmOnboardingPage`, `BdmOnboardingRejectIn`, `BdmOnboardingLinkIn`). Test: `tests/test_bdm_018_admin.py`.

**Produces:** `async svc.lock_pending(db, request_id) -> tuple[BdmOnboardingRequest, BdmOrganization]` (locks organization → request, raises 404 / 409 `request_resolved` / 409 `already_linked`); `svc.complete(db, user, req, org, school, resolution)`; `async svc.item_out(db, req) -> dict`; `async svc.queue_page(db, status, limit, offset)`.

- [ ] Tests:
  - The queue lists a pending request with the prefill: organization fields, primary contact, MoU reference and signed date, requested_by, assigned_bdm. `status=rejected` filters; pending is ordered oldest first.
  - 403 for bdm, bdm_manager, it_admin, school_coordinator; 401 anonymous.
  - Reject: 200 with the reason stored and the BDM notified (the notice body has the reason); 409 `request_resolved` on a repeat; 422 on an empty reason; the organization's `can_request` is true again afterwards.
  - Link: 200 links the organization and completes the request (resolution `linked`); 422 for an unknown code; 409 `school_linked` when the School is linked to another organization; 409 `request_resolved` on a resolved request; audit `bdm_onboarding_request.linked`.
  - Pin: a BDM gets 403 on `GET /api/v1/school/students`.
- [ ] Implement and run until green. Commit.

### Task 4: Create the School from a request (atomic)

**Files:** `api/admin.py` `create_school`, `schemas.SchoolCreate` (`bdm_onboarding_request_id: UUID | None = None`). Test: `tests/test_bdm_018_create.py`.

- [ ] Tests:
  - A create with the request id → 201. The organization's `school_id` equals the new School, the request is completed with resolution `created`, and the BDM is notified "School onboarded".
  - A resolved request → 409, and no School exists with that name.
  - The organization was linked meanwhile → 409, with no School and no Coordinator.
  - A coordinator email clash → 409, and the request stays pending (rollback).
  - Two concurrent creates on one request (asyncio.gather over two clients) → one 201 and one 409, and exactly one School with that name.
  - A create without the field is unchanged (the existing SCH-003 tests still pass).
- [ ] Implement it in `create_school`. When `payload.bdm_onboarding_request_id` is set, call `req, org = await svc.lock_pending(db, id)` before `_provision_school`, then `svc.complete(db, user, req, org, school, "created")` before the commit. `_provision_school` must not receive the new field: build its payload with `payload.model_copy(update={"bdm_onboarding_request_id": None})`, or have the function ignore it, since it reads named attributes only.
- [ ] Run these tests plus `test_sch_003*`, `test_enh_009*`, `test_enh_029*`, `test_enh_023*`. Commit.

### Task 5: `SchoolOut.linked_bdm` + live stages

**Files:** `admin._school_outs_batch`, `schemas.SchoolOut`, `services/bdm_pipeline.py` (`live_status` async with evidence; `pipeline_out(org, live=None)`), `organization_out`. Test: `tests/test_bdm_018_live.py`, `tests/test_bdm_018_school_out.py`.

**Produces:** `async live_status(db, org) -> dict[str, bool] | None`; `pipeline_out(org, live: dict | None = None)`.

- [ ] Tests:
  - With a pending request: Signed is `done`, School Onboarding is `current`, the rest are `upcoming`.
  - Once linked: School Onboarding is `done` and Users Created is `current`.
  - Add a teacher, a student and a parent link → Users Created is `done`.
  - A completed guidance session → Career Guidance is `done`, while a `scheduled` one doesn't count.
  - A completed psychometric record; a portfolio entry; a bridged application → each of those steps is `done`.
  - Without a request or link the steps stay `awaiting_handover`, so the bdm-004 tests are unchanged.
  - `SchoolOut.linked_bdm` = {full_name, active, organization_code} from the list, lookup and PATCH routes; null when not linked.
- [ ] Implement it, rerun the bdm-004 and bdm-005 suites, and commit.

### Task 6: Frontend — BDM onboarding card

**Files:** Create `apps/web/lib/bdmOnboarding.ts` and `apps/web/components/BdmOrganizationOnboarding.tsx`. Modify `lib/bdmOrganizations.ts` (`Organization.onboarding`) and `components/BdmOrganizationDetail.tsx` (render the card below the MoU card; reload the organization on any MoU change). Test: `apps/web/tests/components/BdmOrganizationOnboarding.test.tsx`.

- [ ] Tests for the four states (linked, pending, rejected with a reason and "Request again", none with or without `can_request`). Submit posts `{note}`, shows "Onboarding requested.", and the parent gets the new organization. A 409 or 422 message is shown in role=alert. The button is disabled while busy. The manager view (`canRequest=false`) has no button.
- [ ] Implement with `sendRequest` from `lib/apiErrors`, matching the BdmOrganizationMou card markup (`action-card wide`, `h3`).
- [ ] Run vitest on the file plus `BdmOrganizationDetail*`. Commit.

### Task 7: Frontend — admin queue + School panels

**Files:** Create `components/AdminSchoolOnboardingRequests.tsx`. Modify `AdminSchoolCreatePanel.tsx` (render the queue; prefill via a `key` remount; send `bdm_onboarding_request_id`; drop the Edusphere BDM input) and `AdminSchoolEditPanel.tsx` (show the linked BDM and the read-only legacy note; remove `edusphere_bdm` from `FIELDS`). Tests: `tests/components/AdminSchoolOnboardingRequests.test.tsx`, plus updates to the `AdminSchoolCreatePanel` and `AdminSchoolEditPanel` tests.

- [ ] Tests:
  - The queue covers loading, empty ("No onboarding requests waiting."), error and items.
  - "Use for new school" calls `onUse(item)`.
  - Reject needs a reason and posts it; Link posts `{school_code}`; each removes the item and announces the outcome.
  - The create panel, after `onUse`, prefills name and coordinator, the POST body carries the request id, and a "Creating for ORG-…" banner shows with a "Clear" control.
  - The create panel has no `edusphere_bdm` input.
  - The edit panel shows "Linked BDM", and a save never sends `edusphere_bdm`.
- [ ] Implement, run vitest, and commit.

### Task 8: E2E, docs

**Files:** `apps/web/tests/e2e/bdm-018-school-handover.spec.ts` (follow the bdm-005 e2e setup); `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-083); `docs/delivery/BDM_CRM_BACKLOG.md` (status); `docs/architecture/DATA_MODEL.md`; and the API contract doc, if bdm-005 updated one.

- [ ] Playwright: the BDM requests → the admin uses the request and creates the School → the BDM's organization shows Linked and the pipeline step "School Onboarding" done.
- [ ] Docs. Commit.
