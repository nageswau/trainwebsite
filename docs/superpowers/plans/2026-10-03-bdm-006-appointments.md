# bdm-006 Appointments — Implementation Plan

> **Renumbered 2026-10-03 on merging `main`:** bdm-010 (`DEC-SCOPE-063`, `0068_bdm_trips`) merged first, so bdm-006 is now `DEC-SCOPE-064` and its migration is `0069_bdm_appointments` (`down_revision = "0068_bdm_trips"`). Renumbered again on merging `main` @ `e376c25c` (2026-10-05): bdm-003's `0069_bdm_org_profiles` and AGN-022 / bdm-003 / AGN-019 / AGN-020 (`DEC-SCOPE-064`…`067`) reached `main` first, so bdm-006 is now **`DEC-SCOPE-068`** with migration **`0070_bdm_appointments`** after `0069_bdm_org_profiles` (`down_revision = "0069_bdm_org_profiles"`). The task text below is the execution record and keeps the original `DEC-SCOPE-063` / `0068_bdm_appointments` numbers.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** BDMs book and manage appointments with every §2 field, a per-type type list, an enforced and recorded status lifecycle (confirm / reschedule / cancel / no-show / complete with a minimal outcome), an overlap warning, and real Last / Next meeting dates on organizations — without changing any other contract or row.

**Architecture:** Two new tables (migration `0068_bdm_appointments`) behind a new flat router `app/api/bdm_appointments.py` and a new service `app/services/bdm_appointments.py`, reusing bdm-001's `bdm_context` and bdm-002's `bdm_organizations.load_scoped` unchanged. bdm-002's organization outputs gain two correlated subqueries. The web adds `lib/bdmAppointments.ts`, nine client components and five server pages under `/bdm/appointments` and `/bdm/manager/appointments`, plus an "Add appointment" link on the organization page.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic 2, Alembic, PostgreSQL; Next.js App Router, React, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-03-bdm-006-appointments-design.md` (revision 2). Read §3 (A1–A8), §5.4 (matrix), §5.7 (locks) and §12 before any task.

## Global Constraints

- Migration `0068_bdm_appointments`, `down_revision = "0067_audit_entity_index"`. Decision: the next free `DEC-SCOPE-NNN` on `origin/main` (today `DEC-SCOPE-063`; unmerged bdm-010 also claims `0068` / `063`). Re-run `git fetch origin && git log --oneline HEAD..origin/main -- apps/api/alembic/versions docs/decisions` before Task 1 and before merge; renumber migration + DEC if `main` moved (0066's re-chain idiom).
- No new dependency (Python or npm). No change to `services/bdm.py`, `rbac.py`, `middleware.ts`, auth, `admin.py`, the legacy `Appointment` model, `/overseas/appointments`, `services/portal.py`.
- Only additive API change to existing routes: bdm-002 organization list / detail return real `last_meeting_at` / `next_meeting_at` (same names, `datetime | null`). Nothing else in their responses changes.
- Every write: one transaction — scope → lock → validate → change → event → `AuditLog` → one `commit()` in the route. Services never commit.
- Lock order is always organization → appointment: create and a PATCH that changes `contact_id` lock the organization (`bdm_organizations.load_scoped(..., lock=True)`) before the appointment; every other write locks only the appointment (`FOR UPDATE OF bdm_appointments`).
- Errors: string `detail` for 403/404/409; FastAPI's list for 422 (plus string-detail 422s raised by the service); structured `{message, code: "possible_overlap", matches, total}` only for the overlap 409.
- Out of scope → 404 "Appointment not found" (same as nonexistent). Organization out of type scope → 404 "Organization not found".
- Status codes: illegal / terminal transition and PATCH on a closed appointment → 409; past `starts_at`, complete / no-show before start, foreign type / outcome, foreign contact, archived organization on create → 422.
- Logs (`app.bdm`) and audit metadata carry ids, field names, statuses, `starts_at` values and counts only — never contact snapshot values, purpose, remarks, location or reasons.
- Code `APT-%06d` from `bdm_appointment_code_seq`, never client-supplied. `starts_at` normalized to the minute in the schema. "Now" = the database clock (`select(func.now())`), read once per request.
- Web: reuse global classes (`action-card`, `btn`, `btn secondary small`, `table-wrap`, `form-error`, `form-message`, `empty`, `muted`, `badge`, `status` / `status pending` / `status error`, `visually-hidden`, `portal-content`, `portal-title`, `eyebrow`, `field`, `actions`), `PortalShell`, `FormMessage`, `SearchableSelect`, `BdmConfirm`, `sendJson` / `sendRequest`, `isPage`, `detailMessage`, `NOT_COMPLETED`, `useFocusAfterRender`, `formatSchoolDateTime`, `LINK_STYLE`, `display`. Heading hierarchy follows the existing BDM pages (eyebrow + `h2` page title in `portal-title`, `h3` card titles) — this refines spec §12.2 R-F1's "h1" to the established convention, as bdm-002's plan did.
- Tests: lite set only (owner's standing choice). The full backend and full web suites are run by the owner.

**Spec refinements recorded here (written into the spec in Task 14):**
1. `starts_at` minute normalization happens in the schema (`AfterValidator`), not the service — it is boundary input shaping.
2. `expected_revenue` is returned as a JSON string (Pydantic's `Decimal` serialization, as other money fields); the web type is `string | null`.
3. bdm-002's list and detail rendered `last_meeting_at` / `next_meeting_at` through `display()`, which would print a raw ISO string once values are real. Both switch to `formatSchoolDateTime(v, true)` (Task 9).

## Test commands (used by every task)

Run from the worktree root. Docker Desktop must be running (the owner starts it — never start or stop the stack yourself).

```bash
WT="C:/Users/admin/Documents/edu/EduSphere_Claude_From_Scratch_Final_v3/edusphere/.claude/worktrees/bdm-006"
# API (DB-backed). <paths> e.g. tests/test_bdm_006_appointments.py
docker compose -p bdm006 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm \
  -v "$WT/apps/api:/app" api-test sh -c "alembic upgrade head && python -m pytest -q <paths>"
# Web (no node_modules in the worktree)
MSYS_NO_PATHCONV=1 docker compose -p bdm006 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps \
  -v "$WT/apps/web:/app" -v /app/node_modules web-test sh -c "npx vitest run <paths>"
```

Below, `API_TEST <paths>` and `WEB_TEST "<cmd>"` mean these two commands. Always use the Windows-form `$WT` path (a `$PWD` mount silently mounts a stale tree).

## Review Focus

1. **A create retried after a lost response** — the second POST returns `possible_overlap` naming the appointment just created; never two silent rows. Pinned in Task 4.
2. **Two tabs: one confirms while the other cancels** — exactly one 200 and one 409, one event each; the final status is the winner's. Pinned in Task 8.
3. **Deleting the contact an appointment was booked with** — bdm-002's delete still succeeds; the appointment keeps the snapshot with `contact_id` null, and its detail page still renders. Pinned in Tasks 5 and 13.
4. **An appointment at 23:30 IST (18:00 UTC the same day) and one at 00:30 IST (19:00 UTC the previous day)** — each appears under its IST date in the `date_from`/`date_to` filter, and in the form round-trip. Pinned in Tasks 4 and 10.
5. **The organization is reassigned to another BDM after booking** — the appointment stays with (and is writable only by) its original BDM; the new assignee cannot see it via `GET /bdm/appointments/{id}` (404) but can book their own. Pinned in Task 7.

---

### Task 0: Decision record and backlog notes (docs only)

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md` (append after the last `DEC-SCOPE-*` entry)
- Modify: `docs/delivery/BDM_CRM_BACKLOG.md` (bdm-006 status line)
- Modify: `docs/superpowers/specs/2026-10-03-bdm-002-organization-crm-design.md` (AC5b note: 409 → 422)

- [ ] **Step 1: Confirm the next free decision number**

Run: `git fetch origin && git show origin/main:docs/decisions/PRODUCT_DECISION_REGISTER.md | grep -o "DEC-SCOPE-0[0-9][0-9]" | sort -u | tail -1`
Expected: `DEC-SCOPE-062` → use `DEC-SCOPE-063`. If higher, use the next one and substitute it everywhere below.

- [ ] **Step 2: Append the decision**

```markdown
### DEC-SCOPE-063 — BDM appointments (`bdm-006`)

**Question:** how do BDMs book and manage appointments, which transitions are allowed, and what does Completed require before bdm-007 exists?

**Evidence:** `EVID-016` §2 (lines 27–93), Agent §C (615–653), School §C (873–895), College §C (1110–1134), §8 outcomes (250–275) (`ORIGINAL_REQUIREMENT`); `DEC-SCOPE-055` D3, D11 (Q-02), D16 (Q-07), D20 (Q-11), D26 (Q-17), D29 (Q-20); bdm-002 `DEC-SCOPE-060` AC5b; bdm-006 impact analysis 2026-10-03 (graphify-led).

**Resolution:** owner, in-session 2026-10-03 (`EXPLICIT_APPROVAL`, via questions; design approved section by section):
- **A1** Completed takes a minimal outcome (validated per BDM type) and an optional next follow-up date on the appointment; bdm-007 adds the meeting report on top.
- **A2** Transitions: scheduled / confirmed / rescheduled → confirmed (not from confirmed), rescheduled, cancelled, no show, completed; completed, cancelled and no show are terminal; completed and no show only after the start time; cancel and no show need a reason; reschedule keeps the old time in history.
- **A3** Only the organization's assigned BDM books and manages; managers and super_admin read only.
- **A4** An archived organization blocks new appointments (422); existing ones stay manageable.
- **A5** Deleting an organization contact keeps the appointment's contact snapshot (`contact_id` → NULL). Consequence: a contact delete no longer erases every copy of that person's details.
- **A6** Overlap for the same BDM warns with a 409 the BDM can confirm past.
- **A7** Create and reschedule require a future start time.
- **A8** Outcomes: Agent §C list for agent BDMs; §8 list for school and college BDMs.
- Defaults approved with the design: type list = §2 common ∪ module list (deduplicated by key); contact picked from the organization's contacts; ownership fixed on organization reassignment (bdm-025 moves portfolios); location, purpose, remarks optional.

**Open:** retention / erasure policy for BDM data — `NEEDS_CONFIRMATION` (as bdm-001/002).

**Spec:** `docs/superpowers/specs/2026-10-03-bdm-006-appointments-design.md`.
```

- [ ] **Step 3: Backlog status line** — under `### bdm-006 — Appointments …`, insert after the heading:

```markdown
> **Status (2026-10-03):** in progress on `feature/bdm-006-appointments` (`DEC-SCOPE-063`, migration `0068_bdm_appointments`). Spec: `docs/superpowers/specs/2026-10-03-bdm-006-appointments-design.md`; plan: `docs/superpowers/plans/2026-10-03-bdm-006-appointments.md`. AC5 is satisfied by a minimal outcome on Complete (A1); "Next Follow-up" is captured there.
```

- [ ] **Step 4: bdm-002 spec AC5b wording** — in `2026-10-03-bdm-002-organization-crm-design.md` line ~197, replace `refuse an archived organization (409)` with `refuse an archived organization (422 — bdm-006 A4, DEC-SCOPE-063)`.

- [ ] **Step 5: Commit**

```bash
git add docs/decisions/PRODUCT_DECISION_REGISTER.md docs/delivery/BDM_CRM_BACKLOG.md docs/superpowers/specs/2026-10-03-bdm-002-organization-crm-design.md
git commit -m "docs(bdm-006): DEC-SCOPE-063 and backlog status" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 1: Models, catalogues and migration `0068_bdm_appointments`

**Files:**
- Modify: `apps/api/app/models.py` (after `class BdmOrganizationContact`)
- Create: `apps/api/alembic/versions/0068_bdm_appointments.py`
- Test: `apps/api/tests/test_bdm_006_migration.py`

**Interfaces:**
- Produces (models.py): `BDM_APPOINTMENT_STATUSES`, `BDM_APPOINTMENT_OPEN`, `BDM_APPOINTMENT_COMMON_TYPES`, `BDM_APPOINTMENT_MODULE_TYPES: dict[str, tuple[str, ...]]`, `BDM_APPOINTMENT_ALL_TYPES`, `BDM_APPOINTMENT_COMMON_OUTCOMES`, `BDM_APPOINTMENT_AGENT_OUTCOMES`, `BDM_APPOINTMENT_ALL_OUTCOMES`, `BDM_APPOINTMENT_CODE_SEQ`, classes `BdmAppointment`, `BdmAppointmentEvent`.

- [ ] **Step 1: Write the failing migration test**

```python
"""bdm-006 -- migration 0068_bdm_appointments (spec §4). Round trip and the downgrade refusal run in a throwaway database (the
bdm-001/002 pattern); a downgrade never runs against the shared test database."""

import asyncio
import importlib.util
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import command
from app.core.config import settings

API_ROOT = Path(__file__).resolve().parents[1]
VERSIONS = API_ROOT / "alembic" / "versions"
_spec = importlib.util.spec_from_file_location("_bdm_006_migration_0068", VERSIONS / "0068_bdm_appointments.py")
_migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_migration)

BASE = "0067_audit_entity_index"
HEAD = "0068_bdm_appointments"
ORGS = "SELECT id, code FROM bdm_organizations ORDER BY id"


def test_migration_chains_after_0067_and_is_the_single_head():
    assert _migration.revision == HEAD
    assert _migration.down_revision == BASE
    parents = {}
    for file in VERSIONS.glob("*.py"):
        lines = file.read_text(encoding="utf-8").splitlines()
        rev = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("revision =")), None)
        if rev:
            parents[rev] = next((line.split("=", 1)[1].strip().strip("\"'") for line in lines if line.startswith("down_revision =")), None)
    assert len(set(parents) - set(parents.values())) == 1


def test_models_match_the_migration():
    from app.models import BdmAppointment, BdmAppointmentEvent

    appt = BdmAppointment.__table__
    assert {c.name for c in appt.columns} == {
        "id", "code", "bdm_user_id", "organization_id", "contact_id", "contact_name", "contact_designation", "contact_phone",
        "contact_email", "starts_at", "duration_minutes", "appointment_type", "location", "purpose", "remarks", "status", "outcome",
        "next_follow_up_on", "expected_leads", "expected_revenue", "created_at", "updated_at",
    }
    for required in ("code", "bdm_user_id", "organization_id", "contact_name", "starts_at", "duration_minutes", "appointment_type", "status"):
        assert not appt.c[required].nullable, required
    assert appt.c.contact_id.nullable
    assert next(iter(appt.c.contact_id.foreign_keys)).ondelete == "SET NULL"
    names = {i.name for i in appt.indexes} | {c.name for c in appt.constraints}
    assert {
        "uq_bdm_appointments_code", "ck_bdm_appointments_status", "ck_bdm_appointments_type", "ck_bdm_appointments_outcome",
        "ck_bdm_appointments_outcome_completed", "ck_bdm_appointments_follow_up", "ck_bdm_appointments_duration",
        "ck_bdm_appointments_expected_leads", "ck_bdm_appointments_expected_revenue", "ix_bdm_appointments_bdm_starts",
        "ix_bdm_appointments_org_starts", "ix_bdm_appointments_contact",
    } <= names
    event = BdmAppointmentEvent.__table__
    assert {c.name for c in event.columns} == {
        "id", "appointment_id", "actor_user_id", "from_status", "to_status", "old_starts_at", "new_starts_at", "reason", "position", "created_at",
    }
    names = {i.name for i in event.indexes} | {c.name for c in event.constraints}
    assert {"ck_bdm_appointment_events_to_status", "ix_bdm_appointment_events_appointment"} <= names


def test_catalogues_match_the_source():
    from app.models import (
        BDM_APPOINTMENT_AGENT_OUTCOMES, BDM_APPOINTMENT_ALL_TYPES, BDM_APPOINTMENT_COMMON_OUTCOMES, BDM_APPOINTMENT_COMMON_TYPES,
        BDM_APPOINTMENT_MODULE_TYPES,
    )

    assert len(BDM_APPOINTMENT_COMMON_TYPES) == 8
    assert {k: len(v) for k, v in BDM_APPOINTMENT_MODULE_TYPES.items()} == {"agent": 9, "school": 11, "college": 12}
    assert len(BDM_APPOINTMENT_COMMON_OUTCOMES) == 9 and len(BDM_APPOINTMENT_AGENT_OUTCOMES) == 8
    assert len(BDM_APPOINTMENT_ALL_TYPES) == len(set(BDM_APPOINTMENT_ALL_TYPES))
    assert all(max(len(k) for k in group) <= 40 for group in (BDM_APPOINTMENT_ALL_TYPES, BDM_APPOINTMENT_COMMON_OUTCOMES))


@pytest.mark.asyncio
async def test_tables_and_sequence_exist_in_the_shared_database(db_session):
    conn = await db_session.connection()
    assert (await conn.execute(sa.text("SELECT 1 FROM pg_class WHERE relkind = 'S' AND relname = 'bdm_appointment_code_seq'"))).first()
    assert (await conn.execute(sa.text("SELECT 1 FROM pg_class WHERE relname = 'bdm_appointment_events'"))).first()


def _sql(url: str, sql: str, params: dict | None = None, *, autocommit: bool = False):
    async def _inner():
        engine = create_async_engine(url, isolation_level="AUTOCOMMIT") if autocommit else create_async_engine(url)
        try:
            async with engine.begin() as conn:
                result = await conn.execute(sa.text(sql), params or {})
                return result.fetchall() if result.returns_rows else None
        finally:
            await engine.dispose()

    return asyncio.run(_inner())


@pytest.fixture
def isolated_db():
    """A fresh database at 0067 with one bdm user, one organization and one contact."""
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    original = settings.database_url
    name = f"bdm006_migration_{uuid.uuid4().hex[:8]}"
    url = make_url(original).set(database=name).render_as_string(hide_password=False)
    _sql(original, f'CREATE DATABASE "{name}"', autocommit=True)
    try:
        settings.database_url = url
        command.upgrade(cfg, BASE)
        user, org, contact = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        _sql(url, "INSERT INTO users (id, email, password_hash, full_name, role, division, active, email_verified, locale, profile) VALUES (:id, :email, 'x', 'bdm', 'bdm', 'it', true, true, 'en-GB', '{}')", {"id": user, "email": f"bdm-{name}@example.local"})
        _sql(url, "INSERT INTO bdm_organizations (id, code, org_type, bdm_type, name, name_key, city, city_key, assigned_bdm_user_id, created_by_user_id) VALUES (:id, 'ORG-9', 'college', 'college', 'A', 'a', 'K', 'k', :u, :u)", {"id": org, "u": user})
        _sql(url, "INSERT INTO bdm_organization_contacts (id, organization_id, name, is_primary) VALUES (:id, :org, 'C', true)", {"id": contact, "org": org})
        yield {"cfg": cfg, "url": url, "user": user, "org": org, "contact": contact}
    finally:
        settings.database_url = original
        _sql(original, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', autocommit=True)


def test_round_trip_keeps_organizations_and_drops_the_sequence(isolated_db):
    cfg, url = isolated_db["cfg"], isolated_db["url"]
    before = _sql(url, ORGS)
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    assert _sql(url, ORGS) == before
    assert not _sql(url, "SELECT 1 FROM pg_class WHERE relname = 'bdm_appointment_code_seq'")
    command.upgrade(cfg, HEAD)
    assert _sql(url, ORGS) == before


INSERT = (
    "INSERT INTO bdm_appointments (id, code, bdm_user_id, organization_id, contact_id, contact_name, starts_at, appointment_type, status, outcome) "
    "VALUES (:id, :code, :u, :org, :c, 'C', now(), :type, :status, :outcome)"
)


def test_constraints_hold_and_downgrade_refuses_while_appointments_exist(isolated_db):
    cfg, url, user, org, contact = (isolated_db[k] for k in ("cfg", "url", "user", "org", "contact"))
    # 0001 builds a fresh database from the current models, so the tables already exist at BASE; drop them and let 0068's own DDL
    # create them, so the constraints below are the migration's, not create_all's.
    command.upgrade(cfg, HEAD)
    command.downgrade(cfg, BASE)
    command.upgrade(cfg, HEAD)
    row = {"u": user, "org": org, "c": contact, "type": "college_meeting", "status": "scheduled", "outcome": None}
    with pytest.raises(Exception, match="ck_bdm_appointments_type"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-1", "type": "lunch"})
    with pytest.raises(Exception, match="ck_bdm_appointments_outcome_completed"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-2", "status": "completed"})
    with pytest.raises(Exception, match="ck_bdm_appointments_outcome_completed"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-3", "outcome": "interested"})
    appt = uuid.uuid4()
    _sql(url, INSERT, {**row, "id": appt, "code": "APT-4"})
    with pytest.raises(Exception, match="uq_bdm_appointments_code"):
        _sql(url, INSERT, {**row, "id": uuid.uuid4(), "code": "APT-4"})
    # A5: deleting the contact nulls the link and keeps the snapshot.
    _sql(url, "DELETE FROM bdm_organization_contacts WHERE id = :c", {"c": contact})
    assert _sql(url, "SELECT contact_id, contact_name FROM bdm_appointments WHERE id = :id", {"id": appt}) == [(None, "C")]
    with pytest.raises(Exception, match="appointments exist"):
        command.downgrade(cfg, BASE)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `API_TEST tests/test_bdm_006_migration.py`
Expected: FAIL — `FileNotFoundError` for `0068_bdm_appointments.py` (module load at import).

- [ ] **Step 3: Add the catalogues and models** — in `models.py`, after `class BdmOrganizationContact`:

```python
# bdm-006 (DEC-SCOPE-063, spec §4.1): appointment catalogues. Stable keys; the CHECKs accept every key, the service validates each value
# against the owner's bdm_type (the database cannot see it).
BDM_APPOINTMENT_STATUSES = ("scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show")
BDM_APPOINTMENT_OPEN = ("scheduled", "confirmed", "rescheduled")
BDM_APPOINTMENT_COMMON_TYPES = (
    "college_meeting", "agent_meeting", "school_meeting", "mou_discussion", "student_institution_meeting", "seminar_workshop",
    "corporate_meeting", "other",
)
BDM_APPOINTMENT_MODULE_TYPES = {
    "agent": (
        "agent_meeting", "new_agent_presentation", "product_training", "agreement_discussion", "performance_review", "agent_onboarding",
        "agent_visit", "commission_discussion", "business_review",
    ),
    "school": (
        "principal_meeting", "management_meeting", "career_guidance_presentation", "psychometric_presentation",
        "profile_building_presentation", "parent_orientation", "teacher_orientation", "seminar", "workshop", "mou_discussion",
        "renewal_meeting",
    ),
    "college": (
        "principal_meeting", "hod_meeting", "placement_cell_meeting", "course_promotion", "it_training_presentation", "student_seminar",
        "workshop", "internship_discussion", "placement_discussion", "mou_discussion", "corporate_connect", "faculty_meeting",
    ),
}
BDM_APPOINTMENT_ALL_TYPES = tuple(dict.fromkeys(BDM_APPOINTMENT_COMMON_TYPES + sum(BDM_APPOINTMENT_MODULE_TYPES.values(), ())))
BDM_APPOINTMENT_COMMON_OUTCOMES = (
    "interested", "mou_discussion_required", "student_leads_expected", "course_promotion_interested", "follow_up_required",
    "commercial_discussion", "not_interested", "reschedule", "other",
)
BDM_APPOINTMENT_AGENT_OUTCOMES = (
    "interested", "agreement_required", "product_training_required", "follow_up", "documents_required", "onboarding_required",
    "active_business_expected", "not_interested",
)
BDM_APPOINTMENT_ALL_OUTCOMES = tuple(dict.fromkeys(BDM_APPOINTMENT_COMMON_OUTCOMES + BDM_APPOINTMENT_AGENT_OUTCOMES))
# On the metadata so 0001's create_all builds it for a fresh database; 0068 creates it IF NOT EXISTS.
BDM_APPOINTMENT_CODE_SEQ = Sequence("bdm_appointment_code_seq", metadata=Base.metadata)


class BdmAppointment(Base, TimestampMixin):
    """bdm-006 (DEC-SCOPE-063): a BDM's meeting at an organization (§2). The contact is copied at booking (A5: the copy outlives a contact
    delete). Never deleted: cancelled instead. Not the legacy `Appointment` (overseas counselling slots)."""

    __tablename__ = "bdm_appointments"
    __table_args__ = (
        UniqueConstraint("code", name="uq_bdm_appointments_code"),
        CheckConstraint(_in_list("status", BDM_APPOINTMENT_STATUSES), name="ck_bdm_appointments_status"),
        CheckConstraint(_in_list("appointment_type", BDM_APPOINTMENT_ALL_TYPES), name="ck_bdm_appointments_type"),
        CheckConstraint(f"outcome IS NULL OR {_in_list('outcome', BDM_APPOINTMENT_ALL_OUTCOMES)}", name="ck_bdm_appointments_outcome"),
        CheckConstraint("(status = 'completed') = (outcome IS NOT NULL)", name="ck_bdm_appointments_outcome_completed"),
        CheckConstraint("next_follow_up_on IS NULL OR status = 'completed'", name="ck_bdm_appointments_follow_up"),
        CheckConstraint("duration_minutes BETWEEN 15 AND 720", name="ck_bdm_appointments_duration"),
        CheckConstraint("expected_leads IS NULL OR expected_leads >= 0", name="ck_bdm_appointments_expected_leads"),
        CheckConstraint("expected_revenue IS NULL OR expected_revenue >= 0", name="ck_bdm_appointments_expected_revenue"),
        Index("ix_bdm_appointments_bdm_starts", "bdm_user_id", "starts_at"),
        Index("ix_bdm_appointments_org_starts", "organization_id", "starts_at"),
        Index("ix_bdm_appointments_contact", "contact_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(20))
    bdm_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organizations.id", ondelete="RESTRICT"))
    contact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True)
    contact_name: Mapped[str] = mapped_column(String(200))
    contact_designation: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, server_default=text("60"))
    appointment_type: Mapped[str] = mapped_column(String(40))
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", server_default=text("'scheduled'"))
    outcome: Mapped[str | None] = mapped_column(String(40), nullable=True)
    next_follow_up_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_leads: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_revenue: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)


class BdmAppointmentEvent(Base):
    """bdm-006: one row per status transition (and creation: from_status NULL). Append-only. `position` orders rows created in one
    transaction."""

    __tablename__ = "bdm_appointment_events"
    __table_args__ = (
        CheckConstraint(_in_list("to_status", BDM_APPOINTMENT_STATUSES), name="ck_bdm_appointment_events_to_status"),
        Index("ix_bdm_appointment_events_appointment", "appointment_id", "position"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    appointment_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bdm_appointments.id", ondelete="RESTRICT"))
    actor_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"))
    from_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    old_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    new_starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    position: Mapped[int] = mapped_column(BigInteger, Identity(always=False))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Check that `text`, `func`, `Uuid`, `String`, `UniqueConstraint` are already imported at the top of `models.py` (they are used by `BdmOrganization`); add any that are missing to the existing import lists.

- [ ] **Step 4: Write the migration** — `apps/api/alembic/versions/0068_bdm_appointments.py`:

```python
"""bdm-006 -- bdm_appointments + bdm_appointment_events + bdm_appointment_code_seq.

Revision ID: 0068_bdm_appointments
Revises: 0067_audit_entity_index

docs/superpowers/specs/2026-10-03-bdm-006-appointments-design.md §4 (DEC-SCOPE-063). Adds two tables and one sequence; no existing
row is read or written. 0001 builds a fresh database from the current models (which carry both tables and the sequence), so creation
is guarded (0061/0066's idiom) and the sequence is created IF NOT EXISTS. downgrade() refuses while appointments exist: they are the
only record of each meeting and its history.

If another migration reaches `main` first, re-chain this revision after it (rename the file and revision, update down_revision) as
0066 did; a database stamped at the old id is re-stamped with `alembic stamp --purge <previous head>` then `upgrade head`.
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models import BDM_APPOINTMENT_ALL_OUTCOMES, BDM_APPOINTMENT_ALL_TYPES, BDM_APPOINTMENT_STATUSES

revision = "0068_bdm_appointments"
down_revision = "0067_audit_entity_index"
branch_labels = None
depends_on = None

APPTS = "bdm_appointments"
EVENTS = "bdm_appointment_events"
SEQ = "bdm_appointment_code_seq"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid(name: str, *args, nullable: bool = False, **kwargs) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), *args, nullable=nullable, **kwargs)


def upgrade() -> None:
    op.execute(f"CREATE SEQUENCE IF NOT EXISTS {SEQ}")
    if not op.get_context().as_sql and APPTS in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        APPTS,
        _uuid("id", primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        _uuid("bdm_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        _uuid("organization_id", sa.ForeignKey("bdm_organizations.id", ondelete="RESTRICT")),
        _uuid("contact_id", sa.ForeignKey("bdm_organization_contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=False),
        sa.Column("contact_designation", sa.String(120), nullable=True),
        sa.Column("contact_phone", sa.String(30), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), server_default=sa.text("60"), nullable=False),
        sa.Column("appointment_type", sa.String(40), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("purpose", sa.String(1000), nullable=True),
        sa.Column("remarks", sa.String(2000), nullable=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'scheduled'"), nullable=False),
        sa.Column("outcome", sa.String(40), nullable=True),
        sa.Column("next_follow_up_on", sa.Date(), nullable=True),
        sa.Column("expected_leads", sa.Integer(), nullable=True),
        sa.Column("expected_revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("code", name="uq_bdm_appointments_code"),
        sa.CheckConstraint(_in("status", BDM_APPOINTMENT_STATUSES), name="ck_bdm_appointments_status"),
        sa.CheckConstraint(_in("appointment_type", BDM_APPOINTMENT_ALL_TYPES), name="ck_bdm_appointments_type"),
        sa.CheckConstraint(f"outcome IS NULL OR {_in('outcome', BDM_APPOINTMENT_ALL_OUTCOMES)}", name="ck_bdm_appointments_outcome"),
        sa.CheckConstraint("(status = 'completed') = (outcome IS NOT NULL)", name="ck_bdm_appointments_outcome_completed"),
        sa.CheckConstraint("next_follow_up_on IS NULL OR status = 'completed'", name="ck_bdm_appointments_follow_up"),
        sa.CheckConstraint("duration_minutes BETWEEN 15 AND 720", name="ck_bdm_appointments_duration"),
        sa.CheckConstraint("expected_leads IS NULL OR expected_leads >= 0", name="ck_bdm_appointments_expected_leads"),
        sa.CheckConstraint("expected_revenue IS NULL OR expected_revenue >= 0", name="ck_bdm_appointments_expected_revenue"),
    )
    op.create_index("ix_bdm_appointments_bdm_starts", APPTS, ["bdm_user_id", "starts_at"])
    op.create_index("ix_bdm_appointments_org_starts", APPTS, ["organization_id", "starts_at"])
    op.create_index("ix_bdm_appointments_contact", APPTS, ["contact_id"])
    op.create_table(
        EVENTS,
        _uuid("id", primary_key=True),
        _uuid("appointment_id", sa.ForeignKey(f"{APPTS}.id", ondelete="RESTRICT")),
        _uuid("actor_user_id", sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("old_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("position", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(_in("to_status", BDM_APPOINTMENT_STATUSES), name="ck_bdm_appointment_events_to_status"),
    )
    op.create_index("ix_bdm_appointment_events_appointment", EVENTS, ["appointment_id", "position"])


def downgrade() -> None:
    if not op.get_context().as_sql and op.get_bind().execute(sa.text(f"SELECT 1 FROM {APPTS} LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade 0068_bdm_appointments: BDM appointments exist. Remove them deliberately first.")
    op.drop_table(EVENTS)
    op.drop_table(APPTS)
    op.execute(f"DROP SEQUENCE IF EXISTS {SEQ}")
```

Note: importing the catalogues from `app.models` keeps the CHECK lists identical to the model; if an existing migration in `alembic/versions` already imports from `app.models`, follow it; if none does, inline the three tuples as string constants (as 0066 inlined `ORG_TYPES`) and add a test assertion that they equal the model tuples. Check with `grep -l "from app.models" apps/api/alembic/versions/*.py` and choose before writing.

- [ ] **Step 5: Run the test to verify it passes**

Run: `API_TEST tests/test_bdm_006_migration.py tests/test_bdm_002_migration.py tests/test_agn_017_migration.py`
Expected: all PASS (the two older files' single-head assertions still hold).

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0068_bdm_appointments.py apps/api/tests/test_bdm_006_migration.py
git commit -m "feat(bdm-006): appointment tables, catalogues and migration 0068" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Schemas

**Files:**
- Modify: `apps/api/app/schemas.py` (append after `class BdmOrganizationEnvelope`; extend the `from app.models import` line)
- Test: `apps/api/tests/test_bdm_006_schemas.py`

**Interfaces:**
- Consumes: the Task 1 catalogues.
- Produces: `BdmAppointmentType`, `BdmAppointmentOutcome`, `BdmAppointmentStatus` (Literals); input models `BdmAppointmentCreate`, `BdmAppointmentUpdate`, `BdmAppointmentReschedule`, `BdmAppointmentReason`, `BdmAppointmentComplete`; output models `BdmAppointmentPermissions`, `BdmAppointmentOrgRef`, `BdmAppointmentRow`, `BdmAppointmentEventOut`, `BdmAppointmentOut`, `BdmAppointmentPage`, `BdmAppointmentEnvelope`; `BDM_APPOINTMENT_OPTIONAL_FIELDS` (the optional editable field names, used for audit "fields").

- [ ] **Step 1: Write the failing tests**

```python
"""bdm-006 -- request validation (spec §5.1, §12.1 R-A7, §12.3 input validation)."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas import BdmAppointmentComplete, BdmAppointmentCreate, BdmAppointmentReason, BdmAppointmentReschedule, BdmAppointmentUpdate


def base(**over) -> dict:
    payload = {
        "organization_id": str(uuid.uuid4()), "contact_id": str(uuid.uuid4()), "starts_at": "2030-01-07T10:00:00+05:30",
        "appointment_type": "college_meeting",
    }
    payload.update(over)
    return payload


def test_minimal_create_defaults_and_minute_normalization():
    model = BdmAppointmentCreate.model_validate(base(starts_at="2030-01-07T10:00:42.5+05:30"))
    assert model.duration_minutes == 60 and model.confirm_overlap is False
    assert model.starts_at == datetime(2030, 1, 7, 4, 30, tzinfo=UTC)
    assert model.location is None and model.expected_revenue is None


@pytest.mark.parametrize(
    "over",
    [
        {"starts_at": "2030-01-07T10:00:00"},  # naive
        {"appointment_type": "lunch"},
        {"duration_minutes": 10},
        {"duration_minutes": 721},
        {"duration_minutes": "60"},
        {"expected_leads": -1},
        {"expected_leads": 1.5},
        {"expected_revenue": -1},
        {"expected_revenue": "1.234"},
        {"location": "x" * 256},
        {"purpose": "bad\x00text"},
        {"code": "APT-000001"},
        {"status": "confirmed"},
        {"bdm_user_id": str(uuid.uuid4())},
        {"contact_name": "Injected"},
        {"outcome": "interested"},
    ],
)
def test_create_rejects(over):
    with pytest.raises(ValidationError):
        BdmAppointmentCreate.model_validate(base(**over))


def test_blank_optional_text_becomes_none_and_is_stripped():
    model = BdmAppointmentCreate.model_validate(base(location="   ", purpose="  Demo  ", expected_revenue="1500.5"))
    assert model.location is None and model.purpose == "Demo" and model.expected_revenue == Decimal("1500.50")


def test_update_forbids_time_status_and_org_and_rejects_null_on_required():
    for bad in ({"starts_at": "2030-01-07T10:00:00+05:30"}, {"status": "cancelled"}, {"organization_id": str(uuid.uuid4())}, {"contact_id": None}, {"duration_minutes": None}):
        with pytest.raises(ValidationError):
            BdmAppointmentUpdate.model_validate(bad)
    assert BdmAppointmentUpdate.model_validate({}).model_dump(exclude_unset=True) == {}


def test_reason_is_required_trimmed_and_bounded():
    for bad in ({}, {"reason": ""}, {"reason": "   "}, {"reason": "x" * 501}, {"reason": "a\x07b"}):
        with pytest.raises(ValidationError):
            BdmAppointmentReason.model_validate(bad)
    assert BdmAppointmentReason.model_validate({"reason": "  Principal on leave "}).reason == "Principal on leave"


def test_reschedule_and_complete_shapes():
    r = BdmAppointmentReschedule.model_validate({"starts_at": "2030-01-08T11:00:00+05:30"})
    assert r.duration_minutes is None and r.reason is None and r.confirm_overlap is False
    with pytest.raises(ValidationError):
        BdmAppointmentComplete.model_validate({"outcome": "great"})
    c = BdmAppointmentComplete.model_validate({"outcome": "agreement_required", "next_follow_up_on": "2030-01-10"})
    assert c.next_follow_up_on.isoformat() == "2030-01-10"
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST tests/test_bdm_006_schemas.py`
Expected: FAIL — `ImportError: cannot import name 'BdmAppointmentComplete'`.

- [ ] **Step 3: Implement** — extend the models import to `from app.models import BDM_APPOINTMENT_ALL_OUTCOMES, BDM_APPOINTMENT_ALL_TYPES, BDM_APPOINTMENT_STATUSES, GENDERS`, then append:

```python
# --- bdm-006 (DEC-SCOPE-063, spec §5.1): appointments ----------------------------------------------------------------------------
BdmAppointmentType = Literal[BDM_APPOINTMENT_ALL_TYPES]
BdmAppointmentOutcome = Literal[BDM_APPOINTMENT_ALL_OUTCOMES]
BdmAppointmentStatus = Literal[BDM_APPOINTMENT_STATUSES]
BDM_APPOINTMENT_LABELS = {"location": "Location", "purpose": "Purpose", "remarks": "Remarks", "reason": "Reason"}
BDM_APPOINTMENT_OPTIONAL_FIELDS = ("location", "purpose", "remarks", "expected_leads", "expected_revenue")


def _bdm_appt_text(value: str | None, info: ValidationInfo) -> str | None:
    """bdm-001's text rule: no control characters; blank -> None."""
    if value is not None and _BDM_CONTROL.search(value):
        raise ValueError(f"{BDM_APPOINTMENT_LABELS.get(info.field_name, info.field_name)} contains invalid characters")
    return value or None


def _bdm_appt_optional(max_length: int):
    return Annotated[Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)] | None, AfterValidator(_bdm_appt_text)]


def _bdm_appt_minute(value: datetime) -> datetime:
    """R-A7: compare what the UI shows -- seconds and microseconds are dropped; stored in UTC."""
    return value.replace(second=0, microsecond=0).astimezone(UTC)


def _bdm_appt_reason(value: str) -> str:
    if _BDM_CONTROL.search(value):
        raise ValueError("Reason contains invalid characters")
    if not value:
        raise ValueError("Reason is required")
    return value


BdmApptStart = Annotated[AwareDatetime, AfterValidator(_bdm_appt_minute)]
BdmApptDuration = Annotated[StrictInt, Field(ge=15, le=720)]
BdmApptLeads = Annotated[StrictInt, Field(ge=0, le=1_000_000)] | None
BdmApptRevenue = Annotated[Decimal, Field(ge=0, le=Decimal("9999999999.99"), max_digits=12, decimal_places=2)] | None
BdmApptLocation = _bdm_appt_optional(255)
BdmApptPurpose = _bdm_appt_optional(1000)
BdmApptRemarks = _bdm_appt_optional(2000)
BdmApptReason = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_bdm_appt_reason)]


class BdmAppointmentCreate(BaseModel):
    """spec §5.1: server-owned fields (code, owner, status, outcome, the contact snapshot) are unknown fields here (§12.3)."""

    model_config = ConfigDict(extra="forbid")
    organization_id: UUID
    contact_id: UUID
    starts_at: BdmApptStart
    duration_minutes: BdmApptDuration = 60
    appointment_type: BdmAppointmentType
    location: BdmApptLocation = None
    purpose: BdmApptPurpose = None
    remarks: BdmApptRemarks = None
    expected_leads: BdmApptLeads = None
    expected_revenue: BdmApptRevenue = None
    confirm_overlap: StrictBool = False


class BdmAppointmentUpdate(BaseModel):
    """Omitted = unchanged; a sent null on `contact_id` / `duration_minutes` / `appointment_type` fails the non-nullable type. The time
    changes only through reschedule and the status only through the actions."""

    model_config = ConfigDict(extra="forbid")
    contact_id: UUID = None
    duration_minutes: BdmApptDuration = None
    appointment_type: BdmAppointmentType = None
    location: BdmApptLocation = None
    purpose: BdmApptPurpose = None
    remarks: BdmApptRemarks = None
    expected_leads: BdmApptLeads = None
    expected_revenue: BdmApptRevenue = None
    confirm_overlap: StrictBool = False


class BdmAppointmentReschedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    starts_at: BdmApptStart
    duration_minutes: BdmApptDuration | None = None
    reason: _bdm_appt_optional(500) = None
    confirm_overlap: StrictBool = False


class BdmAppointmentReason(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: BdmApptReason


class BdmAppointmentComplete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: BdmAppointmentOutcome
    next_follow_up_on: date | None = None


class BdmAppointmentPermissions(BaseModel):
    can_edit: bool
    can_confirm: bool
    can_reschedule: bool
    can_cancel: bool
    can_no_show: bool
    can_complete: bool


class BdmAppointmentOrgRef(BaseModel):
    id: UUID
    code: str
    name: str
    archived: bool


class BdmAppointmentRow(BaseModel):
    id: UUID
    code: str
    starts_at: datetime
    duration_minutes: int
    appointment_type: str
    status: str
    organization: BdmAppointmentOrgRef
    contact_name: str
    bdm: BdmOrgPerson


class BdmAppointmentEventOut(BaseModel):
    from_status: str | None
    to_status: str
    old_starts_at: datetime | None
    new_starts_at: datetime | None
    reason: str | None
    actor_name: str
    created_at: datetime


class BdmAppointmentOut(BdmAppointmentRow):
    contact_id: UUID | None
    contact_designation: str | None
    contact_phone: str | None
    contact_email: str | None
    location: str | None
    purpose: str | None
    remarks: str | None
    outcome: str | None
    next_follow_up_on: date | None
    expected_leads: int | None
    expected_revenue: Decimal | None
    events: list[BdmAppointmentEventOut]
    permissions: BdmAppointmentPermissions
    created_at: datetime
    updated_at: datetime


class BdmAppointmentPage(BaseModel):
    items: list[BdmAppointmentRow]
    total: int
    limit: int
    offset: int


class BdmAppointmentEnvelope(BaseModel):
    appointment: BdmAppointmentOut
```

- [ ] **Step 4: Run to verify pass**

Run: `API_TEST tests/test_bdm_006_schemas.py tests/test_bdm_002_schemas.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas.py apps/api/tests/test_bdm_006_schemas.py
git commit -m "feat(bdm-006): appointment request and response schemas" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Service — catalogues, transitions, scope, overlap, output

**Files:**
- Create: `apps/api/app/services/bdm_appointments.py`
- Test: `apps/api/tests/test_bdm_006_service.py`

**Interfaces:**
- Consumes: Task 1 models; `app.services.bdm.bdm_context(db, user) -> BdmProfile`.
- Produces (all used by Tasks 4–8):
  - `TRANSITIONS: dict[str, frozenset[str]]`, `IST`, `NOT_FOUND = "Appointment not found"`
  - `appointment_types(bdm_type: str) -> tuple[str, ...]`, `appointment_outcomes(bdm_type: str) -> tuple[str, ...]`
  - `async next_code(db) -> str`, `format_code(n: int) -> str`, `async db_now(db) -> datetime`, `today_ist(now: datetime) -> date`, `ist_bounds(date_from: date | None, date_to: date | None) -> list`
  - `async caller_filters(db, user) -> list`, `async load_scoped(db, user, appt_id, *, lock=False) -> BdmAppointment`
  - `require_owner(user, appt, action: str) -> None`, `require_transition(appt, to_status: str) -> None`, `require_open(appt) -> None` (409 unless scheduled / confirmed / rescheduled), `require_future(starts_at, now) -> None`, `require_started(appt, now, action: "complete" | "no_show") -> None`
  - `snapshot(contact: BdmOrganizationContact) -> dict`
  - `async find_overlaps(db, bdm_user_id, starts_at, duration, exclude_id=None) -> tuple[list[dict], int]`, `overlap_conflict(matches, total) -> HTTPException`
  - `record(db, appt, actor, from_status, to_status, *, old_starts_at=None, new_starts_at=None, reason=None) -> None`
  - `permissions(user, appt, now) -> dict[str, bool]`
  - `row_out(appt, org, owner) -> dict`, `async appointment_out(db, user, appt, *, refresh=True) -> dict`
  - `meeting_columns() -> tuple[Label, Label]` (labels `last_meeting_at`, `next_meeting_at`, correlated to `BdmOrganization`)
  - `audit(db, user, action, appt_id, metadata=None) -> None`, `log(event, user, appt_id, **extra) -> None`

- [ ] **Step 1: Write the failing pure tests**

```python
"""bdm-006 -- service rules that need no database (spec §4.1, §5.2, §5.4)."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models import BDM_APPOINTMENT_STATUSES
from app.services import bdm_appointments as svc

NOW = datetime(2030, 1, 7, 6, 0, tzinfo=UTC)


def appt(status="scheduled", starts_at=NOW + timedelta(hours=1), owner=None):
    return SimpleNamespace(id=uuid4(), status=status, starts_at=starts_at, bdm_user_id=owner or uuid4())


def user(role="bdm", uid=None):
    return SimpleNamespace(id=uid or uuid4(), role=role)


def test_type_lists_include_common_and_module_without_duplicates():
    for bdm_type, module_count in (("agent", 9), ("school", 11), ("college", 12)):
        types = svc.appointment_types(bdm_type)
        assert len(types) == len(set(types))
        assert set(types) >= {"college_meeting", "seminar_workshop", "other", "mou_discussion"}
    assert len(svc.appointment_types("agent")) == 8 + 9 - 1  # agent_meeting is in both
    assert len(svc.appointment_types("school")) == 8 + 11 - 1  # mou_discussion
    assert len(svc.appointment_types("college")) == 8 + 12 - 1
    assert "principal_meeting" not in svc.appointment_types("agent") and "agent_visit" not in svc.appointment_types("college")


def test_outcome_lists_per_type():
    assert "agreement_required" in svc.appointment_outcomes("agent") and "course_promotion_interested" not in svc.appointment_outcomes("agent")
    assert svc.appointment_outcomes("school") == svc.appointment_outcomes("college")
    assert "agreement_required" not in svc.appointment_outcomes("college")


EXPECTED = {
    "scheduled": {"confirmed", "rescheduled", "cancelled", "no_show", "completed"},
    "confirmed": {"rescheduled", "cancelled", "no_show", "completed"},
    "rescheduled": {"confirmed", "rescheduled", "cancelled", "no_show", "completed"},
    "completed": set(), "cancelled": set(), "no_show": set(),
}


@pytest.mark.parametrize("src", BDM_APPOINTMENT_STATUSES)
@pytest.mark.parametrize("dst", BDM_APPOINTMENT_STATUSES)
def test_transition_matrix(src, dst):
    allowed = dst in EXPECTED[src]
    assert (dst in svc.TRANSITIONS[src]) is allowed
    if allowed:
        svc.require_transition(appt(src), dst)
    else:
        with pytest.raises(HTTPException) as exc:
            svc.require_transition(appt(src), dst)
        assert exc.value.status_code == 409


def test_future_and_started_rules():
    with pytest.raises(HTTPException) as exc:
        svc.require_future(NOW, NOW)
    assert exc.value.status_code == 422 and exc.value.detail == "Choose a time in the future"
    svc.require_future(NOW + timedelta(minutes=1), NOW)
    with pytest.raises(HTTPException) as exc:
        svc.require_started(appt(starts_at=NOW + timedelta(minutes=1)), NOW, "complete")
    assert exc.value.detail == "You can only complete an appointment after its start time"
    svc.require_started(appt(starts_at=NOW), NOW, "no_show")


def test_owner_rule():
    owner = user()
    svc.require_owner(owner, appt(owner=owner.id), "confirm")
    for other in (user(), user("bdm_manager"), user("super_admin")):
        with pytest.raises(HTTPException) as exc:
            svc.require_owner(other, appt(owner=owner.id), "confirm")
        assert exc.value.status_code == 403 and exc.value.detail == "Only the appointment's BDM can change it"


def test_permissions_by_role_and_state():
    owner = user()
    future, past = appt(owner=owner.id), appt(owner=owner.id, starts_at=NOW - timedelta(minutes=1))
    assert svc.permissions(owner, future, NOW) == {"can_edit": True, "can_confirm": True, "can_reschedule": True, "can_cancel": True, "can_no_show": False, "can_complete": False}
    assert svc.permissions(owner, past, NOW)["can_complete"] and svc.permissions(owner, past, NOW)["can_no_show"]
    assert svc.permissions(owner, appt("confirmed", owner=owner.id), NOW)["can_confirm"] is False
    assert not any(svc.permissions(owner, appt("cancelled", owner=owner.id), NOW).values())
    assert not any(svc.permissions(user("bdm_manager"), past, NOW).values())


def test_ist_helpers():
    assert svc.format_code(7) == "APT-000007" and svc.format_code(1234567) == "APT-1234567"
    assert svc.today_ist(datetime(2030, 1, 6, 19, 0, tzinfo=UTC)) == date(2030, 1, 7)  # 00:30 IST
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST tests/test_bdm_006_service.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.bdm_appointments'`.

- [ ] **Step 3: Implement the service**

```python
"""bdm-006 (DEC-SCOPE-063, spec §5.2): appointment scope, transitions, catalogues, overlap and output.

Functions only; nothing here commits -- the route owns the transaction. Every route resolves an appointment through `load_scoped`, so an
id outside the caller's scope is the same 404 as a missing one. Logs carry ids, statuses and counts, never contact details or free text.
"""

import logging
from datetime import date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BDM_APPOINTMENT_AGENT_OUTCOMES,
    BDM_APPOINTMENT_CODE_SEQ,
    BDM_APPOINTMENT_COMMON_OUTCOMES,
    BDM_APPOINTMENT_COMMON_TYPES,
    BDM_APPOINTMENT_MODULE_TYPES,
    BDM_APPOINTMENT_OPEN,
    AuditLog,
    BdmAppointment,
    BdmAppointmentEvent,
    BdmOrganization,
    BdmOrganizationContact,
    BdmProfile,
    User,
)
from app.services.bdm import bdm_context

logger = logging.getLogger("app.bdm")

IST = ZoneInfo("Asia/Kolkata")
NOT_FOUND = "Appointment not found"
OWNER_ONLY = "Only the appointment's BDM can change it"
MAX_DURATION = 720
MAX_OVERLAP_MATCHES = 10
TRANSITIONS: dict[str, frozenset[str]] = {  # spec §5.4 (A2) -- the single source for enforcement and `permissions`
    "scheduled": frozenset({"confirmed", "rescheduled", "cancelled", "no_show", "completed"}),
    "confirmed": frozenset({"rescheduled", "cancelled", "no_show", "completed"}),
    "rescheduled": frozenset({"confirmed", "rescheduled", "cancelled", "no_show", "completed"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "no_show": frozenset(),
}
STATUS_TEXT = {
    "scheduled": "scheduled", "confirmed": "confirmed", "rescheduled": "rescheduled",
    "completed": "completed", "cancelled": "cancelled", "no_show": "marked as a no-show",
}
NOT_STARTED = {
    "complete": "You can only complete an appointment after its start time",
    "no_show": "You can only mark a no-show after the start time",
}


def appointment_types(bdm_type: str) -> tuple[str, ...]:
    """§2 common types plus the module's §C list, order kept, duplicates (agent_meeting, mou_discussion) once."""
    return tuple(dict.fromkeys(BDM_APPOINTMENT_COMMON_TYPES + BDM_APPOINTMENT_MODULE_TYPES[bdm_type]))


def appointment_outcomes(bdm_type: str) -> tuple[str, ...]:
    """A8: Agent §C for agent BDMs, §8 for school and college BDMs."""
    return BDM_APPOINTMENT_AGENT_OUTCOMES if bdm_type == "agent" else BDM_APPOINTMENT_COMMON_OUTCOMES


def format_code(n: int) -> str:
    return f"APT-{n:06d}"


async def next_code(db: AsyncSession) -> str:
    """A sequence never repeats a value; gaps after a rollback are accepted. uq_bdm_appointments_code is the backstop."""
    return format_code(await db.scalar(select(BDM_APPOINTMENT_CODE_SEQ.next_value())))


async def db_now(db: AsyncSession) -> datetime:
    """The database clock, read once per request: every time rule compares against the same instant."""
    return await db.scalar(select(func.now()))


def today_ist(now: datetime) -> date:
    return now.astimezone(IST).date()


def ist_bounds(date_from: date | None, date_to: date | None) -> list:
    """Inclusive IST dates -> the UTC half-open range [date_from 00:00 IST, date_to + 1 00:00 IST)."""
    filters = []
    if date_from is not None:
        filters.append(BdmAppointment.starts_at >= datetime.combine(date_from, time(), IST))
    if date_to is not None:
        filters.append(BdmAppointment.starts_at < datetime.combine(date_to + timedelta(days=1), time(), IST))
    return filters


async def caller_filters(db: AsyncSession, user: User) -> list:
    """Read scope (A3): a BDM their own appointments; a manager their team's (sub-select, so a row lock never touches bdm_profiles);
    super_admin all; any other role 403."""
    if user.role == "bdm":
        await bdm_context(db, user)
        return [BdmAppointment.bdm_user_id == user.id]
    if user.role == "bdm_manager":
        team = select(BdmProfile.user_id).where(BdmProfile.reporting_manager_user_id == user.id)
        return [BdmAppointment.bdm_user_id.in_(team)]
    if user.role == "super_admin":
        return []
    raise HTTPException(403, "BDM role required")


async def load_scoped(db: AsyncSession, user: User, appt_id: UUID, *, lock: bool = False) -> BdmAppointment:
    stmt = select(BdmAppointment).where(BdmAppointment.id == appt_id, *await caller_filters(db, user))
    if lock:
        stmt = stmt.with_for_update(of=BdmAppointment).execution_options(populate_existing=True)
    appt = await db.scalar(stmt)
    if appt is None:
        raise HTTPException(404, NOT_FOUND)
    return appt


def require_owner(user: User, appt: BdmAppointment, action: str) -> None:
    if user.role != "bdm" or appt.bdm_user_id != user.id:
        logger.warning("bdm_appt_write_refused", extra={"extra_fields": {"actor_id": str(user.id), "appointment_id": str(appt.id), "action": action}})
        raise HTTPException(403, OWNER_ONLY)


def require_transition(appt: BdmAppointment, to_status: str) -> None:
    if to_status not in TRANSITIONS[appt.status]:
        raise HTTPException(409, f"Appointment is already {STATUS_TEXT[appt.status]}")


def require_open(appt: BdmAppointment) -> None:
    if appt.status not in BDM_APPOINTMENT_OPEN:
        raise HTTPException(409, f"Appointment is already {STATUS_TEXT[appt.status]}")


def require_future(starts_at: datetime, now: datetime) -> None:
    if starts_at <= now:
        raise HTTPException(422, "Choose a time in the future")


def require_started(appt: BdmAppointment, now: datetime, action: str) -> None:
    if appt.starts_at > now:
        raise HTTPException(422, NOT_STARTED[action])


def snapshot(contact: BdmOrganizationContact) -> dict:
    return {
        "contact_id": contact.id, "contact_name": contact.name, "contact_designation": contact.designation,
        "contact_phone": contact.phone, "contact_email": contact.email,
    }


async def find_overlaps(db: AsyncSession, bdm_user_id: UUID, starts_at: datetime, duration: int, exclude_id: UUID | None = None) -> tuple[list[dict], int]:
    """A6: the owner's open appointments whose [start, start + duration) intersects. The lower bound keeps the query on
    ix_bdm_appointments_bdm_starts (no appointment can start earlier than new_start - MAX_DURATION and still overlap)."""
    end = starts_at + timedelta(minutes=duration)
    their_end = BdmAppointment.starts_at + func.make_interval(0, 0, 0, 0, 0, BdmAppointment.duration_minutes)
    conditions = [
        BdmAppointment.bdm_user_id == bdm_user_id,
        BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN),
        BdmAppointment.starts_at > starts_at - timedelta(minutes=MAX_DURATION),
        BdmAppointment.starts_at < end,
        their_end > starts_at,
    ]
    if exclude_id is not None:
        conditions.append(BdmAppointment.id != exclude_id)
    total = await db.scalar(select(func.count()).select_from(BdmAppointment).where(*conditions))
    if not total:
        return [], 0
    rows = (
        await db.execute(
            select(BdmAppointment, BdmOrganization.name)
            .join(BdmOrganization, BdmOrganization.id == BdmAppointment.organization_id)
            .where(*conditions)
            .order_by(BdmAppointment.starts_at, BdmAppointment.id)
            .limit(MAX_OVERLAP_MATCHES)
        )
    ).all()
    matches = [
        {"id": str(a.id), "code": a.code, "starts_at": a.starts_at.isoformat(), "duration_minutes": a.duration_minutes, "organization_name": name}
        for a, name in rows
    ]
    return matches, total


def overlap_conflict(matches: list[dict], total: int) -> HTTPException:
    return HTTPException(409, {"message": "You already have an appointment at this time", "code": "possible_overlap", "matches": matches, "total": total})


def record(db: AsyncSession, appt: BdmAppointment, actor: User, from_status: str | None, to_status: str, *, old_starts_at=None, new_starts_at=None, reason=None) -> None:
    db.add(BdmAppointmentEvent(appointment_id=appt.id, actor_user_id=actor.id, from_status=from_status, to_status=to_status, old_starts_at=old_starts_at, new_starts_at=new_starts_at, reason=reason))


def permissions(user: User, appt: BdmAppointment, now: datetime) -> dict[str, bool]:
    owner = user.role == "bdm" and appt.bdm_user_id == user.id
    open_ = owner and appt.status in BDM_APPOINTMENT_OPEN
    started = appt.starts_at <= now
    return {
        "can_edit": open_,
        "can_confirm": owner and "confirmed" in TRANSITIONS[appt.status],
        "can_reschedule": open_,
        "can_cancel": open_,
        "can_no_show": open_ and started,
        "can_complete": open_ and started,
    }


def _person(user: User) -> dict:
    return {"id": user.id, "full_name": user.full_name, "active": user.active}


def row_out(appt: BdmAppointment, org: BdmOrganization, owner: User) -> dict:
    return {
        "id": appt.id, "code": appt.code, "starts_at": appt.starts_at, "duration_minutes": appt.duration_minutes,
        "appointment_type": appt.appointment_type, "status": appt.status,
        "organization": {"id": org.id, "code": org.code, "name": org.name, "archived": org.archived_at is not None},
        "contact_name": appt.contact_name, "bdm": _person(owner),
    }


async def appointment_out(db: AsyncSession, user: User, appt: BdmAppointment, *, refresh: bool = True) -> dict:
    """The detail every route returns (R-A1). Refreshes first: server defaults (timestamps) are expired after a flush."""
    if refresh:
        await db.refresh(appt)
    org = await db.get(BdmOrganization, appt.organization_id)
    owner = await db.get(User, appt.bdm_user_id)
    events = (
        await db.execute(
            select(BdmAppointmentEvent, User.full_name)
            .join(User, User.id == BdmAppointmentEvent.actor_user_id)
            .where(BdmAppointmentEvent.appointment_id == appt.id)
            .order_by(BdmAppointmentEvent.position)
        )
    ).all()
    now = await db_now(db)
    return {
        **row_out(appt, org, owner),
        **{k: getattr(appt, k) for k in ("contact_id", "contact_designation", "contact_phone", "contact_email", "location", "purpose", "remarks", "outcome", "next_follow_up_on", "expected_leads", "expected_revenue", "created_at", "updated_at")},
        "events": [
            {"from_status": e.from_status, "to_status": e.to_status, "old_starts_at": e.old_starts_at, "new_starts_at": e.new_starts_at, "reason": e.reason, "actor_name": name, "created_at": e.created_at}
            for e, name in events
        ],
        "permissions": permissions(user, appt, now),
    }


def meeting_columns():
    """bdm-002's Last / Next meeting (spec §5.6), as correlated scalar subqueries on ix_bdm_appointments_org_starts. Across every BDM's
    appointments at the organization; dates only."""
    last = (
        select(func.max(BdmAppointment.starts_at))
        .where(BdmAppointment.organization_id == BdmOrganization.id, BdmAppointment.status == "completed")
        .correlate(BdmOrganization)
        .scalar_subquery()
        .label("last_meeting_at")
    )
    upcoming = (
        select(func.min(BdmAppointment.starts_at))
        .where(BdmAppointment.organization_id == BdmOrganization.id, BdmAppointment.status.in_(BDM_APPOINTMENT_OPEN), BdmAppointment.starts_at > func.now())
        .correlate(BdmOrganization)
        .scalar_subquery()
        .label("next_meeting_at")
    )
    return last, upcoming


def audit(db: AsyncSession, user: User, action: str, appt_id: UUID, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed); ids, field names, statuses and times only."""
    db.add(AuditLog(user_id=user.id, action=f"bdm_appointment.{action}", entity_type="bdm_appointment", entity_id=str(appt_id), metadata_json=metadata or {}))


def log(event: str, user: User, appt_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "appointment_id": str(appt_id), **extra}})
```

- [ ] **Step 4: Run to verify pass**

Run: `API_TEST tests/test_bdm_006_service.py`
Expected: PASS (6×6 matrix = 36 parametrized cases + the rest).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/services/bdm_appointments.py apps/api/tests/test_bdm_006_service.py
git commit -m "feat(bdm-006): appointment service -- catalogues, transitions, scope, overlap, output" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Router — create, read, list (+ registration and test helpers)

**Files:**
- Create: `apps/api/tests/bdm006_helpers.py`
- Create: `apps/api/app/api/bdm_appointments.py`
- Modify: `apps/api/app/main.py:21-22` (import) and `:72` (router tuple: append `bdm_appointments.router` after `bdm_organizations.router`)
- Test: `apps/api/tests/test_bdm_006_appointments.py`

**Interfaces:**
- Consumes: Task 2 schemas; Task 3 service; `app.services.bdm_organizations.load_scoped(db, user, org_id, *, lock=False)`, `load_contact(db, org, contact_id)`; `app.api.bdm.LIMIT, OFFSET, SEARCH, _matching`; `app.api.lookups._pattern`.
- Produces: router `router` (prefix `/bdm/appointments`); module-level helpers used by Tasks 5–6: `_envelope(db, user, appt, *, refresh=True)`, `_contact_of(db, org, contact_id)`, `_check_overlap(db, user, starts_at, duration, confirm, exclude_id=None) -> int`; constants `ARCHIVED`, `NOT_ASSIGNED`, `FOREIGN_CONTACT`. Test helpers `APPTS`, `future(hours)`, `appt_payload(org, **over)`, `create_appt(client, org, **over)`, `bdm_with_org(client, db, bdm_type="college", manager=None)`, `move_to_past(db, appt_id, minutes=30)`, `audits(db, appt_id)`.

- [ ] **Step 1: Test helpers** — `apps/api/tests/bdm006_helpers.py`:

```python
"""bdm-006 test builders. Unique per call: the shared test database is never truncated. Each test uses fresh BDMs, so overlap only
happens where a test books the same BDM twice on purpose (vary `hours` otherwise)."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update

from app.models import AuditLog, BdmAppointment
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm

APPTS = "/api/v1/bdm/appointments"


def future(hours: float = 48) -> str:
    return (datetime.now(UTC) + timedelta(hours=hours)).replace(second=0, microsecond=0).isoformat()


def appt_payload(org: dict, **over) -> dict:
    payload = {"organization_id": org["id"], "contact_id": org["contacts"][0]["id"], "starts_at": future(), "appointment_type": "college_meeting"}
    payload.update(over)
    return payload


async def create_appt(client, org: dict, **over) -> dict:
    response = await client.post(APPTS, json=appt_payload(org, **over))
    assert response.status_code == 201, response.text
    return response.json()["appointment"]


async def bdm_with_org(client, db, bdm_type: str = "college", manager=None):
    """A logged-in BDM of `bdm_type` with one organization assigned to them."""
    manager = manager or await make_manager(db)
    bdm = await make_bdm(db, manager, bdm_type)
    await login(client, bdm)
    return manager, bdm, await create_org(client)


async def move_to_past(db, appt_id, minutes: int = 30) -> None:
    """The only way to test "after the start time": the API never accepts a past time (A7)."""
    await db.execute(update(BdmAppointment).where(BdmAppointment.id == appt_id).values(starts_at=func.now() - timedelta(minutes=minutes)))
    await db.commit()


async def audits(db, appt_id) -> list[str]:
    rows = await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(appt_id)).order_by(AuditLog.created_at, AuditLog.id))
    return list(rows.all())
```

- [ ] **Step 2: Write the failing route tests** — `apps/api/tests/test_bdm_006_appointments.py`:

```python
"""bdm-006 -- create, read, list (AC1, AC8 retry; spec §5.3, §5.5). PATCH tests are appended in Task 5."""

import re
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, appt_payload, audits, bdm_with_org, create_appt, future

IST = ZoneInfo("Asia/Kolkata")


@pytest.mark.asyncio
async def test_create_captures_every_section_2_field(client, db_session):
    _, bdm, org = await bdm_with_org(client, db_session)
    contact = org["contacts"][0]
    a = await create_appt(
        client, org, appointment_type="placement_discussion", duration_minutes=90, location="Main block", purpose="Placement tie-up",
        remarks="Bring brochure", expected_leads=12, expected_revenue=25000.5,
    )
    assert re.fullmatch(r"APT-\d{6,}", a["code"])
    assert a["bdm"]["id"] == str(bdm.id) and a["organization"] == {"id": org["id"], "code": org["code"], "name": org["name"], "archived": False}
    assert (a["contact_id"], a["contact_name"], a["contact_designation"]) == (contact["id"], "Dr Rao", "Principal")
    assert a["status"] == "scheduled" and a["outcome"] is None and a["next_follow_up_on"] is None
    assert (a["appointment_type"], a["duration_minutes"], a["location"], a["purpose"], a["remarks"]) == ("placement_discussion", 90, "Main block", "Placement tie-up", "Bring brochure")
    assert a["expected_leads"] == 12 and a["expected_revenue"] == "25000.50"
    assert [(e["from_status"], e["to_status"]) for e in a["events"]] == [(None, "scheduled")]
    assert a["permissions"] == {"can_edit": True, "can_confirm": True, "can_reschedule": True, "can_cancel": True, "can_no_show": False, "can_complete": False}
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create"]
    assert (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]["code"] == a["code"]


@pytest.mark.asyncio
async def test_codes_increase(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    first, second = await create_appt(client, org, starts_at=future(24)), await create_appt(client, org, starts_at=future(30))
    assert int(second["code"][4:]) > int(first["code"][4:])


@pytest.mark.asyncio
async def test_a_retried_create_meets_the_overlap_warning_naming_the_first(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    payload = appt_payload(org)
    first = (await client.post(APPTS, json=payload)).json()["appointment"]
    retry = await client.post(APPTS, json=payload)
    assert retry.status_code == 409
    detail = retry.json()["detail"]
    assert detail["code"] == "possible_overlap" and detail["total"] == 1 and detail["matches"][0]["code"] == first["code"]
    saved = await client.post(APPTS, json={**payload, "confirm_overlap": True})
    assert saved.status_code == 201
    assert await audits(db_session, saved.json()["appointment"]["id"]) == ["bdm_appointment.create", "bdm_appointment.overlap_override"]


@pytest.mark.asyncio
async def test_adjacent_appointments_do_not_overlap(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    start = datetime.fromisoformat(future(72))
    await create_appt(client, org, starts_at=start.isoformat(), duration_minutes=60)
    await create_appt(client, org, starts_at=(start + timedelta(minutes=60)).isoformat())  # starts as the first ends


@pytest.mark.asyncio
async def test_create_rejections_in_rule_order(client, db_session):
    manager, bdm, org = await bdm_with_org(client, db_session)
    other = await create_org(client)
    cases = [
        ({"starts_at": future(-1)}, 422, "Choose a time in the future"),
        ({"appointment_type": "agent_visit"}, 422, "This appointment type is not available for College BDMs"),
        ({"contact_id": other["contacts"][0]["id"]}, 422, "Choose a contact of this organization"),
    ]
    for over, status, message in cases:
        response = await client.post(APPTS, json=appt_payload(org, **over))
        assert (response.status_code, response.json()["detail"]) == (status, message), over


@pytest.mark.asyncio
async def test_list_filters_ordering_and_ist_day_edges(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    second_org = await create_org(client)
    day = (datetime.now(IST) + timedelta(days=10)).date()
    late = await create_appt(client, org, starts_at=datetime.combine(day, time(23, 30), IST).isoformat(), duration_minutes=30)
    early = await create_appt(client, second_org, contact_id=second_org["contacts"][0]["id"], starts_at=datetime.combine(day + timedelta(days=1), time(0, 30), IST).isoformat(), appointment_type="workshop")

    async def codes(**params) -> list[str]:
        response = await client.get(APPTS, params=params)
        assert response.status_code == 200, response.text
        return [i["code"] for i in response.json()["items"]]

    assert await codes(date_from=day.isoformat(), date_to=day.isoformat()) == [late["code"]]
    assert await codes(date_from=(day + timedelta(days=1)).isoformat()) == [early["code"]]
    assert await codes(date_from=day.isoformat()) == [late["code"], early["code"]]  # ordered by start
    assert await codes(date_from=day.isoformat(), appointment_type="workshop") == [early["code"]]
    assert await codes(date_from=day.isoformat(), organization_id=org["id"]) == [late["code"]]
    assert await codes(q=early["code"]) == [early["code"]]
    assert await codes(q=second_org["name"][-6:]) == [early["code"]]
    assert await codes(date_from=day.isoformat(), status=["scheduled", "confirmed"]) == [late["code"], early["code"]]
    assert await codes(date_from=day.isoformat(), status="cancelled") == []
    page = (await client.get(APPTS, params={"date_from": day.isoformat(), "limit": 1, "offset": 1})).json()
    assert (page["total"], page["limit"], page["offset"], [i["code"] for i in page["items"]]) == (2, 1, 1, [early["code"]])
    row = page["items"][0]
    assert set(row) == {"id", "code", "starts_at", "duration_minutes", "appointment_type", "status", "organization", "contact_name", "bdm"}


@pytest.mark.asyncio
async def test_list_parameter_validation(client, db_session):
    await bdm_with_org(client, db_session)
    for params in ({"limit": 0}, {"limit": 101}, {"offset": -1}, {"status": "lost"}, {"date_from": "2030-02-02", "date_to": "2030-02-01"}, {"bdm_user_id": "00000000-0000-0000-0000-000000000000"}, {"q": "x" * 201}):
        assert (await client.get(APPTS, params=params)).status_code == 422, params


@pytest.mark.asyncio
async def test_unknown_id_is_404(client, db_session):
    await bdm_with_org(client, db_session)
    response = await client.get(f"{APPTS}/00000000-0000-0000-0000-000000000000")
    assert (response.status_code, response.json()["detail"]) == (404, "Appointment not found")


@pytest.mark.asyncio
async def test_school_and_agent_bdms_get_their_own_lists(client, db_session):
    manager = await make_manager(db_session)
    for bdm_type, module_type, foreign in (("school", "parent_orientation", "hod_meeting"), ("agent", "commission_discussion", "parent_orientation")):
        await login(client, await make_bdm(db_session, manager, bdm_type))
        org = await create_org(client)
        assert (await client.post(APPTS, json=appt_payload(org, appointment_type=module_type))).status_code == 201
        assert (await client.post(APPTS, json=appt_payload(org, appointment_type=foreign, starts_at=future(96)))).status_code == 422
        assert (await client.post(APPTS, json=appt_payload(org, appointment_type="seminar_workshop", starts_at=future(120)))).status_code == 201
```

- [ ] **Step 3: Run to verify failure**

Run: `API_TEST tests/test_bdm_006_appointments.py`
Expected: FAIL — 404 on `POST /api/v1/bdm/appointments` (router not registered).

- [ ] **Step 4: Implement the router** — `apps/api/app/api/bdm_appointments.py`:

```python
"""bdm-006 (DEC-SCOPE-063, spec §5.3): BDM appointments.

Every `{appt_id}` resolves through `services.bdm_appointments.load_scoped` (out of scope = 404); every write is one transaction --
scope, row lock (organization before appointment), validation, change, event, audit, one commit here. Lists are
{items, total, limit, offset}, ordered by start time then id."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.core.database import get_db
from app.models import BdmAppointment, BdmOrganization, User
from app.schemas import (
    BDM_APPOINTMENT_OPTIONAL_FIELDS,
    BdmAppointmentCreate,
    BdmAppointmentEnvelope,
    BdmAppointmentPage,
    BdmAppointmentStatus,
    BdmAppointmentType,
)
from app.services import bdm_appointments as svc
from app.services import bdm_organizations as org_svc
from app.services.bdm import bdm_context

router = APIRouter(prefix="/bdm/appointments", tags=["bdm-appointments"])
ARCHIVED = "This organization is archived — restore it before booking"
NOT_ASSIGNED = "Only the assigned BDM can book appointments for this organization"
FOREIGN_CONTACT = "Choose a contact of this organization"


async def _envelope(db: AsyncSession, user: User, appt: BdmAppointment, *, refresh: bool = True) -> dict:
    return {"appointment": await svc.appointment_out(db, user, appt, refresh=refresh)}


async def _contact_of(db: AsyncSession, org: BdmOrganization, contact_id: UUID):
    """A contact of another organization is a bad choice in this form (422), not a missing resource."""
    try:
        return await org_svc.load_contact(db, org, contact_id)
    except HTTPException:
        raise HTTPException(422, FOREIGN_CONTACT) from None


def _type_allowed(bdm_type: str, appointment_type: str) -> None:
    if appointment_type not in svc.appointment_types(bdm_type):
        raise HTTPException(422, f"This appointment type is not available for {bdm_type.capitalize()} BDMs")


async def _check_overlap(db: AsyncSession, user: User, starts_at, duration: int, confirm: bool, exclude_id: UUID | None = None) -> int:
    """A6: warn (409) unless acknowledged; returns the match count so the caller can audit the override."""
    matches, total = await svc.find_overlaps(db, user.id, starts_at, duration, exclude_id)
    if total and not confirm:
        svc.log("bdm_appt_overlap_warned", user, exclude_id or "-", match_count=total)
        raise svc.overlap_conflict(matches, total)
    return total


@router.get("", response_model=BdmAppointmentPage)
async def list_appointments(
    date_from: date | None = None,
    date_to: date | None = None,
    status: list[BdmAppointmentStatus] | None = Query(None),
    appointment_type: BdmAppointmentType | None = None,
    organization_id: UUID | None = None,
    bdm_user_id: UUID | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Filters are ANDed with the caller's scope, so they only narrow it (R-A10). One page query: organization + owner (no N+1)."""
    filters = await svc.caller_filters(db, user)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "date_from must be on or before date_to")
    if bdm_user_id is not None:
        if user.role == "bdm":
            raise HTTPException(422, "bdm_user_id is only for managers")
        filters.append(BdmAppointment.bdm_user_id == bdm_user_id)
    filters += svc.ist_bounds(date_from, date_to)
    if status:
        filters.append(BdmAppointment.status.in_(status))
    if appointment_type:
        filters.append(BdmAppointment.appointment_type == appointment_type)
    if organization_id:
        filters.append(BdmAppointment.organization_id == organization_id)
    filters += _matching(like_pattern(q), BdmAppointment.code, BdmOrganization.name)
    joined = BdmOrganization.id == BdmAppointment.organization_id
    total = await db.scalar(select(func.count()).select_from(BdmAppointment).join(BdmOrganization, joined).where(*filters))
    stmt = (
        select(BdmAppointment, BdmOrganization, User)
        .join(BdmOrganization, joined)
        .join(User, User.id == BdmAppointment.bdm_user_id)
        .where(*filters)
        .order_by(BdmAppointment.starts_at, BdmAppointment.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).all()
    return {"items": [svc.row_out(a, o, u) for a, o, u in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.post("", status_code=201, response_model=BdmAppointmentEnvelope)
async def create_appointment(payload: BdmAppointmentCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """spec §5.5, in this order so each refusal is exactly one rule. Not idempotent: a retry meets the overlap warning (R-A5)."""
    profile = await bdm_context(db, user)
    org = await org_svc.load_scoped(db, user, payload.organization_id, lock=True)  # out of type scope -> 404; serializes with archive
    if org.assigned_bdm_user_id != user.id:
        raise HTTPException(403, NOT_ASSIGNED)
    if org.archived_at is not None:
        raise HTTPException(422, ARCHIVED)
    contact = await _contact_of(db, org, payload.contact_id)
    _type_allowed(profile.bdm_type, payload.appointment_type)
    svc.require_future(payload.starts_at, await svc.db_now(db))
    overlaps = await _check_overlap(db, user, payload.starts_at, payload.duration_minutes, payload.confirm_overlap)
    appt = BdmAppointment(
        code=await svc.next_code(db),
        bdm_user_id=user.id,
        organization_id=org.id,
        starts_at=payload.starts_at,
        duration_minutes=payload.duration_minutes,
        appointment_type=payload.appointment_type,
        status="scheduled",
        **svc.snapshot(contact),
        **{k: getattr(payload, k) for k in BDM_APPOINTMENT_OPTIONAL_FIELDS},
    )
    db.add(appt)
    await db.flush()
    svc.record(db, appt, user, None, "scheduled")
    svc.audit(
        db, user, "create", appt.id,
        {
            "code": appt.code, "organization_id": str(org.id), "appointment_type": appt.appointment_type, "starts_at": appt.starts_at.isoformat(),
            "fields": sorted(k for k in BDM_APPOINTMENT_OPTIONAL_FIELDS if getattr(payload, k) is not None),
        },
    )
    if overlaps:
        svc.audit(db, user, "overlap_override", appt.id, {"match_count": overlaps})
    await db.commit()
    svc.log("bdm_appt_created", user, appt.id, organization_id=str(org.id), overlap_override=bool(overlaps))
    return await _envelope(db, user, appt)


@router.get("/{appt_id}", response_model=BdmAppointmentEnvelope)
async def get_appointment(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await svc.load_scoped(db, user, appt_id)
    return await _envelope(db, user, appt, refresh=False)  # nothing was written
```

Register in `main.py`: add `bdm_appointments,` to the `from app.api import (...)` list after `bdm_organizations,`, and append `bdm_appointments.router` to the router tuple on line 72 after `bdm_organizations.router`.

- [ ] **Step 5: Run to verify pass**

Run: `API_TEST tests/test_bdm_006_appointments.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/bdm_appointments.py apps/api/app/main.py apps/api/tests/bdm006_helpers.py apps/api/tests/test_bdm_006_appointments.py
git commit -m "feat(bdm-006): create, read and list appointments" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: PATCH (edit while open; contact re-snapshot; AC10)

**Files:**
- Modify: `apps/api/app/api/bdm_appointments.py` (append the route; add `BdmAppointmentUpdate` to the schema import)
- Test: `apps/api/tests/test_bdm_006_appointments.py` (append)

**Interfaces:**
- Consumes: Task 4 helpers `_envelope`, `_contact_of`, `_type_allowed`, `_check_overlap`; service `load_scoped`, `require_owner`, `require_open`, `snapshot`, `audit`, `log`; `org_svc.load_scoped(..., lock=True)`.
- Produces: `PATCH /bdm/appointments/{appt_id}` → `{appointment}`.

- [ ] **Step 1: Append the failing tests**

```python
from sqlalchemy import update as sa_update

from app.models import BdmAppointment
from tests.bdm002_helpers import ORGS


@pytest.mark.asyncio
async def test_patch_changes_only_sent_fields_and_audits_their_names(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, location="Gate 1")
    response = await client.patch(f"{APPTS}/{a['id']}", json={"location": "Gate 2", "purpose": "Demo"})
    assert response.status_code == 200, response.text
    b = response.json()["appointment"]
    assert (b["location"], b["purpose"], b["starts_at"], b["status"]) == ("Gate 2", "Demo", a["starts_at"], "scheduled")
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create", "bdm_appointment.update"]
    assert len(b["events"]) == 1  # an edit is not a transition


@pytest.mark.asyncio
async def test_noop_patch_writes_nothing(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, location="Gate 1")
    for body in ({}, {"location": "Gate 1", "duration_minutes": 60}):
        b = (await client.patch(f"{APPTS}/{a['id']}", json=body)).json()["appointment"]
        assert b["updated_at"] == a["updated_at"]
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create"]


@pytest.mark.asyncio
async def test_patch_contact_recopies_the_snapshot_and_refuses_another_orgs_contact(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    org = (await client.post(f"{ORGS}/{org['id']}/contacts", json={"name": "Ms Iyer", "designation": "TPO", "phone": "+91 99999 00000"})).json()["organization"]
    iyer = next(c for c in org["contacts"] if c["name"] == "Ms Iyer")
    a = await create_appt(client, org)
    b = (await client.patch(f"{APPTS}/{a['id']}", json={"contact_id": iyer["id"]})).json()["appointment"]
    assert (b["contact_id"], b["contact_name"], b["contact_designation"], b["contact_phone"]) == (iyer["id"], "Ms Iyer", "TPO", "+91 99999 00000")
    other = await create_org(client)
    response = await client.patch(f"{APPTS}/{a['id']}", json={"contact_id": other["contacts"][0]["id"]})
    assert (response.status_code, response.json()["detail"]) == (422, "Choose a contact of this organization")


@pytest.mark.asyncio
async def test_patch_rules(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(50))
    b = await create_appt(client, org, starts_at=future(51.5))
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"appointment_type": "agent_visit"})).status_code == 422
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"starts_at": future(80)})).status_code == 422  # unknown field
    clash = await client.patch(f"{APPTS}/{a['id']}", json={"duration_minutes": 120})  # now runs into b
    assert clash.status_code == 409 and clash.json()["detail"]["matches"][0]["code"] == b["code"]
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"duration_minutes": 120, "confirm_overlap": True})).status_code == 200
    await db_session.execute(sa_update(BdmAppointment).where(BdmAppointment.id == a["id"]).values(status="cancelled"))
    await db_session.commit()
    closed = await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "late"})
    assert (closed.status_code, closed.json()["detail"]) == (409, "Appointment is already cancelled")


@pytest.mark.asyncio
async def test_deleting_the_booked_contact_keeps_the_snapshot(client, db_session):
    """AC10 / A5 (Review Focus 3): bdm-002's delete route is unchanged and still succeeds."""
    _, _, org = await bdm_with_org(client, db_session)
    org = (await client.post(f"{ORGS}/{org['id']}/contacts", json={"name": "Ms Iyer"})).json()["organization"]
    rao = next(c for c in org["contacts"] if c["name"] == "Dr Rao")
    a = await create_appt(client, org, contact_id=rao["id"])
    assert (await client.delete(f"{ORGS}/{org['id']}/contacts/{rao['id']}")).status_code == 200
    b = (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]
    assert (b["contact_id"], b["contact_name"], b["contact_designation"]) == (None, "Dr Rao", "Principal")
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST tests/test_bdm_006_appointments.py -k "patch or snapshot"`
Expected: FAIL — 405 Method Not Allowed.

- [ ] **Step 3: Implement** — append to `bdm_appointments.py` (and import `BdmAppointmentUpdate`):

```python
@router.patch("/{appt_id}", response_model=BdmAppointmentEnvelope)
async def update_appointment(appt_id: UUID, payload: BdmAppointmentUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """PATCH: only the fields sent; values equal to the stored ones are not changes (no audit, no updated_at bump, R-A6). A contact change
    locks the organization first (§5.7: organization -> appointment), so bdm-002's contact delete cannot remove it mid-write."""
    changes = payload.model_dump(exclude_unset=True, exclude={"confirm_overlap"})
    current = await svc.load_scoped(db, user, appt_id)  # scope (404) and owner (403) before taking any lock
    svc.require_owner(user, current, "update")
    contact = None
    if "contact_id" in changes and changes["contact_id"] != current.contact_id:
        org = await org_svc.load_scoped(db, user, current.organization_id, lock=True)
        contact = await _contact_of(db, org, changes["contact_id"])
    appt = await svc.load_scoped(db, user, appt_id, lock=True)
    svc.require_open(appt)
    changes.pop("contact_id", None)
    changed = sorted(k for k, v in changes.items() if getattr(appt, k) != v)
    if "appointment_type" in changed:
        _type_allowed((await bdm_context(db, user)).bdm_type, changes["appointment_type"])
    overlaps = 0
    if "duration_minutes" in changed:
        overlaps = await _check_overlap(db, user, appt.starts_at, changes["duration_minutes"], payload.confirm_overlap, exclude_id=appt.id)
    for key in changed:
        setattr(appt, key, changes[key])
    if contact is not None:
        for key, value in svc.snapshot(contact).items():
            setattr(appt, key, value)
        changed = sorted({*changed, "contact_id"})
    if changed:
        svc.audit(db, user, "update", appt.id, {"fields": changed})
        if overlaps:
            svc.audit(db, user, "overlap_override", appt.id, {"match_count": overlaps})
    await db.commit()
    if changed:
        svc.log("bdm_appt_updated", user, appt.id, fields=changed)
    return await _envelope(db, user, appt)
```

- [ ] **Step 4: Run to verify pass**

Run: `API_TEST tests/test_bdm_006_appointments.py tests/test_bdm_002_contacts.py`
Expected: PASS (bdm-002's contact tests unchanged and green).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/bdm_appointments.py apps/api/tests/test_bdm_006_appointments.py
git commit -m "feat(bdm-006): edit open appointments; contact snapshot survives contact delete" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Actions — confirm, reschedule, cancel, no-show, complete

**Files:**
- Modify: `apps/api/app/api/bdm_appointments.py` (append five routes; import `BdmAppointmentComplete`, `BdmAppointmentReason`, `BdmAppointmentReschedule`)
- Test: `apps/api/tests/test_bdm_006_transitions.py`

**Interfaces:**
- Consumes: service `load_scoped`, `require_owner`, `require_transition`, `require_future`, `require_started`, `appointment_outcomes`, `today_ist`, `db_now`, `record`, `audit`, `log`; Task 4 `_check_overlap`, `_envelope`.
- Produces: `POST /bdm/appointments/{id}/confirm | reschedule | cancel | no-show | complete` → `{appointment}`.

- [ ] **Step 1: Write the failing tests**

```python
"""bdm-006 -- status actions (AC3, AC4, AC5; spec §5.3, §5.4)."""

from datetime import datetime, timedelta

import pytest

from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm006_helpers import APPTS, audits, bdm_with_org, create_appt, future, move_to_past


def url(appt: dict, action: str) -> str:
    return f"{APPTS}/{appt['id']}/{action}"


@pytest.mark.asyncio
async def test_book_confirm_complete_with_outcome(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    confirmed = (await client.post(url(a, "confirm"))).json()["appointment"]
    assert confirmed["status"] == "confirmed" and confirmed["permissions"]["can_confirm"] is False
    early = await client.post(url(a, "complete"), json={"outcome": "interested"})
    assert (early.status_code, early.json()["detail"]) == (422, "You can only complete an appointment after its start time")
    await move_to_past(db_session, a["id"])
    done = await client.post(url(a, "complete"), json={"outcome": "student_leads_expected", "next_follow_up_on": datetime.now().date().isoformat()})
    assert done.status_code == 200, done.text
    d = done.json()["appointment"]
    assert (d["status"], d["outcome"]) == ("completed", "student_leads_expected") and d["next_follow_up_on"]
    assert [(e["from_status"], e["to_status"]) for e in d["events"]] == [(None, "scheduled"), ("scheduled", "confirmed"), ("confirmed", "completed")]
    assert not any(d["permissions"].values())
    assert await audits(db_session, a["id"]) == ["bdm_appointment.create", "bdm_appointment.confirm", "bdm_appointment.complete"]


@pytest.mark.asyncio
async def test_reschedule_twice_keeps_both_old_times(client, db_session):
    """AC4: each reschedule records its old time; the status is Rescheduled both times."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(30))
    t2, t3 = future(40), future(50)
    first = (await client.post(url(a, "reschedule"), json={"starts_at": t2, "reason": "Principal travelling"})).json()["appointment"]
    second = (await client.post(url(a, "reschedule"), json={"starts_at": t3, "duration_minutes": 30})).json()["appointment"]
    assert (second["status"], second["duration_minutes"]) == ("rescheduled", 30)
    moves = [(e["from_status"], e["to_status"], e["old_starts_at"], e["new_starts_at"], e["reason"]) for e in second["events"][1:]]
    assert moves == [
        ("scheduled", "rescheduled", a["starts_at"], first["starts_at"], "Principal travelling"),
        ("rescheduled", "rescheduled", first["starts_at"], second["starts_at"], None),
    ]
    assert (await client.post(url(a, "confirm"))).json()["appointment"]["status"] == "confirmed"  # rescheduled -> confirmed


@pytest.mark.asyncio
async def test_reschedule_rules(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(30))
    b = await create_appt(client, org, starts_at=future(60))
    same = await client.post(url(a, "reschedule"), json={"starts_at": a["starts_at"]})
    assert (same.status_code, same.json()["detail"]) == (422, "Choose a different time")
    past = await client.post(url(a, "reschedule"), json={"starts_at": future(-2)})
    assert (past.status_code, past.json()["detail"]) == (422, "Choose a time in the future")
    clash = await client.post(url(a, "reschedule"), json={"starts_at": b["starts_at"]})
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "possible_overlap"
    ok = await client.post(url(a, "reschedule"), json={"starts_at": b["starts_at"], "confirm_overlap": True})
    assert ok.status_code == 200
    assert (await audits(db_session, a["id"]))[-2:] == ["bdm_appointment.reschedule", "bdm_appointment.overlap_override"]


@pytest.mark.asyncio
async def test_cancel_and_no_show_need_a_reason_and_are_terminal(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org, starts_at=future(30))
    b = await create_appt(client, org, starts_at=future(60))
    assert (await client.post(url(a, "cancel"), json={})).status_code == 422
    assert (await client.post(url(a, "cancel"), json={"reason": "  "})).status_code == 422
    cancelled = (await client.post(url(a, "cancel"), json={"reason": "College closed"})).json()["appointment"]
    assert cancelled["status"] == "cancelled" and cancelled["events"][-1]["reason"] == "College closed"
    for action, body in (("confirm", None), ("cancel", {"reason": "x"}), ("reschedule", {"starts_at": future(90)})):
        response = await client.post(url(a, action), json=body)
        assert (response.status_code, response.json()["detail"]) == (409, "Appointment is already cancelled"), action
    early = await client.post(url(b, "no-show"), json={"reason": "Nobody came"})
    assert (early.status_code, early.json()["detail"]) == (422, "You can only mark a no-show after the start time")
    await move_to_past(db_session, b["id"])
    assert (await client.post(url(b, "no-show"), json={"reason": "Nobody came"})).json()["appointment"]["status"] == "no_show"
    again = await client.post(url(b, "complete"), json={"outcome": "interested"})
    assert (again.status_code, again.json()["detail"]) == (409, "Appointment is already marked as a no-show")


@pytest.mark.asyncio
async def test_complete_validates_outcome_per_type_and_follow_up_date(client, db_session):
    manager = await make_manager(db_session)
    await login(client, await make_bdm(db_session, manager, "agent"))
    org = await create_org(client)
    a = await create_appt(client, org, appointment_type="agent_visit")
    await move_to_past(db_session, a["id"])
    foreign = await client.post(url(a, "complete"), json={"outcome": "course_promotion_interested"})
    assert (foreign.status_code, foreign.json()["detail"]) == (422, "This outcome is not available for Agent BDMs")
    yesterday = (datetime.now() - timedelta(days=2)).date().isoformat()
    stale = await client.post(url(a, "complete"), json={"outcome": "agreement_required", "next_follow_up_on": yesterday})
    assert (stale.status_code, stale.json()["detail"]) == (422, "Next follow-up can't be in the past")
    assert (await client.post(url(a, "complete"), json={"outcome": "agreement_required"})).status_code == 200


@pytest.mark.asyncio
async def test_confirm_twice_is_409(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    assert (await client.post(url(a, "confirm"))).status_code == 200
    again = await client.post(url(a, "confirm"))
    assert (again.status_code, again.json()["detail"]) == (409, "Appointment is already confirmed")
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST tests/test_bdm_006_transitions.py`
Expected: FAIL — 404/405 on the action routes.

- [ ] **Step 3: Implement** — append to `bdm_appointments.py`:

```python
async def _transitioning(db: AsyncSession, user: User, appt_id: UUID, action: str, to_status: str) -> BdmAppointment:
    """Scope (404), row lock, owner (403), then state (409) -- the order every action shares."""
    appt = await svc.load_scoped(db, user, appt_id, lock=True)
    svc.require_owner(user, appt, action)
    svc.require_transition(appt, to_status)
    return appt


async def _finish(db: AsyncSession, user: User, appt: BdmAppointment, action: str, from_status: str, metadata: dict | None = None) -> dict:
    svc.audit(db, user, action, appt.id, {"from": from_status, "to": appt.status, **(metadata or {})})
    await db.commit()
    svc.log(f"bdm_appt_{action}", user, appt.id, from_status=from_status, to_status=appt.status)
    return await _envelope(db, user, appt)


@router.post("/{appt_id}/confirm", response_model=BdmAppointmentEnvelope)
async def confirm_appointment(appt_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await _transitioning(db, user, appt_id, "confirm", "confirmed")
    before, appt.status = appt.status, "confirmed"
    svc.record(db, appt, user, before, "confirmed")
    return await _finish(db, user, appt, "confirm", before)


@router.post("/{appt_id}/reschedule", response_model=BdmAppointmentEnvelope)
async def reschedule_appointment(appt_id: UUID, payload: BdmAppointmentReschedule, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC4: the old time goes into the event; the status is always Rescheduled (also from Rescheduled)."""
    appt = await _transitioning(db, user, appt_id, "reschedule", "rescheduled")
    svc.require_future(payload.starts_at, await svc.db_now(db))
    if payload.starts_at == appt.starts_at:
        raise HTTPException(422, "Choose a different time")
    duration = payload.duration_minutes or appt.duration_minutes
    overlaps = await _check_overlap(db, user, payload.starts_at, duration, payload.confirm_overlap, exclude_id=appt.id)
    before, old = appt.status, appt.starts_at
    appt.status, appt.starts_at, appt.duration_minutes = "rescheduled", payload.starts_at, duration
    svc.record(db, appt, user, before, "rescheduled", old_starts_at=old, new_starts_at=payload.starts_at, reason=payload.reason)
    if overlaps:
        svc.audit(db, user, "overlap_override", appt.id, {"match_count": overlaps})
    return await _finish(db, user, appt, "reschedule", before, {"old_starts_at": old.isoformat(), "new_starts_at": payload.starts_at.isoformat()})


@router.post("/{appt_id}/cancel", response_model=BdmAppointmentEnvelope)
async def cancel_appointment(appt_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await _transitioning(db, user, appt_id, "cancel", "cancelled")
    before, appt.status = appt.status, "cancelled"
    svc.record(db, appt, user, before, "cancelled", reason=payload.reason)
    return await _finish(db, user, appt, "cancel", before)


@router.post("/{appt_id}/no-show", response_model=BdmAppointmentEnvelope)
async def no_show_appointment(appt_id: UUID, payload: BdmAppointmentReason, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    appt = await _transitioning(db, user, appt_id, "no_show", "no_show")
    svc.require_started(appt, await svc.db_now(db), "no_show")
    before, appt.status = appt.status, "no_show"
    svc.record(db, appt, user, before, "no_show", reason=payload.reason)
    return await _finish(db, user, appt, "no_show", before)


@router.post("/{appt_id}/complete", response_model=BdmAppointmentEnvelope)
async def complete_appointment(appt_id: UUID, payload: BdmAppointmentComplete, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC5 / A1: an outcome valid for the owner's type and a past start time; the follow-up date is not in the past (IST)."""
    appt = await _transitioning(db, user, appt_id, "complete", "completed")
    now = await svc.db_now(db)
    svc.require_started(appt, now, "complete")
    bdm_type = (await bdm_context(db, user)).bdm_type
    if payload.outcome not in svc.appointment_outcomes(bdm_type):
        raise HTTPException(422, f"This outcome is not available for {bdm_type.capitalize()} BDMs")
    if payload.next_follow_up_on is not None and payload.next_follow_up_on < svc.today_ist(now):
        raise HTTPException(422, "Next follow-up can't be in the past")
    before = appt.status
    appt.status, appt.outcome, appt.next_follow_up_on = "completed", payload.outcome, payload.next_follow_up_on
    svc.record(db, appt, user, before, "completed")
    return await _finish(db, user, appt, "complete", before, {"outcome": payload.outcome})
```

Note on the test's follow-up date: `datetime.now().date()` in the container is UTC; it is never later than today in IST, so "today" is always accepted.

- [ ] **Step 4: Run to verify pass**

Run: `API_TEST tests/test_bdm_006_transitions.py tests/test_bdm_006_service.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/bdm_appointments.py apps/api/tests/test_bdm_006_transitions.py
git commit -m "feat(bdm-006): confirm, reschedule, cancel, no-show and complete with history" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Scope matrix, IDOR, archived organizations, reassignment

**Files:**
- Test: `apps/api/tests/test_bdm_006_scope.py`
- Modify only if a test fails: `apps/api/app/api/bdm_appointments.py` / `services/bdm_appointments.py`

**Interfaces:**
- Consumes: everything from Tasks 4–6. Produces: none (verification task; AC6, AC7).

- [ ] **Step 1: Write the tests**

```python
"""bdm-006 -- who sees and changes what (AC6, AC7; spec §5.5, §5.7, §12.3)."""

import pytest

from tests.bdm001_helpers import login, make_manager, make_user
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm006_helpers import APPTS, appt_payload, bdm_with_org, create_appt, future

ACTIONS = (("confirm", None), ("cancel", {"reason": "x"}), ("reschedule", {"starts_at": future(200)}))


@pytest.mark.asyncio
async def test_scope_matrix(client, db_session):
    manager, owner, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    peer = await make_bdm(db_session, manager, "college")
    other_type = await make_bdm(db_session, manager, "school")
    other_manager = await make_manager(db_session)
    super_admin = await make_user(db_session, "super_admin", "global")
    it_admin = await make_user(db_session, "it_admin", "it")
    no_profile = await make_user(db_session, "bdm", "it")

    await login(client, peer)
    assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 404
    assert a["id"] not in [i["id"] for i in (await client.get(APPTS)).json()["items"]]
    refused = await client.post(APPTS, json=appt_payload(org))
    assert (refused.status_code, refused.json()["detail"]) == (403, "Only the assigned BDM can book appointments for this organization")
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "x"})).status_code == 404

    await login(client, other_type)
    hidden = await client.post(APPTS, json=appt_payload(org))
    assert (hidden.status_code, hidden.json()["detail"]) == (404, "Organization not found")

    for reader in (manager, super_admin):
        await login(client, reader)
        detail = await client.get(f"{APPTS}/{a['id']}")
        assert detail.status_code == 200 and not any(detail.json()["appointment"]["permissions"].values())
        for action, body in ACTIONS:
            response = await client.post(f"{APPTS}/{a['id']}/{action}", json=body)
            assert (response.status_code, response.json()["detail"]) == (403, "Only the appointment's BDM can change it"), (reader.role, action)
        assert (await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "x"})).status_code == 403
        assert (await client.post(APPTS, json=appt_payload(org))).status_code == 403
    await login(client, manager)
    assert [i["id"] for i in (await client.get(APPTS, params={"bdm_user_id": str(owner.id)})).json()["items"]] == [a["id"]]
    assert (await client.get(APPTS, params={"bdm_user_id": str(peer.id)})).json()["total"] == 0

    await login(client, other_manager)
    assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 404
    assert (await client.get(APPTS, params={"bdm_user_id": str(owner.id)})).json()["total"] == 0  # a filter never widens scope

    for user in (it_admin, no_profile):
        await login(client, user)
        assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 403
        assert (await client.get(APPTS)).status_code == 403


@pytest.mark.asyncio
async def test_archived_organization_blocks_create_but_not_existing_appointments(client, db_session):
    """AC6 / A4."""
    _, _, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    assert (await client.post(f"{ORGS}/{org['id']}/archive")).status_code == 200
    refused = await client.post(APPTS, json=appt_payload(org, starts_at=future(100)))
    assert (refused.status_code, refused.json()["detail"]) == (422, "This organization is archived — restore it before booking")
    detail = (await client.get(f"{APPTS}/{a['id']}")).json()["appointment"]
    assert detail["organization"]["archived"] is True
    assert (await client.patch(f"{APPTS}/{a['id']}", json={"remarks": "moved"})).status_code == 200
    assert (await client.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "College archived"})).status_code == 200


@pytest.mark.asyncio
async def test_reassigned_organization_keeps_appointments_with_their_bdm(client, db_session):
    """Review Focus 5: ownership is fixed (bdm-025 moves portfolios)."""
    manager, owner, org = await bdm_with_org(client, db_session)
    a = await create_appt(client, org)
    new_assignee = await make_bdm(db_session, manager, "college")
    await login(client, manager)
    assert (await client.post(f"{ORGS}/{org['id']}/assign", json={"bdm_user_id": str(new_assignee.id)})).status_code == 200
    await login(client, owner)
    assert (await client.post(f"{APPTS}/{a['id']}/confirm")).status_code == 200
    assert (await client.post(APPTS, json=appt_payload(org, starts_at=future(100)))).status_code == 403  # no longer assigned
    await login(client, new_assignee)
    assert (await client.get(f"{APPTS}/{a['id']}")).status_code == 404
    assert (await client.post(APPTS, json=appt_payload(org, starts_at=future(100)))).status_code == 201
```

- [ ] **Step 2: Run**

Run: `API_TEST tests/test_bdm_006_scope.py`
Expected: PASS. If a case fails, fix the route or service (never the assertion) and re-run; record the fix in the commit message.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_bdm_006_scope.py
git commit -m "test(bdm-006): scope matrix, archived organizations, reassignment" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Concurrency

**Files:**
- Test: `apps/api/tests/test_bdm_006_concurrency.py`

**Interfaces:** Consumes Tasks 4–6 routes and bdm-002's archive / contact-delete routes. Produces none.

- [ ] **Step 1: Write the tests**

```python
"""bdm-006 -- races (spec §5.7; Review Focus 2). Two real sessions through the app, the bdm-002 pattern."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models import BdmAppointment, BdmAppointmentEvent
from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import ORGS, create_org, make_bdm
from tests.bdm006_helpers import APPTS, appt_payload, create_appt, future


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_confirm_and_cancel_race(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one)
        a = await create_appt(one, org)
        results = await asyncio.gather(one.post(f"{APPTS}/{a['id']}/confirm"), two.post(f"{APPTS}/{a['id']}/cancel", json={"reason": "Clash"}))
    codes = sorted(r.status_code for r in results)
    assert codes in ([200, 200], [200, 409])  # confirm then cancel is legal; cancel then confirm is 409
    events = await db_session.scalar(select(func.count()).select_from(BdmAppointmentEvent).where(BdmAppointmentEvent.appointment_id == a["id"]))
    assert events == 1 + codes.count(200)
    final = await db_session.scalar(select(BdmAppointment.status).where(BdmAppointment.id == a["id"]).execution_options(populate_existing=True))
    assert final == "cancelled"  # in both orders the cancel lands (or was the only success)


@pytest.mark.asyncio
async def test_archive_and_create_serialize(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one)
        archive, create = await asyncio.gather(one.post(f"{ORGS}/{org['id']}/archive"), two.post(APPTS, json=appt_payload(org)))
    assert archive.status_code == 200
    assert create.status_code in (201, 422), create.text  # never a 500


@pytest.mark.asyncio
async def test_contact_switch_and_contact_delete_race(db_session):
    bdm = await make_bdm(db_session, await make_manager(db_session))
    async with _client() as one, _client() as two:
        await login(one, bdm)
        await login(two, bdm)
        org = await create_org(one, contacts=[{"name": "Dr Rao", "is_primary": True}, {"name": "Ms Iyer"}])
        rao, iyer = org["contacts"]
        a = await create_appt(one, org, contact_id=rao["id"])
        patch, delete = await asyncio.gather(
            one.patch(f"{APPTS}/{a['id']}", json={"contact_id": iyer["id"]}),
            two.delete(f"{ORGS}/{org['id']}/contacts/{iyer['id']}"),
        )
    assert delete.status_code == 200
    assert patch.status_code in (200, 422), patch.text  # never a 500
    row = await db_session.scalar(select(BdmAppointment).where(BdmAppointment.id == a["id"]).execution_options(populate_existing=True))
    if patch.status_code == 200:  # switched first, then the delete nulled the link and kept the Iyer snapshot
        assert row.contact_id is None and row.contact_name == "Ms Iyer"
    else:  # the delete won; the switch was refused and the booking still points at Dr Rao
        assert str(row.contact_id) == rao["id"] and row.contact_name == "Dr Rao"
```

Why `final == "cancelled"` holds in both orders: cancel first → confirm is 409; confirm first → cancel is still legal from `confirmed`.

- [ ] **Step 2: Run**

Run: `API_TEST tests/test_bdm_006_concurrency.py`
Expected: PASS. Run it three times; any 500 or deadlock is a lock-order bug to fix in the route (§5.7), not in the test.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_bdm_006_concurrency.py
git commit -m "test(bdm-006): concurrent transitions, archive vs create, contact switch vs delete" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Last / Next meeting on organizations (backend + display)

**Files:**
- Modify: `apps/api/app/services/bdm_organizations.py` (`row_out`, `organization_out`, import `meeting_columns`)
- Modify: `apps/api/app/api/bdm_organizations.py:77-84` (list statement)
- Modify: `apps/api/app/schemas.py` (the `# bdm-006 fills these; always null until then (AC6)` comment on `BdmOrganizationRow`)
- Modify: `apps/web/components/BdmOrganizationsPanel.tsx:234-235`, `apps/web/components/BdmOrganizationDetail.tsx:15,83-84`
- Test: `apps/api/tests/test_bdm_006_org_meetings.py`; `apps/web/tests/components/BdmOrganizationDetail.test.tsx`, `apps/web/tests/components/BdmOrganizationsPanel.test.tsx` (append)

**Interfaces:**
- Consumes: `svc_appt.meeting_columns()` (Task 3).
- Produces: `org_svc.row_out(user, org, assignee, primary, last_meeting_at=None, next_meeting_at=None)`; web `meetingText(v: string | null): string` exported from `lib/bdmOrganizations.ts`.

- [ ] **Step 1: Write the failing API tests**

```python
"""bdm-006 -- bdm-002's Last / Next meeting become real (AC9; spec §5.6, §12.1 R-A9)."""

import uuid

import pytest
from sqlalchemy import event

from app.core.database import engine
from tests.bdm002_helpers import ORGS, create_org
from tests.bdm006_helpers import APPTS, bdm_with_org, create_appt, future, move_to_past


@pytest.mark.asyncio
async def test_values_on_list_and_detail(client, db_session):
    _, _, org = await bdm_with_org(client, db_session)
    blank = (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]
    assert blank["last_meeting_at"] is None and blank["next_meeting_at"] is None  # bdm-002 AC6 still true without appointments
    done = await create_appt(client, org, starts_at=future(10))
    await move_to_past(db_session, done["id"], minutes=120)
    await client.post(f"{APPTS}/{done['id']}/complete", json={"outcome": "interested"})
    stale = await create_appt(client, org, starts_at=future(20))
    await move_to_past(db_session, stale["id"], minutes=30)  # open but past: not "next"
    cancelled = await create_appt(client, org, starts_at=future(30))
    await client.post(f"{APPTS}/{cancelled['id']}/cancel", json={"reason": "x"})
    upcoming = await create_appt(client, org, starts_at=future(40))
    later = await create_appt(client, org, starts_at=future(60))
    detail = (await client.get(f"{ORGS}/{org['id']}")).json()["organization"]
    done_at = (await client.get(f"{APPTS}/{done['id']}")).json()["appointment"]["starts_at"]
    assert detail["last_meeting_at"] == done_at
    assert detail["next_meeting_at"] == upcoming["starts_at"] != later["starts_at"]
    row = next(r for r in (await client.get(ORGS, params={"q": org["code"]})).json()["items"] if r["id"] == org["id"])
    assert (row["last_meeting_at"], row["next_meeting_at"]) == (detail["last_meeting_at"], detail["next_meeting_at"])


@pytest.mark.asyncio
async def test_list_query_count_does_not_grow_with_rows(client, db_session):
    await bdm_with_org(client, db_session)
    prefix = f"Meet{uuid.uuid4().hex[:6]}"
    one = await create_org(client, name=f"{prefix}A only")
    for i in range(5):
        org = await create_org(client, name=f"{prefix}B {i}")
        await create_appt(client, org, starts_at=future(10 + i))
    await create_appt(client, one, starts_at=future(30))
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731 -- (conn, cursor, statement, ...)
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        statements.clear()
        assert (await client.get(ORGS, params={"q": f"{prefix}A"})).json()["total"] == 1
        single = len(statements)
        statements.clear()
        assert (await client.get(ORGS, params={"q": f"{prefix}B"})).json()["total"] == 5
        assert len(statements) == single
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)
```

- [ ] **Step 2: Run to verify failure**

Run: `API_TEST tests/test_bdm_006_org_meetings.py`
Expected: FAIL — `last_meeting_at` is `None`.

- [ ] **Step 3: Implement the backend**

In `services/bdm_organizations.py` add `from app.services.bdm_appointments import meeting_columns` and change:

```python
def row_out(user: User, org: BdmOrganization, assignee: User, primary: BdmOrganizationContact | None, last_meeting_at=None, next_meeting_at=None) -> dict:
    return {
        # ... unchanged keys ...
        "last_meeting_at": last_meeting_at,
        "next_meeting_at": next_meeting_at,
        "permissions": permissions(user, org),
    }
```

In `organization_out`, before the return:

```python
    last_meeting_at, next_meeting_at = (await db.execute(select(*meeting_columns()).select_from(BdmOrganization).where(BdmOrganization.id == org.id))).one()
    return {
        **row_out(user, org, people[org.assigned_bdm_user_id], primary, last_meeting_at, next_meeting_at),
        # ... unchanged ...
    }
```

In `api/bdm_organizations.py` `list_organizations`:

```python
    stmt = (
        select(BdmOrganization, User, Primary, *meeting_columns())
        .join(User, User.id == BdmOrganization.assigned_bdm_user_id)
        .outerjoin(Primary, and_(Primary.organization_id == BdmOrganization.id, Primary.is_primary.is_(True)))
        .where(*filters)
    )
    rows = (await db.execute(stmt.order_by(BdmOrganization.name, BdmOrganization.id).limit(limit).offset(offset))).all()
    return {"items": [svc.row_out(user, org, assignee_, primary, last, upcoming) for org, assignee_, primary, last, upcoming in rows], "total": total or 0, "limit": limit, "offset": offset}
```

with `from app.services.bdm_appointments import meeting_columns`. Update the schema comment to `# bdm-006: computed from appointments (spec §5.6); null when none`.

Check for an import cycle: `services/bdm_appointments.py` imports only `app.models` and `app.services.bdm`, so `bdm_organizations -> bdm_appointments` is one-way.

- [ ] **Step 4: Run backend tests**

Run: `API_TEST tests/test_bdm_006_org_meetings.py tests/test_bdm_002_organizations.py tests/test_bdm_002_scope.py tests/test_bdm_002_service.py`
Expected: PASS (bdm-002 tests unchanged).

- [ ] **Step 5: Web — write the failing display tests.** Append to `BdmOrganizationDetail.test.tsx`:

```tsx
  it("shows real meeting times in IST (bdm-006 AC9)", () => {
    render(<BdmOrganizationDetail initial={org({ last_meeting_at: "2030-01-07T04:30:00Z", next_meeting_at: null })} basePath="/bdm/organizations" />);
    const details = screen.getByRole("region", { name: "Details" });
    expect(within(details).getByText("Last meeting").nextElementSibling).toHaveTextContent(/07 Jan 2030, 10:00 IST/);
    expect(within(details).getByText("Next meeting").nextElementSibling).toHaveTextContent("—");
  });
```

Append to `BdmOrganizationsPanel.test.tsx` a case that stubs `fetch` with one row whose `next_meeting_at` is `"2030-01-07T18:00:00Z"` and expects the cell text `/07 Jan 2030, 23:30 IST/` (reuse the file's existing `row()` / `page()` builders).

- [ ] **Step 6: Implement the display** — in `lib/bdmOrganizations.ts`:

```ts
import { formatSchoolDateTime } from "@/lib/formatDate";

// bdm-006: Last / Next meeting are real timestamps now -- India time, labelled, the same on server and browser (R-F10).
export function meetingText(value: string | null): string {
  return value ? formatSchoolDateTime(value, true) : "—";
}
```

Replace `display(r.last_meeting_at)` / `display(r.next_meeting_at)` in `BdmOrganizationsPanel.tsx` and `display(org.last_meeting_at)` / `display(org.next_meeting_at)` in `BdmOrganizationDetail.tsx` with `meetingText(...)`; change the detail's header comment `Last/Next meeting stay "—" until bdm-006 (AC6).` to `Last/Next meeting come from bdm-006 appointments ("—" when none).`

Confirm the exact rendered text first: run `WEB_TEST "npx vitest run tests/components/BdmOrganizationDetail.test.tsx"` and, if `formatSchoolDateTime` renders e.g. `07 Jan 2030, 10:00 IST` differently (comma / spacing), adjust the regex to the real output — the format function is existing code and is not changed.

- [ ] **Step 7: Run web tests**

Run: `WEB_TEST "npx vitest run tests/components/BdmOrganizationDetail.test.tsx tests/components/BdmOrganizationsPanel.test.tsx tests/lib/bdmOrganizations.test.ts"`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/services/bdm_organizations.py apps/api/app/api/bdm_organizations.py apps/api/app/schemas.py apps/api/tests/test_bdm_006_org_meetings.py apps/web/lib/bdmOrganizations.ts apps/web/components/BdmOrganizationsPanel.tsx apps/web/components/BdmOrganizationDetail.tsx apps/web/tests/components/BdmOrganizationDetail.test.tsx apps/web/tests/components/BdmOrganizationsPanel.test.tsx
git commit -m "feat(bdm-006): real Last/Next meeting on organizations, shown in IST" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Web library + navigation

**Files:**
- Create: `apps/web/lib/bdmAppointments.ts`
- Modify: `apps/web/lib/navigation.ts:44-47`
- Test: `apps/web/tests/lib/bdmAppointments.test.ts`; modify `apps/web/tests/lib/navigation.bdm.test.ts`

**Interfaces:**
- Consumes: `BdmType` (`lib/bdm`), `ORGS_URL`, `TEAM_URL` (`lib/bdmOrganizations`), `LookupPage` (`lib/lookups`), `SCHOOL_TIME_ZONE`, `formatSchoolDateTime` (`lib/formatDate`).
- Produces (used by Tasks 11–13): `APPOINTMENTS_URL`; `STATUSES`, `AppointmentStatus`, `STATUS_LABEL`, `STATUS_CLASS`; `TYPE_LABEL`, `ALL_TYPES`, `appointmentTypes(t)`; `OUTCOME_LABEL`, `appointmentOutcomes(t)`; `DURATIONS`; types `AppointmentPermissions`, `AppointmentRow`, `AppointmentEvent`, `Appointment`, `OverlapMatch`, `Overlap`; `overlap(detail)`, `isAppointmentBody(data)`; `isoToIstInput(iso)`, `istInputToIso(value)`, `nowIstInput()`, `todayIst()`; `formatMinutes(n)`, `whenText(startsAt, minutes)`, `formatInr(v)`; `myOrganizationSearch()`, `teamMemberSearch()`.

- [ ] **Step 1: Write the failing tests** — `apps/web/tests/lib/bdmAppointments.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import { appointmentOutcomes, appointmentTypes, formatInr, formatMinutes, isoToIstInput, istInputToIso, overlap, STATUS_LABEL, TYPE_LABEL } from "@/lib/bdmAppointments";

describe("bdmAppointments (bdm-006)", () => {
  it("lists the common types plus the module's, once each, all labelled", () => {
    expect(appointmentTypes("agent")).toHaveLength(16);
    expect(appointmentTypes("school")).toHaveLength(18);
    expect(appointmentTypes("college")).toHaveLength(19);
    for (const t of ["agent", "school", "college"] as const) {
      const types = appointmentTypes(t);
      expect(new Set(types).size).toBe(types.length);
      expect(types).toContain("seminar_workshop");
      types.forEach((key) => expect(TYPE_LABEL[key]).toBeTruthy());
    }
    expect(appointmentTypes("agent")).not.toContain("principal_meeting");
  });

  it("uses the agent outcome list only for agent BDMs", () => {
    expect(appointmentOutcomes("agent")).toContain("agreement_required");
    expect(appointmentOutcomes("college")).toContain("course_promotion_interested");
    expect(appointmentOutcomes("school")).not.toContain("agreement_required");
  });

  it("converts the datetime-local value to and from India time across midnight (Review Focus 4)", () => {
    expect(istInputToIso("2030-01-07T23:30")).toBe("2030-01-07T23:30:00+05:30");
    expect(isoToIstInput("2030-01-07T18:00:00Z")).toBe("2030-01-07T23:30");
    expect(isoToIstInput("2030-01-06T19:00:00Z")).toBe("2030-01-07T00:30");
    expect(isoToIstInput(istInputToIso("2030-03-01T00:00"))).toBe("2030-03-01T00:00");
  });

  it("parses the overlap 409 and nothing else", () => {
    const detail = { code: "possible_overlap", message: "m", total: 1, matches: [{ id: "a", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, organization_name: "St Mary" }] };
    expect(overlap(detail)?.matches[0].code).toBe("APT-000001");
    expect(overlap({ code: "possible_duplicate", matches: [] })).toBeNull();
    expect(overlap("Appointment is already cancelled")).toBeNull();
  });

  it("formats durations, money and statuses", () => {
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(90)).toBe("1 h 30 min");
    expect(formatMinutes(120)).toBe("2 h");
    expect(formatInr("25000.50")).toBe("₹25,000.50");
    expect(formatInr(null)).toBe("—");
    expect(STATUS_LABEL.no_show).toBe("No show");
  });
});
```

Update `tests/lib/navigation.bdm.test.ts` (a deliberate spec change):

```ts
    expect(BDM_NAV.map((x) => x.href)).toEqual(["/bdm/my-day", "/bdm/organizations", "/bdm/appointments", "/bdm/profile"]);
    expect(BDM_MANAGER_NAV.map((x) => x.href)).toEqual(["/bdm/manager/dashboard", "/bdm/manager/team", "/bdm/manager/organizations", "/bdm/manager/appointments"]);
```

- [ ] **Step 2: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/lib/bdmAppointments.test.ts tests/lib/navigation.bdm.test.ts"`
Expected: FAIL — cannot resolve `@/lib/bdmAppointments`; nav arrays differ.

- [ ] **Step 3: Implement** — `apps/web/lib/bdmAppointments.ts`:

```ts
import type { BdmType } from "@/lib/bdm";
import { ORGS_URL, TEAM_URL } from "@/lib/bdmOrganizations";
import { formatSchoolDateTime, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import type { LookupPage } from "@/lib/lookups";

// bdm-006 (DEC-SCOPE-063): types, catalogues and helpers for BDM appointments. The catalogues are display copies of the API's
// (models.BDM_APPOINTMENT_*); the API validates every value and `permissions` only tells the UI which actions to show.
export const APPOINTMENTS_URL = "/api/v1/bdm/appointments";
const PICKER_LIMIT = 20;

export const STATUSES = ["scheduled", "confirmed", "rescheduled", "completed", "cancelled", "no_show"] as const;
export type AppointmentStatus = (typeof STATUSES)[number];
export const STATUS_LABEL: Record<AppointmentStatus, string> = {
  scheduled: "Scheduled", confirmed: "Confirmed", rescheduled: "Rescheduled", completed: "Completed", cancelled: "Cancelled", no_show: "No show",
};
// R-F2: always text in the existing pills; colour only reinforces it.
export const STATUS_CLASS: Record<AppointmentStatus, string> = {
  scheduled: "status pending", rescheduled: "status pending", confirmed: "status", completed: "status", cancelled: "status error", no_show: "status error",
};

const COMMON_TYPES = ["college_meeting", "agent_meeting", "school_meeting", "mou_discussion", "student_institution_meeting", "seminar_workshop", "corporate_meeting", "other"];
const MODULE_TYPES: Record<BdmType, string[]> = {
  agent: ["agent_meeting", "new_agent_presentation", "product_training", "agreement_discussion", "performance_review", "agent_onboarding", "agent_visit", "commission_discussion", "business_review"],
  school: ["principal_meeting", "management_meeting", "career_guidance_presentation", "psychometric_presentation", "profile_building_presentation", "parent_orientation", "teacher_orientation", "seminar", "workshop", "mou_discussion", "renewal_meeting"],
  college: ["principal_meeting", "hod_meeting", "placement_cell_meeting", "course_promotion", "it_training_presentation", "student_seminar", "workshop", "internship_discussion", "placement_discussion", "mou_discussion", "corporate_connect", "faculty_meeting"],
};
export const TYPE_LABEL: Record<string, string> = {
  college_meeting: "College Meeting", agent_meeting: "Agent Meeting", school_meeting: "School Meeting", mou_discussion: "MoU Discussion",
  student_institution_meeting: "Student / Institution Meeting", seminar_workshop: "Seminar / Workshop", corporate_meeting: "Corporate Meeting", other: "Other",
  new_agent_presentation: "New Agent Presentation", product_training: "Product Training", agreement_discussion: "Agreement Discussion",
  performance_review: "Performance Review", agent_onboarding: "Agent Onboarding", agent_visit: "Agent Visit", commission_discussion: "Commission Discussion",
  business_review: "Business Review", principal_meeting: "Principal Meeting", management_meeting: "Management Meeting",
  career_guidance_presentation: "Career Guidance Presentation", psychometric_presentation: "Psychometric Presentation",
  profile_building_presentation: "Student Profile Building Presentation", parent_orientation: "Parent Orientation", teacher_orientation: "Teacher Orientation",
  seminar: "Seminar", workshop: "Workshop", renewal_meeting: "Renewal Meeting", hod_meeting: "HOD Meeting", placement_cell_meeting: "Placement Cell Meeting",
  course_promotion: "Course Promotion", it_training_presentation: "IT Training Presentation", student_seminar: "Student Seminar",
  internship_discussion: "Internship Discussion", placement_discussion: "Placement Discussion", corporate_connect: "Corporate Connect", faculty_meeting: "Faculty Meeting",
};
export const ALL_TYPES = Object.keys(TYPE_LABEL);
export const appointmentTypes = (t: BdmType): string[] => [...new Set([...COMMON_TYPES, ...MODULE_TYPES[t]])];

const COMMON_OUTCOMES = ["interested", "mou_discussion_required", "student_leads_expected", "course_promotion_interested", "follow_up_required", "commercial_discussion", "not_interested", "reschedule", "other"];
const AGENT_OUTCOMES = ["interested", "agreement_required", "product_training_required", "follow_up", "documents_required", "onboarding_required", "active_business_expected", "not_interested"];
export const OUTCOME_LABEL: Record<string, string> = {
  interested: "Interested", mou_discussion_required: "MoU Discussion Required", student_leads_expected: "Student Leads Expected",
  course_promotion_interested: "Course Promotion Interested", follow_up_required: "Follow-up Required", commercial_discussion: "Commercial Discussion",
  not_interested: "Not Interested", reschedule: "Reschedule", other: "Other", agreement_required: "Agreement Required",
  product_training_required: "Product Training Required", follow_up: "Follow-up", documents_required: "Documents Required",
  onboarding_required: "Onboarding Required", active_business_expected: "Active Business Expected",
};
export const appointmentOutcomes = (t: BdmType): string[] => (t === "agent" ? AGENT_OUTCOMES : COMMON_OUTCOMES);
export const DURATIONS = [15, 30, 45, 60, 90, 120, 180, 240, 360, 480, 720]; // R-F6; the API accepts any 15-720

export type AppointmentPermissions = { can_edit: boolean; can_confirm: boolean; can_reschedule: boolean; can_cancel: boolean; can_no_show: boolean; can_complete: boolean };
export type AppointmentRow = {
  id: string; code: string; starts_at: string; duration_minutes: number; appointment_type: string; status: AppointmentStatus;
  organization: { id: string; code: string; name: string; archived: boolean }; contact_name: string; bdm: { id: string; full_name: string; active: boolean };
};
export type AppointmentEvent = { from_status: AppointmentStatus | null; to_status: AppointmentStatus; old_starts_at: string | null; new_starts_at: string | null; reason: string | null; actor_name: string; created_at: string };
export type Appointment = AppointmentRow & {
  contact_id: string | null; contact_designation: string | null; contact_phone: string | null; contact_email: string | null;
  location: string | null; purpose: string | null; remarks: string | null; outcome: string | null; next_follow_up_on: string | null;
  expected_leads: number | null; expected_revenue: string | null; events: AppointmentEvent[]; permissions: AppointmentPermissions;
  created_at: string; updated_at: string;
};
export type OverlapMatch = { id: string; code: string; starts_at: string; duration_minutes: number; organization_name: string };
export type Overlap = { message: string; matches: OverlapMatch[]; total: number };

export function overlap(detail: unknown): Overlap | null {
  const d = detail as (Partial<Overlap> & { code?: string }) | null;
  if (!d || typeof d !== "object" || d.code !== "possible_overlap" || !Array.isArray(d.matches)) return null;
  return { message: String(d.message ?? ""), matches: d.matches, total: Number(d.total ?? d.matches.length) };
}

export function isAppointmentBody(data: unknown): data is { appointment: Appointment } {
  const a = (data as { appointment?: { id?: unknown } } | null)?.appointment;
  return !!a && typeof a.id === "string";
}

// India has one fixed offset (+05:30, no DST), so a datetime-local value is sent with it and read back in Asia/Kolkata.
const IST_PARTS = new Intl.DateTimeFormat("en-CA", { timeZone: SCHOOL_TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
export function isoToIstInput(iso: string): string {
  const p = Object.fromEntries(IST_PARTS.formatToParts(new Date(iso)).map((part) => [part.type, part.value]));
  return `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}`;
}
export const istInputToIso = (value: string): string => `${value}:00+05:30`;
export const nowIstInput = (): string => isoToIstInput(new Date().toISOString());
export const todayIst = (): string => nowIstInput().slice(0, 10);

export function formatMinutes(n: number): string {
  if (n < 60) return `${n} min`;
  return n % 60 ? `${Math.floor(n / 60)} h ${n % 60} min` : `${n / 60} h`;
}
export const whenText = (startsAt: string, minutes: number): string => `${formatSchoolDateTime(startsAt, true)} · ${formatMinutes(minutes)}`;
export function formatInr(value: string | null): string {
  return value === null ? "—" : `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// The booking picker: the caller's own, active organizations (assigned=me; archived are excluded by the list's default).
export function myOrganizationSearch() {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: String(PICKER_LIMIT), assigned: "me" });
    if (q) query.set("q", q);
    const response = await fetch(`${ORGS_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Organization search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; code: string; name: string; city: string }[]; total: number };
    return { items: page.items.map((o) => ({ id: o.id, label: o.name, detail: `${o.code} · ${o.city}` })), truncated: page.total > page.items.length };
  };
}

// The manager's BDM filter: their team (super_admin: everyone).
export function teamMemberSearch() {
  return async (q: string, signal: AbortSignal): Promise<LookupPage> => {
    const query = new URLSearchParams({ limit: String(PICKER_LIMIT) });
    if (q) query.set("q", q);
    const response = await fetch(`${TEAM_URL}?${query}`, { signal });
    if (!response.ok) throw new Error(`Team search failed (${response.status})`);
    const page = (await response.json()) as { items: { id: string; full_name: string; employee_id: string; bdm_type: BdmType }[]; total: number };
    return { items: page.items.map((b) => ({ id: b.id, label: b.full_name, detail: `${b.employee_id} · ${b.bdm_type}` })), truncated: page.total > page.items.length };
  };
}
```

In `lib/navigation.ts`:

```ts
// bdm-001: BDM and BDM-manager sidebars, and the signed-out chooser (College BDMs sign in at /it, Agent/School BDMs at /overseas;
// managers at /admin). bdm-002 adds Organizations to both; bdm-006 adds Appointments.
export const BDM_NAV: NavItem[] = [{ label: "My Day", href: "/bdm/my-day" }, { label: "Organizations", href: "/bdm/organizations" }, { label: "Appointments", href: "/bdm/appointments" }, { label: "Profile", href: "/bdm/profile" }];
export const BDM_MANAGER_NAV: NavItem[] = [{ label: "Dashboard", href: "/bdm/manager/dashboard" }, { label: "Team", href: "/bdm/manager/team" }, { label: "Organizations", href: "/bdm/manager/organizations" }, { label: "Appointments", href: "/bdm/manager/appointments" }];
```

`lib/bdmOrganizations.ts` gains an import from `lib/formatDate` in Task 9 and `lib/bdmAppointments.ts` imports from `lib/bdmOrganizations.ts` — one direction only, no cycle.

- [ ] **Step 4: Run to verify pass**

Run: `WEB_TEST "npx vitest run tests/lib/bdmAppointments.test.ts tests/lib/navigation.bdm.test.ts tests/components/BdmPages.test.tsx"`
Expected: PASS. If `BdmPages.test.tsx` pins nav labels, update it deliberately the same way.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/bdmAppointments.ts apps/web/lib/navigation.ts apps/web/tests/lib/bdmAppointments.test.ts apps/web/tests/lib/navigation.bdm.test.ts apps/web/tests/components/BdmPages.test.tsx
git commit -m "feat(bdm-006): web appointment library and navigation" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Appointments list panel + list pages

**Files:**
- Create: `apps/web/components/BdmAppointmentsPanel.tsx`
- Create: `apps/web/app/bdm/appointments/page.tsx`, `apps/web/app/bdm/manager/appointments/page.tsx`
- Test: `apps/web/tests/components/BdmAppointmentsPanel.test.tsx`

**Interfaces:**
- Consumes: Task 10 lib; `isPage`, `Page` (`lib/apiErrors`); `PAGE_SIZE` (`lib/bdm`); `LINK_STYLE` (`lib/bdmOrganizations`); `SearchableSelect`.
- Produces: `BdmAppointmentsPanel({ basePath, isBdm, types }: { basePath: string; isBdm: boolean; types: string[] })`.

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentsPanel from "@/components/BdmAppointmentsPanel";
import { ALL_TYPES, type AppointmentRow } from "@/lib/bdmAppointments";

const router = vi.hoisted(() => ({ push: vi.fn() }));
const search = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({ useRouter: () => router, usePathname: () => "/bdm/appointments", useSearchParams: () => new URLSearchParams(search.value) }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (over: Partial<AppointmentRow> = {}): AppointmentRow => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", bdm: { id: "b1", full_name: "Asha", active: true }, ...over,
});
const page = (items: AppointmentRow[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockClear();
  search.value = "";
});

describe("BdmAppointmentsPanel (bdm-006 §6.2, §12.2)", () => {
  it("asks for today onward by default and renders rows with IST times and text statuses", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([row(), row({ id: "a2", code: "APT-000002", status: "cancelled" })]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    expect(await screen.findByRole("link", { name: "APT-000001" })).toHaveAttribute("href", "/bdm/appointments/a1");
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/date_from=\d{4}-\d{2}-\d{2}/);
    expect(screen.getByText(/07 Jan 2030, 10:00 IST/)).toBeInTheDocument();
    expect(screen.getByText("Cancelled")).toHaveClass("status", "error");
    expect(screen.queryByRole("columnheader", { name: "BDM" })).toBeNull();
  });

  it("shows the BDM empty state with a booking link", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    expect(await screen.findByText("No appointments yet.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Book appointment" })[0]).toHaveAttribute("href", "/bdm/appointments/new");
  });

  it("shows the manager empty state, a BDM column and no booking link", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />);
    expect(await screen.findByText("Your team has no appointments in this period.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Book appointment" })).toBeNull();
  });

  it("distinguishes no-match and past-the-end, and retries after a failure", async () => {
    search.value = "status=cancelled";
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([])));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No appointments match these filters.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(router.push).toHaveBeenCalledWith("/bdm/appointments", { scroll: false });
  });

  it("pushes filter changes into the URL", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([row()])))));
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    await screen.findByRole("link", { name: "APT-000001" });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "confirmed" } });
    expect(router.push).toHaveBeenLastCalledWith("/bdm/appointments?status=confirmed", { scroll: false });
  });

  it("shows an organization filter chip from the URL", async () => {
    search.value = "organization=o1";
    const fetchMock = vi.fn(() => Promise.resolve(res(page([row()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={ALL_TYPES} />);
    await screen.findByRole("link", { name: "APT-000001" });
    expect(String(fetchMock.mock.calls[0][0])).toContain("organization_id=o1");
    expect(screen.getByText("Showing one organization")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/components/BdmAppointmentsPanel.test.tsx"`
Expected: FAIL — cannot resolve `@/components/BdmAppointmentsPanel`.

- [ ] **Step 3: Implement** — `apps/web/components/BdmAppointmentsPanel.tsx`:

```tsx
"use client";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { isPage, type Page } from "@/lib/apiErrors";
import { PAGE_SIZE } from "@/lib/bdm";
import { APPOINTMENTS_URL, type AppointmentRow, STATUS_CLASS, STATUS_LABEL, STATUSES, teamMemberSearch, todayIst, TYPE_LABEL, whenText } from "@/lib/bdmAppointments";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

// bdm-006 (spec §6.2, §12.2): a BDM's own appointments or a manager's team's. The API scopes the rows; nothing here filters for
// security. Filters and the page live in the URL (BdmOrganizationsPanel's pattern); "From" defaults to today in India time, and an
// empty "From" in the URL (date_from=) means every date.
type Filters = { offset: number; q: string; dateFrom: string; dateTo: string; status: string; type: string; organization: string; bdm: string };

function readFilters(params: URLSearchParams, today: string): Filters {
  const n = Number.parseInt(params.get("offset") ?? "", 10);
  return {
    offset: Number.isFinite(n) && n > 0 ? n : 0,
    q: (params.get("q") ?? "").trim(),
    dateFrom: params.has("date_from") ? params.get("date_from") ?? "" : today,
    dateTo: params.get("date_to") ?? "",
    status: params.get("status") ?? "",
    type: params.get("type") ?? "",
    organization: params.get("organization") ?? "",
    bdm: params.get("bdm") ?? "",
  };
}

function toUrl(f: Filters, today: string): URLSearchParams {
  const next = new URLSearchParams();
  if (f.offset > 0) next.set("offset", String(f.offset));
  if (f.q) next.set("q", f.q);
  if (f.dateFrom !== today) next.set("date_from", f.dateFrom);
  if (f.dateTo) next.set("date_to", f.dateTo);
  if (f.status) next.set("status", f.status);
  if (f.type) next.set("type", f.type);
  if (f.organization) next.set("organization", f.organization);
  if (f.bdm) next.set("bdm", f.bdm);
  return next;
}

function toApi(f: Filters): string {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(f.offset) });
  if (f.q) query.set("q", f.q);
  if (f.dateFrom) query.set("date_from", f.dateFrom);
  if (f.dateTo) query.set("date_to", f.dateTo);
  if (f.status) query.set("status", f.status);
  if (f.type) query.set("appointment_type", f.type);
  if (f.organization) query.set("organization_id", f.organization);
  if (f.bdm) query.set("bdm_user_id", f.bdm);
  return `${APPOINTMENTS_URL}?${query}`;
}

export default function BdmAppointmentsPanel({ basePath, isBdm, types }: { basePath: string; isBdm: boolean; types: string[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [today] = useState(todayIst);
  const filters = readFilters(params, today);
  const key = toUrl(filters, today).toString();
  const [data, setData] = useState<Page<AppointmentRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [fetching, setFetching] = useState(true);
  const [target, setTarget] = useState<string | null>(null);
  const loading = fetching || (target !== null && target !== key);
  const [version, setVersion] = useState(0);
  const [draftQ, setDraftQ] = useState(filters.q);

  useEffect(() => setDraftQ(filters.q), [filters.q]);

  useEffect(() => {
    let live = true;
    setLoadFailed(false);
    setFetching(true);
    setTarget(null);
    fetch(toApi(readFilters(new URLSearchParams(key), today)))
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<AppointmentRow>(body)) throw new Error("not a page");
        if (live) setData(body);
      })
      .catch(() => live && setLoadFailed(true))
      .finally(() => live && setFetching(false));
    return () => {
      live = false;
    };
  }, [key, version, today]);

  function go(next: Partial<Filters>) {
    const url = toUrl({ ...filters, offset: 0, ...next }, today);
    setTarget(url.toString());
    router.push(url.size ? `${pathname}?${url}` : pathname, { scroll: false });
  }
  const clear = () => go({ q: "", dateFrom: today, dateTo: "", status: "", type: "", organization: "", bdm: "" });
  const filtered = Boolean(filters.q || filters.dateTo || filters.status || filters.type || filters.organization || filters.bdm || filters.dateFrom !== today);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    go({ q: draftQ.trim() });
  };
  const book = isBdm && (
    <Link className="btn small" href={`${basePath}/new`}>
      Book appointment
    </Link>
  );

  return (
    <div className="action-card wide" aria-busy={loading && !loadFailed}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", justifyContent: "space-between" }}>
        <h3>Appointments</h3>
        {book}
      </div>
      <form role="search" aria-label="Filter appointments" onSubmit={submit} style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
        <div className="field" style={{ flex: "1 1 180px", margin: 0 }}>
          <label htmlFor="appt-filter-q">Code or organization</label>
          <input id="appt-filter-q" type="search" value={draftQ} maxLength={200} onChange={(e) => setDraftQ(e.target.value)} />
        </div>
        <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
          <label htmlFor="appt-filter-from">From (IST)</label>
          <input id="appt-filter-from" type="date" value={filters.dateFrom} onChange={(e) => go({ dateFrom: e.target.value })} />
        </div>
        <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
          <label htmlFor="appt-filter-to">To (IST)</label>
          <input id="appt-filter-to" type="date" value={filters.dateTo} min={filters.dateFrom || undefined} onChange={(e) => go({ dateTo: e.target.value })} />
        </div>
        <div className="field" style={{ flex: "0 1 160px", margin: 0 }}>
          <label htmlFor="appt-filter-status">Status</label>
          <select id="appt-filter-status" value={filters.status} onChange={(e) => go({ status: e.target.value })}>
            <option value="">All statuses</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </div>
        <div className="field" style={{ flex: "0 1 200px", margin: 0 }}>
          <label htmlFor="appt-filter-type">Type</label>
          <select id="appt-filter-type" value={filters.type} onChange={(e) => go({ type: e.target.value })}>
            <option value="">All types</option>
            {types.map((t) => (
              <option key={t} value={t}>
                {TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        {!isBdm && (
          <div style={{ flex: "1 1 220px" }}>
            <SearchableSelect label="BDM" noun="BDM" search={teamMemberSearch()} onChange={(option) => option && go({ bdm: option.id })} />
          </div>
        )}
        <button type="submit" className="btn secondary small">
          Search
        </button>
        {filtered && (
          <button type="button" className="btn secondary small" onClick={clear}>
            Clear filters
          </button>
        )}
      </form>
      {(filters.organization || filters.bdm) && (
        <p className="muted" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", margin: "8px 0 0" }}>
          {filters.organization && <span className="badge">Showing one organization</span>}
          {filters.bdm && <span className="badge">Showing one BDM</span>}
          <button type="button" className="btn secondary small" onClick={() => go({ organization: "", bdm: "" })}>
            Show all
          </button>
        </p>
      )}
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">
            Unable to load appointments.
          </p>
          <button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>
            Retry
          </button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">
          Loading appointments…
        </p>
      ) : data.total === 0 ? (
        filtered ? (
          <div role="status">
            <p className="empty">No appointments match these filters.</p>
            <button type="button" className="btn secondary small" onClick={clear}>
              Clear filters
            </button>
          </div>
        ) : (
          <div role="status">
            <p className="empty">{isBdm ? "No appointments yet." : "Your team has no appointments in this period."}</p>
            {book}
          </div>
        )
      ) : data.items.length === 0 ? (
        <>
          <p className="empty" role="status">
            This page is past the end of the list.
          </p>
          <button type="button" className="btn secondary small" onClick={() => go({})}>
            Go to the first page
          </button>
        </>
      ) : (
        <>
          {loading && (
            <p className="muted" role="status" style={{ margin: 0 }}>
              Updating appointments…
            </p>
          )}
          <div className="table-wrap" role="region" aria-label="Appointments" tabIndex={0} style={loading ? { opacity: 0.6 } : undefined}>
            <table style={{ overflowWrap: "anywhere" }}>
              <thead>
                <tr>
                  <th scope="col">Code</th>
                  <th scope="col">Date &amp; time</th>
                  <th scope="col">Organization</th>
                  <th scope="col">Contact</th>
                  <th scope="col">Type</th>
                  <th scope="col">Status</th>
                  {!isBdm && <th scope="col">BDM</th>}
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <Link href={`${basePath}/${r.id}`} style={LINK_STYLE}>
                        {r.code}
                      </Link>
                    </td>
                    <td style={{ minWidth: 150 }}>{whenText(r.starts_at, r.duration_minutes)}</td>
                    <td style={{ minWidth: 140 }}>
                      {r.organization.name}
                      {r.organization.archived && (
                        <>
                          {" "}
                          <span className="badge">Archived</span>
                        </>
                      )}
                    </td>
                    <td>{r.contact_name}</td>
                    <td>{TYPE_LABEL[r.appointment_type] ?? r.appointment_type}</td>
                    <td>
                      <span className={STATUS_CLASS[r.status]}>{STATUS_LABEL[r.status]}</span>
                    </td>
                    {!isBdm && (
                      <td>
                        {r.bdm.full_name}
                        {!r.bdm.active && <span className="muted"> (inactive)</span>}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Appointment pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" disabled={data.offset === 0} onClick={() => go({ offset: Math.max(0, filters.offset - PAGE_SIZE) })}>
                Previous
              </button>
              <button type="button" className="btn secondary small" disabled={data.offset + data.items.length >= data.total} onClick={() => go({ offset: filters.offset + PAGE_SIZE })}>
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
```

The component is ~240 lines, mirroring `BdmOrganizationsPanel` (258 lines) — the established size for a list panel; splitting it would scatter one URL-state machine across files. If review asks, extract the `<table>` into `BdmAppointmentsTable`.

- [ ] **Step 4: Pages** — `apps/web/app/bdm/appointments/page.tsx`:

```tsx
import { Suspense } from "react";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentsPanel from "@/components/BdmAppointmentsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import { appointmentTypes } from "@/lib/bdmAppointments";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-006: the BDM's own appointments (A3). The API is the gate.
export default async function BdmAppointmentsPage() {
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  const type = me.bdm_profile.bdm_type;
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Appointments</div>
            <h2>Your appointments</h2>
            <p className="muted">Times are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading appointments…</p>}>
          <BdmAppointmentsPanel basePath="/bdm/appointments" isBdm types={appointmentTypes(type)} />
        </Suspense>
      </div>
    </PortalShell>
  );
}
```

`apps/web/app/bdm/manager/appointments/page.tsx`:

```tsx
import { Suspense } from "react";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentsPanel from "@/components/BdmAppointmentsPanel";
import PortalShell from "@/components/PortalShell";
import { serverApi } from "@/lib/api";
import { ALL_TYPES } from "@/lib/bdmAppointments";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-006 (A3): the appointments of this manager's team (super_admin: all), read-only.
export default async function BdmManagerAppointmentsPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Appointments</div>
            <h2>Your team&apos;s appointments</h2>
            <p className="muted">Read-only. Times are India time (IST).</p>
          </div>
        </div>
        <Suspense fallback={<p className="muted" role="status">Loading appointments…</p>}>
          <BdmAppointmentsPanel basePath="/bdm/manager/appointments" isBdm={false} types={ALL_TYPES} />
        </Suspense>
      </div>
    </PortalShell>
  );
}
```

- [ ] **Step 5: Run to verify pass**

Run: `WEB_TEST "npx vitest run tests/components/BdmAppointmentsPanel.test.tsx"`
Expected: PASS. Adjust only the IST text regex if `formatSchoolDateTime`'s real output differs (see Task 9 Step 6).

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/BdmAppointmentsPanel.tsx apps/web/app/bdm/appointments/page.tsx apps/web/app/bdm/manager/appointments/page.tsx apps/web/tests/components/BdmAppointmentsPanel.test.tsx
git commit -m "feat(bdm-006): appointment list panel and pages" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: Booking / edit form, overlap alert, new page

**Files:**
- Create: `apps/web/components/BdmOverlapAlert.tsx`, `apps/web/components/BdmAppointmentFields.tsx`, `apps/web/components/BdmAppointmentForm.tsx`
- Create: `apps/web/app/bdm/appointments/new/page.tsx`
- Test: `apps/web/tests/components/BdmAppointmentForm.test.tsx`

**Interfaces:**
- Consumes: Task 10 lib; `sendJson`, `NOT_COMPLETED` (`lib/apiErrors`); `ORGS_URL`, `type Organization`, `type OrgContact` (`lib/bdmOrganizations`); `FormMessage`, `type FormMessageState`; `SearchableSelect`; `useFocusAfterRender`.
- Produces:
  - `BdmOverlapAlert({ overlap, busy, onConfirm, onCancel })` (reused by Task 13's reschedule form)
  - `BdmAppointmentFields({ values, set, bdmType, contacts, contactsLoading })` with `type FieldValues = { contactId: string; when: string; duration: number; type: string; location: string; purpose: string; remarks: string; leads: string; revenue: string }`
  - `BdmAppointmentForm(props: { mode: "create"; bdmType: BdmType; initialOrganization: Organization | null } | { mode: "edit"; bdmType: BdmType; appointment: Appointment; onSaved: (a: Appointment, saved: boolean) => void; onCancel: () => void })`

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import type { Appointment } from "@/lib/bdmAppointments";
import type { Organization } from "@/lib/bdmOrganizations";

const router = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const org = { id: "o1", code: "ORG-000001", name: "St Mary", contacts: [
  { id: "c1", name: "Ms Iyer", designation: null, role: null, phone: null, email: null, is_primary: false },
  { id: "c2", name: "Dr Rao", designation: "Principal", role: "principal", phone: null, email: null, is_primary: true },
] } as unknown as Organization;
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", contact_id: "c2", bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: "Principal", contact_phone: null, contact_email: null, location: "Gate 1", purpose: null, remarks: null, outcome: null, next_follow_up_on: null,
  expected_leads: null, expected_revenue: null, events: [], created_at: "", updated_at: "",
  permissions: { can_edit: true, can_confirm: true, can_reschedule: true, can_cancel: true, can_no_show: false, can_complete: false }, ...over,
}) as Appointment;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockClear();
});

function fillWhen(value = "2030-01-07T10:00") {
  fireEvent.change(screen.getByLabelText("Date and time (IST) (required)"), { target: { value } });
}

describe("BdmAppointmentForm (bdm-006 §6.2, R-F6)", () => {
  it("preselects the primary contact, lists the BDM type's types, and books in IST", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt() }, 201)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    expect(screen.getByLabelText("Contact person (required)")).toHaveValue("c2");
    const types = Array.from((screen.getByLabelText("Type (required)") as HTMLSelectElement).options).map((o) => o.value);
    expect(types).toContain("placement_discussion");
    expect(types).not.toContain("agent_visit");
    fillWhen();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/bdm/appointments/a1?created=1"));
    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown[])[1] && ((fetchMock.mock.calls[0] as unknown[])[1] as RequestInit).body));
    expect(body).toMatchObject({ organization_id: "o1", contact_id: "c2", starts_at: "2030-01-07T10:00:00+05:30", duration_minutes: 60, confirm_overlap: false });
    expect(body.expected_leads).toBeNull();
  });

  it("warns on overlap, then saves anyway with confirm_overlap", async () => {
    const detail = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail }, 409)).mockResolvedValueOnce(res({ appointment: appt() }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("APT-000009");
    expect(alert).toHaveTextContent("Holy Cross");
    expect(screen.getByRole("button", { name: "Book appointment" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(JSON.parse(String(((fetchMock.mock.calls[1] as unknown[])[1] as RequestInit).body)).confirm_overlap).toBe(true);
  });

  it("keeps the entry and shows the API message on failure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "This organization is archived — restore it before booking" }, 422))));
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} />);
    fillWhen();
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Main block" } });
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("archived");
    expect(screen.getByLabelText("Location")).toHaveValue("Main block");
  });

  it("edit sends only changed fields and reports no-change", async () => {
    const onSaved = vi.fn();
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.includes("/organizations/") ? res({ organization: org }) : res({ appointment: appt({ location: "Gate 2" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt()} onSaved={onSaved} onCancel={() => {}} />);
    await screen.findByDisplayValue("Dr Rao");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: "a1" }), false));
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Gate 2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenLastCalledWith(expect.objectContaining({ location: "Gate 2" }), true));
    const patch = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "PATCH");
    expect(JSON.parse(String((patch![1] as RequestInit).body))).toEqual({ location: "Gate 2" });
  });

  it("asks for a new contact when the booked one was deleted", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ organization: org }))));
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt({ contact_id: null })} onSaved={() => {}} onCancel={() => {}} />);
    expect(await screen.findByText(/The booked contact \(Dr Rao\) was removed/)).toBeInTheDocument();
  });
});
```

`screen.findByDisplayValue("Dr Rao")` targets the selected `<option>` text of the contact select; if Testing Library does not match option text, wait on `await waitFor(() => expect(screen.getByLabelText("Contact person (required)")).toHaveValue("c2"))` instead.

- [ ] **Step 2: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/components/BdmAppointmentForm.test.tsx"`
Expected: FAIL — cannot resolve `@/components/BdmAppointmentForm`.

- [ ] **Step 3: Implement `BdmOverlapAlert.tsx`**

```tsx
"use client";
import { useEffect, useRef } from "react";

import { type Overlap, whenText } from "@/lib/bdmAppointments";

// bdm-006 (A6, R-F7): the overlap warning, the bdm-002 duplicate-alert pattern. The matches are plain text (no links), so following one
// cannot lose the unsaved entry. Focus moves to the heading so a screen reader announces it.
export default function BdmOverlapAlert({ overlap, busy, onConfirm, onCancel }: { overlap: Overlap; busy: boolean; onConfirm: () => void; onCancel: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => heading.current?.focus(), []);
  return (
    <div role="alert" className="action-card" onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <h4 ref={heading} tabIndex={-1} style={{ margin: "0 0 8px" }}>
        {overlap.message}
      </h4>
      <ul style={{ margin: "0 0 12px", paddingLeft: 18 }}>
        {overlap.matches.map((m) => (
          <li key={m.id}>
            {m.code} · {whenText(m.starts_at, m.duration_minutes)} · {m.organization_name}
          </li>
        ))}
      </ul>
      {overlap.total > overlap.matches.length && <p className="muted">and {overlap.total - overlap.matches.length} more.</p>}
      <div className="actions">
        <button type="button" className="btn small" onClick={onConfirm} disabled={busy}>
          {busy ? "Saving…" : "Save anyway"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `BdmAppointmentFields.tsx`**

```tsx
"use client";
import type { BdmType } from "@/lib/bdm";
import { appointmentTypes, DURATIONS, formatMinutes, nowIstInput, TYPE_LABEL } from "@/lib/bdmAppointments";
import type { OrgContact } from "@/lib/bdmOrganizations";

// bdm-006 (R-F6): the booking fields in four fieldsets. Presentational: the form owns the state and the submit.
export type FieldValues = { contactId: string; when: string; duration: number; type: string; location: string; purpose: string; remarks: string; leads: string; revenue: string };

export default function BdmAppointmentFields({
  values,
  set,
  bdmType,
  contacts,
  contactsLoading,
  showWhen,
}: {
  values: FieldValues;
  set: <K extends keyof FieldValues>(key: K, value: FieldValues[K]) => void;
  bdmType: BdmType;
  contacts: OrgContact[] | null;
  contactsLoading: boolean;
  showWhen: boolean;
}) {
  return (
    <>
      <fieldset className="field">
        <legend>Who</legend>
        <label htmlFor="appt-contact">Contact person (required)</label>
        <select id="appt-contact" required aria-required="true" value={values.contactId} disabled={contactsLoading || !contacts} onChange={(e) => set("contactId", e.target.value)}>
          {contactsLoading ? <option value="">Loading contacts…</option> : <option value="">Choose a contact</option>}
          {(contacts ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
              {c.designation ? ` — ${c.designation}` : ""}
            </option>
          ))}
        </select>
      </fieldset>
      <fieldset className="field">
        <legend>When</legend>
        {showWhen && (
          <>
            <label htmlFor="appt-when">Date and time (IST) (required)</label>
            <input id="appt-when" type="datetime-local" required aria-required="true" min={nowIstInput()} value={values.when} onChange={(e) => set("when", e.target.value)} />
          </>
        )}
        <label htmlFor="appt-duration">Duration</label>
        <select id="appt-duration" value={values.duration} onChange={(e) => set("duration", Number(e.target.value))}>
          {(DURATIONS.includes(values.duration) ? DURATIONS : [...DURATIONS, values.duration].sort((a, b) => a - b)).map((d) => (
            <option key={d} value={d}>
              {formatMinutes(d)}
            </option>
          ))}
        </select>
      </fieldset>
      <fieldset className="field">
        <legend>Details</legend>
        <label htmlFor="appt-type">Type (required)</label>
        <select id="appt-type" required aria-required="true" value={values.type} onChange={(e) => set("type", e.target.value)}>
          <option value="">Choose a type</option>
          {appointmentTypes(bdmType).map((t) => (
            <option key={t} value={t}>
              {TYPE_LABEL[t]}
            </option>
          ))}
        </select>
        <label htmlFor="appt-location">Location</label>
        <input id="appt-location" maxLength={255} value={values.location} onChange={(e) => set("location", e.target.value)} />
        <label htmlFor="appt-purpose">Purpose</label>
        <textarea id="appt-purpose" maxLength={1000} rows={2} value={values.purpose} onChange={(e) => set("purpose", e.target.value)} />
        <label htmlFor="appt-remarks">Remarks</label>
        <textarea id="appt-remarks" maxLength={2000} rows={2} value={values.remarks} onChange={(e) => set("remarks", e.target.value)} />
      </fieldset>
      <fieldset className="field">
        <legend>Estimates</legend>
        <label htmlFor="appt-leads">Expected leads</label>
        <input id="appt-leads" type="number" inputMode="numeric" min={0} step={1} value={values.leads} onChange={(e) => set("leads", e.target.value)} />
        <label htmlFor="appt-revenue">Expected revenue (INR)</label>
        <input id="appt-revenue" type="number" inputMode="decimal" min={0} step={0.01} value={values.revenue} onChange={(e) => set("revenue", e.target.value)} />
      </fieldset>
    </>
  );
}
```

- [ ] **Step 5: Implement `BdmAppointmentForm.tsx`**

```tsx
"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useState } from "react";

import BdmAppointmentFields, { type FieldValues } from "@/components/BdmAppointmentFields";
import BdmOverlapAlert from "@/components/BdmOverlapAlert";
import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, isoToIstInput, istInputToIso, myOrganizationSearch, type Overlap, overlap as readOverlap } from "@/lib/bdmAppointments";
import { isOrganizationBody, LINK_STYLE, type OrgContact, type Organization, ORGS_URL } from "@/lib/bdmOrganizations";

// bdm-006 (spec §6.2, R-F3-R-F6): book an appointment (create) or edit an open one (edit: no time -- that is Reschedule). The API
// decides every rule; this form keeps the entry on any failure and moves focus to the message.
type Props =
  | { mode: "create"; bdmType: BdmType; initialOrganization: Organization | null }
  | { mode: "edit"; bdmType: BdmType; appointment: Appointment; onSaved: (a: Appointment, saved: boolean) => void; onCancel: () => void };

const primaryOf = (contacts: OrgContact[]) => (contacts.find((c) => c.is_primary) ?? contacts[0])?.id ?? "";
const text = (v: string | null) => v ?? "";
const orNull = (v: string) => (v.trim() === "" ? null : v.trim());

function initialValues(props: Props): FieldValues {
  if (props.mode === "edit") {
    const a = props.appointment;
    return {
      contactId: a.contact_id ?? "", when: isoToIstInput(a.starts_at), duration: a.duration_minutes, type: a.appointment_type, location: text(a.location),
      purpose: text(a.purpose), remarks: text(a.remarks), leads: a.expected_leads === null ? "" : String(a.expected_leads), revenue: text(a.expected_revenue),
    };
  }
  return { contactId: primaryOf(props.initialOrganization?.contacts ?? []), when: "", duration: 60, type: "", location: "", purpose: "", remarks: "", leads: "", revenue: "" };
}

export default function BdmAppointmentForm(props: Props) {
  const router = useRouter();
  const editing = props.mode === "edit" ? props.appointment : null;
  const [orgId, setOrgId] = useState(editing?.organization.id ?? (props.mode === "create" ? props.initialOrganization?.id ?? "" : ""));
  const [contacts, setContacts] = useState<OrgContact[] | null>(props.mode === "create" ? props.initialOrganization?.contacts ?? null : null);
  const [contactsLoading, setContactsLoading] = useState(props.mode === "edit");
  const [values, setValues] = useState<FieldValues>(() => initialValues(props));
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [warning, setWarning] = useState<Overlap | null>(null);
  const set = <K extends keyof FieldValues>(key: K, value: FieldValues[K]) => setValues((v) => ({ ...v, [key]: value }));

  async function loadContacts(id: string, keepChoice: boolean) {
    setContactsLoading(true);
    const response = await fetch(`${ORGS_URL}/${id}`).catch(() => null);
    const body = response?.ok ? await response.json().catch(() => null) : null;
    setContactsLoading(false);
    if (!isOrganizationBody(body)) return setMessage({ text: "Unable to load this organization's contacts.", failed: true });
    setContacts(body.organization.contacts);
    if (!keepChoice) set("contactId", primaryOf(body.organization.contacts));
  }
  useEffect(() => {
    if (editing) void loadContacts(editing.organization.id, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once, for the appointment being edited
  }, []);

  function changedFields(a: Appointment): Record<string, unknown> {
    const next: Record<string, unknown> = {
      contact_id: values.contactId || a.contact_id, duration_minutes: values.duration, appointment_type: values.type,
      location: orNull(values.location), purpose: orNull(values.purpose), remarks: orNull(values.remarks),
      expected_leads: values.leads === "" ? null : Number(values.leads), expected_revenue: orNull(values.revenue),
    };
    const before: Record<string, unknown> = {
      contact_id: a.contact_id, duration_minutes: a.duration_minutes, appointment_type: a.appointment_type, location: a.location, purpose: a.purpose,
      remarks: a.remarks, expected_leads: a.expected_leads, expected_revenue: a.expected_revenue === null ? null : String(Number(a.expected_revenue)),
    };
    if (next.expected_revenue !== null) next.expected_revenue = String(Number(next.expected_revenue));
    return Object.fromEntries(Object.entries(next).filter(([k, v]) => v !== before[k]));
  }

  async function submit(confirmOverlap = false) {
    setMessage(null);
    if (editing) {
      const body = changedFields(editing);
      if (!Object.keys(body).length) return props.mode === "edit" && props.onSaved(editing, false);
      setBusy(true);
      const outcome = await sendJson(`${APPOINTMENTS_URL}/${editing.id}`, "PATCH", confirmOverlap ? { ...body, confirm_overlap: true } : body);
      setBusy(false);
      return handle(outcome, (a) => props.mode === "edit" && props.onSaved(a, true));
    }
    setBusy(true);
    const outcome = await sendJson(APPOINTMENTS_URL, "POST", {
      organization_id: orgId, contact_id: values.contactId, starts_at: istInputToIso(values.when), duration_minutes: values.duration, appointment_type: values.type,
      location: orNull(values.location), purpose: orNull(values.purpose), remarks: orNull(values.remarks),
      expected_leads: values.leads === "" ? null : Number(values.leads), expected_revenue: orNull(values.revenue), confirm_overlap: confirmOverlap,
    });
    setBusy(false);
    handle(outcome, (a) => router.push(`/bdm/appointments/${a.id}?created=1`));
  }

  function handle(outcome: Awaited<ReturnType<typeof sendJson>>, onOk: (a: Appointment) => void) {
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setWarning(null);
      return onOk(outcome.data.appointment);
    }
    if (!outcome.ok && outcome.status === 409) {
      const clash = readOverlap(outcome.detail);
      if (clash) return setWarning(clash);
    }
    setWarning(null);
    setMessage({ text: outcome.ok ? "Unable to save this appointment." : outcome.message, failed: true });
  }

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submit(false);
  };
  const deletedContact = editing && editing.contact_id === null && !values.contactId;

  return (
    <form onSubmit={onSubmit} aria-label={editing ? "Edit appointment" : "Book appointment"}>
      {!editing && (
        <SearchableSelect
          label="Organization (required)"
          noun="organization"
          required
          search={myOrganizationSearch()}
          initial={props.mode === "create" && props.initialOrganization ? { id: props.initialOrganization.id, label: props.initialOrganization.name, detail: props.initialOrganization.code } : null}
          onChange={(option) => {
            setOrgId(option?.id ?? "");
            setContacts(null);
            set("contactId", "");
            if (option) void loadContacts(option.id, false);
          }}
        />
      )}
      {!editing && (
        <p className="muted" style={{ marginTop: 4 }}>
          Only organizations assigned to you can be booked.{" "}
          <Link href="/bdm/organizations" style={LINK_STYLE}>
            Open organizations
          </Link>
        </p>
      )}
      {deletedContact && (
        <p className="muted" role="note">
          The booked contact ({editing.contact_name}) was removed from the organization. Choose another contact to change it, or leave it as recorded.
        </p>
      )}
      <BdmAppointmentFields values={values} set={set} bdmType={props.bdmType} contacts={contacts} contactsLoading={contactsLoading} showWhen={!editing} />
      {warning && <BdmOverlapAlert overlap={warning} busy={busy} onConfirm={() => void submit(true)} onCancel={() => setWarning(null)} />}
      {message && <FormMessage message={message} />}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy || warning !== null || (!editing && (!orgId || !values.contactId))}>
          {busy ? "Saving…" : editing ? "Save changes" : "Book appointment"}
        </button>
        {editing && props.mode === "edit" && (
          <button type="button" className="btn secondary" onClick={props.onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
```

Also in this step, in `components/SearchableSelect.tsx`: add `"organization"` to the `Noun` union and `organization: "organizations"` to `PLURAL` — a one-line additive change, as bdm-002 added `"BDM"`. With no assigned organizations the picker shows its own "No organizations found", and the static hint under it points to Organizations (R-F5) — no new prop on the shared component.

The deleted-contact case: `values.contactId` starts as `""`, so `changedFields` falls back to `a.contact_id` (null) and sends no contact change unless one is chosen.

- [ ] **Step 6: New page** — `apps/web/app/bdm/appointments/new/page.tsx`:

```tsx
import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import type { Organization } from "@/lib/bdmOrganizations";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-006: book an appointment. `?organization=<id>` (from the organization page) preselects it; an unknown, out-of-scope or archived
// organization is simply not preselected -- the API refuses archived ones with its own message (A4).
export default async function BdmAppointmentNewPage({ searchParams }: { searchParams: Promise<{ organization?: string }> }) {
  const { organization: orgParam } = await searchParams;
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  let organization: Organization | null = null;
  if (orgParam) {
    try {
      const found = (await serverApi<{ organization: Organization }>(`/api/v1/bdm/organizations/${encodeURIComponent(orgParam)}`)).organization;
      organization = found.assigned_bdm.id === me.id && !found.archived ? found : null;
    } catch (e) {
      if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, BDM_SIGN_IN);
    }
  }
  const type = me.bdm_profile.bdm_type;
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        <div className="portal-title">
          <div>
            <div className="eyebrow">Appointments</div>
            <h2>Book appointment</h2>
            <p className="muted">Times are India time (IST). You can book for organizations assigned to you.</p>
          </div>
        </div>
        <div className="action-card wide">
          <BdmAppointmentForm mode="create" bdmType={type} initialOrganization={organization} />
        </div>
      </div>
    </PortalShell>
  );
}
```

- [ ] **Step 7: Run to verify pass**

Run: `WEB_TEST "npx vitest run tests/components/BdmAppointmentForm.test.tsx tests/components/SearchableSelect.test.tsx"`
Expected: PASS (the `SearchableSelect` suite still green after the additive `Noun`).

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/BdmOverlapAlert.tsx apps/web/components/BdmAppointmentFields.tsx apps/web/components/BdmAppointmentForm.tsx apps/web/components/SearchableSelect.tsx apps/web/app/bdm/appointments/new/page.tsx apps/web/tests/components/BdmAppointmentForm.test.tsx
git commit -m "feat(bdm-006): booking and edit form with overlap warning" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Detail view — details, actions, history; detail pages; "Add appointment" on the organization

**Files:**
- Create: `apps/web/components/BdmAppointmentReasonForm.tsx`, `BdmAppointmentRescheduleForm.tsx`, `BdmAppointmentCompleteForm.tsx`, `BdmAppointmentActions.tsx`, `BdmAppointmentHistory.tsx`, `BdmAppointmentDetail.tsx` (all in `apps/web/components/`)
- Create: `apps/web/app/bdm/appointments/[id]/page.tsx`, `apps/web/app/bdm/manager/appointments/[id]/page.tsx`
- Modify: `apps/web/components/BdmOrganizationDetail.tsx` (header actions)
- Test: `apps/web/tests/components/BdmAppointmentDetail.test.tsx`, `BdmAppointmentActions.test.tsx`, `BdmAppointmentHistory.test.tsx`; append to `BdmOrganizationDetail.test.tsx`

**Interfaces:**
- Consumes: Task 10 lib; Task 12 `BdmAppointmentForm` (edit mode) and `BdmOverlapAlert`; `sendJson`; `useFocusAfterRender`; `formatSchoolDateTime`, `formatDate`; `display`, `LINK_STYLE`.
- Produces:
  - `BdmAppointmentReasonForm({ label, submitText, busyText, busy, onSubmit: (reason: string) => void, onCancel })`
  - `BdmAppointmentRescheduleForm({ appointment, busy, warning, onSubmit: (body: { starts_at: string; duration_minutes: number; reason: string | null }, confirm: boolean) => void, onCancel })`
  - `BdmAppointmentCompleteForm({ bdmType, busy, onSubmit: (body: { outcome: string; next_follow_up_on: string | null }) => void, onCancel })`
  - `BdmAppointmentActions({ appointment, bdmType, onChanged: (a: Appointment, text: string) => void })`
  - `BdmAppointmentHistory({ events })`
  - `BdmAppointmentDetail({ initial, basePath, bdmType, created }: { initial: Appointment; basePath: string; bdmType: BdmType | null; created?: boolean })`

- [ ] **Step 1: Write the failing tests**

`tests/components/BdmAppointmentActions.test.tsx`:

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentActions from "@/components/BdmAppointmentActions";
import type { Appointment, AppointmentPermissions } from "@/lib/bdmAppointments";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const none: AppointmentPermissions = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false };
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", contact_id: "c1", bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: null, contact_phone: null, contact_email: null, location: null, purpose: null, remarks: null, outcome: null, next_follow_up_on: null,
  expected_leads: null, expected_revenue: null, events: [], created_at: "", updated_at: "", permissions: none, ...over,
}) as Appointment;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmAppointmentActions (bdm-006 §6.2, R-F4, R-F7)", () => {
  it("renders nothing without permissions (managers, closed appointments)", () => {
    const { container } = render(<BdmAppointmentActions appointment={appt()} bdmType="college" onChanged={() => {}} />);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("confirms in one click and re-renders from the response", async () => {
    const onChanged = vi.fn();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "confirmed" }) }))));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_confirm: true } })} bdmType="college" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "confirmed" }), "Appointment confirmed."));
  });

  it("requires a reason to cancel; Escape closes and returns focus", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "cancelled" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_cancel: true } })} bdmType="college" onChanged={() => {}} />);
    const trigger = screen.getByRole("button", { name: "Cancel appointment" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect(screen.getByText("Enter a reason.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByLabelText("Reason (required)"), { key: "Escape" });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel appointment" })));
  });

  it("on a 409 refetches and says what the appointment became", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "Appointment is already cancelled" }, 409)).mockResolvedValueOnce(res({ appointment: appt({ status: "cancelled" }) }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_confirm: true } })} bdmType="college" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }), "This appointment changed — it is now Cancelled."));
  });

  it("completes with an outcome from the BDM type's list", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "completed", outcome: "agreement_required" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="agent" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    const outcomes = Array.from((screen.getByLabelText("Outcome (required)") as HTMLSelectElement).options).map((o) => o.value);
    expect(outcomes).toContain("agreement_required");
    expect(outcomes).not.toContain("course_promotion_interested");
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "agreement_required" } });
    fireEvent.click(screen.getByRole("button", { name: "Mark completed" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(((fetchMock.mock.calls[0] as unknown[])[1] as RequestInit).body))).toEqual({ outcome: "agreement_required", next_follow_up_on: null });
  });

  it("shows the overlap warning inside Reschedule and confirms past it", async () => {
    const detail = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-08T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail }, 409)).mockResolvedValueOnce(res({ appointment: appt({ status: "rescheduled" }) }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_reschedule: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-08T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new time" }));
    expect(await screen.findByText(/APT-000009/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(((fetchMock.mock.calls[1] as unknown[])[1] as RequestInit).body))).toMatchObject({ starts_at: "2030-01-08T10:00:00+05:30", confirm_overlap: true });
  });
});
```

`tests/components/BdmAppointmentDetail.test.tsx`:

```tsx
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import type { Appointment } from "@/lib/bdmAppointments";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
const none = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false };
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 90, appointment_type: "placement_discussion", status: "completed",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: true }, contact_name: "Dr Rao", contact_id: null, bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: "Principal", contact_phone: "+91 90000 00000", contact_email: "rao@x.edu", location: "<b>Main</b>", purpose: "Tie-up", remarks: null,
  outcome: "student_leads_expected", next_follow_up_on: "2030-01-10", expected_leads: 12, expected_revenue: "25000.50",
  events: [{ from_status: null, to_status: "scheduled", old_starts_at: null, new_starts_at: null, reason: null, actor_name: "Asha", created_at: "2030-01-01T04:30:00Z" }],
  created_at: "", updated_at: "", permissions: none, ...over,
}) as Appointment;
afterEach(cleanup);

describe("BdmAppointmentDetail (bdm-006 AC1, R-F1, R-F2, R-F12)", () => {
  it("shows every section 2 field, the outcome, and plain text only", () => {
    render(<BdmAppointmentDetail initial={appt()} basePath="/bdm/manager/appointments" bdmType={null} />);
    const details = screen.getByRole("region", { name: "Details" });
    const value = (label: string) => within(details).getByText(label).nextElementSibling;
    expect(value("Date & time")).toHaveTextContent(/07 Jan 2030, 10:00 IST · 1 h 30 min/);
    expect(value("Contact person")).toHaveTextContent("Dr Rao");
    expect(value("Mobile")).toHaveTextContent("+91 90000 00000");
    expect(value("Type")).toHaveTextContent("Placement Discussion");
    expect(value("Location")).toHaveTextContent("<b>Main</b>");
    expect(value("Expected revenue")).toHaveTextContent("₹25,000.50");
    expect(value("Remarks")).toHaveTextContent("—");
    expect(screen.getByRole("region", { name: "Outcome" })).toHaveTextContent("Student Leads Expected");
    expect(screen.getByText("Completed")).toHaveClass("status");
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/manager/organizations/o1");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("link", { name: /rao@x\.edu/ })).toBeNull();
  });

  it("hints when the start has passed and shows the booked notice once", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    render(<BdmAppointmentDetail initial={appt({ status: "confirmed", outcome: null, next_follow_up_on: null, permissions: { ...none, can_complete: true, can_no_show: true } })} basePath="/bdm/appointments" bdmType="college" created />);
    expect(screen.getByRole("note")).toHaveTextContent("The start time has passed — complete it or mark it as a no-show.");
    expect(screen.getByRole("status")).toHaveTextContent("Appointment APT-000001 booked.");
    expect(replace).toHaveBeenCalledWith(null, "", "/bdm/appointments/a1");
  });
});
```

`tests/components/BdmAppointmentHistory.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import BdmAppointmentHistory from "@/components/BdmAppointmentHistory";

afterEach(cleanup);

it("lists booking, transitions, the old and new time, and reasons in order (AC3, AC4)", () => {
  render(
    <BdmAppointmentHistory
      events={[
        { from_status: null, to_status: "scheduled", old_starts_at: null, new_starts_at: null, reason: null, actor_name: "Asha", created_at: "2030-01-01T04:30:00Z" },
        { from_status: "scheduled", to_status: "rescheduled", old_starts_at: "2030-01-07T04:30:00Z", new_starts_at: "2030-01-08T05:30:00Z", reason: "Principal travelling", actor_name: "Asha", created_at: "2030-01-02T04:30:00Z" },
      ]}
    />,
  );
  const items = screen.getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Booked");
  expect(items[1]).toHaveTextContent("Scheduled → Rescheduled");
  expect(items[1]).toHaveTextContent(/from 07 Jan 2030, 10:00 IST to 08 Jan 2030, 11:00 IST/);
  expect(items[1]).toHaveTextContent("Reason: Principal travelling");
});
```

Append to `BdmOrganizationDetail.test.tsx`:

```tsx
  it("offers Add appointment only to the assigned BDM on the BDM portal", () => {
    const { unmount } = render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/organizations" />);
    expect(screen.getByRole("link", { name: "Add appointment" })).toHaveAttribute("href", "/bdm/appointments/new?organization=o1");
    unmount();
    render(<BdmOrganizationDetail initial={org({ permissions: perms({ can_edit: true }) })} basePath="/bdm/manager/organizations" />);
    expect(screen.queryByRole("link", { name: "Add appointment" })).toBeNull();
  });
```

- [ ] **Step 2: Run to verify failure**

Run: `WEB_TEST "npx vitest run tests/components/BdmAppointmentActions.test.tsx tests/components/BdmAppointmentDetail.test.tsx tests/components/BdmAppointmentHistory.test.tsx tests/components/BdmOrganizationDetail.test.tsx"`
Expected: FAIL — modules not found; the organization link test fails.

- [ ] **Step 3: `BdmAppointmentReasonForm.tsx`**

```tsx
"use client";
import { type FormEvent, useId, useState } from "react";

// bdm-006 (A2, R-F6, R-F7): the reason a cancel or no-show needs. The textarea takes focus; Escape cancels; an empty reason is caught here
// as well as by the API (422).
export default function BdmAppointmentReasonForm({ label, submitText, busyText, busy, onSubmit, onCancel }: { label: string; submitText: string; busyText: string; busy: boolean; onSubmit: (reason: string) => void; onCancel: () => void }) {
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const id = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!reason.trim()) return setMissing(true);
    onSubmit(reason.trim());
  };
  return (
    <form aria-label={label} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={id}>Reason (required)</label>
        <textarea id={id} autoFocus required aria-required="true" maxLength={500} rows={3} value={reason} aria-invalid={missing} aria-describedby={`${id}-hint`} onChange={(e) => { setReason(e.target.value); setMissing(false); }} />
        <p id={`${id}-hint`} className={missing ? "form-error" : "muted"} style={{ margin: 0 }}>
          {missing ? "Enter a reason." : `${reason.length}/500`}
        </p>
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>
          {busy ? busyText : submitText}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Keep it
        </button>
      </div>
    </form>
  );
}
```

`noValidate` makes the client "Enter a reason." message (not the browser bubble) show for an empty reason; the API still refuses it (422).

- [ ] **Step 4: `BdmAppointmentRescheduleForm.tsx`**

```tsx
"use client";
import { type FormEvent, useState } from "react";

import BdmOverlapAlert from "@/components/BdmOverlapAlert";
import { type Appointment, DURATIONS, formatMinutes, isoToIstInput, istInputToIso, nowIstInput, type Overlap } from "@/lib/bdmAppointments";

type Body = { starts_at: string; duration_minutes: number; reason: string | null };

// bdm-006 (AC4): a new future time (IST), optionally a new duration and a reason. The old time is kept in the history by the API.
export default function BdmAppointmentRescheduleForm({ appointment, busy, warning, onSubmit, onCancel }: { appointment: Appointment; busy: boolean; warning: Overlap | null; onSubmit: (body: Body, confirm: boolean) => void; onCancel: () => void }) {
  const [when, setWhen] = useState(isoToIstInput(appointment.starts_at));
  const [duration, setDuration] = useState(appointment.duration_minutes);
  const [reason, setReason] = useState("");
  const body = (): Body => ({ starts_at: istInputToIso(when), duration_minutes: duration, reason: reason.trim() || null });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(body(), false);
  };
  const durations = DURATIONS.includes(duration) ? DURATIONS : [...DURATIONS, duration].sort((a, b) => a - b);
  return (
    <form aria-label="Reschedule appointment" className="action-card" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={`resched-${appointment.id}`}>New date and time (IST) (required)</label>
        <input id={`resched-${appointment.id}`} type="datetime-local" autoFocus required aria-required="true" min={nowIstInput()} value={when} onChange={(e) => setWhen(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor={`resched-dur-${appointment.id}`}>Duration</label>
        <select id={`resched-dur-${appointment.id}`} value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
          {durations.map((d) => (
            <option key={d} value={d}>
              {formatMinutes(d)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={`resched-why-${appointment.id}`}>Reason</label>
        <textarea id={`resched-why-${appointment.id}`} maxLength={500} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
      </div>
      {warning && <BdmOverlapAlert overlap={warning} busy={busy} onConfirm={() => onSubmit(body(), true)} onCancel={onCancel} />}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || warning !== null}>
          {busy ? "Saving…" : "Save new time"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 5: `BdmAppointmentCompleteForm.tsx`**

```tsx
"use client";
import { type FormEvent, useState } from "react";

import type { BdmType } from "@/lib/bdm";
import { appointmentOutcomes, OUTCOME_LABEL, todayIst } from "@/lib/bdmAppointments";

// bdm-006 (A1, A8): the minimal outcome Completed requires, from the BDM type's list, and an optional next follow-up date (today or later,
// India calendar). bdm-007 adds the full meeting report.
export default function BdmAppointmentCompleteForm({ bdmType, busy, onSubmit, onCancel }: { bdmType: BdmType; busy: boolean; onSubmit: (body: { outcome: string; next_follow_up_on: string | null }) => void; onCancel: () => void }) {
  const [outcome, setOutcome] = useState("");
  const [followUp, setFollowUp] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (outcome) onSubmit({ outcome, next_follow_up_on: followUp || null });
  };
  return (
    <form aria-label="Complete appointment" className="action-card" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor="complete-outcome">Outcome (required)</label>
        <select id="complete-outcome" autoFocus required aria-required="true" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
          <option value="">Choose an outcome</option>
          {appointmentOutcomes(bdmType).map((o) => (
            <option key={o} value={o}>
              {OUTCOME_LABEL[o]}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="complete-follow-up">Next follow-up (IST date)</label>
        <input id="complete-follow-up" type="date" min={todayIst()} value={followUp} onChange={(e) => setFollowUp(e.target.value)} />
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !outcome}>
          {busy ? "Saving…" : "Mark completed"}
        </button>
        <button type="button" className="btn secondary small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 6: `BdmAppointmentActions.tsx`**

```tsx
"use client";
import { useState } from "react";

import BdmAppointmentCompleteForm from "@/components/BdmAppointmentCompleteForm";
import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import BdmAppointmentRescheduleForm from "@/components/BdmAppointmentRescheduleForm";
import { sendJson } from "@/lib/apiErrors";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, APPOINTMENTS_URL, isAppointmentBody, type Overlap, overlap as readOverlap, STATUS_LABEL } from "@/lib/bdmAppointments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Group = "reschedule" | "cancel" | "no_show" | "complete";
const DONE: Record<string, string> = { confirm: "Appointment confirmed.", reschedule: "Appointment rescheduled.", cancel: "Appointment cancelled.", "no-show": "Marked as a no-show.", complete: "Appointment completed." };

// bdm-006 (spec §6.2, R-F4, R-F7): the status actions, from `permissions` only (the API enforces every rule). One inline group is open
// at a time; Escape or Cancel closes it and focus returns to its button. A 409 means the appointment changed elsewhere: refetch and say so.
export default function BdmAppointmentActions({ appointment, bdmType, onChanged }: { appointment: Appointment; bdmType: BdmType | null; onChanged: (a: Appointment, text: string) => void }) {
  const [open, setOpen] = useState<Group | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [warning, setWarning] = useState<Overlap | null>(null);
  const focus = useFocusAfterRender();
  const p = appointment.permissions;
  const buttonId = (g: string) => `appt-${appointment.id}-${g}`;
  if (!Object.values(p).some(Boolean)) return null;

  const close = (g: Group) => {
    setOpen(null);
    setWarning(null);
    focus(buttonId(g));
  };
  async function refetch(): Promise<Appointment | null> {
    const response = await fetch(`${APPOINTMENTS_URL}/${appointment.id}`).catch(() => null);
    const body = response?.ok ? await response.json().catch(() => null) : null;
    return isAppointmentBody(body) ? body.appointment : null;
  }
  async function act(path: string, body: Record<string, unknown> = {}) {
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(`${APPOINTMENTS_URL}/${appointment.id}/${path}`, "POST", body);
    setBusy(false);
    if (outcome.ok && isAppointmentBody(outcome.data)) {
      setOpen(null);
      setWarning(null);
      return onChanged(outcome.data.appointment, DONE[path]);
    }
    if (!outcome.ok && outcome.status === 409) {
      const clash = readOverlap(outcome.detail);
      if (clash) return setWarning(clash);
      const fresh = await refetch();
      if (fresh) {
        setOpen(null);
        return onChanged(fresh, `This appointment changed — it is now ${STATUS_LABEL[fresh.status]}.`);
      }
    }
    setFailure(outcome.ok ? "Unable to update this appointment." : outcome.message);
  }
  const toggle = (g: Group) => {
    setFailure(null);
    setWarning(null);
    setOpen(open === g ? null : g);
  };

  return (
    <section className="action-card wide" aria-label="Actions">
      <div className="actions">
        {p.can_confirm && (
          <button id={buttonId("confirm")} type="button" className="btn small" disabled={busy} onClick={() => void act("confirm")}>
            {busy && !open ? "Confirming…" : "Confirm"}
          </button>
        )}
        {p.can_reschedule && (
          <button id={buttonId("reschedule")} type="button" className="btn secondary small" aria-expanded={open === "reschedule"} onClick={() => toggle("reschedule")}>
            Reschedule
          </button>
        )}
        {p.can_complete && bdmType && (
          <button id={buttonId("complete")} type="button" className="btn secondary small" aria-expanded={open === "complete"} onClick={() => toggle("complete")}>
            Complete
          </button>
        )}
        {p.can_no_show && (
          <button id={buttonId("no_show")} type="button" className="btn secondary small" aria-expanded={open === "no_show"} onClick={() => toggle("no_show")}>
            Mark no-show
          </button>
        )}
        {p.can_cancel && (
          <button id={buttonId("cancel")} type="button" className="btn secondary small" aria-expanded={open === "cancel"} onClick={() => toggle("cancel")}>
            Cancel appointment
          </button>
        )}
      </div>
      {open === "reschedule" && (
        <BdmAppointmentRescheduleForm appointment={appointment} busy={busy} warning={warning} onSubmit={(body, confirm) => void act("reschedule", { ...body, confirm_overlap: confirm })} onCancel={() => close("reschedule")} />
      )}
      {open === "complete" && bdmType && <BdmAppointmentCompleteForm bdmType={bdmType} busy={busy} onSubmit={(body) => void act("complete", body)} onCancel={() => close("complete")} />}
      {open === "cancel" && <BdmAppointmentReasonForm label="Cancel appointment" submitText="Yes, cancel it" busyText="Cancelling…" busy={busy} onSubmit={(reason) => void act("cancel", { reason })} onCancel={() => close("cancel")} />}
      {open === "no_show" && <BdmAppointmentReasonForm label="Mark as no-show" submitText="Mark no-show" busyText="Saving…" busy={busy} onSubmit={(reason) => void act("no-show", { reason })} onCancel={() => close("no_show")} />}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
    </section>
  );
}
```

- [ ] **Step 7: `BdmAppointmentHistory.tsx`**

```tsx
import { type AppointmentEvent, STATUS_LABEL } from "@/lib/bdmAppointments";
import { formatSchoolDateTime } from "@/lib/formatDate";

// bdm-006 (AC3, AC4): every transition in order, with who, when, the old and new time of a reschedule and any reason. Uses the existing
// journey-timeline styles (.jtl). Plain text only (R-F12).
export default function BdmAppointmentHistory({ events }: { events: AppointmentEvent[] }) {
  return (
    <section className="action-card wide" aria-label="History">
      <h3>History</h3>
      <ol className="jtl" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {events.map((e, i) => (
          <li key={`${e.created_at}-${i}`} className="jtl-row">
            <div className="jtl-rail" aria-hidden="true">
              <span className="jtl-node" />
            </div>
            <div>
              <span className="jtl-date">{formatSchoolDateTime(e.created_at, true)}</span>
              <p className="jtl-title">{e.from_status ? `${STATUS_LABEL[e.from_status]} → ${STATUS_LABEL[e.to_status]}` : "Booked"}</p>
              <p className="jtl-detail">
                By {e.actor_name}
                {e.old_starts_at && e.new_starts_at && ` · moved from ${formatSchoolDateTime(e.old_starts_at, true)} to ${formatSchoolDateTime(e.new_starts_at, true)}`}
              </p>
              {e.reason && <p className="jtl-detail">Reason: {e.reason}</p>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
```

- [ ] **Step 8: `BdmAppointmentDetail.tsx`**

```tsx
"use client";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import BdmAppointmentActions from "@/components/BdmAppointmentActions";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import BdmAppointmentHistory from "@/components/BdmAppointmentHistory";
import type { BdmType } from "@/lib/bdm";
import { type Appointment, formatInr, OUTCOME_LABEL, STATUS_CLASS, STATUS_LABEL, TYPE_LABEL, whenText } from "@/lib/bdmAppointments";
import { display, LINK_STYLE } from "@/lib/bdmOrganizations";
import { formatDate } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

function Rows({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(120px, max-content) 1fr", gap: "8px 16px", margin: 0 }}>
      {rows.map(([label, value]) => [
        <dt key={`${label}-t`} className="muted">
          {label}
        </dt>,
        <dd key={`${label}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>
          {value}
        </dd>,
      ])}
    </dl>
  );
}

// bdm-006 (spec §6.2, §12.2): one appointment. Every write re-renders from the appointment the API returns. Actions render from
// `permissions` only; a manager (bdmType null) sees no actions.
export default function BdmAppointmentDetail({ initial, basePath, bdmType, created = false }: { initial: Appointment; basePath: string; bdmType: BdmType | null; created?: boolean }) {
  const [appt, setAppt] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<string | null>(created ? `Appointment ${initial.code} booked.` : null);
  const focus = useFocusAfterRender();
  const statusId = `appt-${appt.id}-status`;
  const editId = `appt-${appt.id}-edit`;
  useEffect(() => {
    if (created) window.history.replaceState(null, "", `${basePath}/${initial.id}`);
  }, [created, basePath, initial.id]);
  const orgHref = `${basePath.startsWith("/bdm/manager") ? "/bdm/manager/organizations" : "/bdm/organizations"}/${appt.organization.id}`;
  const changed = (next: Appointment, text: string) => {
    setAppt(next);
    setNotice(text);
    focus(statusId);
  };
  const p = appt.permissions;
  const showEditor = editing && p.can_edit && bdmType;

  const rows: [string, ReactNode][] = [
    ["Date & time", whenText(appt.starts_at, appt.duration_minutes)],
    ["Organization", <Link key="org" href={orgHref} style={LINK_STYLE}>{appt.organization.name}</Link>],
    ["Contact person", appt.contact_name],
    ["Designation", display(appt.contact_designation)],
    ["Mobile", display(appt.contact_phone)],
    ["Email", display(appt.contact_email)],
    ["Type", TYPE_LABEL[appt.appointment_type] ?? appt.appointment_type],
    ["Location", display(appt.location)],
    ["Purpose", display(appt.purpose)],
    ["Remarks", display(appt.remarks)],
    ["Expected leads", display(appt.expected_leads)],
    ["Expected revenue", formatInr(appt.expected_revenue)],
    ["BDM", `${appt.bdm.full_name}${appt.bdm.active ? "" : " (inactive)"}`],
  ];

  return (
    <>
      <div className="portal-title" style={{ flexWrap: "wrap", gap: 12 }}>
        <div>
          <div className="eyebrow">
            {appt.code} · {TYPE_LABEL[appt.appointment_type] ?? appt.appointment_type}
          </div>
          <h2>
            {appt.organization.name} <span className={STATUS_CLASS[appt.status]}>{STATUS_LABEL[appt.status]}</span>{" "}
            {appt.organization.archived && <span className="badge">Archived</span>}
          </h2>
          <p style={{ margin: 0 }}>
            <Link href={basePath} style={LINK_STYLE}>
              Back to appointments
            </Link>
          </p>
        </div>
        <div className="actions">
          {p.can_edit && bdmType && !showEditor && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </div>
      </div>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>
        {notice}
      </div>
      {p.can_complete && (
        <p className="muted" role="note">
          The start time has passed — complete it or mark it as a no-show.
        </p>
      )}
      {showEditor ? (
        <section className="action-card wide" aria-label="Edit details">
          <h3>Edit details</h3>
          <BdmAppointmentForm
            mode="edit"
            bdmType={bdmType}
            appointment={appt}
            onSaved={(a, saved) => {
              setEditing(false);
              changed(a, saved ? "Changes saved." : "No changes to save.");
            }}
            onCancel={() => {
              setEditing(false);
              focus(editId);
            }}
          />
        </section>
      ) : (
        <section className="action-card wide" aria-label="Details">
          <h3>Details</h3>
          <Rows rows={rows} />
        </section>
      )}
      {appt.status === "completed" && (
        <section className="action-card wide" aria-label="Outcome">
          <h3>Outcome</h3>
          <Rows rows={[["Outcome", OUTCOME_LABEL[appt.outcome ?? ""] ?? display(appt.outcome)], ["Next follow-up", appt.next_follow_up_on ? formatDate(appt.next_follow_up_on) : "—"]]} />
        </section>
      )}
      {!showEditor && <BdmAppointmentActions appointment={appt} bdmType={bdmType} onChanged={changed} />}
      <BdmAppointmentHistory events={appt.events} />
    </>
  );
}
```

`formatDate("2030-01-10")` parses a date-only string as UTC midnight, which renders as 10 Jan in IST and UTC — safe for a date. If the detail test shows a one-day shift in the container's zone, pass `SCHOOL_TIME_ZONE` as `formatDate`'s third argument.

- [ ] **Step 9: Detail pages** — `apps/web/app/bdm/appointments/[id]/page.tsx`:

```tsx
import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { BDM_TYPE_LABEL, type BdmMe } from "@/lib/bdm";
import type { Appointment } from "@/lib/bdmAppointments";
import { BDM_NAV, BDM_SIGN_IN } from "@/lib/navigation";

// bdm-006: one appointment. A 404 (unknown or not the BDM's) is a plain "not found" -- it never says which.
export default async function BdmAppointmentPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ created?: string }> }) {
  const { id } = await params;
  const created = (await searchParams).created === "1";
  let me: BdmMe;
  try {
    me = await serverApi<BdmMe>("/api/v1/bdm/me");
  } catch (e) {
    return accessUnavailable(e, BDM_SIGN_IN);
  }
  let appointment: Appointment | null = null;
  try {
    appointment = (await serverApi<{ appointment: Appointment }>(`/api/v1/bdm/appointments/${encodeURIComponent(id)}`)).appointment;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, BDM_SIGN_IN);
  }
  return (
    <PortalShell nav={BDM_NAV} roleLabel={`${BDM_TYPE_LABEL[me.bdm_profile.bdm_type]} BDM`} userName={me.full_name}>
      <div className="portal-content">
        {appointment ? (
          <BdmAppointmentDetail initial={appointment} basePath="/bdm/appointments" bdmType={me.bdm_profile.bdm_type} created={created} />
        ) : (
          <div className="action-card">
            <h2>Appointment not found</h2>
            <p>
              <Link href="/bdm/appointments">Back to appointments</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
```

`apps/web/app/bdm/manager/appointments/[id]/page.tsx`:

```tsx
import Link from "next/link";

import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { Appointment } from "@/lib/bdmAppointments";
import { BDM_MANAGER_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-006 (A3): one team appointment, read-only (the API returns all-false permissions for managers and super_admin).
export default async function BdmManagerAppointmentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  if (user.role !== "bdm_manager" && user.role !== "super_admin") return accessDenied(user, "This page is for BDM managers.");
  let appointment: Appointment | null = null;
  try {
    appointment = (await serverApi<{ appointment: Appointment }>(`/api/v1/bdm/appointments/${encodeURIComponent(id)}`)).appointment;
  } catch (e) {
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) return accessUnavailable(e, "/admin/login");
  }
  return (
    <PortalShell nav={BDM_MANAGER_NAV} roleLabel={user.role === "super_admin" ? "Super Admin" : "BDM Manager"} userName={user.full_name}>
      <div className="portal-content">
        {appointment ? (
          <BdmAppointmentDetail initial={appointment} basePath="/bdm/manager/appointments" bdmType={null} />
        ) : (
          <div className="action-card">
            <h2>Appointment not found</h2>
            <p>
              <Link href="/bdm/manager/appointments">Back to appointments</Link>
            </p>
          </div>
        )}
      </div>
    </PortalShell>
  );
}
```

- [ ] **Step 10: "Add appointment" on the organization** — in `BdmOrganizationDetail.tsx`, inside `<div className="actions">`, first child:

```tsx
          {basePath === "/bdm/organizations" && p.can_edit && !showEditor && ( // bdm-006: the assigned BDM, not archived (A3, A4)
            <Link className="btn small" href={`/bdm/appointments/new?organization=${org.id}`}>
              Add appointment
            </Link>
          )}
```

`can_edit` is true only for the assigned BDM (or super_admin, who uses the manager portal's `basePath`) on a non-archived organization, which is exactly who may book.

- [ ] **Step 11: Run to verify pass**

Run: `WEB_TEST "npx vitest run tests/components/BdmAppointmentActions.test.tsx tests/components/BdmAppointmentDetail.test.tsx tests/components/BdmAppointmentHistory.test.tsx tests/components/BdmOrganizationDetail.test.tsx tests/components/BdmAppointmentForm.test.tsx"`
Expected: PASS.

- [ ] **Step 12: Type-check, lint, build**

Run: `WEB_TEST "npx tsc --noEmit && npx eslint app components lib tests && npx next build"`
Expected: no errors. Fix types (not by `any` or suppressions) if any appear.

- [ ] **Step 13: Commit**

```bash
git add apps/web/components/BdmAppointment*.tsx apps/web/components/BdmOrganizationDetail.tsx "apps/web/app/bdm/appointments/[id]/page.tsx" "apps/web/app/bdm/manager/appointments/[id]/page.tsx" apps/web/tests/components/BdmAppointment*.test.tsx apps/web/tests/components/BdmOrganizationDetail.test.tsx
git commit -m "feat(bdm-006): appointment detail with actions and history; Add appointment on organizations" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: End-to-end journey, documentation, lite verification

**Files:**
- Create: `apps/web/tests/e2e/bdm-006-appointments.spec.ts`
- Create: `docs/quality/BDM-006_BROWSER_QA_2026-10-03.md` (after browser QA)
- Modify: `docs/architecture/DATA_MODEL.md`, `docs/architecture/API_CONTRACT.md`, `docs/architecture/RBAC_MATRIX.md` (§2.13), `docs/quality/RTM.md`, `docs/ux/ROLE_NAVIGATION.md`, `docs/delivery/BDM_CRM_BACKLOG.md` (status line), `docs/superpowers/specs/2026-10-03-bdm-006-appointments-design.md` (refinements)

**Interfaces:** Consumes the whole feature. Produces release evidence.

- [ ] **Step 1: Write the e2e spec**

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// bdm-006 (AC1-AC7): a College BDM books from the organization page, confirms, reschedules (the history keeps the old time), waits for
// the start time and completes with an outcome; an archived organization offers no booking; the manager sees the appointment read-only;
// the list fits a phone. The API never accepts a past start (A7), so the journey books ~2 minutes ahead and waits (plan refinement 4).

async function superAdmin(page: Page) {
  await page.goto("/admin/login");
  await page.fill("#login-email", "superadmin@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/admin");
}

async function signIn(page: Page, portal: "it" | "admin", email: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/${portal}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

/** A datetime-local value in IST `minutes` after the next whole minute, and that instant in ms. */
function istSlot(minutes: number): { input: string; at: number } {
  const at = Math.ceil(Date.now() / 60_000) * 60_000 + minutes * 60_000;
  return { input: new Date(at + 330 * 60_000).toISOString().slice(0, 16), at };
}

test("BDM appointments: book, confirm, reschedule, complete; archived org; manager read-only", async ({ page }) => {
  test.setTimeout(300_000); // includes waiting for the start time to pass
  const stamp = Date.now();
  await superAdmin(page);
  const manager = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm_manager", division: "global", full_name: `E2E Manager ${stamp}`, email: `bdm006-m-${stamp}@example.local` },
  })).json();
  const bdm = await (await page.request.post("/api/v1/admin/users", {
    data: { role: "bdm", full_name: `E2E BDM ${stamp}`, email: `bdm006-b-${stamp}@example.local`, bdm_profile: { bdm_type: "college", employee_id: `E2E6-${stamp}`, reporting_manager_user_id: manager.id } },
  })).json();
  for (const account of [manager, bdm]) await activateWithToken(page.request, account.development_welcome_token);

  await signIn(page, "it", bdm.email, "/bdm/my-day");
  const newOrg = async (name: string) =>
    (await (await page.request.post("/api/v1/bdm/organizations", { data: { org_type: "college", name, city: "Kochi", contacts: [{ name: "Dr Rao", designation: "Principal", is_primary: true }] } })).json()).organization;
  const org = await newOrg(`E2E College ${stamp}`);
  const archived = await newOrg(`E2E Closed ${stamp}`);
  await page.request.post(`/api/v1/bdm/organizations/${archived.id}/archive`);

  // AC1: book from the organization page.
  await page.goto(`/bdm/organizations/${org.id}`);
  await page.getByRole("link", { name: "Add appointment" }).click();
  await page.waitForURL(`**/bdm/appointments/new?organization=${org.id}`);
  await expect(page.getByLabel("Contact person (required)")).toHaveValue(org.contacts[0].id);
  const first = istSlot(2);
  await page.getByLabel("Date and time (IST) (required)").fill(first.input);
  await page.getByLabel("Type (required)").selectOption("college_meeting");
  await page.getByLabel("Location").fill("Main block");
  await page.getByRole("button", { name: "Book appointment" }).click();
  await page.waitForURL(/\/bdm\/appointments\/[0-9a-f-]{36}$/);
  await expect(page.getByRole("status").first()).toContainText("booked");
  await expect(page.getByText("Scheduled", { exact: true })).toBeVisible();

  // AC3: confirm, then AC4: reschedule one minute later; the history keeps the old time.
  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Confirmed", { exact: true })).toBeVisible();
  const second = istSlot(3);
  await page.getByRole("button", { name: "Reschedule" }).click();
  await page.getByLabel("New date and time (IST) (required)").fill(second.input);
  await page.getByRole("button", { name: "Save new time" }).click();
  await expect(page.getByText("Rescheduled", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("region", { name: "History" })).toContainText("moved from");

  // AC5: after the start time, complete with an outcome.
  await page.waitForTimeout(Math.max(0, second.at - Date.now() + 2_000));
  await page.reload();
  await expect(page.getByRole("note")).toContainText("The start time has passed");
  await page.getByRole("button", { name: "Complete" }).click();
  await page.getByLabel("Outcome (required)").selectOption("interested");
  await page.getByRole("button", { name: "Mark completed" }).click();
  await expect(page.getByRole("region", { name: "Outcome" })).toContainText("Interested");
  const code = (await page.locator(".eyebrow").first().textContent())?.split(" · ")[0] ?? "";

  // AC6: an archived organization offers no booking.
  await page.goto(`/bdm/organizations/${archived.id}`);
  await expect(page.getByRole("link", { name: "Add appointment" })).toHaveCount(0);

  // Phone width: no horizontal page scroll on the list (R-F8).
  await page.setViewportSize({ width: 375, height: 800 });
  await page.goto("/bdm/appointments?date_from=");
  await expect(page.getByRole("link", { name: code })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
  await page.setViewportSize({ width: 1280, height: 800 });

  // AC7: the manager reads it, with no actions.
  await signIn(page, "admin", manager.email, "/bdm/manager/dashboard");
  await page.goto("/bdm/manager/appointments?date_from=");
  await page.getByRole("link", { name: code }).click();
  await expect(page.getByRole("region", { name: "History" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Confirm|Reschedule|Complete|Cancel appointment|Edit/ })).toHaveCount(0);
});
```

- [ ] **Step 2: Run the e2e journeys** (the owner starts the worktree stack; seed is additive: `docker compose -p bdm006 -f docker-compose.yml exec -T api python -m app.seed`)

Run: `MSYS_NO_PATHCONV=1 docker compose -p bdm006 -f docker-compose.yml -f docker-compose.ci.yml --profile ci run --rm --no-deps -e E2E_BASE_URL=http://host.docker.internal:<web port> -v "$WT/apps/web:/app" -v /app/node_modules web-test sh -c "npx playwright test tests/e2e/bdm-001-bdm-profile.spec.ts tests/e2e/bdm-002-organization-crm.spec.ts tests/e2e/bdm-006-appointments.spec.ts"`
Expected: 3 passed. On failure, open only that test's trace.

- [ ] **Step 3: Documentation**
  - `DATA_MODEL.md`: a `bdm_appointments` / `bdm_appointment_events` section copied from spec §4.2–4.3 (columns, CHECKs, indexes, FK rules incl. `contact_id ON DELETE SET NULL`), citing `DEC-SCOPE-063`.
  - `API_CONTRACT.md`: one row per route from spec §5.3 (auth: authenticated; roles; status codes from §5.8), and an addendum on `GET /bdm/organizations` + `{id}`: "`last_meeting_at` / `next_meeting_at` now computed (bdm-006, spec §5.6)".
  - `RBAC_MATRIX.md` §2.13: rows for `bdm` (own appointments; book only on assigned, non-archived organizations), `bdm_manager` (team read-only), `super_admin` (all, read-only), `it_admin` / `overseas_admin` (none, 403).
  - `RTM.md`: AC1–AC10 → test files and test names (Tasks 4–9, 11–14).
  - `ROLE_NAVIGATION.md`: Appointments entries in both BDM sidebars.
  - `BDM_CRM_BACKLOG.md`: replace the in-progress status line with "COMPLETE for its scope" + evidence (filled in Step 5).
  - Spec: add a "Revision 3 — plan refinements" note listing refinements 1–3 from this plan's header and 4: the e2e books ~2 minutes ahead and waits instead of moving `starts_at` (the e2e container has no database access; the backend tests move it).

- [ ] **Step 4: Lite verification** (the owner runs the full suites)

```bash
API_TEST tests/test_bdm_006_migration.py tests/test_bdm_006_schemas.py tests/test_bdm_006_service.py tests/test_bdm_006_appointments.py tests/test_bdm_006_transitions.py tests/test_bdm_006_scope.py tests/test_bdm_006_concurrency.py tests/test_bdm_006_org_meetings.py tests/test_bdm_002_organizations.py tests/test_bdm_002_contacts.py tests/test_bdm_002_scope.py tests/test_bdm_002_service.py tests/test_bdm_002_assign.py tests/test_bdm_002_migration.py tests/test_bdm_001_reads.py tests/test_agn_017_migration.py
WEB_TEST "npx vitest run tests/lib/bdmAppointments.test.ts tests/lib/bdmOrganizations.test.ts tests/lib/navigation.bdm.test.ts tests/components/BdmAppointment tests/components/BdmOrganization tests/components/BdmPages.test.tsx tests/components/SearchableSelect.test.tsx"
WEB_TEST "npx tsc --noEmit && npx eslint app components lib tests && npx next build"
```

Expected: all pass. Record the exact counts.

- [ ] **Step 5: Browser QA** — with the stack running, walk AC1–AC7 in a real browser (the `webapp-testing` / Browser Use skill, as bdm-002 did): booking from the organization page, every action, the overlap warning, a 409 from a second tab, keyboard-only use of the action groups (Tab / Escape), 320 px and 375 px widths, screen-reader names of the alerts. Record findings in `docs/quality/BDM-006_BROWSER_QA_2026-10-03.md` (finding, severity, fix commit, re-check); fix each with a test first.

- [ ] **Step 6: Re-check `main`, then commit**

```bash
git fetch origin && git log --oneline HEAD..origin/main -- apps/api/alembic/versions docs/decisions
# If a migration or DEC landed: re-chain 0068 and renumber DEC-SCOPE-063 everywhere, re-run Step 4's API_TEST line.
git add apps/web/tests/e2e/bdm-006-appointments.spec.ts docs/
git commit -m "docs(bdm-006): e2e journey, architecture docs, RTM and verification evidence" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review (done while writing)

**Spec coverage** — every spec section maps to a task:

| Spec | Task |
|---|---|
| §3 A1–A8 + defaults | 0 (DEC), 3 (rules), 4–6 (enforced) |
| §4.1 catalogues, §4.2–4.4 tables / migration | 1 |
| §5.1 schemas (+ R-A7 minute normalization) | 2 |
| §5.2 service (+ R-A11 index-bounded overlap) | 3 |
| §5.3 list / create / detail | 4 |
| §5.3 PATCH, §5.7 contact-change lock order | 5 |
| §5.3 actions, §5.4 matrix | 3 (pure matrix), 6 (routes) |
| §5.5 create order | 4 (`test_create_rejections_in_rule_order`) |
| §5.6 organization outputs (+ display fix) | 9 |
| §5.7 races | 8 |
| §5.8 errors | 4–7 |
| §6.1 pages | 11, 12, 13 |
| §6.2 components | 11, 12, 13 |
| §6.3 navigation | 10 |
| §6.4 / §12.2 responsive, a11y, states | 11–13 tests + 14 (e2e width, browser QA) |
| §7 AC1–AC10 | AC1: 4, 13 · AC2: 3, 4, 12 · AC3: 3, 6, 13 · AC4: 6, 13 · AC5: 6 · AC6: 7, 14 · AC7: 7, 14 · AC8: 4, 5, 6, 12 · AC9: 9 · AC10: 5 |
| §10 docs | 0, 14 |
| §12.3 security (IDOR, mass assignment, logs, audit) | 2 (forbid), 3 (log fields), 4–7 (audit, scope tests) |

**Placeholder scan** — no "TBD"/"TODO"; every code step has code. The two judgment points are explicit decisions with a check: Task 1 Step 4 (import catalogues in the migration vs inline, decided by an existing-migration grep) and Task 9 / 11 (adjust an IST text regex to the real output of the unchanged `formatSchoolDateTime`).

**Type consistency** — checked across tasks: `row_out(appt, org, owner)` (Task 3) vs `org_svc.row_out(user, org, assignee, primary, last, next)` (Task 9) are different modules; `_contact_of`, `_type_allowed`, `_check_overlap`, `_envelope` defined in Task 4 and reused in 5–6; `require_open` is in Task 3's interface list; web `Appointment` / `AppointmentRow` / `Overlap` / `FieldValues` names match between Tasks 10–13; `BdmOverlapAlert` props are the same in the form and the reschedule form; `meetingText` (Task 9) lives in `lib/bdmOrganizations.ts`, not the appointments lib.

**Review Focus** — five lines, each pinned: retry (Task 4 `test_a_retried_create_meets_the_overlap_warning_naming_the_first`), confirm/cancel race (Task 8), contact delete (Task 5 + Task 13 detail renders `contact_id: null`), IST day edges (Task 4 list test + Task 10 lib test), reassignment (Task 7).

---

## Task list (summary)

| # | Task | Deliverable | Main tests |
|---|---|---|---|
| 0 | Decision record and backlog notes | `DEC-SCOPE-063`, backlog status, bdm-002 AC5b wording | — (docs) |
| 1 | Models, catalogues, migration `0068` | 2 tables, 1 sequence, catalogues | `test_bdm_006_migration.py` |
| 2 | Schemas | request / response models | `test_bdm_006_schemas.py` |
| 3 | Service | rules, scope, overlap, output, meeting columns | `test_bdm_006_service.py` (6×6 matrix) |
| 4 | Router: create, read, list | `GET/POST /bdm/appointments`, `GET /{id}` | `test_bdm_006_appointments.py` |
| 5 | PATCH | edit open appointments, contact re-snapshot, AC10 | `test_bdm_006_appointments.py` (append) |
| 6 | Actions | confirm, reschedule, cancel, no-show, complete | `test_bdm_006_transitions.py` |
| 7 | Scope matrix | AC6, AC7, reassignment | `test_bdm_006_scope.py` |
| 8 | Concurrency | races serialize, never 500 | `test_bdm_006_concurrency.py` |
| 9 | Organization Last / Next meeting | real values + IST display | `test_bdm_006_org_meetings.py`, org component tests |
| 10 | Web library + navigation | `lib/bdmAppointments.ts`, sidebars | `bdmAppointments.test.ts`, nav test |
| 11 | List panel + list pages | `/bdm/appointments`, `/bdm/manager/appointments` | `BdmAppointmentsPanel.test.tsx` |
| 12 | Booking / edit form + new page | form, fields, overlap alert | `BdmAppointmentForm.test.tsx` |
| 13 | Detail, actions, history, detail pages, Add link | detail view and actions | Actions / Detail / History / org detail tests; `tsc` / `eslint` / `build` |
| 14 | E2E, docs, lite verification, browser QA | release evidence | `bdm-006-appointments.spec.ts` + lite sets |
