# ccrm-017 — Student journey stage for direct students (design)

`DEC-SCOPE-258`. Backlog: `docs/delivery/COUNSELOR_CRM_BACKLOG.md` § ccrm-017 (source: Counselor CRM Specification §6 "critical rule:
journey stage separate from application statuses", §5 Overview — UNVERIFIED generic spec). Dependencies ccrm-014 (sub-status) and
ccrm-015 (outcomes) are merged.

## Intent

A counselor or the Overseas Admin opening a student's 360 sees, at a glance, where the student is in the whole journey (one stage),
separately from each application's own stage. The value is derived on every read and never stored on an application.

## Decisions (builder's defaults, all `NEEDS_CONFIRMATION` — owner asked for an autonomous run with recommended answers)

- **J1 Stages:** six, in order — `lead` (Lead), `counselling` (Counselling), `applying` (Applying), `offer` (Offer), `visa` (Visa),
  `enrolled` (Enrolled) — the backlog's own list.
- **J2 Application stage → journey stage:** `enquiry`, `eligibility_evaluation` → Counselling; `university_selection` → Applying;
  `offer` → Offer; `visa_documentation`, `status_tracking` → Visa; `enrolled` → Enrolled. The legacy (seed) `university_review` counts as Applying (browser QA-01); any other unknown/legacy stage counts as Counselling.
- **J3 Best application:** the furthest journey stage among the student's **live** applications — every application that is not
  closed (`withdrawn`, or a terminal ccrm-015 outcome: rejected / withdrawn / offer declined / visa refused). Enrolled counts as live.
  On hold and Deferred stay live; the stage keeps its value and carries a note ("On hold" / "Deferred") from the best application.
  Ties: the most recently updated application. Agency applications count too (ccrm-009 V1: the 360 shows all the student's applications).
- **J4 No live application:** Counselling when the student has a counselor link (csc-001), an appointment that is not
  cancelled / no-show, or any (closed) application; otherwise Lead. When every application is closed the note says
  "All applications closed".
- **J5 Where it shows:** the ccrm-009 overview payload gains `journey`; the 360's Overview tab (spec §5 Overview) shows it first, as a six-step tracker
  (AGN-015's `.jny-steps` styling; state as text, never colour alone). The ccrm-009 B1 "journey hidden" default is lifted.
- **J6 Not generalising `agent_journey`:** the backlog's "BE: generalise agent_journey" is not followed — AGN-015's tracker is a
  per-application agency step list with agency scoping and a different shape; the stage here is one value from the application stage,
  outcome and engagement. A pure module `app/student_journey.py` holds the stage list and the rule so ccrm-032 / nehn-033 reuse it.

## Contract

`GET /api/v1/counselor/students/{id}/overview` (§12FF) adds (additive, backward compatible):

```
"journey": {
  "stage": "offer", "label": "Offer",
  "steps": [{"key": "lead", "label": "Lead", "state": "done"}, ..., {"key": "offer", "label": "Offer", "state": "current"}, ...],
  "application": {"id": "...", "application_code": "APP-000012", "university": "..."} | null,
  "note": "On hold" | "Deferred" | "All applications closed" | null
}
```

`state` ∈ `done` / `current` / `upcoming`. Same scope and roles as the overview (csc-001 counselor scope, Overseas Admin); no new
route, no migration, no write, no audit row, no new RBAC rule.

## Non-goals

Student-facing progress page (nehn-033), dashboard use (ccrm-032), storing the stage, changing any application stage rule.

## Tests

Pure rule unit tests (each J2 mapping, J3 best/closed/on-hold, J4 lead vs counselling); route test that the overview carries the
journey for a three-application student and stays 404 for another counselor's student; web render test of the tracker; e2e on the
360 overview.
