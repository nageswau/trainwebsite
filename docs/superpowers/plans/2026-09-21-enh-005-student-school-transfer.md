# ENH-005 — Student School Transfer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Every task is RED (write the test, run it, see it fail for the *expected* reason) → GREEN (minimum code, run, pass) → REFACTOR (tidy, rerun) → commit.

**Goal:** A school coordinator can request a student's transfer to another school; an admin approves or rejects it; approval moves the student and handles parents, in-flight results, teacher and history in one transaction.

**Architecture:** One new table `school_student_transfer_requests` is both the workflow and the history. A new module `apps/api/app/api/school_transfers.py` holds two routers (`/school`, `/overseas-admin`) and one transactional `approve` core. Two existing readers change (parent scope link-only; `withdrawn` filter). The frontend adds six components on the existing `.link-list` / `.jtl` / inline-confirm design language.

**Tech Stack:** FastAPI + SQLAlchemy async + PostgreSQL + Alembic; Pydantic v2; Next.js/React + vitest + Playwright. **No new dependency.**

**Spec:** `docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md` (read it first; §-numbers below refer to it). Where the plan and spec differ, the spec wins except for the one refinement listed under Global Constraints.

## Global Constraints

- No new dependency; no new global CSS (a module CSS only if a browser run proves the reused classes insufficient).
- API: `snake_case`, lowercase enums, errors `{"detail": …}`, typed Pydantic in/out, `extra="forbid"` on every request body; the 409/403/429 `detail` strings are exactly those in spec §5.3a.
- Constants (module level, `school_transfers.py`): `TRANSFER_LOCK_TIMEOUT = "5s"`, `MAX_OPEN_TRANSFER_REQUESTS_PER_SCHOOL = 50`, `TRANSFER_FILINGS_PER_HOUR = 30`, `FREE_TEXT_MAX = 500`.
- Audit action names: `school.transfer_request_filed`, `school.transfer_request_denied`, `school.transfer_request_cancelled`, `school.transfer_request_rejected`, `school.student_transfer`, `school.user_school_scope_changed`.
- Logs and audit metadata: IDs, counts, reason tokens only; never `student_code`, `reason`, `note`, names or emails.
- **Refinement to spec §5.2/S7:** the free-text validator rejects control characters **except `\n` and `\t`** (a `<textarea>` reason legitimately has line breaks) plus U+202A–U+202E and U+2066–U+2069; it accepts U+200C/U+200D. Record this in the spec's docs task.
- Existing behaviour is preserved: run the named regression files after every backend task that touches `schools.py`.
- Backend DB tests run inside the isolated compose project against a migrated Postgres, never the host (`docker compose -f docker-compose.yml -f docker-compose.ci.yml -p <project> --profile ci run --rm --no-deps api-test python -m pytest ...`, with `app`, `tests` and `alembic` mounted so an edit needs no rebuild). **The user controls Docker; the agent does not start it unless the user explicitly authorises it.** Docker was not running when this plan was written, so tasks marked **[DB]** waited; on 2026-09-21 the user explicitly authorised bringing up an isolated stack for this worktree (project `enh005-e2e`, web 3300, API 8300, apart from the ENH-006 stack), and the **[DB]** tasks were then run RED/GREEN.
- Test command (from `apps/api`): `python -m pytest tests/<file> -q`. Web: `npm --prefix apps/web run test -- <file>`.

## File Structure

| File | Responsibility |
|---|---|
| `apps/api/app/services/mailer.py` (modify) | escape values in `_parent_notification_html` |
| `apps/api/app/schemas.py` (append) | transfer request/response models + the free-text validator |
| `apps/api/app/models.py` (append) | `SchoolStudentTransferRequest` |
| `apps/api/alembic/versions/0034_school_transfer_requests.py` (create) | table, partial unique index, CHECKs |
| `apps/api/app/api/schools.py` (modify) | parent link-only scope; `withdrawn` filters; comment correction; invariant comment |
| `apps/api/app/api/school_transfers.py` (create) | coordinator + admin routers, filing/throttle/cap, approve core |
| `apps/api/app/main.py` (modify) | register the two routers |
| `apps/api/tests/test_enh_005_*.py` (create) | one file per concern (below) |
| `apps/web/lib/apiErrors.ts`, `lib/transfers.ts` (create) | shared error parsing, types, status map |
| `apps/web/components/SchoolTransfer*.tsx`, `AdminSchoolTransferPanel.tsx`, `AdminTransferRow.tsx` (create) | UI (spec §7.1) |
| `apps/web/components/SchoolStudentDetailPanel.tsx`, `app/school/parent/dashboard/page.tsx`, `app/school/parent/children/[id]/page.tsx`, `components/WorkflowPanel.tsx`, `lib/navigation.ts` (modify) | opt-in wiring |
| `apps/web/app/school/coordinator/transfers/page.tsx` (create) | server page |
| `apps/web/tests/components/*.test.tsx`, `tests/e2e/enh-005-school-transfer.spec.ts` (create) | UI tests |

---

### Task 1: Escape values in the parent notification email (D9 / S1)

**Files:** Modify `apps/api/app/services/mailer.py:126-160`; Test `apps/api/tests/test_enh_005_mailer_escaping.py`.
**Interfaces:** Produces: `_parent_notification_html(*, recipient_name, school_name, title, body, action_url) -> str` (signature unchanged), now returning escaped text.

- [ ] **Step 1: Write the failing test**

```python
from app.services.mailer import _parent_notification_html

HOSTILE = dict(recipient_name="<b>P</b>", school_name="S<script>x</script>", title='"><img src=x onerror=1>', body="a & <i>b</i>", action_url='/school/x"><a href=evil>')


def test_every_interpolated_value_is_escaped():
    html = _parent_notification_html(**HOSTILE)
    for live in ("<b>P</b>", "<script>", "<img", "<i>b</i>", '"><a href=evil>'):
        assert live not in html
    assert "&lt;b&gt;P&lt;/b&gt;" in html
    assert "a &amp; &lt;i&gt;b&lt;/i&gt;" in html


def test_ordinary_text_renders_unchanged_apart_from_entities():
    html = _parent_notification_html(recipient_name="Asha", school_name="Sunrise", title="Result published", body="Maths is ready.", action_url="/school/parent/children/1")
    assert "Result published" in html and "Maths is ready." in html and 'href="/school/parent/children/1"' in html
```

- [ ] **Step 2: Run it, confirm RED for the right reason** — `python -m pytest tests/test_enh_005_mailer_escaping.py -q` → `test_every_interpolated_value_is_escaped` FAILS because `<b>P</b>` is present raw (not an ImportError).
- [ ] **Step 3: Implement** — `from html import escape` is already imported. In `_parent_notification_html` build `name, title_h, body_h, school_h = escape(recipient_name), escape(title), escape(body), escape(school_name)` and `href = escape(action_url, quote=True)`; use them in the template instead of the raw arguments.
- [ ] **Step 4: Run, confirm GREEN** (both tests) and run the existing SCH-007 file (needs DB → run only if DB is up; otherwise note it).
- [ ] **Step 5: Commit** — `git commit -m "fix(mailer): escape values in the parent notification HTML"` (own commit).

---

### Task 2: Transfer schemas and free-text validation (S7, spec §5.2)

**Files:** Modify `apps/api/app/schemas.py` (append); Test `apps/api/tests/test_enh_005_schemas.py`.
**Interfaces — Produces (exact names, used by Tasks 5–8):**
`clean_free_text(value: str | None) -> str | None`; `TransferRequestCreate(to_school_id: UUID, reason: str|None)`; `IncomingTransferCreate(student_code: str, reason: str|None)` (code normalised to upper-case `[0-9A-F]{8}`); `TransferRejectRequest(note: str|None)`; `TransferStatusFilter = Literal["pending","approved","rejected","cancelled","all"]`; response models `SchoolRef(id, name)`, `TransferRequestOut`, `TransferRequestPage(items,total,limit,offset)`, `TransferDestination`, `AcceptedOut(accepted: bool)`, `TransferHistoryEntry`, `TransferHistoryResponse`, `TransferOutcome`, `AdminTransferPreview`, `AdminTransferRequestOut`, `AdminTransferPage`.

- [ ] **Step 1: Write the failing tests**

```python
import uuid
import pytest
from pydantic import ValidationError
from app.schemas import IncomingTransferCreate, TransferRejectRequest, TransferRequestCreate


def test_student_code_is_normalised_and_ascii_hex_only():
    assert IncomingTransferCreate(student_code=" a3f9c21b ").student_code == "A3F9C21B"
    for bad in ("A3F9C21", "A3F9C21BX", "G3F9C21B", "", "٣٣٣٣٣٣٣٣", "ＡＡＡＡＡＡＡＡ"):
        with pytest.raises(ValidationError):
            IncomingTransferCreate(student_code=bad)


@pytest.mark.parametrize("model,kwargs", [
    (TransferRequestCreate, {"to_school_id": uuid.uuid4()}),
    (IncomingTransferCreate, {"student_code": "A3F9C21B"}),
    (TransferRejectRequest, {}),
])
@pytest.mark.parametrize("extra", ["school_id", "from_school_id", "filed_by_school_id", "status", "student_id"])
def test_client_supplied_server_fields_are_a_422(model, kwargs, extra):
    with pytest.raises(ValidationError):
        model(**kwargs, **{extra: "x"})


def test_free_text_rules():
    ok = TransferRequestCreate(to_school_id=uuid.uuid4(), reason="line one\nline two\tक्\u200dष")
    assert "\u200d" in ok.reason
    for bad in ("a\x00b", "a\u202eb", "a\u2066b", "x" * 501):
        with pytest.raises(ValidationError):
            TransferRequestCreate(to_school_id=uuid.uuid4(), reason=bad)
    assert TransferRejectRequest(note="  ").note is None  # blank normalises to None
    with pytest.raises(ValidationError):
        TransferRejectRequest(note="a\u202eb")
```

- [ ] **Step 2: Run, confirm RED** — `ImportError: cannot import name 'IncomingTransferCreate'` (expected: the names do not exist yet).
- [ ] **Step 3: Implement** (append to `schemas.py`, matching the ENH-004 block's style):

```python
import re

_BIDI = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
FREE_TEXT_MAX = 500
_CODE = re.compile(r"[0-9A-F]{8}")


def clean_free_text(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > FREE_TEXT_MAX:
        raise ValueError(f"must be {FREE_TEXT_MAX} characters or fewer")
    for ch in value:
        if ch in _BIDI or (unicodedata.category(ch) == "Cc" and ch not in "\n\t"):
            raise ValueError("must not contain control or bidirectional-override characters")
    return value


class TransferRequestCreate(BaseModel):
    model_config = {"extra": "forbid"}
    to_school_id: UUID
    reason: str | None = None
    _reason = field_validator("reason")(lambda cls, v: clean_free_text(v))


class IncomingTransferCreate(BaseModel):
    model_config = {"extra": "forbid"}
    student_code: str
    reason: str | None = None
    _reason = field_validator("reason")(lambda cls, v: clean_free_text(v))

    @field_validator("student_code")
    @classmethod
    def _code(cls, value: str) -> str:
        code = value.strip().upper()
        if not _CODE.fullmatch(code):
            raise ValueError("student_code must be 8 characters, 0-9 and A-F")
        return code


class TransferRejectRequest(BaseModel):
    model_config = {"extra": "forbid"}
    note: str | None = None
    _note = field_validator("note")(lambda cls, v: clean_free_text(v))
```

then the response models exactly as named in **Interfaces** (plain `BaseModel`s; `TransferRequestOut` fields per spec §5.2: `id, direction, status, student_id, student_code, student_name, from_school, to_school, reason, decision_note, created_at, decided_at`, with `student_id`/`student_name`/`from_school` nullable; `TransferRequestPage`/`AdminTransferPage` = `items, total, limit, offset`; `AdminTransferRequestOut` adds `filed_by_school, requester, decided_by, outcome, preview`).
- [ ] **Step 4: Run, confirm GREEN.**
- [ ] **Step 5: REFACTOR** — if the `field_validator` lambda form is unclear, replace with three small named `@field_validator` methods calling `clean_free_text`; rerun.
- [ ] **Step 6: Commit** — `feat(enh-005): transfer request and response schemas`.

---

### Task 3: Model and migration `0034` (spec §5.1)

**Files:** Modify `apps/api/app/models.py` (append after `SchoolStudentGradeHistory`); Create `apps/api/alembic/versions/0034_school_transfer_requests.py` (down-revision `0033_student_grade_history`'s revision id — read it); Test `apps/api/tests/test_enh_005_model.py`.
**Interfaces — Produces:** `SchoolStudentTransferRequest` with columns per spec §5.1; index `uq_school_transfer_pending_student` (unique, `WHERE status = 'pending'`); CHECKs `ck_school_transfer_distinct_schools` (`from_school_id <> to_school_id`) and `ck_school_transfer_filed_by_side` (`filed_by_school_id IN (from_school_id, to_school_id)`); index on `filed_by_school_id`.

- [ ] **Step 1: Write the failing test** (no DB needed)

```python
from app.models import SchoolStudentTransferRequest as T


def test_table_shape_matches_the_spec():
    t = T.__table__
    assert t.name == "school_student_transfer_requests"
    idx = {i.name: i for i in t.indexes}
    pending = idx["uq_school_transfer_pending_student"]
    assert pending.unique and [c.name for c in pending.columns] == ["school_student_id"]
    assert str(pending.dialect_options["postgresql"]["where"]) == "status = 'pending'"
    assert any(c.name == "filed_by_school_id" for i in t.indexes for c in i.columns)
    checks = {c.name for c in t.constraints if c.__class__.__name__ == "CheckConstraint"}
    assert {"ck_school_transfer_distinct_schools", "ck_school_transfer_filed_by_side"} <= checks
    assert {"status", "outcome", "decision_note", "decided_by_user_id", "decided_at", "reason"} <= set(t.c.keys())
```

plus an offline-SQL check that the migration matches: run `python -m alembic upgrade 0033_student_grade_history:0034 --sql` and assert the output contains `CREATE TABLE school_student_transfer_requests`, `CREATE UNIQUE INDEX uq_school_transfer_pending_student` and `WHERE status = 'pending'` (subprocess test, skipped only if alembic offline mode is unsupported by `env.py` — then run once by hand and record).
- [ ] **Step 2: Run, confirm RED** — `ImportError: cannot import name 'SchoolStudentTransferRequest'`.
- [ ] **Step 3: Implement** the model (SQLAlchemy 2 `Mapped` style like `SchoolStudentGradeHistory`; `__table_args__` holds the two `CheckConstraint`s and `Index("uq_school_transfer_pending_student", "school_student_id", unique=True, postgresql_where=text("status = 'pending'"))`) and the migration (`op.create_table` + `op.create_index(..., postgresql_where=sa.text("status = 'pending'"))`; `downgrade` drops the index then the table; a comment notes that `withdrawn` result rows written after upgrade remain as plain strings). **Additive only; no existing row touched.**
- [ ] **Step 4: Run, confirm GREEN**; run the offline-SQL check.
- [ ] **Step 5: Commit** — `feat(enh-005): transfer request model and migration 0034`.
- **[DB] Step 6 (user-gated):** once the DB is up, apply with `alembic upgrade head` and confirm the table with `\d school_student_transfer_requests`; rehearse `downgrade -1` then `upgrade head` on a scratch copy first.

---

### Task 4: Parent scope is link-only; `withdrawn` filters; link-creator invariant **[DB]** (spec §8, S2)

**Files:** Modify `apps/api/app/api/schools.py` (`_scoped_students_query` ~643, `_load_readable_student` ~864, `list_academic_team_results` ~1982, `academic_team_progress` ~2001, comment ~1234); Test `apps/api/tests/test_enh_005_scope.py`.
**Interfaces:** Consumes ENH-004 helpers. Produces: no new names.

- [ ] **Step 1: Write failing tests** (fixture: two schools A/B, a coordinator each, a parent at A linked to a student moved to B by a direct SQL update — the transfer endpoint does not exist yet): `test_parent_reads_a_linked_child_at_another_school` (200 on `GET /school/students/{id}` and the child is in `GET /school/students`); `test_parent_still_cannot_read_an_unlinked_student` (403, both same-school and other-school, with the **existing** messages "This student is not linked to your account" / "This student is at a different institution"); `test_results_readers_follow_the_link` (published result visible to that parent); `test_withdrawn_results_are_hidden_from_academic_team_list_and_progress` (a `withdrawn` row is absent from `/academic-team/results` and excluded from the `/academic-team/progress` average, and `PATCH`/`verify`/`publish` on it is 409); `test_link_creators_refuse_cross_school_pairs` (three cases: `POST /school/students/{id}/parents` with a parent at another school → 422; `POST /school/students` with `parent_email` of a parent at another school → 422; `accept_invite` links only students of the invite's school).
- [ ] **Step 2: Run, confirm RED** — the first test fails with 403 "different institution"; the withdrawn test fails because the row is returned.
- [ ] **Step 3: Implement** — parent branch of `_scoped_students_query`: drop the `school_id` predicate (link subquery only); `_load_readable_student`: for `school_parent` check the link first and, if unlinked, keep today's message precedence (different school → "This student is at a different institution", else "not linked"); add `SchoolAcademicResult.status != "withdrawn"` to the two queries; correct the comment at ~1234-1237; add the S2 invariant comment on `_scoped_students_query`.
- [ ] **Step 4: Run new + regression** (`test_sch_001`, `test_sch_006`, `test_sch_007`, `test_sch_008`, `test_enh_004_student_promotion.py`) — GREEN.
- [ ] **Step 5: REFACTOR** — none expected; rerun.
- [ ] **Step 6: Commit.**

---

### Task 5: Coordinator filing — outgoing, incoming, throttle, cap **[DB]** (spec §5.2, D7, D8, S3)

**Files:** Create `apps/api/app/api/school_transfers.py` (routers `coordinator_router` prefix `/school`, `admin_router` prefix `/overseas-admin`; constants from Global Constraints); Modify `apps/api/app/main.py` (add both to the router tuple); Test `apps/api/tests/test_enh_005_filing.py`.
**Interfaces — Consumes:** Task 2 schemas; Task 3 model; `_require_coordinator`, `_own_school_id` from `schools.py`. **Produces:** `POST /school/students/{student_id}/transfer-requests`, `POST /school/transfer-requests/incoming`; helper `async def _filing_guard(db, user, school_id) -> None` (throttle then cap; raises 429/409); helper `_audit(db, user, action, outcome, meta)`.

Tests (write all first; each named for its AC): `test_outgoing_creates_pending_row_with_server_derived_fields` (AC-01); `test_outgoing_foreign_or_unknown_student_is_the_identical_403_and_audited` (AC-02); `test_outgoing_same_or_unknown_destination_is_422`; `test_outgoing_duplicate_pending_is_409_and_index_backed` (AC-03); `test_client_supplied_server_fields_are_422`; `test_incoming_is_identical_202_for_valid_unknown_own_and_duplicate` (AC-04, compares status and JSON); `test_incoming_creates_a_row_only_for_a_valid_other_school_student`; `test_incoming_malformed_code_is_422`; `test_cap_of_50_open_is_409_before_any_lookup` (AC-20; the 51st, for both endpoints; freeing a slot restores filing); `test_31st_attempt_in_an_hour_is_429_with_retry_after` (AC-26; counts valid and invalid, not 422s; another coordinator unaffected; lapses via a monkeypatched clock); `test_every_attempt_writes_exactly_one_audit_row_without_code_or_reason` (AC-27); `test_non_coordinator_is_403_and_unauthenticated_401`.

- [ ] **Step 1:** write the tests above using the ENH-004 test fixtures (`_user`, a `ctx` builder creating two schools, coordinators, teacher, parent).
- [ ] **Step 2: Run, confirm RED** — 404 (routes not registered).
- [ ] **Step 3: Implement** in the spec's check order: dependency role gate → body → `_filing_guard` → scope → insert; `IntegrityError` on the partial index → rollback → 409 (outgoing) or same 202 (incoming); denied paths write the audit row and `commit()` before raising (ENH-004 pattern); throttle counts `AuditLog` rows for `user.id` with the two filing actions since `now - 1h`; log `transfer_filing_throttled` with IDs/counts only.
- [ ] **Step 4: Run, confirm GREEN;** rerun `test_enh_004_student_promotion.py`.
- [ ] **Step 5: REFACTOR** (extract the shared audit helper if duplicated) and rerun.
- [ ] **Step 6: Commit.**

---

### Task 6: Coordinator list, cancel, destinations, history **[DB]** (spec §5.2)

**Files:** Modify `school_transfers.py`; Test `apps/api/tests/test_enh_005_coordinator_reads.py`.
**Produces:** `GET /school/transfer-destinations`, `GET /school/transfer-requests?status=&limit=&offset=`, `POST /school/transfer-requests/{id}/cancel`, `GET /school/students/{id}/transfer-history`; helper `_request_out(row, caller_school_id) -> TransferRequestOut` applying the redaction rule.

Tests: `test_destinations_exclude_own_school_and_return_id_and_name_only`; `test_list_is_scoped_to_the_filing_school_in_the_query` (AC-06; another school's requests never appear, even approved); `test_status_filter_defaults_to_pending_and_rejects_unknown_with_422`; `test_pagination_limit_offset_total_order_and_bounds` (AC-21); `test_redacted_incoming_rows_have_null_student_fields_and_identical_schema` (AC-05); `test_cancel_only_by_filing_school_only_while_pending` (unknown id and other school's id → identical 403; decided → 409; concurrent approve serialises); `test_history_returns_approved_transfers_without_reason_or_staff_ids_and_is_scoped_by_the_student_loader` (AC-14, parent linked-only).

- [ ] Steps 1–6 as Task 5 (RED = 404; GREEN; refactor; commit).

---

### Task 7: Approval transaction **[DB]** (spec §5.4, D1/D3/D4, S4, S5)

**Files:** Modify `school_transfers.py` (admin router + `_approve(db, request_id, admin) -> AdminTransferRequestOut` core); Test `apps/api/tests/test_enh_005_approve.py`.
**Interfaces — Produces:** `POST /overseas-admin/school-transfer-requests/{id}/approve`; `_require_transfer_admin` dependency (role in `{"overseas_admin","super_admin"}`).

Tests: `test_only_overseas_admin_and_super_admin_can_approve` (AC-07: both coordinators, teacher, parent, principal, counselor → 403, unauthenticated 401); `test_approval_moves_the_student_and_scopes_flip` (AC-08: A's coordinator 403, B's 200; A's staff 403, B's staff 200); `test_teacher_and_pending_parent_email_are_cleared` (AC-09); `test_parents_move_only_when_no_other_child_remains_at_the_losing_school` (AC-10: three parents — sole-child moves, sibling-at-A stays, both read the child; links all preserved); `test_approval_writes_only_profile_school_id_on_parents` (AC-28: role/division/assignments/active/email/password_hash unchanged; linked non-parent untouched); `test_in_flight_results_are_withdrawn_with_history_and_published_stay` (AC-11); `test_other_service_delivery_records_are_unchanged` (AC-12); `test_stale_or_decided_approve_is_409_and_changes_nothing` (AC-13); `test_audit_rows_same_transaction_and_per_moved_parent` (AC-27; injected audit failure rolls everything back — AC-16); `test_notifications_after_commit_and_failure_does_not_undo_approval` (AC-15, AC-22: incoming requester's notice carries the code only); `test_lock_timeout_is_409` (patch `TRANSFER_LOCK_TIMEOUT="200ms"` and hold a student row lock in another session).

- [ ] **Step 1–2:** tests; RED = 404.
- [ ] **Step 3: Implement** exactly the eight steps of spec §5.4 in the stated lock order (request → student → parents by id → results by id); `set_config('lock_timeout', :timeout, true)` with a bound parameter; `55P03` and `IntegrityError` → `db.rollback()` then 409 with the §5.3a strings; per-parent `AuditLog` rows; notifications after commit in a second transaction wrapped in `try/except` that logs `transfer_notification_failed` (IDs only); structured logs `student_transfer_approved` with counts.
- [ ] **Step 4: GREEN;** rerun ENH-004, SCH-006, SCH-007 files.
- [ ] **Step 5: REFACTOR** (split `_approve` into `_move_parents`, `_withdraw_results` only if it exceeds ~80 lines) and rerun.
- [ ] **Step 6: Commit.**

---

### Task 8: Reject, admin list with preview, admin history **[DB]** (spec §5.3, AC-21, AC-23)

**Files:** Modify `school_transfers.py`; Test `apps/api/tests/test_enh_005_admin_reads.py`.
**Produces:** `GET /overseas-admin/school-transfer-requests`, `POST .../{id}/reject`, `GET /overseas-admin/school-students/{id}/transfer-history`.

Tests: `test_reject_changes_only_the_request_and_notifies_with_redaction` (AC-13, AC-22); `test_admin_list_status_filter_pagination_and_envelope`; `test_preview_counts_are_correct_and_flag_missing_portfolio_staff`; `test_admin_list_preview_uses_a_constant_number_of_queries` (AC-23: count statements with a SQLAlchemy `before_cursor_execute` listener over 1 vs 25 rows — equal); `test_admin_history_lists_all_statuses_with_names`.

- [ ] Steps 1–6 as above (RED = 404).

---

### Task 9: Concurrency **[DB]** (AC-17)

**Files:** Test `apps/api/tests/test_enh_005_concurrency.py` (raw-SQL helpers as in `test_enh_004_student_promotion.py`).
Tests: `test_two_simultaneous_approvals_one_wins_one_409`; `test_promotion_racing_a_transfer_gets_403_and_writes_nothing_and_the_transfer_succeeds`; `test_sibling_transfers_sharing_a_parent_leave_the_correct_final_school_and_links`; `test_approve_versus_verify_never_deadlocks`.
- [ ] Write; run; expected GREEN if Task 7's lock order is right — if RED, fix the lock order in `_approve` (not the test); commit.

---

### Task 10: Cross-cutting checks (S8, S9, AC-18, AC-30, AC-32)

**Files:** Test `apps/api/tests/test_enh_005_hardening.py`.
Tests: `test_every_enh_005_mutation_route_is_post_and_no_get_mutates` (introspect `app.routes` for `school_transfers` handlers — **runs without DB**); `test_no_log_record_contains_code_reason_note_names_or_emails` (`caplog` over the filing/cancel/approve/reject flows — DB); `test_notification_action_urls_match_the_safe_pattern` (DB); regression sweep of the existing School suites (DB).
- [ ] Steps as above; commit.

---

### Task 11: Frontend foundation and components (spec §7.1)

**Files (create):** `apps/web/lib/apiErrors.ts` (`detailMessage(detail)`, `isPage(data)`), `lib/transfers.ts` (types, `STATUS_LABEL`, `STATUS_CLASS`), `components/SchoolTransferRequestForm.tsx`, `SchoolIncomingTransferForm.tsx`, `SchoolTransfersPanel.tsx`, `SchoolTransferHistory.tsx`, `AdminSchoolTransferPanel.tsx`, `AdminTransferRow.tsx`, `app/school/coordinator/transfers/page.tsx`; **modify:** `SchoolStudentDetailPanel.tsx` (`showTransfer`), `app/school/coordinator/students/[id]/page.tsx`, `app/school/parent/children/[id]/page.tsx` (history), `app/school/parent/dashboard/page.tsx` (school line only when children span >1 school), `components/WorkflowPanel.tsx` (`showSchoolTransfers`), `lib/navigation.ts` (`transfers` in `SCHOOL_NAV.coordinator`, `school-transfers` in `PORTAL_NAV["overseas/admin"]`). **Tests:** one `apps/web/tests/components/<Component>.test.tsx` each.
**Prerequisite:** `npm --prefix apps/web ci` in this worktree (installs from the existing lockfile; not a new dependency).

Per component, RED first with these named tests (vitest + Testing Library, `fetch` stubbed, `next/navigation` mocked as in `SchoolPromotionPanel.test.tsx`):
- `SchoolTransferRequestForm`: disabled + message when no destinations; pending banner replaces the form; submit disabled and "Sending request…" while in flight (double submit blocked); `422`/`409` shown in a `role="alert"` region that receives focus; `401` shows the sign-in link; success is a `role="status"` message and `router.refresh` is called; every field has a label tied by `aria-describedby`.
- `SchoolIncomingTransferForm`: format validation with `aria-invalid`; the identical neutral message for `202` regardless of input; `409` cap message; `429` message with the retry seconds; field cleared and refocused after success.
- `SchoolTransfersPanel`: skeleton + `aria-busy` on filter change while previous rows stay; empty and filtered-empty states with actions; error with "Try again"; "Load more" appends and updates "Showing X of Y"; redacted incoming row shows the code only and never `null`/blank; Cancel disabled while in flight and focus restored.
- `AdminSchoolTransferPanel`/`AdminTransferRow`: loads after first paint with skeleton; Approve → inline confirm with consequence text, focus on Confirm, Escape returns focus to the trigger; approve success removes the row and announces the outcome in the mounted status region; Reject shows the labelled note field with the visibility hint; `409` refetches; `.form-warning` when the destination has no portfolio staff; each button's `aria-label` names the student and contains its visible text.
- `SchoolTransferHistory`: renders nothing for an empty list, entries with a text badge, and an "unavailable" line when the load failed.
- `SchoolStudentDetailPanel`: unchanged output when `showTransfer` is false. Parent dashboard: school line only for a multi-school parent.

- [ ] Steps 1–6 per component (RED = module not found → then behavioural failures; GREEN; refactor; commit per component).

---

### Task 12: Playwright spec and browser validation **[DB + stack, user-gated]**

**Files:** Create `apps/web/tests/e2e/enh-005-school-transfer.spec.ts` (pattern of `enh-004-student-promotion.spec.ts`: two throwaway schools; file → approve → parent still sees the child; keyboard-only approve; no horizontal overflow at 320/768/1024/1440).
- [ ] The user brings the stack up **from this worktree's code** (the compose file builds from the checkout it is run in); the agent runs the spec and the manual checks (loading/empty/error, keyboard, mobile, reduced motion) and records evidence. **This task is what "browser validation" means; it is not complete until it is run.**

---

### Task 13: Documentation (spec §12)

**Files:** `docs/decisions/PRODUCT_DECISION_REGISTER.md` (`DEC-SCOPE-022`, D1–D9, A1–A3, S6, the free-text refinement), `docs/architecture/DATA_MODEL.md`, `API_CONTRACT.md` §12A (ten endpoints, §5.3a catalogue, redaction, `limit`/`offset` deviation), `RBAC_MATRIX.md` §2.12, `SECURITY_CONTROLS.md` §6A/§10, `THREAT_MODEL.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md` ENH-005 status (state exactly what is and is not verified), and a note on the ENH-004 plan's immutability claim.
- [ ] Write; check every claim against the code; commit.

---

### Task 14: Verification and handoff (no completion claim)

- [ ] Run every new backend and web test file plus the named regression files; record the exact commands and outputs.
- [ ] `git diff main...HEAD --stat`; confirm no `docs/sources/` change and no unrelated file.
- [ ] Hand off for browser validation (Task 12) and the independent Codex review. **Do not mark ENH-005 complete.**

---

## Self-Review

- **Spec coverage:** §5.1 → T3; §5.2 → T5, T6; §5.3 → T7, T8; §5.4 → T7, T9; §5.5 → T2, T5; §6/6.1 → T1, T4, T5, T7, T10; §7/7.1 → T11, T12; §8 → T1, T4, T11; AC-01…AC-32 mapped in the task test names (AC-19/24/25 → T11/T12); §12 → T13.
- **Placeholders:** none; DB-task tests are named with their assertions and are written in full at execution time against the ENH-004 fixtures.
- **Types:** schema names in Task 2's Interfaces are the ones Tasks 5–8 use; helper names `_filing_guard`, `_audit`, `_request_out`, `_approve`, `_require_transfer_admin` are defined where first produced.
