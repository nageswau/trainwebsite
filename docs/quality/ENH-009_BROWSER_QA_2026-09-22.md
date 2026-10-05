# ENH-009 — browser QA record (2026-09-22)

Feature: School Profile mandatory full field coverage (`ENH-009`, `School CRM.md` §2/`EVID-014`,
`DEC-SCOPE-025`, renumbered from `DEC-SCOPE-023` on merge with `main`). Tool: Browser Use (CDP)
against the running web app, plus direct API calls (`curl`) for the authorization/validation
boundary checks that a browser cannot exercise cleanly (role-swapping between requests without
losing the admin session under test).

**Status of this record: closes the "real browser validation" item explicitly left open in
`RTM.md`'s `ENH-009` addendum.** This is the first browser exercise of the actual shipped
feature — the QA pass run before implementation (`docs/quality/...` from that session) tested
only the pre-ENH-009 baseline and explicitly could not exercise any of the fields, panels, or
endpoints this feature added.

## Method and environment

- **Stack:** this worktree's own isolated compose project (`enh009-*`: web `:3010`, API `:8010`,
  its own Postgres/Redis), rebuilt from the post-merge HEAD (`61a1c04`, ENH-008/ENH-010 merged
  in) immediately before this pass, seeded via `python -m app.seed` (demo password `Demo@123`).
- **Roles exercised:** Overseas Admin (actor, `overseasadmin@edusphere.local`), School Coordinator
  (`school.coordinator@edusphere.local`) and Counselor (`counselor@edusphere.local`) for the
  authorization-boundary checks, and unauthenticated.
- **Tooling note:** the daemon's default Chrome instance had no remote-debugging port open and a
  locked profile blocked auto-launch; a separate, isolated Chrome instance was started with its
  own temp profile and `--remote-debugging-port` (user-approved: "start new chrome instance") so
  the user's own browser windows were never touched. Within that isolated instance, CDP's
  `Input.dispatchMouseEvent` (used by `click_at_xy`) consistently failed to register clicks —
  sometimes silently, sometimes with a timeout — even after the window was restored and
  foregrounded; this reads as an environment/tooling issue (synthetic OS-level input injection
  against a freshly spawned, non-interactive Chrome process on this host), not an application
  defect. Form interaction was instead driven via direct DOM value assignment and
  `form.requestSubmit()` / `button.click()` (native, non-synthetic JS APIs that still route
  through the real React `onSubmit`/`onClick` handlers and the real `fetch` calls) — this is
  disclosed because it is a materially different interaction path than a literal mouse click, even
  though it exercises the identical application code.
- **Not covered:** browsers other than Chrome, screen readers, real touch devices, tablet/mobile
  viewports, a production build behind a real proxy. The role-boundary checks (coordinator/
  counselor/unauthenticated against the admin-only endpoints) were run via direct API calls rather
  than in-browser role switches, to avoid disturbing the single browser session under test.

## Findings

| ID | Severity | Role | Page | Finding | Status |
|---|---|---|---|---|---|
| ENH009-QA-01 | Low (not reproduced) | Overseas Admin | `/overseas/admin/schools` | Once, immediately after the *first* successful "Create school" submission (via a JS-dispatched `button.click()`, not a real click — see tooling note above), the browser tab ended up on the public homepage (`/`), logged out, instead of staying on the schools admin page. The create itself had already succeeded (the `POST` returned successfully, the row later appeared in the list). Re-logging in and repeating the exact same create-then-refresh cycle, and separately the edit/save cycle, did not reproduce it. Given the unrelated Input-domain tooling instability documented above, this is recorded as an unreproduced observation, not a confirmed defect — flagging it rather than silently dropping it, per this session's QA convention. | **Not fixed — not confirmed as a real defect.** Recommend a human keep an eye out for an unexpected session drop after creating a school; if it recurs outside this tooling-degraded environment, escalate. |

**Clean, confirmed live:** no other unexpected redirects across ~15 further requests (2 creates,
1 lookup, 1 edit-save, repeated list reloads); no broken images; no console errors observed via
`window.onerror` was not separately instrumented this pass (time-boxed to the field-coverage
surface itself), but no in-page error banners or blank-render states were seen on any of the
pages visited.

## Acceptance criteria — observed live, not read from code

| AC | Result |
|---|---|
| All in-scope `EVID-014` fields are captured on create and are round-trip accurate | **PASS** — created "QA Validation School" with all 12 new fields (Branch, Address, Contact number, Email, Website, Grades available, Board, Partnership date, Agreement/MoU reference, Edusphere BDM, Vice Principal, Monthly visit schedule) plus City/State/Tier/Coordinator name+email; the Partner Schools list row and the lookup response both echoed every value exactly (`School ID 6F58002A`, `Branch "North Campus"`, `City "London"`, `State "Greater London"`, `Board "IB"`, `Tier "gold"`, etc.) |
| `school_code` is generated and displayed | **PASS** — `6F58002A` assigned on create, shown in the widened Partner Schools list's "School ID" column and usable immediately as the Edit panel's lookup key |
| Partner Schools list is widened to show the new columns | **PASS** — table header now reads School ID / Name / Branch / City / State / Board / Tier / Created (previously id/name/city/state/tier/created only); pre-existing test-fixture rows correctly show `-` for fields they were never given (not a defect — those rows were inserted directly by test fixtures, bypassing the create endpoint) |
| Edit panel: lookup by School ID loads the current profile | **PASS** — looking up `6F58002A` loaded all 12 field values exactly as created |
| Edit panel: partial update sends only changed fields | **PASS**, confirmed at the database level, not just the UI — changing Address and clearing Vice Principal produced an audit row of exactly `{"changed_fields": ["address", "vice_principal_name"]}` (field names only, no values, per the design's stated privacy rationale); the untouched Branch field was confirmed unchanged after save |
| Edit panel: clearing a field sends explicit `null`, not an omitted key | **PASS** — Vice Principal was cleared to empty and persisted as `null` in the reloaded state, distinct from "field not sent" |
| `GET .../schools/lookup?code=` is admin-only, narrower than the sibling student-lookup endpoint | **PASS** — `school_coordinator` → `403 "Overseas Admin role required"`; `counselor` → same `403` (the deliberate exclusion that differs from `school-students/lookup`, which does allow `counselor`); unauthenticated → `401` |
| `POST`/`PATCH` schools endpoints reject a non-admin caller | **PASS** — `school_coordinator` attempting `POST /overseas-admin/schools` → `403` |
| `board` is a closed enum, `email` respects its column's `max_length` | **PASS** — `board: "Cambridge"` → `422` naming the literal's allowed values; a >255-char `email` → `422 string_too_long` (this is the exact fix from ENH-009's final-review wave, confirmed live post-merge) |
| `extra="forbid"` blocks a smuggled `school_code` on create | **PASS** — `422 extra_forbidden`, the field is never silently accepted |
| Lookup of a non-existent code fails cleanly | **PASS** — `404 "No school found with that School ID"`, no information leak about which codes exist |
| Computed fields (`student_count`, `teacher_count`, `principal_name`, `school_coordinator_name`, `career_counsellor_names`) are derived correctly, not stored | **PASS** — the freshly created school's lookup response showed `student_count: 0`, `teacher_count: 0`, `principal_name: null`, `career_counsellor_names: []` (all correct — none assigned), and `school_coordinator_name: "Alice Coordinator"` correctly derived from the seed Coordinator account created in the same request |
| HTML5 client-side `required` validation still works on the create form | **PASS** — submitting with School name empty was blocked by `checkValidity() === False`; no network request fired |

**Not re-verified this pass (already covered by the 1062-passed backend suite and 338-passed
frontend suite run immediately after the post-merge rebuild, both against this same code):**
concurrency/race conditions on `update_school`, the N+1 query-batching fix on `list_schools`, the
`school_code` backfill migration's idempotency, and desktop/tablet/mobile responsive layout of the
new Identity/Academic/Partnership field groups.
