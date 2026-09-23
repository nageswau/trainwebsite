# ENH-023 Partnership Tier Change Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a school's partnership tier change a recorded, notified business event, and let work started before a downgrade be finished while new work for a lost service stays refused.

**Architecture:** `update_school` (admin.py) locks the school row, records the full transition in the existing `school.tier_update` audit row (timestamped with `clock_timestamp()`), returns an additive `tier_change`, and notifies the school after commit. `require_school_entitlement` (schools.py, from ENH-022) gains an optional `grandfathered_since`; a would-be denial is lifted when a transition row after that time lists the service as lost. The 15 "finish existing work" routes pass their record's `created_at`. The admin edit panel gains tier fields with a preview-then-confirm downgrade step, and principals get a notifications page.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL (asyncpg), pytest + pytest-asyncio + httpx; Next.js (App Router), React, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-23-enh-023-tier-change-design.md`

## Global Constraints

- No migration, no new table, no new dependency (spec D4, §8).
- `TIER_ORDER`, `TIER_SERVICES`, `_cumulative_services`, `_entitlement_denial`, ENH-022's three `403` strings, its denial audit and `GET /school/entitlements` stay unchanged.
- `require_school_entitlement` called **without** `grandfathered_since` must behave byte-for-byte as today; `tests/test_enh_022_tier_enforcement.py` and `tests/test_enh_022_tier_rules.py` must pass **without edits** (AC-13).
- Only the 15 routes in spec §6 pass `grandfathered_since`. Create routes, new enrolments, new visa cases, bridged applications, portfolio entry create and career goal never do.
- An `expired` denial is never grandfathered (D6).
- Audit action string: `school.tier_update` (constant `TIER_UPDATE`). Metadata keys exactly: `tier`, `from_tier`, `to_tier`, `direction`, `gained`, `lost`, `tier_valid_until`, `previous_tier_valid_until`.
- `direction` values exactly: `upgrade`, `downgrade`, `unchanged`.
- Errors stay FastAPI `{"detail": "<string>"}`; no `error_code` shape and no `Idempotency-Key`/ETag (neither is contracted).
- `expected_tier` (D12) is optional; when present and different from the locked row's tier → `409` with exactly `This school's tier changed to {Current} since you looked it up. Look it up again before changing the tier.` When absent → today's behaviour.
- `""` for `tier`/`expected_tier`/preview `tier` is normalised to `null` (D13).
- The PATCH declares `response_model=SchoolUpdateOut`, the preview `response_model=TierChangeOut` (both in `schemas.py`).
- Notifications only when `direction != "unchanged"`, only after the tier change commits, each recipient isolated so a failure never fails the PATCH.
- Notification titles are cut to 180 characters (`Notification.title` is `String(180)`).
- The edit panel keeps the exact text `School profile updated.` (the `sch-003` E2E asserts it).
- Frontend uses only existing classes (`form-error`, `form-message`, `form-warning`, `btn`, `btn secondary`, `field`, `form`, `form-grid`, `action-card`); no CSS changes.
- Logs and audit metadata hold IDs, role, tier names and service keys only; no names, emails or request bodies.
- The Docker stack is started by the user. Backend tests need the database up; ask the user to start it rather than starting it yourself.
- Backend tests: `cd apps/api && pytest <file> -v`. Frontend: `cd apps/web && npx vitest run <file>`. E2E: `cd apps/web && npx playwright test <file>`.

## Review Focus

- **Admin edits a field after the downgrade confirmation appears.** Confirm must not send the stale body. Any form change clears the confirmation (Task 9, test `editing the form after the confirmation clears it`).
- **School name near 200 characters.** The admin copy's title would exceed `String(180)` and the notification insert would fail silently. Titles are truncated (Task 4, test `test_long_school_name_is_cut_to_the_title_limit`).
- **Removal via "Not set".** The preview must be called with an empty tier and show every lost service; the PATCH must send `tier: null` (Task 3 `test_preview_empty_tier_means_removal`, Task 9 `removing the tier asks for confirmation`).
- **Free-text activity after a tier removal.** Attendance on an activity with no `activity_type` must be grandfathered by the removal row (Task 5, `test_free_text_activity_attendance_survives_removal`).
- **Downgrade combined with expiry in one PATCH.** Grandfathering must not revive an expired partnership (Task 5, `test_expired_school_is_refused_even_on_grandfathered_work`).

---

## File structure

| File | Responsibility | Tasks |
|---|---|---|
| `apps/api/app/api/schools.py` | `TIER_UPDATE`, `_tier_name`, `_tier_transition`, `tier_change_payload`, `_grandfathers`, `_lost_since`, `_is_grandfathered`, `require_school_entitlement(…, grandfathered_since=)`; anchors on 4 routes | 1, 5 |
| `apps/api/app/api/admin.py` | `update_school` (lock, `expected_tier` 409, `""` normalisation, metadata, response, notify), preview route, `_tier_notices`, `_notify_tier_change` | 2, 3, 4 |
| `apps/api/app/schemas.py` | `SchoolUpdate.expected_tier`; `TierChangeService`, `TierChangeOut`, `SchoolUpdateOut` | 2 |
| `apps/api/app/api/school_skills.py` | `_require_module_entitlement(…, grandfathered_since=)`; anchors on 6 routes | 6 |
| `apps/api/app/api/portfolio.py` | anchors on 3 routes (entry lookup moves before the tier check) | 7 |
| `apps/api/app/api/workflows.py` | `_require_bridged_visa_entitlement(…, grandfathered_since=)`; anchor on `update_visa` | 7 |
| `apps/api/tests/test_enh_023_tier_rules.py` (new) | Pure unit tests, no database | 1, 4, 5 |
| `apps/api/tests/test_enh_023_tier_change.py` (new) | Database integration tests | 2–8 |
| `apps/api/tests/test_sch_003_school_onboarding.py` | Two metadata assertions updated to the D4 shape | 2 |
| `apps/web/components/AdminSchoolEditPanel.tsx` | Tier fields, preview/confirm flow, alert role | 9 |
| `apps/web/tests/components/AdminSchoolEditPanel.test.tsx` | Extended | 9 |
| `apps/web/app/school/principal/notifications/page.tsx` (new) | Principal notifications page | 10 |
| `apps/web/tests/components/SchoolPrincipalNotificationsPage.test.tsx` (new) | Page access tests | 10 |
| `apps/web/lib/navigation.ts` | Principal nav gains `notifications` | 10 |
| `apps/web/app/school/coordinator/notifications/page.tsx` | Empty text mentions partnership changes | 10 |
| `apps/web/tests/e2e/enh-023-tier-change.spec.ts` (new) | End-to-end downgrade + notifications | 11 |
| `docs/…` | Decision, contract, RBAC, RTM, backlog, screens, nav | 12 |

---

### Task 1: Tier transition helpers

**Files:**
- Modify: `apps/api/app/api/schools.py` (after `SERVICE_LABELS = …`, around line 847)
- Test: `apps/api/tests/test_enh_023_tier_rules.py` (create)

**Interfaces:**
- Produces:
  - `TIER_UPDATE: str = "school.tier_update"`
  - `_tier_name(tier: str | None) -> str`
  - `_tier_transition(old: str | None, new: str | None) -> tuple[str, list[str], list[str]]` → `(direction, gained_keys, lost_keys)`
  - `tier_change_payload(old: str | None, new: str | None) -> dict` → `{"direction", "from_tier", "to_tier", "gained": [{"key","label"}], "lost": [{"key","label"}]}`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_enh_023_tier_rules.py`:

```python
"""ENH-023 (DEC-SCOPE-029) -- tier-change rules and grandfathering, without a database."""

import pytest

from app.api.schools import TIER_SERVICES, TIER_UPDATE, _tier_name, _tier_transition, tier_change_payload

BRONZE = [k for k, _ in TIER_SERVICES["bronze"]]
SILVER = [k for k, _ in TIER_SERVICES["silver"]]
GOLD = [k for k, _ in TIER_SERVICES["gold"]]
PLATINUM = [k for k, _ in TIER_SERVICES["platinum"]]


def test_action_name_is_the_existing_tier_update_action():
    assert TIER_UPDATE == "school.tier_update"


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        (None, "bronze", ("upgrade", BRONZE, [])),
        ("gold", "platinum", ("upgrade", PLATINUM, [])),
        (None, "gold", ("upgrade", BRONZE + SILVER + GOLD, [])),
        ("platinum", "gold", ("downgrade", [], PLATINUM)),
        ("silver", None, ("downgrade", [], BRONZE + SILVER)),
        ("platinum", "bronze", ("downgrade", [], SILVER + GOLD + PLATINUM)),
        ("gold", "gold", ("unchanged", [], [])),
        (None, None, ("unchanged", [], [])),
        ("diamond", "bronze", ("upgrade", BRONZE, [])),
    ],
)
def test_tier_transition_truth_table(old, new, expected):
    assert _tier_transition(old, new) == expected


def test_tier_name_capitalises_and_names_the_absence_of_a_tier():
    assert _tier_name("gold") == "Gold"
    assert _tier_name(None) == "no partnership tier"
    assert _tier_name("diamond") == "no partnership tier"


def test_tier_change_payload_carries_labels_in_tier_services_order():
    payload = tier_change_payload("platinum", "gold")
    assert payload["direction"] == "downgrade"
    assert (payload["from_tier"], payload["to_tier"]) == ("platinum", "gold")
    assert payload["gained"] == []
    assert payload["lost"][0] == {"key": "dedicated_counselor", "label": "Dedicated EduSphere counselor"}
    assert [s["key"] for s in payload["lost"]] == PLATINUM
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/api && pytest tests/test_enh_023_tier_rules.py -v`
Expected: FAIL with `ImportError: cannot import name 'TIER_UPDATE'`

- [ ] **Step 3: Implement**

In `apps/api/app/api/schools.py`, directly after the `SERVICE_LABELS = …` line, add:

```python
TIER_UPDATE = "school.tier_update"


def _tier_name(tier: str | None) -> str:
    return tier.capitalize() if tier in TIER_ORDER else "no partnership tier"


def _tier_transition(old: str | None, new: str | None) -> tuple[str, list[str], list[str]]:
    """ENH-023 / DEC-SCOPE-029: (direction, gained keys, lost keys). Built only from `_cumulative_services`, so tier ordering
    lives in one place; an unknown or None tier has no services. Tiers are cumulative, so a change never both gains and loses."""
    before = [key for key, _ in _cumulative_services(old)]
    after = [key for key, _ in _cumulative_services(new)]
    gained = [key for key in after if key not in before]
    lost = [key for key in before if key not in after]
    return ("upgrade" if gained else "downgrade" if lost else "unchanged"), gained, lost


def tier_change_payload(old: str | None, new: str | None) -> dict:
    """The `tier_change` object returned by the tier PATCH and its preview (ENH-023 spec §4.2)."""
    direction, gained, lost = _tier_transition(old, new)
    return {
        "direction": direction,
        "from_tier": old,
        "to_tier": new,
        "gained": [{"key": key, "label": SERVICE_LABELS[key]} for key in gained],
        "lost": [{"key": key, "label": SERVICE_LABELS[key]} for key in lost],
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_023_tier_rules.py tests/test_enh_022_tier_rules.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_023_tier_rules.py
git commit -m "feat(enh-023): tier transition helpers"
```

---

### Task 2: Record the transition on the tier PATCH

**Files:**
- Modify: `apps/api/app/schemas.py` — `SchoolUpdate` (add `expected_tier`); new classes after `SchoolOut` (line ~1259)
- Modify: `apps/api/app/api/admin.py` — `update_school` (around lines 1139-1167)
- Modify: `apps/api/tests/test_sch_003_school_onboarding.py:427-463` (two metadata assertions)
- Test: `apps/api/tests/test_enh_023_tier_change.py` (create)

**Interfaces:**
- Consumes: `TIER_UPDATE`, `tier_change_payload`, `_tier_name` (Task 1)
- Produces:
  - `schemas.TierChangeService(key: str, label: str)`
  - `schemas.TierChangeOut(direction: Literal["upgrade","downgrade","unchanged"], from_tier: str | None, to_tier: str | None, gained: list[TierChangeService], lost: list[TierChangeService])`
  - `schemas.SchoolUpdateOut(SchoolOut)` + `tier_change: TierChangeOut | None`
  - `SchoolUpdate.expected_tier: str | None = None`
  - PATCH response typed as `SchoolUpdateOut`; audit metadata per Global Constraints; audit `created_at = clock_timestamp()`.
  - Task 3 uses `TierChangeOut`; Task 9 sends `expected_tier`; Task 4 inserts the notification call where marked.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/tests/test_enh_023_tier_change.py`:

```python
"""ENH-023 (DEC-SCOPE-029) -- tier changes and grandfathered work against a real database."""

from datetime import date, timedelta
from uuid import UUID

import pytest
from enh005_helpers import login, mk_school, mk_staff
from sqlalchemy import func, select

from app.api.schools import TIER_DENIED, TIER_SERVICES, TIER_UPDATE
from app.models import AuditLog

SCHOOLS = "/api/v1/overseas-admin/schools"
PLATINUM = [k for k, _ in TIER_SERVICES["platinum"]]
EXPIRED_ON = date.today() - timedelta(days=2)
NO_TIER = "This school has no active partnership tier."


async def world(db, tier, staff_role=None, students=1) -> dict:
    w = await mk_school(db, label="T23", tier=tier, students=students)
    if staff_role:
        w["staff"] = await mk_staff(db, w["school"], w["admin"], role=staff_role)
    return w


async def change_tier(client, w, **body) -> dict:
    """PATCH the tier as the school's Overseas Admin (the only sanctioned tier change)."""
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def tier_rows(db, school_id) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.action == TIER_UPDATE, AuditLog.entity_id == str(school_id)).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


async def denials(db, school_id) -> int:
    return await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == TIER_DENIED, AuditLog.entity_id == str(school_id)))


# --- The transition record (AC-1..AC-4, AC-9) ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_downgrade_records_the_transition_and_returns_tier_change(client, db_session):
    w = await world(db_session, "platinum")
    body = await change_tier(client, w, tier="gold")
    assert body["tier"] == "gold"
    assert body["tier_change"]["direction"] == "downgrade"
    assert [s["key"] for s in body["tier_change"]["lost"]] == PLATINUM
    [row] = await tier_rows(db_session, w["school"].id)
    assert row.metadata_json == {
        "tier": "gold", "from_tier": "platinum", "to_tier": "gold", "direction": "downgrade",
        "gained": [], "lost": PLATINUM, "tier_valid_until": None, "previous_tier_valid_until": None,
    }


@pytest.mark.asyncio
async def test_upgrade_records_gained_services(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="platinum")
    assert body["tier_change"]["direction"] == "upgrade"
    [row] = await tier_rows(db_session, w["school"].id)
    assert (row.metadata_json["from_tier"], row.metadata_json["gained"], row.metadata_json["lost"]) == ("gold", PLATINUM, [])


@pytest.mark.asyncio
async def test_same_tier_and_valid_until_only_are_unchanged(client, db_session):
    w = await world(db_session, "gold")
    same = await change_tier(client, w, tier="gold")
    only_date = await change_tier(client, w, tier_valid_until="2027-03-31")
    assert same["tier_change"]["direction"] == only_date["tier_change"]["direction"] == "unchanged"
    rows = await tier_rows(db_session, w["school"].id)
    assert [r.metadata_json["direction"] for r in rows] == ["unchanged", "unchanged"]
    assert rows[1].metadata_json["tier_valid_until"] == "2027-03-31"
    assert rows[1].metadata_json["previous_tier_valid_until"] is None


@pytest.mark.asyncio
async def test_profile_only_patch_has_no_tier_change(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, branch="North")
    assert body["tier_change"] is None
    assert body["branch"] == "North"
    assert await tier_rows(db_session, w["school"].id) == []


@pytest.mark.asyncio
async def test_down_then_up_keeps_both_transitions(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier="platinum")
    rows = await tier_rows(db_session, w["school"].id)
    assert [(r.metadata_json["from_tier"], r.metadata_json["to_tier"]) for r in rows] == [("platinum", "gold"), ("gold", "platinum")]


@pytest.mark.asyncio
async def test_invalid_tier_is_still_422_and_records_nothing(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "diamond"})
    assert (r.status_code, r.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")
    assert await tier_rows(db_session, w["school"].id) == []


# --- Precondition, empty string, typed contract (D12, D13, AC-15..AC-17) ----------------------------------------------


@pytest.mark.asyncio
async def test_stale_expected_tier_is_409_and_writes_nothing(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["admin"].email)
    r = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold", "expected_tier": "bronze"})
    assert r.status_code == 409
    assert r.json()["detail"] == "This school's tier changed to Platinum since you looked it up. Look it up again before changing the tier."
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"
    assert await tier_rows(db_session, w["school"].id) == []


@pytest.mark.asyncio
async def test_matching_expected_tier_saves_and_is_not_a_profile_field(client, db_session):
    w = await world(db_session, "platinum")
    body = await change_tier(client, w, tier="gold", expected_tier="platinum")
    assert body["tier_change"]["direction"] == "downgrade"
    profile_rows = await db_session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "school.profile_update", AuditLog.entity_id == str(w["school"].id)))
    assert profile_rows == 0


@pytest.mark.asyncio
async def test_expected_tier_empty_string_means_tierless(client, db_session):
    w = await world(db_session, None)
    body = await change_tier(client, w, tier="bronze", expected_tier="")
    assert body["tier_change"]["direction"] == "upgrade"
    await login(client, w["admin"].email)
    bad = await client.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold", "expected_tier": "diamond"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")


@pytest.mark.asyncio
async def test_empty_string_tier_is_stored_as_a_removal(client, db_session):
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="")
    assert body["tier"] is None
    assert body["tier_change"]["to_tier"] is None
    [row] = await tier_rows(db_session, w["school"].id)
    assert (row.metadata_json["to_tier"], row.metadata_json["tier"], row.metadata_json["direction"]) == (None, None, "downgrade")


@pytest.mark.asyncio
async def test_openapi_documents_the_typed_tier_change(client):
    spec = (await client.get("/openapi.json")).json()
    patch = spec["paths"]["/api/v1/overseas-admin/schools/{school_id}"]["patch"]
    assert patch["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/SchoolUpdateOut")
    direction = spec["components"]["schemas"]["TierChangeOut"]["properties"]["direction"]
    assert set(direction["enum"]) == {"upgrade", "downgrade", "unchanged"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py -v`
Expected: FAIL — `KeyError: 'tier_change'`, metadata mismatches, `422` for the unknown `expected_tier` field (`extra="forbid"`), and a missing `SchoolUpdateOut` in OpenAPI (the app serves FastAPI's default `/openapi.json`).

- [ ] **Step 3: Add the schemas**

In `apps/api/app/schemas.py`, add one field to `SchoolUpdate` directly after `tier_valid_until: date | None = None`:

```python
    # ENH-023 D12: optional precondition -- the tier the caller last saw. A mismatch under the row lock is a 409, so a
    # stale preview can never turn into an unconfirmed downgrade. Omitted = no precondition (backward compatible).
    expected_tier: str | None = None
```

and add after the `SchoolOut` class:

```python
class TierChangeService(BaseModel):
    key: str
    label: str


class TierChangeOut(BaseModel):
    """ENH-023 -- a tier change's effect, from the tier PATCH (`tier_change`) and its preview."""

    direction: Literal["upgrade", "downgrade", "unchanged"]
    from_tier: str | None
    to_tier: str | None
    gained: list[TierChangeService]
    lost: list[TierChangeService]


class SchoolUpdateOut(SchoolOut):
    """`SchoolOut` plus the additive `tier_change` (null when the body carried no tier field)."""

    tier_change: TierChangeOut | None = None
```

- [ ] **Step 4: Implement `update_school`**

Add `SchoolUpdateOut` to the `from app.schemas import …` line in `admin.py`, change the decorator to
`@agents_router.patch("/schools/{school_id}", response_model=SchoolUpdateOut)`, and replace the function body (keep the signature) with:

```python
    """DEC-SCOPE-017 / ENH-009 (DEC-SCOPE-025) -- Overseas Admin updates a School's partnership
    tier and/or profile fields. `name`/`city`/`state`/`coordinator_*` stay out of scope for this
    endpoint -- they were never editable before and no acceptance criterion asks for that.
    ENH-023 (DEC-SCOPE-029): a tier change is recorded as a transition (old -> new, gained/lost), returned as
    `tier_change`, guarded by the optional `expected_tier` precondition (D12), and told to the school after the commit."""
    from app.api.schools import TIER_UPDATE, _tier_name, tier_change_payload  # noqa: PLC0415 -- lazy, like the bridge import below

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    # ENH-023 §8: the row lock queues concurrent tier changes, so each one's `from_tier` is the tier committed before it.
    school = await db.scalar(select(School).where(School.id == school_id).with_for_update())
    if not school:
        raise HTTPException(404, "School not found")
    fields = payload.model_dump(exclude_unset=True)
    for key in ("tier", "expected_tier"):  # D13: "" is no tier, stored and compared as null
        if key in fields:
            fields[key] = fields[key] or None
            if fields[key] is not None and fields[key] not in {"bronze", "silver", "gold", "platinum"}:
                raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
    if "expected_tier" in fields and fields.pop("expected_tier") != school.tier:
        # D12, checked under the lock: the tier moved since the caller looked, so what they confirmed is not what would happen.
        raise HTTPException(409, f"This school's tier changed to {_tier_name(school.tier)} since you looked it up. Look it up again before changing the tier.")
    old_tier, old_valid_until = school.tier, school.tier_valid_until
    if "tier" in fields:
        school.tier = fields["tier"]
    if "tier_valid_until" in fields:
        school.tier_valid_until = fields["tier_valid_until"]
    tier_change = None
    if "tier" in fields or "tier_valid_until" in fields:
        tier_change = tier_change_payload(old_tier, school.tier)
        metadata = {
            "tier": school.tier,
            "from_tier": old_tier,
            "to_tier": school.tier,
            "direction": tier_change["direction"],
            "gained": [s["key"] for s in tier_change["gained"]],
            "lost": [s["key"] for s in tier_change["lost"]],
            "tier_valid_until": school.tier_valid_until.isoformat() if school.tier_valid_until else None,
            "previous_tier_valid_until": old_valid_until.isoformat() if old_valid_until else None,
        }
        # clock_timestamp(), not the transaction-start now(): a record created by a transaction that still saw the old tier
        # sorts before this row, so grandfathering (schools._lost_since) treats it as existing work (ENH-023 §8).
        db.add(AuditLog(user_id=user.id, action=TIER_UPDATE, entity_type="school", entity_id=str(school.id), metadata_json=metadata, created_at=func.clock_timestamp()))
    profile_fields = [k for k in fields if k not in {"tier", "tier_valid_until"}]
    for key in profile_fields:
        setattr(school, key, fields[key])
    if profile_fields:
        db.add(AuditLog(user_id=user.id, action="school.profile_update", entity_type="school", entity_id=str(school.id), metadata_json={"changed_fields": sorted(profile_fields)}))
    await db.commit()
    out = await _school_out(db, school)
    # Task 4 inserts the post-commit notification call here.
    return {**out.model_dump(mode="json"), "tier_change": tier_change}
```

Then update the two pinned assertions in `apps/api/tests/test_sch_003_school_onboarding.py` (the D4 contract change; the schools there start tier-less):

In `test_patch_school_tier_only_still_works_unchanged`, replace `assert tier_log.metadata_json == {"tier": "gold"}` with:

```python
    # ENH-023 (DEC-SCOPE-029 D4): the row now records the whole transition, not just the new tier.
    assert tier_log.metadata_json == {
        "tier": "gold", "from_tier": None, "to_tier": "gold", "direction": "upgrade",
        "gained": ["career_seminar", "career_awareness_session", "parent_orientation", "psychometric_test", "soft_skills",
                   "individual_counselling", "web_designing",
                   "application_support", "scholarship_assistance", "ielts_coaching", "sat_coaching", "foreign_language_classes", "digital_portfolio_creation"],
        "lost": [], "tier_valid_until": "2027-01-01", "previous_tier_valid_until": None,
    }
```

In `test_patch_school_with_tier_and_profile_fields_logs_both_audit_rows`, replace `assert tier_logs[0].metadata_json == {"tier": "silver"}` with:

```python
    assert tier_logs[0].metadata_json == {
        "tier": "silver", "from_tier": None, "to_tier": "silver", "direction": "upgrade",
        "gained": ["career_seminar", "career_awareness_session", "parent_orientation", "psychometric_test", "soft_skills",
                   "individual_counselling", "web_designing"],
        "lost": [], "tier_valid_until": None, "previous_tier_valid_until": None,
    }
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py tests/test_sch_003_school_onboarding.py tests/test_sch_011_entitlements.py tests/test_enh_009_school_profile_schemas.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/api/admin.py apps/api/tests/test_enh_023_tier_change.py apps/api/tests/test_sch_003_school_onboarding.py
git commit -m "feat(enh-023): record tier transitions, typed tier_change, expected_tier precondition"
```

---

### Task 3: Tier-change preview endpoint

**Files:**
- Modify: `apps/api/app/api/admin.py` (new route directly after `update_school`)
- Test: `apps/api/tests/test_enh_023_tier_change.py` (append)

**Interfaces:**
- Consumes: `TIER_ORDER`, `tier_change_payload` (Task 1); `TierChangeOut` (Task 2)
- Produces: `GET /api/v1/overseas-admin/schools/{school_id}/tier-change-preview?tier=<tier>` → `TierChangeOut`; empty or absent `tier` = removal. Task 9 calls it.

- [ ] **Step 1: Write the failing tests** (append)

```python
# --- Preview (AC-5) ----------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_reports_a_downgrade_and_writes_nothing(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["admin"].email)
    r = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "gold"})
    assert r.status_code == 200
    assert r.json()["direction"] == "downgrade"
    assert [s["key"] for s in r.json()["lost"]] == PLATINUM
    assert await tier_rows(db_session, w["school"].id) == []
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"


@pytest.mark.asyncio
async def test_preview_empty_tier_means_removal(client, db_session):
    w = await world(db_session, "silver")
    await login(client, w["admin"].email)
    r = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": ""})
    assert (r.json()["direction"], r.json()["to_tier"]) == ("downgrade", None)
    assert len(r.json()["lost"]) == 7


@pytest.mark.asyncio
async def test_preview_errors(client, db_session):
    w = await world(db_session, "gold")
    await login(client, w["coordinator"].email)
    assert (await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "gold"})).status_code == 403
    await login(client, w["admin"].email)
    missing = await client.get(f"{SCHOOLS}/00000000-0000-0000-0000-000000000000/tier-change-preview", params={"tier": "gold"})
    assert missing.status_code == 404
    bad = await client.get(f"{SCHOOLS}/{w['school'].id}/tier-change-preview", params={"tier": "diamond"})
    assert (bad.status_code, bad.json()["detail"]) == (422, "tier must be one of bronze, silver, gold, platinum")
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py -v -k preview`
Expected: FAIL with 404/405 (route missing).

- [ ] **Step 3: Implement** (add `TierChangeOut` to the `from app.schemas import …` line, then add the route directly after `update_school` in `admin.py`)

```python
@agents_router.get("/schools/{school_id}/tier-change-preview", response_model=TierChangeOut)
async def preview_school_tier_change(school_id: UUID, tier: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-023 -- what a tier change would gain or lose, so the admin UI can confirm a downgrade before it happens. Read-only:
    no lock, no write. An empty or absent `tier` means removing the tier."""
    from app.api.schools import TIER_ORDER, tier_change_payload  # noqa: PLC0415 -- lazy, like update_school

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")
    new_tier = tier or None
    if new_tier is not None and new_tier not in TIER_ORDER:
        raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
    return tier_change_payload(school.tier, new_tier)
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_enh_023_tier_change.py
git commit -m "feat(enh-023): tier-change preview endpoint"
```

---

### Task 4: Notify the school and the acting admin

**Files:**
- Modify: `apps/api/app/api/admin.py` (two helpers above `update_school`; one call inside it)
- Test: `apps/api/tests/test_enh_023_tier_rules.py` (append), `apps/api/tests/test_enh_023_tier_change.py` (append)

**Interfaces:**
- Consumes: `_tier_name` (Task 1); `schools._notify_parent(db, user, *, school_name, title, body, action_url)` (existing)
- Produces: `_tier_notices(school_name: str, change: dict) -> tuple[tuple[str, str], tuple[str, str]]` → `((school_title, school_body), (admin_title, admin_body))`; `async _notify_tier_change(db, school_id: UUID, school_name: str, actor_id: UUID, change: dict) -> None`

- [ ] **Step 1: Write the failing unit tests** (append to `test_enh_023_tier_rules.py`)

```python
from app.api.admin import _tier_notices  # noqa: E402 -- grouped with the notice tests


def test_upgrade_notice_lists_what_became_available():
    (title, body), (admin_title, admin_body) = _tier_notices("Oak School", tier_change_payload("gold", "platinum"))
    assert title == "Your partnership is now Platinum"
    assert body.startswith("Oak School has moved from Gold to Platinum. Newly available: Dedicated EduSphere counselor, Monthly campus visits")
    assert admin_title == "Tier change recorded: Oak School, Gold → Platinum"
    assert admin_body.startswith("Newly available: Dedicated EduSphere counselor")


def test_downgrade_and_removal_notices_promise_completion():
    (title, body), (admin_title, _) = _tier_notices("Oak School", tier_change_payload("platinum", "gold"))
    assert title == "Your partnership changed from Platinum to Gold"
    assert body.startswith("These services are no longer available for new work: Dedicated EduSphere counselor")
    assert body.endswith("Work already started for them can still be completed.")
    (removed, _), _ = _tier_notices("Oak School", tier_change_payload("bronze", None))
    assert removed == "Your partnership changed from Bronze to no partnership tier"


def test_long_school_name_is_cut_to_the_title_limit():
    (_, _), (admin_title, _) = _tier_notices("S" * 200, tier_change_payload("gold", "platinum"))
    assert len(admin_title) == 180
```

- [ ] **Step 2: Write the failing integration tests** (append to `test_enh_023_tier_change.py`)

```python
from app.api import schools  # noqa: E402
from app.models import Notification, NotificationDelivery  # noqa: E402


async def notices_for(db, user_id) -> list[Notification]:
    return list((await db.scalars(select(Notification).where(Notification.user_id == user_id))).all())


# --- Notifications (AC-1..AC-3, AC-11) ---------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upgrade_notifies_coordinator_principal_and_admin_only(client, db_session):
    w = await world(db_session, "gold")
    await change_tier(client, w, tier="platinum")
    [coord] = await notices_for(db_session, w["coordinator"].id)
    [principal] = await notices_for(db_session, w["principal"].id)
    [admin] = await notices_for(db_session, w["admin"].id)
    assert coord.title == principal.title == "Your partnership is now Platinum"
    assert "Visa support" in coord.body
    assert (coord.action_url, principal.action_url) == ("/school/coordinator/entitlements", "/school/principal/entitlements")
    assert admin.title.startswith("Tier change recorded: ") and admin.action_url is None
    assert await notices_for(db_session, w["teacher"].id) == [] and await notices_for(db_session, w["parent"].id) == []
    delivered = await db_session.scalar(select(func.count()).select_from(NotificationDelivery).where(NotificationDelivery.notification_id == coord.id, NotificationDelivery.channel == "email"))
    assert delivered == 1


@pytest.mark.asyncio
async def test_downgrade_notice_lists_lost_services(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier=None)
    [coord] = await notices_for(db_session, w["coordinator"].id)
    assert coord.title == "Your partnership changed from Platinum to no partnership tier"
    assert "Work already started for them can still be completed." in coord.body


@pytest.mark.asyncio
async def test_unchanged_tier_notifies_nobody(client, db_session):
    w = await world(db_session, "gold")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier_valid_until="2027-03-31")
    assert await notices_for(db_session, w["coordinator"].id) == []
    assert await notices_for(db_session, w["admin"].id) == []


@pytest.mark.asyncio
async def test_failing_email_never_fails_or_undoes_the_tier_change(client, db_session, monkeypatch):
    async def boom(**_):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(schools, "send_parent_notification_email", boom)
    w = await world(db_session, "gold")
    body = await change_tier(client, w, tier="platinum")
    assert body["tier"] == "platinum"
    await db_session.refresh(w["school"])
    assert w["school"].tier == "platinum"
    assert len(await tier_rows(db_session, w["school"].id)) == 1
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd apps/api && pytest tests/test_enh_023_tier_rules.py tests/test_enh_023_tier_change.py -v -k "notice or notif or email"`
Expected: FAIL — `ImportError: cannot import name '_tier_notices'`, then no Notification rows.

- [ ] **Step 4: Implement**

Add above `update_school` in `admin.py`:

```python
NOTIFICATION_TITLE_MAX = 180  # Notification.title is String(180); a school name alone may be 200 (ENH-023 §9)
SCHOOL_ENTITLEMENTS_URL = {"school_coordinator": "/school/coordinator/entitlements", "school_principal": "/school/principal/entitlements"}


def _tier_notices(school_name: str, change: dict) -> tuple[tuple[str, str], tuple[str, str]]:
    """((school title, body), (admin title, body)) for a change that moved the tier (ENH-023 spec §4.4)."""
    from app.api.schools import _tier_name  # noqa: PLC0415

    before, after = _tier_name(change["from_tier"]), _tier_name(change["to_tier"])
    if change["direction"] == "upgrade":
        labels = ", ".join(s["label"] for s in change["gained"])
        school = (f"Your partnership is now {after}", f"{school_name} has moved from {before} to {after}. Newly available: {labels}.")
        admin_body = f"Newly available: {labels}."
    else:
        labels = ", ".join(s["label"] for s in change["lost"])
        school = (f"Your partnership changed from {before} to {after}", f"These services are no longer available for new work: {labels}. Work already started for them can still be completed.")
        admin_body = f"No longer available for new work: {labels}. Work already started for them can still be completed."
    admin_title = f"Tier change recorded: {school_name}, {before} → {after}"
    return (school[0][:NOTIFICATION_TITLE_MAX], school[1]), (admin_title[:NOTIFICATION_TITLE_MAX], admin_body)


async def _notify_tier_change(db: AsyncSession, school_id: UUID, school_name: str, actor_id: UUID, change: dict) -> None:
    """ENH-023 (D5/D9), for a tier change that has ALREADY committed: the school's active Coordinators and Principals, then the
    acting admin, each get an in-app notice plus the email channel. Each recipient is tried and committed alone; a failure is
    logged and swallowed, never undoing or failing the tier change (SCH-007-AC04 pattern, school_skills._notify_after_commit)."""
    from app.api.schools import _notify_parent  # noqa: PLC0415 -- takes any User: in-app row, email attempt, NotificationDelivery

    (school_title, school_body), (admin_title, admin_body) = _tier_notices(school_name, change)
    staff = (
        await db.execute(
            select(User.id, User.role).where(User.role.in_(list(SCHOOL_ENTITLEMENTS_URL)), User.active.is_(True), User.profile["school_id"].as_string() == str(school_id))
        )
    ).all()
    notices = [(user_id, school_title, school_body, SCHOOL_ENTITLEMENTS_URL[role]) for user_id, role in staff]
    notices.append((actor_id, admin_title, admin_body, None))
    for user_id, title, body, action_url in notices:
        try:
            recipient = await db.get(User, user_id, populate_existing=True)
            await _notify_parent(db, recipient, school_name=school_name, title=title, body=body, action_url=action_url)
            await db.commit()
        except Exception:  # noqa: BLE001 -- the tier change has committed; see docstring
            await db.rollback()
            logger.warning("tier_change_notification_failed", extra={"extra_fields": {"school_id": str(school_id), "recipient_id": str(user_id)}}, exc_info=True)
```

In `update_school`, replace the line `# Task 4 inserts the post-commit notification call here.` with:

```python
    if tier_change and tier_change["direction"] != "unchanged":
        await _notify_tier_change(db, school.id, school.name, user.id, tier_change)
```

(`out` is built before this call, so a rollback inside the notifier can never expire what the response needs.)

- [ ] **Step 5: Run to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_023_tier_rules.py tests/test_enh_023_tier_change.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/tests/test_enh_023_tier_rules.py apps/api/tests/test_enh_023_tier_change.py
git commit -m "feat(enh-023): notify the school and acting admin of tier changes"
```

---

### Task 5: Grandfathering in the enforcement check + the four schools.py routes

**Files:**
- Modify: `apps/api/app/api/schools.py` — new helpers beside `require_school_entitlement`; its signature; `mark_attendance`, `update_psychometric_record`, `update_test_prep_record`, `update_language_record`
- Test: `apps/api/tests/test_enh_023_tier_rules.py` (append), `apps/api/tests/test_enh_023_tier_change.py` (append)

**Interfaces:**
- Consumes: `TIER_UPDATE` (Task 1); transition rows written by Task 2
- Produces:
  - `_grandfathers(metadata: dict, service_key: str | None) -> bool`
  - `async _lost_since(db, school_id: UUID, service_key: str | None, since: datetime) -> bool`
  - `async _is_grandfathered(db, school, reason: str, service_key: str | None, since: datetime) -> bool`
  - `async require_school_entitlement(db, user, school_id, service_key, *, grandfathered_since: datetime | None = None) -> None`, used by Tasks 6 and 7

- [ ] **Step 1: Write the failing unit tests** (append to `test_enh_023_tier_rules.py`)

```python
from datetime import UTC, date, datetime  # noqa: E402
from types import SimpleNamespace  # noqa: E402
from uuid import uuid4  # noqa: E402

from fastapi import HTTPException  # noqa: E402
from test_enh_022_tier_rules import USER, FakeDB  # noqa: E402

from app.api import schools  # noqa: E402
from app.api.schools import _grandfathers, require_school_entitlement  # noqa: E402

TODAY = date(2026, 9, 23)
SINCE = datetime(2026, 9, 1, tzinfo=UTC)
DOWNGRADE = {"direction": "downgrade", "from_tier": "platinum", "to_tier": "gold", "lost": ["visa_support", "internships"]}
REMOVAL = {"direction": "downgrade", "from_tier": "bronze", "to_tier": None, "lost": ["career_seminar"]}


def test_grandfathers_matches_only_a_lost_service_of_a_downgrade():
    assert _grandfathers(DOWNGRADE, "visa_support")
    assert not _grandfathers(DOWNGRADE, "ielts_coaching")
    assert not _grandfathers({"direction": "upgrade", "lost": ["visa_support"]}, "visa_support")
    assert not _grandfathers({"tier": "gold"}, "visa_support")  # a row written before ENH-023


def test_free_text_work_is_grandfathered_only_by_a_removal():
    assert _grandfathers(REMOVAL, None)
    assert not _grandfathers(DOWNGRADE, None)


@pytest.mark.asyncio
async def test_grandfathered_write_is_allowed_with_no_denial_row(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)
    calls = []

    async def lost(db, school_id, key, since):
        calls.append((key, since))
        return True

    monkeypatch.setattr(schools, "_lost_since", lost)
    db = FakeDB(SimpleNamespace(id=uuid4(), tier="gold", tier_valid_until=None))
    await require_school_entitlement(db, USER, uuid4(), "visa_support", grandfathered_since=SINCE)
    assert db.added == [] and db.commits == 0
    assert calls == [("visa_support", SINCE)]


@pytest.mark.asyncio
async def test_without_an_anchor_the_lookup_never_runs(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)

    async def lost(*_):
        raise AssertionError("must not be called")

    monkeypatch.setattr(schools, "_lost_since", lost)
    db = FakeDB(SimpleNamespace(id=uuid4(), tier="gold", tier_valid_until=None))
    with pytest.raises(HTTPException):
        await require_school_entitlement(db, USER, uuid4(), "visa_support")
    assert db.commits == 1


@pytest.mark.asyncio
async def test_expired_is_never_grandfathered(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)

    async def lost(*_):
        return True

    monkeypatch.setattr(schools, "_lost_since", lost)
    expired = FakeDB(SimpleNamespace(id=uuid4(), tier="platinum", tier_valid_until=date(2026, 9, 1)))
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(expired, USER, uuid4(), "visa_support", grandfathered_since=SINCE)
    assert exc.value.detail.startswith("This school's partnership expired on")
    removed_after_expiry = FakeDB(SimpleNamespace(id=uuid4(), tier=None, tier_valid_until=date(2026, 9, 1)))
    with pytest.raises(HTTPException):
        await require_school_entitlement(removed_after_expiry, USER, uuid4(), "visa_support", grandfathered_since=SINCE)


@pytest.mark.asyncio
async def test_not_lost_after_the_anchor_is_still_denied(monkeypatch):
    monkeypatch.setattr(schools, "_today_ist", lambda: TODAY)

    async def lost(*_):
        return False

    monkeypatch.setattr(schools, "_lost_since", lost)
    db = FakeDB(SimpleNamespace(id=uuid4(), tier="gold", tier_valid_until=None))
    with pytest.raises(HTTPException) as exc:
        await require_school_entitlement(db, USER, uuid4(), "visa_support", grandfathered_since=SINCE)
    assert exc.value.status_code == 403 and db.commits == 1
```

- [ ] **Step 2: Write the failing integration tests** (append to `test_enh_023_tier_change.py`)

```python
from datetime import UTC, datetime  # noqa: E402

from app.models import SchoolLanguageRecord, SchoolTestPrepRecord  # noqa: E402


def activity(activity_type=None) -> dict:
    body = {"title": "Session", "scheduled_at": datetime.now(UTC).isoformat()}
    return body | ({"activity_type": activity_type} if activity_type else {})


def attendance(w) -> dict:
    return {"records": [{"student_id": str(w["students"][0].id), "present": True}]}


# --- Grandfathered work: activities and records (AC-6..AC-8) ----------------------------------------------------------


@pytest.mark.asyncio
async def test_campus_visit_scheduled_before_a_downgrade_can_still_take_attendance(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    await change_tier(client, w, tier="gold")
    await login(client, w["coordinator"].email)
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json=attendance(w))
    assert r.status_code == 200, r.text
    assert (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).status_code == 403  # new work
    assert await denials(db_session, w["school"].id) == 1


@pytest.mark.asyncio
async def test_free_text_activity_attendance_survives_removal(client, db_session):
    w = await world(db_session, "bronze")
    await login(client, w["coordinator"].email)
    free = (await client.post("/api/v1/school/activities", json=activity())).json()
    await change_tier(client, w, tier=None)
    await login(client, w["coordinator"].email)
    assert (await client.post(f"/api/v1/school/activities/{free['id']}/attendance", json=attendance(w))).status_code == 200
    r = await client.post("/api/v1/school/activities", json=activity())
    assert (r.status_code, r.json()["detail"]) == (403, NO_TIER)


@pytest.mark.asyncio
async def test_psychometric_record_survives_tier_removal(client, db_session):
    w = await world(db_session, "bronze", staff_role="psychometric_team")
    await login(client, w["staff"].email)
    body = {"school_student_id": str(w["students"][0].id), "assessment_type": "Aptitude"}
    record = (await client.post("/api/v1/school/psychometric-team/records", json=body)).json()
    await change_tier(client, w, tier=None)
    await login(client, w["staff"].email)
    patched = await client.patch(f"/api/v1/school/psychometric-team/records/{record['id']}", json={"report_url": "https://example.local/r.pdf"})
    assert patched.status_code == 200, patched.text
    assert (await client.post("/api/v1/school/psychometric-team/records", json=body)).status_code == 403


@pytest.mark.asyncio
async def test_test_prep_and_language_records_survive_downgrades(client, db_session):
    w = await world(db_session, "gold", staff_role="academic_team")
    await login(client, w["staff"].email)
    sid = str(w["students"][0].id)
    sat = (await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": sid, "test_type": "sat"})).json()
    german = (await client.post("/api/v1/school/academic-team/language-records", json={"school_student_id": sid, "language": "German"})).json()
    await change_tier(client, w, tier="bronze")
    await login(client, w["staff"].email)
    assert (await client.patch(f"/api/v1/school/academic-team/test-prep-records/{sat['id']}", json={"actual_score": "1400"})).status_code == 200
    assert (await client.patch(f"/api/v1/school/academic-team/language-records/{german['id']}", json={"certification_status": "certified"})).status_code == 200
    assert (await db_session.get(SchoolTestPrepRecord, UUID(sat["id"]), populate_existing=True)).actual_score == "1400"
    assert (await db_session.get(SchoolLanguageRecord, UUID(german["id"]), populate_existing=True)).certification_status == "certified"
    assert (await client.post("/api/v1/school/academic-team/test-prep-records", json={"school_student_id": sid, "test_type": "sat"})).status_code == 403


@pytest.mark.asyncio
async def test_expired_school_is_refused_even_on_grandfathered_work(client, db_session):
    w = await world(db_session, "platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    await change_tier(client, w, tier="gold", tier_valid_until=EXPIRED_ON.isoformat())
    await login(client, w["coordinator"].email)
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json=attendance(w))
    assert r.status_code == 403
    assert r.json()["detail"].startswith("This school's partnership expired on")


@pytest.mark.asyncio
async def test_work_created_after_the_downgrade_is_not_grandfathered(client, db_session):
    w = await world(db_session, "platinum")
    await change_tier(client, w, tier="gold")
    await change_tier(client, w, tier="platinum")
    await login(client, w["coordinator"].email)
    visit = (await client.post("/api/v1/school/activities", json=activity("campus_visit"))).json()
    w["school"].tier = "gold"  # a direct database change leaves no transition row
    await db_session.commit()
    r = await client.post(f"/api/v1/school/activities/{visit['id']}/attendance", json=attendance(w))
    assert r.status_code == 403
    assert "Monthly campus visits" in r.json()["detail"]
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd apps/api && pytest tests/test_enh_023_tier_rules.py tests/test_enh_023_tier_change.py -v -k "grandfather or survive or anchor or expired or lost or after_the_downgrade or free_text"`
Expected: FAIL — `ImportError: cannot import name '_grandfathers'`; the route tests get 403 where 200 is expected.

- [ ] **Step 4: Implement the helpers** (`schools.py`, directly above `require_school_entitlement`)

```python
def _grandfathers(metadata: dict, service_key: str | None) -> bool:
    """ENH-023 §5: does this `school.tier_update` row take `service_key` away? Rows written before ENH-023 carry no
    `direction` and never match; `service_key=None` (a free-text activity, ENH-022 D7) is taken away only by a removal."""
    if metadata.get("direction") != "downgrade":
        return False
    if service_key is None:
        return metadata.get("to_tier") is None
    return service_key in metadata.get("lost", [])


async def _lost_since(db: AsyncSession, school_id: UUID, service_key: str | None, since: datetime) -> bool:
    """Was `service_key` taken from this school by a tier change after `since`? Filters on the indexed action in SQL and reads
    the metadata in Python: no JSON operators, no migration. These rows are business inputs now and must not be pruned."""
    rows = (
        await db.scalars(select(AuditLog.metadata_json).where(AuditLog.action == TIER_UPDATE, AuditLog.entity_id == str(school_id), AuditLog.created_at > since))
    ).all()
    return any(_grandfathers(metadata or {}, service_key) for metadata in rows)


async def _is_grandfathered(db: AsyncSession, school: School | None, reason: str, service_key: str | None, since: datetime) -> bool:
    """ENH-023 D2/D6: only a `not_included`/`no_tier` denial on an unexpired school can be lifted; `expired` never is."""
    if school is None or reason not in {"not_included", "no_tier"}:
        return False
    if school.tier_valid_until is not None and school.tier_valid_until < _today_ist():
        return False
    return await _lost_since(db, school.id, service_key, since)
```

- [ ] **Step 5: Change `require_school_entitlement`**

Change its signature and docstring, and insert the grandfather branch between `reason, message = denial` and `fields = …`:

```python
async def require_school_entitlement(db: AsyncSession, user: User, school_id: UUID, service_key: str | None, *, grandfathered_since: datetime | None = None) -> None:
    """403 unless the school's valid cumulative tier includes `service_key`. Call it after the route's own role and scope
    checks and before any write: a denial commits its audit row (D12), so nothing else may be pending in the session.
    ENH-023 (DEC-SCOPE-029 D2/D8): a route finishing existing work passes that work's `created_at` as `grandfathered_since`;
    the denial is then lifted when a tier change after that time took the service away (never for an expired partnership)."""
    school = await db.get(School, school_id)
    tier = school.tier if school else None
    denial = _entitlement_denial(tier, school.tier_valid_until if school else None, service_key, _today_ist())
    if denial is None:
        return
    reason, message = denial
    if grandfathered_since is not None and await _is_grandfathered(db, school, reason, service_key, grandfathered_since):
        logger.info("tier_grandfathered", extra={"extra_fields": {"actor_id": str(user.id), "role": user.role, "school_id": str(school_id), "service_key": service_key}})
        return
    # … the rest of the function (fields / AuditLog / commit / warning / raise) is unchanged
```

- [ ] **Step 6: Pass the anchors on the four schools.py routes**

In `mark_attendance`:

```python
    await require_school_entitlement(db, user, school_id, ACTIVITY_SERVICE_KEYS[activity.activity_type] if activity.activity_type else None, grandfathered_since=activity.created_at)
```

In `update_psychometric_record`:

```python
    await require_school_entitlement(db, user, student.school_id, "psychometric_test", grandfathered_since=record.created_at)
```

In `update_test_prep_record`:

```python
    await require_school_entitlement(db, user, student.school_id, TEST_PREP_SERVICE_KEYS[record.test_type], grandfathered_since=record.created_at)  # the stored test, never the body's
```

In `update_language_record`:

```python
    await require_school_entitlement(db, user, student.school_id, "foreign_language_classes", grandfathered_since=record.created_at)
```

- [ ] **Step 7: Run to verify they pass, and ENH-022 is untouched**

Run: `cd apps/api && pytest tests/test_enh_023_tier_rules.py tests/test_enh_023_tier_change.py tests/test_enh_022_tier_rules.py tests/test_enh_022_tier_enforcement.py -v`
Expected: all PASS, with no edits to either ENH-022 file.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/api/schools.py apps/api/tests/test_enh_023_tier_rules.py apps/api/tests/test_enh_023_tier_change.py
git commit -m "feat(enh-023): grandfather work started before a downgrade"
```

---

### Task 6: Grandfathered skills work

**Files:**
- Modify: `apps/api/app/api/school_skills.py` — `_require_module_entitlement` and 6 call sites
- Test: `apps/api/tests/test_enh_023_tier_change.py` (append)

**Interfaces:**
- Consumes: `require_school_entitlement(…, grandfathered_since=)` (Task 5)
- Produces: `_require_module_entitlement(db, user, school_id, module_type, *, grandfathered_since: datetime | None = None)`

- [ ] **Step 1: Write the failing test** (append)

```python
from enh011_helpers import ASSESSMENTS, BATCHES, ENROLMENTS, SESSIONS  # noqa: E402

from app.models import SchoolSkillBatch  # noqa: E402


@pytest.mark.asyncio
async def test_digital_skills_batch_can_be_finished_after_a_downgrade_but_not_grown(client, db_session):
    w = await world(db_session, "silver", staff_role="career_counselor")
    await login(client, w["staff"].email)
    today = date.today().isoformat()
    sid = str(w["students"][0].id)
    batch = (await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "digital_skills", "title": "T", "start_date": today})).json()
    enrolment = (await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [sid]})).json()[0]
    await change_tier(client, w, tier="bronze")  # web_designing lost
    await login(client, w["staff"].email)

    assert (await client.patch(f"{BATCHES}/{batch['id']}", json={"title": "Renamed"})).status_code == 200
    session = await client.post(f"{BATCHES}/{batch['id']}/sessions", json={"session_date": today})
    assert session.status_code == 201, session.text
    marked = await client.put(f"{SESSIONS}/{session.json()['id']}/attendance", json={"records": [{"enrollment_id": enrolment["id"], "present": True}]})
    assert marked.status_code == 200, marked.text
    assessment = await client.post(f"{BATCHES}/{batch['id']}/assessments", json={"name": "Quiz", "max_score": 10})
    assert assessment.status_code == 201, assessment.text
    scored = await client.put(f"{ASSESSMENTS}/{assessment.json()['id']}/scores", json={"scores": [{"enrollment_id": enrolment["id"], "score": 7}]})
    assert scored.status_code == 200, scored.text
    assert (await client.patch(f"{ENROLMENTS}/{enrolment['id']}", json={"status": "completed"})).status_code == 200

    # Growing the commitment is new work: refused (D8).
    grown = await client.post(f"{BATCHES}/{batch['id']}/enrollments", json={"school_student_ids": [sid]})
    assert grown.status_code == 403
    new_batch = await client.post(BATCHES, json={"school_id": str(w["school"].id), "module_type": "digital_skills", "title": "New", "start_date": today})
    assert new_batch.status_code == 403
    assert await denials(db_session, w["school"].id) == 2
    stored = await db_session.get(SchoolSkillBatch, UUID(batch["id"]), populate_existing=True)
    assert stored.title == "Renamed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py -v -k digital_skills_batch`
Expected: FAIL — the batch PATCH returns 403.

- [ ] **Step 3: Implement**

In `school_skills.py`, add `from datetime import datetime` to the imports if it is not already imported (keep the existing `date` import if present), then change the helper:

```python
async def _require_module_entitlement(db: AsyncSession, user: User, school_id: UUID, module_type: str, *, grandfathered_since: datetime | None = None) -> None:
    """ENH-022: every skills write consumes the module's tier service (`digital_skills` is sold as `web_designing`). Called
    after the route's portfolio check and before any write, so an out-of-portfolio caller never learns a school's tier.
    ENH-023 D8: writes that finish an existing batch pass the batch's (or enrolment's) `created_at`; creates never do."""
    await require_school_entitlement(db, user, school_id, USAGE_KEYS[module_type], grandfathered_since=grandfathered_since)
```

Change these call sites (the other two, in `create_skill_batch` and `enrol_students`, stay as they are):

```python
# update_skill_batch, create_skill_session, mark_skill_attendance, create_skill_assessment, record_skill_scores:
    await _require_module_entitlement(db, user, batch.school_id, batch.module_type, grandfathered_since=batch.created_at)

# update_enrolment_status:
    await _require_module_entitlement(db, user, batch.school_id, batch.module_type, grandfathered_since=row.created_at)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py tests/test_enh_022_tier_enforcement.py tests/test_enh_011_batches.py tests/test_enh_011_enrollments.py tests/test_enh_011_attendance.py tests/test_enh_011_scores.py tests/test_enh_011_concurrency.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/school_skills.py apps/api/tests/test_enh_023_tier_change.py
git commit -m "feat(enh-023): grandfather skills batches started before a downgrade"
```

---

### Task 7: Grandfathered portfolio and visa work

**Files:**
- Modify: `apps/api/app/api/portfolio.py` — `update_portfolio_entry`, `delete_portfolio_entry`, `update_personal_statement`
- Modify: `apps/api/app/api/workflows.py` — `_require_bridged_visa_entitlement`, `update_visa`
- Test: `apps/api/tests/test_enh_023_tier_change.py` (append)

**Interfaces:**
- Consumes: `require_school_entitlement(…, grandfathered_since=)` (Task 5)
- Produces: `_require_bridged_visa_entitlement(db, user, application, *, grandfathered_since: datetime | None = None)`

- [ ] **Step 1: Write the failing tests** (append)

```python
from test_sch_010_overseas_bridge import _make_university  # noqa: E402

from app.models import PortfolioEntry  # noqa: E402

PORTFOLIO = "/api/v1/school/students/{sid}/portfolio"


@pytest.mark.asyncio
async def test_portfolio_work_can_be_edited_after_a_downgrade_but_not_added(client, db_session):
    w = await world(db_session, "gold")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await login(client, w["coordinator"].email)
    entry = (await client.post(f"{url}/entries", json={"section": "project", "title": "Robot"})).json()
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hi"})).status_code == 200
    await change_tier(client, w, tier="silver")
    await login(client, w["coordinator"].email)
    assert (await client.patch(f"{url}/entries/{entry['id']}", json={"title": "Robot v2"})).status_code == 200
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hello"})).status_code == 200
    assert (await client.post(f"{url}/entries", json={"section": "project", "title": "New"})).status_code == 403
    assert (await client.delete(f"{url}/entries/{entry['id']}")).status_code == 204
    assert await db_session.get(PortfolioEntry, UUID(entry["id"]), populate_existing=True) is None


@pytest.mark.asyncio
async def test_personal_statement_never_started_is_new_work(client, db_session):
    w = await world(db_session, "gold")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await change_tier(client, w, tier="silver")
    await login(client, w["coordinator"].email)
    assert (await client.patch(f"{url}/personal-statement", json={"personal_statement": "Hi"})).status_code == 403


@pytest.mark.asyncio
async def test_unknown_portfolio_entry_is_404_before_the_tier_check(client, db_session):
    w = await world(db_session, "silver")
    url = PORTFOLIO.format(sid=w["students"][0].id)
    await login(client, w["coordinator"].email)
    r = await client.patch(f"{url}/entries/00000000-0000-0000-0000-000000000000", json={"title": "X"})
    assert r.status_code == 404
    assert await denials(db_session, w["school"].id) == 0


@pytest.mark.asyncio
async def test_visa_case_can_be_updated_after_a_downgrade_but_not_opened(client, db_session):
    w = await world(db_session, "platinum", students=2)
    university = await _make_university(db_session)
    await login(client, w["admin"].email)
    apps = [
        await client.post(f"/api/v1/overseas-admin/school-students/{s.id}/applications", json={"university_id": str(university.id), "intake": "Fall 2027"})
        for s in w["students"]
    ]
    assert [a.status_code for a in apps] == [201, 201]
    visa = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": apps[0].json()["id"], "status": "checklist"})
    assert visa.status_code == 201, visa.text
    await change_tier(client, w, tier="gold")  # visa_support lost; application_support kept
    assert (await client.patch(f"/api/v1/workflows/overseas/visa/{visa.json()['id']}", json={"tracking_reference": "X1"})).status_code == 200
    second = await client.post("/api/v1/workflows/overseas/visa", json={"application_id": apps[1].json()["id"], "status": "checklist"})
    assert second.status_code == 403
    assert "Visa support" in second.json()["detail"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py -v -k "portfolio or personal_statement or visa"`
Expected: FAIL — PATCHes return 403; the unknown-entry test gets 403 instead of 404.

- [ ] **Step 3: Implement the portfolio routes**

In `update_portfolio_entry` and `delete_portfolio_entry`, load the entry **before** the tier check (still after the role/scope check) and pass its `created_at`:

```python
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)  # role/scope checked before the entry lookup below (spec §6)
    entry = await _load_portfolio_entry(db, student.id, entry_id)
    # ENH-023 D8: editing or removing an entry that existed before a downgrade finishes existing work.
    await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation", grandfathered_since=entry.created_at)
```

(and delete the original `entry = await _load_portfolio_entry(...)` line that followed the tier check in each route).

In `update_personal_statement`, replace the tier-check line with:

```python
    # ENH-023 D8: a statement already started is existing work; the first one ever is new work.
    started = await db.scalar(select(PortfolioProfile.created_at).where(PortfolioProfile.school_student_id == student.id))
    await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation", grandfathered_since=started)
```

- [ ] **Step 4: Implement the visa route**

In `workflows.py`, add `datetime` to the `from datetime import …` line if it is not already imported. Change the helper:

```python
async def _require_bridged_visa_entitlement(db: AsyncSession, user: User, application: OverseasApplication, *, grandfathered_since: datetime | None = None) -> None:
    """ENH-022 (D9): a visa case on a School-bridged application consumes the school's Platinum `visa_support`. An ordinary
    Overseas application (no `school_student_id`) is untouched. Call after `_assigned_application`, before any write.
    ENH-023 D8: updating an existing visa case passes its `created_at`; opening a new case never does."""
    if application.school_student_id is None:
        return
    from app.api.schools import require_school_entitlement  # noqa: PLC0415 -- lazy, like admin.py's bridge import
    from app.models import SchoolStudent  # noqa: PLC0415

    student = await db.get(SchoolStudent, application.school_student_id)  # FK: always present for a bridged application
    await require_school_entitlement(db, user, student.school_id, "visa_support", grandfathered_since=grandfathered_since)
```

In `update_visa`:

```python
    await _require_bridged_visa_entitlement(db, user, application, grandfathered_since=item.created_at)
```

`create_visa_case` is unchanged.

- [ ] **Step 5: Run to verify they pass**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py tests/test_enh_022_tier_enforcement.py tests/test_enh_012_digital_portfolio.py tests/test_sch_010_overseas_bridge.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/api/portfolio.py apps/api/app/api/workflows.py apps/api/tests/test_enh_023_tier_change.py
git commit -m "feat(enh-023): grandfather portfolio entries and visa cases"
```

---

### Task 8: Concurrent tier changes queue

**Files:**
- Test: `apps/api/tests/test_enh_023_tier_change.py` (append). No production change is expected: the lock was added in Task 2. This task proves it.

**Interfaces:**
- Consumes: `update_school`'s `with_for_update()` (Task 2)

- [ ] **Step 1: Write the test** (append)

```python
import asyncio  # noqa: E402
from contextlib import asynccontextmanager  # noqa: E402

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import School  # noqa: E402


@asynccontextmanager
async def _school_locked(school_id):
    session = SessionLocal()
    try:
        await session.execute(select(School).where(School.id == school_id).with_for_update())
        yield
    finally:
        await session.rollback()
        await session.close()


@pytest.mark.asyncio
async def test_concurrent_tier_changes_queue_and_record_true_transitions(db_session):
    w = await world(db_session, "platinum")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as admin:
        await login(admin, w["admin"].email)
        async with _school_locked(w["school"].id):
            first = asyncio.create_task(admin.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "gold"}))
            await asyncio.sleep(0.3)
            second = asyncio.create_task(admin.patch(f"{SCHOOLS}/{w['school'].id}", json={"tier": "silver"}))
            await asyncio.sleep(0.7)
            assert not first.done() and not second.done(), "a tier change did not wait for the school row lock"
        results = await asyncio.wait_for(asyncio.gather(first, second), timeout=20)
    assert [r.status_code for r in results] == [200, 200]
    rows = await tier_rows(db_session, w["school"].id)
    assert len(rows) == 2
    assert rows[0].metadata_json["from_tier"] == "platinum"
    assert rows[1].metadata_json["from_tier"] == rows[0].metadata_json["to_tier"]
```

- [ ] **Step 2: Run it**

Run: `cd apps/api && pytest tests/test_enh_023_tier_change.py -v -k concurrent`
Expected: PASS. To prove the test can fail, temporarily replace `.with_for_update()` in `update_school` with nothing, re-run, expect FAIL on the `not done()` assertion, then restore the lock and re-run to PASS.

- [ ] **Step 3: Commit**

```bash
git add apps/api/tests/test_enh_023_tier_change.py
git commit -m "test(enh-023): concurrent tier changes queue on the school row lock"
```

---

### Task 9: Tier fields and downgrade confirmation in the edit panel

**Files:**
- Modify: `apps/web/components/AdminSchoolEditPanel.tsx`
- Test: `apps/web/tests/components/AdminSchoolEditPanel.test.tsx` (extend)

**Interfaces:**
- Consumes: `GET …/tier-change-preview?tier=` (Task 3); PATCH response `tier_change` and the `expected_tier` precondition / `409` (Task 2)
- Produces: new field IDs `#edit-tier` (name `tier`) and `#edit-tier-valid-until` (name `tier_valid_until`); buttons "Confirm downgrade" and "Cancel", used by Task 11.

- [ ] **Step 1: Write the failing tests** (append inside the existing `describe`)

```tsx
  const ID = "11111111-1111-1111-1111-111111111111";
  const base = { id: ID, school_code: "ABCD1234", name: "Test School", branch: null, tier: "platinum", tier_valid_until: null };
  const downgrade = { direction: "downgrade", from_tier: "platinum", to_tier: "gold", gained: [], lost: [{ key: "visa_support", label: "Visa support" }] };
  const upgrade = { direction: "upgrade", from_tier: "gold", to_tier: "platinum", gained: [{ key: "visa_support", label: "Visa support" }], lost: [] };

  async function lookUp() {
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Partnership tier");
  }

  it("saves an upgrade straight away and names what became available", async () => {
    const mock = stubFetch([json({ ...base, tier: "gold" }, 200), json(upgrade, 200), json({ ...base, tier_change: upgrade }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "platinum" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("School profile updated. Partnership is now Platinum; newly available: Visa support.");
    expect(mock.mock.calls[1][0]).toBe(`/api/v1/overseas-admin/schools/${ID}/tier-change-preview?tier=platinum`);
    expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({ tier: "platinum", expected_tier: "gold" });
  });

  it("asks before a downgrade and saves only on confirm", async () => {
    const mock = stubFetch([json(base, 200), json(downgrade, 200), json({ ...base, tier: "gold", tier_change: downgrade }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/These services will no longer be available for new work: Visa support\./);
    expect(mock).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Confirm downgrade" }));
    await screen.findByText("School profile updated. Partnership is now Gold.");
    expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({ tier: "gold", expected_tier: "platinum" });
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
  });

  it("a tier changed by someone else since lookup is a 409 alert and keeps the input", async () => {
    const stale = "This school's tier changed to Silver since you looked it up. Look it up again before changing the tier.";
    stubFetch([json(base, 200), json(downgrade, 200), json({ detail: stale }, 409)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    fireEvent.click(await screen.findByRole("button", { name: "Confirm downgrade" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(stale);
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
    expect((screen.getByLabelText("Partnership tier") as HTMLSelectElement).value).toBe("gold");
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("cancel keeps the input and saves nothing", async () => {
    const mock = stubFetch([json(base, 200), json(downgrade, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
    expect((screen.getByLabelText("Partnership tier") as HTMLSelectElement).value).toBe("gold");
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("editing the form after the confirmation clears it", async () => {
    stubFetch([json(base, 200), json(downgrade, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByRole("button", { name: "Confirm downgrade" });
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
  });

  it("removing the tier asks for confirmation", async () => {
    const removal = { ...downgrade, to_tier: null };
    const mock = stubFetch([json(base, 200), json(removal, 200), json({ ...base, tier: null, tier_change: removal }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/Downgrading Test School from Platinum to no partnership tier\./);
    expect(mock.mock.calls[1][0]).toBe(`/api/v1/overseas-admin/schools/${ID}/tier-change-preview?tier=`);
    fireEvent.click(screen.getByRole("button", { name: "Confirm downgrade" }));
    await screen.findByText("School profile updated. Partnership is now no partnership tier.");
    expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({ tier: null, expected_tier: "platinum" });
  });

  it("a failed preview is an alert, saves nothing and frees the button", async () => {
    const mock = stubFetch([json(base, 200), json({ detail: "Overseas Admin role required" }, 403)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Overseas Admin role required");
    expect(mock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("a network failure during the preview says nothing was saved", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json(base, 200)).mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", mock);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network error -- nothing was saved. Check your connection and try again.");
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("an untouched tier is never sent and needs no preview", async () => {
    const mock = stubFetch([json({ ...base, tier_valid_until: "2027-01-01" }, 200), json({ ...base, branch: "North", tier_change: null }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("School profile updated.");
    expect(mock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ branch: "North" });
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd apps/web && npx vitest run tests/components/AdminSchoolEditPanel.test.tsx`
Expected: the 9 new tests FAIL (no "Partnership tier" field); the 3 existing tests PASS.

- [ ] **Step 3: Implement** — replace `apps/web/components/AdminSchoolEditPanel.tsx` with:

```tsx
"use client";

import { FormEvent, useState } from "react";

import { detailMessage, isRequestBody } from "@/lib/apiErrors";
import { type Feedback, toneClass } from "@/lib/welcomeLink";

type School = {
  id: string; school_code: string | null; name: string;
  branch: string | null; address: string | null; contact_number: string | null;
  email: string | null; website: string | null; grades_available: string | null;
  board: string | null; partnership_date: string | null; mou_reference: string | null;
  edusphere_bdm: string | null; monthly_visit_schedule: string | null; vice_principal_name: string | null;
  tier?: string | null; tier_valid_until?: string | null;
};

type Service = { key: string; label: string };
type TierChange = { direction: "upgrade" | "downgrade" | "unchanged"; from_tier: string | null; to_tier: string | null; gained: Service[]; lost: Service[] };
type Body = Record<string, string | null>;

const FIELDS = ["branch", "address", "contact_number", "email", "website", "grades_available", "board", "partnership_date", "mou_reference", "edusphere_bdm", "monthly_visit_schedule", "vice_principal_name", "tier", "tier_valid_until"] as const;

const tierName = (tier: string | null) => (tier ? tier.charAt(0).toUpperCase() + tier.slice(1) : "no partnership tier");
const labels = (services: Service[]) => services.map((s) => s.label).join(", ");

function savedText(change: TierChange | null | undefined): string {
  if (!change || change.direction === "unchanged") return "School profile updated.";
  const gained = change.direction === "upgrade" && change.gained.length ? `; newly available: ${labels(change.gained)}` : "";
  return `School profile updated. Partnership is now ${tierName(change.to_tier)}${gained}.`;
}

// ENH-009 / DEC-SCOPE-025: lookup-by-code then PATCH, mirroring the existing
// GET .../school-students/lookup?code= convention (admin.py:1240) -- the codebase has no
// clickable-table-row-to-edit pattern anywhere, and the established convention is "read via the
// generic portal section, write via a dedicated panel" (same split as AdminSchoolCreatePanel.tsx).
// ENH-023 / DEC-SCOPE-029: the tier is edited here too. A changed tier is previewed first; a downgrade or removal is only
// saved after the admin confirms the list of services the school loses (D7) -- never silently.
export default function AdminSchoolEditPanel() {
  const [busy, setBusy] = useState<null | "lookup" | "checking" | "saving">(null);
  const [message, setMessage] = useState<Feedback | null>(null);
  const [school, setSchool] = useState<School | null>(null);
  const [pending, setPending] = useState<{ body: Body; change: TierChange } | null>(null);

  async function lookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const code = new FormData(event.currentTarget).get("code");
    setBusy("lookup");
    setMessage(null);
    setSchool(null);
    setPending(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/lookup?code=${encodeURIComponent(String(code))}`);
    } catch {
      setBusy(null);
      setMessage({ text: "Network error -- check your connection and try again.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail, "Unable to look up that school."), tone: "error" });
      return;
    }
    setSchool(data as School);
  }

  async function preview(current: School, tier: string | null): Promise<TierChange | null> {
    setBusy("checking");
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/${current.id}/tier-change-preview?tier=${encodeURIComponent(tier ?? "")}`);
    } catch {
      setBusy(null);
      setMessage({ text: "Network error -- nothing was saved. Check your connection and try again.", tone: "error" });
      return null;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail, "Unable to check the tier change. Nothing was saved."), tone: "error" });
      return null;
    }
    return data as TierChange;
  }

  async function patch(current: School, body: Body) {
    setBusy("saving");
    setMessage(null);
    let response: Response;
    try {
      response = await fetch(`/api/v1/overseas-admin/schools/${current.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      setBusy(null);
      setMessage({ text: "Network error -- it is not known whether the changes saved. Look the school up again before retrying.", tone: "error" });
      return;
    }
    const data = await response.json().catch(() => ({}));
    setBusy(null);
    setPending(null);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), tone: "error" });
      return;
    }
    if (!isRequestBody(data)) {
      setMessage({ text: "The save could not be confirmed. Look the school up again before changing anything else.", tone: "error" });
      return;
    }
    setSchool(data as School);
    setMessage({ text: savedText((data as { tier_change?: TierChange | null }).tier_change), tone: "success" });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!school) return;
    const form = new FormData(event.currentTarget);
    // Diff against the loaded school, so only genuinely-changed fields are sent: an emptied
    // field goes as an explicit `null` (the backend's `exclude_unset=True` clears it), and an
    // untouched field is omitted entirely -- otherwise the `school.profile_update` audit row's
    // `changed_fields` would list all 12 fields on every save (final-review finding, ENH-009),
    // and an untouched tier would write a `school.tier_update` row (ENH-023).
    const body: Body = {};
    for (const field of FIELDS) {
      const raw = String(form.get(field) ?? "").trim();
      const next = raw === "" ? null : raw;
      const current = school[field] ?? null;
      if (next !== current) body[field] = next;
    }
    setMessage(null);
    setPending(null);
    if ("tier" in body) {
      // D12: the tier this admin looked at. If it moved since, the server answers 409 instead of applying a change the
      // admin never confirmed.
      body.expected_tier = school.tier ?? null;
      const change = await preview(school, body.tier);
      if (!change) return;
      if (change.direction === "downgrade") {
        setPending({ body, change });
        return;
      }
    }
    await patch(school, body);
  }

  const isBusy = busy !== null;
  return (
    <div className="action-card">
      <h3>Edit school profile</h3>
      <form className="form" onSubmit={lookup}>
        <div className="field">
          <label htmlFor="school-lookup-code">School ID</label>
          <input id="school-lookup-code" name="code" required />
        </div>
        <button className="btn" disabled={isBusy}>{busy === "lookup" ? "Looking up…" : "Look up"}</button>
      </form>
      {school && (
        <form className="form" onSubmit={save} onChange={() => setPending(null)} style={{ marginTop: 16 }}>
          <p className="muted">{school.name} ({school.school_code})</p>
          <div className="field"><label htmlFor="edit-branch">Branch</label><input id="edit-branch" name="branch" defaultValue={school.branch ?? ""} /></div>
          <div className="field"><label htmlFor="edit-address">Address</label><input id="edit-address" name="address" defaultValue={school.address ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-contact-number">Contact number</label><input id="edit-contact-number" name="contact_number" defaultValue={school.contact_number ?? ""} /></div>
            <div className="field"><label htmlFor="edit-email">Email</label><input id="edit-email" name="email" type="email" defaultValue={school.email ?? ""} /></div>
          </div>
          <div className="field"><label htmlFor="edit-website">Website</label><input id="edit-website" name="website" defaultValue={school.website ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-grades">Grades available</label><input id="edit-grades" name="grades_available" defaultValue={school.grades_available ?? ""} /></div>
            <div className="field">
              <label htmlFor="edit-board">Board</label>
              <select id="edit-board" name="board" defaultValue={school.board ?? ""}>
                <option value="">Not set</option>
                <option value="CBSE">CBSE</option>
                <option value="ICSE">ICSE</option>
                <option value="State">State</option>
                <option value="IB">IB</option>
                <option value="Other">Other</option>
              </select>
            </div>
          </div>
          <div className="field"><label htmlFor="edit-partnership-date">Partnership date</label><input id="edit-partnership-date" name="partnership_date" type="date" defaultValue={school.partnership_date ?? ""} /></div>
          <div className="field"><label htmlFor="edit-mou">Agreement / MoU reference</label><input id="edit-mou" name="mou_reference" defaultValue={school.mou_reference ?? ""} /></div>
          <div className="form-grid">
            <div className="field"><label htmlFor="edit-bdm">Edusphere BDM</label><input id="edit-bdm" name="edusphere_bdm" defaultValue={school.edusphere_bdm ?? ""} /></div>
            <div className="field"><label htmlFor="edit-vp">Vice Principal</label><input id="edit-vp" name="vice_principal_name" defaultValue={school.vice_principal_name ?? ""} /></div>
          </div>
          <div className="field"><label htmlFor="edit-visits">Monthly visit schedule</label><input id="edit-visits" name="monthly_visit_schedule" defaultValue={school.monthly_visit_schedule ?? ""} /></div>
          <div className="form-grid">
            <div className="field">
              <label htmlFor="edit-tier">Partnership tier</label>
              <select id="edit-tier" name="tier" defaultValue={school.tier ?? ""}>
                <option value="">Not set</option>
                <option value="bronze">Bronze</option>
                <option value="silver">Silver</option>
                <option value="gold">Gold</option>
                <option value="platinum">Platinum</option>
              </select>
            </div>
            <div className="field"><label htmlFor="edit-tier-valid-until">Valid until</label><input id="edit-tier-valid-until" name="tier_valid_until" type="date" defaultValue={school.tier_valid_until ?? ""} /></div>
          </div>
          <button className="btn" disabled={isBusy}>{busy === "checking" ? "Checking tier change…" : busy === "saving" ? "Saving…" : "Save changes"}</button>
          {pending && (
            <div className="form-warning" style={{ marginTop: 8 }}>
              <p>
                Downgrading {school.name} from {tierName(pending.change.from_tier)} to {tierName(pending.change.to_tier)}. These services will no
                longer be available for new work: {labels(pending.change.lost)}. Work already started can still be completed. The school will be notified.
              </p>
              <button type="button" className="btn" disabled={isBusy} onClick={() => patch(school, pending.body)}>Confirm downgrade</button>{" "}
              <button type="button" className="btn secondary" disabled={isBusy} onClick={() => setPending(null)}>Cancel</button>
            </div>
          )}
        </form>
      )}
      {message && (
        <div className={toneClass[message.tone]} role={message.tone === "error" ? "alert" : "status"} aria-live={message.tone === "error" ? "assertive" : "polite"} style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd apps/web && npx vitest run tests/components/AdminSchoolEditPanel.test.tsx && npx tsc --noEmit`
Expected: 12 tests PASS; no type errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/AdminSchoolEditPanel.tsx apps/web/tests/components/AdminSchoolEditPanel.test.tsx
git commit -m "feat(enh-023): tier fields and downgrade confirmation in the school edit panel"
```

---

### Task 10: Principal notifications page

**Files:**
- Create: `apps/web/app/school/principal/notifications/page.tsx`
- Modify: `apps/web/lib/navigation.ts:38` (principal nav)
- Modify: `apps/web/app/school/coordinator/notifications/page.tsx` (empty text)
- Test: `apps/web/tests/components/SchoolPrincipalNotificationsPage.test.tsx` (create)

**Interfaces:**
- Consumes: `GET /api/v1/workflows/notifications` (existing, keyed on the signed-in user)
- Produces: route `/school/principal/notifications`; nav label "Notifications"

- [ ] **Step 1: Write the failing test**

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolPrincipalNotificationsPage from "@/app/school/principal/notifications/page";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";

// Async server component: `serverApi` reads next/headers cookies, so it is mocked (the real ApiError class is kept);
// the shell is stubbed because this test is about who sees what, not the chrome.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div data-testid="shell">{children}</div> }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "school", profile: {} });
const notice = { id: "n1", title: "Your partnership changed from Platinum to Gold", body: "These services are no longer available for new work: Visa support.", read: false, action_url: "/school/principal/entitlements", created_at: "2026-09-23T10:00:00Z" };

function serve(role: string, notifications: unknown[]) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user(role);
    if (path === "/api/v1/workflows/notifications") return notifications;
    throw new Error(`unexpected request ${path}`);
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("SchoolPrincipalNotificationsPage", () => {
  it("lists the principal's own notifications", async () => {
    serve("school_principal", [notice]);
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("Your partnership changed from Platinum to Gold")).toBeTruthy();
  });

  it("explains the empty state", async () => {
    serve("school_principal", []);
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("No notifications yet. You will be told here when your school's partnership changes.")).toBeTruthy();
  });

  it.each(["school_coordinator", "school_teacher", "school_parent"])("denies %s and never loads the feed", async (role) => {
    serve(role, [notice]);
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.getByText("School Principal role required")).toBeTruthy();
    expect(vi.mocked(serverApi).mock.calls.map((c) => c[0])).not.toContain("/api/v1/workflows/notifications");
  });

  it("still shows Access unavailable when the feed cannot be loaded", async () => {
    vi.mocked(serverApi).mockRejectedValue(new Error("Not authenticated"));
    render(await SchoolPrincipalNotificationsPage());
    expect(screen.getByText("Access unavailable")).toBeTruthy();
  });

  it("is in the principal navigation", () => {
    expect(SCHOOL_NAV.principal.map((item) => item.href)).toContain("/school/principal/notifications");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npx vitest run tests/components/SchoolPrincipalNotificationsPage.test.tsx`
Expected: FAIL — cannot resolve `@/app/school/principal/notifications/page`.

- [ ] **Step 3: Implement**

Create `apps/web/app/school/principal/notifications/page.tsx`:

```tsx
import PortalShell from "@/components/PortalShell";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";
import { accessDenied, accessUnavailable } from "@/components/AccessUnavailable";

// ENH-023 (DEC-SCOPE-029 D9): the School Principal's own notifications -- their school's partnership tier changing. Same
// feed as the Coordinator page, keyed on the signed-in user, never a client-supplied id. Principal-only.
export default async function SchoolPrincipalNotificationsPage() {
  let user: User;
  let notifications: NotificationItem[];
  try {
    user = await serverApi<User>("/api/v1/auth/me");
    if (user.role !== "school_principal") return accessDenied(user, "School Principal role required");
    notifications = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch (e) {
    return accessUnavailable(e);
  }
  return (
    <PortalShell nav={SCHOOL_NAV.principal} roleLabel="Principal" userName={user.full_name}>
      <div className="portal-content">
        <h1>Notifications</h1>
        <div className="card">
          <SchoolNotificationList notifications={notifications} emptyText="No notifications yet. You will be told here when your school's partnership changes." />
        </div>
      </div>
    </PortalShell>
  );
}
```

In `apps/web/lib/navigation.ts`, change the principal array from `["dashboard", "reports", "entitlements"]` to `["dashboard", "reports", "entitlements", "notifications"]`.

In `apps/web/app/school/coordinator/notifications/page.tsx`, change the `emptyText` to:
`"No notifications yet. You will be told here when a transfer request is decided, a student joins your school, or your school's partnership changes."`

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/web && npx vitest run tests/components/SchoolPrincipalNotificationsPage.test.tsx tests/components/PortalShell.test.tsx tests/components/SchoolNotificationList.test.tsx && npx tsc --noEmit`
Expected: all PASS. If `PortalShell.test.tsx` pins the principal nav length, update that count only; never change what the shell renders.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/school/principal/notifications/page.tsx apps/web/lib/navigation.ts apps/web/app/school/coordinator/notifications/page.tsx apps/web/tests/components/SchoolPrincipalNotificationsPage.test.tsx
git commit -m "feat(enh-023): principal notifications page"
```

---

### Task 11: End-to-end downgrade with notifications

**Files:**
- Create: `apps/web/tests/e2e/enh-023-tier-change.spec.ts`

**Interfaces:**
- Consumes: `#edit-tier`, "Confirm downgrade" (Task 9); `/school/principal/notifications` (Task 10); `E2E_PASSWORD`, `createAndActivateFromUi` from `./helpers/welcome`

- [ ] **Step 1: Ask the user to start the stack** (they run `docker compose` themselves) and wait for confirmation.

- [ ] **Step 2: Write the spec**

```ts
import { test, expect } from "@playwright/test";
import { E2E_PASSWORD, createAndActivateFromUi } from "./helpers/welcome";

// ENH-023 (DEC-SCOPE-029) -- an Overseas Admin downgrades a Platinum school to Gold through the confirmation step; the
// school's Coordinator and Principal are each told exactly what was lost.

async function signIn(page, email: string, password: string, landing: string) {
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**${landing}`);
}

test("downgrade asks for confirmation and notifies the coordinator and principal (ENH-023)", async ({ page }) => {
  test.setTimeout(150_000);
  const unique = Date.now();
  const coordinatorEmail = `enh023-e2e-coord-${unique}@example.local`;
  const principalEmail = `enh023-e2e-principal-${unique}@example.local`;
  const principalPassword = "Sup3r-Secret-Pass!";

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-name", `E2E ENH-023 School ${unique}`);
  await page.selectOption("#school-tier", "platinum");
  await page.fill("#school-coordinator-name", "E2E ENH-023 Coordinator");
  await page.fill("#school-coordinator-email", coordinatorEmail);
  await createAndActivateFromUi(page, 'button:has-text("Create school + seed Coordinator")', "/overseas-admin/schools");
  const created = page.getByText(/School created\. School code [A-Z0-9]{8}\./);
  await expect(created).toBeVisible();
  const schoolCode = (await created.textContent())!.match(/School code ([A-Z0-9]{8})/)![1];

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  const invite = await page.request.post("/api/v1/school/team/invites", { data: { role: "school_principal", full_name: "E2E ENH-023 Principal", email: principalEmail } });
  expect(invite.ok()).toBeTruthy();
  const token = (await invite.json()).development_invite_token;
  await page.request.post("/api/v1/auth/logout");
  await page.goto(`/school/invite/${token}/accept`);
  await page.fill("#invite-password", principalPassword);
  await page.click('button:has-text("Accept and set up login")');
  await page.waitForURL("**/school/principal/dashboard");

  await signIn(page, "overseasadmin@edusphere.local", "Demo@123", "/overseas/admin/dashboard");
  await page.goto("/overseas/admin/schools");
  await page.fill("#school-lookup-code", schoolCode);
  await page.click('button:has-text("Look up")');
  await page.selectOption("#edit-tier", "gold");
  await page.click('button:has-text("Save changes")');
  await expect(page.getByText(/These services will no longer be available for new work: .*Visa support/)).toBeVisible();
  await page.click('button:has-text("Confirm downgrade")');
  await expect(page.getByText("School profile updated. Partnership is now Gold.")).toBeVisible();

  await signIn(page, coordinatorEmail, E2E_PASSWORD, "/school/coordinator/dashboard");
  await page.goto("/school/coordinator/notifications");
  await expect(page.getByText("Your partnership changed from Platinum to Gold")).toBeVisible();

  await signIn(page, principalEmail, principalPassword, "/school/principal/dashboard");
  await page.goto("/school/principal/notifications");
  await expect(page.getByText("Your partnership changed from Platinum to Gold")).toBeVisible();
});
```

- [ ] **Step 3: Run it, plus the specs that drive the same forms**

Run: `cd apps/web && npx playwright test tests/e2e/enh-023-tier-change.spec.ts tests/e2e/sch-003-school-onboarding.spec.ts tests/e2e/sch-011-entitlements.spec.ts`
Expected: all PASS. On a failure, open only that test's trace/screenshot.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-023-tier-change.spec.ts
git commit -m "test(enh-023): e2e downgrade confirmation and notifications"
```

---

### Task 12: Documentation, full regression, completion evidence

**Files:**
- Modify: `docs/decisions/PRODUCT_DECISION_REGISTER.md`, `docs/architecture/API_CONTRACT.md` (§12A), `docs/architecture/RBAC_MATRIX.md`, `docs/quality/RTM.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md`, `docs/ux/SCREEN_CATALOG.md`, `docs/ux/screen_catalog.json`, `docs/ux/ROLE_NAVIGATION.md`

- [ ] **Step 1: Decision register** — append `### DEC-SCOPE-029 — Partnership tier change: grandfathered downgrades, transition audit, notifications (ENH-023)`. Status `CONFIRMED_CURRENT — resolved 2026-09-23, in-session`. Resolution = the spec's §3 table D1–D13 verbatim. Note the number is provisional and renumbered on merge if taken.

- [ ] **Step 2: API contract** — in §12A, add an `ENH-023` addendum:
  - (a) `PATCH /overseas-admin/schools/{school_id}` now takes a row lock and returns the additive `tier_change` object (typed `SchoolUpdateOut`/`TierChangeOut`, spec §4.2), `null` for profile-only bodies. It accepts the optional `expected_tier` precondition (`409` with the exact Global Constraints message on mismatch; omitted = unchanged behaviour) and normalises `""` to `null` for `tier`/`expected_tier`. The `school.tier_update` metadata changes from `{tier}` to the eight keys in Global Constraints, and the row's `created_at` is `clock_timestamp()`. Post-commit notifications go to the school's Coordinator(s)/Principal(s) and the acting admin, only when the tier moved.
  - (b) New `GET /overseas-admin/schools/{school_id}/tier-change-preview?tier=` (Overseas Admin/Super Admin; `403`/`404`/`422`; read-only).
  - (c) The ENH-022 helper's grandfather rule and the 15 routes from spec §6.
  - (d) `PATCH`/`DELETE …/portfolio/entries/{id}` now return `404` for an unknown entry before any tier `403`.

- [ ] **Step 3: RBAC matrix** — under the ENH-022 tier dimension, add: "ENH-023: on the 15 completion actions (spec §6), a school that lost the service through a recorded downgrade after the record's creation keeps write access to that record; creates stay gated; expiry is never grandfathered." Add the principal's read of their own notifications.

- [ ] **Step 4: RTM, backlog, screens, nav**
  - RTM: add an `ENH-023` row following the `ENH-022`/`ENH-013` addendum format, citing the spec, this plan, the two new test files, the panel/page tests, the E2E spec and the regression results from Step 6.
  - Backlog §ENH-023: add a status line, `Implemented on feature/enh-023-tier-change-workflow (DEC-SCOPE-029)`, plus follow-ups (a) Overseas Admin notifications page, (b) share lock closing the §8 residual race, (c) pre-expiry notices.
  - `SCREEN_CATALOG.md` and `screen_catalog.json`: add `SCR-SCH-036 — /school/principal/notifications — Principal's own notifications (ENH-023, added 2026-09-23)`, following the `SCR-SCH-035` entry's format, and note the edit panel's new tier fields on its existing entry.
  - `ROLE_NAVIGATION.md`, Principal section: add `SCR-SCH-036 — /school/principal/notifications — Own notifications, e.g. partnership tier changes (ENH-023, added 2026-09-23).`

- [ ] **Step 5: Commit docs**

```bash
git add docs/
git commit -m "docs(enh-023): decision, contract, RBAC, RTM, backlog, screens"
```

- [ ] **Step 6: Full regression.** `require_school_entitlement` is shared by every gated route, so this change is cross-cutting and justifies the full suites under the every-3-to-4-features cadence. With the stack up:

Run: `cd apps/api && pytest -q`
Run: `cd apps/web && npx vitest run && npx tsc --noEmit && npx playwright test`
Expected: all PASS. Record the pass/fail counts in the RTM row. Investigate any failure (superpowers:systematic-debugging) before changing anything; never change product behaviour to make a draft test pass.

- [ ] **Step 7: Browser QA** — at phone width (375px) and desktop, on the admin schools page: confirm the confirmation box sits directly under Save and is readable, Cancel/Confirm are reachable by keyboard, and an error is announced (`role="alert"`). On the principal notifications page, check the empty and filled states. Record the results in `docs/quality/ENH-023_BROWSER_QA_2026-09-23.md`, following the ENH-011 QA file's format, and commit it.

- [ ] **Step 8: Commit the evidence**

```bash
git add docs/quality/ENH-023_BROWSER_QA_2026-09-23.md docs/quality/RTM.md
git commit -m "docs(enh-023): regression and browser QA evidence"
```
