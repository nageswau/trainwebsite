# upc-010 — University visits + approval (design + plan)

**Status:** design written 2026-10-08. The owner's standing instruction for this session is "proceed with the recommended answers;
ask only if genuinely blocking". The item answers VS1–VS18 (§1), including Q-13, are **recommended defaults accepted under that
instruction** (`NEEDS_CONFIRMATION` as separate per-question approvals). They are registered that way in `DEC-SCOPE-126`.

**Branch:** `feature/upc-010`, cut from `origin/main` @ `215e3e2e` (after #157, upc-006).
**Backlog:** `docs/delivery/UNIVERSITY_PARTNERSHIP_CRM_BACKLOG.md` §4 upc-010 and U9.
**Dependencies:** upc-001 (`0103`, `DEC-SCOPE-118`) and upc-006 (`0108`, `DEC-SCOPE-123`) are merged on main. This was verified in code:
`PartnershipProfile.reporting_head_user_id`, `services/partnership_universities.py` and `UniversityContact`.
**Source:** `EVID-020` §8, lines 314–350. It contains "separate from normal meetings", 14 planning fields and the flow Planned → Approved →
Travel Booked → Visit Completed → Follow-up → Closed.
**Numbering:** migration `0111_university_visits`, `DEC-SCOPE-126`, API §12AT, RBAC §2.52. Drafted as `0109` / `DEC-SCOPE-124` / §12AR /
§2.50; renumbered on merging `main` @ `4043631f` (upc-004 took `0109` / 124 / §12AR / §2.50, rec-004 `0110` / 125 / §12AS / §2.51).
**Gate:** `APPROVAL_GATES.md` GATE-09.

## 1. Decisions (recommended defaults)

| # | Question | Answer |
|---|---|---|
| VS1 | One university or several per visit | **One.** A multi-university trip is several visits, and upc-011's calendar shows them together. The country is derived from the university. The city defaults to the university's city and can be edited |
| VS2 | Stored statuses | Exactly §8's six: `planned, approved, travel_booked, visit_completed, follow_up, closed`. A planned visit is a **draft**, **waiting for approval** (`submitted_at` set) or **returned** (`rejection_reason` set). The UI shows these as sub-labels |
| VS3 | Transitions | `submit` (draft/returned → waiting); `approve` / `reject` (waiting; reject needs a reason and returns the visit to an editable state); `book` (approved → travel_booked; needs a confirmed date); `complete` (travel_booked → visit_completed; on or after the confirmed date; needs a follow-up date); `follow-up` (visit_completed → follow_up); `close` (follow_up → closed) |
| VS4 | Q-13a: the head travels, or who approves | The approver is the **lead's reporting head** when the lead is a `partnership_manager`, that head is active, and the head is neither the creator nor a participant. **Otherwise any active `super_admin`** approves (U9 fallback). Nobody ever approves a visit they created, lead or join. A manager can never approve (AC1) |
| VS5 | Q-13b: can an approval be cancelled after booking | **No un-approving.** A visit that is called off at any stage before it is completed (planned, approved, travel_booked) is **closed early with a required reason**. It keeps the six statuses, and the history shows it was closed without a visit |
| VS6 | Who creates | `partnership_manager` (the lead is themselves) and `partnership_head` (the lead is themselves or an active direct report). The university must be active and in the caller's university edit scope (the upc-006 `can_edit_contacts` rule). `super_admin` reads every visit and approves as the fallback; it does not create |
| VS7 | Who reads | `partnership_manager` (with a profile), `partnership_head` and `super_admin` read **every** visit (the backlog's "a manager reads every university"). Every other role gets a 403. overseas_admin is not in U9 |
| VS8 | Who acts on a visit | The **lead or the creator** edits, submits, books, completes, starts the follow-up and closes. Any other caller gets a 403 |
| VS9 | What stays editable | The university never changes after create (plan a new visit). In draft or returned: every other field. While waiting: nothing (409 "waiting for approval"). Once approved or booked, the approved scope (university, city, purpose, lead, participants, proposed date, travel and hotel requirements) is frozen. Confirmed date, travel and hotel notes, agenda, expected outcome and meeting contacts stay editable. After completion: only the follow-up date, until the visit is closed. Closed: read-only |
| VS10 | Dates (IST) | The proposed date is required and is today or later whenever it is set. The confirmed date is optional and is today or later whenever it changes. `complete` before the confirmed date is a 422 (N1). The follow-up date is required on `complete` and is today or later |
| VS11 | Other EduSphere employees | Active `partnership_manager` / `partnership_head` users other than the lead, at most 10 (the people upc-011's calendar tracks). They come from `GET /partnership/visits/employee-options` |
| VS12 | Meeting contacts | upc-006 contacts **of the visit's university** (any other contact is a 422), at most 20. Deleting a contact removes it from visits (FK CASCADE): contacts are PII and their deletion wins |
| VS13 | Travel and hotel | `travel_required` / `hotel_required` booleans plus notes of at most 1000 characters each (U9: requirement flags + booking notes; no booking integration, no expenses) |
| VS14 | History | `university_visit_events` is append-only. Each row holds the action, from status, to status, actor, reason and time, for create, edit, submit, approve, reject, book, complete, follow-up and close. It is returned on the detail. Each write also adds an `AuditLog` row (ids, codes and field names only) |
| VS15 | Notifications | In-app only (`channels=[]`, the bdm-010 idiom). Submit notifies the approver (or every active super_admin on the fallback). Approve and reject notify the lead, and the creator when that is someone else |
| VS16 | Follow-up date | Stored on the visit. upc-020 (not built yet, and not a dependency) turns it into a follow-up task. AC3 "prompts for the follow-up date" means the Complete form requires it |
| VS17 | Codes | `VIS-000001` from `university_visit_code_seq` (the TRV idiom) |
| VS18 | Text limits | Purpose is required, at most 1000. Agenda and expected outcome are at most 2000 each. Travel and hotel notes are at most 1000. City is at most 120. A reject or close reason is required, at most 1000 |

## 2. Data model — migration `0111_university_visits`

- `university_visit_code_seq`.
- `university_visits`:
  - id, code String(20) unique, university_id FK RESTRICT, city String(120), purpose Text, lead_user_id FK users,
    created_by_user_id FK users;
  - proposed_date Date, confirmed_date Date null;
  - travel_required / hotel_required bool, travel_notes / hotel_notes Text null;
  - agenda Text null, expected_outcome Text null, follow_up_date Date null;
  - status String(16) CHECK (six values), submitted_at, rejection_reason Text null;
  - decided_by_user_id FK null, decided_at, close_reason Text null, created_at / updated_at.
  - Indexes: `ix_university_visits_university`, `ix_university_visits_lead`, `ix_university_visits_pending` (WHERE status='planned'
    AND submitted_at IS NOT NULL).
- `university_visit_participants` (visit_id FK CASCADE, user_id FK RESTRICT, PK both).
- `university_visit_contacts` (visit_id FK CASCADE, contact_id FK → university_contacts CASCADE, PK both).
- `university_visit_events`: id, visit_id FK CASCADE, action String(20), from_status/to_status String(16) null, actor_user_id FK,
  reason Text null, created_at. Index (visit_id, created_at).
- Downgrade refuses while any visit exists.

## 3. Backend

`services/university_visits.py` holds rules, scope and output only; it never commits. `api/university_visits.py` (prefix
`/partnership`) owns the transaction. One transition table drives both the enforcement and the `can_*` flags (the bdm_travel `RULES`
idiom).

| Route | Who | Notes |
|---|---|---|
| `GET /partnership/visits` | readers (VS7) | `{items,total,limit,offset}`; filters `status`, `university_id`, `mine` (lead, creator or participant); newest proposed date first |
| `GET /partnership/visits/approvals` | head / super_admin | Waiting visits this caller may approve (VS4), oldest submission first; other roles 403 |
| `GET /partnership/visits/university-options?q` | creators | Active universities in the caller's edit scope (`{items,total}` of id/name/code/city/country) |
| `GET /partnership/visits/lead-options?q` | creators | Manager: themselves. Head: themselves + active direct reports |
| `GET /partnership/visits/employee-options?q` | readers | Active partnership managers and heads (`full_name`, email) |
| `POST /partnership/visits` | creators | 201 `{visit}`, status planned (draft) |
| `GET /partnership/visits/{id}` | readers | `{visit}` with participants, contacts, events and `permissions` |
| `PATCH /partnership/visits/{id}` | lead/creator | Only the fields sent, per VS9; `extra="forbid"` |
| `POST /partnership/visits/{id}/submit\|book\|follow-up` | lead/creator | 409 outside the transition table |
| `POST /partnership/visits/{id}/complete` | lead/creator | body `{follow_up_date}` |
| `POST /partnership/visits/{id}/close` | lead/creator | body `{reason}`: required when closing early, optional from follow_up |
| `POST /partnership/visits/{id}/approve\|reject` | approver (VS4) | reject body `{reason}`. Manager → 403; a non-approver → 403; not waiting → 409 |

- **Every write**, in one transaction:
  - lock the visit row `FOR UPDATE`;
  - decide: approve also locks the lead's profile and head `FOR SHARE`, so a concurrent reassignment or deactivation is serialised;
  - change the visit, add the event row and the audit row, add the in-app notices;
  - commit once, then write a structured log (ids, action, status).
- Unknown visit → 404. A refusal is logged with ids only.
- **Validation (422):**
  - the university, lead, participant or contact must be valid;
  - dates follow VS10, and text limits follow VS18;
  - `extra="forbid"`.

## 4. Frontend

- `lib/visits.ts`: types, `VISIT_STATUSES` words, URLs, and the three option searches.
- Pages (all server components, PortalShell via `shellFor`):
  - `/partnership/visits`: list with a status filter, a "Mine" toggle and URL paging. "Plan a visit" is shown to managers and heads;
  - `/partnership/visits/new?university=<id>`: `VisitForm`;
  - `/partnership/visits/[id]`: facts, contacts, participants, history and `VisitActions`;
  - `/partnership/visits/[id]/edit`: `VisitForm` with the visit, sending changed fields only;
  - `/partnership/visits/approvals`: the approval queue for heads and super_admin.
- `VisitForm` (client):
  - fields: the university (SearchableSelect, or fixed when given), the lead (heads only), purpose, city, proposed and confirmed date,
    the travel and hotel flags with notes, other employees (multi-pick chips), meeting contacts (checkboxes loaded for the university),
    agenda and expected outcome;
  - 422 field errors, a double-submit guard, and the frozen fields disabled per VS9.
- `VisitActions` (client):
  - only the actions the `permissions` flags allow;
  - Reject and early Close open an inline reason form; Complete opens an inline follow-up date form (AC3);
  - a `role=status` success notice, `role=alert` errors, and `router.refresh()`.
- University page: a **Visits** section listing that university's visits (code, date, status, lead). It shows "Plan a visit" to a manager
  or head with `can_edit_contacts`.
- Navigation:
  - the manager menu's "University Visits" goes live;
  - the head nav gains "University Visits" and "Visit approvals";
  - the super admin nav gains "Partnership visit approvals".

## 5. Acceptance criteria

| AC | Statement | Proven by |
|---|---|---|
| AC1 | A manager cannot set Approved (approve → 403; no PATCH of status) | pytest; e2e |
| AC2 | Travel Booked only after Approved (book on planned → 409) | pytest; e2e |
| AC3 | Completing requires the follow-up date (missing → 422; the UI asks for it) | pytest; vitest; e2e |
| AC4 | The six §8 statuses, the flow enforced, every change in the history | pytest |
| AC5 | Approver = reporting head; super_admin only on fallback; the creator, lead or a participant never approves | pytest |
| P1 | A UK visit approved by the head | pytest; e2e |
| N1 | Visit Completed before the confirmed date → 422 | pytest |
| E1 | The head as the traveller → super_admin approves (Q-13) | pytest |
| R1 | Other roles 403; a contact of another university 422; an inactive or out-of-scope university 403/409; an unknown visit 404 | pytest |

## 6. Tasks (TDD, in order)

1. Migration, models and a parity/round-trip test (`test_upc_010_migration.py`).
2. Schemas, service and routes: create/read/options tests, then edit-rule tests, then the transition and approval tests, then the code
   (`test_upc_010_visits.py`).
3. Frontend: lib, `VisitForm`, `VisitActions`, the pages, the university page section, and nav, with vitest
   (`VisitActions.test.tsx`, `VisitForm.test.tsx`, nav test).
4. Playwright `upc-010-university-visits.spec.ts`.
5. Docs: DEC-SCOPE-126, API §12AT, RBAC §2.52, DATA_MODEL, SCREEN_CATALOG and the backlog status.

## 7. Regression set (lite)

`test_upc_006_*`, `test_upc_003_*`, `test_upc_001_*`, `test_bdm_010*` (the notify helper is shared), the upc-003/006 vitest files,
`navigation.partnership.test.ts`, and `upc-006-university-contacts.spec.ts`.

## 8. Engineering review notes (Phase 3)

- **API:**
  - The detail also returns `editable_fields` (empty for non-actors), so the edit form locks exactly what VS9 locks.
  - The detail's `permissions` are `can_edit, can_submit, can_decide, can_book, can_complete, can_follow_up, can_close`.
  - They are computed from the same transition table and actor rules that the routes enforce. The UI only hides actions; the API
    decides.
- **Security:**
  - Reads are role-gated (VS7).
  - Every write re-checks the lead/creator or the approver after `FOR UPDATE` (no TOCTOU).
  - The option endpoints return only what the caller may submit.
  - Contact PII stays with the partnership roles.
  - Logs and audit metadata hold no free text. Reasons live in `university_visit_events`, which only readers can see.
- **Frontend:**
  - Reuses `SearchableSelect`, the inline confirmation idiom, `.action-grid` and the data table.
  - Every form works from the keyboard, with visible labels and `aria-invalid` plus described-by errors.
  - On mobile the layout is a single column.
