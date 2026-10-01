# ENH-020 Financial Support / Loan Assistance Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Career Counsellor tracks a school student's education-loan / financial-assistance / scholarship / funding-guidance
case through Required → Counselling → Documents → Application → Approved → Completed (or Closed), and coordinators,
principals and linked parents can read it.

**Architecture:** New table `school_funding_records` (migration `0053`, cut as `0051`), new router `apps/api/app/api/school_funding.py`
reusing `schools.py` helpers (portfolio/reader scoping, tier gate, notifications, serializer names), two new usage counts in
`schools.service_usage`. Frontend: one lib file, a form, a counsellor panel + page, and a read-only card on three existing
student pages. No new dependency.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic, PostgreSQL 16; Next.js (App Router, server
components), React, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md` (D1–D13, AC01–AC20).

## Global Constraints

- Statuses exactly: `required`, `counselling`, `documents`, `application`, `approved`, `completed`, `closed`; forward one step or to `closed`; `completed`/`closed` final.
- Support types exactly: `education_loan`, `financial_assistance`, `scholarship`, `funding_guidance`; `scholarship` → `scholarship_assistance`, the rest → `loan_assistance`.
- Caps: `provider_name` ≤200, `amount_text` ≤120, `closure_reason` ≤500 (single-line, `_clean_text`), `notes` ≤4000 (multi-line, NUL refused).
- Errors are `{"detail": "<sentence for people>"}`; snake_case; lists are bare arrays; not paginated; no `Idempotency-Key`.
- One open case per (`school_student_id`, `school_id`, `support_type`), DB-enforced.
- Records carry `school_id` (creating school); staff see only `record.school_id == student.school_id`; parents see all of their child's.
- `school_teacher` never reads; only `career_counselor` writes.
- No record contents (provider, amount, notes, closure reason) in audit rows, logs or notifications.
- Tier gate before any `db.add`; parents notified only after the commit; notification failure never undoes a save.
- Existing response shapes unchanged except `/school/entitlements` `used` for `loan_assistance`/`scholarship_assistance` (null → int).
- No new npm/pip dependency. Reuse: `PortalShell`, `card`, `table-wrap`, `status`, `record-details`, `FormMessage`, `SearchableSelect`, `refocus`, `detailMessage`, `accessUnavailable`, `skeleton-line`.

## Review Focus

1. Whitespace-only `closure_reason` when closing → treated as missing: 422 "Give a reason for closing this case." (Task 4).
2. `closure_reason` sent with a non-closing PATCH (including a notes-only edit) → 422, nothing written (Task 4).
3. A student with **no** linked parent → create/advance still 201/200, zero notifications, no error (Task 3).
4. A parent linked to two children at two schools → E4 for each child returns only that child's cases; an unlinked child → 403 (Task 5).
5. Indic names with zero-width joiners in `provider_name` are accepted; bidi-override characters are refused (Task 1).

---

### Task 0: Record the decision (coding gate)

**Files:** Modify `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append `DEC-SCOPE-045`), `docs/delivery/ENHANCEMENT_BACKLOG.md` (row 132, row 943, §ENH-020 status line, §3 table row).

- [ ] Append `### DEC-SCOPE-045 — ENH-020 financial support / loan assistance tracking` with **Status:** CONFIRMED_CURRENT (2026-10-01, in-session, `EXPLICIT_APPROVAL` per answer, provisional number), the trigger (audit result), D1–D13 copied from spec §2, evidence (`School CRM.md` §21, `EVID-014`; `DEC-SCOPE-017`), "New Feature ID authorized: ENH-020".
- [ ] Backlog: row 132 → "in progress (`DEC-SCOPE-045`)"; §3 ENH-020 row → "Resolved 2026-10-01: `DEC-SCOPE-045`"; §ENH-020 gets "**Audit result (2026-10-01):** no Overseas equivalent — new tracker; spec/plan paths".
- [ ] Commit `docs(enh-020): record DEC-SCOPE-045`.

### Task 1: Schema constants and request models

**Files:** Modify `apps/api/app/schemas.py` (after the ENH-026 block, before ENH-027). Test: `apps/api/tests/test_enh_020_schemas.py`.

**Produces:** `FundingSupportType`, `FundingStatus` (Literals); `FUNDING_SUPPORT_TYPE_LABEL: dict[str,str]`;
`FUNDING_STATUS_LABEL: dict[str,str]`; `FUNDING_STATUS_NEXT: dict[str, frozenset[str]]`; `FUNDING_FINAL_STATUSES: frozenset[str]`;
`funding_transition_allowed(current: str, requested: str) -> bool`; `FundingRecordCreate`, `FundingRecordUpdate` (`extra="forbid"`).

- [ ] **Step 1: failing tests** (`test_enh_020_schemas.py`):
  - `test_every_status_pair` — parametrize over all 7×7 pairs; allowed iff `requested == current` or in the table (`required→counselling|closed`, … `approved→completed|closed`, finals → nothing).
  - `test_finals_are_completed_and_closed`; `test_labels_cover_every_value` (`set(FUNDING_STATUS_LABEL) == set(get_args(FundingStatus))`, same for types).
  - `test_create_forbids_status_owner_and_school` — `FundingRecordCreate.model_validate({..., "status": "approved"})` raises; `validation_message` == `"status is not an accepted field"`; same for `school_id`, `career_counselor_user_id`.
  - `test_update_forbids_support_type` → `"support_type is not an accepted field"`.
  - `test_malformed_student_id_is_a_validation_error` (`"not-a-uuid"` raises `ValidationError`).
  - `test_single_line_fields_trim_and_cap` — `"  HDFC  "` → `"HDFC"`, `"   "` → `None`, 201 chars → error `"provider_name must be at most 200 characters"`; `amount_text` 121; `closure_reason` 501; newline in `provider_name` → error.
  - `test_indic_zwj_accepted_bidi_refused` (Review Focus 5): `"ಕರ್ನಾಟಕ‍ ಬ್ಯಾಂಕ್"` accepted; `"‮knab"` refused.
  - `test_notes_multiline_capped_and_nul_refused` — `"a\nb"` kept; 4001 chars refused (`"notes must be at most 4000 characters"`); `"\x00"` refused; `None` → `""`.
- [ ] **Step 2:** run `pytest tests/test_enh_020_schemas.py -q` → ImportError (names undefined).
- [ ] **Step 3: implement** in `schemas.py`:

```python
# --- ENH-020: financial support / loan assistance (docs/superpowers/specs/2026-10-01-enh-020-funding-support-tracking-design.md §3) ---

FundingSupportType = Literal["education_loan", "financial_assistance", "scholarship", "funding_guidance"]
FundingStatus = Literal["required", "counselling", "documents", "application", "approved", "completed", "closed"]
FUNDING_SUPPORT_TYPE_LABEL: dict[str, str] = {
    "education_loan": "Education loan", "financial_assistance": "Financial assistance", "scholarship": "Scholarship", "funding_guidance": "Funding guidance",
}
FUNDING_STATUS_LABEL: dict[str, str] = {
    "required": "Required", "counselling": "Counselling", "documents": "Documents", "application": "Application",
    "approved": "Approved", "completed": "Completed", "closed": "Closed",
}
FUNDING_STATUS_NEXT: dict[str, frozenset[str]] = {  # D3: one step forward, or Closed from any open stage
    "required": frozenset({"counselling", "closed"}), "counselling": frozenset({"documents", "closed"}),
    "documents": frozenset({"application", "closed"}), "application": frozenset({"approved", "closed"}),
    "approved": frozenset({"completed", "closed"}), "completed": frozenset(), "closed": frozenset(),
}
FUNDING_FINAL_STATUSES: frozenset[str] = frozenset({"completed", "closed"})
FUNDING_NOTES_MAX = 4000


def funding_transition_allowed(current: str, requested: str) -> bool:
    return requested == current or requested in FUNDING_STATUS_NEXT[current]


def _funding_notes(value) -> str:
    text_value = _career_notes(value)
    if len(text_value) > FUNDING_NOTES_MAX:
        raise ValueError(f"must be at most {FUNDING_NOTES_MAX} characters")
    return text_value


class FundingRecordFields(BaseModel):
    """ENH-020 body fields shared by create and update (spec §3.3). extra="forbid": ids, owners, school and dates are never writable."""

    model_config = {"extra": "forbid"}
    provider_name: str | None = None
    amount_text: str | None = None
    notes: str = ""

    @field_validator("provider_name", mode="before")
    @classmethod
    def _provider(cls, value):
        return _clean_text(value, 200)

    @field_validator("amount_text", mode="before")
    @classmethod
    def _amount(cls, value):
        return _clean_text(value, 120)

    @field_validator("notes", mode="before")
    @classmethod
    def _notes(cls, value):
        return _funding_notes(value)


class FundingRecordCreate(FundingRecordFields):
    school_student_id: UUID
    support_type: FundingSupportType


class FundingRecordUpdate(FundingRecordFields):
    """PATCH body, presence-aware (`model_fields_set`). `expected_status` is the optional precondition (409 on mismatch)."""

    status: FundingStatus | None = None
    closure_reason: str | None = None
    expected_status: FundingStatus | None = None

    @field_validator("closure_reason", mode="before")
    @classmethod
    def _reason(cls, value):
        return _clean_text(value, 500)
```

- [ ] **Step 4:** tests pass. **Step 5:** commit `feat(enh-020): funding record schemas`.

### Task 2: Model and migration 0053 (cut as 0051)

**Files:** Modify `apps/api/app/models.py` (after `SchoolCareerRecord`); Create `apps/api/alembic/versions/0053_school_funding_records.py`; Test: `apps/api/tests/test_enh_020_migration.py`.

**Produces:** `SchoolFundingRecord` with columns per spec §3.1; constraint/index names `ck_funding_record_support_type`,
`ck_funding_record_status`, `ck_funding_record_closure`, `uq_funding_record_open_student_type`, `ix_school_funding_records_school_type`,
plus `ix_school_funding_records_school_student_id` (from `index=True`).

- [ ] **Step 1: failing tests** (pattern `test_enh_030_migration.py`): `test_migration_follows_0050_and_is_the_single_head`;
  `test_table_matches_the_model` (columns→nullable map, check names, index names incl. the partial unique one);
  `test_status_and_type_literals_match_the_check_constraints` (parse the model's CheckConstraint SQL text, compare with `get_args`);
  `test_closed_needs_reason_at_the_database` (insert a `closed` row with no reason via ORM → `IntegrityError`);
  `test_second_open_case_is_refused_but_a_closed_one_is_not` (two `required` rows same student/school/type → IntegrityError naming `uq_funding_record_open_student_type`; with the first `closed`+reason → ok).
- [ ] **Step 2:** run → fails (module/table missing). Apply `alembic upgrade head` in the test container after Step 3.
- [ ] **Step 3: implement** model:

```python
class SchoolFundingRecord(Base, TimestampMixin):
    """ENH-020 (DEC-SCOPE-045) -- School CRM.md §21 financial support / loan assistance case. `school_id` is the student's school
    when the case was opened (D12): staff see a case only while the student is still there; a parent always sees it."""

    __tablename__ = "school_funding_records"
    __table_args__ = (
        CheckConstraint("support_type IN ('education_loan', 'financial_assistance', 'scholarship', 'funding_guidance')", name="ck_funding_record_support_type"),
        CheckConstraint("status IN ('required', 'counselling', 'documents', 'application', 'approved', 'completed', 'closed')", name="ck_funding_record_status"),
        CheckConstraint("(status = 'closed') = (closure_reason IS NOT NULL)", name="ck_funding_record_closure"),
        Index("uq_funding_record_open_student_type", "school_student_id", "school_id", "support_type", unique=True, postgresql_where=text("status NOT IN ('completed', 'closed')")),
        Index("ix_school_funding_records_school_type", "school_id", "support_type"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    school_student_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("school_students.id"), index=True)
    school_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("schools.id"))
    support_type: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20))
    status_changed_on: Mapped[date] = mapped_column(Date)
    provider_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_text: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    closure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    career_counselor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    updated_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
```

  Migration `0053_school_funding_records` (revises `0052_agent_staff_permissions`; cut as `0051` on `0050`): existing-table guard as `0048`;
  `op.create_table` with the same columns/FKs/checks (`created_at`/`updated_at` `server_default=sa.func.now()`, NOT NULL);
  `op.create_index` for the student index, the composite index, and the partial unique index
  (`postgresql_where=sa.text("status NOT IN ('completed', 'closed')")`); `downgrade()` drops the table.
- [ ] **Step 4:** `alembic upgrade head`, `alembic check` (no drift), tests pass; `alembic downgrade -1 && alembic upgrade head` round-trips.
- [ ] **Step 5:** commit `feat(enh-020): school_funding_records table (0051)`.

### Task 3: E1 create + router skeleton + serializer

**Files:** Create `apps/api/app/api/school_funding.py`; Modify `apps/api/app/main.py` (register `school_funding.router`),
`apps/api/app/api/schools.py` (add `FUNDING_SERVICE_KEYS` beside `TEST_PREP_SERVICE_KEYS`). Test: `apps/api/tests/test_enh_020_funding_records.py`.

**Consumes:** `_student_in_portfolio`-equivalent pieces from `schools.py`: `_portfolio_school_ids`, `OUTSIDE_PORTFOLIO`,
`require_school_entitlement`, `_today_ist`, `_master_fields_or_422`, `_user_names`, `_notify_student_parents`.
**Produces:** `router`; `_records_out(db, rows) -> list[dict]`; `_deny(db, user, reason, entity_type, entity_id, message) -> NoReturn`;
`_notify_parents(db, student, title, body, ids) -> None`; constants `CREATE_ACTION="school.funding_record_create"`,
`UPDATE_ACTION="school.funding_record_update"`, `DENIED_ACTION="school.funding_record_denied"`, `ENTITY="school_funding_record"`.

- [ ] **Step 1: failing tests** (fixture `world` = `mk_school(label="E20", students=2)` platinum + `mk_staff(role="career_counselor")`):
  - `test_create_starts_at_required_today` (AC01): 201; keys == spec response set; `status=="required"`, `status_changed_on==TODAY` (IST), `counselor_name`; audit `school.funding_record_create` with `metadata_json == {"support_type": ..., "fields": [...]}` and **no** provider/notes text in it; parent `Notification` count +1, title "Funding support update for {name}", body contains "Education loan" and "Required" and not the provider.
  - `test_create_with_no_linked_parent_still_succeeds` (Review Focus 3): second student has no parent → 201.
  - `test_create_denials` (AC02/AC18): coordinator → 403 + one `school.funding_record_denied` row (`metadata_json["reason"]=="role"`); outsider counsellor → 403 `OUTSIDE_PORTFOLIO` + denied row (`"outside_portfolio"`); unknown student → 404; malformed id → 422; no record rows written.
  - `test_tier_gate_is_per_type` (AC03): gold school → `scholarship` 201, the three others 403 with the helper's message and a `school.tier_access_denied` row; bronze → scholarship 403; platinum → all four 201.
  - `test_second_open_case_is_409_until_finished` (AC04): second `education_loan` → 409 detail `"{name} already has an open education loan case. Open it from the list to update it."`; set the first to `closed` directly in DB → 201.
  - `test_concurrent_creates_one_wins` (AC04): two clients, `asyncio.gather` → sorted codes `[201, 409]`; exactly one row.
  - `test_create_forbids_status_and_owner_fields` (AC10).
  - `test_create_survives_notification_failure` (AC12): monkeypatch `school_funding._notify_student_parents` to raise → 201, row saved, warning logged (`caplog`, message `funding_record_notify_failed`).
  - `test_logs_carry_no_contents` (AC19): `caplog` at INFO; provider/notes strings absent from every record's message and `extra_fields`.
- [ ] **Step 2:** run → 404 (route missing).
- [ ] **Step 3: implement** `school_funding.py` (module docstring cites the spec; imports helpers from `app.api.schools`):

```python
@router.post("/funding-records", status_code=201)
async def create_funding_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Spec §4.1. One transaction up to the commit; parents are notified after it."""
    if user.role != "career_counselor":
        await _deny(db, user, "role", ENTITY, None, COUNSELOR_REQUIRED)
    fields = _master_fields_or_422(FundingRecordCreate, payload)
    student = await _locked_student(db, fields.school_student_id)
    if student is None:
        raise HTTPException(404, "Student not found")
    if student.school_id not in await _portfolio_school_ids(db, user):
        await _deny(db, user, "outside_portfolio", "school_student", student.id, OUTSIDE_PORTFOLIO)
    await require_school_entitlement(db, user, student.school_id, FUNDING_SERVICE_KEYS[fields.support_type])
    name, type_label = student.full_name, FUNDING_SUPPORT_TYPE_LABEL[fields.support_type]
    record = SchoolFundingRecord(
        school_student_id=student.id, school_id=student.school_id, support_type=fields.support_type, status="required",
        status_changed_on=_today_ist(), provider_name=fields.provider_name, amount_text=fields.amount_text, notes=fields.notes,
        career_counselor_user_id=user.id,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        if OPEN_CASE_INDEX not in str(exc.orig):
            raise
        logger.info("funding_record_duplicate_open", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "support_type": fields.support_type}})
        raise HTTPException(409, f"{name} already has an open {type_label.lower()} case. Open it from the list to update it.") from None
    sent = sorted(fields.model_fields_set - {"school_student_id", "support_type"})
    db.add(AuditLog(user_id=user.id, action=CREATE_ACTION, entity_type=ENTITY, entity_id=str(record.id), metadata_json={"support_type": fields.support_type, "fields": sent}))
    await db.commit()
    await db.refresh(record)
    out = (await _records_out(db, [record]))[0]
    ids = {"actor_id": str(user.id), "record_id": str(record.id), "student_id": str(student.id)}
    logger.info("funding_record_create", extra={"extra_fields": {**ids, "support_type": fields.support_type}})
    await _notify_parents(db, student, title=f"Funding support update for {name}", body=f"{type_label} support is now being tracked (Required).", ids=ids)
    return out
```

  `_deny` adds the denied `AuditLog` (`outcome="denied"`, `metadata_json={"role": user.role, "reason": reason}`), commits
  (on `SQLAlchemyError`: rollback + `logger.exception("funding_record_denied_audit_failed")`, the denial stands), logs
  `funding_record_denied` (ids/role/reason only) and raises `HTTPException(403, message)`. `_notify_parents` wraps
  `_notify_student_parents(..., action_url=f"/school/parent/children/{student.id}")` + `commit` in `try/except Exception`
  → `rollback` + `logger.warning("funding_record_notify_failed", ...)`. `_locked_student` = `select(SchoolStudent)…with_for_update().execution_options(populate_existing=True)`.
- [ ] **Step 4:** tests pass. **Step 5:** commit `feat(enh-020): create funding support cases`.

### Task 4: E2 update

**Files:** Modify `apps/api/app/api/school_funding.py`; Test: `apps/api/tests/test_enh_020_funding_records.py` (append).

- [ ] **Step 1: failing tests:**
  - `test_full_lifecycle` (AC05): required→counselling→documents→application→approved→completed, each 200, `status_changed_on` reset, `updated_by_name`.
  - `test_skips_and_backward_moves_are_422` (parametrized: required→documents, counselling→required, approved→application): detail starts `"Cannot change status from "`.
  - `test_closing_needs_a_reason` (AC06, Review Focus 1): `{"status":"closed"}` and `{"status":"closed","closure_reason":"   "}` → 422 `"Give a reason for closing this case."`; with reason → 200, `closure_reason` returned.
  - `test_reason_only_when_closing` (Review Focus 2): `{"notes":"x","closure_reason":"y"}` on an open case → 422 `"A closure reason can only be given when closing the case."`, nothing written.
  - `test_final_cases_are_read_only` (AC07): after completed / closed, any PATCH → 422 `"This case is Completed and can no longer be changed."` / `"…Closed…"`.
  - `test_stale_expected_status_is_409` (AC08): exact detail `"This case was changed by someone else (now Counselling). Reload to see the latest."`, no update audit row.
  - `test_repeat_patch_is_a_noop` (AC05): resend current values → 200, zero update audits.
  - `test_update_audit_has_names_and_status_only` (AC19).
  - `test_parents_notified_only_on_status_change` (AC12).
  - `test_support_type_and_owner_cannot_be_patched` (AC10): `support_type`, `school_student_id`, `school_id`, `career_counselor_user_id` → 422 `"<key> is not an accepted field"`.
  - `test_update_denials` (AC18): coordinator, outsider counsellor → 403 + denied row; unknown id → 404.
  - `test_downgrade_grandfathers_existing_cases` (AC09): platinum case; `PATCH /overseas-admin/schools/{id}` tier→gold (as admin); advance → 200; new `education_loan` create → 403.
  - `test_concurrent_transitions_serialize` (copy `_held`/`_client_for` from ENH-026 for `SchoolFundingRecord`) → `[200, 409]`.
  - `test_a_patch_racing_a_transfer_is_refused` (copy ENH-026 race test) → 403 `OUTSIDE_PORTFOLIO`, nothing written.
  - `test_previous_school_case_is_read_only_after_transfer` (AC17): `move_student_directly` to a second school whose counsellor portfolio covers it → that counsellor's PATCH → 403 `"This case belongs to the student's previous school and can no longer be changed."`.
- [ ] **Step 2:** run → 405/404.
- [ ] **Step 3: implement** `PATCH /funding-records/{record_id}` exactly per spec §4.2 steps 1–12 (lock record, lock student, portfolio and
  `school_id` checks with `_deny`, `require_school_entitlement(..., grandfathered_since=record.created_at)`, validate, `expected_status` 409,
  final 422, transition 422, closure-reason rules, no-op return, `updated_by_user_id`, audit `{"changed_fields": [...], "status": {"old","new"}}`
  when status changed, commit, response, notify on status change with body `f"{type_label} support is now at {status_label}."`, log `funding_record_update`).
  Tracked fields: `("status", "provider_name", "amount_text", "notes", "closure_reason")`.
- [ ] **Step 4:** tests pass. **Step 5:** commit `feat(enh-020): advance and close funding support cases`.

### Task 5: E3/E4 reads

**Files:** Modify `school_funding.py`; Test: `apps/api/tests/test_enh_020_reads.py`.

- [ ] **Step 1: failing tests:**
  - `test_counsellor_list_open_first_then_recent` (E3): open cases before finished; only portfolio schools; another school's case absent.
  - `test_student_reads_by_role` (AC11): coordinator/principal own school 200; other school's coordinator 403 + denied row; linked parent 200; unlinked parent 403; **assigned teacher 403** `"Funding support cases are not visible to teachers."` + denied row (`"teacher"`); academic_team 403; counsellor in portfolio 200, outside 403.
  - `test_parent_with_children_at_two_schools` (Review Focus 4).
  - `test_transfer_hides_previous_school_cases_from_staff` (AC17): after `move_student_directly`, new coordinator E4 → `[]`, new counsellor E3 lacks it, parent E4 still lists it; new school can create the same type → 201.
  - `test_reads_are_not_tier_gated`: tier set to `None` → E3/E4 still 200.
  - `test_response_has_no_school_id_or_master_data`.
- [ ] **Step 2:** run → 404. **Step 3: implement** E3 (`join SchoolStudent`, `SchoolFundingRecord.school_id.in_(portfolio)`, `SchoolStudent.school_id == SchoolFundingRecord.school_id`,
  order `case((status.in_(FINAL), 1), else_=0), updated_at.desc()`) and E4 (teacher deny → role allowlist deny → `_load_student_for_reader` with 403 re-raised through `_deny(..., "scope", "school_student", student_id, exc.detail)` → staff filter `school_id == student.school_id`).
- [ ] **Step 4:** pass. **Step 5:** commit `feat(enh-020): funding support case reads`.

### Task 6: Entitlement usage + intentional test updates + seed

**Files:** Modify `apps/api/app/api/schools.py` (`service_usage`, `school_entitlements` docstring), `apps/api/app/seed.py` (comment + demo cases),
`apps/api/tests/test_sch_011_entitlements.py:138-139`, `apps/api/tests/test_enh_016_contracts.py:70-73,94`; Test: `apps/api/tests/test_enh_020_usage.py`.

- [ ] **Step 1: failing tests** (`test_enh_020_usage.py`): `test_usage_counts_distinct_students_per_creating_school` (AC13: 2 loan cases + 1 funding_guidance for 2 students → `loan_assistance == 2`; 1 scholarship → 1; a closed case still counts; a case at school B for a transferred student counts for B, not the student's new school); `test_other_usage_keys_unchanged` (snapshot of all other keys before/after creating cases); `test_scorecard_and_pipeline_still_not_tracked` (AC14: `SCORECARD_AREAS` scholarship keys None, `UNTRACKED_OUTCOMES` has `scholarships`, ENH-017 `NOT_TRACKED` keys unchanged).
  Update `test_sch_011_entitlements.py` loop to `("alumni_network", "parent_help_desk")` and assert `loan_assistance`/`scholarship_assistance` are `0`; update `test_enh_016_contracts.py` usage expectations to `0` for both keys.
- [ ] **Step 2:** run → `None != 2`. **Step 3: implement** two `_per_school` calls (spec §5) with `LOAN_SUPPORT_TYPES = tuple(t for t, key in FUNDING_SERVICE_KEYS.items() if key == "loan_assistance")`; seed: one `education_loan` case at `documents` and one `scholarship` case at `required` for the demo school's students, idempotent (`if not await db.scalar(select(SchoolFundingRecord.id).limit(1))`).
- [ ] **Step 4:** pass, plus full `test_enh_016_*`, `test_enh_017_*`, `test_sch_011_*`, `test_enh_022_*`, `test_enh_023_*`. **Step 5:** commit `feat(enh-020): count loan and scholarship assistance usage`.

### Task 7: Frontend lib + form

**Files:** Create `apps/web/lib/fundingRecords.ts`, `apps/web/components/FundingRecordForm.tsx`; Tests `apps/web/tests/components/fundingRecords.test.ts`, `apps/web/tests/components/FundingRecordForm.test.tsx`.

**Produces:** `FundingStatus`, `FundingSupportType`, `FundingRecord` types; `SUPPORT_TYPE_LABEL`, `STATUS_LABEL`; `nextStatuses(s)`; `isFinal(s)`;
`stageText(s)` ("Stage 3 of 6 · Documents" / "Completed" / "Closed"); `FundingRecordForm({ students, record?, onDone, onCancel })`.

- [ ] **Step 1: failing tests:** lib — `nextStatuses` mirrors the server table for all 7; `stageText`. Form — create posts `{school_student_id, support_type, provider_name, amount_text, notes}` to `/api/v1/school/funding-records`; edit offers only current + next in "Stage"; choosing Closed shows a required "Reason for closing" and focuses it; edit sends `expected_status`; 409 shows "Reload"; 5xx shows the kept-entry text; network failure shows `NOT_COMPLETED`; button disabled + `aria-busy` while saving; `maxLength` attributes 200/120/500/4000.
- [ ] **Step 2:** `npx vitest run tests/components/fundingRecords.test.ts tests/components/FundingRecordForm.test.tsx` → fail (modules missing).
- [ ] **Step 3: implement** following `CareerRecordForm.tsx` (raw `fetch`, `inFlight` ref, `FormMessage`, `detailMessage`, `NOT_COMPLETED`, `SearchableSelect` for the student, `router.refresh()` on success and on Reload).
- [ ] **Step 4:** pass. **Step 5:** commit `feat(enh-020): funding case form`.

### Task 8: Counsellor panel, page, nav, loading, phone CSS

**Files:** Create `apps/web/components/SchoolFundingRecordsPanel.tsx`, `apps/web/app/school/career-counselor/funding/page.tsx`, `.../funding/loading.tsx`;
Modify `apps/web/lib/navigation.ts`, `apps/web/app/globals.css`; Tests `apps/web/tests/components/SchoolFundingRecordsPanel.test.tsx`, `apps/web/tests/components/FundingLoading.test.tsx`.

- [ ] **Step 1: failing tests:** open cases table (headers Student/Type/Stage/Since/Provider), finished cases inside `<details>` with count, no Edit on finished; empty text; no-portfolio text; Edit opens the form, heading focused, Escape returns focus to the Edit button; Edit button accessible names unique; table cells carry `data-label`; nav contains `/school/career-counselor/funding`; loading renders inside `PortalShell` with `aria-busy`.
- [ ] **Step 2:** run → fail. **Step 3: implement** (patterns: `SchoolCareerRecordsPanel`, dashboard `loading.tsx`, `accessUnavailable`); CSS: add `.table.funding-records` selectors to the existing `psy-records` phone rule and a `.funding-panel .btn { min-height: 44px }` phone rule.
- [ ] **Step 4:** pass. **Step 5:** commit `feat(enh-020): counsellor funding page`.

### Task 9: Read-only card on student pages

**Files:** Create `apps/web/components/FundingRecordsCard.tsx`; Modify `apps/web/app/school/parent/children/[id]/page.tsx`, `apps/web/app/school/coordinator/students/[id]/page.tsx`, `apps/web/app/school/principal/students/[id]/page.tsx`; Test `apps/web/tests/components/FundingRecordsCard.test.tsx`.

- [ ] **Step 1: failing tests:** renders each case as `record-details` (Type, Stage, Provider, Amount, Notes, Closure reason, Updated by); `null` → error text; `[]` → empty text; no buttons.
- [ ] **Step 2:** fail. **Step 3: implement** card + `loadFundingRecords(id)` (`serverApi` E4, `.catch(() => null)`) joined into each page's existing `Promise.all`.
- [ ] **Step 4:** pass + `npm run typecheck` + `npm run lint`. **Step 5:** commit `feat(enh-020): funding cases on student pages`.

### Task 10: Playwright

**Files:** Create `apps/web/tests/e2e/enh-020-funding-support.spec.ts` (setup copied from `enh-026-counselling-record.spec.ts`).

- [ ] Flows: counsellor creates an education-loan case, advances one stage by keyboard, closes with a reason; a 320px and 768px viewport pass has no horizontal scroll and stacked rows; axe scan (if the repo's existing e2e uses `@axe-core/playwright`; otherwise skip axe — no new dependency) ; parent sees the read-only card; teacher's direct E4 call → 403.
- [ ] Run against the `enh020` stack (`web`, `api`) — **browser validation is a separate, later step owned by the user**; this task only adds the spec and runs it if the stack is up.
- [ ] Commit `test(enh-020): e2e funding support flow`.

### Task 11: Contract docs

**Files:** `docs/architecture/API_CONTRACT.md` §12A (E1–E4 rows, entitlements addendum), `docs/architecture/DATA_MODEL.md` §6.25, `docs/architecture/RBAC_MATRIX.md` §2.12, `docs/ux/SCREEN_CATALOG.md` + `screen_catalog.json` (SCR-SCH-041/041), `docs/ux/ROLE_NAVIGATION.md`, `docs/quality/RTM.md`.

- [ ] Write each entry from the spec; commit `docs(enh-020): contracts, data model, RBAC, screens, RTM`.

### Task 12: Verification sweep (no completion claim)

- [ ] API container: `ruff format --check app tests`, `ruff check .`, `mypy app`, `alembic upgrade head`, `alembic check`, full `pytest -q`.
- [ ] Web: `npm run typecheck`, `npm run lint`, `npx vitest run`, `npm run build`.
- [ ] Record results in the ENH-020 backlog entry as "IMPLEMENTED — NOT YET COMPLETE (pending browser validation and independent review)".
