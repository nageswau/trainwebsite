# itc-030: IT counselor dashboard and workspace (design)

**Source:** `docs/delivery/IT_COUNSELOR_CRM_BACKLOG.md` `itc-030` (PDF §8 IT Counselor dashboard, §11 Counselor workspace, §12 AC10),
plus Appendix B ("Pending HR actions"). The source is `UNVERIFIED`. This spec is Claude's build reading of it, so every call marked
*Claude's call* is `NEEDS_CONFIRMATION`.
**Dependencies (all merged):** itc-003 (#counselor link), itc-010 (counseling), itc-011 (one-step conversion), itc-013 (fee account),
itc-023 (at-risk flags, #425), itc-027 (HR review tasks, #428).
**Decision:** `DEC-SCOPE-367`. No migration. API §12JM (additive). RBAC §2.267 (no new grant). Sibling itc-022 holds 365/§2.265, and 366
is left for itc-017.

## 1. Intent

The IT counselor's dashboard today shows 2 counts and the 5 latest leads (`portal._it_counselor`). The PDF asks for one place where the
counselor sees their whole book of work. It covers leads, follow-ups, the counseling pipeline, conversions, enrolled students, fees,
training risk and HR, filtered by course, batch, date range and status. Each widget's figure must equal its own list (AC1), and the
filters must apply to every widget (AC2). The IT Admin gets the same board across all counselors, with an owner filter.

**Non-goals:** no new table, no stored figures, no new write path. Conversion stays itc-011's flow on the lead page. The workspace
links to it and does not duplicate it.

## 2. API: `GET /api/v1/counselor/it/dashboard`

Query parameters (all optional): `program` (course id), `batch` (batch id), `from`, `to` (inclusive ISO dates, India time), `stage`
(a lead stage key) and `owner` (an IT counselor id, IT Admin only).

| Caller | Scope |
|---|---|
| IT counselor (`counselor`, division `it`) | Their own book: leads with `owner_id = me`, and students linked to them (itc-003 `it_student_counselors`). |
| IT Admin (`it_admin`, division `it`) | Every IT counselor's book: leads with an owner, and every linked student. `owner` narrows it to one counselor. |
| Anyone else (overseas counselor, trainer, HR, …) | **403** "Only an IT counselor or the IT Admin has this dashboard". |

The request takes no student or lead id, so there is nothing to IDOR. Each figure is computed live, and nothing is logged or audited
(the ccrm-032 D1 precedent).

**Validation (422, and a filter is never silently ignored):**
- `program` / `batch` is not a UUID or does not exist → "Unknown filter value" (`application_filters.UNKNOWN_VALUE`).
- `batch` and `program` are both given but the batch belongs to another programme → "The batch is not in that course".
- `from` / `to` is malformed or reversed → the ccrm-012 messages (`application_filters.date_range`).
- `stage` is not in `lead_stages.STAGES` → "Unknown filter value".
- `owner` from an IT counselor → "The owner filter is for the IT Admin". From the IT Admin, an `owner` that is not an IT counselor →
  "Choose an IT counselor".

### Response

```json
{
  "filters": {"program": null, "batch": null, "from": null, "to": null, "stage": null, "owner": null},
  "options": {"programs": [{"value", "label"}], "batches": [{"value", "label", "program"}], "stages": [{"value", "label"}],
              "owners": [{"value", "label"}] /* IT Admin only, else [] */},
  "today": "2026-11-03",
  "widgets": {
    "assigned_leads":   {"count", "more", "items": [...]},
    "follow_ups":       {"count", "overdue", "more", "items": [...]},
    "pipeline":         {"count", "stages": [{"stage", "label", "count"}]},
    "conversions":      {"count", "more", "items": [...]},
    "enrolled_students":{"count", "more", "items": [...]},
    "outstanding_fees": {"count", "total", "more", "items": [...]},
    "at_risk":          {"count", "more", "items": [...]},
    "pending_hr":       {"count", "more", "items": [...]},
    "ready_to_convert": {"count", "more", "items": [...]}
  }
}
```

An item is `{id, label, detail, date, overdue, href}` (the ccrm-032 shape). A list holds at most 10 items (`LIMIT`) and `count` is
the full count of the same statement. That makes AC1 true by construction: the figure and the list come from one query.

## 3. Widget definitions (Claude's call where Appendix B is silent)

The **lead book L** is IT leads (`division='it'`) not merged (`merged_at IS NULL`) in the caller's scope. The **student book S** is
the linked IT students in scope.

| Widget | Definition | Date anchor |
|---|---|---|
| Assigned leads | L at an open stage (`ORDER` + Nurture), excluding `converted` | `created_at` |
| Follow-ups due today and overdue | Open `LeadFollowUp`s of L with `due_at` before tomorrow 00:00 IST. `overdue` = due before now. Soonest first. | `due_at` |
| Counseling pipeline | Count of L per open stage, in pipeline order. `count` = the sum. | `created_at` |
| Conversions | L with `converted_at` set (itc-011 / tel-018 link). Newest first. | `converted_at` |
| Enrolled students | Distinct S with ≥1 `active` enrolment | `enrolled_on` |
| Outstanding fees | `active` enrolments of S whose itc-013 balance is > 0. `total` = Σ balances (Appendix B "Outstanding"). Largest first. | `enrolled_on` |
| At-risk students | Open `StudentRiskFlag`s (itc-023) of S | `raised_at` |
| Pending HR actions | `HrReviewTask`s of S in stage `changes_requested`. No itc-027 stage "awaits the counselor", so Appendix B reduces to this stage. | `updated_at` |
| Ready to convert (workspace) | L at a convertible stage (`lead_handover.convertible_stage`: Qualified to Counselling Completed), not yet converted. Each item links to the lead page, where itc-011's Convert action lives. | `created_at` |

**How the filters apply (AC2).** One rule per filter:
- **Course (`program`):** a lead matches through its product's course (`tel_products.program_id`). A student, an enrolment, a flag or
  an HR task matches through an enrolment whose batch is in the programme.
- **Batch:** a student, enrolment, flag or HR task matches through an enrolment in that batch. A lead is not in a batch yet, so lead
  widgets narrow to the batch's **programme** (*Claude's call*).
- **Date range:** each widget's anchor column (table above) falls in the inclusive IST range. "Due today and overdue" still caps
  follow-ups at today, so a range narrows them to due dates inside it.
- **Status (`stage`):** a lead stage, applied to every lead widget (the pipeline shows only that stage). Student widgets have no lead
  stage, so they are **not narrowed**, and the board says so beside the filter (*Claude's call*, NEEDS_CONFIRMATION Q-29b). A student
  lifecycle filter waits on itc-031's stage being queryable.
- **Owner (IT Admin):** both books narrow to that counselor.

**Links.** For a counselor, a lead links to `/it/counselor/leads/{id}` and a student to `/it/counselor/students/{id}` (itc-029 360).
For the IT Admin, a lead links to `/it/admin/leads` and a student to `/it/admin/students/{id}`.

## 4. Performance

The query count is fixed whatever the book size, about 17: options (3), plus an owner list for the admin, and per widget one count plus
one page. The pipeline is one GROUP BY. Outstanding fees uses one enrolment read plus `fee_accounts.balance_for`, which is one UNION
query.

## 5. Frontend

- **`/it/counselor/dashboard`:** the portal payload is unchanged (its two tiles and recent-leads table stay, so tel-017 is unchanged).
  Its lead slot becomes `ItCounselorDashboardPanel` (a server component reading the endpoint with the page's query). The panel replaces
  the standalone at-risk list, because the board has its own at-risk widget with the same scope.
- **`/it/admin/counselor-dashboard`:** a new IT Admin nav item, "Counselor Dashboard", with a header-only portal payload. The same panel
  shows the Owner select.
- **Filter bar (`ItCounselorDashboardFilters`, client):** a GET form with Course, Batch, Status, From, To (and Owner) and Apply/Clear
  buttons. Values live in the URL, so the page survives a reload and Back/Forward. A 422 renders the unfiltered board with the message
  (the AGN-023 / itc-024 fallback).
- **Board:** a figure row of tiles (each a link to its section), then the sections in a responsive grid (the CounselorDashboardBoard
  idiom: side by side on desktop, stacked on a phone). Each section shows its count badge, up to 10 items, an empty text, and "Showing
  10 of N" when there are more. The workspace sections come first: today's follow-ups, ready to convert, at-risk, pending HR.
- **States:** a skeleton while loading (Suspense), an error card with "Try again" when the read fails, the access card on a 401, and
  empty text per section. A counselor with no students sees an empty text in every student section (the backlog edge case).

## 6. Q-29 (Tasks nav)

Verified on `main@933f7f78`: `PORTAL_NAV["it/counselor"]` has no `tasks` item. The only task link is the shared "Management tasks"
page (`/account/management-tasks`), which every staff portal has. The suspected defect does not exist, so there is no nav change (the
browser QA re-checks the link).

## 7. Alternatives considered

- *Widen the portal payload (`_it_counselor`)* (the itc-024 route): rejected. Nine sections with filters and options would bloat a
  generic table payload, and the backlog names `GET /counselor/it/dashboard`. The ccrm-032 own-endpoint panel is the closer precedent
  and keeps a failure isolated.
- *Link each tile to an existing page (My Leads, My Students)*: rejected for AC1. Those pages do not take the dashboard's filters, so
  their counts would differ.
- *Filter student widgets by the source lead's stage*: rejected. Almost every student's lead is at Converted, so the filter would empty
  those widgets.

## 8. Tests

Backend `tests/test_itc_030_it_counselor_dashboard.py`:
- the 403 matrix (overseas counselor, trainer, HR, student) and 401 signed out;
- the counselor's scope (another counselor's leads and students excluded);
- every widget's count equals its item count (≤ LIMIT) and its definition: open vs closed, merged excluded, follow-up today/overdue/
  tomorrow, conversions, an active vs withdrawn enrolment, a positive vs zero balance, an open vs cleared flag, changes_requested vs other
  stages, convertible stages;
- each filter narrows its widgets, and stage leaves student widgets alone;
- the 422s (bad UUID, unknown batch, batch outside programme, reversed dates, bad stage, owner from a counselor, owner not a counselor);
- admin: all books, and the owner filter;
- a counselor with nothing;
- a fixed query count;
- the existing `test_tel_017_it_counselor` stays green.

Frontend vitest for the board (sections, empty text, overdue badge, the stage note) and the filter bar (URL building, Clear). E2e
`itc-030-it-counselor-dashboard.spec.ts`: a counselor filters and sees the figure equal the list, the admin uses the owner filter, an
overseas counselor gets the error card, and a mobile layout check.
