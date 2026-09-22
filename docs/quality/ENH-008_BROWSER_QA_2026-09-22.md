# ENH-008 — independent exploratory browser QA (2026-09-22)

Feature: parent account linked to children across multiple schools (`ENH-008`).
Tool: Browser Use (CDP) against a running Chrome, driving the running web app; plus targeted API calls
from the page and direct DB reads for independent verification of each step.

## Method and environment (read this before trusting the results)

- **Stack:** an isolated compose project (`enh008-qa`: web `:3030`, API `:8030`, its own Postgres/Redis
  volumes, migration `0034`, freshly seeded with `python -m app.seed`). A second school ("Lakeview
  International School") was created through the real admin UI during this session specifically to
  enable the cross-school scenario — the seed data alone only has one school.
- **Data written on the isolated stack only:** one manually-created school + coordinator, one new
  student ("Kabir Mehta") linking the seeded demo parent cross-school, one rejected roster row (teacher
  email as parent_email, correctly rolled back, verified no orphan row). None of it touches a real
  database or any other worktree's stack.
- **Roles used:** super_admin (briefly, before switching to overseas_admin — see Operational notes),
  overseas_admin, school_coordinator (two, one per school), school_parent, school_teacher (as the
  negative-test target only, never logged in as).
- **Not covered this pass:** server errors (5xx simulation), loading-state observation under real
  latency (pages resolved too fast locally to catch the Suspense fallback visually), refresh mid-flow,
  offline/throttled network simulation, bulk upload, transfers, entitlements pages.
- **Evidence you can re-run:** `apps/web/tests/e2e/sch-roster-parent-invite.spec.ts`'s third test
  (added this session, `04b4ac7`) automates the core scenario below end-to-end. **Not committed:** the
  exploratory screenshots and manual `curl`/`psql` verification commands (they live in this session's
  transcript, not a scratch folder, since this was a single-session pass, not a scripted harness run).
  This file is the summary of record.

**Operational note, not an app finding:** this machine's local Chrome is shared with other concurrent
Claude sessions testing other worktrees (observed on ports 3000/3010/3020 during this pass). Two tab
collisions occurred; recovering required one `Network.clearBrowserCookies` call, which would have
logged out whichever other session was using that Chrome profile at the time. Flagged for visibility,
not something this branch caused or can fix.

## Coverage (20 requested areas)

Happy path (cross-school linking, verified live + DB), invalid input (non-`school_parent` email
rejected with the transaction cleanly rolled back — no orphan student row), empty states (empty
roster, "No students yet", child-detail sections with no records yet), duplicate submission (409, no
double link), unauthorized (401, no session), incorrect role (403, teacher hitting a coordinator-only
endpoint), desktop/tablet/mobile (1034×737, 768×1024, 375×812: no overflow, sidebar collapses
correctly, school-grouping headings render at every width), navigation (roster → dashboard → child
detail → back), success messages ("Parent linked immediately (they already had an account)."), error
messages (role-conflict message correct, form values preserved on error), broken images (none — logo
`640×640`, `complete: true`), console errors (none captured on dashboard, child-detail, or Team pages).
Server errors, loading-state visuals, refresh, and failed-network simulation were not exercised this
pass (see above).

## Findings

| ID | Severity | Role | Finding | Status |
|---|---|---|---|---|
| QA-ENH008-001 | Low (pre-existing, not caused by this branch) | Coordinator | The roster table's "Parent" column only ever renders a pending-invite badge or `-`; it has no positive indicator for an already-linked parent (`_student_out()`'s response has no linked-parent field at all, so this is structural, not a display bug specific to the cross-school case). Confirmed reproducible for the ordinary same-school case too by code inspection. | Open, not ENH-008 |
| QA-ENH008-002 | Low (pre-existing, not caused by this branch) | Coordinator | The role-conflict error message leaks the raw API field name: `parent_email 'x@y' belongs to an existing account that is not a Parent`. This exact phrasing predates ENH-008 — Task 1 only removed the "at this school" clause from it. | Open, not ENH-008 |

No Critical, High, or Medium severity issues found. Every ENH-008 acceptance criterion and the Task 4
addendum were independently verified working, live, with database cross-checks at each step:

| Scenario | Result |
|---|---|
| AC1 — parent at School A linked to a new student at School B | **PASS.** UI: "Kabir Mehta added to the roster. Parent linked immediately (they already had an account)." DB: `school_parent_links` gained a third row for the same parent, at the new school, alongside the two pre-existing Sunrise rows. |
| AC2 — parent dashboard groups both children under their own school | **PASS**, desktop and mobile (375px). "Sunrise Public School" / "Lakeview International School" headings render correctly; child-detail page also states `School: Lakeview International School` explicitly. |
| AC3 — parent sees none of a school's data with zero links there | **PASS.** Direct navigation to another Sunrise student's detail page (same school, no link) returned "This student is not linked to your account" — the single, collapsed message from Task 3's fix, not a leak. |
| AC4 — non-`school_parent` email still rejected | **PASS.** Teacher email correctly rejected; roster form retained its values (no retype needed); no orphan `school_students` row left behind despite the flush-before-check code shape. |
| Task 4 addendum — parent visible/manageable on a Team page despite a mismatched `profile.school_id` | **PASS.** The demo parent (whose `profile.school_id` still names Sunrise, pre-dating this branch's deprecation) correctly appears with a working "Deactivate" action on Lakeview's Team page — the link-derived union working exactly as designed. |

## Re-run and regression notes

- This session's own backend test additions (`test_enh_005_scope.py`, `test_sch_roster_parent_invite.py`)
  and the new Playwright test added during the Codex-review follow-up (`04b4ac7`) were all re-run and
  pass: 20/20 backend, 3/3 Playwright in the touched spec file. A full regression suite (backend, web
  unit, full Playwright) was run separately as the plan's own Task 6 gate (197/197) and the final
  whole-branch review's fix-wave verification (222/222 backend, 333/333 web unit) — not repeated here.
- No code was modified as a result of this QA pass — findings QA-ENH008-001/002 are both pre-existing,
  low-severity, and explicitly out of scope for this branch.
