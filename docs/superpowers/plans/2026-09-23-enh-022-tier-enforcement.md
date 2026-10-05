# ENH-022 — Tier-Gated Feature Access Enforcement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject every write to a `TIER_SERVICES`-listed service with a hard `403` (plus a denial audit) when the school's valid, cumulative partnership tier does not include it.

**Architecture:** One helper, `require_school_entitlement(db, user, school_id, service_key)`, beside `TIER_ORDER`/`TIER_SERVICES`/`_cumulative_services()` in `apps/api/app/api/schools.py`, called inside each gated handler after its existing role and scope checks and before any mutation. The decision logic is a pure function (`_entitlement_denial`) so it is unit-testable without a database. Frontend work is limited to the save-failure path of six older panels, through one small shared `sendJson()` in `apps/web/lib/apiErrors.ts`.

**Tech Stack:** FastAPI, SQLAlchemy async, pytest + pytest-asyncio + httpx (backend); Next.js/React, Vitest + Testing Library (frontend); Playwright (E2E).

**Spec:** `docs/superpowers/specs/2026-09-23-enh-022-tier-enforcement-design.md` (decisions D1–D12, `DEC-SCOPE-027`).

## Global Constraints

- Hard `403`, FastAPI `{"detail": "<string>"}`; exact strings from spec §5.1: `This school has no active partnership tier.` / `This school's partnership expired on {%d %b %Y}.` / `This school's {Tier} partnership does not include {label} (requires {MinTier} or higher).`
- Expiry is compared with today's **Asia/Kolkata** date; the valid-until date itself is valid; `NULL` never expires.
- Check order per handler: existing role → existing scope → validation of the key-deciding field → **tier** → everything else. **Never move an existing check**; insert the tier call immediately after the existing scope check (or after the key-deciding field's validation when that comes later).
- The tier call must precede every `db.add`, attribute mutation and `flush` in the handler (the denial commits its audit row, so anything pending would be committed with it).
- Denial audit: `AuditLog(action="school.tier_access_denied", entity_type="school", entity_id=str(school_id), outcome="denied", metadata_json={"service_key", "reason", "tier"})` + `logger.warning("tier_access_denied", …)`; no names, emails or student IDs.
- `GET /school/entitlements`, `TIER_ORDER`, `TIER_SERVICES`, `_cumulative_services()` are not modified.
- No migration, no new dependency, no new component or CSS class.
- **The user controls Docker.** Backend tests that need Postgres are marked **[DB]**; they run only after the user starts Docker / authorises an isolated compose project for this worktree. Command (from repo root), `app`/`tests` mounted so edits need no rebuild:
  `docker compose -f docker-compose.yml -f docker-compose.ci.yml -p enh022 --profile ci run --rm -v ./apps/api/app:/app/app -v ./apps/api/tests:/app/tests api-test python -m pytest -q <files>` — called **`DBTEST <files>`** below.
- Pure backend unit tests run on the host: `cd apps/api && python -m pytest -q tests/test_enh_022_tier_rules.py`.
- Web unit tests: `npm --prefix apps/web run test -- <file>` (requires `npm --prefix apps/web ci` once in this worktree).

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `apps/api/app/api/schools.py` | Modify | Tier rules + `require_school_entitlement`; activity/test-prep key maps; gate activities, career, psychometric, test-prep, language |
| `apps/api/app/api/school_skills.py` | Modify | Gate 8 skills write routes via `USAGE_KEYS[module_type]` |
| `apps/api/app/api/portfolio.py` | Modify | Gate 4 portfolio write routes |
| `apps/api/app/api/admin.py` | Modify | Gate bridged-application create |
| `apps/api/app/api/workflows.py` | Modify | Gate VisaCase create/update on a bridged application |
| `apps/api/tests/test_enh_022_tier_rules.py` | Create | Pure/unit tests (no DB) |
| `apps/api/tests/test_enh_022_tier_enforcement.py` | Create | [DB] per-route integration tests |
| `apps/api/tests/enh005_helpers.py` | Modify | `mk_school(..., tier="platinum")` default so ENH-004/005/011/012 suites keep an entitled school |
| `apps/api/tests/test_sch_00{4,5,7,8,9}_*.py`, `test_sch_010_overseas_bridge.py`, others found by the sweep | Modify | Fixture schools get `tier="platinum"` (setup only; no assertion changes) |
| `apps/web/lib/apiErrors.ts` | Modify | Add `sendJson()` (never throws; `NOT_COMPLETED` on network failure) |
| 6 panels in `apps/web/components/` | Modify | Use `sendJson`, `role="alert"` on failure, message beside the failing form |
| `apps/web/tests/components/*.test.tsx` | Create | One test file per changed panel + `apiErrors` |
| `apps/web/tests/e2e/*.spec.ts` | Modify / Create | Existing school-creating specs pick Platinum; new `enh-022-tier-enforcement.spec.ts` |
| `docs/…` | Modify | Decision register, API contract, RBAC matrix, RTM, backlog |

---

### Task 1: Tier rules and the enforcement helper (host-runnable)

**Files:**
- Modify: `apps/api/app/api/schools.py` (beside `TIER_ORDER` … `_cumulative_services`, ~line 798-839; add `from zoneinfo import ZoneInfo` and `from sqlalchemy.exc import SQLAlchemyError` to imports)
- Test: `apps/api/tests/test_enh_022_tier_rules.py`

**Interfaces — Produces:**
- `TIER_DENIED = "school.tier_access_denied"`
- `ACTIVITY_SERVICE_KEYS: dict[str, str]`, `TEST_PREP_SERVICE_KEYS: dict[str, str]`
- `_today_ist() -> date`
- `_minimum_tier(service_key: str) -> str` (raises `ValueError` for an unknown key)
- `_entitlement_denial(tier: str | None, valid_until: date | None, service_key: str | None, today: date) -> tuple[str, str] | None` — `(reason, message)`; reason ∈ `no_tier|expired|not_included`
- `async require_school_entitlement(db: AsyncSession, user: User, school_id: UUID, service_key: str | None) -> None`

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-022 (DEC-SCOPE-027) -- tier rules and the enforcement helper, without a database."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.api import schools
from app.api.schools import TIER_DENIED, _entitlement_denial, _minimum_tier, require_school_entitlement

TODAY = date(2026, 9, 23)
NO_TIER = "This school has no active partnership tier."


def test_minimum_tier_is_the_first_tier_that_lists_the_key():
    assert _minimum_tier("psychometric_test") == "bronze"
    assert _minimum_tier("web_designing") == "silver"
    assert _minimum_tier("ielts_coaching") == "gold"
    assert _minimum_tier("visa_support") == "platinum"


def test_unknown_service_key_is_a_programming_error():
    with pytest.raises(ValueError):
        _minimum_tier("ielts")
    with pytest.raises(ValueError):
        _entitlement_denial("platinum", None, "not_a_service", TODAY)


@pytest.mark.parametrize("tier", [None, "", "diamond"])
def test_no_or_unknown_tier_is_denied(tier):
    assert _entitlement_denial(tier, None, "psychometric_test", TODAY) == ("no_tier", NO_TIER)
    assert _entitlement_denial(tier, None, None, TODAY) == ("no_tier", NO_TIER)


def test_minimum_tier_allows_and_one_below_denies_with_exact_message():
    assert _entitlement_denial("gold", None, "ielts_coaching", TODAY) is None
    assert _entitlement_denial("silver", None, "ielts_coaching", TODAY) == (
        "not_included",
        "This school's Silver partnership does not include IELTS coaching (requires Gold or higher).",
    )


def test_tiers_are_cumulative():
    assert _entitlement_denial("platinum", None, "career_seminar", TODAY) is None
    assert _entitlement_denial("silver", None, "soft_skills", TODAY) is None


def test_expiry_is_inclusive_and_null_never_expires():
    assert _entitlement_denial("platinum", TODAY, "visa_support", TODAY) is None
    assert _entitlement_denial("platinum", None, "visa_support", TODAY) is None
    assert _entitlement_denial("platinum", date(2026, 9, 22), "visa_support", TODAY) == (
        "expired",
        "This school's partnership expired on 22 Sep 2026.",
    )


def test_any_valid_tier_check():
    assert _entitlement_denial("bronze", None, None, TODAY) is None
    assert _entitlement_denial("bronze", date(2026, 1, 1), None, TODAY)[0] == "expired"


def test_today_is_the_india_date(monkeypatch):
    import datetime as real

    class FakeDateTime(real.datetime):
        @classmethod
        def now(cls, tz=None):
            # 18:31 UTC on 22 Sep is 00:01 IST on 23 Sep.
            return real.datetime(2026, 9, 22, 18, 31, tzinfo=real.UTC).astimezone(tz)

    monkeypatch.setattr(schools, "datetime", FakeDateTime)
    assert schools._today_ist() == date(2026, 9, 23)


class FakeDB:
    """Just enough of AsyncSession for the helper: get / add / commit / rollback."""

    def __init__(self, school, fail_commit=False):
        self.school, self.fail_commit = school, fail_commit
        self.added, self.commits, self.rollbacks = [], 0, 0

    async def get(self, model, key):
        return self.school

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        if self.fail_commit:
            raise OperationalError("COMMIT", {}, Exception("connection lost"))
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


USER = SimpleNamespace(id=uuid4(), role="school_coordinator")


@pytest.mark.asyncio
async def test_allowed_request_writes_nothing(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    db = FakeDB(SimpleNamespace(tier="gold", tier_valid_until=None))
    await require_school_entitlement(db, USER, uuid4(), "ielts_coaching")
    assert db.added == [] and db.commits == 0


@pytest.mark.asyncio
async def test_denial_commits_one_audit_row_then_raises_403(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    school_id = uuid4()
    db = FakeDB(SimpleNamespace(tier="bronze", tier_valid_until=None))
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, school_id, "monthly_campus_visits")
    assert exc.value.status_code == 403
    assert exc.value.detail == "This school's Bronze partnership does not include Monthly campus visits (requires Platinum or higher)."
    assert db.commits == 1 and len(db.added) == 1
    audit = db.added[0]
    assert (audit.action, audit.entity_type, audit.entity_id, audit.outcome) == (TIER_DENIED, "school", str(school_id), "denied")
    assert audit.metadata_json == {"service_key": "monthly_campus_visits", "reason": "not_included", "tier": "bronze"}


@pytest.mark.asyncio
async def test_missing_school_is_denied_not_a_500(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    db = FakeDB(None)
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, uuid4(), None)
    assert (exc.value.status_code, exc.value.detail) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_a_failed_audit_commit_still_denies(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    db = FakeDB(SimpleNamespace(tier=None, tier_valid_until=None), fail_commit=True)
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, uuid4(), "career_seminar")
    assert exc.value.status_code == 403
    assert db.rollbacks == 1
```

- [ ] **Step 2: Run to verify RED**

Run: `cd apps/api && python -m pytest -q tests/test_enh_022_tier_rules.py`
Expected: collection error — `ImportError: cannot import name 'TIER_DENIED' from 'app.api.schools'`.

- [ ] **Step 3: Implement** (insert after `_cumulative_services`, leave the three existing definitions untouched)

```python
# ENH-022 / DEC-SCOPE-027: the tier is enforced on every write to a TIER_SERVICES service, not only reported.
TIER_TIMEZONE = ZoneInfo("Asia/Kolkata")  # D10: a partnership expires on the India calendar
TIER_DENIED = "school.tier_access_denied"
NO_ACTIVE_TIER = "This school has no active partnership tier."
SERVICE_LABELS = {key: label for services in TIER_SERVICES.values() for key, label in services}
# Request values -> the service they consume. Also the allowlists those request fields are validated against.
ACTIVITY_SERVICE_KEYS = {"career_seminar": "career_seminar", "career_awareness_session": "career_awareness_session", "parent_orientation": "parent_orientation", "campus_visit": "monthly_campus_visits"}
TEST_PREP_SERVICE_KEYS = {"ielts": "ielts_coaching", "sat": "sat_coaching"}


def _today_ist() -> date:
    return datetime.now(TIER_TIMEZONE).date()


def _minimum_tier(service_key: str) -> str:
    for tier in TIER_ORDER:
        if any(key == service_key for key, _ in TIER_SERVICES[tier]):
            return tier
    raise ValueError(f"Unknown tier service key: {service_key!r}")


def _entitlement_denial(tier: str | None, valid_until: date | None, service_key: str | None, today: date) -> tuple[str, str] | None:
    """(reason, 403 message) when the school may not use `service_key`, else None. `service_key=None` asks only for a
    valid tier (D7). An unknown key raises: a mis-wired call site must fail loudly, never deny forever in silence."""
    minimum = _minimum_tier(service_key) if service_key is not None else None
    if tier not in TIER_ORDER:
        return "no_tier", NO_ACTIVE_TIER
    if valid_until is not None and valid_until < today:
        return "expired", f"This school's partnership expired on {valid_until.strftime('%d %b %Y')}."
    if service_key is not None and service_key not in {key for key, _ in _cumulative_services(tier)}:
        return "not_included", (
            f"This school's {tier.capitalize()} partnership does not include {SERVICE_LABELS[service_key]} "
            f"(requires {minimum.capitalize()} or higher)."
        )
    return None


async def require_school_entitlement(db: AsyncSession, user: User, school_id: UUID, service_key: str | None) -> None:
    """403 unless the school's valid cumulative tier includes `service_key`. Call it after the route's own role and scope
    checks and before any write: a denial commits its audit row (D12), so nothing else may be pending in the session."""
    school = await db.get(School, school_id)
    denial = _entitlement_denial(school.tier if school else None, school.tier_valid_until if school else None, service_key, _today_ist())
    if denial is None:
        return
    reason, message = denial
    fields = {"actor_id": str(user.id), "role": user.role, "school_id": str(school_id), "service_key": service_key, "reason": reason}
    db.add(AuditLog(user_id=user.id, action=TIER_DENIED, entity_type="school", entity_id=str(school_id), outcome="denied", metadata_json={"service_key": service_key, "reason": reason, "tier": school.tier if school else None}))
    try:
        await db.commit()
    except SQLAlchemyError:
        # The denial stands even if its audit row cannot be written.
        await db.rollback()
        logger.exception("tier_access_denied_audit_failed", extra={"extra_fields": fields})
    logger.warning("tier_access_denied", extra={"extra_fields": fields})
    raise HTTPException(403, message)
```

- [ ] **Step 4: Run to verify GREEN**

Run: `cd apps/api && python -m pytest -q tests/test_enh_022_tier_rules.py`
Expected: all pass.

- [ ] **Step 5: Refactor** — replace the activity allowlist literal in `create_activity` with the map (behavior identical):
`if activity_type and activity_type not in ACTIVITY_SERVICE_KEYS:` and in `create_test_prep_record` `if test_type not in TEST_PREP_SERVICE_KEYS:` (error strings unchanged). Rerun Step 4 and `python -m ruff check app/api/schools.py tests/test_enh_022_tier_rules.py`.

- [ ] **Step 6: Commit** — `feat(enh-022): tier entitlement rules and enforcement helper`

---

### Task 2 [DB]: Gate activities (create + attendance)

**Files:** Modify `schools.py` `create_activity`, `mark_attendance`; Create `tests/test_enh_022_tier_enforcement.py`; Modify `tests/enh005_helpers.py`.

**Interfaces — Consumes:** `require_school_entitlement`, `ACTIVITY_SERVICE_KEYS`. **Produces (test helpers in the new file):** `world(db, tier, valid_until=None)`, `denials(db, school_id) -> int`.

- [ ] **Step 1: Give `mk_school` an entitled default** (shared by ENH-004/005/011/012 suites; ENH-005 transfer routes are not gated so nothing else changes):

```python
async def mk_school(db, *, admin=None, label: str = "School", students: int = 1, with_teacher: bool = True, tier: str | None = "platinum", tier_valid_until=None) -> dict:
    ...
    school = School(name=f"ENH-005 {label} {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id, tier=tier, tier_valid_until=tier_valid_until)
```

- [ ] **Step 2: Write failing tests** (new file header + activity tests)

```python
"""ENH-022 (DEC-SCOPE-027) -- per-route tier enforcement against a real database."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.api.schools import TIER_DENIED
from app.models import AuditLog, SchoolActivity
from enh005_helpers import login, mk_school, mk_staff

NO_TIER = "This school has no active partnership tier."
YESTERDAY = date.today() - timedelta(days=2)  # two days: never "today" in IST whatever the host timezone


async def denials(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(school_id)))


async def world(db, tier, valid_until=None, staff_role=None):
    w = await mk_school(db, label="T", tier=tier, tier_valid_until=valid_until)
    if staff_role:
        w["staff"] = await mk_staff(db, w["school"], w["admin"], role=staff_role)
    return w


def activity(activity_type=None):
    body = {"title": "Session", "scheduled_at": datetime.now(UTC).isoformat()}
    return body | ({"activity_type": activity_type} if activity_type else {})


async def activity_count(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(SchoolActivity).where(SchoolActivity.school_id == school_id))


@pytest.mark.asyncio
async def test_campus_visit_needs_platinum(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["coordinator"].email)
    r = await client.post("/api/v1/school/activities", json=activity("campus_visit"))
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Gold partnership does not include Monthly campus visits (requires Platinum or higher)."
    assert await activity_count(db_session, w["school"].id) == 0
    assert await denials(db_session, w["school"].id) == 1

    p = await world(db_session, "platinum")
    await login(client, p["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).status_code == 201
    assert await denials(db_session, p["school"].id) == 0


@pytest.mark.asyncio
async def test_bronze_activity_allowed_on_bronze(client, db_session):
    w = await world(db_session, "bronze")
    await login(client, w["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity("career_seminar"))).status_code == 201


@pytest.mark.asyncio
async def test_free_text_activity_needs_any_valid_tier(client, db_session):
    ok = await world(db_session, "bronze")
    await login(client, ok["coordinator"].email)
    assert (await client.post("/api/v1/school/activities", json=activity())).status_code == 201
    none = await world(db_session, None)
    await login(client, none["coordinator"].email)
    r = await client.post("/api/v1/school/activities", json=activity())
    assert (r.status_code, r.json()["detail"]) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_expired_partnership_blocks_activities(client, db_session):
    w = await world(db_session, "platinum", valid_until=YESTERDAY)
    await login(client, w["coordinator"].email)
    r = await client.post("/api/v1/school/activities", json=activity("career_seminar"))
    assert r.status_code == 403
    assert r.json()["detail"] == f"This school's partnership expired on {YESTERDAY.strftime('%d %b %Y')}."


@pytest.mark.asyncio
async def test_attendance_uses_the_stored_activity_type(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    created = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    w["school"].tier = "gold"  # downgraded after the visit was scheduled
    await db_session.commit()
    body = {"records": [{"student_id": str(w["students"][0].id), "present": True}]}
    r = await client.post(f"/api/v1/school/activities/{created['id']}/attendance", json=body)
    assert r.status_code == 403
    assert "Monthly campus visits" in r.json()["detail"]


@pytest.mark.asyncio
async def test_other_schools_activity_is_still_404_with_no_tier_audit(client, db_session):
    rich = await world(db_session, "platinum")
    await login(client, rich["coordinator"].email)
    created = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    poor = await world(db_session, None)
    await login(client, poor["coordinator"].email)
    body = {"records": [{"student_id": str(poor["students"][0].id), "present": True}]}
    r = await client.post(f"/api/v1/school/activities/{created['id']}/attendance", json=body)
    assert r.status_code == 404
    assert await denials(db_session, poor["school"].id) == 0
```

- [ ] **Step 3: RED** — `DBTEST tests/test_enh_022_tier_enforcement.py` → the gated-denial tests fail with `201 != 403`; the out-of-scope test passes already (it pins existing behavior).

- [ ] **Step 4: Implement**

In `create_activity`, directly after the existing `activity_type` validation and before `activity = SchoolActivity(...)`:
```python
    await require_school_entitlement(db, user, school_id, ACTIVITY_SERVICE_KEYS.get(activity_type) if activity_type else None)
```
In `mark_attendance`, directly after the existing `404 Activity not found` check:
```python
    await require_school_entitlement(db, user, school_id, ACTIVITY_SERVICE_KEYS.get(activity.activity_type) if activity.activity_type else None)
```

- [ ] **Step 5: GREEN** — `DBTEST tests/test_enh_022_tier_enforcement.py tests/test_sch_001_school_portal_access.py tests/test_sch_007_parent_portal.py tests/test_sch_011_entitlements.py`. Any existing failure caused by a tier-less fixture school: add `tier="platinum"` to that file's `School(...)` constructor only (no assertion edits). Rerun.

- [ ] **Step 6: Commit** — `feat(enh-022): gate activity scheduling and attendance by tier`

---

### Task 3 [DB]: Gate career-counselor and psychometric records

**Files:** Modify `schools.py` `create_career_record`, `create_psychometric_record`, `update_psychometric_record`; Test: append to `test_enh_022_tier_enforcement.py`.

- [ ] **Step 1: Failing tests**

```python
from app.models import SchoolCareerRecord, SchoolPsychometricRecord


@pytest.mark.asyncio
@pytest.mark.parametrize("record_type", ["guidance_session", "counselling_note", "recommendation"])
async def test_every_career_record_needs_silver(client, db_session, record_type):
    w = await world(db_session, "bronze", staff_role="career_counselor")
    await login(client, w["staff"].email)
    body = {"school_student_id": str(w["students"][0].id), "record_type": record_type, "notes": "n"}
    r = await client.post("/api/v1/school/career-counselor/records", json=body)
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Bronze partnership does not include Individual counselling (requires Silver or higher)."
    assert await db_session.scalar(select(func.count()).select_from(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == w["students"][0].id)) == 0
    s = await world(db_session, "silver", staff_role="career_counselor")
    await login(client, s["staff"].email)
    body["school_student_id"] = str(s["students"][0].id)
    assert (await client.post("/api/v1/school/career-counselor/records", json=body)).status_code == 201


@pytest.mark.asyncio
async def test_psychometric_needs_a_valid_tier_on_create_and_update(client, db_session):
    w = await world(db_session, "bronze", staff_role="psychometric_team")
    await login(client, w["staff"].email)
    created = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(w["students"][0].id), "assessment_type": "Aptitude"})
    assert created.status_code == 201
    w["school"].tier_valid_until = YESTERDAY
    await db_session.commit()
    r = await client.patch(f"/api/v1/school/psychometric-team/records/{created.json()['id']}", json={"report_url": "https://example.local/r.pdf"})
    assert r.status_code == 403
    record = await db_session.get(SchoolPsychometricRecord, created.json()["id"])
    await db_session.refresh(record)
    assert record.report_url is None and record.status == "assigned"
    assert await denials(db_session, w["school"].id) == 1


@pytest.mark.asyncio
async def test_tierless_school_cannot_get_psychometric_records(client, db_session):
    w = await world(db_session, None, staff_role="psychometric_team")
    await login(client, w["staff"].email)
    r = await client.post("/api/v1/school/psychometric-team/records", json={"school_student_id": str(w["students"][0].id), "assessment_type": "Aptitude"})
    assert (r.status_code, r.json()["detail"]) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_counselor_outside_portfolio_keeps_the_old_403_and_no_tier_audit(client, db_session):
    w = await world(db_session, None)
    outsider_home = await world(db_session, "platinum", staff_role="career_counselor")
    await login(client, outsider_home["staff"].email)
    body = {"school_student_id": str(w["students"][0].id), "record_type": "guidance_session", "notes": "n"}
    r = await client.post("/api/v1/school/career-counselor/records", json=body)
    assert (r.status_code, r.json()["detail"]) == (403, "This student is at a school outside your own portfolio")
    assert await denials(db_session, w["school"].id) == 0
```

- [ ] **Step 2: RED** — `DBTEST tests/test_enh_022_tier_enforcement.py -k "career or psychometric or portfolio_keeps"` → gated tests fail with `201/200 != 403`.

- [ ] **Step 3: Implement**
- `create_career_record`: after `student = await _student_in_portfolio(...)`: `await require_school_entitlement(db, user, student.school_id, "individual_counselling")`.
- `create_psychometric_record`: after `student = await _student_in_portfolio(...)`: `await require_school_entitlement(db, user, student.school_id, "psychometric_test")`.
- `update_psychometric_record`: change `await _student_in_portfolio(db, user, record.school_student_id)` to `student = await _student_in_portfolio(...)`, then `await require_school_entitlement(db, user, student.school_id, "psychometric_test")`, before `became_completed = False`.

- [ ] **Step 4: GREEN** — `DBTEST tests/test_enh_022_tier_enforcement.py tests/test_sch_004_career_guidance.py tests/test_sch_005_psychometric_assessment.py tests/test_sch_008_student_timeline.py`; fixture-only `tier="platinum"` fixes as in Task 2 Step 5.

- [ ] **Step 5: Commit** — `feat(enh-022): gate career-counselor and psychometric records by tier`

---

### Task 4 [DB]: Gate test-prep and language records

**Files:** Modify `schools.py` `create_test_prep_record`, `update_test_prep_record`, `create_language_record`, `update_language_record`; Test: append.

- [ ] **Step 1: Failing tests**

```python
from app.models import SchoolTestPrepRecord


@pytest.mark.asyncio
async def test_ielts_needs_gold_and_patch_uses_the_stored_test_type(client, db_session):
    w = await world(db_session, "silver", staff_role="academic_team")
    await login(client, w["staff"].email)
    r = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(w["students"][0].id), "test_type": "ielts"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Silver partnership does not include IELTS coaching (requires Gold or higher)."

    g = await world(db_session, "gold", staff_role="academic_team")
    await login(client, g["staff"].email)
    created = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(g["students"][0].id), "test_type": "sat"})
    assert created.status_code == 201
    g["school"].tier = "silver"
    await db_session.commit()
    patched = await client.patch(f"/api/v1/school/academic-team/test-prep-records/{created.json()['id']}", json={"actual_score": "1400", "test_type": "ielts"})
    assert patched.status_code == 403
    assert "SAT coaching" in patched.json()["detail"]
    record = await db_session.get(SchoolTestPrepRecord, created.json()["id"])
    await db_session.refresh(record)
    assert record.actual_score is None


@pytest.mark.asyncio
async def test_invalid_test_type_is_still_422_before_the_tier_check(client, db_session):
    w = await world(db_session, None, staff_role="academic_team")
    await login(client, w["staff"].email)
    r = await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": str(w["students"][0].id), "test_type": "toefl"})
    assert r.status_code == 422
    assert await denials(db_session, w["school"].id) == 0


@pytest.mark.asyncio
async def test_language_classes_need_gold_on_create_and_update(client, db_session):
    w = await world(db_session, "gold", staff_role="academic_team")
    await login(client, w["staff"].email)
    created = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(w["students"][0].id), "language": "German"})
    assert created.status_code == 201
    w["school"].tier = "bronze"
    await db_session.commit()
    r = await client.patch(f"/api/v1/school/academic-team/language-records/{created.json()['id']}", json={"certification_status": "certified"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Bronze partnership does not include Foreign language classes (requires Gold or higher)."
    b = await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": str(w["students"][0].id), "language": "French"})
    assert b.status_code == 403
```

- [ ] **Step 2: RED** — `DBTEST tests/test_enh_022_tier_enforcement.py -k "ielts or test_type or language"`.

- [ ] **Step 3: Implement**
- `create_test_prep_record`: after the existing `test_type` validation: `await require_school_entitlement(db, user, student.school_id, TEST_PREP_SERVICE_KEYS[test_type])`.
- `update_test_prep_record`: `student = await _student_in_portfolio(...)`; then `await require_school_entitlement(db, user, student.school_id, TEST_PREP_SERVICE_KEYS[record.test_type])` before `became_completed = False`.
- `create_language_record`: after `student = await _student_in_portfolio(...)`: `await require_school_entitlement(db, user, student.school_id, "foreign_language_classes")`.
- `update_language_record`: `student = await _student_in_portfolio(...)`; then the same call before `became_certified = False`.

- [ ] **Step 4: GREEN** — `DBTEST tests/test_enh_022_tier_enforcement.py tests/test_sch_009_test_prep_language.py tests/test_enh_002_*.py`; fixture-only fixes.

- [ ] **Step 5: Commit** — `feat(enh-022): gate test-prep and language records by tier`

---

### Task 5 [DB]: Gate the skills tracker (8 routes)

**Files:** Modify `apps/api/app/api/school_skills.py`; Test: append.

**Interfaces — Consumes:** `require_school_entitlement` (import from `app.api.schools` alongside `_notify_student_parents, _portfolio_school_ids`), existing `USAGE_KEYS`.

- [ ] **Step 1: Failing tests**

```python
from enh011_helpers import BATCHES


@pytest.mark.asyncio
async def test_digital_skills_batch_needs_silver_soft_skills_bronze(client, db_session):
    w = await world(db_session, "bronze", staff_role="career_counselor")
    await login(client, w["staff"].email)
    base = {"school_id": str(w["school"].id), "title": "T", "start_date": "2026-10-01"}
    r = await client.post(BATCHES, json=base | {"module_type": "digital_skills"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Bronze partnership does not include Web designing (requires Silver or higher)."
    assert (await client.post(BATCHES, json=base | {"module_type": "soft_skills"})).status_code == 201


@pytest.mark.asyncio
async def test_every_skills_write_is_blocked_after_expiry(client, db_session):
    w = await world(db_session, "silver", staff_role="career_counselor")
    await login(client, w["staff"].email)
    batch = (await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "digital_skills", "title": "T", "start_date": date.today().isoformat()})).json()
    enrolment = (await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(w["students"][0].id)]})).json()[0]
    session = (await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": date.today().isoformat()})).json()
    assessment = (await client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Quiz", "max_score": 10})).json()
    w["school"].tier_valid_until = YESTERDAY
    await db_session.commit()
    calls = [
        client.patch(f"{BATCHES}/{batch['id']}", json={"title": "New"}),
        client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [str(w["students"][0].id)]}),
        client.patch(f"/api/v1/school/career-counselor/skill-enrollments/{enrolment['id']}", json={"status": "completed"}),
        client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": (date.today() + timedelta(days=1)).isoformat()}),
        client.put(f"/api/v1/school/career-counselor/skill-sessions/{session['id']}/attendance", json={"records": [{"enrollment_id": enrolment["id"], "present": True}]}),
        client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Quiz 2", "max_score": 10}),
        client.put(f"/api/v1/school/career-counselor/skill-assessments/{assessment['id']}/scores", json={"scores": [{"enrollment_id": enrolment["id"], "score": 5}]}),
    ]
    for call in calls:
        r = await call
        assert r.status_code == 403, r.text
        assert r.json()["detail"].startswith("This school's partnership expired on")
    assert await denials(db_session, w["school"].id) == len(calls)


@pytest.mark.asyncio
async def test_batch_in_another_portfolio_is_still_404(client, db_session):
    w = await world(db_session, "platinum", staff_role="career_counselor")
    await login(client, w["staff"].email)
    batch = (await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "soft_skills", "title": "T", "start_date": "2026-10-01"})).json()
    other = await world(db_session, None, staff_role="career_counselor")
    await login(client, other["staff"].email)
    assert (await client.patch(f"{BATCHES}/{batch['id']}", json={"title": "X"})).status_code == 404
```

- [ ] **Step 2: RED** — `DBTEST tests/test_enh_022_tier_enforcement.py -k skills`.

- [ ] **Step 3: Implement** — add one local helper in `school_skills.py` and call it right after each route's existing scope step (after `_batch_in_portfolio(...)`, or after the enrolment's locked join for `update_enrolment_status`; after the portfolio check for `create_skill_batch`), before `_require_open`/validation/writes:

```python
async def _require_module_entitlement(db: AsyncSession, user: User, school_id: UUID, module_type: str) -> None:
    """ENH-022: a skills write consumes the module's tier service (digital_skills is sold as `web_designing`)."""
    await require_school_entitlement(db, user, school_id, USAGE_KEYS[module_type])
```
Calls: `create_skill_batch` → `(db, user, payload.school_id, payload.module_type)`; the other seven → `(db, user, batch.school_id, batch.module_type)`. Move `USAGE_KEYS` above its first use (definition unchanged).

- [ ] **Step 4: GREEN** — `DBTEST tests/test_enh_022_tier_enforcement.py tests/test_enh_011_*.py`.

- [ ] **Step 5: Commit** — `feat(enh-022): gate the skills tracker by tier`

---

### Task 6 [DB]: Gate portfolio writes

**Files:** Modify `apps/api/app/api/portfolio.py` (import `require_school_entitlement` with the existing `app.api.schools` import); Test: append.

- [ ] **Step 1: Failing tests**

```python
from app.models import PortfolioEntry

PORTFOLIO = "/api/v1/school/students/{sid}/portfolio"


@pytest.mark.asyncio
async def test_portfolio_writes_need_gold_reads_stay_open(client, db_session):
    w = await world(db_session, "silver")
    sid = w["students"][0].id
    await login(client, w["coordinator"].email)
    r = await client.post(f"{PORTFOLIO.format(sid=sid)}/entries", json={"section": "project", "title": "Robot"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Silver partnership does not include Digital portfolio creation (requires Gold or higher)."
    assert (await client.patch(f"{PORTFOLIO.format(sid=sid)}/personal-statement", json={"personal_statement": "Hi"})).status_code == 403
    assert (await client.get(PORTFOLIO.format(sid=sid))).status_code == 200


@pytest.mark.asyncio
async def test_portfolio_update_and_delete_blocked_after_downgrade(client, db_session):
    w = await world(db_session, "gold")
    sid = w["students"][0].id
    await login(client, w["coordinator"].email)
    entry = (await client.post(f"{PORTFOLIO.format(sid=sid)}/entries", json={"section": "project", "title": "Robot"})).json()
    w["school"].tier = "silver"
    await db_session.commit()
    assert (await client.patch(f"{PORTFOLIO.format(sid=sid)}/entries/{entry['id']}", json={"title": "Changed"})).status_code == 403
    assert (await client.delete(f"{PORTFOLIO.format(sid=sid)}/entries/{entry['id']}")).status_code == 403
    row = await db_session.get(PortfolioEntry, entry["id"])
    await db_session.refresh(row)
    assert row.title == "Robot"
```

- [ ] **Step 2: RED** — `DBTEST tests/test_enh_022_tier_enforcement.py -k portfolio`.

- [ ] **Step 3: Implement** — in each of the 4 write routes, directly after `_require_portfolio_write(user, student)`:
`await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation")`.

- [ ] **Step 4: GREEN** — `DBTEST tests/test_enh_022_tier_enforcement.py tests/test_enh_012_digital_portfolio.py`.

- [ ] **Step 5: Commit** — `feat(enh-022): gate portfolio writes by tier`

---

### Task 7 [DB]: Gate the School→Overseas bridge and bridged visa cases

**Files:** Modify `admin.py` `create_bridged_application`; `workflows.py` `create_visa_case`, `update_visa`; Test: append (reuses `test_sch_010_overseas_bridge._make_university`/`_add_counselor`).

- [ ] **Step 1: Failing tests**

```python
from test_sch_010_overseas_bridge import _make_university


async def _bridged_application(client, db_session, tier):
    w = await world(db_session, tier)
    university = await _make_university(db_session)
    await login(client, w["admin"].email)
    r = await client.post(f"/api/v1/overseas-admin/school-students/{w['students'][0].id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
    return w, r


@pytest.mark.asyncio
async def test_bridged_application_needs_gold(client, db_session):
    w, r = await _bridged_application(client, db_session, "silver")
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Silver partnership does not include Application support (requires Gold or higher)."
    assert await denials(db_session, w["school"].id) == 1
    _, ok = await _bridged_application(client, db_session, "gold")
    assert ok.status_code == 201


@pytest.mark.asyncio
async def test_visa_case_on_a_bridged_application_needs_platinum(client, db_session):
    w, app = await _bridged_application(client, db_session, "gold")
    r = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": app.json()["id"], "status": "checklist"})
    assert r.status_code == 403
    assert r.json()["detail"] == "This school's Gold partnership does not include Visa support (requires Platinum or higher)."

    p, papp = await _bridged_application(client, db_session, "platinum")
    visa = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": papp.json()["id"], "status": "checklist"})
    assert visa.status_code == 201
    p["school"].tier_valid_until = YESTERDAY
    await db_session.commit()
    assert (await client.patch(f"/api/v1/workflows/overseas/visa/{visa.json()['id']}", json={"tracking_reference": "X1"})).status_code == 403
```
(The non-bridged visa path is pinned by the unchanged `test_visa_001_checklist.py`/`test_visa_003_status.py` runs in Step 4.)

- [ ] **Step 2: RED** — `DBTEST tests/test_enh_022_tier_enforcement.py -k "bridged or visa"`.

- [ ] **Step 3: Implement**
- `admin.py create_bridged_application`: extend the lazy import to `from app.api.schools import _notify_student_parents, require_school_entitlement`; after the `School student not found` 404: `await require_school_entitlement(db, user, student.school_id, "application_support")`.
- `workflows.py`: add a module-level helper next to `_assigned_application`:

```python
async def _require_bridged_visa_entitlement(db: AsyncSession, user: User, application: OverseasApplication) -> None:
    """ENH-022: a visa case on a School-bridged application consumes the school's `visa_support` (Platinum)."""
    if application.school_student_id is None:
        return
    from app.api.schools import require_school_entitlement  # noqa: PLC0415 -- same lazy import admin.py uses

    student = await db.get(SchoolStudent, application.school_student_id)
    if student is not None:
        await require_school_entitlement(db, user, student.school_id, "visa_support")
```
  `create_visa_case`: `application = await _assigned_application(...)` then `await _require_bridged_visa_entitlement(db, user, application)` before the duplicate check. `update_visa`: `application = await _assigned_application(db, user, item.application_id)` then the same call before `if "status" in payload`. Add `SchoolStudent` to the models import if absent.

- [ ] **Step 4: GREEN** — `DBTEST tests/test_enh_022_tier_enforcement.py tests/test_sch_010_overseas_bridge.py tests/test_visa_001_checklist.py tests/test_visa_003_status.py tests/test_ovs_002_application.py tests/test_ovs_004_status_tracking.py`; fixture-only fixes in `test_sch_010`.

- [ ] **Step 5: Commit** — `feat(enh-022): gate bridged applications and bridged visa cases by tier`

---

### Task 8 [DB]: Entitlements regression pin + full backend sweep

- [ ] **Step 1: Pin `/entitlements` (AC-8)** — append:

```python
@pytest.mark.asyncio
async def test_entitlements_report_is_unchanged_for_an_expired_school(client, db_session):
    w = await world(db_session, "gold", valid_until=YESTERDAY)
    await login(client, w["coordinator"].email)
    body = (await client.get("/api/v1/school/entitlements")).json()
    assert body["tier"] == "gold"
    assert body["tier_valid_until"] == YESTERDAY.isoformat()
    assert [s["key"] for s in body["services"]][-1] == "digital_portfolio_creation"
    assert await denials(db_session, w["school"].id) == 0
```
Run `DBTEST tests/test_enh_022_tier_enforcement.py -k entitlements` → passes immediately (pins existing behavior; confirm by temporarily breaking nothing).

- [ ] **Step 2: Full backend suite** — `DBTEST tests` (no file filter). Fix only tier-less **fixtures** of suites that hit a gated route (`tier="platinum"`); never change an assertion or product code to make a pre-existing test pass. Record anything else as a finding.

- [ ] **Step 3: Refactor pass** — `python -m ruff check app tests && python -m ruff format --check app tests`; remove any duplication introduced in Tasks 2–7; rerun `DBTEST tests/test_enh_022_tier_enforcement.py` and the host unit file.

- [ ] **Step 4: Commit** — `test(enh-022): pin entitlements report; tier fixtures for existing suites`

---

### Task 9: Frontend error path — shared `sendJson`

**Files:** Modify `apps/web/lib/apiErrors.ts`; Test: `apps/web/tests/lib/apiErrors.test.ts`.

**Interfaces — Produces:** `type SendOutcome = { ok: true; data: Record<string, unknown> } | { ok: false; message: string }`; `sendJson(url: string, method: "POST" | "PATCH", body: unknown): Promise<SendOutcome>` — never throws.

- [ ] **Step 0:** `npm --prefix apps/web ci` (node_modules is absent in this worktree).

- [ ] **Step 1: Failing test**

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { NOT_COMPLETED, sendJson } from "@/lib/apiErrors";

afterEach(() => vi.unstubAllGlobals());

describe("sendJson", () => {
  it("returns the server's string detail on a 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: "This school has no active partnership tier." }) }));
    expect(await sendJson("/x", "POST", {})).toEqual({ ok: false, message: "This school has no active partnership tier." });
  });
  it("never throws on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect(await sendJson("/x", "PATCH", {})).toEqual({ ok: false, message: NOT_COMPLETED });
  });
  it("falls back to a generic message for a non-JSON error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new Error("not json"); } }));
    expect(await sendJson("/x", "POST", {})).toEqual({ ok: false, message: "Something went wrong." });
  });
  it("returns the JSON body on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "a1" }) });
    vi.stubGlobal("fetch", fetchMock);
    expect(await sendJson("/x", "POST", { a: 1 })).toEqual({ ok: true, data: { id: "a1" } });
    expect(fetchMock).toHaveBeenCalledWith("/x", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ a: 1 }) });
  });
});
```

- [ ] **Step 2: RED** — `npm --prefix apps/web run test -- tests/lib/apiErrors.test.ts` → `sendJson is not a function`/import error.

- [ ] **Step 3: Implement** (append to `apiErrors.ts`)

```ts
export type SendOutcome = { ok: true; data: Record<string, unknown> } | { ok: false; message: string };

// ENH-022: one JSON write for the older School panels. Never throws: a dropped network is NOT_COMPLETED (the entry is kept),
// any error response carries the server's `detail` -- e.g. a partnership-tier 403 -- worded by detailMessage.
export async function sendJson(url: string, method: "POST" | "PATCH", body: unknown): Promise<SendOutcome> {
  let response: Response;
  try {
    response = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  } catch {
    return { ok: false, message: NOT_COMPLETED };
  }
  const data = await response.json().catch(() => null);
  if (!response.ok) return { ok: false, message: detailMessage(data?.detail) };
  return { ok: true, data: data && typeof data === "object" ? data : {} };
}
```

- [ ] **Step 4: GREEN**, then **Step 5: Commit** — `feat(enh-022): sendJson for the school panels' error path`

---

### Task 10: Frontend — six panels use `sendJson`, alert on failure, message beside its form

**Files:** Modify `SchoolActivitiesPanel.tsx`, `SchoolCareerRecordsPanel.tsx`, `SchoolPsychometricRecordsPanel.tsx`, `SchoolTestPrepLanguagePanel.tsx`, `AdminSchoolApplicationsPanel.tsx`, `CounselorVisaPanel.tsx`. Test: one `apps/web/tests/components/<Panel>.test.tsx` each.

**Common change per panel** (behavior on success unchanged):
1. Delete the local `detailMessage` copy; `import { sendJson } from "@/lib/apiErrors";` (plus `detailMessage` only where a remaining GET still uses it — `AdminSchoolApplicationsPanel.lookupStudent`).
2. Replace each write's `fetch` + `response.json()` + `if (!response.ok)` block with:
```ts
const result = await sendJson(url, "POST", body);
setBusy(false);
if (!result.ok) {
  setMessage({ text: result.message, failed: true, form: "<form key>" });
  return;
}
// existing success lines, reading `result.data` where they read `data`
```
3. Message state gains `form` in panels with several forms (`SchoolActivitiesPanel`: `"schedule" | "attendance"`; `SchoolPsychometricRecordsPanel`: `"assign" | "attach"`; `SchoolTestPrepLanguagePanel`: `"testprep" | "language"`, where the table-row actions `recordActualScore`/`markCertified` use their section's key). The single panel-level message block moves into each form's `action-card`, directly after its submit button, rendered only for its own key. `SchoolCareerRecordsPanel` and `AdminSchoolApplicationsPanel` (one form) move the block inside the form's card after the submit button; `CounselorVisaPanel` already renders per application.
4. The rendered block becomes:
```tsx
<div className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live={message.failed ? "assertive" : "polite"}>
  {message.text}
</div>
```
5. On failure nothing is reset (`formElement.reset()` stays on the success path only).

- [ ] **Step 1: Failing tests** — `SchoolActivitiesPanel.test.tsx` (the pattern; the other five follow it against their own labels and URLs):

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolActivitiesPanel from "@/components/SchoolActivitiesPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const TIER_403 = "This school's Gold partnership does not include Monthly campus visits (requires Platinum or higher).";

function fillSchedule() {
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Campus visit" } });
  fireEvent.change(screen.getByLabelText(/date & time/i), { target: { value: "2026-10-01T10:00" } });
  fireEvent.change(screen.getByLabelText(/entitlement category/i), { target: { value: "campus_visit" } });
  fireEvent.click(screen.getByRole("button", { name: "Schedule activity" }));
}

describe("SchoolActivitiesPanel error path (ENH-022)", () => {
  it("shows the tier 403 as an alert inside the schedule card and keeps the input", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: TIER_403 }) }));
    render(<SchoolActivitiesPanel activities={[]} students={[]} />);
    fillSchedule();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(TIER_403);
    const card = screen.getByRole("heading", { name: "Schedule an activity" }).closest(".action-card") as HTMLElement;
    expect(within(card).getByRole("alert")).toBe(alert);
    expect(screen.getByLabelText("Title")).toHaveValue("Campus visit");
  });

  it("recovers from a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<SchoolActivitiesPanel activities={[]} students={[]} />);
    fillSchedule();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByRole("button", { name: "Schedule activity" })).toBeEnabled();
  });

  it("announces success politely", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "a1", title: "Campus visit" }) }));
    render(<SchoolActivitiesPanel activities={[]} students={[]} />);
    fillSchedule();
    expect(await screen.findByRole("status")).toHaveTextContent("Campus visit scheduled.");
  });
});
```
For each other panel write the same three cases against its primary write (Career: "Save record"; Psychometric: "Assign assessment"; TestPrep: "Start preparation"; AdminSchoolApplications: stub the lookup GET to return a student first, then "Start application"; CounselorVisa: stub the counselor applications GET to return one row, then "Start visa case"), plus for multi-form panels one assertion that the alert is **not** inside the other form's card.

- [ ] **Step 2: RED** — `npm --prefix apps/web run test -- tests/components/SchoolActivitiesPanel.test.tsx` (etc.) → fails: no `role="alert"` (current `role="status"`) and the network case leaves the button on "Scheduling…".

- [ ] **Step 3: Implement** the common change in each panel, one panel at a time, rerunning its test.

- [ ] **Step 4: GREEN + regression** — `npm --prefix apps/web run test` (whole unit suite), `npm --prefix apps/web run lint`, `npx --prefix apps/web tsc --noEmit -p apps/web`.

- [ ] **Step 5: Commit** — one commit per panel: `fix(enh-022): <Panel> shows save failures as an alert beside its form`

---

### Task 11 [Stack]: E2E — Platinum fixtures + new tier spec

**Files:** Modify `sch-004-005-006-service-delivery`, `sch-007`, `sch-008`, `sch-009`, `sch-010`, `enh-002`, `enh-011`, `enh-012` specs (the admin create-school step); Create `apps/web/tests/e2e/enh-022-tier-enforcement.spec.ts`.

- [ ] **Step 1:** In each listed spec, before clicking `Create school + seed Coordinator`, add `await page.selectOption("#school-tier", "platinum");`.
- [ ] **Step 2: New spec** — reuse the create-school + activate pattern from `enh-011-skills.spec.ts` (`createAndActivateFromUi`), selecting **Bronze**; log in as the new coordinator; on `/school/coordinator/activities` schedule "Campus visit" with category "Monthly campus visit" → expect `getByRole("alert")` to contain `does not include Monthly campus visits (requires Platinum or higher)` and the Title field to keep its value; then schedule "Career seminar" with category "Career seminar" → expect `getByRole("status")` to contain `scheduled.`; repeat at 390×844 viewport and assert the alert is within the viewport after scrolling it into view.
- [ ] **Step 3:** Run (user-started stack): `cd apps/web && npx playwright test tests/e2e/enh-022-tier-enforcement.spec.ts tests/e2e/sch-*.spec.ts tests/e2e/enh-00*.spec.ts tests/e2e/enh-01*.spec.ts --workers=1`.
- [ ] **Step 4: Commit** — `test(enh-022): e2e tier enforcement; school-creating specs pick Platinum`

---

### Task 12: Documentation

- [ ] `docs/decisions/PRODUCT_DECISION_REGISTER.md`: add `DEC-SCOPE-027` with D1–D12 (copy the spec §3 table), status `EXPLICIT_APPROVAL (user, 2026-09-23)`.
- [ ] `docs/architecture/API_CONTRACT.md`: addendum "2026-09-23 (`ENH-022` / `DEC-SCOPE-027`)" — the §7 route list, the three `403` strings, check order, denial audit, retry note.
- [ ] `docs/architecture/RBAC_MATRIX.md`: tier as an additional dimension on the §7 actions (note `school_coordinator` etc. are now also tier-bounded).
- [ ] `RTM.md` + `ENHANCEMENT_BACKLOG.md`: ENH-022 status `IMPLEMENTED — pending browser validation and independent review`; add two follow-up items (dedicated-counselor model/enforcement; `/entitlements` reflecting expiry) and the pre-deploy data check query:
  `SELECT id, name, tier, tier_valid_until FROM schools WHERE tier IS NULL OR tier_valid_until < (now() AT TIME ZONE 'Asia/Kolkata')::date;`
- [ ] Commit — `docs(enh-022): decision, contract, RBAC, RTM and backlog updates`

---

## Self-review

- **Spec coverage:** §5 helper/strings → T1; §6 order/compat → Global Constraints + each task; §7 routes → T2 (activities ×2), T3 (career, psychometric ×2), T4 (test-prep ×2, language ×2), T5 (skills ×8), T6 (portfolio ×4), T7 (bridge, visa ×2) = 24 routes; §8 transactions/audit → T1 tests + per-route "row unchanged + denial count"; §9 frontend → T9–T10; AC-1…AC-10 → T1–T10; AC-8 → T8; §12 E2E → T11; §13 docs → T12; §15 security (order, no oracle, fail-closed, audit fields) → T1 + out-of-scope tests in T2/T3/T5.
- **Placeholders:** none; the five non-exemplar panel tests are specified by exact labels and stubs.
- **Type consistency:** `require_school_entitlement(db, user, school_id, service_key)` used identically in T2–T7; `TEST_PREP_SERVICE_KEYS`/`ACTIVITY_SERVICE_KEYS` defined in T1; `sendJson`/`SendOutcome` defined in T9, used in T10.
