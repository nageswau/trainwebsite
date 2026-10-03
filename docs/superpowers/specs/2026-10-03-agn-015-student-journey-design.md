# AGN-015 — Agent student journey and complete history (design)

**Decision:** `DEC-SCOPE-061` (owner, in-session 2026-10-03). **Branch:** `feature/agn-015-student-journey` from `main` @ `e1c2084`.
**Status:** design approved in-session (parts 1–2 explicitly; parts 3–4 accepted by the owner's instruction to proceed).

## 1. Requirement and evidence

- Owner statement (in-session, 2026-10-03): requirement **"Student Journey" (§4) and "View complete student history" (§2): Create →
  Counseling → Shortlist → Documents → Application → Offer → Deposit → Visa → Enrollment.** Acceptance: **every event from the source
  items appears once, in order, with its actor; the step tracker matches the stored data.**
- `EVID-015` (`Agent CRM Functionalities.md`, `DERIVED_BLUEPRINT`) §2 "View complete student history", §4 "Staff Login – Student
  Journey Only", §5 Steps 1–9. The source's wording is not the approval; §4's path omits Counseling, Shortlist and Deposit while §5
  includes them — the owner's nine-step list resolves this.
- `docs/delivery/AGENT_CRM_BACKLOG.md` `ang-015` (`DERIVED_BLUEPRINT`): proposed `/journey` + `/timeline`, "no database change".
  Overridden in one respect by the owner's answer Q1 (an additive index, §6).

## 2. Owner answers (in-session, 2026-10-03)

| # | Question | Answer |
|---|---|---|
| J1 | Events with no history table (counseling saves, reassignment, shortlist removals, deposit changes, visa moves) | Read them from `audit_logs`; add an index for per-entity reads |
| J2 | Tracker for several applications | Steps 1–4 once for the student; steps 5–9 one row per application |
| J3 | Step completion rules | The table in §4 |
| J4 | Actors outside the agency | Agency members by name; everyone else by a fixed role label |
| J5 | Extra event kinds | Assignment & archive, Tasks & follow-ups, Document downloads (not deposit checkout starts) |
| J6 | Order | Newest first, paginated |

## 3. Event catalogue — every event has exactly one source (J1, J5)

| Src | Rank | Table | Rows for this student | `kind` | Actor column |
|---|---|---|---|---|---|
| S1 | 1 | `agent_students` | the record | `student_created` | `agent_id` |
| S2 | 2 | `audit_logs` (`entity_type='agent_student'`, `entity_id`=record) | actions below | see map | `user_id` |
| S3 | 3 | `application_status_history` | the student's in-scope applications | `application_created` / `application_stage_changed` / `application_withdrawn` / `application_enrolled` / `application_updated` | `changed_by_id` |
| S4 | 4 | `audit_logs` (`overseas_application`, those ids) | actions below | see map | `user_id` (deposit paid: the payer) |
| S5 | 5 | `audit_logs` (`application_deposit`, deposits of those applications) | remit, refund | `deposit_remitted` / `deposit_refunded` | `user_id` |
| S6 | 6 | `audit_logs` (`visa_case`, visa cases of those applications) | counsellor create/update | `visa_started` / `visa_updated` | `user_id` |
| S7 | 7 | `document_events` | events of in-scope documents of the student, and of the student's in-scope requests | `document_<event>` (9 kinds; `cancelled` → `document_request_cancelled`) | `actor_user_id` |
| S8 | 8 | `student_documents` | in-scope documents of the student with **no** `uploaded` event (made before AGN-009) | `document_uploaded` | `uploaded_by_user_id` |

Audit action → `kind` (S2/S4/S5/S6). Any other action is not an event:

| Action | kind |
|---|---|
| `agent_student.update` | `student_updated` (fields) |
| `agent_student.duplicate_override` | `student_duplicate_override` |
| `agent_student.assign` | `student_assigned` |
| `agent_student.archive` / `.unarchive` | `student_archived` / `student_restored` |
| `agent_student.counseling` | `counseling_saved` (fields) |
| `agent_student.shortlist_add` / `_update` / `_remove` | `shortlist_added` / `shortlist_updated` (fields) / `shortlist_removed` |
| `agent_student.task_add` / `_update` / `_complete` / `_cancel` | `task_added` / `task_updated` (fields) / `task_completed` / `task_cancelled` |
| `overseas.application.update` | `application_edited` (fields = metadata keys or `fields`) |
| `overseas.application.enrollment_update` | `enrollment_updated` (fields) |
| `overseas.application.visa_start` / `visa_update` / `visa_advance` / `visa_decision` | `visa_started` / `visa_updated` (fields) / `visa_stage_changed` (from/to stage) / `visa_decision_recorded` |
| `overseas.application.deposit` / `deposit_paid` | `deposit_set` (fields) / `deposit_paid` |
| `overseas.deposit.remit` / `.refund` | `deposit_remitted` / `deposit_refunded` |
| `visa.create` / `visa.update` | `visa_started` / `visa_updated` (fields = payload keys) |

**Excluded on purpose** (another source holds the event, or it is out of scope): `agent_student.create`, `agent.student_link`,
`overseas.application.create/advance/withdraw/offer/enroll` (S3), `document.*`, `document_request.*` (S7), `deposit_checkout` (J5),
`agent.commission_*` (Master-only, DEC-SCOPE-051), `overseas.deposit.unlinked_payment`, university-database actions.

S3 classification: `from_status IS NULL` → created; `to_status='withdrawn'` → withdrawn; `to_status='enrolled' AND from_status IS
DISTINCT FROM 'enrolled'` → enrolled; `from_status <> to_status` → stage changed; else → `application_updated` (offer recorded or
next action — the history note says which).

**Order:** `occurred_at DESC, rank DESC, seq DESC, id DESC` (`seq` is `document_events.seq`, else 0). Rows written in one transaction
share `now()`; the rank makes their order stable and documented.

**Item contents:** `kind`, subject (`application`: id + university name; `document`: id + document type), `from_status`/`to_status`
(stage changes, document status changes, visa stage changes), `fields` (names only, strings only), `notes` (status-history and
document-event notes only — the same viewers already read them in Application detail and Document history). Never field values,
amounts, the visa decision, emails, phones, file keys or raw audit metadata.

**Actor (J4):** the user's full name when the user is a member of the viewer's organisation (`org_member_ids`); otherwise
`EduSphere counsellor` (counselor), `EduSphere admin` (overseas_admin, super_admin, admin roles), `Student`, `Parent`, `University`
(university_rep), `Agency user` (an agent outside this agency — not expected), `System` (no user).

## 4. Step tracker (J2, J3)

Student steps: `create`, `counseling`, `shortlist`, `documents`. Application steps: `application`, `offer`, `deposit`, `visa`,
`enrollment`. States: `not_started | in_progress | done | not_required | refunded | refused | withdrawn`.

| Step | not_started | in_progress | done | other |
|---|---|---|---|---|
| create | — | — | always | — |
| counseling | no row | row, `completed` false | `completed` true | — |
| shortlist | 0 entries | — | ≥ 1 entry | — |
| documents | no in-scope document and no open request | otherwise | ≥ 1 document, all `verified`, no open request | — |
| application | — | `submitted_on` null | `submitted_on` set | — |
| offer | stage before `offer` and no `offer_type` | — | `offer_type` set or stage index ≥ `offer` | — |
| deposit | no deposit row | `pending` | `paid`, `remitted` | `not_required`, `refunded` |
| visa | no case | case, no decision or decision ≠ approved/refused/withdrawn | decision `approved` | `refused`, `withdrawn` (visa decision) |
| enrollment | — / not enrolled | — | stage `enrolled` | — |

A **withdrawn** application: every step not `done` (and not `not_required`/`refunded`/`refused`) shows `withdrawn`. Applications
are listed oldest first (`created_at, id`); `university` is the university name.

## 5. API (both new, read-only; existing responses unchanged)

Prefix `/api/v1/workflows/overseas/agent/crm/students/{student_id}`.

```
GET …/journey  → 200
{"student": {"id", "full_name", "status"},
 "steps": [{"key", "state"}] ×4,
 "applications": [{"id", "university", "intake", "status", "steps": [{"key", "state"}] ×5}]}

GET …/timeline?limit=20&offset=0   limit 1–100 (default 20), offset 0–10 000
→ 200 {"items": [{"id", "at", "kind", "actor", "application", "document", "from_status", "to_status", "fields", "notes"}],
       "total", "limit", "offset"}
```

`id` is `"<source>:<row id>"` (unique across sources). Every key is always present (null when not applicable).

Errors: 401 (no session, `get_current_user`); 403 (not an approved overseas agent, `_gate`); **404 "Student not found"** for an
unknown id, another agency's student, or a staff member's unassigned student (indistinguishable); 422 malformed UUID / limit /
offset. Archived students are readable.

## 6. Data, authorization, transactions, security

- **Scope (IDOR):** student via `agent_students.load_scoped`; applications `application_scope(user)` ∧ the existing owner filter
  (record id, or the linked login) ∧ `school_student_id IS NULL`; documents `document_scope(user)` ∧ `student_clause(record)`;
  requests `request_scope(user)` ∧ `agent_student_id = record`. Audit rows only by entity ids drawn from those scoped sets — never
  from the request. Deposits and visa cases only of scoped applications.
- **Role:** Master and Staff run the same code; Staff are narrowed by `DEC-SCOPE-042` G4 inside the scopes. No new permission.
- **SQL:** SQLAlchemy Core `union_all`, bound parameters only. Audit `entity_id` is a string column: compared with `str(uuid)`.
- **Transactions:** no locks, no writes, no commit. The timeline page and `total` are one statement (`count(*) OVER ()`), so they
  agree. The journey is ~5 reads under READ COMMITTED; a write between them can show a mixed state the next load corrects (accepted).
- **Migration `0067_audit_entity_index`:** `CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id, created_at)`;
  no rows read or written; downgrade drops it. Built non-concurrently (repo convention) — a brief write lock on `audit_logs`.
- **XSS/CSRF:** text rendered as React text nodes; GET-only under the existing SameSite=Lax httpOnly cookie.
- **Logs:** `agent_student_journey_viewed` / `agent_student_timeline_viewed` with org, actor, student ids and offset only.
- **No new audit action, no rate limit** (as every agent GET; residual unchanged).

## 7. Frontend

- `lib/agentJourney.ts`: URLs, types, `STEP_LABELS`, `STATE_LABELS`, `KIND_LABELS`, `kindLabel()` (humanised fallback), type guards.
- `components/AgentStudentJourney.tsx`: fetches `/journey` on mount and whenever the student's `updated_at` changes; renders
  `<section aria-labelledby>` with an `h5` "Journey"; student steps in `<ol aria-label="Student steps">`; one `<ol aria-label="Steps
  for {university}">` per application with a caption (university · intake · stage label). Each step is an `<li>` with the step name and
  its state **as text** plus an `aria-hidden` glyph (✓ • –); the first not-done step of each list has `aria-current="step"`.
  Flex-wrap rows; one column under 640px; no horizontal overflow at 320px. States: loading (`role="status"` "Loading journey…"),
  error (inline `form-error` + Try again; 401 → Sign in again), empty applications ("No applications yet.").
- `components/AgentStudentTimeline.tsx`: hidden until the user presses **Show history** (`aria-expanded`), so opening a student
  costs one extra request, not two. Then the AGN-021 `AgentStaffActivity` pattern: newest-request-wins guard, `<ol aria-label="Student
  history">`, Loading / Updating / "No history yet." / error + Try again / 401 sign-in, Previous / Next with "Showing a–b of n",
  Refresh. Row: label · subject · from → to · fields · actor · `<time>`; notes in `.history-note`.
- Mounted in `AgentStudentDetailPanel` when `editing === "none"`: Journey after the record details' Edit button, history after
  Tasks. No new region/heading named Counseling, Visa, Enrollment, Offer, Deposit or Tasks (existing tests find those by name).
- CSS: a few `.jny-*` rules in `app/globals.css` from existing tokens (`--line`, `--muted`, `--ink`, `--blue`).
- No new dependency.

## 8. Regression risks and mitigations

| Risk | Mitigation |
|---|---|
| `test_agn_017_migration` pins head `0065` | update the pinned head constant to `0066` (test intent unchanged: one head) |
| Exact key sets (`test_agn_008_read`, `test_agn_006`, `test_agn_013`) | no existing response changes |
| Web tests stub `fetch` for any URL (`AgentStudentsPanel`, `AgentStudentCounselingCard`) | journey component tolerates any body (type guard → error state); update those tests' fetch routing only where a new GET consumes a queued response |
| Name-based region/heading lookups in e2e | unique names "Journey", "Student history" |
| Audit index build lock | additive, small table today; noted |
| Pre-AGN-009 documents | S8 fallback upload event; their earlier reviews are not reconstructable (recorded limitation) |

## 9. Tests (lite, AGN-015 only)

API `tests/test_agn_015_journey.py`, `tests/test_agn_015_timeline.py`, `tests/test_agn_015_security.py`,
`tests/test_agn_015_migration.py` (+ `agn015_helpers.py`): tracker rules per step and per state; a full journey's events each
appear once in order with actor; exclusions (no duplicate for create/advance/offer/enroll/upload); outside actor labels; pagination
and total; 404 for other agency / unassigned staff / unknown; 422 for bad limit; archived readable; staff sees only scoped
applications; migration up/down. Web: `tests/lib/agentJourney.test.ts`, `tests/components/AgentStudentJourney.test.tsx`,
`tests/components/AgentStudentTimeline.test.tsx`, plus the touched existing panel tests. E2E `tests/e2e/agn-015-student-journey.spec.ts`
is written for the owner's full run (browser validation is a separate step).
