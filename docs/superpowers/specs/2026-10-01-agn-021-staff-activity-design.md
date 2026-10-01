# AGN-021 — View Staff Activity: Design

**Status:** approved in conversation, written for owner review (2026-10-01). **Branch:** `feature/agn-021-staff-activity` (from `origin/main` 6360dc0).
**Decision:** `DEC-SCOPE-045` (provisional number; A1–A5 below, recorded with the code). **Backlog:** `ENHANCEMENT_BACKLOG.md` §AGN-021 (added with the code).
**Builds on:** `AGN-001` (`DEC-SCOPE-038`), `AGN-002` (`DEC-SCOPE-040`), `AGN-004` (`DEC-SCOPE-042`), `AGN-003` (`DEC-SCOPE-044`).
**Amended 2026-10-01 after the final review (R4):** §5.1 log line, §6 error state and §6 edit line now describe the implemented behaviour.
**Evidence:** `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 Staff "View staff activity". The source's wording is not the approval; the owner's statement and answers are.
**Supersedes:** the earlier AGN-021 design (`2026-10-01-agn-021-staff-permission-matrix-design.md`, branch `feature/agn-021-staff-permission-matrix`) — that scope shipped as `AGN-003` (PR #33) before AGN-021 was built; the owner re-scoped AGN-021 to staff activity on 2026-10-01.
**Oriented with:** Graphify query + a read-only audit-trail inventory of `main` (2026-10-01); brainstorming (superpowers), in-session.

## 1. Intent

The owner's `AGN-021` statement (in-session, 2026-10-01): requirement **"View staff activity" (§2 Staff)**; acceptance criteria:
**a Staff member's actions appear within one page load; other orgs' users → 404.**

**Owner answers (in-session 2026-10-01, `EXPLICIT_APPROVAL`; recorded as `DEC-SCOPE-045`):**
- **A1 — What is activity.** Student-journey work only: student records created / edited / saved over a duplicate warning, a student
  account linked, an application created, a document uploaded, a document verified. Sign-ins, password and profile changes, messages,
  support tickets and lookup searches are not shown.
- **A2 — Viewers.** Only an active Master of the staff member's agency. Staff are refused (403); any other organisation's user → 404.
  Deactivated staff remain viewable (history is kept).
- **A3 — Detail.** Each line: time, a plain action label, and the subject the Master can already see (student name; application as
  student — university; document as type — student). For an edit, the names of the fields changed — never their values. Reviewer
  notes, emails and ids are never shown.
- **A4 — Freshness.** "Within one page load" = read from the audit log on every request with no cache, so an action is visible the
  next time the Master opens or refreshes the view. A Refresh button; no live push or polling.
- **A5 — Source.** The existing audit log (no new store, no new writes). Lifts "staff activity" out of `C-10`; **staff performance
  (KPIs) stays parked**.

## 2. Out of scope

Staff performance / KPIs / funnels (EVID-015 §8, CLIENT_QUESTIONS 7), activity of Masters, Staff viewing their own activity, exporting
activity, actions that are not audited today (reads, downloads, logout, failed sign-ins — no new audit writes), filters/search,
retention policy for `audit_logs` (open PRD item), live updates.

## 3. Approaches considered

- **A — read the existing audit log (chosen).** All seven actions are already written with the staff user as `user_id` (indexed);
  one read-only Master route filters by an allow-list. No migration, no writes, no drift between two stores.
- **B — a `staff_activity` table written per action.** Duplicates the audit log, six call sites change, empty history at release. Rejected.
- **C — reuse `GET /admin/audit`.** Not tenant-scoped, unpaginated, admin-only. Rejected.

## 4. Data used (no schema change)

`audit_logs`: `user_id` (indexed), `action` (indexed), `entity_type`, `entity_id`, `metadata_json`, `created_at`. Rows written today by a
staff user (verified on `main` 6360dc0):

| `action` | Written at | `entity_type` / `entity_id` | Metadata used |
|---|---|---|---|
| `agent_student.create` | `api/agent_students.py:97` | `agent_student` / record id | none (field names not shown for create) |
| `agent_student.update` | `api/agent_students.py:145` | `agent_student` / record id | `fields` (names) |
| `agent_student.duplicate_override` | `api/agent_students.py:99,147` | `agent_student` / record id | none |
| `agent.student_link` | `api/workflows.py:2363` | `agent_student` / link row id | none |
| `overseas.application.create` | `api/workflows.py:1804` | `overseas_application` / application id | none |
| `document.upload` | `api/workflows.py:2026` | `student_document` / document id | none |
| `document.verify` | `api/workflows.py:2066` (agent branch) | `student_document` / document id | `verification_status` only (`notes` never read out) |

The `user_id` index serves the per-staff filter; the per-staff row count is small, so no new index is needed (a composite
`(user_id, created_at)` index is a later optimisation if the table grows; noted in RAID, not built).

## 5. Backend

### 5.1 Route — `api/agent_team.py`

`GET /workflows/overseas/agent/team/staff/{member_id}/activity?limit=25&offset=0`

- `limit: int = Query(25, ge=1, le=100)`, `offset: int = Query(0, ge=0, le=10_000)` (the `school_analytics` `MAX_OFFSET` guard).
- `_require_master(user)` → Staff `403 MASTER_ONLY`; suspended/pending agency → the existing denial (403).
- `member = await find_staff_member(db, membership.org_id, member_id)` → `404 "Staff member not found"` for another agency's member,
  a Master's member id, or an unknown id (identical response; no disclosure).
- Read-only: no org lock, no user lock, no commit.
- `logger.info("agent_org_staff_activity_viewed", extra={"extra_fields": {"org_id", "actor_id", "member_id", "offset"}})` — ids only (the module's `_commit_staff_change` logging style).
- Returns `service.staff_activity_page(db, member, limit, offset)`.

### 5.2 Services — `services/agent_orgs.py` (lookup) and new `services/staff_activity.py` (the read)

- **`find_staff_member(db, org_id, member_id) -> AgentOrgMember`** (`agent_orgs.py`) — the existing `_staff_member` query (`id`,
  `org_id`, `role == 'staff'`) extracted, 404 on miss, no lock. `_staff_member` calls it, then locks the user as today (behaviour unchanged).
- `services/staff_activity.py` (one responsibility: reading a staff member's audited work; `agent_orgs.py` stays about membership):
- **`STAFF_ACTIVITY_ACTIONS`** — the seven actions of §4 (a tuple; the single allow-list); `MAX_ACTIVITY_OFFSET = 10_000`.
- **`staff_activity_page(db, member, limit, offset) -> dict`**:
  - `where = (AuditLog.user_id == member.user_id, AuditLog.action.in_(STAFF_ACTIVITY_ACTIONS))`
  - `total = count(where)`; `rows = select ... order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)`.
  - Subjects resolved for the page in at most three batched queries keyed by `entity_id` (rows whose `entity_id` is not a UUID are
    skipped safely):
    - `agent_student` ids → `AgentStudent` left-joined to `User` on `student_id`: name = `AgentStudent.full_name` or the linked user's
      `full_name`.
    - `overseas_application` ids → `OverseasApplication` joined to student `User` and `University`: `"<student> — <university>"`.
    - `student_document` ids → `StudentDocument` joined to `User`: `"<document_type> — <student>"`.
  - Missing entity → `subject = "No longer available"`.
  - Item: `{"id": row.id, "at": row.created_at, "action": row.action, "subject": str, "fields": list[str] | None}` where `fields` is
    `metadata_json["fields"]` (a list of strings, else `None`) for `agent_student.update` only, and for `document.verify` the action
    stays `document.verify` and `subject` is as above (staff can only verify — AGN-003 P6 — so no status is needed).
  - Returns `{"items": [...], "total": total, "limit": limit, "offset": offset}`.

The subjects are data the Master may already read: every entity a staff member can act on is inside the agency (AGN-004 G4 scope is a
subset of the Master's), and agency membership is permanent (`models.py` `AgentStudent` docstring), so no cross-tenant subject can
appear.

### 5.3 Errors and HTTP semantics

`GET` only; safe and idempotent. 200 page (possibly empty); 403 Staff / inactive agency; 404 member not in the caller's agency;
422 `limit`/`offset` out of range or `member_id` not a UUID (FastAPI). No 5xx path from data: non-UUID `entity_id`, missing entities,
non-list `fields` are handled.

## 6. Frontend (`apps/web`)

- **`lib/agentStaff.ts`:** `type StaffActivityItem = { id: string; at: string; action: string; subject: string; fields: string[] | null }`;
  `ACTIVITY_LABELS: Record<string, string>` — `agent_student.create` "Created a student record", `agent_student.update` "Edited a student
  record", `agent_student.duplicate_override` "Saved a student record despite a duplicate warning", `agent.student_link` "Linked a student
  account", `overseas.application.create` "Created an application", `document.upload` "Uploaded a document", `document.verify` "Verified a
  document"; unknown action → "Other activity".
- **`AgentStaffActivity`** (new component, `{ member: StaffMember }`): fetches `${STAFF_URL}/${member.id}/activity?limit=10&offset=…`
  (page size 10 inside a row), validates with `isPage`; renders an `<ol aria-label="Activity of <code>">` — each item: label, `subject`,
  for an edit " — <field names joined by ', ', with `_` replaced by spaces>" (names only, never values), and `<time dateTime={at}>{formatDate(at, true)}</time>`. States: loading ("Loading activity…",
  `role="status"`); empty ("No activity yet."); error (`role="alert"`: a 4xx response with a string `detail` shows that detail; anything else — 5xx, network failure, non-page body, non-string `detail` — shows "Unable to load activity."; and
  **Try again**); pager ("Showing a–b of N", Previous/Next disabled at the ends and while loading); **Refresh** reloads the current page.
  A request counter ignores a response that is older than the latest request (no stale overwrite).
  **Amended after browser QA (2026-10-01, `docs/quality/AGN-021_BROWSER_QA_2026-10-01.md`):** a 401 shows "Your session has expired."
  with a **Sign in again** link to `/overseas/login` and no retry (QA-03, the app's `LoadFailureAlert` convention); the error state offers
  one retry action, **Try again** — Refresh is hidden while an error shows (QA-01); while a newer page or a Refresh loads over the current
  list, "Updating activity…" (`role="status"`) shows and the list is dimmed (QA-02); on open, focus moves to the Activity heading
  (`tabIndex=-1`) rather than to the last button (QA-04).
- **`AgentStaffRow`:** a new mode `activity` and an **Activity** button beside Permissions (all statuses, including deactivated); the
  section has a **Close** button; focus returns to the Activity button on close (the row's existing `id("<action>")` focus pattern).
- **Accessibility / responsive:** native buttons; list semantics; `aria-busy` on the list while loading; no horizontal scroll at 320 px
  (text wraps, `overflow-wrap: anywhere` already on `.card` content — verified in browser QA).

## 7. Acceptance criteria → tests (written before the code)

| AC | Statement | Tests |
|---|---|---|
| AC01 | Each allow-listed action a Staff member performs through the real API appears in the Master's next activity request, newest first. | `test_agn_021_activity.py::test_staff_work_appears_on_the_next_request` |
| AC02 | Another agency's Master, a Master's own member id and an unknown id → 404 `"Staff member not found"`; Staff → 403; inactive agency → 403. | `test_agn_021_activity.py` |
| AC03 | Rows outside the allow-list (sign-in, profile/password change, link search, message) and another staff member's rows never appear. | `test_agn_021_activity.py` |
| AC04 | Subjects resolve for each entity type; a missing entity reads "No longer available"; reviewer notes, emails, field values and ids other than the row id are never in the response. | `test_agn_021_activity.py` |
| AC05 | Paging: `{items,total,limit,offset}`, stable order on equal timestamps (`id` tiebreak), `limit` 1–100 and `offset` 0–10000 else 422. | `test_agn_021_activity.py` |
| AC06 | Deactivated staff remain viewable. | `test_agn_021_activity.py` |
| AC07 | UI: Activity opens from the staff row; loading / empty / error + Try again / paging / Refresh; stale responses ignored; keyboard + focus return; 320 px. | `AgentStaffActivity.test.tsx`, `AgentStaffRow.test.tsx`, `agn-021-staff-activity.spec.ts` |

The owner's AC map: "appear within one page load" = AC01 (+ AC07 Refresh); "other orgs' users → 404" = AC02.

## 8. Security review

| Check | Finding / control |
|---|---|
| Authentication | Unchanged (cookie JWT, `get_current_user`). |
| Authorization | `_require_master` (Staff 403); tenant scope via `find_staff_member(org_id=membership.org_id)`; no org id in the path. |
| IDOR | `member_id` from another agency → 404 indistinguishable from unknown (AC02). Rows filtered by the member's own `user_id`. |
| Data minimisation | Allow-list of seven work actions; no notes, values, emails, recipients; subjects limited to what the Master can already see. |
| Input validation | `member_id: UUID`; bounded `limit`/`offset`; `entity_id` parsed defensively. |
| XSS | React text rendering only. |
| CSRF | Read-only `GET`; unchanged cookie policy (`SameSite=lax`, single CORS origin). |
| SQL injection | ORM, bound parameters; the allow-list is a server constant. |
| Sensitive logs | One info line with ids only. |
| Rate limiting | None added: Master-only, paginated, bounded offset. |
| Audit | Viewing is logged (operational), not audited — consistent with every other read in the app. |

## 9. Regression risks

| Risk | Mitigation |
|---|---|
| `_staff_member` refactor (used by edit/deactivate/reactivate/reset/permissions) | extraction only; lock behaviour unchanged; AGN-002/003 suites in the lite set |
| `AgentStaffRow` mode added | existing row tests keep passing; new cases added |
| Audit row shape changes in future | allow-list + defensive parsing; missing subject reads "No longer available" |

## 10. Documentation to update with the code

`PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-045` A1–A5; D13/S1/D1 parentheticals: staff activity decided, staff performance parked),
`ENHANCEMENT_BACKLOG.md` (§AGN-021; EVID-015 row), `CONFLICT_MATRIX.md` `C-10`, `RBAC_MATRIX.md` (Staff activity row: Master ✅, Staff ❌),
`API_CONTRACT.md` (the route), `SCREEN_CATALOG.md` + `screen_catalog.json` (SCR-AGT-007 Activity section), `ROLE_NAVIGATION.md` (no change
— same Team page; note only), `RTM.md` (AGN-021 row), `RAID.md` (audit-log retention open; possible composite index later). The old
permission-matrix spec/plan exist only on `feature/agn-021-staff-permission-matrix` (not merged; the owner decides whether to delete it).
