# bdm-020 — School activity tracking (live, per school) — design

**Feature:** `BDM_CRM_BACKLOG.md` §4 bdm-020 (School §E of `EVID-016`, `DERIVED_BLUEPRINT`). **Depends on:** bdm-018 (merged, PR #87).
**Decision:** `DEC-SCOPE-089` (owner, in-session 2026-10-06, three structured questions answered with the recommended option).

## 1. Decisions

- **A1** University Guidance uses the School module's own figure (`school_analytics.DEVELOPMENT_ROWS`: students with an application
  at University Selection or later). This refines D24 (Q-15) for this one metric, so that AC1 ("counts equal the School module's own
  analytics") holds.
- **A2** Student profile completion is **"Not tracked"** (D24): listed, with no number.
- **A3** The design below is approved: one read-only endpoint, a panel on both organization pages, no migration, and the School
  analytics helpers reused without being edited.

## 2. API — `GET /api/v1/bdm/organizations/{org_id}/school-activity`

- **Scope:** `bdm_organizations.load_scoped`. A School BDM can read their module, a manager their team, and super_admin everything.
  Any other role gets 403 (`caller_scope`). An unknown or out-of-scope organization gets 404 `Organization not found`.
- **A non-School organization** (seen by a manager or super_admin) gets 404 `School activity is only for School organizations`.
  The caller can already read that organization, so the message reveals nothing.
- **Unlinked** (`school_id` null): 200 `{linked: false, school: null, total_students: null, metrics: []}`. The UI shows "Not
  onboarded yet".
- **Linked:** 200 `{linked: true, school: {name, school_code}, total_students, metrics}`. `metrics` lists, in order: Career Guidance,
  Psychometric Test, Foreign Language, English Testing, University Guidance (each `{key, label, tracked: true, completed,
  pending}`, with pending = total − completed, D2), then Student Profile Completion (`tracked: false`, `completed`/`pending` null).
- **Computation:** `students_in([school_id])` + `student_indicators` + `DEVELOPMENT_ROWS`, imported unchanged from
  `school_analytics`. The total is the count of `school_students` currently at that School (ENH-005: a student who transferred out
  counts at the new School). The query count is constant.
- **No student row:** only integers and the School's name/code. No ids or names. Small counts are acceptable (backlog).
- **Read-only:** no writes, no audit row. One structured log line `bdm_school_activity_viewed` (actor, org, school ids).
- Archived or Lost organizations can still be read (a read-only view).

## 3. Web

- `lib/bdmSchoolActivity.ts` (types, URL, shape guard) and `lib/bdmSchoolActivityServer.ts` `firstSchoolActivity(id)` follow the
  `firstMou` pattern: they never reject and return null on failure.
- `components/BdmOrganizationSchoolActivity.tsx`, a read-only `action-card` "School activity". Its states:
  - **linked:** a table of Metric / Completed / Pending (the School module's wording), with "Not tracked" spanning the row.
  - **not linked:** "Not onboarded yet. Counts appear once Overseas Admin links the School."
  - **error (null):** "Unable to load the school activity." with a "Try again" button (GET via `sendRequest`, plus a busy state).
- It is rendered by `BdmOrganizationDetail` for School organizations only, and fed by both `/bdm/organizations/[id]` and
  `/bdm/manager/organizations/[id]`.

## 4. Tests

- **pytest `test_bdm_020_school_activity.py`:**
  - parity with `/school/analytics/student-development` for the same School (coordinator view);
  - the 0 / unlinked states;
  - scope: peer School BDM can read (module scope), College BDM 404, other manager 404, own manager and super_admin 200,
    school coordinator 403;
  - non-School organization 404;
  - no student-identifying keys in the body;
  - a transferred-out student counts at the new School only.
- **vitest** for the panel states and the retry.
- **Playwright** `bdm-020-school-activity.spec.ts` for the linked / unlinked panel on both pages.

## 5. Regression risk

Low. Nothing shared is edited; `school_analytics` is only imported. Run `test_enh_016_*` and `test_bdm_018_*` as the guard.
