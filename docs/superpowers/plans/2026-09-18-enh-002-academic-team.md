# ENH-002 Academic Team Completeness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the missing `teacher_remarks` field to `SchoolAcademicResult` and close the "view academic progress" gap with a new portfolio-wide aggregate endpoint, completing the Academic Team role's confirmed capability list (`EVID-014` §13) without touching the already-correct `DEC-ROLE-007` separation logic.

**Architecture:** Two additive backend changes riding entirely on existing patterns — one nullable column surfaced through the existing single `_result_out()` serializer (already shared by three read endpoints), and one new read-only aggregate endpoint reusing the existing `_portfolio_school_ids()` scoping helper with no new table. Frontend changes extend two existing panels and add one new read-only presentational component, matching this codebase's server-component-by-default, no-component-library, no-client-fetch-library conventions.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + PostgreSQL (backend); Next.js App Router + React server/client components, hand-rolled CSS utility classes (frontend); pytest + pytest-asyncio (backend tests).

**Spec:** This conversation's approved design (brainstorming + `api-and-interface-design` + `frontend-ui-engineering` + `security-and-hardening` review passes). No separate spec file was written — this was run as a bounded-path design per `superpowers:brainstorming`, with full design ceremony captured in chat and here.

## Global Constraints

- Stay inside ENH-002 scope: do not touch `_advance_result()`, `verify_academic_result()`, `publish_academic_result()`, or any `DEC-ROLE-007` separation logic.
- Reuse existing helpers: `_portfolio_school_ids()`, `_student_in_portfolio()`, `_result_out()` — do not duplicate their logic.
- `teacher_remarks`: optional, nullable `Text`, max 2000 chars enforced at the API boundary (not a DB constraint), editable only while `status == "draft"` (same gate as `grade`/`marks_obtained`).
- Never write `teacher_remarks`'s content into `AuditLog.metadata_json` (existing convention: small structured metadata only, never full field values).
- New `GET /school/academic-team/progress` endpoint: `academic_team` role only, via the **singular** check (`user.role != "academic_team"`), not the multi-role tuple pattern used by `list_readable_results`. No client-supplied student/school id. Average computed over **all** statuses (draft/verified/published), matching the existing `list_academic_team_results` exposure level to the Academic Team member themselves — not the published-only external rule.
- No pagination, no Pydantic schema introduction, no camelCase, no new error-envelope shape, no rate limiting — match this router's 100% existing convention (raw `payload: dict`, bare-array list responses, `HTTPException(status, detail=str)`).
- Frontend: no Tailwind, no component library, no client-side data-fetching library — reuse the existing `card`/`field`/`table`/`table-wrap`/`muted`/`btn` utility classes and the existing `Promise.all` + try/catch page pattern.
- Preserve API compatibility: every change is additive (new optional request field, new response key, brand-new endpoint). No existing field, type, or route is altered or removed.
- Preserve database data: the migration is additive/nullable only, no backfill, no data rewrite.

## Test Execution Recipe

All backend test commands in this plan run via an ad-hoc container joined to the already-running compose network, mounting the worktree's live source (the compose services have no source bind mount, so this is the fast loop for this repo without rebuilding the `api` image each iteration). Run from the worktree root (`.worktrees/enh-002-academic-team`):

```bash
MSYS_NO_PATHCONV=1 docker run --rm --network edusphere_default \
  -v "$(pwd)/apps/api:/app" -w /app \
  --env-file "../../.env" \
  -e AUTO_CREATE_SCHEMA=false \
  edusphere-api \
  python -m pytest -q tests/test_sch_006_academic_results.py
```

Substitute the target test file/function per task. This does not start, stop, or recreate any compose service.

Frontend checks run in `apps/web` using the symlinked `node_modules`:
```bash
npm run typecheck
npm run lint
```

---

### Task 1: `teacher_remarks` column — model + migration

**Files:**
- Modify: `apps/api/app/models.py:1160-1180` (`SchoolAcademicResult`)
- Create: `apps/api/alembic/versions/0031_school_academic_result_teacher_remarks.py`
- Test: `apps/api/tests/test_sch_006_academic_results.py`

**Interfaces:**
- Produces: `SchoolAcademicResult.teacher_remarks: str | None` — a plain nullable ORM column, consumed by Task 2's serializer/create-endpoint work.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_sch_006_academic_results.py` (after the existing imports/fixtures, before the first `@pytest.mark.asyncio` test):

```python
@pytest.mark.asyncio
async def test_teacher_remarks_column_round_trips_on_the_model(db_session):
    """ENH-002: SchoolAcademicResult must accept and persist teacher_remarks."""
    admin = User(email=f"enh002-admin-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Admin", role="overseas_admin", division="overseas", active=True)
    db_session.add(admin)
    await db_session.flush()
    school = School(name=f"ENH-002 Test School {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db_session.add(school)
    await db_session.flush()
    student = SchoolStudent(school_id=school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Remarks Student", created_by_user_id=admin.id)
    db_session.add(student)
    await db_session.flush()
    result = SchoolAcademicResult(
        school_student_id=student.id, academic_year="2026", term="Term 1", subject="Mathematics",
        max_marks=100, marks_obtained=90, status="draft", uploaded_by_user_id=admin.id,
        teacher_remarks="Strong grasp of algebra.",
    )
    db_session.add(result)
    await db_session.commit()
    await db_session.refresh(result)
    assert result.teacher_remarks == "Strong grasp of algebra."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `... pytest -q tests/test_sch_006_academic_results.py::test_teacher_remarks_column_round_trips_on_the_model -v`
Expected: FAIL with `TypeError: 'teacher_remarks' is an invalid keyword argument for SchoolAcademicResult` (the ORM constructor rejects the unknown kwarg — confirms the failure reason is "field doesn't exist yet," not something else).

- [ ] **Step 3: Add the column to the model**

In `apps/api/app/models.py`, inside `SchoolAcademicResult` (after `grade`, before `status`):

```python
    grade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    teacher_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft")
```

`Text` is already imported in `models.py` (used by `SchoolCareerRecord.notes`).

- [ ] **Step 4: Write the migration**

Create `apps/api/alembic/versions/0031_school_academic_result_teacher_remarks.py`:

```python
"""Add school_academic_results.teacher_remarks (ENH-002).

Revision ID: 0031_school_academic_result_teacher_remarks
Revises: 0030_academic_years

School CRM.md Part B §9's Result Entry field list includes "Teacher Remarks" alongside
Academic Year/Term/Subject/Marks/Grade/Uploaded By -- every other field in that list was
already present on SchoolAcademicResult except this one. Nullable, additive-only: no
backfill, existing rows read as NULL.
"""
from alembic import op
import sqlalchemy as sa

revision = "0031_school_academic_result_teacher_remarks"
down_revision = "0030_academic_years"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("school_academic_results")}
    if "teacher_remarks" not in columns:
        op.add_column("school_academic_results", sa.Column("teacher_remarks", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("school_academic_results", "teacher_remarks")
```

- [ ] **Step 5: Apply the migration to the shared dev database**

This is the one step in this plan that touches the running dev Postgres. It is additive-only (nullable column, no backfill) and does not require stopping or recreating any container:

```bash
MSYS_NO_PATHCONV=1 docker run --rm --network edusphere_default \
  -v "$(pwd)/apps/api:/app" -w /app \
  --env-file "../../.env" \
  -e AUTO_CREATE_SCHEMA=false \
  edusphere-api \
  alembic upgrade head
```
Expected output ends with `Running upgrade 0030_academic_years -> 0031_school_academic_result_teacher_remarks`.

- [ ] **Step 6: Run test to verify it passes**

Run: `... pytest -q tests/test_sch_006_academic_results.py::test_teacher_remarks_column_round_trips_on_the_model -v`
Expected: PASS

- [ ] **Step 7: Run full existing SCH-006 suite to confirm no regression**

Run: `... pytest -q tests/test_sch_006_academic_results.py`
Expected: all tests pass (9 existing + 1 new = 10).

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0031_school_academic_result_teacher_remarks.py apps/api/tests/test_sch_006_academic_results.py
git commit -m "feat(enh-002): add teacher_remarks column to SchoolAcademicResult"
```

---

### Task 2: `teacher_remarks` on create — serializer + endpoint

**Files:**
- Modify: `apps/api/app/api/schools.py:1639-1647` (`_result_out`)
- Modify: `apps/api/app/api/schools.py:1650-1678` (`create_academic_result`)
- Test: `apps/api/tests/test_sch_006_academic_results.py`

**Interfaces:**
- Consumes: `SchoolAcademicResult.teacher_remarks` (Task 1).
- Produces: `_result_out()` now includes `"teacher_remarks"` in its returned dict — every caller of `_result_out()` (list_academic_team_results, list_readable_results, student_overview) inherits this automatically; no changes needed in those three functions themselves.

- [ ] **Step 1: Write the failing test**

Add to `apps/api/tests/test_sch_006_academic_results.py`:

```python
@pytest.mark.asyncio
async def test_teacher_remarks_can_be_set_on_upload(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
        "teacher_remarks": "Good improvement this term.",
    })
    assert response.status_code == 201, response.text
    assert response.json()["teacher_remarks"] == "Good improvement this term."


@pytest.mark.asyncio
async def test_teacher_remarks_is_optional_on_upload(client, db_session):
    """Backward compatibility: omitting teacher_remarks must keep working exactly as before."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
    })
    assert response.status_code == 201, response.text
    assert response.json()["teacher_remarks"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `... pytest -q tests/test_sch_006_academic_results.py::test_teacher_remarks_can_be_set_on_upload tests/test_sch_006_academic_results.py::test_teacher_remarks_is_optional_on_upload -v`
Expected: both FAIL on `assert response.json()["teacher_remarks"] == ...` — the key is simply absent from the response dict (KeyError-style `None != "Good improvement this term."`, and second test fails because the key doesn't exist at all rather than existing as `None`... actually since `.json()["teacher_remarks"]` on a missing key raises `KeyError`, expect a `KeyError: 'teacher_remarks'` failure for both).

- [ ] **Step 3: Add teacher_remarks to `_result_out()`**

In `apps/api/app/api/schools.py`, modify `_result_out`:

```python
def _result_out(r: SchoolAcademicResult) -> dict:
    percentage = round(float(r.marks_obtained) / float(r.max_marks) * 100, 2) if float(r.max_marks) else None
    return {
        "id": r.id, "school_student_id": r.school_student_id, "academic_year": r.academic_year, "term": r.term,
        "subject": r.subject, "max_marks": float(r.max_marks), "marks_obtained": float(r.marks_obtained),
        "percentage": percentage, "grade": r.grade, "teacher_remarks": r.teacher_remarks, "status": r.status,
        "uploaded_by_user_id": r.uploaded_by_user_id, "verified_by_user_id": r.verified_by_user_id,
        "published_by_user_id": r.published_by_user_id,
    }
```

- [ ] **Step 4: Accept `teacher_remarks` on create**

In `apps/api/app/api/schools.py`, modify `create_academic_result`:

```python
@router.post("/academic-team/results", status_code=201)
async def create_academic_result(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    try:
        max_marks = float(payload.get("max_marks"))
        marks_obtained = float(payload.get("marks_obtained"))
    except (TypeError, ValueError):
        raise HTTPException(422, "max_marks and marks_obtained must be numbers")
    subject = str(payload.get("subject", "")).strip()
    academic_year = str(payload.get("academic_year", "")).strip()
    term = str(payload.get("term", "")).strip()
    if not subject or not academic_year or not term:
        raise HTTPException(422, "academic_year, term, and subject are required")
    teacher_remarks = _clean_teacher_remarks(payload.get("teacher_remarks"))
    result = SchoolAcademicResult(
        school_student_id=student.id, academic_year=academic_year, term=term, subject=subject,
        max_marks=max_marks, marks_obtained=marks_obtained, grade=payload.get("grade"),
        teacher_remarks=teacher_remarks, status="draft", uploaded_by_user_id=user.id,
    )
    db.add(result)
    await db.flush()
    db.add(SchoolResultStatusHistory(result_id=result.id, from_status="none", to_status="draft", changed_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.result_create", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={"subject": subject}))
    await db.commit()
    return _result_out(result)
```

Add the `_clean_teacher_remarks` helper just above `_result_out` (used by both create and update — written now, exercised fully by Task 3's validation test):

```python
def _clean_teacher_remarks(value) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `... pytest -q tests/test_sch_006_academic_results.py::test_teacher_remarks_can_be_set_on_upload tests/test_sch_006_academic_results.py::test_teacher_remarks_is_optional_on_upload -v`
Expected: PASS

- [ ] **Step 6: Run full SCH-006/007/008 regression**

Run: `... pytest -q tests/test_sch_006_academic_results.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py`
Expected: all pass — confirms the shared `_result_out()` change didn't break the Parent overview or timeline paths.

- [ ] **Step 7: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_sch_006_academic_results.py
git commit -m "feat(enh-002): accept and return teacher_remarks on academic result upload"
```

---

### Task 3: `teacher_remarks` on update — draft-only edit gate

**Files:**
- Modify: `apps/api/app/api/schools.py:1681-1699` (`update_academic_result`)
- Test: `apps/api/tests/test_sch_006_academic_results.py`

**Interfaces:**
- Consumes: `_clean_teacher_remarks()` (Task 2).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_teacher_remarks_can_be_edited_while_draft(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Physics", "max_marks": 100, "marks_obtained": 70})
    result_id = created.json()["id"]

    edited = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"teacher_remarks": "Needs more practice with vectors."})
    assert edited.status_code == 200
    assert edited.json()["teacher_remarks"] == "Needs more practice with vectors."


@pytest.mark.asyncio
async def test_teacher_remarks_cannot_be_edited_after_verify(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Physics", "max_marks": 100, "marks_obtained": 70})
    result_id = created.json()["id"]

    await _login(client, reviewer.email)
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")

    await _login(client, uploader.email)
    edit_after_verify = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"teacher_remarks": "Too late."})
    assert edit_after_verify.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `... pytest -q tests/test_sch_006_academic_results.py::test_teacher_remarks_can_be_edited_while_draft -v`
Expected: FAIL — `assert edited.json()["teacher_remarks"] == "..."` fails because `update_academic_result`'s editable-field loop doesn't include `"teacher_remarks"`, so the PATCH silently succeeds (200) but leaves the field unset (`None`). The second test should already PASS as written (the 409 draft-only guard is unconditional on status, not per-field) — run it anyway to confirm it passes both before and after Step 3, proving this task doesn't touch that guard.

- [ ] **Step 3: Add teacher_remarks to the editable-field tuple**

In `apps/api/app/api/schools.py`, modify `update_academic_result`:

```python
@router.patch("/academic-team/results/{result_id}")
async def update_academic_result(result_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    result = await db.get(SchoolAcademicResult, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    await _student_in_portfolio(db, user, result.school_student_id)
    if result.status != "draft":
        raise HTTPException(409, "Only a Draft result can be edited")
    for field in ("subject", "academic_year", "term", "grade"):
        if field in payload:
            setattr(result, field, payload[field])
    for field in ("max_marks", "marks_obtained"):
        if field in payload:
            setattr(result, field, float(payload[field]))
    if "teacher_remarks" in payload:
        result.teacher_remarks = _clean_teacher_remarks(payload["teacher_remarks"])
    db.add(AuditLog(user_id=user.id, action="school.result_update", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={}))
    await db.commit()
    return _result_out(result)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `... pytest -q tests/test_sch_006_academic_results.py::test_teacher_remarks_can_be_edited_while_draft tests/test_sch_006_academic_results.py::test_teacher_remarks_cannot_be_edited_after_verify -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_sch_006_academic_results.py
git commit -m "feat(enh-002): allow teacher_remarks edits while a result is still draft"
```

---

### Task 4: `teacher_remarks` max-length validation

**Files:**
- Modify: `apps/api/app/api/schools.py` (`_clean_teacher_remarks`, or its callers)
- Test: `apps/api/tests/test_sch_006_academic_results.py`

- [ ] **Step 1: Write the failing tests**

```python
TEACHER_REMARKS_MAX_LENGTH = 2000


@pytest.mark.asyncio
async def test_teacher_remarks_over_2000_chars_is_rejected_on_create(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
        "teacher_remarks": "x" * 2001,
    })
    assert response.status_code == 422
    assert "teacher_remarks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_teacher_remarks_at_exactly_2000_chars_is_accepted(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    response = await client.post("/api/v1/school/academic-team/results", json={
        "school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1",
        "subject": "Mathematics", "max_marks": 100, "marks_obtained": 85,
        "teacher_remarks": "x" * 2000,
    })
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_teacher_remarks_over_2000_chars_is_rejected_on_update(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Chemistry", "max_marks": 100, "marks_obtained": 60})
    result_id = created.json()["id"]
    edited = await client.patch(f"/api/v1/school/academic-team/results/{result_id}", json={"teacher_remarks": "x" * 2001})
    assert edited.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `... pytest -q tests/test_sch_006_academic_results.py -k teacher_remarks_over_2000 -v`
Expected: FAIL — both over-length tests currently get `201`/`200` (no cap enforced yet); the at-exactly-2000 test should already PASS (no cap means everything is accepted).

- [ ] **Step 3: Enforce the cap at both call sites**

Modify `_clean_teacher_remarks` in `apps/api/app/api/schools.py` to raise, and call it before construction/mutation in both `create_academic_result` and `update_academic_result`:

```python
def _clean_teacher_remarks(value) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if len(cleaned) > 2000:
        raise HTTPException(422, "teacher_remarks must be 2000 characters or fewer")
    return cleaned
```

No other change is needed in `create_academic_result`/`update_academic_result` — both already call `_clean_teacher_remarks(...)` (Tasks 2 and 3), so the cap applies at both sites automatically because the helper itself now raises.

- [ ] **Step 4: Run tests to verify they pass**

Run: `... pytest -q tests/test_sch_006_academic_results.py -k teacher_remarks -v`
Expected: PASS (all teacher_remarks-related tests, including Tasks 2/3's).

- [ ] **Step 5: Run full SCH-006 suite**

Run: `... pytest -q tests/test_sch_006_academic_results.py`
Expected: all pass (14 tests: 9 original + 5 new so far).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_sch_006_academic_results.py
git commit -m "feat(enh-002): cap teacher_remarks at 2000 characters"
```

---

### Task 5: Visibility regression — published-only gate and audit-log restraint

This task adds no new behavior — it proves the shared `_result_out()` change from Task 2 didn't weaken two already-critical guarantees: `SCH-006-AC02` (no pre-publish leak) and the existing audit-log minimalism convention.

**Files:**
- Test only: `apps/api/tests/test_sch_006_academic_results.py`

- [ ] **Step 1: Write the tests**

```python
@pytest.mark.asyncio
async def test_teacher_remarks_is_not_leaked_before_publish(client, db_session):
    """SCH-006-AC02, extended to the new field: a draft/verified result's teacher_remarks
    must never reach /school/results, exactly like every other field on that result."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Biology", "max_marks": 100, "marks_obtained": 88, "teacher_remarks": "Excellent lab work."})

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/results")
    assert readable.status_code == 200
    assert readable.json() == []


@pytest.mark.asyncio
async def test_teacher_remarks_is_visible_once_published(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    reviewer = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Biology", "max_marks": 100, "marks_obtained": 88, "teacher_remarks": "Excellent lab work."})
    result_id = created.json()["id"]
    await _login(client, reviewer.email)
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/verify")
    await client.post(f"/api/v1/school/academic-team/results/{result_id}/publish")

    await _login(client, ctx["coordinator"].email)
    readable = await client.get("/api/v1/school/results")
    assert readable.status_code == 200
    assert readable.json()[0]["teacher_remarks"] == "Excellent lab work."


@pytest.mark.asyncio
async def test_teacher_remarks_content_is_never_written_to_the_audit_log(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Biology", "max_marks": 100, "marks_obtained": 88, "teacher_remarks": "A private observation about this student."})

    rows = (await db_session.scalars(select(AuditLog).where(AuditLog.action == "school.result_create"))).all()
    assert rows, "expected an AuditLog row for the create action"
    for row in rows:
        assert "A private observation" not in str(row.metadata_json)
```

This test needs `AuditLog` imported in the test file's `from app.models import (...)` line — add it to the existing import if not already present.

- [ ] **Step 2: Run tests to verify current state**

Run: `... pytest -q tests/test_sch_006_academic_results.py -k "not_leaked_before_publish or visible_once_published or never_written_to_the_audit_log" -v`
Expected: all three should already **PASS** — this task is a verification/regression-lock, not new behavior. If any fails, that's a real bug introduced by Tasks 2-4 and must be fixed before proceeding (do not adjust the test to match broken behavior).

- [ ] **Step 3: No implementation change expected**

If Step 2 passed, there is nothing to implement — proceed to commit. This step exists to make the guarantee explicit and permanent in the test suite, not to add code.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_sch_006_academic_results.py
git commit -m "test(enh-002): lock in pre-publish visibility and audit-log restraint for teacher_remarks"
```

---

### Task 6: Extract `_percentage()` helper (refactor)

Pure refactor — no behavior change. Deduplicates the percentage ternary that Task 7's aggregate endpoint would otherwise duplicate a third time.

**Files:**
- Modify: `apps/api/app/api/schools.py:1639-1647` (`_result_out`)

**Interfaces:**
- Produces: `_percentage(max_marks: float, marks_obtained: float) -> float | None`, consumed by Task 7.

- [ ] **Step 1: Confirm current tests pass (baseline for this refactor)**

Run: `... pytest -q tests/test_sch_006_academic_results.py`
Expected: all pass (this is the "before" snapshot a refactor must not change).

- [ ] **Step 2: Extract the helper**

In `apps/api/app/api/schools.py`, just above `_result_out`:

```python
def _percentage(max_marks: float, marks_obtained: float) -> float | None:
    return round(marks_obtained / max_marks * 100, 2) if max_marks else None


def _result_out(r: SchoolAcademicResult) -> dict:
    percentage = _percentage(float(r.max_marks), float(r.marks_obtained))
    return {
        "id": r.id, "school_student_id": r.school_student_id, "academic_year": r.academic_year, "term": r.term,
        "subject": r.subject, "max_marks": float(r.max_marks), "marks_obtained": float(r.marks_obtained),
        "percentage": percentage, "grade": r.grade, "teacher_remarks": r.teacher_remarks, "status": r.status,
        "uploaded_by_user_id": r.uploaded_by_user_id, "verified_by_user_id": r.verified_by_user_id,
        "published_by_user_id": r.published_by_user_id,
    }
```

- [ ] **Step 3: Rerun tests to confirm no behavior change**

Run: `... pytest -q tests/test_sch_006_academic_results.py`
Expected: identical pass count to Step 1.

- [ ] **Step 4: Commit**

```bash
git add apps/api/app/api/schools.py
git commit -m "refactor(enh-002): extract _percentage() helper for reuse by the progress endpoint"
```

---

### Task 7: `GET /school/academic-team/progress` — role check + portfolio scoping

**Files:**
- Modify: `apps/api/app/api/schools.py` (new route, placed after `list_academic_team_results`, before `@router.get("/results")`)
- Test: `apps/api/tests/test_sch_006_academic_results.py`

**Interfaces:**
- Consumes: `_portfolio_school_ids()`, `_percentage()` (Task 6).
- Produces: `GET /school/academic-team/progress` → `list[dict]`, each `{school_student_id, full_name, school_name, result_count, average_percentage}`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_progress_endpoint_requires_academic_team_role(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    await _login(client, ctx["coordinator"].email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_progress_endpoint_rejects_career_counselor_and_psychometric_team(client, db_session):
    """Anti-regression: this endpoint must use the singular academic_team check, not a
    copy-pasted multi-role tuple that would accidentally admit these two sibling roles."""
    ctx = await _create_school_with_coordinator(db_session)
    for role in ("career_counselor", "psychometric_team"):
        member = User(email=f"enh002-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="Sibling Role", role=role, division="overseas", active=True, profile={})
        db_session.add(member)
        await db_session.flush()
        db_session.add(UserRoleAssignment(user_id=member.id, division="overseas", role=role, is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
        db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=ctx["school"].id, role=role, assigned_by_user_id=ctx["admin"].id))
        await db_session.commit()
        await _login(client, member.email)
        response = await client.get("/api/v1/school/academic-team/progress")
        assert response.status_code == 403, f"{role} must not access the Academic Team progress view"


@pytest.mark.asyncio
async def test_progress_endpoint_only_includes_the_callers_own_portfolio(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    other_school = School(name=f"ENH-002 Other School {uuid.uuid4().hex[:6]}", created_by_user_id=ctx["admin"].id)
    db_session.add(other_school)
    await db_session.flush()
    other_student = SchoolStudent(school_id=other_school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Outside Portfolio", created_by_user_id=ctx["admin"].id)
    db_session.add(other_student)
    await db_session.commit()

    await _login(client, member.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 200
    student_ids = {row["school_student_id"] for row in response.json()}
    assert str(ctx["student"].id) in student_ids
    assert str(other_student.id) not in student_ids


@pytest.mark.asyncio
async def test_progress_endpoint_returns_empty_list_for_a_member_with_no_portfolio(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    unassigned = User(email=f"enh002-noportfolio-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name="No Portfolio", role="academic_team", division="overseas", active=True, profile={})
    db_session.add(unassigned)
    await db_session.flush()
    db_session.add(UserRoleAssignment(user_id=unassigned.id, division="overseas", role="academic_team", is_active=True, assigned_by_user_id=ctx["admin"].id, approval_status="approved"))
    await db_session.commit()
    await _login(client, unassigned.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `... pytest -q tests/test_sch_006_academic_results.py -k progress_endpoint -v`
Expected: FAIL with 404 (route doesn't exist yet) for all four.

- [ ] **Step 3: Implement the endpoint (role check + scoping only, no aggregation yet)**

In `apps/api/app/api/schools.py`, after `list_academic_team_results` (before the `@router.get("/results")` block):

```python
@router.get("/academic-team/progress")
async def academic_team_progress(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-002: portfolio-wide progress aggregate for the Academic Team member themselves --
    average is computed over ALL statuses (draft/verified/published) in their own portfolio,
    matching list_academic_team_results' existing exposure level, not the published-only rule
    that applies to external roles (Coordinator/Teacher/Parent)."""
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    rows = (
        await db.execute(select(SchoolStudent, School).join(School, School.id == SchoolStudent.school_id).where(SchoolStudent.school_id.in_(portfolio)).order_by(SchoolStudent.full_name.asc()))
    ).all()
    student_ids = [s.id for s, _sc in rows]
    result_rows = (await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id.in_(student_ids)))).all() if student_ids else []
    by_student: dict = {}
    for r in result_rows:
        by_student.setdefault(r.school_student_id, []).append(r)
    out = []
    for student, school in rows:
        student_results = by_student.get(student.id, [])
        percentages = [p for p in (_percentage(float(r.max_marks), float(r.marks_obtained)) for r in student_results) if p is not None]
        out.append({
            "school_student_id": student.id, "full_name": student.full_name, "school_name": school.name,
            "result_count": len(student_results),
            "average_percentage": round(sum(percentages) / len(percentages), 2) if percentages else None,
        })
    return out
```

This route must be placed **before** `@router.get("/results")` — FastAPI matches routes in registration order within a router, and while `/academic-team/progress` and `/academic-team/results` don't collide, keeping this next to its sibling `/academic-team/results` list route keeps the SCH-006 section together (matches this file's existing grouping-by-feature convention).

- [ ] **Step 4: Run tests to verify they pass**

Run: `... pytest -q tests/test_sch_006_academic_results.py -k progress_endpoint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_sch_006_academic_results.py
git commit -m "feat(enh-002): add GET /school/academic-team/progress endpoint"
```

---

### Task 8: Progress aggregation correctness

**Files:**
- Test only: `apps/api/tests/test_sch_006_academic_results.py`

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_progress_includes_a_student_with_zero_results(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, member.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    assert response.status_code == 200
    row = next(r for r in response.json() if r["school_student_id"] == str(ctx["student"].id))
    assert row["result_count"] == 0
    assert row["average_percentage"] is None


@pytest.mark.asyncio
async def test_progress_average_reflects_mixed_max_marks_across_subjects(client, db_session):
    """Average of PERCENTAGES per subject, not sum(marks)/sum(max_marks) -- subjects can
    have different max_marks, so those two formulas diverge and only the former is correct."""
    ctx = await _create_school_with_coordinator(db_session)
    uploader = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    await _login(client, uploader.email)
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 80})
    await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student"].id), "academic_year": "2026", "term": "Term 1", "subject": "Art", "max_marks": 20, "marks_obtained": 10})
    # 80% and 50% -> average 65%, NOT (80+10)/(100+20)*100 = 75%.
    response = await client.get("/api/v1/school/academic-team/progress")
    row = next(r for r in response.json() if r["school_student_id"] == str(ctx["student"].id))
    assert row["result_count"] == 2
    assert row["average_percentage"] == 65.0


@pytest.mark.asyncio
async def test_progress_spans_every_school_in_a_multi_school_portfolio(client, db_session):
    ctx = await _create_school_with_coordinator(db_session)
    member = await _add_academic_team_member(db_session, ctx["admin"], ctx["school"])
    second_school = School(name=f"ENH-002 Second School {uuid.uuid4().hex[:6]}", created_by_user_id=ctx["admin"].id)
    db_session.add(second_school)
    await db_session.flush()
    db_session.add(SchoolStaffAssignment(user_id=member.id, school_id=second_school.id, role="academic_team", assigned_by_user_id=ctx["admin"].id))
    second_student = SchoolStudent(school_id=second_school.id, student_code=await unique_student_code(db_session, SchoolStudent.student_code), full_name="Second School Student", created_by_user_id=ctx["admin"].id)
    db_session.add(second_student)
    await db_session.commit()

    await _login(client, member.email)
    response = await client.get("/api/v1/school/academic-team/progress")
    student_ids = {row["school_student_id"] for row in response.json()}
    assert str(ctx["student"].id) in student_ids
    assert str(second_student.id) in student_ids
    row = next(r for r in response.json() if r["school_student_id"] == str(second_student.id))
    assert row["school_name"] == second_school.name
```

- [ ] **Step 2: Run tests to verify current state**

Run: `... pytest -q tests/test_sch_006_academic_results.py -k "progress_includes_a_student_with_zero or progress_average_reflects or progress_spans_every_school" -v`
Expected: all three should already **PASS** given Task 7's implementation — this task exercises aggregation math the implementation was already written to handle, making that correctness explicit and permanent. If any fails, fix `academic_team_progress()` (most likely culprit: averaging raw marks instead of per-row percentages) before proceeding.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_sch_006_academic_results.py
git commit -m "test(enh-002): lock in progress-endpoint aggregation correctness"
```

---

### Task 9: Frontend — `teacher_remarks` in `SchoolAcademicResultsPanel.tsx`

**Files:**
- Modify: `apps/web/components/SchoolAcademicResultsPanel.tsx`

- [ ] **Step 1: Update the local `Result` type**

```tsx
type Result = {
  id: string; school_student_id: string; academic_year: string; term: string; subject: string;
  max_marks: number; marks_obtained: number; percentage: number | null; grade: string | null;
  teacher_remarks: string | null; status: string; uploaded_by_user_id: string; verified_by_user_id: string | null; published_by_user_id: string | null;
};
```

- [ ] **Step 2: Include `teacher_remarks` in the create request**

In `createResult`, add to the `body: JSON.stringify({...})` object (after `grade`):

```tsx
        grade: form.get("grade") || undefined,
        teacher_remarks: form.get("teacher_remarks") || undefined,
```

- [ ] **Step 3: Add the form field**

After the existing `result-grade` field block, before the closing `</form>`:

```tsx
            <div className="field">
              <label htmlFor="result-remarks">Teacher remarks</label>
              <textarea id="result-remarks" name="teacher_remarks" rows={2} placeholder="Optional" />
            </div>
```

- [ ] **Step 4: Show remarks as a secondary line under the Subject cell**

Change the Subject `<td>`:

```tsx
                      <td>{r.subject} ({r.academic_year}, {r.term}){r.teacher_remarks && <><br /><span className="muted" style={{ fontSize: 13 }}>{r.teacher_remarks}</span></>}</td>
```

- [ ] **Step 5: Add `scope="col"` to the table headers**

```tsx
                <tr><th scope="col">Student</th><th scope="col">Subject</th><th scope="col">Marks</th><th scope="col">Status</th><th scope="col">Actions</th></tr>
```

- [ ] **Step 6: Typecheck**

Run (in `apps/web`): `npm run typecheck`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/SchoolAcademicResultsPanel.tsx
git commit -m "feat(enh-002): add teacher_remarks input and display to the Academic Team results panel"
```

---

### Task 10: Frontend — `Remarks` column in `SchoolChildOverview.tsx`

**Files:**
- Modify: `apps/web/components/SchoolChildOverview.tsx`

- [ ] **Step 1: Update the local `Result` type**

```tsx
type Result = { id: string; academic_year: string; term: string; subject: string; max_marks: number; marks_obtained: number; percentage: number | null; grade: string | null; teacher_remarks: string | null };
```

- [ ] **Step 2: Add the column header and cell**

```tsx
              <thead><tr><th scope="col">Year</th><th scope="col">Term</th><th scope="col">Subject</th><th scope="col">Marks</th><th scope="col">%</th><th scope="col">Grade</th><th scope="col">Remarks</th></tr></thead>
              <tbody>
                {overview.results.map((r) => (
                  <tr key={r.id}><td>{r.academic_year}</td><td>{r.term}</td><td>{r.subject}</td><td>{r.marks_obtained} / {r.max_marks}</td><td>{r.percentage ?? "-"}</td><td>{r.grade || "-"}</td><td>{r.teacher_remarks || "-"}</td></tr>
                ))}
              </tbody>
```

- [ ] **Step 3: Typecheck**

Run (in `apps/web`): `npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/web/components/SchoolChildOverview.tsx
git commit -m "feat(enh-002): show teacher_remarks in the Parent child-overview results table"
```

---

### Task 11: Frontend — new progress panel + dashboard wiring

**Files:**
- Create: `apps/web/components/SchoolAcademicProgressPanel.tsx`
- Modify: `apps/web/app/school/academic-team/dashboard/page.tsx`

**Interfaces:**
- Consumes: `GET /school/academic-team/progress` (Task 7) → `{school_student_id, full_name, school_name, result_count, average_percentage}[]`.

- [ ] **Step 1: Create the panel component**

```tsx
type ProgressRow = { school_student_id: string; full_name: string; school_name: string; result_count: number; average_percentage: number | null };

// ENH-002: portfolio-wide progress aggregate. Read-only, server-renderable (no "use client")
// -- no mutation, so no hydration cost, matching SchoolChildOverview.tsx's pattern rather
// than SchoolAcademicResultsPanel.tsx's client/actions pattern.
export default function SchoolAcademicProgressPanel({ progress }: { progress: ProgressRow[] }) {
  return (
    <div className="card">
      <h2>Portfolio progress</h2>
      {progress.length === 0 ? (
        <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Student</th><th scope="col">School</th><th scope="col">Results</th><th scope="col">Avg %</th></tr></thead>
            <tbody>
              {progress.map((p) => (
                <tr key={p.school_student_id}>
                  <td>{p.full_name}</td><td>{p.school_name}</td><td>{p.result_count}</td>
                  <td>{p.average_percentage === null ? "No results yet" : `${p.average_percentage}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
```

Save as `apps/web/components/SchoolAcademicProgressPanel.tsx`.

- [ ] **Step 2: Wire into the dashboard page**

In `apps/web/app/school/academic-team/dashboard/page.tsx`, add the import, the type, the fetch, and the render:

```tsx
import SchoolAcademicProgressPanel from "@/components/SchoolAcademicProgressPanel";
```

```tsx
type ProgressRow = { school_student_id: string; full_name: string; school_name: string; result_count: number; average_percentage: number | null };
```

In the destructured `Promise.all`:

```tsx
  let progress: ProgressRow[];
  try {
    [user, results, students, testPrepRecords, languageRecords, progress] = await Promise.all([
      serverApi<User>("/api/v1/auth/me"),
      serverApi<Result[]>("/api/v1/school/academic-team/results"),
      serverApi<Student[]>("/api/v1/school/portfolio-students"),
      serverApi<TestPrepRecord[]>("/api/v1/school/academic-team/test-prep-records"),
      serverApi<LanguageRecord[]>("/api/v1/school/academic-team/language-records"),
      serverApi<ProgressRow[]>("/api/v1/school/academic-team/progress"),
    ]);
```

(Add `let progress: ProgressRow[];` alongside the other `let` declarations above the `try`.)

In the render:

```tsx
    <PortalShell nav={SCHOOL_NAV["academic-team"]} roleLabel="Academic Team" userName={user.full_name}>
      <SchoolAcademicProgressPanel progress={progress} />
      <SchoolAcademicResultsPanel results={results} students={students} currentUserId={user.id} />
      <SchoolTestPrepLanguagePanel testPrepRecords={testPrepRecords} languageRecords={languageRecords} students={students} />
    </PortalShell>
```

(Progress placed first — a summary belongs above the detailed worklist it summarizes.)

- [ ] **Step 3: Typecheck**

Run (in `apps/web`): `npm run typecheck`
Expected: no errors.

- [ ] **Step 4: Lint**

Run (in `apps/web`): `npm run lint`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/SchoolAcademicProgressPanel.tsx apps/web/app/school/academic-team/dashboard/page.tsx
git commit -m "feat(enh-002): add portfolio progress panel to the Academic Team dashboard"
```

---

### Task 12: Documentation close-out

**Files:**
- Modify: `docs/architecture/DATA_MODEL.md` (§6.16)
- Modify: `docs/architecture/API_CONTRACT.md` (SCH-006 endpoint rows)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (ENH-002 entry)

- [ ] **Step 1: Update `DATA_MODEL.md` §6.16**

Add `teacher_remarks` to `SchoolAcademicResult`'s documented field list (the line beginning `- **SchoolAcademicResult** fields:`), noting it as added by `0031_school_academic_result_teacher_remarks`, nullable, ENH-002.

- [ ] **Step 2: Update `API_CONTRACT.md`**

On the `POST /school/academic-team/results` row, note the new optional `teacher_remarks` field (2000-char cap, 422 over limit). Add a new row for `GET /school/academic-team/progress` (Authenticated, Academic Team only, own portfolio) describing the aggregate shape.

- [ ] **Step 3: Close out the ENH-002 entry in `ENHANCEMENT_BACKLOG.md`**

Mark the acceptance criteria as met: teacher_remarks field shipped with the documented visibility rule; progress view built as `GET /school/academic-team/progress` (per-student average across the portfolio, all statuses, matching existing internal exposure).

- [ ] **Step 4: Commit**

```bash
git add docs/architecture/DATA_MODEL.md docs/architecture/API_CONTRACT.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(enh-002): document teacher_remarks field and the new progress endpoint"
```

---

### Task 13: Full regression pass

**Files:** none (verification only)

- [ ] **Step 1: Full backend SCH-00x regression**

```bash
MSYS_NO_PATHCONV=1 docker run --rm --network edusphere_default \
  -v "$(pwd)/apps/api:/app" -w /app \
  --env-file "../../.env" -e AUTO_CREATE_SCHEMA=false \
  edusphere-api \
  python -m pytest -q tests/test_sch_001_school_portal_access.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_003_school_onboarding.py tests/test_sch_004_career_guidance.py tests/test_sch_005_psychometric_assessment.py tests/test_sch_006_academic_results.py tests/test_sch_007_parent_portal.py tests/test_sch_008_student_timeline.py tests/test_sch_009_test_prep_language.py tests/test_sch_011_entitlements.py tests/test_sch_reports.py tests/test_sch_school_staff_provisioning.py
```
Expected: all pass, zero failures. Per this project's regression-cadence convention, this full-module pass substitutes for a whole-suite run at this checkpoint.

- [ ] **Step 2: Frontend build**

```bash
cd apps/web && npm run typecheck && npm run lint && npm run build
```
Expected: clean build.

- [ ] **Step 3: Report status — do not claim completion**

This plan's automated verification (pytest + typecheck/lint/build) does not substitute for browser validation or independent review. After this task, report: implementation complete per plan, all automated tests green, **browser validation and independent Codex review still required** before this can be considered done.
