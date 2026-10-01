# AGN-005 — Close the §6 Staff Matrix Gap: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put AGN-004's agency-student routes into the §6 Master-vs-Staff matrix tests and docs, and pin the staff UI's hidden Unarchive control, without changing any production code.

**Architecture:** Extend the three parametrised lists in `apps/api/tests/test_agn_003_matrix.py` (the §6 matrix stays in one file); `_world` gains two agency student records assigned to the calling staff member. One vitest case in `AgentStudentsPanel.test.tsx`. The behaviour already exists, so each new test's RED is proven by a temporary, uncommitted mutation of the guard it protects.

**Tech Stack:** pytest + pytest-asyncio + httpx (`client_for`), SQLAlchemy 2 async; Vitest + Testing Library; Docker Compose `ci` profile.

**Spec:** `docs/superpowers/specs/2026-10-01-agn-005-staff-matrix-gap-design.md`

## Global Constraints

- No change under `apps/api/app`, `apps/api/alembic`, `apps/web/components`, `apps/web/lib`, `apps/web/app` (AC05). Mutations are reverted and checked with `git diff --exit-code`.
- Every pre-existing row, assertion and expected value in `test_agn_003_matrix.py` and `AgentStudentsPanel.test.tsx` stays as it is.
- Refusals assert the exact `detail`: `"Only an agency Master can archive students"`, `"Only an agency Master can assign students"`.
- Records used by staff are assigned to the caller (else AGN-004's `404` mask answers first).
- No new dependency, helper module or abstraction; reuse `agn004_helpers.mk_record` and `RECORDS`.
- Lite regression set only (owner's standing choice); the full backend suite is not run for this feature.
- No new operational logging: no production code changes; AGN-004's `agent_student_*` structured logs are unchanged.
- Do not claim COMPLETE: browser validation and the independent Codex review remain (owner, 2026-10-01).

## Review Focus

1. A staff refusal that passes because of the `404` existence mask, not the role check → exact-`detail` assertion (Task 1).
2. A refusal that writes data before raising → record state and `agent_student.*` audit rows asserted unchanged (Task 1).
3. A Master `200` that only passes because of record state (e.g. unarchive on an active record would be `409`) → unarchive uses the archived record (Task 1).
4. New `_world` rows colliding with existing cases (duplicate check, uniqueness) → records carry no email/phone; whole file re-run (Task 1 step 6).
5. The web case passing because Show archived was never on → assert the list request carried `include_archived=true` (Task 2).

## Test commands (PowerShell, from the worktree root)

The owner runs Docker. Ask them to start the isolated test services once:

```powershell
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn005 --profile ci build api-test web-test
docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn005 --profile ci up -d --wait postgres redis
```

Then:

```powershell
function dc { docker compose -f docker-compose.yml -f docker-compose.ci.yml -p agn005 --profile ci @args }
dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test alembic upgrade head
```

- **API(x)** = `dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test python -m pytest -q x`
- **WEB(x)** = `dc run --rm --no-deps -v "${PWD}\apps\web\components:/app/components" -v "${PWD}\apps\web\lib:/app/lib" -v "${PWD}\apps\web\tests:/app/tests" -v "${PWD}\apps\web\app:/app/app" web-test npx vitest run x`
- **LINT** = `dc run --rm --no-deps -v "${PWD}\apps\api:/app" api-test ruff check tests/test_agn_003_matrix.py`

---

### Task 1: §6 matrix rows for agency student records (AC01–AC03, AC05)

**Files:**
- Modify: `apps/api/tests/test_agn_003_matrix.py` (docstring 1–6, imports 8–13, constants 15–18, lists 21–79, `_world` 90–104, `test_staff_refused` 114–126)
- Mutate temporarily (never committed): `apps/api/app/api/agent_students.py:157` and `:181`

**Interfaces:**
- Consumes: `tests.agn004_helpers.mk_record(db, *, agent, full_name, email=None, phone=None, assigned_member=None, status="active") -> AgentStudent`; `tests.agn004_helpers.RECORDS = "/api/v1/workflows/overseas/agent/crm/students"`.
- Produces: `ids["record"]`, `ids["archived_record"]` placeholders in the matrix lists.

- [ ] **Step 1: Write the tests**

Docstring — replace lines 1–3 with:

```python
"""AGN-003-AC01/AC02 and AGN-005-AC01..AC03 -- the EVID-015 §6 matrix as built (AGN-003 spec §3, AGN-005 spec §3). Staff have both
optional toggles OFF here; the toggles' ON side is tested in test_agn_003_permissions.py and test_agn_003_verify.py. The student rows
(Create/View/Edit/Delete/Assign Student) use AGN-004's /crm/students routes on a student assigned to the caller, so a refusal comes
from the Master-only check and not from the 404 existence mask. Rows with no route for any agent (Edit Application, Change
Application Status, Staff Performance, CRM Settings) are N/A and have nothing to call.
```

(lines 4–6 — the two cited Master cells — stay as they are.)

Imports — replace lines 8–13 with:

```python
import pytest
from sqlalchemy import select

from app.models import AgentOrgMember, AgentStudent, AuditLog, StudentDocument, User
from tests.agn001_helpers import client_for, mk_active_org, mk_user, uniq
from tests.agn002_helpers import STAFF, mk_staff
from tests.agn003_helpers import agency_document, mk_university
from tests.agn004_helpers import RECORDS, mk_record
```

Append to `STAFF_REFUSED` (after the Add University row):

```python
    ("Delete Student", "post", RECORDS + "/{record}/archive", None, "Only an agency Master can archive students"),
    ("Delete Student", "post", RECORDS + "/{archived_record}/unarchive", None, "Only an agency Master can archive students"),
    ("Assign Student", "post", RECORDS + "/{record}/assign", {"member_id": "{other_staff}"}, "Only an agency Master can assign students"),
```

Append to `BOTH_ALLOWED` (after the last University Database row):

```python
    ("Create Student", "post", RECORDS, {"full_name": "Matrix New Student"}, 201),
    ("View Students", "get", RECORDS, None, 200),
    ("View Students", "get", RECORDS + "/{record}", None, 200),
    ("Edit Student", "patch", RECORDS + "/{record}", {"full_name": "Edited Student"}, 200),
```

Append to `MASTER_ALLOWED`:

```python
    ("Delete Student", "post", RECORDS + "/{record}/archive", None, 200),
    ("Delete Student", "post", RECORDS + "/{archived_record}/unarchive", None, 200),
    ("Assign Student", "post", RECORDS + "/{record}/assign", {"member_id": "{other_staff}"}, 200),
```

In `_world`, after `other_university = await mk_university(db_session)`:

```python
    # AGN-005: agency students with no login, assigned to the caller (staff reach only their assigned students, DEC-SCOPE-042 G4).
    record = await mk_record(db_session, agent=ctx["master"], full_name="Matrix Record", assigned_member=caller["member"])
    archived = await mk_record(db_session, agent=ctx["master"], full_name="Matrix Archived", assigned_member=caller["member"], status="archived")
```

and add to the `ids` dict: `"record": record.id, "archived_record": archived.id,`.

In `test_staff_refused`, after `assert other_user.full_name == "Other Staff"`:

```python
    record = await db_session.get(AgentStudent, ids["record"], populate_existing=True)
    archived = await db_session.get(AgentStudent, ids["archived_record"], populate_existing=True)
    assert (record.status, record.assigned_member_id, record.full_name) == ("active", caller["member"].id, "Matrix Record")
    assert archived.status == "archived"
    student_ids = [str(ids["record"]), str(ids["archived_record"])]
    audits = (await db_session.execute(select(AuditLog).where(AuditLog.action.like("agent_student.%"), AuditLog.entity_id.in_(student_ids)))).scalars().all()
    assert audits == [], f"{row}: a refused call wrote {[a.action for a in audits]}"
```

- [ ] **Step 2: Run the new cases against today's code**

Run: API(`tests/test_agn_003_matrix.py -k "Student"`)
Expected: all new cases PASS (the behaviour already exists — AGN-004). If any fails, stop: the test or the assumption is wrong, not the product (CLAUDE.md: never alter product behaviour to make a test pass).

- [ ] **Step 3: RED by mutation — prove the refusals can fail**

Comment out `_require_master_action(...)` at `apps/api/app/api/agent_students.py:157` and `:181` (working copy only).
Run: API(`tests/test_agn_003_matrix.py -k "test_staff_refused and Student"`)
Expected: 3 FAILED — archive and assign with `200` instead of `403` ("refused by the wrong gate" / status message), unarchive with `200`. Record the observed output for the RTM.

- [ ] **Step 4: Restore and confirm the product is untouched**

Run: `git checkout -- apps/api/app/api/agent_students.py; git diff --exit-code apps/api/app`
Expected: exit 0, no output.

- [ ] **Step 5: GREEN — rerun the new cases**

Run: API(`tests/test_agn_003_matrix.py -k "Student"`)
Expected: all PASS.

- [ ] **Step 6: Whole file (existing cases with the new `_world`) and lint**

Run: API(`tests/test_agn_003_matrix.py`), then LINT.
Expected: all PASS (62 pre-existing + 14 new); ruff "All checks passed!".

- [ ] **Step 7: Refactor check**

Only if duplication appeared: none is expected (rows are data). Rerun step 6 after any change.

- [ ] **Step 8: Commit**

```powershell
git add apps/api/tests/test_agn_003_matrix.py
git commit -m "test(agn-005): §6 matrix rows for agency student records (create/view/edit allowed; archive/unarchive/assign staff 403)"
```

### Task 2: Staff see no Unarchive control (AC06)

**Files:**
- Modify: `apps/web/tests/components/AgentStudentsPanel.test.tsx` (new case after "hides Master-only controls from staff", ~line 81)
- Mutate temporarily (never committed): `apps/web/components/AgentStudentsPanel.tsx:346`

**Interfaces:**
- Consumes: the file's `item`, `page`, `res` fixtures; `AgentStudentsPanel({ memberRole })`.

- [ ] **Step 1: Write the test**

```tsx
  it("hides Unarchive from staff on an archived student (AGN-005-AC06)", async () => {
    window.history.replaceState(null, "", "/?archived=1"); // Show archived on (QA-06 keeps it in the URL; afterEach resets it)
    const fetchMock = vi.fn(() => Promise.resolve(res(page([item({ status: "archived" })]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsPanel memberRole="staff" />);
    await screen.findByText("Asha Rao");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("include_archived=true"))).toBe(true);
    expect(screen.queryByRole("button", { name: "Unarchive Asha Rao" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Archive Asha Rao" })).toBeNull();
    expect(screen.getByRole("button", { name: "View Asha Rao" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run against today's code**

Run: WEB(`tests/components/AgentStudentsPanel.test.tsx -t "hides Unarchive"`)
Expected: PASS. If the `include_archived` assertion fails, fix the test's way of turning Show archived on (tick the "Show archived" checkbox with `fireEvent.click(screen.getByLabelText(...))`), not the component.

- [ ] **Step 3: RED by mutation**

Change `{isMaster &&` at `apps/web/components/AgentStudentsPanel.tsx:346` to `{true &&` (working copy only).
Run: WEB(`tests/components/AgentStudentsPanel.test.tsx -t "hides Unarchive"`)
Expected: FAIL — `Unarchive Asha Rao` button found.

- [ ] **Step 4: Restore**

Run: `git checkout -- apps/web/components/AgentStudentsPanel.tsx; git diff --exit-code apps/web/components`
Expected: exit 0.

- [ ] **Step 5: GREEN — whole file**

Run: WEB(`tests/components/AgentStudentsPanel.test.tsx`)
Expected: all PASS (pre-existing + 1).

- [ ] **Step 6: Commit**

```powershell
git add apps/web/tests/components/AgentStudentsPanel.test.tsx
git commit -m "test(agn-005): staff see no Unarchive control on an archived student"
```

### Task 3: Documentation (AC04)

**Files:**
- Modify: `docs/architecture/RBAC_MATRIX.md` §2.8 AGN-003 addendum (table rows Create/View/Edit/Delete/Assign Student, the N/A bullet, the "Proved by" paragraph)
- Modify: `docs/superpowers/specs/2026-10-01-agn-003-staff-permissions-design.md` §3 (one dated note under the table)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (revision note near line 66, summary table row after AGN-004 at line 150, new §AGN-005 entry after §AGN-003)
- Modify: `docs/quality/RTM.md` (AGN-005 row after the AGN-003 addendum)

- [ ] **Step 1: RBAC_MATRIX.md** — replace the five student rows with:

```markdown
| Create Student | `POST /workflows/overseas/agent/students` (links an existing student); `POST /workflows/overseas/agent/crm/students` (no login, AGN-004) | ✅ | ✅ (assigned to them) |
| View Students | `GET /workflows/overseas/agent/students`, `GET /portal/overseas/agent/students`, `GET /lookups/overseas-students`, `GET /workflows/overseas/agent/crm/students`, `GET …/crm/students/{id}` | ✅ agency | ✅ assigned only (`DEC-SCOPE-042` G4) |
| Edit Student | `PATCH /workflows/overseas/agent/crm/students/{id}` (students with no login) | ✅ | ✅ assigned only |
| Delete Student | `POST …/crm/students/{id}/archive`, `POST …/crm/students/{id}/unarchive` (no delete route; `DEC-SCOPE-042` D5) | ✅ | ❌ |
| Assign Student / Assign Students | `POST …/crm/students/{id}/assign` | ✅ | ❌ |
```

Change the N/A bullet's first clause to "**N/A rows** (Edit Application, Change Application Status, Staff Performance, CRM Settings) have no route for any agent…", and append to "Proved by": "The student rows: `test_agn_003_matrix.py` (AGN-005, 2026-10-01 — they were N/A in AGN-003's draft because AGN-004's `/crm/students` routes reached `main` later)."

- [ ] **Step 2: AGN-003 spec §3 note** — under the matrix table:

```markdown
> **Note (2026-10-01, AGN-005):** Edit, Delete and Assign Student were N/A when this table was drafted; AGN-004's `/crm/students`
> routes reached `main` afterwards. The rows as built and tested are in `RBAC_MATRIX.md` §2.8 and
> `2026-10-01-agn-005-staff-matrix-gap-design.md` §3. This table is kept as designed.
```

- [ ] **Step 3: ENHANCEMENT_BACKLOG.md** — revision note, table row `| AGN-005 | Close the §6 staff matrix gap for agency student records (tests + docs, no behaviour change) | Small | Low | No | AGN-003, AGN-004 |`, and a §AGN-005 entry in the AGN-003 format with AC01–AC06 copied verbatim from the spec §6, status "IMPLEMENTED, NOT COMPLETE — browser validation and independent Codex review pending".

- [ ] **Step 4: RTM.md** — AGN-005 row: requirement → spec → plan → tests (each AC → test id) → evidence from Tasks 1, 2, 4 (counts and mutation results as observed) → the 422-before-403 observation (spec §10) as a follow-up candidate → status "IMPLEMENTED, NOT COMPLETE".

- [ ] **Step 5: Commit**

```powershell
git add docs/architecture/RBAC_MATRIX.md docs/superpowers/specs/2026-10-01-agn-003-staff-permissions-design.md docs/delivery/ENHANCEMENT_BACKLOG.md docs/quality/RTM.md
git commit -m "docs(agn-005): student rows in the §6 matrix; backlog and RTM"
```

### Task 4: Verification (lite set)

- [ ] **Step 1: Backend lite set**

Run: API(`tests/test_agn_001_*.py tests/test_agn_002_*.py tests/test_agn_003_*.py tests/test_agn_004_*.py tests/test_agt_001*.py tests/test_agt_002*.py tests/test_agt_003*.py tests/test_agt_004*.py tests/test_ovs_005_documents.py tests/test_enh_031_*.py`) — if the container's shell does not expand globs, list the files explicitly (`ls apps/api/tests`).
Expected: 0 failed. Record counts.

- [ ] **Step 2: Web**

Run: WEB(`tests/components/AgentStudentsPanel.test.tsx tests/lib/navigation.agent.test.ts`) and `dc run --rm --no-deps -v ... web-test npx tsc --noEmit`.
Expected: 0 failed; tsc exit 0.

- [ ] **Step 3: Scope check**

Run: `git diff --stat origin/main -- apps/api/app apps/api/alembic apps/web/components apps/web/lib apps/web/app`
Expected: empty (AC05).

- [ ] **Step 4: Update the RTM evidence with the observed numbers; commit.**

- [ ] **Step 5: Hand-off** — report to the owner: lite set results, mutation results, what remains (browser validation; independent Codex review). Do not mark COMPLETE.
