# nehn-033 — Overseas student Overview / Progress page (design)

- **Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-033` (§18 L497-517, §17 L470, action 14).
- **Decision:** `DEC-SCOPE-332` (this design). The 10-stage mapping is the backlog's own proposal, marked `NEEDS_CONFIRMATION`
  there (FEEDBACK_TRACKER OD-10). The user told this session to go ahead with the recommended answers, so the mapping below is
  **a Claude call, not client approval**. It stays open for the client to confirm.
- **Dependencies (all merged on main):** nehn-001 (offer predicate), ccrm-014 (sub-status), ccrm-015 (outcomes), ccrm-017 (journey),
  ccrm-019 (admission checklist), ccrm-020 (document requests), ccrm-023/025 (offers, decision), ccrm-026 (visa lifecycle).

## Intent

A student should not have to visit several tabs to understand where their application is. One read-only page shows:
the current stage of each application, the documents they still need to upload (each linking to upload), and the next
required actions.

## Goals / non-goals

- Goal: an overseas student sees a step tracker per application, their missing documents and their next actions on `/overseas/student/progress`.
- Non-goal: no new stored stage, no migration, no change to the stage list. The page is derived on every read (backlog: "avoid that if the mapping suffices").
- Non-goal: no counselor/agent reuse in this item. The counselor already has ccrm-017's journey and the agency has AGN-015.
- Anti-goal: never leak internal data. That covers the visa refusal reason, outcome reasons/owners, file keys, fees and counselor notes.

## Stage mapping (9 steps; `NEEDS_CONFIRMATION`, OD-10)

The client's two offer stages ("Conditional offer" / "Unconditional offer") are **one step** whose label names the offer type.
The data keeps only the current `offer_type`, so a two-step tracker would have to guess whether a conditional offer came first.

| # | key | label (as shown) | is the current step when |
|---|-----|------------------|---------------------------|
| 1 | `submitted` | Application submitted | `enquiry` (or any legacy value) |
| 2 | `under_review` | Application under review | `eligibility_evaluation` |
| 3 | `university_selected` | University selected | `university_selection`, no `submitted_on` |
| 4 | `offer_processing` | Offer processing | `university_selection` + `submitted_on`; legacy `university_review` |
| 5 | `offer` | Offer → "Conditional offer" / "Unconditional offer" / "Pathway offer" / "Offer received" (by `offer_type`) | `offer` |
| 6 | `documentation` | Documentation pending / Documentation completed | `visa_documentation`/`status_tracking` with no visa case, or a case at `not_started`/`preparing` |
| 7 | `visa_processing` | Visa processing | case at `appointment_booked`/`submitted`/`additional_info_requested`/`decision_pending` |
| 8 | `visa_decision` | Visa decision → "Visa decision: Approved / Rejected / Withdrawn" | case has a `decision` |
| 9 | `final` | Final outcome → "Final outcome: Enrolled / Visa rejected / Withdrawn / Rejected / Offer declined / Did not arrive / Cancelled" | `enrolled`, or the application is closed |

- Step states: `done`, `current`, `upcoming`, `not_reached` (closed before getting there), `stopped` (a closing step: visa refused/withdrawn, final closed).
  The UI always shows the state as text, never colour alone (the AGN-015 / ccrm-017 rule).
- "Documentation completed": the visa case's checklist has every item's newest document on this application `verified` (the existing `agent_visa.checklist_status`).
- Closed applications: `status = withdrawn`, or a terminal ccrm-015 outcome. A closed application is shown at the step it reached, the steps after it read `not_reached`, and the final step reads `stopped` with the outcome.
  For `status = withdrawn` the step reached comes from the `from_status` of the newest `ApplicationStatusHistory` row that moved it to `withdrawn` (no history row: step 1).
- A visa decision of `refused` (AC2) gives step 8 "Visa decision: Rejected" (`stopped`) and step 9 "Final outcome: Visa rejected" (`stopped`). The application's headline is "Visa decision: Rejected".
  A visa decision of `withdrawn` works the same way. `approved` gives step 8 `done`, and step 9 is current until the application is `enrolled`.
- Non-terminal outcomes `on_hold` / `deferred` add a note ("On hold" / "Deferred").

## Missing documents (student-level, live applications only)

These are the documents the student must upload. Ones already uploaded and awaiting review are not listed.
1. Open ccrm-020 document requests to the student, with their due date and overdue flag.
2. Required ccrm-019 admission-checklist items whose status is `missing`, `incomplete`, `reupload_required` or `expired`, skipping items that already have an open request (the request is listed instead).
3. Visa checklist items whose newest document on the application is `not_uploaded`, `incomplete`, `reupload_required` or `expired`.

Each item gives a name, its source (Document request / Admission checklist / Visa checklist), the university and application code,
a status label, an optional due date, and `upload_url = /overseas/student/documents`. That page holds the request upload form and the document upload form.

## Next actions (in order)

1. "Upload N missing document(s)" when there are any (links to Documents).
2. Per live application:
   - the counselor's free-text `next_action` when set;
   - an active offer that is still `considering`: "Tell your counselor whether you accept the offer from {university}" plus " by {deadline}" when one is set;
   - a deposit record that is required and `pending`: "Pay the deposit for {university}" plus " by {due date}";
   - an open visa case at `not_started`/`preparing` with no appointment date: "Book your visa appointment ({university})";
   - a visa case at `additional_info_requested`: "Send the additional information the visa office asked for ({university})".

## API

`GET /api/v1/overseas/me/progress`, for `overseas_student` only. Any other role gets 403 and no session gets 401. Nothing is read
from the request, so there is no IDOR surface: every query is keyed on `user.id`. The route is read-only: no lock, no write, no audit (it is a read of the student's own data).

```json
{
  "applications": [{
    "id": "uuid", "application_code": "EDU-…", "university": "…", "intake": "…",
    "current": {"key": "offer", "label": "Conditional offer"}, "closed": false, "note": null,
    "steps": [{"key": "submitted", "label": "Application submitted", "state": "done"}, "…"]
  }],
  "missing_documents": [{"name": "Passport", "source": "Visa checklist", "application_code": "…", "university": "…", "status_label": "Not uploaded", "due_date": null, "overdue": false, "upload_url": "/overseas/student/documents"}],
  "next_actions": [{"text": "…", "href": "/overseas/student/documents" | null}]
}
```

Applications are ordered live first, then by `updated_at` descending. The queries are one per source (applications, visa cases, offers, deposits, withdrawn history, requests, checklists),
never one per application.

## Code layout

- `apps/api/app/overseas_progress.py`: pure mapper (`steps(...)`, labels). No model imports, unit-tested directly.
- `apps/api/app/services/overseas_progress.py`: reads the sources and builds the response. It reuses `application_checklists._summary`-style item statuses, `agent_visa.checklist_status` and `student_document_requests.page`.
- `apps/api/app/api/overseas_progress.py`: `me_router` (`/overseas/me`), registered in `main.py`.
- `apps/api/app/services/portal.py`: `progress` section header (title + subtitle, no table).
- Web: nav entry "Progress" right after Dashboard. `PortalPage` mounts `<OverseasProgress/>` (a server component that uses `serverApi`). `lib/overseasProgress.ts` holds the types. The `jny-*` stepper CSS is reused.
- Error state: an inline `role="status"` card ("Your progress could not be loaded. Refresh the page to try again.") as `MyStudentProfile` has. Empty state: "You have no applications yet." with a link to Applications.

## Acceptance criteria

1. A student at `offer` with `offer_type=conditional` sees "Conditional offer" as the current step, and steps 1-4 are done.
2. A visa decision of `refused` shows "Visa decision: Rejected", and the final outcome reads "Final outcome: Visa rejected".
3. Missing documents are listed, and each links to upload (`/overseas/student/documents`).
4. Only the student's own applications appear. Counselors, agents and admins get 403.
5. The page works at desktop, tablet and phone width with no horizontal scroll, and the state is shown as text.
