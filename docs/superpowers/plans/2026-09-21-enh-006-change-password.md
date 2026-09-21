# ENH-006 Self-Service Change Password Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A signed-in user of any role can change their own password by supplying the current and a new one, with a generic wrong-password error, a per-user rate limit, and audit logging.

**Architecture:** One new authenticated route `POST /auth/change-password` in the existing `auth.py`, a `ChangePasswordRequest` Pydantic model, and a limiter that counts the `auth.change_password_failed` audit rows the route already writes (no table, no migration). The user row is locked `FOR UPDATE` so parallel guesses serialize. One new client form, one new server page modelled on `/account/privacy`, and one header link.

**Tech Stack:** FastAPI + async SQLAlchemy + bcrypt (existing), pytest (strict asyncio), Next.js app router + React, vitest + Testing Library, Playwright. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md` (decision `DEC-SCOPE-021`). Read it first — §4 (contract and check order) is authoritative.

## Global Constraints

- No new dependency, no migration, no new table, no Redis (`DEC-SCOPE-021` #2).
- Do **not** change `get_current_user`, `create_token`, `_set_auth_cookies`, JWT claims, `login`, `register`, `refresh`, `logout`, `forgot_password`, `reset_password`, `PATCH /auth/me`, `rbac.py`, `middleware.ts`, `ResetPasswordForm.tsx`, `ForgotPasswordForm.tsx`, the desktop `.portal-nav` and every role's `nav` array (spec §2, §9). `PortalShell.tsx` and `HeaderAuthActions.tsx` change **only additively** (one link each, plus one appended mobile-menu item).
- Other sessions are **not** invalidated (`DEC-SCOPE-021` #3).
- Rate limit: **5** wrong current passwords per authenticated user per **15 minutes**; then `429` + integer `Retry-After` (1–900 s), even for a correct password; keyed on user id, never IP.
- Passwords: `new_password` 10–128 characters; `current_password` 1–1024; never stripped or normalised.
- Error body is FastAPI's `{"detail": …}`; messages are pinned: `"Incorrect current password"`, `"New password must be different from the current password"`, `"Too many incorrect attempts; try again in N seconds"`.
- Audit actions: `auth.change_password` (success, `outcome` default) and `auth.change_password_failed` (`outcome="denied"`, `metadata_json={"reason": "incorrect_current_password"}`). Never a password or hash in an audit row or a log record.
- Check order (contract): authenticate → body validation → same-password compare → lock+refresh → limiter → verify current → write.
- Tests and E2E create their own throwaway users; never change a seeded account's password.
- Web copy must not contain the retired default password or the string "Temporary password" (`tests/lib/no-default-password.test.ts`).
- Frontend reuses the existing design language and helpers only: `.form`/`.field`/`.btn`/`.form-error`/`.form-message`/`.action-card`, `PublicShell`, `MobileNavToggle`, `lib/focus.ts` `refocus`, tokens such as `var(--blue)`. No new UI primitive, no skeleton/loading system (none exists in the repo), no animation.
- Accessibility: every input labelled; the field at fault gets `aria-invalid` + `aria-describedby`; focus is moved deliberately after each outcome; touch targets ≥ 44 px; works at 375 px with no horizontal scroll; keyboard-completable.
- On a successful change, the user's unused `purpose='reset'` password-reset tokens are revoked in the same transaction (`superseded_at`); welcome tokens, used tokens and other users' tokens are never touched; the `PasswordResetToken` schema and `reset_password` are unchanged (`DEC-SCOPE-021` #5).
- Accepted risk, do **not** "fix" it here: other sessions survive a change, so a stolen refresh cookie stays usable for up to 14 days (access tokens 60 minutes); document it (Task 8), do not add session invalidation (`DEC-SCOPE-021` #6).
- Security abuse cases are tests, not new behaviour: no change to app-wide body parsing, CORS, headers, cookies or JWT handling.
- Never alter product behaviour merely to make a draft test pass.

## Execution prerequisites (read before Task 1)

- **The user controls Docker.** Do not start, stop or rebuild the stack yourself; ask the user, and wait for them to say it is up. The API image has no source bind mounts and Postgres is not published to the host, so backend tests run inside the `api` container (`AGENTS.md`).
- **Backend test loop.** Once the user confirms the stack is up and allows it, use this loop instead of a rebuild per edit (it copies files into the running container; `pytest` imports `app` in-process, so the running server is unaffected):
  ```powershell
  docker compose cp apps/api/app/. api:/app/app/
  docker compose cp apps/api/tests/. api:/app/tests/
  docker compose exec api python -m pytest -q tests/test_enh_006_change_password.py
  ```
  Call this **`BACKEND_TEST`** below. If the user does not allow `docker compose cp`, ask them to run `docker compose build api; docker compose up -d --force-recreate api` at the checkpoint before each run step, and say so in the report. Backend tests leave rows behind (`AGENTS.md`); that is expected.
- **Frontend unit loop:** `cd apps/web; npx vitest run <file>` (no Docker). Call this **`WEB_UNIT`**.
- **E2E** needs the `web` image rebuilt after web changes (`docker compose build web; docker compose up -d --force-recreate web`) — the user does this. Run: `cd apps/web; npx playwright test tests/e2e/enh-006-change-password.spec.ts --workers=1`.
- **Commits:** the commit steps below need the user's go-ahead (ask once at handoff). Each commit message ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

## File structure

| File | Action | Responsibility |
|---|---|---|
| `apps/api/app/schemas.py` | Modify | `ChangePasswordRequest` |
| `apps/api/app/api/auth.py` | Modify | the route, the limiter helper and its constants |
| `apps/api/tests/test_enh_006_change_password.py` | Create | all backend tests (Tasks 1–3) |
| `apps/web/components/ChangePasswordForm.tsx` | Create | the form, its states, focus and a11y behaviour |
| `apps/web/app/account/password/page.tsx` | Create | server page: auth gate, `PublicShell`, back link, `.action-card` |
| `apps/web/components/HeaderAuthActions.tsx` | Modify | one "Password" link (public header) |
| `apps/web/components/PortalShell.tsx` | Modify | additive: sidebar-footer link + one appended mobile-menu item (every portal role) |
| `apps/web/tests/components/ChangePasswordForm.test.tsx` | Create | form unit tests |
| `apps/web/tests/components/PortalShell.test.tsx` | Create | portal entry-point unit tests |
| `apps/web/tests/e2e/enh-006-change-password.spec.ts` | Create | E2E (desktop, keyboard, mobile) |
| `docs/architecture/API_CONTRACT.md`, `docs/architecture/SECURITY_CONTROLS.md`, `docs/quality/RTM.md`, `docs/delivery/ENHANCEMENT_BACKLOG.md` | Modify | documentation (Task 8) |

---

### Task 1: Endpoint core — schema, route, validation, authorization, audit

**Files:**
- Create: `apps/api/tests/test_enh_006_change_password.py`
- Modify: `apps/api/app/schemas.py` (add class after `ProfileUpdate`)
- Modify: `apps/api/app/api/auth.py` (import line 18; constant after line 23; new route at end of file)

**Interfaces:**
- Produces: `ChangePasswordRequest(current_password: str, new_password: str)` in `app.schemas`; `POST /api/v1/auth/change-password` → `200 {"ok": true}`; module constant `CHANGE_PASSWORD_FAILED = "auth.change_password_failed"` in `app.api.auth`; test helpers `_make_user`, `_sign_in`, `_signed_in_user`, `_rows`, `_password_is` and constants `PASSWORD`, `NEW_PASSWORD`, `URL`, `FAILED`, `CHANGED` in the test file (Tasks 2–3 reuse them).

- [ ] **Step 1: Confirm a green baseline for the suites this feature sits next to**

Run `BACKEND_TEST` variants: `docker compose exec api python -m pytest -q tests/test_role_assignments.py tests/test_sec_001_audit_trail.py`
Expected: PASS. Record the counts. If anything already fails, stop and report it — do not attribute it to ENH-006 later.

- [ ] **Step 2: Write the failing tests**

Create `apps/api/tests/test_enh_006_change_password.py`:

```python
"""ENH-006 / DEC-SCOPE-021 -- self-service change password (authenticated).
Spec: docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md

Every test creates its own user: never change a seeded account's password (other suites log in with it).
"""

import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.models import AuditLog, User

PASSWORD = "Sup3r-Secret-Pass!"
NEW_PASSWORD = "Brand-New-Pass-1!"
URL = "/api/v1/auth/change-password"
FAILED = "auth.change_password_failed"
CHANGED = "auth.change_password"


async def _make_user(db_session, *, role="it_student", division="it", active=True) -> User:
    user = User(email=f"enh006-{uuid.uuid4().hex[:10]}@example.local", password_hash=hash_password(PASSWORD), full_name="ENH-006 User", role=role, division=division, active=active, email_verified=True)
    db_session.add(user)
    await db_session.commit()
    return user


async def _sign_in(client, user, password=PASSWORD):
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": password, "division": user.division})
    assert response.status_code == 200, response.text


async def _signed_in_user(client, db_session, **kwargs) -> User:
    user = await _make_user(db_session, **kwargs)
    await _sign_in(client, user)
    return user


async def _rows(db_session, user, action) -> list[AuditLog]:
    return list((await db_session.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == action))).all())


async def _password_is(db_session, user, password) -> bool:
    await db_session.refresh(user)
    return verify_password(password, user.password_hash)


@pytest.mark.asyncio
async def test_change_password_succeeds_and_only_the_new_password_logs_in(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "set-cookie" not in response.headers  # no token or cookie is reissued
    assert await _password_is(db_session, user, NEW_PASSWORD)
    login = {"email": user.email, "division": user.division}
    assert (await client.post("/api/v1/auth/login", json={**login, "password": NEW_PASSWORD})).status_code == 200
    assert (await client.post("/api/v1/auth/login", json={**login, "password": PASSWORD})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("role,division", [("it_student", "it"), ("overseas_admin", "overseas"), ("school_coordinator", "overseas"), ("super_admin", "global")])
async def test_every_role_changes_its_own_password_and_gets_one_audit_row(client, db_session, role, division):
    user = await _signed_in_user(client, db_session, role=role, division=division)
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert await _password_is(db_session, user, NEW_PASSWORD)
    assert len(await _rows(db_session, user, CHANGED)) == 1
    assert await _rows(db_session, user, FAILED) == []


@pytest.mark.asyncio
async def test_a_change_never_touches_another_account(client, db_session):
    other = await _make_user(db_session)
    await _signed_in_user(client, db_session)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    assert await _password_is(db_session, other, PASSWORD)


@pytest.mark.asyncio
async def test_a_wrong_current_password_is_400_changes_nothing_and_is_audited_as_denied(client, db_session):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": "not-the-password", "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json() == {"detail": "Incorrect current password"}
    assert await _password_is(db_session, user, PASSWORD)
    rows = await _rows(db_session, user, FAILED)
    assert len(rows) == 1
    assert rows[0].outcome == "denied"
    assert rows[0].metadata_json == {"reason": "incorrect_current_password"}
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_no_session_is_401_even_when_the_body_is_also_invalid(client):
    assert (await client.post(URL, json={"current_password": "", "new_password": "x"})).status_code == 401
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 401


@pytest.mark.asyncio
async def test_a_deactivated_account_session_is_401(client, db_session):
    user = await _signed_in_user(client, db_session)
    user.active = False
    await db_session.commit()
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"current_password": PASSWORD, "new_password": "short-9ch"},
        {"current_password": PASSWORD, "new_password": "x" * 129},
        {"current_password": "", "new_password": NEW_PASSWORD},
        {"current_password": PASSWORD},
        {"new_password": NEW_PASSWORD},
    ],
    ids=["new-too-short", "new-too-long", "current-empty", "new-missing", "current-missing"],
)
async def test_a_malformed_body_is_422_changes_nothing_and_uses_no_attempt(client, db_session, payload):
    user = await _signed_in_user(client, db_session)
    assert (await client.post(URL, json=payload)).status_code == 422
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_a_new_password_equal_to_the_current_one_is_422_and_no_oracle(client, db_session):
    user = await _signed_in_user(client, db_session)
    for current in (PASSWORD, "not-the-password"):  # correct or wrong: the same answer, so it reveals nothing
        response = await client.post(URL, json={"current_password": current, "new_password": current})
        assert response.status_code == 422
        assert response.json() == {"detail": "New password must be different from the current password"}
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `BACKEND_TEST` (whole file).
Expected: FAIL — the endpoint does not exist (`404`/`405` instead of `200`/`400`/`422`; the 401 tests may pass or fail with 404). Confirm they fail for that reason, not an import error.

- [ ] **Step 4: Add the schema**

In `apps/api/app/schemas.py`, immediately after the `ProfileUpdate` class:

```python
class ChangePasswordRequest(BaseModel):
    # ENH-006. Passwords are never stripped or normalised. current_password is bounded (not at 128) so a legacy
    # long password still works while the input stays finite; new_password follows the registration/reset rule.
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=10, max_length=128)
```

- [ ] **Step 5: Add the route**

In `apps/api/app/api/auth.py`: change the schemas import (line 18) to

```python
from app.schemas import ChangePasswordRequest, LoginRequest, LoginResponse, ProfileUpdate, RegistrationRequest, UserOut
```

add below `logger = logging.getLogger("app.auth")`:

```python
CHANGE_PASSWORD_FAILED = "auth.change_password_failed"
```

and append at the end of the file (after `reset_password`, which stays untouched):

```python
@router.post("/change-password")
async def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # ENH-006 / DEC-SCOPE-021. The order of these checks is part of the contract (spec §4): authenticate (the
    # dependency) -> body validation (the model) -> same-password compare -> lock -> verify -> write. The compare is
    # between the two request fields only, so it reveals nothing about the stored hash.
    if payload.new_password == payload.current_password:
        raise HTTPException(422, "New password must be different from the current password")
    # get_current_user loaded this row without a lock: lock it and refresh the hash in one statement, so a request that
    # waited behind another change verifies against the hash that change committed, not a stale one.
    await db.refresh(user, attribute_names=["password_hash"], with_for_update=True)
    if not verify_password(payload.current_password, user.password_hash):
        # Commit BEFORE raising (the update_me denial pattern) so the failure survives the error response.
        db.add(AuditLog(user_id=user.id, action=CHANGE_PASSWORD_FAILED, entity_type="user", entity_id=str(user.id), outcome="denied", metadata_json={"reason": "incorrect_current_password"}))
        await db.commit()
        raise HTTPException(400, "Incorrect current password")
    user.password_hash = hash_password(payload.new_password)
    db.add(AuditLog(user_id=user.id, action="auth.change_password", entity_type="user", entity_id=str(user.id), metadata_json={}))
    await db.commit()
    logger.info("password_changed", extra={"extra_fields": {"user_id": str(user.id)}})
    return {"ok": True}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `BACKEND_TEST` (copy the changed `app/` and `tests/` first).
Expected: PASS for every test in the file. If `test_no_session_is_401_even_when_the_body_is_also_invalid` returns `422` instead of `401`, FastAPI is validating the body before the dependency: fix by taking the body as `payload: dict = Body(...)` is **not** allowed — instead keep the model and move the `Depends(get_current_user)` parameter first in the signature, and re-run; if it still returns `422`, stop and report (the contract order in the spec must be revisited with the user).

- [ ] **Step 7: Lint**

Run: `cd apps/api; python -m ruff check app/api/auth.py app/schemas.py tests/test_enh_006_change_password.py` (skip if the venv is not installed and say so).
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add apps/api/app/schemas.py apps/api/app/api/auth.py apps/api/tests/test_enh_006_change_password.py
git commit -m "feat(enh-006): add POST /auth/change-password with audit and validation

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: Rate limit — 5 wrong attempts per 15 minutes per user

**Files:**
- Modify: `apps/api/tests/test_enh_006_change_password.py` (append)
- Modify: `apps/api/app/api/auth.py` (imports, constants, helper, one block in the route)

**Interfaces:**
- Consumes: Task 1 helpers/constants; `CHANGE_PASSWORD_FAILED`.
- Produces: `async def _change_password_wait_seconds(db: AsyncSession, user_id: UUID) -> int` (0 = allowed; else seconds 1–900); constants `CHANGE_PASSWORD_MAX_FAILURES = 5`, `CHANGE_PASSWORD_WINDOW = timedelta(minutes=15)`; test helper `_seed_failures(db_session, user, ages_minutes)`.

- [ ] **Step 1: Write the failing tests**

In the test file's imports, add `from datetime import UTC, datetime, timedelta` (above `import pytest`, in the standard-library group). Then append to the test file:

```python
async def _seed_failures(db_session, user, ages_minutes):
    """Insert denied change-password audit rows, each back-dated by the given number of minutes."""
    now = datetime.now(UTC)
    for age in ages_minutes:
        db_session.add(
            AuditLog(user_id=user.id, action=FAILED, entity_type="user", entity_id=str(user.id), outcome="denied", metadata_json={"reason": "incorrect_current_password"}, created_at=now - timedelta(minutes=age))
        )
    await db_session.commit()


WRONG = {"current_password": "not-the-password", "new_password": NEW_PASSWORD}


@pytest.mark.asyncio
async def test_five_wrong_attempts_are_400_and_the_sixth_is_429_with_retry_after(client, db_session):
    user = await _signed_in_user(client, db_session)
    for _ in range(5):
        assert (await client.post(URL, json=WRONG)).status_code == 400
    blocked = await client.post(URL, json=WRONG)
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers["Retry-After"]) <= 900
    assert "try again in" in blocked.json()["detail"]
    assert len(await _rows(db_session, user, FAILED)) == 5  # the blocked attempt added no row


@pytest.mark.asyncio
async def test_a_correct_password_is_still_refused_while_blocked(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [1, 1, 1, 1, 1])
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 429
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, CHANGED) == []


@pytest.mark.asyncio
async def test_retry_after_is_when_the_fifth_newest_failure_leaves_the_window(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [14, 13, 12, 11, 10])  # the oldest, 14 min ago, leaves the window in ~60 s
    blocked = await client.post(URL, json=WRONG)
    assert blocked.status_code == 429
    assert 55 <= int(blocked.headers["Retry-After"]) <= 61


@pytest.mark.asyncio
async def test_failures_older_than_the_window_do_not_count(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [16, 17, 18, 19, 20])
    response = await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    assert response.status_code == 200
    assert await _password_is(db_session, user, NEW_PASSWORD)


@pytest.mark.asyncio
async def test_four_recent_failures_do_not_block_and_the_fifth_wrong_attempt_arms_the_block(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [1, 2, 3, 4, 20])  # the 20-minute-old row is outside the window
    assert (await client.post(URL, json=WRONG)).status_code == 400
    assert (await client.post(URL, json=WRONG)).status_code == 429


@pytest.mark.asyncio
async def test_the_limit_is_per_user(client, db_session):
    blocked_user = await _make_user(db_session)
    await _seed_failures(db_session, blocked_user, [1, 1, 1, 1, 1])
    other = await _signed_in_user(client, db_session)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    assert await _password_is(db_session, other, NEW_PASSWORD)
    assert len(await _rows(db_session, blocked_user, FAILED)) == 5
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `BACKEND_TEST`.
Expected: the six new tests FAIL (no `429` is ever returned; e.g. `assert 400 == 429`), Task 1 tests still PASS.

- [ ] **Step 3: Implement the limiter**

In `apps/api/app/api/auth.py`, add `import math` to the imports (alphabetical, after `import logging`), and replace the single constant line added in Task 1 with:

```python
CHANGE_PASSWORD_FAILED = "auth.change_password_failed"
# DEC-SCOPE-021: 5 wrong current passwords per user per 15 minutes, counted from the audit rows written on each failure.
CHANGE_PASSWORD_MAX_FAILURES = 5
CHANGE_PASSWORD_WINDOW = timedelta(minutes=15)


async def _change_password_wait_seconds(db: AsyncSession, user_id: UUID) -> int:
    """Seconds this user must wait before another change-password attempt; 0 means allowed.

    Blocked when the newest MAX_FAILURES failures are all inside the window; the block lifts when the oldest of those
    leaves it. Derived from existing audit rows (same idea as the Re-send throttle), so it needs no table. Clamped so
    app/DB clock skew can never produce an absurd wait."""
    now = datetime.now(UTC)
    newest = (
        await db.scalars(
            select(AuditLog.created_at)
            .where(AuditLog.user_id == user_id, AuditLog.action == CHANGE_PASSWORD_FAILED, AuditLog.created_at > now - CHANGE_PASSWORD_WINDOW)
            .order_by(AuditLog.created_at.desc())
            .limit(CHANGE_PASSWORD_MAX_FAILURES)
        )
    ).all()
    if len(newest) < CHANGE_PASSWORD_MAX_FAILURES:
        return 0
    remaining = (newest[-1] + CHANGE_PASSWORD_WINDOW - now).total_seconds()
    return min(int(CHANGE_PASSWORD_WINDOW.total_seconds()), max(1, math.ceil(remaining)))
```

In the route, insert this block **immediately after** the `await db.refresh(...)` line and before `if not verify_password(...)`:

```python
    # Before bcrypt, so a blocked caller cannot burn CPU; a blocked attempt is logged but NOT audited as a failure, or a
    # lockout would extend itself forever.
    wait = await _change_password_wait_seconds(db, user.id)
    if wait:
        logger.warning("change_password_throttled", extra={"extra_fields": {"user_id": str(user.id), "wait_seconds": wait}})
        raise HTTPException(429, f"Too many incorrect attempts; try again in {wait} seconds", headers={"Retry-After": str(wait)})
```

- [ ] **Step 4: Run to verify everything passes**

Run: `BACKEND_TEST` (copy first).
Expected: PASS — all Task 1 and Task 2 tests.

- [ ] **Step 5: Lint and commit**

Run `python -m ruff check app/api/auth.py tests/test_enh_006_change_password.py` (if available), then:

```bash
git add apps/api/app/api/auth.py apps/api/tests/test_enh_006_change_password.py
git commit -m "feat(enh-006): rate-limit change-password to 5 wrong attempts per 15 minutes per user

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: Concurrency, secrets-in-logs, and a mutation check of the lock

**Files:**
- Modify: `apps/api/tests/test_enh_006_change_password.py` (append)

**Interfaces:** consumes Task 1–2 helpers. Produces nothing new. These are characterization tests of behaviour Tasks 1–2 already implement, so they are expected to pass on first run; Step 3 proves they can fail.

- [ ] **Step 1: Write the tests**

In the test file's imports add `import asyncio`, `import hashlib`, `import json`, `import logging` (standard-library group, above `import uuid`) and extend the models import to `from app.models import AuditLog, PasswordResetToken, User`. Then append:

```python
@pytest.mark.asyncio
async def test_two_simultaneous_wrong_guesses_at_attempt_five_yield_one_400_and_one_429(client, db_session):
    user = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, user, [1, 1, 1, 1])
    results = await asyncio.gather(client.post(URL, json=WRONG), client.post(URL, json=WRONG))
    assert sorted(r.status_code for r in results) == [400, 429]
    assert len(await _rows(db_session, user, FAILED)) == 5


@pytest.mark.asyncio
async def test_two_simultaneous_changes_with_the_same_current_password_yield_one_200_and_one_400(client, db_session):
    user = await _signed_in_user(client, db_session)
    first = {"current_password": PASSWORD, "new_password": "First-New-Pass-1!"}
    second = {"current_password": PASSWORD, "new_password": "Second-New-Pass-1!"}
    results = await asyncio.gather(client.post(URL, json=first), client.post(URL, json=second))
    assert sorted(r.status_code for r in results) == [200, 400]
    winner = first["new_password"] if results[0].status_code == 200 else second["new_password"]
    assert await _password_is(db_session, user, winner)
    assert len(await _rows(db_session, user, CHANGED)) == 1


@pytest.mark.asyncio
async def test_a_change_racing_a_reset_password_completes_without_error_or_deadlock(client, db_session):
    user = await _signed_in_user(client, db_session)
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    db_session.add(PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), expires_at=datetime.now(UTC) + timedelta(minutes=30)))
    await db_session.commit()
    results = await asyncio.wait_for(
        asyncio.gather(
            client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD}),
            client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "Reset-New-Pass-1!"}),
        ),
        timeout=30,
    )
    statuses = [r.status_code for r in results]
    assert 500 not in statuses  # a deadlock surfaces as a 500 (Postgres aborts one transaction)
    assert 200 in statuses


@pytest.mark.asyncio
async def test_no_password_or_hash_reaches_the_logs_or_audit_rows(client, db_session, caplog):
    caplog.set_level(logging.INFO, logger="app.auth")
    changed = await _signed_in_user(client, db_session)
    old_hash = changed.password_hash
    assert (await client.post(URL, json=WRONG)).status_code == 400
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    await db_session.refresh(changed)
    blocked = await _signed_in_user(client, db_session)
    await _seed_failures(db_session, blocked, [1, 1, 1, 1, 1])
    assert (await client.post(URL, json=WRONG)).status_code == 429

    messages = {r.getMessage() for r in caplog.records}
    assert {"password_changed", "change_password_throttled"} <= messages  # the records exist, so the scan below is not vacuous
    haystack = "\n".join(r.getMessage() + json.dumps(getattr(r, "extra_fields", {}), default=str) for r in caplog.records)
    for user in (changed, blocked):
        haystack += json.dumps([row.metadata_json for row in await _rows(db_session, user, FAILED) + await _rows(db_session, user, CHANGED)])
    for secret in (PASSWORD, NEW_PASSWORD, WRONG["current_password"], old_hash, changed.password_hash):
        assert secret not in haystack
```

- [ ] **Step 2: Run**

Run: `BACKEND_TEST`.
Expected: PASS for the whole file. If `test_two_simultaneous_changes…` fails with `[200, 200]`, or the attempt-five test fails with `[400, 400]`, the lock/refresh is not working — stop and fix `auth.py`, do not weaken the test.

- [ ] **Step 3: Mutation check — prove the concurrency tests can fail**

Temporarily comment out the line `await db.refresh(user, attribute_names=["password_hash"], with_for_update=True)` in `auth.py`, copy the file into the container, run only the three concurrency tests:
`docker compose exec api python -m pytest -q tests/test_enh_006_change_password.py -k "simultaneous"`
Expected: at least `test_two_simultaneous_changes_with_the_same_current_password…` and `test_two_simultaneous_wrong_guesses…` FAIL. Then **restore the line** (`git diff apps/api/app/api/auth.py` must show no change from Task 2's commit), copy again, re-run the file, expect PASS. Record the mutation result in the final report.

- [ ] **Step 4: Commit**

```bash
git add apps/api/tests/test_enh_006_change_password.py
git commit -m "test(enh-006): cover concurrency, reset race and secret-free logs/audit rows

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3b: Revoke unused reset links on a successful change, and security abuse-case tests

Why (spec §12, `DEC-SCOPE-021` #5): `reset_password` refuses tokens with `superseded_at` set, and `forgot_password` never revokes older tokens, so a reset link still in the mail after a change could overwrite the new password for up to 30 minutes. The abuse-case tests characterize behaviour Tasks 1–3 already provide (mass assignment, token-type confusion, type coercion, hostile strings, content type).

**Files:**
- Modify: `apps/api/tests/test_enh_006_change_password.py` (imports + append)
- Modify: `apps/api/app/api/auth.py` (one statement in the success path of `change_password`)

**Interfaces:**
- Consumes: Task 1–3 helpers (`_make_user`, `_signed_in_user`, `_rows`, `_password_is`, `URL`, `PASSWORD`, `NEW_PASSWORD`, `FAILED`, `CHANGED`, `WRONG`); existing `PasswordResetToken` columns `purpose`, `used_at`, `superseded_at`; `POST /auth/reset-password`.
- Produces: test helper `_seed_reset_token(db_session, user, *, purpose="reset", used=False) -> tuple[str, PasswordResetToken]` (raw token, row).

- [ ] **Step 1: Write the failing revocation tests**

In the test file's imports add `from httpx import ASGITransport, AsyncClient` (third-party group), `from app.main import app`, and extend the security import to `from app.core.security import create_token, hash_password, verify_password`. Then append:

```python
async def _seed_reset_token(db_session, user, *, purpose="reset", used=False):
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    now = datetime.now(UTC)
    token = PasswordResetToken(
        user_id=user.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        purpose=purpose,
        expires_at=now + timedelta(minutes=30),
        used_at=now if used else None,
    )
    db_session.add(token)
    await db_session.commit()
    return raw, token


@pytest.mark.asyncio
async def test_a_change_revokes_unused_reset_links_so_an_emailed_link_cannot_overwrite_it(client, db_session):
    user = await _signed_in_user(client, db_session)
    raw, token = await _seed_reset_token(db_session, user)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    await db_session.refresh(token)
    assert token.superseded_at is not None
    replay = await client.post("/api/v1/auth/reset-password", json={"token": raw, "new_password": "Attacker-Chosen-1!"})
    assert replay.status_code == 400
    assert replay.json() == {"detail": "Reset token is invalid or expired"}
    assert await _password_is(db_session, user, NEW_PASSWORD)


@pytest.mark.asyncio
async def test_a_change_leaves_used_links_welcome_links_and_other_users_links_alone(client, db_session):
    user = await _signed_in_user(client, db_session)
    other = await _make_user(db_session)
    _, used = await _seed_reset_token(db_session, user, used=True)
    _, welcome = await _seed_reset_token(db_session, user, purpose="welcome")
    _, others = await _seed_reset_token(db_session, other)
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 200
    for token in (used, welcome, others):
        await db_session.refresh(token)
        assert token.superseded_at is None


@pytest.mark.asyncio
async def test_a_refused_change_revokes_nothing(client, db_session):
    user = await _signed_in_user(client, db_session)
    raw, token = await _seed_reset_token(db_session, user)
    assert (await client.post(URL, json=WRONG)).status_code == 400
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": PASSWORD})).status_code == 422
    await db_session.refresh(token)
    assert token.superseded_at is None
```

- [ ] **Step 2: Run to verify the first test fails**

Run: `BACKEND_TEST`.
Expected: `test_a_change_revokes_unused_reset_links…` FAILS (`superseded_at` is `None`); the other two new tests and everything earlier PASS.

- [ ] **Step 3: Implement the revocation**

In `apps/api/app/api/auth.py`, in `change_password`, directly after `user.password_hash = hash_password(payload.new_password)` and before the success `AuditLog`, add (`update` and `PasswordResetToken` are already imported in this file):

```python
    # DEC-SCOPE-021 #5: a change also kills any reset link still in the mail (it could otherwise overwrite this password
    # for up to 30 minutes). Only unused "reset" links of THIS user: welcome links belong to accounts with no password
    # yet (ENH-003's state machine), used links are history, and other users' links are not ours.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.purpose == "reset", PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None))
        .values(superseded_at=datetime.now(UTC))
    )
```

- [ ] **Step 4: Run to verify it passes, plus the reset suite**

Run: `BACKEND_TEST`, then `docker compose exec api python -m pytest -q tests/test_enh_003_first_time_provisioning.py` (the reset/welcome behaviour must be unchanged).
Expected: PASS for both.

- [ ] **Step 5: Write the abuse-case tests** (characterization — expected to pass on first run)

Append:

```python
@pytest.mark.asyncio
async def test_extra_fields_cannot_change_role_division_email_or_anything_but_the_password(client, db_session):
    user = await _signed_in_user(client, db_session)
    original = (user.role, user.division, user.email, user.active, user.full_name)
    response = await client.post(
        URL,
        json={
            "current_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "role": "super_admin",
            "division": "global",
            "email": "attacker@example.local",
            "active": False,
            "full_name": "Hacked",
            "password_hash": "x",
            "id": str(uuid.uuid4()),
            "user_id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 200
    await db_session.refresh(user)
    assert (user.role, user.division, user.email, user.active, user.full_name) == original
    assert verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.asyncio
async def test_a_refresh_token_is_not_accepted_as_a_session_here(db_session):
    user = await _make_user(db_session)
    token = create_token(str(user.id), user.role, user.division, "refresh")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies={"edusphere_access": token}) as anonymous:
        assert (await anonymous.post(URL, json={"current_password": PASSWORD, "new_password": NEW_PASSWORD})).status_code == 401
    assert await _password_is(db_session, user, PASSWORD)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [12345678901, ["a"], {"a": 1}, True, None], ids=["int", "list", "object", "bool", "null"])
async def test_non_string_passwords_are_422_and_never_coerced(client, db_session, bad):
    user = await _signed_in_user(client, db_session)
    assert (await client.post(URL, json={"current_password": bad, "new_password": NEW_PASSWORD})).status_code == 422
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": bad})).status_code == 422
    assert await _password_is(db_session, user, PASSWORD)
    assert await _rows(db_session, user, FAILED) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hostile",
    ["'; DROP TABLE users; --", "pw\u0000tail-of-the-password", "<script>alert(1)</script>", "\U0001f511" * 30],
    ids=["sql", "nul-byte", "markup", "astral"],
)
async def test_hostile_strings_are_just_wrong_passwords_and_are_never_echoed(client, db_session, hostile):
    user = await _signed_in_user(client, db_session)
    response = await client.post(URL, json={"current_password": hostile, "new_password": NEW_PASSWORD})
    assert response.status_code == 400
    assert response.json() == {"detail": "Incorrect current password"}
    rows = await _rows(db_session, user, FAILED)
    assert len(rows) == 1
    assert hostile not in json.dumps(rows[0].metadata_json)
    assert await _password_is(db_session, user, PASSWORD)


@pytest.mark.asyncio
async def test_a_password_with_odd_characters_round_trips_as_a_new_password(client, db_session):
    user = await _signed_in_user(client, db_session)
    odd = "pässwörd-\u0000-'\"<>-\U0001f511-end"
    assert (await client.post(URL, json={"current_password": PASSWORD, "new_password": odd})).status_code == 200
    login = await client.post("/api/v1/auth/login", json={"email": user.email, "password": odd, "division": user.division})
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_the_endpoint_does_not_accept_a_non_json_body(client, db_session):
    # A cross-site "simple request" (text/plain or a form) must not be able to carry the JSON. SameSite=Lax cookies and the
    # current-password requirement are the primary CSRF defences; this is the third. If this fails, the image's FastAPI
    # parses non-JSON content types as JSON: report it to the user -- do not change app-wide body parsing here.
    user = await _signed_in_user(client, db_session)
    body = json.dumps({"current_password": PASSWORD, "new_password": NEW_PASSWORD})
    for content_type in ("text/plain", "application/x-www-form-urlencoded"):
        response = await client.post(URL, content=body, headers={"Content-Type": content_type})
        assert response.status_code == 422
    assert await _password_is(db_session, user, PASSWORD)
```

- [ ] **Step 6: Run**

Run: `BACKEND_TEST`.
Expected: PASS for the whole file. A failure in `test_the_endpoint_does_not_accept_a_non_json_body` is a finding to report (see the test's comment), not something to "fix" by weakening the assertion.

- [ ] **Step 7: Lint and commit**

Run `python -m ruff check app/api/auth.py tests/test_enh_006_change_password.py` (if available), then:

```bash
git add apps/api/app/api/auth.py apps/api/tests/test_enh_006_change_password.py
git commit -m "feat(enh-006): revoke unused reset links on change; add security abuse-case tests

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `ChangePasswordForm` component

**Files:**
- Create: `apps/web/tests/components/ChangePasswordForm.test.tsx`
- Create: `apps/web/components/ChangePasswordForm.tsx`

**Interfaces:**
- Consumes: `refocus(id: string): void` from `@/lib/focus` (existing helper: puts keyboard focus back after a control was disabled while busy).
- Produces: default export `ChangePasswordForm({ email, forgotPasswordHref }: { email: string; forgotPasswordHref?: string })`. `email` feeds a visually hidden read-only username field (password managers use it to update the right saved login; it is never sent). `forgotPasswordHref` is `/it/forgot-password`, `/overseas/forgot-password`, or omitted for the global division (which has no forgot-password page). Posts `{current_password, new_password}` to `/api/v1/auth/change-password`. Element ids: `change-current-password`, `change-new-password`, `change-show-passwords`, `change-password-submit`, `change-password-error`, `change-password-hint`. Form: `aria-label="Change password"`, `aria-busy` while pending. Error in `.form-error` `role="alert"`; success in `.form-message` `role="status"`.

Behaviour (spec §6):

| Outcome | Message | Field marked / focus | Extras |
|---|---|---|---|
| 200 | "Your password was changed." | focus → submit button; fields cleared | |
| 400 | server's "Incorrect current password" | current field `aria-invalid`, **cleared**, focused (new password kept) | "Forgot your current password?" link if `forgotPasswordHref` |
| 422 | server message (string or list) | new field `aria-invalid`, focused | |
| 429 | "Too many incorrect attempts. Try again in N minutes." from `Retry-After` (static text, not a live countdown); server message if the header is unusable | focus → submit button | |
| 401 | "Your session has expired…" | focus → submit button | links to both login pages with `?next=%2Faccount%2Fpassword` |
| network failure | "…could not confirm whether your password was changed. Sign in with your new password; if that fails, try again." | focus → submit button | never claims success |
| any other status | server message or "Unable to change password. Try again in a moment." | focus → submit button | |

Also: a second `submit` event while a request is pending is ignored (a repeat submit after success would return 400 and burn a rate-limit attempt); a native "Show passwords" checkbox switches both inputs between `password` and `text` without losing what was typed; a muted note under the form says other devices stay signed in until their sessions expire (`DEC-SCOPE-021` #3).

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ChangePasswordForm from "@/components/ChangePasswordForm";

const json = (body: unknown, status: number, headers: Record<string, string> = {}) => new Response(JSON.stringify(body), { status, headers });

function stubFetch(response: Response) {
  const mock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", mock);
  return mock;
}

// Passing `{}` renders the form without a forgot-password link (the global division has none); a bare `undefined` argument
// would trigger the default and hide that case.
function renderForm(props: { forgotPasswordHref?: string } = { forgotPasswordHref: "/it/forgot-password" }) {
  return render(<ChangePasswordForm email="asha@example.local" {...props} />);
}

function fill(current = "Sup3r-Secret-Pass!", next = "Brand-New-Pass-1!") {
  fireEvent.change(screen.getByLabelText("Current password"), { target: { value: current } });
  fireEvent.change(screen.getByLabelText("New password"), { target: { value: next } });
}

function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Change password" }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ChangePasswordForm (ENH-006)", () => {
  it("posts both passwords, confirms, clears the fields and returns focus to the button on success", async () => {
    const mock = stubFetch(json({ ok: true }, 200));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed.");
    expect(mock).toHaveBeenCalledWith(
      "/api/v1/auth/change-password",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ current_password: "Sup3r-Secret-Pass!", new_password: "Brand-New-Pass-1!" }) }),
    );
    expect(screen.getByLabelText("Current password")).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("");
    expect(screen.queryByRole("alert")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Change password" })).toHaveFocus());
  });

  it("disables the button and marks the form busy while the request is pending", async () => {
    let release!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; })));
    renderForm();
    fill();
    submit();
    const button = await screen.findByRole("button", { name: "Changing…" });
    expect(button).toBeDisabled();
    expect(screen.getByRole("form", { name: "Change password" })).toHaveAttribute("aria-busy", "true");
    release(json({ ok: true }, 200));
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed.");
    expect(screen.getByRole("button", { name: "Change password" })).toBeEnabled();
    expect(screen.getByRole("form", { name: "Change password" })).toHaveAttribute("aria-busy", "false");
  });

  it("ignores a second submit while one is pending (a repeat after success would burn a rate-limit attempt)", async () => {
    let release!: (response: Response) => void;
    const mock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { release = resolve; }));
    vi.stubGlobal("fetch", mock);
    renderForm();
    fill();
    const form = screen.getByRole("form", { name: "Change password" });
    fireEvent.submit(form);
    fireEvent.submit(form); // implicit submission / a second event must not slip past the disabled button
    expect(mock).toHaveBeenCalledTimes(1);
    release(json({ ok: true }, 200));
    expect(await screen.findByRole("status")).toBeInTheDocument();
  });

  it("wrong current password (400): generic message, current field flagged, cleared and focused, new password kept, recovery link offered", async () => {
    stubFetch(json({ detail: "Incorrect current password" }, 400));
    renderForm();
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Incorrect current password");
    const current = screen.getByLabelText("Current password");
    expect(current).toHaveAttribute("aria-invalid", "true");
    expect(current).toHaveAttribute("aria-describedby", "change-password-error");
    expect(current).toHaveValue("");
    expect(screen.getByLabelText("New password")).toHaveValue("Brand-New-Pass-1!");
    expect(screen.getByRole("link", { name: "Forgot your current password?" })).toHaveAttribute("href", "/it/forgot-password");
    expect(screen.queryByRole("status")).toBeNull();
    await waitFor(() => expect(current).toHaveFocus());
  });

  it("offers no forgot-password link when the account's division has none", async () => {
    stubFetch(json({ detail: "Incorrect current password" }, 400));
    renderForm({});
    fill();
    submit();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Forgot your current password?" })).toBeNull();
  });

  it("validation error (422), string or list: message shown, new field flagged and focused", async () => {
    stubFetch(json({ detail: "New password must be different from the current password" }, 422));
    renderForm();
    fill("Same-Password-1!", "Same-Password-1!");
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("New password must be different from the current password");
    const next = screen.getByLabelText("New password");
    expect(next).toHaveAttribute("aria-invalid", "true");
    expect(next).toHaveAttribute("aria-describedby", "change-password-hint change-password-error");
    await waitFor(() => expect(next).toHaveFocus());
    expect(screen.queryByRole("link", { name: "Forgot your current password?" })).toBeNull();
    cleanup();
    stubFetch(json({ detail: [{ msg: "String should have at least 10 characters" }] }, 422));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("String should have at least 10 characters");
  });

  it("turns Retry-After into minutes for a rate-limited attempt (429) and flags no field", async () => {
    stubFetch(json({ detail: "Too many incorrect attempts; try again in 720 seconds" }, 429, { "Retry-After": "720" }));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many incorrect attempts. Try again in 12 minutes.");
    expect(screen.getByLabelText("Current password")).not.toHaveAttribute("aria-invalid");
    expect(screen.getByLabelText("New password")).not.toHaveAttribute("aria-invalid");
  });

  it("falls back to the server message for a 429 without a usable Retry-After", async () => {
    stubFetch(json({ detail: "Too many incorrect attempts; try again in 30 seconds" }, 429));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Too many incorrect attempts; try again in 30 seconds");
  });

  it("sends an expired session (401) back to the sign-in pages and returns here afterwards", async () => {
    stubFetch(json({ detail: "Invalid session" }, 401));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Your session has expired");
    expect(screen.getByRole("link", { name: "IT Training sign in" })).toHaveAttribute("href", "/it/login?next=%2Faccount%2Fpassword");
    expect(screen.getByRole("link", { name: "Overseas Education sign in" })).toHaveAttribute("href", "/overseas/login?next=%2Faccount%2Fpassword");
  });

  it("says the outcome is unconfirmed when the network fails, and does not claim success", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderForm();
    fill();
    submit();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("could not confirm whether your password was changed");
    expect(alert).toHaveTextContent("Sign in with your new password");
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("shows a calm message for an unexpected server error", async () => {
    stubFetch(json({}, 500));
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to change password. Try again in a moment.");
  });

  it("clears the previous error when the user tries again", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ detail: "Incorrect current password" }, 400)).mockResolvedValueOnce(json({ ok: true }, 200));
    vi.stubGlobal("fetch", mock);
    renderForm();
    fill();
    submit();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Current password"), { target: { value: "Sup3r-Secret-Pass!" } });
    submit();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(await screen.findByRole("status")).toHaveTextContent("Your password was changed.");
    expect(screen.getByLabelText("Current password")).not.toHaveAttribute("aria-invalid");
  });

  it("labels the inputs, describes the length rule, and sets the autocomplete tokens", () => {
    renderForm();
    const current = screen.getByLabelText("Current password");
    const next = screen.getByLabelText("New password");
    expect(current).toHaveAttribute("autocomplete", "current-password");
    expect(next).toHaveAttribute("autocomplete", "new-password");
    expect(next).toHaveAttribute("minlength", "10");
    expect(next).toHaveAttribute("maxlength", "128");
    expect(next).toHaveAttribute("aria-describedby", "change-password-hint");
    expect(document.getElementById("change-password-hint")).toHaveTextContent("Use at least 10 characters.");
  });

  it("carries a hidden read-only username for password managers that is never sent", async () => {
    const mock = stubFetch(json({ ok: true }, 200));
    renderForm();
    const username = document.querySelector('input[name="username"]') as HTMLInputElement;
    expect(username).toHaveValue("asha@example.local");
    expect(username).toHaveAttribute("autocomplete", "username");
    expect(username).toHaveAttribute("readonly");
    expect(username).toHaveAttribute("aria-hidden", "true");
    expect(username).toHaveAttribute("tabindex", "-1");
    fill();
    submit();
    await screen.findByRole("status");
    expect(String(mock.mock.calls[0][1].body)).not.toContain("asha@example.local");
  });

  it("shows and hides both passwords with a native checkbox without losing what was typed", () => {
    renderForm();
    fill();
    const toggle = screen.getByRole("checkbox", { name: "Show passwords" });
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "password");
    fireEvent.click(toggle);
    expect(screen.getByLabelText("Current password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "text");
    expect(screen.getByLabelText("New password")).toHaveValue("Brand-New-Pass-1!");
    fireEvent.click(toggle);
    expect(screen.getByLabelText("New password")).toHaveAttribute("type", "password");
  });

  it("tells the user other devices stay signed in", () => {
    renderForm();
    expect(screen.getByText(/other devices stay signed in until their sessions expire/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run `WEB_UNIT`: `cd apps/web; npx vitest run tests/components/ChangePasswordForm.test.tsx`
Expected: FAIL — cannot resolve `@/components/ChangePasswordForm`.

- [ ] **Step 3: Implement the component**

Create `apps/web/components/ChangePasswordForm.tsx`:

```tsx
"use client";

import { FormEvent, useRef, useState } from "react";
import Link from "next/link";
import { refocus } from "@/lib/focus";

function message(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  }
  return "Unable to change password. Try again in a moment.";
}

function waitLabel(seconds: number) {
  const minutes = Math.ceil(seconds / 60);
  return minutes <= 1 ? "a minute" : `${minutes} minutes`;
}

// Where a signed-out visitor returns to after signing in (LoginForm honours `?next=`).
const NEXT = encodeURIComponent("/account/password");

export default function ChangePasswordForm({ email, forgotPasswordHref }: { email: string; forgotPasswordHref?: string }) {
  const [error, setError] = useState("");
  const [errorField, setErrorField] = useState<"current" | "new" | null>(null);
  const [notice, setNotice] = useState("");
  const [signedOut, setSignedOut] = useState(false);
  const [showPasswords, setShowPasswords] = useState(false);
  const [busy, setBusy] = useState(false);
  // State lags a render, so a second submit event could slip past `busy`; a repeat after success would be a 400 that
  // burns one of the five rate-limit attempts.
  const submitting = useRef(false);

  function finish(focusId: string) {
    submitting.current = false;
    setBusy(false);
    refocus(focusId); // a control disabled while busy loses keyboard focus; put it where the user needs it next
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    setErrorField(null);
    setNotice("");
    setSignedOut(false);
    const data = new FormData(form);
    let response: Response;
    try {
      response = await fetch("/api/v1/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: data.get("current_password"), new_password: data.get("new_password") }),
      });
    } catch {
      // The server commits the change BEFORE it answers, so a lost response is an unknown outcome -- and resubmitting
      // the same form would fail with "Incorrect current password" if the change did go through.
      setError("Network error -- we could not confirm whether your password was changed. Sign in with your new password; if that fails, try again.");
      finish("change-password-submit");
      return;
    }
    const body = await response.json().catch(() => ({}));
    if (response.ok) {
      form.reset();
      setNotice("Your password was changed.");
      finish("change-password-submit");
      return;
    }
    if (response.status === 401) {
      setSignedOut(true);
      finish("change-password-submit");
      return;
    }
    if (response.status === 429) {
      const seconds = Number(response.headers.get("Retry-After"));
      setError(Number.isFinite(seconds) && seconds > 0 ? `Too many incorrect attempts. Try again in ${waitLabel(seconds)}.` : message(body.detail));
      finish("change-password-submit");
      return;
    }
    setError(message(body.detail));
    if (response.status === 400) {
      // Clear the wrong value, keep the new password the user already typed, and put the cursor where they retype.
      const current = form.elements.namedItem("current_password");
      if (current instanceof HTMLInputElement) current.value = "";
      setErrorField("current");
      finish("change-current-password");
      return;
    }
    if (response.status === 422) {
      setErrorField("new");
      finish("change-new-password");
      return;
    }
    finish("change-password-submit");
  }

  const inputType = showPasswords ? "text" : "password";

  return (
    <form className="form" onSubmit={submit} aria-label="Change password" aria-busy={busy}>
      {/* Lets password managers update the right saved login. Visually hidden, not focusable, never sent. */}
      <input type="text" name="username" autoComplete="username" value={email} readOnly tabIndex={-1} aria-hidden="true" style={{ position: "absolute", width: 1, height: 1, opacity: 0, pointerEvents: "none" }} />
      <div className="field">
        <label htmlFor="change-current-password">Current password</label>
        <input
          id="change-current-password"
          name="current_password"
          type={inputType}
          maxLength={1024}
          autoComplete="current-password"
          autoCapitalize="off"
          spellCheck={false}
          aria-invalid={errorField === "current" ? true : undefined}
          aria-describedby={errorField === "current" ? "change-password-error" : undefined}
          required
        />
      </div>
      <div className="field">
        <label htmlFor="change-new-password">New password</label>
        <input
          id="change-new-password"
          name="new_password"
          type={inputType}
          minLength={10}
          maxLength={128}
          autoComplete="new-password"
          autoCapitalize="off"
          spellCheck={false}
          aria-invalid={errorField === "new" ? true : undefined}
          aria-describedby={errorField === "new" ? "change-password-hint change-password-error" : "change-password-hint"}
          required
        />
        <span id="change-password-hint" className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>
      </div>
      <div className="field">
        <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <input id="change-show-passwords" type="checkbox" checked={showPasswords} onChange={(event) => setShowPasswords(event.target.checked)} />
          Show passwords
        </label>
      </div>
      {error && (
        <div id="change-password-error" className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>{error}</p>
          {errorField === "current" && forgotPasswordHref && (
            <p style={{ margin: "6px 0 0" }}>
              <Link href={forgotPasswordHref} style={{ color: "var(--blue)", fontWeight: 800 }}>Forgot your current password?</Link>
            </p>
          )}
        </div>
      )}
      {signedOut && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>Your session has expired. Sign in again to change your password.</p>
          <p style={{ margin: "6px 0 0" }}>
            <Link href={`/it/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>IT Training sign in</Link>{" "}
            <Link href={`/overseas/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>Overseas Education sign in</Link>
          </p>
        </div>
      )}
      {notice && (
        <div className="form-message" role="status" aria-live="polite">
          {notice}
        </div>
      )}
      <button id="change-password-submit" className="btn" disabled={busy}>
        {busy ? "Changing…" : "Change password"}
      </button>
      <p className="muted" style={{ fontSize: 13, margin: 0 }}>
        You stay signed in on this device. Other devices stay signed in until their sessions expire.
      </p>
    </form>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run `WEB_UNIT` for the file. Expected: PASS (16 tests). If jsdom rejects `role="form"` lookup by `aria-label`, keep the `aria-label` (it is the accessible name) and query with `container.querySelector("form")` in the three affected tests, and say so in the report.

- [ ] **Step 5: Commit**

```bash
git add apps/web/components/ChangePasswordForm.tsx apps/web/tests/components/ChangePasswordForm.test.tsx
git commit -m "feat(enh-006): add the change-password form with focus, error, rate-limit and show-password handling

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `/account/password` page and the public-header link

**Files:**
- Create: `apps/web/app/account/password/page.tsx`
- Modify: `apps/web/components/HeaderAuthActions.tsx` (one line after the "Privacy" link, line 54)
- Test (added during execution, written and seen failing before the code): `apps/web/tests/components/HeaderAuthActions.test.tsx`, `apps/web/tests/components/AccountPasswordPage.test.tsx` (the page's own decisions — division→forgot-password link, back link, `?next=` links, signed-out card — asserted on the returned element tree without rendering the site shell)

**Interfaces:**
- Consumes: `ChangePasswordForm` (Task 4); `PublicShell` (existing: site header, `<main>`, footer); `serverApi<User>`; `ROLE_DASHBOARD_PATH`.
- Produces: route `/account/password`. Signed-out → "Sign in required" card whose links carry `?next=%2Faccount%2Fpassword`. Signed-in → "← Back to dashboard" link, `h1` "Change your password", "Signed in as …", and the form inside the existing `.action-card`. Header link text exactly "Password".

- [ ] **Step 1: Create the page**

```tsx
import Link from "next/link";
import ChangePasswordForm from "@/components/ChangePasswordForm";
import PublicShell from "@/components/PublicShell";
import { serverApi } from "@/lib/api";
import { ROLE_DASHBOARD_PATH } from "@/lib/navigation";
import type { User } from "@/lib/types";

// ENH-006: like /account/privacy (SEC-002), this belongs to no one role's portal nav (`PORTAL_NAV`), so it is one shared
// route. Unlike that page it renders inside PublicShell (site header, footer) and links back to the role's dashboard, so
// it is never a dead end. It gates itself: /account/* is outside middleware.ts's matcher, and the API re-checks the
// session on every request regardless.
const NEXT = encodeURIComponent("/account/password");

export default async function AccountPasswordPage() {
  let user: User;
  try {
    user = await serverApi<User>("/api/v1/auth/me");
  } catch {
    return (
      <PublicShell>
        <div className="section">
          <div className="container card">
            <h1>Sign in required</h1>
            <p className="muted">You need to be signed in to change your password.</p>
            <div className="actions">
              <a className="btn" href={`/it/login?next=${NEXT}`}>IT Training sign in</a>
              <a className="btn secondary" href={`/overseas/login?next=${NEXT}`}>Overseas Education sign in</a>
            </div>
          </div>
        </div>
      </PublicShell>
    );
  }
  const division = user.division === "it" || user.division === "overseas" ? user.division : undefined;
  return (
    <PublicShell division={division}>
      <div className="section compact">
        <div className="container" style={{ maxWidth: 560 }}>
          <Link href={ROLE_DASHBOARD_PATH[user.role] || "/"} className="muted">← Back to dashboard</Link>
          <h1 style={{ fontSize: 34, marginTop: 14 }}>Change your password</h1>
          <p className="muted">Signed in as {user.full_name} ({user.email}).</p>
          <div className="action-card">
            <ChangePasswordForm email={user.email} forgotPasswordHref={division ? `/${division}/forgot-password` : undefined} />
          </div>
        </div>
      </div>
    </PublicShell>
  );
}
```

- [ ] **Step 2: Add the public-header link**

In `apps/web/components/HeaderAuthActions.tsx`, directly after `<Link className="btn secondary" href="/account/privacy">Privacy</Link>` add:

```tsx
      <Link className="btn secondary" href="/account/password">Password</Link>
```

- [ ] **Step 3: Typecheck and lint**

Run: `cd apps/web; npm run typecheck; npm run lint`
Expected: clean.

- [ ] **Step 4: Run the unit suites that scan or render this code**

Run `WEB_UNIT`: `cd apps/web; npx vitest run tests/components/ChangePasswordForm.test.tsx tests/components/ResetPasswordForm.test.tsx tests/lib/no-default-password.test.ts`
Expected: PASS (the no-default-password guard scans the new copy).

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/account/password/page.tsx apps/web/components/HeaderAuthActions.tsx
git commit -m "feat(enh-006): add /account/password inside the site shell and a header link to it

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Portal entry point — `PortalShell` (desktop sidebar + mobile menu)

Why: `HeaderAuthActions` renders only in the public site header. Portal pages use `PortalShell`, which has no header; at ≤980 px its sidebar is hidden and the mobile menu shows only the role's nav items. Without this task a signed-in student inside their portal, especially on a phone, has no way to the page. (Spec §6, approved 2026-09-21.)

**Files:**
- Create: `apps/web/tests/components/PortalShell.test.tsx`
- Modify: `apps/web/components/PortalShell.tsx` (two additive edits; the file is one long line — edit by exact substring)

**Interfaces:**
- Consumes: existing `PortalShell({children, nav, roleLabel, userName, studentCode})` and `MobileNavToggle({nav, …})`.
- Produces: a "Change password" `Link` (`href="/account/password"`) in `.sidebar-footer` above "Sign out"; the same link appended as the last item of the array passed to the mobile `MobileNavToggle` only. The desktop `.portal-nav` and every role's `nav` array are unchanged.

- [ ] **Step 1: Find any existing tests that render `PortalShell` (they must stay green)**

Run: `cd apps/web; grep -rln PortalShell tests components app | grep -v node_modules`
Note the test files, if any; they are part of Step 5.

- [ ] **Step 2: Write the failing test**

```tsx
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/it/student/dashboard",
}));

const nav = [
  { href: "/it/student/dashboard", label: "Dashboard" },
  { href: "/it/student/courses", label: "My courses" },
];

function renderShell() {
  return render(
    <PortalShell nav={nav} roleLabel="IT Student" userName="Asha">
      <p>page content</p>
    </PortalShell>,
  );
}

afterEach(cleanup);

describe("PortalShell change-password entry point (ENH-006)", () => {
  it("offers Change password in the desktop sidebar footer beside Sign out", () => {
    const { container } = renderShell();
    const footer = container.querySelector(".sidebar-footer") as HTMLElement;
    expect(within(footer).getByRole("link", { name: "Change password" })).toHaveAttribute("href", "/account/password");
    expect(within(footer).getByRole("button", { name: "Sign out" })).toBeInTheDocument();
  });

  it("appends it to the mobile menu after the role's own items, and leaves the desktop nav untouched", () => {
    const { container } = renderShell();
    const desktop = container.querySelector(".portal-nav") as HTMLElement;
    expect(within(desktop).getAllByRole("link").map((link) => link.textContent)).toEqual(["Dashboard", "My courses"]);
    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const mobile = container.querySelector("#portal-mobile-nav-panel") as HTMLElement;
    expect(within(mobile).getAllByRole("link").map((link) => link.textContent)).toEqual(["Dashboard", "My courses", "Change password"]);
  });

  it("still renders the page content", () => {
    renderShell();
    expect(screen.getByText("page content")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run to verify it fails**

Run `WEB_UNIT`: `cd apps/web; npx vitest run tests/components/PortalShell.test.tsx`
Expected: the first two tests FAIL (no such link). If the file fails to load because `next/image` cannot run under jsdom, add `vi.mock("next/image", () => ({ default: (props: { alt: string }) => <img alt={props.alt} /> }));` and re-run; the expected failure is still the missing link.

- [ ] **Step 4: Make the two additive edits in `PortalShell.tsx`**

Replace (exact substring):
`<div className="sidebar-footer"><button className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} onClick={logout}>Sign out</button></div>`
with:
`<div className="sidebar-footer" style={{display:"grid",gap:10,justifyItems:"start"}}><Link className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} href="/account/password">Change password</Link><button className="btn ghost small" style={{color:"white",borderColor:"#45668e"}} onClick={logout}>Sign out</button></div>`

Replace (exact substring):
`<MobileNavToggle nav={nav} buttonClassName="portal-mobile-menu"`
with:
`<MobileNavToggle nav={[...nav,{href:"/account/password",label:"Change password"}]} buttonClassName="portal-mobile-menu"`

- [ ] **Step 5: Run to verify it passes, then the neighbours**

Run `WEB_UNIT`: `cd apps/web; npx vitest run tests/components/PortalShell.test.tsx` — expect PASS (3 tests). Then run `npm run typecheck; npm run lint` and every test file found in Step 1 — expect green.

- [ ] **Step 6: Commit**

```bash
git add apps/web/components/PortalShell.tsx apps/web/tests/components/PortalShell.test.tsx
git commit -m "feat(enh-006): link every portal to the change-password page (sidebar footer and mobile menu)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Playwright spec

**Files:**
- Create: `apps/web/tests/e2e/enh-006-change-password.spec.ts`

**Interfaces:** consumes the running stack with the new API and rebuilt `web` image. Each test registers its own throwaway student (register also sets the session cookies on the shared browser context and the student's dashboard is `/it/student/dashboard`).

- [ ] **Step 1: Write the spec**

```ts
import { test, expect, type Page } from "@playwright/test";

// ENH-006 -- self-service change password (DEC-SCOPE-021). Requires the stack running via `docker compose up` with the
// api and web images rebuilt after this change. Every test registers its own throwaway student and never changes a
// seeded account's password (other specs sign in with it).

const OLD_PASSWORD = "Sup3r-Secret-Pass!";
const NEW_PASSWORD = "Brand-New-Pass-1!";

async function registerStudent(page: Page) {
  const email = `enh006-e2e-${Date.now()}-${Math.floor(Math.random() * 1_000_000)}@example.local`;
  const registered = await page.request.post("/api/v1/auth/register", {
    data: { email, password: OLD_PASSWORD, full_name: "E2E Change Password", division: "it", account_type: "student" },
  });
  expect(registered.ok()).toBeTruthy();
  return email; // registering also signed this browser context in
}

async function fillAndSubmit(page: Page, current: string, next: string) {
  await page.getByLabel("Current password").fill(current);
  await page.getByLabel("New password").fill(next);
  await page.getByRole("button", { name: "Change password" }).click();
}

const login = (page: Page, email: string, password: string) => page.request.post("/api/v1/auth/login", { data: { email, password, division: "it" } });

test("a signed-in user changes their password through the page and only the new one signs in (ENH-006)", async ({ page }) => {
  const email = await registerStudent(page);
  await page.goto("/account/password");
  await expect(page.getByRole("heading", { name: "Change your password" })).toBeVisible();
  await fillAndSubmit(page, OLD_PASSWORD, NEW_PASSWORD);
  await expect(page.locator(".form-message")).toHaveText("Your password was changed.");
  await page.request.post("/api/v1/auth/logout");
  expect((await login(page, email, OLD_PASSWORD)).status()).toBe(401);
  expect((await login(page, email, NEW_PASSWORD)).status()).toBe(200);
});

test("the form can be completed and submitted from the keyboard (ENH-006 accessibility)", async ({ page }) => {
  const email = await registerStudent(page);
  await page.goto("/account/password");
  await page.getByLabel("Current password").focus();
  await page.keyboard.type(OLD_PASSWORD);
  await page.keyboard.press("Tab");
  await page.keyboard.type(NEW_PASSWORD);
  await page.keyboard.press("Enter");
  await expect(page.locator(".form-message")).toHaveText("Your password was changed.");
  await expect(page.getByRole("button", { name: "Change password" })).toBeFocused();
  await page.request.post("/api/v1/auth/logout");
  expect((await login(page, email, NEW_PASSWORD)).status()).toBe(200);
});

test("a wrong current password shows the generic error, clears and refocuses that field, and offers recovery (ENH-006)", async ({ page }) => {
  const email = await registerStudent(page);
  await page.goto("/account/password");
  await fillAndSubmit(page, "not-the-password", NEW_PASSWORD);
  await expect(page.locator(".form-error")).toContainText("Incorrect current password");
  await expect(page.getByLabel("Current password")).toHaveValue("");
  await expect(page.getByLabel("Current password")).toBeFocused();
  await expect(page.getByLabel("New password")).toHaveValue(NEW_PASSWORD);
  await expect(page.getByRole("link", { name: "Forgot your current password?" })).toHaveAttribute("href", "/it/forgot-password");
  await expect(page.locator(".form-message")).toHaveCount(0);
  expect((await login(page, email, OLD_PASSWORD)).status()).toBe(200);
});

test("after five wrong attempts the page shows the rate-limit message, even for the right password (ENH-006)", async ({ page }) => {
  const email = await registerStudent(page);
  for (let i = 0; i < 5; i++) {
    const wrong = await page.request.post("/api/v1/auth/change-password", { data: { current_password: "not-the-password", new_password: NEW_PASSWORD } });
    expect(wrong.status()).toBe(400);
  }
  await page.goto("/account/password");
  await fillAndSubmit(page, OLD_PASSWORD, NEW_PASSWORD);
  await expect(page.locator(".form-error")).toContainText("Too many incorrect attempts");
  expect((await login(page, email, OLD_PASSWORD)).status()).toBe(200); // the password was not changed
});

test("Show passwords reveals both fields and hides them again (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/account/password");
  await expect(page.getByLabel("New password")).toHaveAttribute("type", "password");
  await page.getByLabel("Show passwords").check();
  await expect(page.getByLabel("Current password")).toHaveAttribute("type", "text");
  await expect(page.getByLabel("New password")).toHaveAttribute("type", "text");
  await page.getByLabel("Show passwords").uncheck();
  await expect(page.getByLabel("New password")).toHaveAttribute("type", "password");
});

test("a signed-out visitor is sent to sign in and lands back on the password page (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.request.post("/api/v1/auth/logout");
  await page.goto("/account/password");
  await expect(page.getByRole("heading", { name: "Sign in required" })).toBeVisible();
  await page.getByRole("link", { name: "IT Training sign in" }).click();
  await page.waitForURL("**/it/login**");
  await page.fill("#login-email", "student.it@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/account/password");
  await expect(page.getByRole("heading", { name: "Change your password" })).toBeVisible();
});

test("the Password link is reachable from the signed-in public header (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/it");
  await page.getByRole("link", { name: "Password", exact: true }).click();
  await page.waitForURL("**/account/password");
  await expect(page.getByRole("heading", { name: "Change your password" })).toBeVisible();
});

test("a portal user reaches the page from the sidebar and can go back to their dashboard (ENH-006)", async ({ page }) => {
  await registerStudent(page);
  await page.goto("/it/student/dashboard");
  await page.locator(".sidebar-footer").getByRole("link", { name: "Change password" }).click();
  await page.waitForURL("**/account/password");
  await page.getByRole("link", { name: "← Back to dashboard" }).click();
  await page.waitForURL("**/it/student/dashboard");
});

test("on a 375px phone the portal menu leads to a usable page with no horizontal scroll (ENH-006 mobile)", async ({ page }) => {
  await registerStudent(page);
  await page.setViewportSize({ width: 375, height: 667 });
  await page.goto("/it/student/dashboard");
  await page.getByRole("button", { name: "Open menu" }).click();
  await page.locator("#portal-mobile-nav-panel").getByRole("link", { name: "Change password" }).click();
  await page.waitForURL("**/account/password");
  await expect(page.getByLabel("Current password")).toBeVisible();
  await expect(page.getByLabel("New password")).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const button = page.getByRole("button", { name: "Change password" });
  expect((await button.boundingBox())!.height).toBeGreaterThanOrEqual(44); // touch target
  await fillAndSubmit(page, OLD_PASSWORD, NEW_PASSWORD);
  await expect(page.locator(".form-message")).toHaveText("Your password was changed.");
});
```

- [ ] **Step 2: Run against the rebuilt stack**

Ask the user to rebuild and recreate `api` and `web`, and wait for them to say the stack is up. Then run:
`cd apps/web; npx playwright test tests/e2e/enh-006-change-password.spec.ts --workers=1`
Expected: 9 PASS. The signed-out test signs in as the seeded demo student (read-only use: it never changes that account). If a test fails, re-run it alone once (`AGENTS.md`: warming cache / shared-DB contention) before diagnosing; open traces only for failures. Do not weaken an assertion to pass.

- [ ] **Step 3: Run the neighbouring specs (regression — `PortalShell` and the header changed)**

Run: `npx playwright test tests/e2e/auth-001-login.spec.ts tests/e2e/auth-002-rbac-ui.spec.ts tests/e2e/sec-002-gdpr-data-requests.spec.ts tests/e2e/sch-001-school-portal-access.spec.ts tests/e2e/adm-014-super-admin-console.spec.ts tests/e2e/desktop-nav-dropdown.spec.ts tests/e2e/stu-011-profile-documents.spec.ts tests/e2e/trn-001-mobile-nav.spec.ts --workers=1`
Expected: PASS (the added header link and portal link must not break their selectors).

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-006-change-password.spec.ts
git commit -m "test(enh-006): add the change-password Playwright spec

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---
### Task 8: Documentation

**Files:**
- Modify: `docs/architecture/API_CONTRACT.md` (§1 table, after the `PATCH /auth/me` row, line ~53)
- Modify: `docs/architecture/SECURITY_CONTROLS.md` (§1 after the "Welcome-link Re-send throttle" row, line ~30; §10 after "Actor + outcome recorded", line ~133)
- Modify: `docs/quality/RTM.md` (new addendum + row after the `ENH-004` row, line ~209)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (ENH-006 section, after its "Dependencies" paragraph; the row at line 109 stays)

- [ ] **Step 1: `API_CONTRACT.md` §1** — add this row after the `PATCH /auth/me` row:

```markdown
| `POST /auth/change-password` | Authenticated | Self | `ENH-006` / `DEC-SCOPE-021`. Body `{current_password, new_password}`; `new_password` 10–128 characters. `200 {"ok": true}`. `400 "Incorrect current password"` is the only message for a wrong current password. `422` for a malformed body, a length violation, or a new password identical to the current one — none of these consumes an attempt. `429` + integer `Retry-After` (seconds) after 5 wrong current passwords in 15 minutes for that user, including for a correct password while blocked. `401` without a session (checked before body validation). Failures are audited as `auth.change_password_failed` (`outcome=denied`), a change as `auth.change_password`. A successful change also revokes the user's unused password-reset links. Other sessions are **not** invalidated (access tokens live 60 minutes, refresh tokens 14 days — accepted risk, `DEC-SCOPE-021`). **Not safe to retry blindly:** if a response is lost after the change was committed, a retry (which still carries the old current password) returns `400` and counts as a failed attempt. No `Idempotency-Key` (§0.2). Errors use FastAPI's `{"detail": …}` body, as every route does. |
```

- [ ] **Step 2: `SECURITY_CONTROLS.md`** — add to §1 after the Re-send throttle row:

```markdown
| Change-password brute-force limit | `POST /auth/change-password` allows 5 wrong current passwords per user per 15 minutes (`429` + `Retry-After`), keyed on the authenticated user id (never IP) and counted from the `auth.change_password_failed` audit rows, so it needs no table. The check runs before bcrypt, and blocked attempts are not counted, so a lockout cannot extend itself. **Depends on those audit rows not being purged inside the 15-minute window.** Login, forgot-password and reset-password remain unthrottled — the open item above still stands. A successful change revokes the user's unused password-reset links. **Accepted risks (`DEC-SCOPE-021`):** other sessions survive a password change — a stolen refresh cookie stays usable for up to 14 days (`refresh_token_days`; access tokens 60 minutes) because `/auth/refresh` does not consult the password; a holder of a stolen session can lock the victim out of this route for 15 minutes at a time (forgot-password is unaffected); blocked attempts are logged, not audited, so a flood cannot grow `audit_logs`. | Guessing the current password from a hijacked session | `ENH-006` |
```

and to §10 after the "Actor + outcome recorded" row:

```markdown
| Password-change audit | `auth.change_password` and `auth.change_password_failed` (`outcome=denied`) rows carry ids only — never a password or hash. The failure row is committed before the `400` is raised, so it survives the error and feeds the limiter | Forensics; limiter integrity | `ENH-006` |
```

- [ ] **Step 3: `RTM.md`** — read lines ~196–212, then add (matching the column set of the `ENH-004` row directly above and the addendum style) an addendum "**Addendum, 2026-09-21 (`ENH-006`)**" with one row `ENH-006` whose cells state: contract `API_CONTRACT.md` §1 (`POST /auth/change-password`), `SECURITY_CONTROLS.md` §1/§10, no `DATA_MODEL.md` change (no migration); status **COMPLETE** only after Task 9 passes, otherwise "IN PROGRESS"; evidence: `apps/api/tests/test_enh_006_change_password.py`, `apps/web/tests/components/ChangePasswordForm.test.tsx`, `apps/web/tests/components/PortalShell.test.tsx`, `apps/web/tests/e2e/enh-006-change-password.spec.ts`, with the **exact counts from the real runs** in Task 9 (never estimated), and the open items from spec §11.

- [ ] **Step 4: `ENHANCEMENT_BACKLOG.md`** — under ENH-006, after "Dependencies", add:

```markdown
**Status (2026-09-21).** Designed and decided in `docs/superpowers/specs/2026-09-21-enh-006-change-password-design.md` (`DEC-SCOPE-021`); implemented on branch `feature/enh-006-change-password`. Corrections to this entry: the routes are now at `forgot_password()` line 175 / `reset_password()` line 198; the minimum-length rule is the registration/reset rule (10–128), not `accept_invite`'s; the audit actions are `auth.change_password` / `auth.change_password_failed`, not `auth.password_change`; database impact is still none (the limiter counts existing audit rows); other sessions are **not** invalidated. Open, not decided here: login/forgot/reset throttling, session invalidation, a notification email, and the public header hiding its secondary buttons on phones (the portal menu now carries the entry point; spec §11).
```

- [ ] **Step 5: Consistency check and commit**

Run: `git diff --stat` — only the four docs plus earlier files. Re-read each added row once for wording that overstates (nothing "verified" that Task 9 has not run).

```bash
git add docs/architecture/API_CONTRACT.md docs/architecture/SECURITY_CONTROLS.md docs/quality/RTM.md docs/delivery/ENHANCEMENT_BACKLOG.md
git commit -m "docs(enh-006): record the change-password contract, controls and traceability

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 9: Final verification and review gate

**Files:** none new (fixes go in the file they belong to, with a test).

- [ ] **Step 1: Backend targeted regression** (never the full suite — `deps.py`/JWT are untouched)

Run: `docker compose exec api python -m pytest -q tests/test_enh_006_change_password.py tests/test_role_assignments.py tests/test_sec_001_audit_trail.py tests/test_sec_002_gdpr_data_requests.py tests/test_enh_003_first_time_provisioning.py`
Expected: all PASS; compare the counts with Task 1 Step 1 for the two suites measured there.

- [ ] **Step 2: Frontend checks**

Run: `cd apps/web; npm test; npm run typecheck; npm run lint` — expected all green. (`npm run build` only if the user wants it; the `web` image rebuild in Task 7 already compiled the pages.)

- [ ] **Step 3: Spec traceability check** — for each of AC-01…AC-11 in the spec, name the passing test that proves it (AC-10 and AC-11: the revocation and abuse-case tests of Task 3b; AC-08: `ChangePasswordForm.test.tsx`, `PortalShell.test.tsx` and the 375 px, keyboard and show-passwords E2E tests; AC-09: Steps 1–2 above, the neighbouring E2E specs from Task 7 Step 3, and `git diff main --stat` showing no edit to any file listed under "Do not change" beyond the two additive frontend links). Any AC without evidence is a gap: fix or report it.

- [ ] **Step 4: Independent review** — dispatch the `agent-skills:code-reviewer` and `agent-skills:security-auditor` agents on `git diff main...HEAD` with the spec path; ask the security auditor to walk every row of spec §12 and try to break AC-10/AC-11; ask the reviewer to check the frontend against Global Constraints (design-language reuse, accessibility, focus handling) as well as the backend. Address findings with tests first; re-run Steps 1–2 after any fix.

- [ ] **Step 5: Report honestly** — what changed, the exact tests run and their outcomes (targeted, not a full regression; say so), the mutation-check result, migrations: none, config: none, and the open items (spec §11). Use `superpowers:verification-before-completion` before claiming done. Do not push, and open a PR only if the user asks.
