# ENH-008 — Parent Multi-School Linking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a `school_parent` account be linked to children at more than one school, deriving all parent authorization from `SchoolParentLink` rows instead of the single-valued `User.profile["school_id"]`.

**Architecture:** No schema/model/migration changes. Six small, independent backend edits in `apps/api/app/api/schools.py` and `apps/api/app/api/school_transfers.py` that each relax or remove a `profile.school_id`-based check for the `school_parent` role only; every other role's use of `profile.school_id` is untouched. Two small frontend additions (a `loading.tsx` each for two existing pages, reusing an existing CSS utility) and one small frontend UI grouping change. Each backend task is TDD: a failing test first, minimal fix, then a refactor pass.

**Tech Stack:** FastAPI + SQLAlchemy async + Postgres (backend, `apps/api/`), Next.js App Router server components (frontend, `apps/web/`), pytest + pytest-asyncio (backend tests), existing `enh005_helpers.py` fixtures.

**Spec:** `docs/superpowers/specs/2026-09-22-enh-008-parent-multi-school-design.md`

## Global Constraints

- Stay inside ENH-008 scope only — no unrelated refactors, no touching `school_coordinator`/`school_principal`/`school_teacher` handling of `profile.school_id` (unchanged for those roles everywhere).
- No new dependencies, no new Pydantic schemas, no new DB columns, no data migration/backfill.
- `TransferOutcome`'s `parents_moved`/`parents_kept` response fields keep their exact current names and shape — the new per-parent audit detail goes into `AuditLog.metadata_json` only, never into the HTTP response, so the API contract is untouched.
- Every `AuditLog.metadata_json` write in this codebase stores IDs and reason tokens only, never a name, email, or free-text reason (`school_transfers.py:_audit()`'s own docstring, security review S8) — any new metadata added here must follow that rule (parent UUIDs, never emails).
- Backend tests do NOT run against the host — this project's tests run inside a Docker container (`api-test`, built from `apps/api/Dockerfile.ci`) against Postgres/Redis reachable only on the internal Docker network. An isolated Postgres+Redis stack for this worktree is already up under Docker Compose project name `enh008-sdd` (brought up and migrated by the controller before dispatching Task 1) — do not start, stop, or rebuild this stack yourself; if a test run fails with a connection error, stop and report it rather than trying to fix the stack.
- Run backend tests from the **repository root** (not `apps/api/`): `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/<file>.py -v` (optionally `::test_name` on the file path, or `-k <pattern>`, for one test). The three `-v` mounts make an edit to `apps/api/app`, `apps/api/tests`, or `apps/api/alembic` visible to the container immediately, with no image rebuild needed. `testpaths = ["tests"]` and `asyncio_mode = "strict"` are already configured in `apps/api/pyproject.toml`. This exact pattern is precedented in `docs/superpowers/plans/2026-09-21-enh-005-student-school-transfer.md`'s own Global Constraints.
- **`MSYS_NO_PATHCONV=1` is not optional on this Windows/Git-Bash session.** Without it, Git Bash's automatic POSIX-to-Windows path conversion silently mangles the container-side half of every `-v host:container` argument — the mount does not error, it just does not take effect, and the container falls back to whatever was baked into the image at its last build (i.e. stale code from before this branch's edits). This produces a false-positive GREEN: pytest runs, passes, and reports a plausible-looking summary, but against old code. Confirmed directly (controller ran the identical command with and without the prefix on 2026-09-22: without it, the container saw a stale copy of `test_enh_005_scope.py` missing that session's newest test function entirely; with it, the mount was live and correct). Every implementer and reviewer subagent must use the prefix on every Docker test command, with no exceptions, and should verify a mount is live (e.g. `python -c "print('<a distinctive string only in your latest edit>' in open('/app/tests/<file>').read())"`) before trusting a PASS if anything about the result looks stale or surprising.
- Every task's commit is a separate commit on `feature/enh-008-parent-multi-school-link` (already created, currently at `main`'s HEAD after the spec-doc commit).

---

### Task 1: `_parent_email_conflict()` — drop the cross-school comparison

**Files:**
- Modify: `apps/api/app/api/schools.py:600-609`
- Test: `apps/api/tests/test_enh_005_scope.py:114-122` (rewrite `test_adding_a_student_refuses_a_parent_email_that_belongs_to_another_school`)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_parent_email_conflict(db: AsyncSession, *, parent_email: str) -> str | None` — **signature changes** (drops the `school_id` keyword argument entirely, since it becomes unused; Task 2 and the existing `_link_or_invite_parent()` caller at `schools.py:624` both update their call sites in this task).

- [ ] **Step 1: Write the failing test**

Replace the existing test in `apps/api/tests/test_enh_005_scope.py` (currently asserts `422`):

```python
@pytest.mark.asyncio
async def test_adding_a_student_at_school_a_can_use_a_parent_already_linked_at_school_b(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    await login(client, a["coordinator"].email)
    name = f"Cross Link {uuid.uuid4().hex[:6]}"

    response = await client.post("/api/v1/school/students", json={"full_name": name, "parent_email": b["parent"].email})

    assert response.status_code == 201, response.text
    assert response.json()["parent_status"] == "linked"
    student = await db_session.scalar(select(SchoolStudent).where(SchoolStudent.full_name == name))
    assert student is not None
    link = await db_session.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == b["parent"].id, SchoolParentLink.school_student_id == student.id))
    assert link is not None
```

(`SchoolParentLink` is already imported at the top of this file, per line 9's existing import list.)

- [ ] **Step 2: Run test to verify it fails**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py::test_adding_a_student_at_school_a_can_use_a_parent_already_linked_at_school_b -v` (from the repository root)
Expected: FAIL — `assert response.status_code == 201` fails because the server still returns `422` (today's cross-school rejection).

- [ ] **Step 3: Write minimal implementation**

In `apps/api/app/api/schools.py`, replace lines 600-609:

```python
async def _parent_email_conflict(db: AsyncSession, *, parent_email: str) -> str | None:
    """None means the email is safe to use as a parent_email (either genuinely new, or
    already a school_parent account at any school); a string explains why it can't be --
    an existing account under that email with a role other than school_parent. Shared by
    single-add/edit (raises 422) and bulk upload (rejects just that row, `SCH-002-AC04`'s
    never-block-the-batch discipline)."""
    existing_user = await db.scalar(select(User).where(User.email == parent_email))
    if existing_user and existing_user.role != "school_parent":
        return f"parent_email '{parent_email}' belongs to an existing account that is not a Parent"
    return None
```

Update its one existing caller, `_link_or_invite_parent()` at `schools.py:624`, to drop the now-removed keyword argument:

```python
    conflict = await _parent_email_conflict(db, parent_email=parent_email)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py::test_adding_a_student_at_school_a_can_use_a_parent_already_linked_at_school_b -v`
Expected: PASS

- [ ] **Step 5: Verify the AC4 regression pin still passes unchanged**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_sch_roster_parent_invite.py::test_parent_email_belonging_to_a_non_parent_account_is_rejected -v`
Expected: PASS, with no code change to that test — this is the "must not regress" check for AC4 (a non-`school_parent` email, e.g. an `academic_team` member's, is still rejected). If it fails, the role-mismatch branch in Step 3 was written incorrectly — do not weaken this test to make it pass.

- [ ] **Step 6: Refactor — none needed beyond Step 3's signature cleanup**

The signature change in Step 3 (dropping the dead `school_id` parameter) *is* this task's refactor — done inline rather than as a separate pass, since leaving an unused parameter on a function whose whole point just changed would be more confusing to fix in two steps than one. Re-run Steps 2, 4, 5's commands once more to confirm nothing regressed.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_005_scope.py
git commit -m "feat(enh-008): allow linking a parent already registered at another school"
```

---

### Task 2: `link_parent()` — delegate to `_parent_email_conflict()`

**Files:**
- Modify: `apps/api/app/api/schools.py:1195-1215`
- Test: `apps/api/tests/test_enh_005_scope.py:106-111` (rewrite `test_link_parent_refuses_a_parent_from_another_school`)

**Interfaces:**
- Consumes: `_parent_email_conflict(db, *, parent_email)` from Task 1.
- Produces: no change to `link_parent()`'s route signature or response shape — still `POST /school/students/{student_id}/parents`, `201` with `{"id", "parent_user_id", "school_student_id"}`.

- [ ] **Step 1: Write the failing test**

Replace the existing test in `apps/api/tests/test_enh_005_scope.py` (currently asserts `422`):

```python
@pytest.mark.asyncio
async def test_link_parent_accepts_a_parent_already_linked_at_another_school(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    await login(client, a["coordinator"].email)

    response = await client.post(f"/api/v1/school/students/{a['students'][0].id}/parents", json={"parent_email": b["parent"].email})

    assert response.status_code == 201, response.text
    link = await db_session.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == b["parent"].id, SchoolParentLink.school_student_id == a["students"][0].id))
    assert link is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py::test_link_parent_accepts_a_parent_already_linked_at_another_school -v`
Expected: FAIL — `422` today.

- [ ] **Step 3: Write minimal implementation**

Replace `apps/api/app/api/schools.py:1195-1215`:

```python
@router.post("/students/{student_id}/parents", status_code=201)
async def link_parent(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(404, "Student not found")
    parent_email = str(payload.get("parent_email", "")).lower().strip()
    conflict = await _parent_email_conflict(db, parent_email=parent_email)
    if conflict:
        raise HTTPException(422, conflict)
    parent = await db.scalar(select(User).where(User.email == parent_email, User.role == "school_parent"))
    if not parent:
        raise HTTPException(422, "parent_email must belong to an existing Parent account")
    existing = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == parent.id, SchoolParentLink.school_student_id == student.id))
    if existing:
        raise HTTPException(409, "This parent is already linked to this student")
    link = SchoolParentLink(parent_user_id=parent.id, school_student_id=student.id, linked_by_user_id=user.id)
    db.add(link)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.parent_link", entity_type="school_parent_link", entity_id=str(link.id), metadata_json={"student_id": str(student.id), "parent_id": str(parent.id)}))
    await db.commit()
    return {"id": link.id, "parent_user_id": parent.id, "school_student_id": student.id}
```

Note the two checks: `_parent_email_conflict()` alone would treat "no account with this email at all" as safe (`None`, since it's designed for `_link_or_invite_parent()`'s invite fallback) — `link_parent()` has no invite fallback, so the separate `if not parent:` check after it is required, not redundant.

- [ ] **Step 4: Run test to verify it passes**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py::test_link_parent_accepts_a_parent_already_linked_at_another_school -v`
Expected: PASS

- [ ] **Step 5: Verify existing "not found at all" and "wrong role" cases still 422**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py -v` (whole file) and `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_sch_roster_parent_invite.py -v` (whole file)
Expected: all PASS. This confirms `link_parent()`'s split-check design (Step 3) didn't silently let an unknown email or a wrong-role email through.

- [ ] **Step 6: Refactor**

None needed — Step 3's code is already the minimal, final form (no duplicate conflict logic remains between `link_parent()` and `_link_or_invite_parent()`, satisfying the spec's dedup goal).

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_005_scope.py
git commit -m "feat(enh-008): link_parent() delegates conflict check to _parent_email_conflict()"
```

---

### Task 3: `_load_readable_student()`, `list_students()`, `_readable_students()` — stop gating parent reads on `_own_school_id()`

**Files:**
- Modify: `apps/api/app/api/schools.py:643 (_scoped_students_query type hint), 835-840, 870-889, 1536-1543`
- Test: `apps/api/tests/test_enh_005_scope.py:41-53` (rewrite `test_a_parent_still_cannot_read_an_unlinked_student_and_keeps_todays_messages`), plus two new tests

**Interfaces:**
- Consumes: `_scoped_students_query(db, user, school_id)` (existing, from `schools.py:643`).
- Produces: `_scoped_students_query(db: AsyncSession, user: User, school_id: UUID | None)` — **type hint widens** from `UUID` to `UUID | None` (no behavior change: the parent branch inside it already ignores `school_id`).

- [ ] **Step 1: Write the failing tests**

This task changes an existing test's expected message (found during planning: `_load_readable_student()` uses `school_id` only to pick between two 403 message variants for a parent, and once a parent has no single "own school" that distinction stops making sense). Replace `test_a_parent_still_cannot_read_an_unlinked_student_and_keeps_todays_messages` in `apps/api/tests/test_enh_005_scope.py`:

```python
@pytest.mark.asyncio
async def test_a_parent_still_cannot_read_an_unlinked_student(client, db_session):
    a = await mk_school(db_session, label="A", students=2)
    b = await mk_school(db_session, label="B")
    same_school_unlinked = a["students"][1]
    other_school = b["students"][0]
    await login(client, a["parent"].email)

    r = await client.get(f"/api/v1/school/students/{same_school_unlinked.id}")
    assert (r.status_code, r.json()["detail"]) == (403, NOT_LINKED)
    r = await client.get(f"/api/v1/school/students/{other_school.id}")
    assert (r.status_code, r.json()["detail"]) == (403, NOT_LINKED)
    listing = await client.get("/api/v1/school/students")
    assert [s["id"] for s in listing.json()] == [str(a["students"][0].id)]
```

Confirmed by reading the full file during planning: `DIFFERENT_INSTITUTION` (line 15) is referenced only at the line being replaced above (line 51) — delete the `DIFFERENT_INSTITUTION = "This student is at a different institution"` constant definition at line 15 entirely. Keep `NOT_LINKED` (line 14), which stays in use.

Add two new tests to the same file:

```python
@pytest.mark.asyncio
async def test_a_parent_with_children_at_two_schools_sees_both(client, db_session):
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    db_session.add(SchoolParentLink(parent_user_id=a["parent"].id, school_student_id=b["students"][0].id, linked_by_user_id=b["coordinator"].id))
    await db_session.commit()
    await login(client, a["parent"].email)

    listing = await client.get("/api/v1/school/students")

    assert {s["id"] for s in listing.json()} == {str(a["students"][0].id), str(b["students"][0].id)}
    for student in (a["students"][0], b["students"][0]):
        assert (await client.get(f"/api/v1/school/students/{student.id}")).status_code == 200


@pytest.mark.asyncio
async def test_a_parent_with_zero_links_at_a_school_sees_none_of_its_data(client, db_session):
    a = await mk_school(db_session, label="A", students=0)
    b = await mk_school(db_session, label="B")
    await login(client, a["parent"].email)

    listing = await client.get("/api/v1/school/students")

    assert listing.json() == []
    assert (await client.get(f"/api/v1/school/students/{b['students'][0].id}")).status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py -k "unlinked or two_schools or zero_links" -v`
Expected: `test_a_parent_with_children_at_two_schools_sees_both` FAILs (today's `_own_school_id()` 403s before the cross-school link is even considered, since `a["parent"]`'s `profile.school_id` is School A but they're now also linked at School B); the rewritten `test_a_parent_still_cannot_read_an_unlinked_student` FAILs on its second assertion (today still returns `DIFFERENT_INSTITUTION`, not `NOT_LINKED`); `test_a_parent_with_zero_links_at_a_school_sees_none_of_its_data` currently PASSES already (not a new failure) — note this and move on, it's a valid regression guard even though it doesn't newly fail.

- [ ] **Step 3: Write minimal implementation**

In `apps/api/app/api/schools.py`, widen the type hint at line 643:

```python
async def _scoped_students_query(db: AsyncSession, user: User, school_id: UUID | None):
```

Replace `list_students()` (lines 835-840):

```python
@router.get("/students")
async def list_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = None if user.role == "school_parent" else _own_school_id(user)
    stmt = await _scoped_students_query(db, user, school_id)
    rows = (await db.scalars(stmt.order_by(SchoolStudent.full_name.asc()))).all()
    return [_student_out(s) for s in rows]
```

Replace `_load_readable_student()` (lines 870-889):

```python
async def _load_readable_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """One student, checked against the acting School role's own scope (SCH-001-AC02/AC03):
    own institution for every role, plus assigned-only for Teacher and own-child-only for
    Parent -- the same rule as the list, applied to a direct record ID. ENH-005/ENH-008: a
    Parent is scoped by their links alone (see `_scoped_students_query`), never by a single
    "own school" -- a Parent can legitimately have links at more than one school, so there is
    no single institution left to distinguish "wrong institution" from "not linked" against;
    an unlinked student always gets the one generic message below."""
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if user.role == "school_parent":
        linked = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == user.id, SchoolParentLink.school_student_id == student.id))
        if not linked:
            raise HTTPException(403, "This student is not linked to your account")
        return student
    school_id = _own_school_id(user)
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    if user.role == "school_teacher" and student.assigned_teacher_user_id != user.id:
        raise HTTPException(403, "This student is not assigned to you")
    return student
```

Replace `_readable_students()` (lines 1536-1543):

```python
async def _readable_students(db: AsyncSession, user: User) -> set:
    """The set of school_student_id values this reading role (Coordinator/Principal/
    Teacher/Parent) may see published/visible service-delivery content for -- reuses the
    exact same scoping as SCH-001's own roster access, since it's the same underlying
    own-institution/assigned/own-child rule (SCH-001-AC02/AC03)."""
    school_id = None if user.role == "school_parent" else _own_school_id(user)
    stmt = await _scoped_students_query(db, user, school_id)
    return set((await db.scalars(stmt.with_only_columns(SchoolStudent.id))).all())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_scope.py -v` (whole file)
Expected: all PASS, including `test_teacher_and_principal_scopes_are_unchanged_by_the_parent_change` and `test_a_parent_reads_a_linked_child_who_lives_at_another_school` (both must keep passing unmodified — they exercise the staff-role and single-link-elsewhere-school branches, which Step 3 does not touch).

- [ ] **Step 5: Refactor**

None needed — the three call sites now consistently follow the same `None if user.role == "school_parent" else _own_school_id(user)` pattern; no further extraction is justified for three short, already-readable lines (would be an unnecessary abstraction for this size).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_005_scope.py
git commit -m "feat(enh-008): stop gating parent reads on a single profile.school_id"
```

---

### Task 4: `accept_invite()` — stop writing `profile.school_id` for `school_parent` invites

**Files:**
- Modify: `apps/api/app/api/schools.py:225-234`
- Test: `apps/api/tests/test_sch_roster_parent_invite.py` (new test)

**Interfaces:**
- Consumes: nothing new.
- Produces: no change to `accept_invite()`'s route signature or response shape (`{"id", "email", "role"}`, confirmed by reading the full function body — it never returns `profile`, so no consumer-visible change).

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_sch_roster_parent_invite.py`, following the exact same invite-then-accept pattern as the existing `test_accept_flow_links_every_student_with_the_same_pending_email` (lines 86-112 of that file): create a student with a `parent_email` to trigger an invite, read the `development_invite_token` off the response, log out, then accept it.

```python
@pytest.mark.asyncio
async def test_accepting_a_parent_invite_does_not_set_profile_school_id(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    parent_email = f"sch-roster-parent-{uuid.uuid4().hex[:8]}@example.local"

    created = await client.post("/api/v1/school/students", json={"full_name": "Profile Check Student", "parent_email": parent_email})
    assert created.status_code == 201, created.text
    token = created.json()["development_invite_token"]

    await client.post("/api/v1/auth/logout")
    accept = await client.post(f"/api/v1/school/invites/{token}/accept", json={"password": PASSWORD})
    assert accept.status_code == 201, accept.text

    account = await db_session.scalar(select(User).where(User.id == uuid.UUID(accept.json()["id"])))
    assert account.profile == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_sch_roster_parent_invite.py::test_accepting_a_parent_invite_does_not_set_profile_school_id -v`
Expected: FAIL — `account.profile == {"school_id": "<uuid>"}` today, not `{}`.

- [ ] **Step 3: Write minimal implementation**

In `apps/api/app/api/schools.py`, replace the `profile=` line inside `accept_invite()`'s `User(...)` construction (line 233):

```python
        profile={} if invite.role == "school_parent" else {"school_id": str(invite.school_id)},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_sch_roster_parent_invite.py -v` (whole file)
Expected: all PASS, including every non-parent-role accept-invite test already in this file (unaffected — they still get `profile={"school_id": ...}`).

- [ ] **Step 5: Refactor**

None needed.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_sch_roster_parent_invite.py
git commit -m "feat(enh-008): stop writing profile.school_id for newly-provisioned parent accounts"
```

---

### Task 5: `school_transfers.py:_approve()` — remove the parent profile-write and per-parent audit row, preserve response shape and locking

**Files:**
- Modify: `apps/api/app/api/school_transfers.py:76 (remove ACTION_SCOPE_CHANGED), 407-427, 446`
- Test: `apps/api/tests/test_enh_005_approve.py` (rewrite 3 tests), `apps/api/tests/test_enh_005_concurrency.py` (rewrite 2 tests)

**Interfaces:**
- Consumes: `_audit(db, actor_id, action, entity_id, *, outcome="recorded", **metadata)` (existing, `school_transfers.py:80`).
- Produces: `_approve()`'s return signature and `request.outcome` dict shape are **unchanged** (`{"parents_moved": int, "parents_kept": int, "results_withdrawn": int, "teacher_cleared": bool, "pending_parent_email_cleared": bool}`) — only the *mechanism* behind `parents_moved`/`parents_kept` changes, from a write-then-count to a read-only count. The `ACTION_TRANSFER` `AuditLog` row gains two new metadata keys: `parents_moved_ids: list[str]`, `parents_kept_ids: list[str]` (parent UUIDs as strings, never emails).

- [ ] **Step 1: Write the failing tests**

Three edits to `apps/api/tests/test_enh_005_approve.py`:

**(a)** Replace `test_a_parent_moves_only_when_no_other_child_remains_and_every_link_is_kept` (lines 131-144) — drop the two `profile["school_id"]` assertions (they described a write that no longer happens), keep everything else (link preservation and cross-account readability are the actual behavior this test protects):

```python
@pytest.mark.asyncio
async def test_a_parent_moves_only_when_no_other_child_remains_and_every_link_is_kept(client, db_session, world):
    w = world
    await _approve(client, w)

    p1, p2 = await _fresh(db_session, User, w["p1"].id), await _fresh(db_session, User, w["p2"].id)
    assert p1.profile.get("school_id") == str(w["a"]["school"].id)  # never written to -- stays exactly as created
    assert p2.profile.get("school_id") == str(w["a"]["school"].id)
    links = {(row.parent_user_id, row.school_student_id) for row in (await db_session.scalars(select(SchoolParentLink).where(SchoolParentLink.school_student_id == w["kid"].id))).all()}
    assert links == {(w["p1"].id, w["kid"].id), (w["p2"].id, w["kid"].id)}
    for parent in (w["p1"], w["p2"]):  # both can still read the child, wherever their account is
        await login(client, parent.email)
        assert (await client.get(f"/api/v1/school/students/{w['kid'].id}")).status_code == 200
    await login(client, w["p2"].email)
    assert {row["id"] for row in (await client.get("/api/v1/school/students")).json()} == {str(w["kid"].id), str(w["sibling"].id)}
```

**(b)** Replace `test_approval_writes_only_profile_school_id_on_parent_accounts` (lines 148-167) — rename it, since nothing writes to any linked account anymore, and extend `snapshot()` to cover `profile` for full-row before/after equality:

```python
@pytest.mark.asyncio
async def test_approval_writes_nothing_on_any_linked_user_account(client, db_session, world):
    w = world
    odd = await mk_user(db_session, role="school_teacher", name="Teacher wrongly linked as a parent", school_id=w["a"]["school"].id, assigned_by=w["a"]["coordinator"])
    await db_session.flush()
    db_session.add(SchoolParentLink(parent_user_id=odd.id, school_student_id=w["kid"].id, linked_by_user_id=w["a"]["coordinator"].id))
    await db_session.commit()
    linked = [w["p1"].id, w["p2"].id, odd.id]

    async def snapshot():
        out = {}
        for uid in linked:
            u = await _fresh(db_session, User, uid)
            assignments = (await db_session.scalars(select(UserRoleAssignment).where(UserRoleAssignment.user_id == uid))).all()
            out[uid] = (u.role, u.division, u.active, u.email, u.password_hash, u.full_name, u.profile, sorted((x.role, x.division, x.is_active, x.approval_status) for x in assignments))
        return out

    before = await snapshot()
    assert (await _approve(client, w)).status_code == 200
    assert await snapshot() == before
```

**(c)** Replace `test_audit_rows_are_written_for_the_transfer_and_for_each_moved_parent` (lines 261-277) — the per-parent `school.user_school_scope_changed` rows disappear; the parent IDs now live in the transfer's own audit metadata:

```python
@pytest.mark.asyncio
async def test_audit_row_names_the_moved_and_kept_parents_and_leaks_nothing_else(client, db_session, world):
    w = world
    assert (await _approve(client, w)).status_code == 200

    transfer = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.student_transfer", AuditLog.entity_id == str(w["request"].id)))).all()
    assert len(transfer) == 1 and transfer[0].user_id == w["admin"].id and transfer[0].outcome == "recorded"
    meta = transfer[0].metadata_json
    assert meta["parents_moved"] == 1 and meta["parents_kept"] == 1 and "request_id" in meta
    assert meta["parents_moved_ids"] == [str(w["p1"].id)]
    assert meta["parents_kept_ids"] == [str(w["p2"].id)]
    no_scope_rows = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.user_school_scope_changed"))
    assert no_scope_rows == 0  # the old per-parent audit action is no longer written at all
    blob = json.dumps([x.metadata_json for x in transfer])
    assert w["kid"].full_name not in blob and w["kid"].student_code not in blob and "Family is moving" not in blob
```

**(d)** In `test_a_failure_inside_the_transaction_leaves_everything_exactly_as_it_was` (lines 281-303), delete line 303 (`assert await db_session.scalar(select(func.count())...action == "school.user_school_scope_changed"...) == 0`) — the action no longer exists at all, so this line would test nothing; leave every other assertion in that test as-is (they cover the real point of the test, which is that the whole transaction rolls back on the final audit write's failure, including the student move, teacher/pending-email clearing, and result status).

Two edits to `apps/api/tests/test_enh_005_concurrency.py`:

**(e)** In `test_two_simultaneous_approvals_of_one_request_one_wins_and_one_is_409` (lines 108-120), replace line 119's `moved` count query and line 120's assertion:

```python
    winner = next(r for r in results if r.status_code == 200)
    assert winner.json()["outcome"]["parents_moved"] == 1
```

(keep lines 116-118 exactly as they are — the `[200, 409]` status check and the student's final `school_id` check are unaffected by this change).

**(f)** Replace `test_two_siblings_transferred_at_once_leave_their_shared_parent_at_the_new_school_with_both_links` (lines 158-181) — the `profile["school_id"]` assertion and the `ACTION_SCOPE_CHANGED` count both go; replace with the same "exactly one moved, one kept, across the two responses" proof read from each response body, since the row lock on the shared parent (unchanged, still held) is what still guarantees this split:

```python
@pytest.mark.asyncio
async def test_two_siblings_transferred_at_once_leave_their_shared_parent_at_the_new_school_with_both_links(db_session):
    a = await mk_school(db_session, label="A", students=0)
    b = await mk_school(db_session, label="B", students=0)
    kids = [await mk_student(db_session, a["school"], a["coordinator"], f"sib{i}") for i in range(2)]
    parent = await mk_user(db_session, role="school_parent", name="Shared parent", school_id=a["school"].id, assigned_by=a["coordinator"])
    await db_session.flush()
    db_session.add_all([SchoolParentLink(parent_user_id=parent.id, school_student_id=k.id, linked_by_user_id=a["coordinator"].id) for k in kids])
    await db_session.commit()
    requests = [await mk_request(db_session, k, from_school=a["school"], to_school=b["school"], filed_by_school=a["school"], requester=a["coordinator"]) for k in kids]

    async with _client_for(a["admin"].email) as one, _client_for(a["admin"].email) as two:
        async with _held(User, parent.id):  # both approvals reach the shared parent's row and queue there
            tasks = [asyncio.create_task(c.post(APPROVE.format(rid=r.id))) for c, r in ((one, requests[0]), (two, requests[1]))]
            await asyncio.sleep(0.7)
        results = await asyncio.gather(*tasks)

    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert (await _fresh(db_session, User, parent.id)).profile.get("school_id") == str(a["school"].id)  # never written to
    for kid in kids:
        assert (await _fresh(db_session, SchoolStudent, kid.id)).school_id == b["school"].id
    links = await db_session.scalar(select(func.count()).select_from(SchoolParentLink).where(SchoolParentLink.parent_user_id == parent.id))
    assert links == 2
    total_moved = sum(r.json()["outcome"]["parents_moved"] for r in results)
    total_kept = sum(r.json()["outcome"]["parents_kept"] for r in results)
    assert (total_moved, total_kept) == (1, 1)  # serialised on the parent: the first approval saw the sibling still at A (kept), the second found none left (moved)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_approve.py tests/test_enh_005_concurrency.py -v`
Expected: the 5 rewritten tests FAIL against today's code (the profile-write/audit-row-based assertions no longer match what the new test bodies expect); every other test in both files still PASSes (they don't touch this behavior).

- [ ] **Step 3: Write minimal implementation**

In `apps/api/app/api/school_transfers.py`, remove the now-dead constant at line 76:

```python
ACTION_TRANSFER = "school.student_transfer"
```

(delete the `ACTION_SCOPE_CHANGED = "school.user_school_scope_changed"` line entirely — confirmed its only other reference, the per-parent `_audit()` call below, is also being removed in this same step).

Replace the parent loop, lines 407-427:

```python
    # Parents (D1): the link is never touched. An account at the losing school whose only child there was this student follows the
    # child conceptually (this and every other place a Parent's data is scoped reads that from SchoolParentLink alone, per ENH-008) --
    # nothing is written to the parent's own account. The row lock below still matters: it's what makes two siblings transferred at
    # once serialise on their shared parent, so the moved/kept read below sees a consistent view (security review S2/S4).
    linked = select(SchoolParentLink.parent_user_id).where(SchoolParentLink.school_student_id == student.id)
    parents = (await db.scalars(select(User).where(User.id.in_(linked)).order_by(User.id).with_for_update())).all()
    moved_parent_ids: list[str] = []
    kept_parent_ids: list[str] = []
    for parent in parents:
        if parent.role != "school_parent":
            continue
        others_at_from = await db.scalar(
            select(func.count())
            .select_from(SchoolParentLink)
            .join(SchoolStudent, SchoolStudent.id == SchoolParentLink.school_student_id)
            .where(SchoolParentLink.parent_user_id == parent.id, SchoolStudent.school_id == request.from_school_id, SchoolStudent.id != student.id)
        )
        if others_at_from:
            kept_parent_ids.append(str(parent.id))
        else:
            moved_parent_ids.append(str(parent.id))
    moved, kept = len(moved_parent_ids), len(kept_parent_ids)
```

Update the final `_audit()` call, line 446 (`request.outcome` is assigned just above this, unchanged in shape — only the `_audit(...)` call itself gains two kwargs):

```python
    _audit(db, admin_id, ACTION_TRANSFER, request.id, from_school_id=from_id, to_school_id=to_id, parents_moved_ids=moved_parent_ids, parents_kept_ids=kept_parent_ids, **request.outcome)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_enh_005_approve.py tests/test_enh_005_concurrency.py -v`
Expected: all PASS, including the 6 untouched tests in `test_enh_005_approve.py` (`test_only_overseas_admin_and_super_admin_may_approve...`, `test_approval_moves_the_student_and_flips_every_scope`, `test_the_teacher_assignment_and_pending_parent_email_are_cleared_and_the_grade_is_kept` — its `outcome` dict assertion at line 122 should pass with identical values, computed a different way — `test_in_flight_results_are_withdrawn_with_history_and_published_ones_stay`, `test_career_psychometric_test_prep_and_language_records_follow_the_student_unchanged`, `test_a_second_approval_a_stale_request_and_an_unknown_id_change_nothing`, `test_a_stale_request_is_409_and_stays_pending`, `test_a_rejected_or_cancelled_request_cannot_be_approved`, `test_notifications_go_out_after_the_commit_and_a_failure_never_undoes_the_approval`, `test_a_lock_wait_past_the_timeout_is_409_and_changes_nothing`) and every untouched test in `test_enh_005_concurrency.py`.

- [ ] **Step 5: Refactor**

None needed — `moved, kept = len(moved_parent_ids), len(kept_parent_ids)` already avoids the previous duplicate-counter pattern in one pass.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/school_transfers.py apps/api/tests/test_enh_005_approve.py apps/api/tests/test_enh_005_concurrency.py
git commit -m "feat(enh-008): transfer approval stops re-scoping parent accounts, audits parent ids instead"
```

---

### Task 6: Backend regression gate

**Files:** none changed — verification only.

- [ ] **Step 1: Run the targeted School-domain regression suite**

Run from the repository root:

```bash
MSYS_NO_PATHCONV=1 docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh008-sdd --profile ci run --rm --no-deps -v "$(pwd)/apps/api/app:/app/app" -v "$(pwd)/apps/api/tests:/app/tests" -v "$(pwd)/apps/api/alembic:/app/alembic" api-test python -m pytest tests/test_sch_001_school_portal_access.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_011_entitlements.py tests/test_sch_roster_parent_invite.py tests/test_enh_004_student_promotion.py tests/test_enh_005_scope.py tests/test_enh_005_approve.py tests/test_enh_005_concurrency.py tests/test_enh_005_hardening.py -v
```

Expected: all PASS. This is the spec's named targeted gate (§8), run now rather than deferred to the project's usual batched 3-4-feature cadence, since this is an authorization-model change.

- [ ] **Step 2: If anything fails**

Do not weaken an assertion to make it pass — a failure here means either a call site to `_own_school_id()`, `profile.school_id`, or `ACTION_SCOPE_CHANGED` was missed in Tasks 1-5 (re-check with `grep -rn "ACTION_SCOPE_CHANGED\|profile.*school_id" apps/api/app/api/schools.py apps/api/app/api/school_transfers.py` for anything not yet touched) or a test's fixture setup exposed a real gap in the design — stop and report which specific test failed and why before adjusting either the implementation or the test.

- [ ] **Step 3: Commit (only if Step 2 required a fix)**

```bash
git add -A
git commit -m "fix(enh-008): <describe the specific regression found and fixed>"
```

---

### Task 7: Frontend — `loading.tsx` for the parent dashboard and child-detail pages

**Files:**
- Create: `apps/web/app/school/parent/dashboard/loading.tsx`
- Create: `apps/web/app/school/parent/children/[id]/loading.tsx`

**Interfaces:**
- Consumes: the existing `.skeleton-line` CSS class (`apps/web/app/controls.css:46-48`) — already defined, already `prefers-reduced-motion`-safe, not modified by this task.
- Produces: nothing consumed by other tasks — these are Next.js App Router convention files, picked up automatically as the Suspense fallback while their sibling `page.tsx` resolves.

This task has no backend/API surface to TDD against (it's a static loading skeleton), so it follows a lighter verify-by-running cycle instead of RED/GREEN against pytest.

- [ ] **Step 1: Create the dashboard loading skeleton**

```tsx
import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading your children">
        <h1>My children</h1>
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "60%" }} /></div>
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "60%" }} /></div>
      </div>
    </PortalShell>
  );
}
```

Save as `apps/web/app/school/parent/dashboard/loading.tsx`.

- [ ] **Step 2: Create the child-detail loading skeleton**

```tsx
import PortalShell from "@/components/PortalShell";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return (
    <PortalShell nav={SCHOOL_NAV.parent} roleLabel="Parent" userName="">
      <div className="portal-content" aria-busy="true" aria-label="Loading this child's profile">
        <div className="card"><div className="skeleton-line" style={{ marginBottom: 10 }} /><div className="skeleton-line" style={{ width: "40%" }} /></div>
      </div>
    </PortalShell>
  );
}
```

Save as `apps/web/app/school/parent/children/[id]/loading.tsx`.

- [ ] **Step 3: Verify in the browser**

This step requires the dev server (`npm run dev` in `apps/web/`, or however this project's dev server is normally started — check `apps/web/package.json`'s `scripts` if unsure) and is part of the browser-validation pass the user has already said is still owed after implementation, not something to claim complete from reading the code alone. Confirm: the skeleton briefly appears on a hard navigation to `/school/parent/dashboard` and to `/school/parent/children/<id>` (throttle the network in devtools if it resolves too fast to see), then is replaced by the real content with no layout jump.

- [ ] **Step 4: Commit**

```bash
git add apps/web/app/school/parent/dashboard/loading.tsx apps/web/app/school/parent/children/\[id\]/loading.tsx
git commit -m "feat(enh-008): add loading skeletons to the parent dashboard and child-detail pages"
```

---

### Task 8: Frontend — group dashboard child cards by school when a parent spans schools

**Files:**
- Modify: `apps/web/app/school/parent/dashboard/page.tsx`

**Interfaces:**
- Consumes: `childrenSpanSchools()` (existing, `apps/web/components/SchoolChildOverview.tsx:33-35`) — not modified.
- Produces: no change to any exported interface — this is a render-only change inside the page component.

- [ ] **Step 1: Modify the render to group by school when `multiSchool` is true**

In `apps/web/app/school/parent/dashboard/page.tsx`, replace the `children.map((c, i) => {...})` block (current lines 50-73) with a version that groups by `o?.student.school_name` when `multiSchool` is true, and renders exactly as before (a flat list, no headings) when it's false:

```tsx
        {children.length === 0 ? (
          <div className="card">
            <p className="muted">No child linked to your account yet. Contact your school to get set up.</p>
          </div>
        ) : (
          (() => {
            const cards = children.map((c, i) => {
              const o = overviews[i];
              return (
                <div className="card" key={c.id} data-testid={`child-card-${c.id}`}>
                  <h2>{c.full_name} <span className="muted" style={{ fontSize: 14 }}>({c.student_code})</span></h2>
                  <p><strong>Grade/Class:</strong> {c.grade_or_class || "-"}</p>
                  <p><strong>Date of birth:</strong> {formatDate(c.date_of_birth)}</p>
                  {multiSchool && o?.student.school_name && <p><strong>School:</strong> {o.student.school_name}</p>}
                  {o ? (
                    <>
                      <p><strong>Class teacher:</strong> {o.student.assigned_teacher_name || "Not assigned yet"}</p>
                      <ChildStatusRow overview={o} />
                      {o.recommended_careers.length > 0 && (
                        <p><strong>Recommended careers:</strong> {o.recommended_careers.map((r) => <span className="badge" key={r.id} style={{ marginRight: 6 }}>{r.notes}</span>)}</p>
                      )}
                    </>
                  ) : (
                    <p className="muted">Progress details are unavailable right now.</p>
                  )}
                  <a className="btn" href={`/school/parent/children/${c.id}`}>View full profile &amp; progress</a>
                </div>
              );
            });
            if (!multiSchool) return cards;
            const bySchool = new Map<string, typeof cards>();
            children.forEach((c, i) => {
              const school = overviews[i]?.student.school_name || "Other";
              bySchool.set(school, [...(bySchool.get(school) ?? []), cards[i]]);
            });
            return [...bySchool.entries()].map(([school, group]) => (
              <div key={school}>
                <h2 style={{ marginTop: 24 }}>{school}</h2>
                {group}
              </div>
            ));
          })()
        )}
```

Note: once grouped, the per-card `{multiSchool && ... <p><strong>School:</strong> ...}` line becomes redundant with its new group heading — remove that `<p>` from inside the card in the grouped branch to avoid saying the school name twice. Simplest correct approach: keep the per-card line only when `!multiSchool` is never true anyway (it's already gated on `multiSchool`) — since grouping only happens when `multiSchool` is true, drop that conditional `<p>` entirely now that the group heading always covers it:

```tsx
                  <p><strong>Grade/Class:</strong> {c.grade_or_class || "-"}</p>
                  <p><strong>Date of birth:</strong> {formatDate(c.date_of_birth)}</p>
                  {o ? (
```

(i.e. delete the `{multiSchool && o?.student.school_name && <p><strong>School:</strong> ...}</p>}` line from inside each card entirely, since the group heading now carries that information whenever it would have shown).

- [ ] **Step 2: Verify in the browser**

Also part of the browser-validation pass owed after implementation. Confirm both states: a single-school parent's dashboard renders identically to before (flat list, no group headings, no visual change) — check this against a parent fixture with one school; a multi-school parent's dashboard (created via Task 3's new backend behavior) shows cards grouped under a heading per school.

- [ ] **Step 3: Commit**

```bash
git add apps/web/app/school/parent/dashboard/page.tsx
git commit -m "feat(enh-008): group dashboard child cards by school for multi-school parents"
```

---

## After this plan

Per the user's explicit instruction, implementation completion must not be claimed on its own — two things are still owed after all 8 tasks are done and committed:

1. **Browser validation** — Tasks 7 and 8 each have an explicit in-browser verification step; additionally, exercise the full flow end-to-end in a real browser: a coordinator at School B links a parent already registered at School A, log in as that parent, confirm both children appear correctly attributed to their own school, confirm a parent with zero links at a school sees none of its data.
2. **Independent Codex review** — a separate review pass, outside this session, before this branch is considered ready to merge.
