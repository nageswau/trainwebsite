# tel-019 BDM meeting requests — Implementation Plan

> **For agentic workers:** executed natively (superpowers:executing-plans) in the `tel-019` worktree. Steps use `- [ ]`.

**Goal:** a telecaller files a BDM meeting request; a BDM of the matching type accepts it into exactly one `bdm_appointments` row or
declines it with a reason; the telecaller sees the status.

**Architecture:** one new table + service + router (`bdm_meeting_requests`). Accept reuses bdm-006's booking rules through
`book_appointment()`, extracted from `api/bdm_appointments.create_appointment` with no behaviour change, inside the accept transaction
(lock order request → organization → appointment). Frontend reuses `BdmAppointmentForm` for the accept step.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + PostgreSQL; Next.js (app router) + React + vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-07-tel-019-bdm-meeting-requests-design.md`

## Global Constraints

- Migration `0093_bdm_meeting_requests`, `down_revision = "0091_lead_appointments"` (re-chain to `0092` if tel-010 merges first).
- `DEC-SCOPE-097`, API §12S, RBAC §2.25.
- Out of scope = 404; role that may not act = 403; every write one transaction with audit in it; logs/audit carry no PII or free text.
- Codes `MRQ-000001`; statuses `pending` / `accepted` / `declined`; corporate → college BDMs.
- Times shown in IST; datetime-local inputs use `istInputToIso` / `isoToIstInput` from `lib/bdmAppointments`.
- Tests run in docker (`api-test`, `web-test`) with Windows-form mount paths; lite backend set only.

## Review Focus

1. Two BDMs accept the same pool request at once → exactly one appointment; the loser gets 404 (row taken) — test with two sessions sequentially after lock + a concurrency test via two connections.
2. Accept refused by a bdm-006 rule (overlap 409, archived 422) → the request stays `pending` and no appointment exists (transaction rolled back).
3. A request accepted after its proposed time → accept with a future start succeeds; a past start → 422 "Choose a time in the future".
4. A named request for a BDM of another type → 422 at create; a named request is invisible to other BDMs of the same type (404).
5. Telecaller form with a blank email / whitespace-only purpose → email stored NULL; purpose 422 "Purpose is required".

---

### Task 1: Model + migration 0093

**Files:** Modify `apps/api/app/models.py` (after `BdmAppointmentEvent`); Create `apps/api/alembic/versions/0093_bdm_meeting_requests.py`;
Test `apps/api/tests/test_tel_019_migration.py`.

**Produces:** `BdmMeetingRequest` model; constants `BDM_MEETING_REQUEST_TYPES = ("college","agent","school","corporate")`,
`BDM_MEETING_REQUEST_STATUSES = ("pending","accepted","declined")`, `BDM_MEETING_REQUEST_BDM_TYPE = {"college":"college","agent":"agent","school":"school","corporate":"college"}`,
`BDM_MEETING_REQUEST_CODE_SEQ`.

- [ ] Write migration test (tel-016 pattern): chain + single head; upgrade creates table/CHECKs/indexes; CHECK rejects `accepted` without appointment; round trip in a throwaway DB; downgrade refuses with a row present.
- [ ] Run → fails (module missing).
- [ ] Add model + migration (guarded upgrade, `CREATE SEQUENCE IF NOT EXISTS`, frozen copies of the CHECK lists asserted equal to the model's).
- [ ] Run → passes. Commit `feat(tel-019): bdm_meeting_requests table (0093)`.

### Task 2: Extract `book_appointment` from bdm-006 create (no behaviour change)

**Files:** Modify `apps/api/app/api/bdm_appointments.py:124-165`.

**Produces:** `async def book_appointment(db, user, payload: BdmAppointmentCreate) -> BdmAppointment` — everything the route did before
`db.commit()` (profile gate, org lock, assigned/archived, contact, type, future, trip, overlap, insert, event, audits). The route becomes
`appt = await book_appointment(...); await db.commit(); log; envelope`.

- [ ] Run `tests/test_bdm_006_appointments.py tests/test_bdm_006_scope.py tests/test_bdm_011*` → green baseline.
- [ ] Refactor; rerun → still green. Commit `refactor(bdm-006): book_appointment shared by create and tel-019 accept`.

### Task 3: Schemas + service + telecaller routes

**Files:** Modify `apps/api/app/schemas.py` (end); Create `apps/api/app/services/bdm_meeting_requests.py`, `apps/api/app/api/bdm_meeting_requests.py`;
Modify `apps/api/app/main.py` (register `telecaller_router`, `router`); Create `apps/api/tests/tel019_helpers.py`, `apps/api/tests/test_tel_019_requests.py`.

**Produces:**
- `MeetingRequestCreate` (extra forbid): `request_type`, `bdm_user_id: UUID|None`, `organization_name`, `person_name`, `contact_phone`, `contact_email`, `proposed_at: BdmApptStart`, `mode: Literal[APPOINTMENT_MODES]`, `location`, `purpose`, `remarks`.
- `MeetingRequestDecline`: `reason: BdmApptReason`.
- service: `TYPE_LABEL`, `scope_filters(db, user) -> list` (403 for other roles), `load_scoped(db, user, id, lock=False)`, `active_bdms(db) -> dict[str, list]`, `require_target(db, bdm_user_id, bdm_type)`, `next_code(db)`, `outs(db, user, rows) -> list[dict]`, `audit(db, user, action, req, meta)`.
- routes: `GET/POST /telecaller/meeting-requests`, `GET /telecaller/meeting-requests/options`.

Tests: pool create 201 (code, `bdm_type` college for corporate, audit has no PII); named create; target of the wrong type 422; inactive target 422; past / >366 days 422; blank purpose 422; bad phone 422; blank email → null; non-telecaller 403 (manager, bdm); options lists BDMs per type; list shows own only.

- [ ] Write tests → fail → implement → pass → commit.

### Task 4: BDM routes — list, detail, accept, decline

**Files:** `apps/api/app/api/bdm_meeting_requests.py`; Test `apps/api/tests/test_tel_019_bdm.py`.

**Consumes:** `book_appointment` (Task 2), service (Task 3).

Tests: AC1 corporate pool request visible to a college BDM, 404 for agent/school BDMs; named request 404 for another college BDM; manager sees team + pool, not another team's named one; super_admin all; telecaller 403 on `/bdm/...`; AC2 accept → one appointment, request accepted with taker + appointment, audits; second accept 409; another BDM accepting a taken pool request 404; negative: agent BDM accepts college request 404; edge: proposed time past + future start 200; overlap 409 leaves request pending and no extra appointment; manager accept 403; AC3 decline without reason 422; decline → final, then accept 409; permissions flags.

- [ ] Write tests → fail → implement → pass → commit.

### Task 5: Frontend — telecaller

**Files:** Create `apps/web/lib/meetingRequests.ts`, `apps/web/components/MeetingRequestForm.tsx`, `apps/web/components/MeetingRequestList.tsx`,
`apps/web/app/telecaller/meeting-requests/page.tsx`, `apps/web/app/telecaller/meeting-requests/new/page.tsx`; Modify `apps/web/lib/navigation.ts` (TELECALLER_NAV "BDM requests");
Test `apps/web/tests/components/MeetingRequestForm.test.tsx`.

Tests: BDM choices follow the type (corporate shows college BDMs); submit posts the IST time as ISO; a 422 shows the message and keeps the entry; server error keeps the entry.

- [ ] Write tests → fail → implement → pass → commit.

### Task 6: Frontend — BDM + manager

**Files:** Create `apps/web/app/bdm/meeting-requests/page.tsx`, `apps/web/app/bdm/meeting-requests/[id]/page.tsx`, `apps/web/components/MeetingRequestDecide.tsx`,
`apps/web/app/bdm/manager/meeting-requests/page.tsx`; Modify `apps/web/components/BdmAppointmentForm.tsx` (optional `request` prop in create mode: prefill + submit URL), `apps/web/app/bdm/my-day/page.tsx` (card), `apps/web/lib/navigation.ts` (BDM + manager "Requests");
Test `apps/web/tests/components/MeetingRequestDecide.test.tsx`.

Tests: accept form prefilled (type, start, purpose) and posts to the accept URL; decline requires a reason; no accept/decline when permissions are false; existing `BdmAppointmentForm` tests still pass.

- [ ] Write tests → fail → implement → pass → commit.

### Task 7: E2E + docs

**Files:** Create `apps/web/e2e/tel-019-meeting-requests.spec.ts`; Modify `docs/decisions/PRODUCT_DECISION_REGISTER.md` (DEC-SCOPE-097), `docs/architecture/API_CONTRACT.md` (§12S), `docs/architecture/RBAC_MATRIX.md` (§2.25), `docs/delivery/TELECALLER_CRM_BACKLOG.md` (tel-019 status line).

- [ ] E2E: telecaller files a school request → school BDM sees it on My Day → accepts → telecaller sees Accepted with the appointment code; a corporate request declined with a reason shows it to the telecaller.
- [ ] Docs; commit.
