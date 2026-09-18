# ENH-003 First-Time Provisioning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every admin-provisioned account receives a single-use, hashed-at-rest, 72-hour emailed set-password link instead of a default/admin-known password; admins can see links that expired unused and Re-send.

**Architecture:** Extend `password_reset_tokens` with `purpose` + `superseded_at` (one additive migration, no new table). One new functions-only module `app/services/provisioning.py` (issue / deliver / status derivation) plus one mailer function; the three create routes, `reset_password`, `GET /admin/users`, `GET /admin/dashboard` change additively; one new endpoint `POST /admin/users/{id}/welcome-links`. Frontend (reviewed against frontend-ui-engineering; existing design language reused): a small shared feedback/request helper with a success/warning/error tone, one appended CSS block, directory status pill + filter + Re-send, one new list-style dashboard panel, reset-page recovery link, and Vitest component tests alongside Playwright.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, pytest + pytest-asyncio + httpx (backend); Next.js/React, Vitest, Playwright (frontend).

**Spec:** `docs/superpowers/specs/2026-09-19-enh-003-first-time-provisioning-design.md` (read it alongside this plan). Decision record: `DEC-SCOPE-019` in `docs/decisions/PRODUCT_DECISION_REGISTER.md`; backlog item `ENH-003`. `AC-nn` IDs below are spec-local — never cite them from `API_CONTRACT.md`/`RTM.md`.

## Global Constraints

- Welcome link expiry is **72 hours**; forgot-password resets stay **30 minutes**.
- **No password is ever accepted, generated-and-shown, stored in cleartext, logged, or returned** for an admin-provisioned account. No route falls back to a default password. New accounts get `unusable_password_hash()` (hash of a discarded random secret).
- A stray `password` (`coordinator_password` on schools) in any of the 3 create payloads → **`422`**, no user created. Check order: auth → authz `403` → `422` → existing validation → duplicate-email `409`.
- Tokens are stored only as SHA-256 hex; the raw token never appears in the DB, audit `metadata_json`, logs, or any production response. `development_welcome_token` is returned **only** when `settings.environment in ("development","test")`.
- Commit-then-send: user + role assignment + token commit together; the email is sent **after** commit; a failed/`not_configured` send never rolls back creation. `deliver_welcome_link` never raises.
- `reset_password`: length checks (`422`, 10–128 characters) first, then one atomic `UPDATE … WHERE used_at IS NULL AND superseded_at IS NULL AND expires_at > now RETURNING`; a welcome token for an **inactive** account is refused (rolled back, not consumed); every failure is the same `400 "Reset token is invalid or expired"`.
- Existing conventions: snake_case fields, lowercase enum values, `{"detail": "<string>"}` errors, raw-`dict` payloads, no new Pydantic models, no new dependencies, no `Idempotency-Key`.
- **UI rules (Tasks 7-10):** reuse `.status`/`.badge`/`.btn small`/`.form-message`/`.form-error`/`.collection-summary`; new CSS only in the one appended `controls.css` block; state is never colour-only (text always present); one always-mounted `role="status"` outcome region per panel; per-row buttons carry an `aria-label` naming the person; focus is restored or moved after an action ends; a created-but-not-emailed account is an amber **warning**, not an error; `prefers-reduced-motion` respected; ≥ 44 px touch targets at ≤ 640 px; no `event.currentTarget` after an `await` (RAID I-05); no new dependency; `DataTable` is not modified.
- **Security hardening (review 2026-09-19, user-approved):** create routes validate email with the repo's existing pattern `^[^\s@]+@[^\s@]+\.[^\s@]+$` (≤ 255 characters) → `422`; the mailer and `deliver_welcome_link` treat a raising sender as a failed send (never a `500`); stored delivery errors have URLs redacted; welcome links are refused for inactive accounts and revoked whenever an admin actually changes `active`; Re-send has a 60-second per-account cooldown (`429` + `Retry-After`); the reset page is never reported to Google Analytics and is served with `Referrer-Policy: no-referrer`; passwords are capped at 128 characters. Status is derived from the user's **latest** welcome token so a revoked link stays Re-sendable.
- Do **not** touch `SchoolAccountInvite`/`accept_invite`, `forgot_password`, self-registration, `get_current_user`, `ensure_admin`, `send_notification`, or `update_user` beyond the single revoke-on-`active`-change step in Task 6.
- Do **not** fix the pre-existing issues listed in spec §2 non-goals.
- **Environment:** every step that needs the database (migration, pytest DB tests, Playwright) runs only after the user confirms their docker stack is up — never start/stop docker yourself. Run targeted tests per task; **one** full backend regression in Task 11.
- **Commits:** commit steps run only with the user's approval. Commit messages end with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.

---

### Task 0: Branch state, environment gate, baseline

- [ ] **Step 1: Report working-tree state and get the user's isolation decision**

```bash
git branch --show-current
git status --short | head -50
```

The current branch carries substantial uncommitted work (including this session's edits to `docs/decisions/PRODUCT_DECISION_REGISTER.md` and the untracked `docs/delivery/ENHANCEMENT_BACKLOG.md`, the spec and this plan). A `git worktree` starts from a commit and will **not** contain them. Ask the user to choose: (a) commit the ENH-003 docs first (after reviewing `git diff` of the register, which also holds earlier changes), then `git worktree add ../edusphere-enh-003 -b feature/enh-003-first-time-provisioning`; or (b) work in place on the current branch. Do not proceed without an answer.

- [ ] **Step 2: Ask the user to confirm the docker stack is up, and how they apply migrations**

Do not run docker. Ask them to confirm and to tell you the command they use for `alembic upgrade head` (Task 1 needs it).

- [ ] **Step 3: Record the baseline**

Run from `apps/api`:

```bash
python -m pytest tests/test_role_assignments.py tests/test_not_001_email_notifications.py tests/test_mailer.py tests/test_sch_003_school_onboarding.py tests/test_enh_001_academic_year.py tests/test_sch_school_staff_provisioning.py -q
```

Expected: all pass. Write down the pass count; later tasks must not reduce it.

---

### Task 1: Model columns + migration `0031` (+ the new test file's helpers)

**Files:**
- Modify: `apps/api/app/models.py` (`PasswordResetToken`, ~line 914)
- Create: `apps/api/alembic/versions/0031_welcome_token_purpose.py`
- Create: `apps/api/tests/test_enh_003_first_time_provisioning.py`

**Interfaces:**
- Produces (test helpers reused by every later task, all in the new test file): `PASSWORD`, `NEW_PASSWORD`, `_email()`, `_sha(raw)`, `_make_user(db_session, *, role, division, active, email_verified, password)`, `_login(client, email, password, division)`, `_seed_token(db_session, user, *, purpose, expires_in, used, superseded, created_at) -> (raw, token)`.
- Produces (schema): `PasswordResetToken.purpose: str` (default `"reset"`), `PasswordResetToken.superseded_at: datetime | None`.

- [ ] **Step 1: Write the failing test file (helpers + schema tests)**

```python
"""ENH-003 / DEC-SCOPE-019 -- first-time provisioning: emailed, single-use, 72-hour set-password
link for admin-provisioned accounts. Spec: docs/superpowers/specs/2026-09-19-enh-003-first-time-provisioning-design.md
"""

import asyncio
import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.models import AuditLog, PasswordResetToken, User

PASSWORD = "Sup3r-Secret-Pass!"
NEW_PASSWORD = "Brand-New-Pass-1!"


def _email(prefix: str = "enh003") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.local"


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _make_user(db_session, *, role="overseas_admin", division="overseas", active=True, email_verified=True, password=PASSWORD) -> User:
    user = User(email=_email(), password_hash=hash_password(password), full_name="ENH-003 User", role=role, division=division, active=active, email_verified=email_verified)
    db_session.add(user)
    await db_session.commit()
    return user


async def _login(client, email: str, password: str = PASSWORD, division: str = "overseas"):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password, "division": division})


async def _seed_token(db_session, user, *, purpose="welcome", expires_in=timedelta(hours=72), used=False, superseded=False, created_at=None):
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    now = datetime.now(UTC)
    token = PasswordResetToken(
        user_id=user.id, token_hash=_sha(raw), purpose=purpose, expires_at=now + expires_in,
        used_at=now if used else None, superseded_at=now if superseded else None,
    )
    if created_at is not None:
        token.created_at = created_at
    db_session.add(token)
    await db_session.commit()
    return raw, token


# --- Task 1: schema -------------------------------------------------------------------

@pytest.mark.asyncio
async def test_password_reset_tokens_have_purpose_and_superseded_columns(db_session):
    conn = await db_session.connection()
    columns = await conn.run_sync(lambda sync_conn: {c["name"]: c for c in sa.inspect(sync_conn).get_columns("password_reset_tokens")})
    assert "purpose" in columns and "superseded_at" in columns
    assert columns["purpose"]["nullable"] is False
    assert columns["superseded_at"]["nullable"] is True


@pytest.mark.asyncio
async def test_a_token_created_without_a_purpose_defaults_to_reset(db_session):
    user = await _make_user(db_session)
    token = PasswordResetToken(user_id=user.id, token_hash=_sha(uuid.uuid4().hex), expires_at=datetime.now(UTC) + timedelta(minutes=30))
    db_session.add(token)
    await db_session.commit()
    await db_session.refresh(token)
    assert token.purpose == "reset"
    assert token.superseded_at is None
```

- [ ] **Step 2: Run to verify it fails**

Run (from `apps/api`): `python -m pytest tests/test_enh_003_first_time_provisioning.py -v`
Expected: FAIL (`purpose`/`superseded_at` not present / `TypeError: 'purpose' is an invalid keyword argument`).

- [ ] **Step 3: Add the model columns**

In `apps/api/app/models.py`, replace the `PasswordResetToken` class body's last line:

```python
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

with:

```python
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ENH-003 / DEC-SCOPE-019: "reset" (forgot-password, 30 min) or "welcome" (admin-provisioned
    # first-time set-password link, 72 h). `superseded_at` is set when an admin Re-send replaces an
    # unused welcome token.
    purpose: Mapped[str] = mapped_column(String(20), default="reset", server_default="reset")
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Create the migration**

```python
"""ENH-003 -- password_reset_tokens.purpose + superseded_at (welcome links for admin-provisioned accounts).

Revision ID: 0031_welcome_token_purpose
Revises: 0030_academic_years

docs/superpowers/specs/2026-09-19-enh-003-first-time-provisioning-design.md §4. Additive only.
`purpose` is NOT NULL with a server default of 'reset', which backfills every existing row without a
rewrite; no index (two values, no selectivity -- the user_id index already serves the queries).
"""

from alembic import op
import sqlalchemy as sa

revision = "0031_welcome_token_purpose"
down_revision = "0030_academic_years"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c["name"] for c in inspector.get_columns("password_reset_tokens")}
    if "purpose" not in existing:
        op.add_column("password_reset_tokens", sa.Column("purpose", sa.String(20), nullable=False, server_default="reset"))
    if "superseded_at" not in existing:
        op.add_column("password_reset_tokens", sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("password_reset_tokens", "superseded_at")
    op.drop_column("password_reset_tokens", "purpose")
```

- [ ] **Step 5: Ask the user to apply the migration, then run the tests**

Ask the user to run `alembic upgrade head` in their API environment. Then:
Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -v`
Expected: PASS (2 tests). Also confirm existing rows: ask the user to run (or run via their DB tool) `SELECT purpose, count(*) FROM password_reset_tokens GROUP BY purpose;` → only `reset`.

- [ ] **Step 6: Commit** (with approval)

```bash
git add apps/api/app/models.py apps/api/alembic/versions/0031_welcome_token_purpose.py apps/api/tests/test_enh_003_first_time_provisioning.py
git commit -m "feat(enh-003): add purpose and superseded_at to password_reset_tokens" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `mailer.send_welcome_email`

**Files:**
- Modify: `apps/api/app/services/mailer.py`
- Test: `apps/api/tests/test_enh_003_first_time_provisioning.py` (append)

**Interfaces:**
- Consumes: `settings.smtp_host`, `settings.smtp_from_email`, `settings.frontend_url`, existing `_send_sync`, `ROLE_LABELS`.
- Produces: `async def send_welcome_email(*, to_email: str, recipient_name: str, role: str, set_password_url: str, expires_at: datetime, invited_by_name: str) -> tuple[str, str | None]` returning `("not_configured"|"sent"|"failed", error)`.

- [ ] **Step 1: Append the failing tests**

```python
# --- Task 2: welcome email ------------------------------------------------------------

from app.services import mailer  # noqa: E402

LINK = "https://example.local/overseas/reset-password?token=abc123"


def _configure_smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "smtp.example.local")
    monkeypatch.setattr(settings, "smtp_from_email", "no-reply@edusphere.local")
    monkeypatch.setattr(settings, "smtp_username", None)
    monkeypatch.setattr(settings, "smtp_password", None)


def _welcome_kwargs(**overrides):
    base = dict(to_email="new.staff@example.local", recipient_name="Asha", role="academic_team", set_password_url=LINK, expires_at=datetime.now(UTC) + timedelta(hours=72), invited_by_name="Overseas Admin")
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_welcome_email_reports_not_configured_without_smtp(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", None)
    assert await mailer.send_welcome_email(**_welcome_kwargs()) == ("not_configured", None)


@pytest.mark.asyncio
async def test_welcome_email_carries_the_link_and_expiry_and_no_password(monkeypatch):
    _configure_smtp(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    status, error = await mailer.send_welcome_email(**_welcome_kwargs())
    assert (status, error) == ("sent", None)
    msg = sent[0]
    assert msg["To"] == "new.staff@example.local"
    assert "no-reply@edusphere.local" in msg["From"]
    text = msg.get_body(preferencelist=("plain",)).get_content()
    html_body = msg.get_body(preferencelist=("html",)).get_content()
    assert LINK in text and LINK in html_body
    assert "72 hours" in text
    assert "ChangeMe" not in text and "ChangeMe" not in html_body


@pytest.mark.asyncio
async def test_welcome_email_escapes_names_in_html(monkeypatch):
    _configure_smtp(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    await mailer.send_welcome_email(**_welcome_kwargs(recipient_name="<b>Eve</b>", invited_by_name="<i>Admin</i>"))
    html_body = sent[0].get_body(preferencelist=("html",)).get_content()
    assert "<b>Eve</b>" not in html_body and "&lt;b&gt;Eve&lt;/b&gt;" in html_body
    assert "<i>Admin</i>" not in html_body


@pytest.mark.asyncio
async def test_welcome_email_reports_a_send_failure(monkeypatch):
    _configure_smtp(monkeypatch)

    def boom(msg):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(mailer, "_send_sync", boom)
    status, error = await mailer.send_welcome_email(**_welcome_kwargs())
    assert status == "failed" and "smtp down" in error


@pytest.mark.asyncio
async def test_welcome_email_never_raises_on_a_malformed_address(monkeypatch):
    _configure_smtp(monkeypatch)
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: None)
    status, error = await mailer.send_welcome_email(**_welcome_kwargs(to_email="victim@example.local\r\nBcc: attacker@example.local"))
    assert status == "failed" and error
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -k welcome_email -v`
Expected: FAIL — `AttributeError: module 'app.services.mailer' has no attribute 'send_welcome_email'`.

- [ ] **Step 3: Implement**

In `apps/api/app/services/mailer.py`, change the imports block

```python
import asyncio
import smtplib
from datetime import datetime
from email.message import EmailMessage
```

to

```python
import asyncio
import smtplib
from datetime import UTC, datetime
from email.message import EmailMessage
from html import escape
```

and append at the end of the file:

```python
# --- ENH-003 / DEC-SCOPE-019: first-time set-password link for admin-provisioned accounts -------

WELCOME_EXPIRY_HOURS_LABEL = "72 hours"


def _welcome_html(*, recipient_name: str, role_label: str, set_password_url: str, expires_at: datetime, invited_by_name: str) -> str:
    logo_url = f"{settings.frontend_url}/brand/logo-dark.png"
    expires_label = expires_at.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    name, role, inviter = escape(recipient_name), escape(role_label), escape(invited_by_name)
    url = escape(set_password_url, quote=True)
    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f7fb;font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#0f2850;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f7fb;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 4px 18px rgba(15,40,80,.08);">
            <tr>
              <td style="background:#0a1e3f;padding:28px 32px;">
                <img src="{logo_url}" alt="EduSphere" height="40" style="display:block;">
              </td>
            </tr>
            <tr>
              <td style="padding:32px;">
                <h1 style="font-size:20px;margin:0 0 16px;">Welcome to EduSphere</h1>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">Hi {name},</p>
                <p style="font-size:15px;line-height:1.6;margin:0 0 16px;">
                  {inviter} has created your EduSphere account as <strong>{role}</strong>. Set your password to get started.
                </p>
                <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0;">
                  <tr>
                    <td style="border-radius:12px;background:#1554d8;">
                      <a href="{url}" style="display:inline-block;padding:14px 28px;color:#ffffff;font-weight:700;font-size:15px;text-decoration:none;">Set your password</a>
                    </td>
                  </tr>
                </table>
                <p style="font-size:13px;line-height:1.6;color:#60738b;margin:0 0 8px;">
                  This link is single-use and expires in {WELCOME_EXPIRY_HOURS_LABEL} ({expires_label}). If the button doesn't work, copy and paste this link into your browser:
                </p>
                <p style="font-size:13px;line-height:1.6;word-break:break-all;margin:0;">
                  <a href="{url}" style="color:#1554d8;">{url}</a>
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:20px 32px;background:#f8fafc;border-top:1px solid #edf1f6;">
                <p style="font-size:12px;color:#60738b;margin:0;">
                  Didn't expect this? You can safely ignore this email.
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def _welcome_text(*, recipient_name: str, role_label: str, set_password_url: str, expires_at: datetime, invited_by_name: str) -> str:
    expires_label = expires_at.astimezone(UTC).strftime("%d %b %Y %H:%M UTC")
    return (
        f"Hi {recipient_name},\n\n"
        f"{invited_by_name} has created your EduSphere account as {role_label}.\n\n"
        f"Set your password: {set_password_url}\n\n"
        f"This link is single-use and expires in {WELCOME_EXPIRY_HOURS_LABEL} ({expires_label}).\n\n"
        f"Didn't expect this? You can safely ignore this email."
    )


async def send_welcome_email(
    *, to_email: str, recipient_name: str, role: str, set_password_url: str, expires_at: datetime, invited_by_name: str,
) -> tuple[str, str | None]:
    """ENH-003: the first-time set-password email for an admin-provisioned account. Same
    (status, error) contract as the invite mailer: `not_configured` is a normal, reportable
    state that never blocks the account creation that triggered it."""
    if not settings.smtp_host or not settings.smtp_from_email:
        return "not_configured", None
    role_label = ROLE_LABELS.get(role, role.replace("_", " ").title())
    try:
        # Building the message is inside the try on purpose: a malformed address makes EmailMessage
        # raise ValueError, and a send problem must never escape as a 500 after the account committed.
        msg = EmailMessage()
        msg["Subject"] = "Welcome to EduSphere -- set your password"
        msg["From"] = f"EduSphere <{settings.smtp_from_email}>"
        msg["To"] = to_email
        fields = dict(recipient_name=recipient_name, role_label=role_label, set_password_url=set_password_url, expires_at=expires_at, invited_by_name=invited_by_name)
        msg.set_content(_welcome_text(**fields))
        msg.add_alternative(_welcome_html(**fields), subtype="html")
        await asyncio.to_thread(_send_sync, msg)
        return "sent", None
    except Exception as exc:
        return "failed", str(exc)[:500]
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py tests/test_mailer.py -v`
Expected: PASS (new 5 + existing mailer tests unchanged).

- [ ] **Step 5: Commit** (with approval): `git add apps/api/app/services/mailer.py apps/api/tests/test_enh_003_first_time_provisioning.py && git commit -m "feat(enh-003): add welcome set-password email to the mailer" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 3: `services/provisioning.py`

**Files:**
- Create: `apps/api/app/services/provisioning.py`
- Test: `apps/api/tests/test_enh_003_first_time_provisioning.py` (append)

**Interfaces:**
- Consumes: `PasswordResetToken` (Task 1), `mailer.send_welcome_email` (Task 2), `send_notification`, `hash_password`, `AuditLog`.
- Produces (exact names later tasks import):
  - `WELCOME_EXPIRY_HOURS = 72`, `DEV_TOKEN_ENVIRONMENTS = ("development", "test")`, `RESEND_COOLDOWN_SECONDS = 60`
  - `class IssuedWelcome(NamedTuple): raw: str; expires_at: datetime; token_id: UUID`
  - `class Provisioning(NamedTuple): status: str; expires_at: datetime`
  - `def unusable_password_hash() -> str`
  - `async def revoke_welcome_tokens(db, user_id: UUID) -> None` (no commit; supersedes the user's open welcome tokens)
  - `async def issue_welcome_token(db, *, user: User, issued_by: User) -> IssuedWelcome` (no commit; revokes open tokens, inserts a new one, flushes, writes the `user.welcome_link_issue` audit row)
  - `async def deliver_welcome_link(db, *, user: User, issued: IssuedWelcome, issued_by: User) -> dict` (after commit; **never raises**; URLs redacted from stored errors)
  - `async def provisioning_statuses(db, user_ids) -> dict[UUID, Provisioning]` (absent ⇒ active). Status comes from the user's **latest** welcome token, superseded ones included: used ⇒ active; any token used at/after its creation ⇒ active; else `pending_setup` if unsuperseded and unexpired, `link_expired` if expired **or superseded with nothing newer** (i.e. revoked)
  - `async def user_ids_with_status(db, actor: User, status: str) -> list[UUID]` (active users only; division-scoped unless `super_admin`)
  - `async def resend_wait_seconds(db, user_id: UUID) -> int` (0 when a Re-send is allowed; otherwise seconds to wait, at most 60)

Note: spec §5 named `expired_welcome_link_user_ids`; this plan generalizes it with a `status` argument. `issue_welcome_token` takes `issued_by` because it audits. Security review (2026-09-19) added `revoke_welcome_tokens`, `resend_wait_seconds`, URL redaction, and the latest-token status rule (spec §13).

- [ ] **Step 1: Append the failing tests**

```python
# --- Task 3: provisioning service -----------------------------------------------------

from app.services import provisioning  # noqa: E402


@pytest.mark.asyncio
async def test_unusable_password_hash_is_random_and_matches_nothing_guessable():
    first, second = provisioning.unusable_password_hash(), provisioning.unusable_password_hash()
    assert first != second
    assert not verify_password("ChangeMe@12345", first)


@pytest.mark.asyncio
async def test_issue_welcome_token_stores_only_the_hash_for_72_hours_and_audits_without_the_raw_token(db_session):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor", email_verified=False)
    issued = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()

    row = await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.id == issued.token_id))
    assert row.purpose == "welcome" and row.token_hash == _sha(issued.raw) and issued.raw not in row.token_hash
    assert timedelta(hours=71, minutes=59) < row.expires_at - datetime.now(UTC) <= timedelta(hours=72)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_issue"))
    assert audit is not None and issued.raw not in json.dumps(audit.metadata_json)


@pytest.mark.asyncio
async def test_a_second_issue_supersedes_the_first_and_only_one_stays_open(db_session):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor")
    first = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    second = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    rows = {r.id: r for r in (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == target.id))).all()}
    assert rows[first.token_id].superseded_at is not None
    assert rows[second.token_id].superseded_at is None


@pytest.mark.asyncio
async def test_statuses_pending_expired_resent_revoked_and_resolved(db_session):
    pending = await _make_user(db_session, role="counselor")
    expired = await _make_user(db_session, role="counselor")
    resent = await _make_user(db_session, role="counselor")
    revoked = await _make_user(db_session, role="counselor")
    consumed = await _make_user(db_session, role="counselor")
    resolved = await _make_user(db_session, role="counselor")
    plain = await _make_user(db_session, role="counselor")

    await _seed_token(db_session, pending)
    await _seed_token(db_session, expired, expires_in=timedelta(hours=-1))
    # a Re-send: the old token is superseded (and long expired), the newest one is open -> pending
    await _seed_token(db_session, resent, expires_in=timedelta(hours=-5), superseded=True, created_at=datetime.now(UTC) - timedelta(hours=100))
    await _seed_token(db_session, resent)
    # revoked (e.g. account deactivated): the only token is superseded and nothing newer exists
    await _seed_token(db_session, revoked, superseded=True)
    await _seed_token(db_session, consumed, used=True)
    # link expired, but the user later set a password through forgot-password
    await _seed_token(db_session, resolved, expires_in=timedelta(hours=-1), created_at=datetime.now(UTC) - timedelta(hours=100))
    await _seed_token(db_session, resolved, purpose="reset", used=True)

    ids = [u.id for u in (pending, expired, resent, revoked, consumed, resolved, plain)]
    result = await provisioning.provisioning_statuses(db_session, ids)
    assert result[pending.id].status == "pending_setup"
    assert result[expired.id].status == "link_expired"
    assert result[resent.id].status == "pending_setup"
    assert result[revoked.id].status == "link_expired"
    assert consumed.id not in result and resolved.id not in result and plain.id not in result
    assert await provisioning.provisioning_statuses(db_session, []) == {}


@pytest.mark.asyncio
async def test_revoke_supersedes_only_open_welcome_tokens_and_leaves_the_account_re_sendable(db_session):
    user = await _make_user(db_session, role="counselor")
    _, open_token = await _seed_token(db_session, user)
    _, used_token = await _seed_token(db_session, user, used=True, created_at=datetime.now(UTC) - timedelta(days=5))
    _, reset_token = await _seed_token(db_session, user, purpose="reset", expires_in=timedelta(minutes=30))
    await provisioning.revoke_welcome_tokens(db_session, user.id)
    await db_session.commit()
    for token in (open_token, used_token, reset_token):
        await db_session.refresh(token)
    assert open_token.superseded_at is not None
    assert used_token.superseded_at is None and reset_token.superseded_at is None


@pytest.mark.asyncio
async def test_user_ids_with_status_is_division_scoped_and_skips_inactive_users(db_session):
    overseas_admin = await _make_user(db_session)
    it_admin = await _make_user(db_session, role="it_admin", division="it")
    super_admin = await _make_user(db_session, role="super_admin", division="global")
    overseas_expired = await _make_user(db_session, role="counselor", division="overseas")
    it_expired = await _make_user(db_session, role="trainer", division="it")
    inactive_expired = await _make_user(db_session, role="counselor", division="overseas", active=False)
    for u in (overseas_expired, it_expired, inactive_expired):
        await _seed_token(db_session, u, expires_in=timedelta(hours=-1))

    overseas_ids = set(await provisioning.user_ids_with_status(db_session, overseas_admin, "link_expired"))
    it_ids = set(await provisioning.user_ids_with_status(db_session, it_admin, "link_expired"))
    all_ids = set(await provisioning.user_ids_with_status(db_session, super_admin, "link_expired"))
    assert overseas_expired.id in overseas_ids and it_expired.id not in overseas_ids
    assert it_expired.id in it_ids and overseas_expired.id not in it_ids
    assert inactive_expired.id not in overseas_ids and inactive_expired.id not in all_ids
    assert {overseas_expired.id, it_expired.id} <= all_ids


@pytest.mark.asyncio
async def test_resend_cooldown_only_applies_after_a_first_re_send_and_lapses(db_session):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor")
    await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    assert await provisioning.resend_wait_seconds(db_session, target.id) == 0  # first Re-send is always allowed

    await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()
    wait = await provisioning.resend_wait_seconds(db_session, target.id)
    assert 0 < wait <= provisioning.RESEND_COOLDOWN_SECONDS

    for token in (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == target.id))).all():
        token.created_at = datetime.now(UTC) - timedelta(minutes=2)
    await db_session.commit()
    assert await provisioning.resend_wait_seconds(db_session, target.id) == 0


async def _delivery_setup(db_session, monkeypatch, *, smtp, webhook):
    admin = await _make_user(db_session)
    target = await _make_user(db_session, role="counselor")
    issued = await provisioning.issue_welcome_token(db_session, user=target, issued_by=admin)
    await db_session.commit()

    async def fake_smtp(**kwargs):
        return smtp() if callable(smtp) else smtp

    async def fake_webhook(channel, payload):
        return webhook

    monkeypatch.setattr(provisioning, "send_welcome_email", fake_smtp)
    monkeypatch.setattr(provisioning, "send_notification", fake_webhook)
    return admin, target, issued


@pytest.mark.asyncio
async def test_deliver_reports_status_and_only_returns_the_dev_token_in_dev_or_test(db_session, monkeypatch):
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("sent", None), webhook=("not_configured", None))

    monkeypatch.setattr(settings, "environment", "test")
    dev = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert dev["email_status"] == "sent" and dev["development_welcome_token"] == issued.raw and dev["expires_at"] == issued.expires_at

    monkeypatch.setattr(settings, "environment", "production")
    prod = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert "development_welcome_token" not in prod

    audit = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))).all()
    assert len(audit) == 2 and all(issued.raw not in json.dumps(a.metadata_json) for a in audit)
    assert audit[0].metadata_json["smtp_status"] == "sent"


@pytest.mark.asyncio
async def test_deliver_redacts_urls_from_the_errors_it_stores(db_session, monkeypatch):
    leaky = "Client error '404 Not Found' for url 'https://hooks.example.local/secret-path?key=abc123'"
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", "connect to https://smtp.example.local:587 failed"), webhook=("failed", leaky))
    await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    stored = json.dumps(audit.metadata_json)
    assert "hooks.example.local" not in stored and "abc123" not in stored and "smtp.example.local" not in stored
    assert "[redacted-url]" in stored


@pytest.mark.asyncio
async def test_deliver_treats_a_raising_sender_as_a_failed_send_not_an_exception(db_session, monkeypatch):
    def boom():
        raise ValueError("Header values may not contain linefeed or carriage return characters")

    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=boom, webhook=("not_configured", None))
    result = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert result["email_status"] == "failed"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(target.id), AuditLog.action == "user.welcome_link_delivery"))
    assert audit.metadata_json["smtp_status"] == "failed" and "linefeed" in audit.metadata_json["smtp_error"]


@pytest.mark.asyncio
async def test_deliver_never_raises_when_the_audit_write_fails(db_session, monkeypatch):
    admin, target, issued = await _delivery_setup(db_session, monkeypatch, smtp=("failed", "boom"), webhook=("not_configured", None))

    async def broken_commit():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session, "commit", broken_commit)
    result = await provisioning.deliver_welcome_link(db_session, user=target, issued=issued, issued_by=admin)
    assert result["email_status"] == "failed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -k "unusable or issue or statuses or revoke or user_ids or cooldown or deliver" -v`
Expected: FAIL — `ImportError: cannot import name 'provisioning' from 'app.services'`.

- [ ] **Step 3: Create `apps/api/app/services/provisioning.py`**

```python
"""ENH-003 / DEC-SCOPE-019 -- first-time provisioning of admin-created accounts.

An admin never knows or chooses a credential: the account is created with an unusable password
hash and the user receives a single-use, hashed-at-rest, 72-hour set-password link
(`PasswordResetToken`, `purpose="welcome"`). Functions only -- no new abstraction layer.

Transaction shape (spec §6): the caller creates the user and calls `issue_welcome_token` in ONE
transaction and commits; `deliver_welcome_link` runs AFTER that commit, so a failed or
unconfigured send can never roll back the account, and never holds a DB transaction open across
the (up to 10 s) SMTP call. `deliver_welcome_link` never raises.
"""

import asyncio
import hashlib
import logging
import math
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.models import AuditLog, PasswordResetToken, User
from app.services.integrations import send_notification
from app.services.mailer import send_welcome_email

logger = logging.getLogger("app.provisioning")

WELCOME_EXPIRY_HOURS = 72
DEV_TOKEN_ENVIRONMENTS = ("development", "test")
RESEND_COOLDOWN_SECONDS = 60

_URL = re.compile(r"https?://\S+")


class IssuedWelcome(NamedTuple):
    raw: str
    expires_at: datetime
    token_id: UUID


class Provisioning(NamedTuple):
    status: str  # "pending_setup" | "link_expired"; a user absent from the result is "active"
    expires_at: datetime


def unusable_password_hash() -> str:
    """Hash of a random secret that is discarded immediately -- never a constant."""
    return hash_password(secrets.token_urlsafe(48))


def _set_password_url(user: User, raw: str) -> str:
    # Built from configuration, never from the request's Host header (no host-header poisoning).
    segment = "overseas" if user.division == "overseas" else "it"  # super_admin logs in via /it
    return f"{settings.frontend_url}/{segment}/reset-password?token={raw}"


def _redact(text: str | None) -> str | None:
    """Stored errors can echo a webhook/SMTP URL (which may embed a secret); keep none of it."""
    return None if text is None else _URL.sub("[redacted-url]", text)[:500]


def _outcome(result) -> tuple[str, str | None]:
    if isinstance(result, BaseException):  # a sender that raised is a failed send, not a 500
        return "failed", _redact(str(result))
    status, error = result
    return status, _redact(error)


async def revoke_welcome_tokens(db: AsyncSession, user_id: UUID) -> None:
    """No commit. Supersedes the user's open welcome tokens. Used by Re-send (old link replaced) and
    when an admin changes `active`, so a link mailed to a wrong recipient cannot come back to life on
    reactivation -- the account then reads `link_expired` and needs an explicit Re-send."""
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.purpose == "welcome", PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None))
        .values(superseded_at=datetime.now(UTC))
    )


async def issue_welcome_token(db: AsyncSession, *, user: User, issued_by: User) -> IssuedWelcome:
    """No commit. Revokes open welcome tokens, inserts a new one, audits the issue (token id + expiry
    only -- never the raw token)."""
    await revoke_welcome_tokens(db, user.id)
    raw = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + timedelta(hours=WELCOME_EXPIRY_HOURS)
    token = PasswordResetToken(user_id=user.id, token_hash=hashlib.sha256(raw.encode()).hexdigest(), purpose="welcome", expires_at=expires_at)
    db.add(token)
    await db.flush()
    db.add(AuditLog(user_id=issued_by.id, action="user.welcome_link_issue", entity_type="user", entity_id=str(user.id), metadata_json={"token_id": str(token.id), "expires_at": expires_at.isoformat()}))
    return IssuedWelcome(raw, expires_at, token.id)


async def deliver_welcome_link(db: AsyncSession, *, user: User, issued: IssuedWelcome, issued_by: User) -> dict:
    """Call AFTER the caller's commit. SMTP and the generic webhook (parity with the invite flow)
    run concurrently; a sender that raises counts as a failed send. The outcome is audited
    (statuses and URL-redacted errors, never the raw token). Never raises."""
    webhook, smtp = await asyncio.gather(
        send_notification("email", {"to": user.email, "template": "welcome_set_password", "reset_token": issued.raw, "expires_hours": WELCOME_EXPIRY_HOURS}),
        send_welcome_email(
            to_email=user.email, recipient_name=user.full_name, role=user.role,
            set_password_url=_set_password_url(user, issued.raw), expires_at=issued.expires_at, invited_by_name=issued_by.full_name,
        ),
        return_exceptions=True,
    )
    webhook_status, webhook_error = _outcome(webhook)
    smtp_status, smtp_error = _outcome(smtp)
    try:
        db.add(AuditLog(
            user_id=issued_by.id, action="user.welcome_link_delivery", entity_type="user", entity_id=str(user.id),
            metadata_json={"token_id": str(issued.token_id), "smtp_status": smtp_status, "smtp_error": smtp_error, "webhook_status": webhook_status, "webhook_error": webhook_error},
        ))
        await db.commit()
    except Exception:
        logger.exception("could not record the welcome-link delivery audit row")
        await db.rollback()
    result = {"email_status": smtp_status, "expires_at": issued.expires_at}
    if settings.environment in DEV_TOKEN_ENVIRONMENTS:
        result["development_welcome_token"] = issued.raw
    return result


async def provisioning_statuses(db: AsyncSession, user_ids) -> dict[UUID, Provisioning]:
    """Derived from each user's LATEST welcome token (superseded ones included, so a revoked link
    with nothing newer reads `link_expired` and stays Re-sendable). A user who has since set a
    password -- the latest welcome token was used, or any token was used at/after its creation
    (e.g. forgot-password) -- is active, i.e. absent. Two queries; no N+1."""
    ids = list(user_ids)
    if not ids:
        return {}
    tokens = (await db.scalars(
        select(PasswordResetToken).where(PasswordResetToken.user_id.in_(ids), PasswordResetToken.purpose == "welcome")
    )).all()
    latest: dict[UUID, PasswordResetToken] = {}
    for token in tokens:
        current = latest.get(token.user_id)
        if current is None or token.created_at > current.created_at:
            latest[token.user_id] = token
    unused = [user_id for user_id, token in latest.items() if token.used_at is None]
    if not unused:
        return {}
    rows = (await db.execute(
        select(PasswordResetToken.user_id, func.max(PasswordResetToken.used_at))
        .where(PasswordResetToken.user_id.in_(unused), PasswordResetToken.used_at.is_not(None))
        .group_by(PasswordResetToken.user_id)
    )).all()
    last_used = {row[0]: row[1] for row in rows}
    now = datetime.now(UTC)
    result: dict[UUID, Provisioning] = {}
    for user_id in unused:
        token = latest[user_id]
        used = last_used.get(user_id)
        if used is not None and used >= token.created_at:
            continue
        expired = token.superseded_at is not None or token.expires_at < now
        result[user_id] = Provisioning("link_expired" if expired else "pending_setup", token.expires_at)
    return result


async def user_ids_with_status(db: AsyncSession, actor: User, status: str) -> list[UUID]:
    """Active users in the actor's scope (all divisions for super_admin) whose derived
    provisioning status equals `status` -- the exact set, not limited by any list cap."""
    stmt = select(User.id).where(
        User.active.is_(True),
        User.id.in_(select(PasswordResetToken.user_id).where(PasswordResetToken.purpose == "welcome", PasswordResetToken.used_at.is_(None))),
    )
    if actor.role != "super_admin":
        stmt = stmt.where(User.division == actor.division)
    candidates = list((await db.scalars(stmt)).all())
    statuses = await provisioning_statuses(db, candidates)
    return [user_id for user_id in candidates if user_id in statuses and statuses[user_id].status == status]


async def resend_wait_seconds(db: AsyncSession, user_id: UUID) -> int:
    """Per-account Re-send throttle (security review 2026-09-19): the first Re-send after creation is
    always allowed; any later one within RESEND_COOLDOWN_SECONDS of the newest welcome link is not.
    0 means allowed. Capped so DB/app clock skew can never produce an absurd wait."""
    count, newest = (await db.execute(
        select(func.count(PasswordResetToken.id), func.max(PasswordResetToken.created_at))
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.purpose == "welcome")
    )).one()
    if count < 2 or newest is None:
        return 0
    remaining = RESEND_COOLDOWN_SECONDS - (datetime.now(UTC) - newest).total_seconds()
    return min(RESEND_COOLDOWN_SECONDS, max(0, math.ceil(remaining)))
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -v`
Expected: PASS (all tasks 1–3 tests).

- [ ] **Step 5: Commit** (with approval): `git add apps/api/app/services/provisioning.py apps/api/tests/test_enh_003_first_time_provisioning.py && git commit -m "feat(enh-003): add welcome-link provisioning service" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 4: `reset_password` — atomic single-use consumption, welcome handling, hardening

**Files:**
- Modify: `apps/api/app/api/auth.py` (`reset_password`, lines ~178-195; import line 7)
- Test: `apps/api/tests/test_enh_003_first_time_provisioning.py` (append)

**Interfaces:**
- Consumes: `PasswordResetToken.purpose/superseded_at` (Task 1). Success response and the `400` message unchanged.
- Produces: consuming a `welcome` token sets `users.email_verified = True` (audit `auth.welcome_password_set`); reset tokens keep audit `auth.password_reset`. New failures: `422` above 128 characters; a welcome link for an **inactive** account gets the generic `400` and is **not** consumed (security review S2, S8).

- [ ] **Step 1: Append the failing tests**

```python
# --- Task 4: reset_password -----------------------------------------------------------

RESET_URL = "/api/v1/auth/reset-password"
INVALID = "Reset token is invalid or expired"


async def _pending_user(db_session, *, active=True, **token_kwargs):
    user = await _make_user(db_session, role="counselor", email_verified=False, active=active, password=uuid.uuid4().hex + "Zz1!")
    raw, token = await _seed_token(db_session, user, **token_kwargs)
    return user, raw, token


@pytest.mark.asyncio
async def test_a_welcome_link_sets_the_password_verifies_the_email_and_allows_login(client, db_session):
    user, raw, token = await _pending_user(db_session)
    response = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == 200 and response.json() == {"ok": True}
    await db_session.refresh(user)
    await db_session.refresh(token)
    assert user.email_verified is True and token.used_at is not None
    assert (await _login(client, user.email, NEW_PASSWORD)).status_code == 200
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "auth.welcome_password_set")) is not None


@pytest.mark.asyncio
async def test_a_used_link_is_rejected_with_the_generic_400(client, db_session):
    user, raw, _ = await _pending_user(db_session)
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200
    second = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
    assert second.status_code == 400 and second.json()["detail"] == INVALID


@pytest.mark.asyncio
async def test_two_simultaneous_submissions_yield_exactly_one_success(client, db_session):
    _, raw, _ = await _pending_user(db_session)
    results = await asyncio.gather(
        client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD}),
        client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD}),
    )
    assert sorted(r.status_code for r in results) == [200, 400]


@pytest.mark.asyncio
async def test_expired_superseded_and_unknown_links_all_return_the_same_400(client, db_session):
    _, expired, _ = await _pending_user(db_session, expires_in=timedelta(hours=-1))
    _, superseded, _ = await _pending_user(db_session, superseded=True)
    for raw in (expired, superseded, "not-a-real-token"):
        response = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
        assert response.status_code == 400 and response.json()["detail"] == INVALID


@pytest.mark.asyncio
async def test_a_too_short_password_is_422_and_does_not_burn_the_link(client, db_session):
    _, raw, _ = await _pending_user(db_session)
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": "short"})).status_code == 422
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_password_length_is_capped_at_128_and_an_oversized_one_does_not_burn_the_link(client, db_session):
    _, raw, _ = await _pending_user(db_session)
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": "x" * 129})).status_code == 422
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": "A1" + "x" * 126})).status_code == 200  # exactly 128


@pytest.mark.asyncio
async def test_a_welcome_link_is_refused_for_a_deactivated_account_and_is_not_consumed(client, db_session):
    user, raw, token = await _pending_user(db_session, active=False)
    response = await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})
    assert response.status_code == 400 and response.json()["detail"] == INVALID
    await db_session.refresh(token)
    await db_session.refresh(user)
    assert token.used_at is None  # the failed attempt rolled back; the link was not burned
    assert not verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.asyncio
async def test_a_forgot_password_token_keeps_its_behavior_and_does_not_verify_the_email(client, db_session):
    user, raw, _ = await _pending_user(db_session, purpose="reset", expires_in=timedelta(minutes=30))
    assert (await client.post(RESET_URL, json={"token": raw, "new_password": NEW_PASSWORD})).status_code == 200
    await db_session.refresh(user)
    assert user.email_verified is False
    assert await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "auth.password_reset")) is not None
```

- [ ] **Step 2: Run to verify which fail**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -k "welcome_link_sets or used_link or simultaneous or same_400 or too_short or capped_at_128 or deactivated_account or forgot_password_token" -v`
Expected: FAIL for `welcome_link_sets` (email not verified, wrong audit), `superseded` (still accepted), `capped_at_128` (129 accepted), `deactivated_account` (accepted) and likely `simultaneous` (both 200). The reset-purpose and too-short tests pass already.

- [ ] **Step 3: Implement**

In `apps/api/app/api/auth.py` change `from sqlalchemy import select` to `from sqlalchemy import select, update`, then replace the whole `reset_password` function with:

```python
@router.post("/reset-password")
async def reset_password(payload: dict, db: AsyncSession = Depends(get_db)):
    raw = str(payload.get("token", ""))
    new_password = str(payload.get("new_password", ""))
    if len(new_password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    if len(new_password) > 128:
        # Same cap as the registration schemas; bcrypt silently ignores bytes past 72 anyway.
        raise HTTPException(422, "Password must be at most 128 characters")
    digest = hashlib.sha256(raw.encode()).hexdigest()
    now = datetime.now(UTC)
    # ENH-003: consume atomically so "single-use" holds under concurrency -- a read-then-write
    # let two simultaneous submissions both pass `used_at IS NULL`. Every failure (unknown, used,
    # expired, superseded) is deliberately the same 400 so a caller cannot tell them apart. bcrypt
    # only runs after a valid token, so invalid requests cannot burn CPU.
    consumed = (await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.token_hash == digest, PasswordResetToken.used_at.is_(None), PasswordResetToken.superseded_at.is_(None), PasswordResetToken.expires_at > now)
        .values(used_at=now)
        .returning(PasswordResetToken.user_id, PasswordResetToken.purpose)
    )).first()
    if not consumed:
        raise HTTPException(400, "Reset token is invalid or expired")
    user = await db.get(User, consumed.user_id)
    if not user:
        # Raising without a commit rolls the token consumption back with the session.
        raise HTTPException(400, "User unavailable")
    welcome = consumed.purpose == "welcome"
    if welcome and not user.active:
        # A welcome link is only good for an active account (security review S2): the rollback keeps
        # the token unconsumed, and deactivation/reactivation revokes it (Task 6).
        raise HTTPException(400, "Reset token is invalid or expired")
    user.password_hash = hash_password(new_password)
    if welcome:
        # The link was delivered to this address, so using it proves control of it (DEC-SCOPE-019 #5).
        user.email_verified = True
    db.add(AuditLog(user_id=user.id, action="auth.welcome_password_set" if welcome else "auth.password_reset", entity_type="user", entity_id=str(user.id), metadata_json={}))
    await db.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run to verify it passes, plus the existing auth suites**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py tests/test_role_assignments.py tests/test_not_001_email_notifications.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit** (with approval): `git add apps/api/app/api/auth.py apps/api/tests/test_enh_003_first_time_provisioning.py && git commit -m "feat(enh-003): consume reset tokens atomically, verify email on welcome links, refuse inactive accounts" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 5: The three create routes + migrate the two existing pytest helpers

**Files:**
- Modify: `apps/api/app/api/admin.py` (`create_user` ~234-269, `create_school` ~901-940, `create_school_staff` ~1068-1106, imports line 14/16)
- Modify: `apps/api/tests/test_sch_003_school_onboarding.py` (`_create_school`, lines 35-52)
- Modify: `apps/api/tests/test_enh_001_academic_year.py` (`_create_school_with_coordinator`, lines 490-501)
- Test: `apps/api/tests/test_enh_003_first_time_provisioning.py` (append)

**Interfaces:**
- Consumes: Task 3 functions. Produces: each route's success response = existing fields + `email_status`, `expires_at`, (dev/test) `development_welcome_token`; `_reject_supplied_password(payload, *fields)` helper in `admin.py`.

- [ ] **Step 1: Append the failing tests**

```python
# --- Task 5: create routes ------------------------------------------------------------

async def _admin_client(client, db_session, *, role="overseas_admin", division="overseas"):
    admin = await _make_user(db_session, role=role, division=division)
    assert (await _login(client, admin.email, division="it" if division in ("it", "global") else division)).status_code == 200
    return admin


def _no_password_keys(body: dict) -> bool:
    return not any("password" in key.lower() for key in body)


@pytest.mark.asyncio
@pytest.mark.parametrize("path,body,field", [
    ("/api/v1/admin/users", {"role": "counselor", "division": "overseas", "full_name": "X"}, "password"),
    ("/api/v1/overseas-admin/school-staff", {"role": "academic_team", "full_name": "X"}, "password"),
    ("/api/v1/overseas-admin/schools", {"name": "S", "coordinator_full_name": "X"}, "coordinator_password"),
])
async def test_a_supplied_password_is_rejected_with_422_and_creates_nothing(client, db_session, path, body, field):
    await _admin_client(client, db_session)
    email = _email()
    payload = {**body, ("coordinator_email" if field == "coordinator_password" else "email"): email, field: "Should-Be-Ignored-1!"}
    response = await client.post(path, json=payload)
    assert response.status_code == 422 and "password" in response.json()["detail"].lower()
    assert await db_session.scalar(select(User).where(User.email == email)) is None


@pytest.mark.asyncio
async def test_create_user_issues_a_welcome_link_and_never_a_password(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    monkeypatch.setattr(settings, "smtp_host", None)
    admin = await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "New Counselor"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert _no_password_keys(body) and "ChangeMe" not in response.text
    assert body["email_status"] == "not_configured" and body["email"] == email
    assert timedelta(hours=71, minutes=59) < datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC) <= timedelta(hours=72)

    user = await db_session.scalar(select(User).where(User.email == email))
    assert not verify_password("ChangeMe@12345", user.password_hash)
    assert (await _login(client, email, "ChangeMe@12345")).status_code == 401
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).all()
    assert len(tokens) == 1 and tokens[0].purpose == "welcome"
    assert tokens[0].token_hash == _sha(body["development_welcome_token"])

    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.entity_id == str(user.id)))).all()
    assert {"user.create", "user.welcome_link_issue", "user.welcome_link_delivery"} <= {a.action for a in audits}
    assert all(body["development_welcome_token"] not in json.dumps(a.metadata_json) for a in audits)
    assert any(a.user_id == admin.id for a in audits)


@pytest.mark.asyncio
async def test_the_created_user_can_activate_from_the_link_and_log_in(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    email = _email()
    body = (await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "New Counselor"})).json()
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
    assert (await _login(client, email, NEW_PASSWORD)).status_code == 200
    user = await db_session.scalar(select(User).where(User.email == email))
    await db_session.refresh(user)
    assert user.email_verified is True


@pytest.mark.asyncio
async def test_the_dev_token_is_never_returned_in_production(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    await _admin_client(client, db_session)
    body = (await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": _email(), "full_name": "P"})).json()
    assert "development_welcome_token" not in body and "email_status" in body


@pytest.mark.asyncio
async def test_school_staff_route_provisions_with_a_welcome_link(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/overseas-admin/school-staff", json={"role": "academic_team", "full_name": "Staff", "email": email, "school_ids": []})
    assert response.status_code == 201, response.text
    body = response.json()
    assert _no_password_keys(body) and body["role"] == "academic_team" and body["school_ids"] == []
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
    assert (await _login(client, email, NEW_PASSWORD)).status_code == 200


@pytest.mark.asyncio
async def test_create_school_seeds_a_coordinator_with_a_welcome_link(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/overseas-admin/schools", json={"name": f"S {uuid.uuid4().hex[:6]}", "coordinator_full_name": "Coord", "coordinator_email": email})
    assert response.status_code == 201, response.text
    body = response.json()
    assert _no_password_keys(body) and body["coordinator_email"] == email
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
    assert (await _login(client, email, NEW_PASSWORD)).status_code == 200
    assert (await client.get("/api/v1/school/team")).status_code == 200


@pytest.mark.asyncio
async def test_a_failed_send_never_blocks_creation_and_is_audited(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")

    async def failing_smtp(**kwargs):
        return "failed", "smtp down"

    monkeypatch.setattr(provisioning, "send_welcome_email", failing_smtp)
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "F"})
    assert response.status_code == 201 and response.json()["email_status"] == "failed"
    user = await db_session.scalar(select(User).where(User.email == email))
    delivery = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == str(user.id), AuditLog.action == "user.welcome_link_delivery"))
    assert delivery.metadata_json["smtp_status"] == "failed" and delivery.metadata_json["smtp_error"] == "smtp down"
    assert await db_session.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)) is not None


@pytest.mark.asyncio
async def test_the_composed_email_goes_to_the_new_user_with_the_link_and_no_password(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")
    _configure_smtp(monkeypatch)
    sent = []
    monkeypatch.setattr(mailer, "_send_sync", lambda msg: sent.append(msg))
    await _admin_client(client, db_session)
    email = _email()
    body = (await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "New"})).json()
    assert body["email_status"] == "sent" and len(sent) == 1 and sent[0]["To"] == email
    text = sent[0].get_body(preferencelist=("plain",)).get_content()
    assert f"/overseas/reset-password?token={body['development_welcome_token']}" in text
    assert "72 hours" in text and "ChangeMe" not in text


@pytest.mark.asyncio
async def test_a_duplicate_email_is_409_including_under_a_race(client, db_session):
    await _admin_client(client, db_session)
    email = _email()
    payload = {"role": "counselor", "division": "overseas", "email": email, "full_name": "Dup"}
    results = await asyncio.gather(client.post("/api/v1/admin/users", json=payload), client.post("/api/v1/admin/users", json=payload))
    assert sorted(r.status_code for r in results) == [201, 409]
    assert (await client.post("/api/v1/admin/users", json=payload)).status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/admin/users", "/api/v1/overseas-admin/school-staff", "/api/v1/overseas-admin/schools"])
@pytest.mark.parametrize("bad_email", ["not-an-email", "a b@example.local", "a@b", "victim@example.local\r\nBcc: attacker@example.local", "x" * 250 + "@example.local", ""])
async def test_a_malformed_email_is_422_and_creates_nothing(client, db_session, path, bad_email):
    await _admin_client(client, db_session)
    payloads = {
        "/api/v1/admin/users": {"role": "counselor", "division": "overseas", "full_name": "X", "email": bad_email},
        "/api/v1/overseas-admin/school-staff": {"role": "academic_team", "full_name": "X", "email": bad_email, "school_ids": []},
        "/api/v1/overseas-admin/schools": {"name": "S", "coordinator_full_name": "X", "coordinator_email": bad_email},
    }
    before = await db_session.scalar(sa.select(sa.func.count()).select_from(User))
    response = await client.post(path, json=payloads[path])
    assert response.status_code == 422, response.text
    assert await db_session.scalar(sa.select(sa.func.count()).select_from(User)) == before


@pytest.mark.asyncio
async def test_a_sender_that_raises_never_turns_a_committed_creation_into_a_500(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "environment", "test")

    async def exploding_smtp(**kwargs):
        raise ValueError("bad header")

    monkeypatch.setattr(provisioning, "send_welcome_email", exploding_smtp)
    await _admin_client(client, db_session)
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": "counselor", "division": "overseas", "email": email, "full_name": "Boom"})
    assert response.status_code == 201 and response.json()["email_status"] == "failed"
    assert await db_session.scalar(select(User).where(User.email == email)) is not None


def test_no_default_password_constant_remains_in_the_api_source():
    root = Path(__file__).resolve().parents[1] / "app"
    offenders = [str(p.relative_to(root)) for p in root.rglob("*.py") if "ChangeMe@12345" in p.read_text(encoding="utf-8")]
    assert offenders == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -k "supplied_password or welcome_link or school_staff_route or create_school_seeds or failed_send or composed_email or duplicate_email or dev_token_is_never or default_password_constant" -v`
Expected: FAIL (routes still accept passwords / no `email_status`).

- [ ] **Step 3: Implement in `apps/api/app/api/admin.py`**

3a. Under the existing `from app.services.storage import storage` line add:

```python
from app.services.provisioning import deliver_welcome_link, issue_welcome_token, unusable_password_hash
```

3b. Directly under `ensure_admin` (after its `return user`) add:

```python
def _reject_supplied_password(payload: dict, *fields: str) -> None:
    """ENH-003 / DEC-SCOPE-019: an admin never supplies or knows a credential for an account they
    provision -- the user sets their own via the emailed link."""
    if any(field in payload for field in fields):
        raise HTTPException(422, "A password cannot be supplied; the user sets their own via the emailed set-password link")
```

3b2. Add `import re` to `admin.py`'s imports, and directly under `_reject_supplied_password` add (security review S3: the email is now the only delivery channel for a credential-setting link, and these routes previously accepted any string; the pattern is the one the registration schemas already use, which also rejects whitespace, so a CR/LF header-injection attempt cannot pass):

```python
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def _valid_email(raw) -> str:
    email = str(raw or "").lower().strip()
    if len(email) > 255 or not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(422, "A valid email address is required")
    return email
```

3c. `create_user`: delete the line `    from app.core.security import hash_password` (leave `from app.models import AuditLog`). After the existing `403` division check, add `    _reject_supplied_password(payload, "password")`, and replace `email = str(payload["email"]).lower().strip()` with `email = _valid_email(payload.get("email"))` (a missing or malformed email is now a `422`, not a `500`). Replace from `    item = User(` through the `return` with:

```python
    item = User(
        email=email,
        password_hash=unusable_password_hash(),
        full_name=payload["full_name"],
        role=role,
        division=division,
        phone=payload.get("phone"),
        active=payload.get("active", True),
        email_verified=payload.get("email_verified", False),
        profile=payload.get("profile", {}),
    )
    db.add(item)
    try:
        await db.flush()
    except IntegrityError:
        # Two simultaneous creates for one email: the unique constraint picks the winner.
        await db.rollback()
        raise HTTPException(409, "Email already exists")
    issued = await issue_welcome_token(db, user=item, issued_by=user)
    db.add(AuditLog(user_id=user.id, action="user.create", entity_type="user", entity_id=str(item.id), metadata_json={"role": role, "division": division}))
    await db.commit()
    delivery = await deliver_welcome_link(db, user=item, issued=issued, issued_by=user)
    return {"id": item.id, "email": item.email, "role": item.role, "division": item.division, **delivery}
```

3d. `create_school`: delete `    from app.core.security import hash_password`; after the role check (`raise HTTPException(403, "Overseas Admin role required")`) add `    _reject_supplied_password(payload, "coordinator_password")`; after the existing required-fields check (`School name and Coordinator name/email are required`) add `    email = _valid_email(email)`. Replace the coordinator construction `password_hash=hash_password(payload.get("coordinator_password") or "ChangeMe@12345"),` with `password_hash=unusable_password_hash(),`. Replace

```python
    db.add(coordinator)
    await db.flush()
```

with

```python
    db.add(coordinator)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Email already exists")
    issued = await issue_welcome_token(db, user=coordinator, issued_by=user)
```

and replace the final

```python
    await db.commit()
    return {"id": school.id, "name": school.name, "coordinator_id": coordinator.id, "coordinator_email": coordinator.email}
```

with

```python
    await db.commit()
    delivery = await deliver_welcome_link(db, user=coordinator, issued=issued, issued_by=user)
    return {"id": school.id, "name": school.name, "coordinator_id": coordinator.id, "coordinator_email": coordinator.email, **delivery}
```

3e. `create_school_staff`: delete `    from app.core.security import hash_password` (keep `from app.models import SchoolStaffAssignment`); after the role check add `    _reject_supplied_password(payload, "password")`; after the existing `if not email or not full_name:` check add `    email = _valid_email(email)`. Replace `password_hash=hash_password(payload.get("password") or "ChangeMe@12345"),` with `password_hash=unusable_password_hash(),`. Replace

```python
    db.add(staff)
    await db.flush()
```

with

```python
    db.add(staff)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Email already exists")
    issued = await issue_welcome_token(db, user=staff, issued_by=user)
```

and the final commit/return with

```python
    await db.commit()
    delivery = await deliver_welcome_link(db, user=staff, issued=issued, issued_by=user)
    return {"id": staff.id, "email": staff.email, "role": staff.role, "school_ids": [str(s.id) for s in schools], **delivery}
```

- [ ] **Step 4: Migrate the two existing pytest helpers (same task, so the suite never goes red)**

In `test_sch_003_school_onboarding.py` replace in `_create_school`:

```python
            "coordinator_email": f"sch003-coord-{suffix}@example.local",
            "coordinator_password": PASSWORD,
        },
    )
    assert response.status_code == 201
    data = response.json()
    return {"admin": admin, **data}
```

with

```python
            "coordinator_email": f"sch003-coord-{suffix}@example.local",
        },
    )
    assert response.status_code == 201
    data = response.json()
    # ENH-003: the Coordinator sets their own password from the welcome link (dev/test token).
    activation = await client.post("/api/v1/auth/reset-password", json={"token": data["development_welcome_token"], "new_password": PASSWORD})
    assert activation.status_code == 200
    return {"admin": admin, **data}
```

In `test_enh_001_academic_year.py` replace in `_create_school_with_coordinator`:

```python
        json={"name": f"ENH-001 School {suffix}", "coordinator_full_name": "Coordinator", "coordinator_email": f"enh001-coord-{suffix}@example.local", "coordinator_password": ADMIN_PASSWORD},
    )
    assert response.status_code == 201
    data = response.json()
    await client.post("/api/v1/auth/login",
```

with

```python
        json={"name": f"ENH-001 School {suffix}", "coordinator_full_name": "Coordinator", "coordinator_email": f"enh001-coord-{suffix}@example.local"},
    )
    assert response.status_code == 201
    data = response.json()
    await client.post("/api/v1/auth/reset-password", json={"token": data["development_welcome_token"], "new_password": ADMIN_PASSWORD})
    await client.post("/api/v1/auth/login",
```

(Keep the remainder of that `login` call unchanged.)

- [ ] **Step 5: Find any other caller depending on the old behavior**

```bash
grep -rn "coordinator_password\|ChangeMe" apps/api/tests --include=*.py | grep -v "test_enh_003"
```

Expected: no output. If a file appears, migrate it the same way before continuing.

- [ ] **Step 6: Run the new tests and every suite that provisions schools/staff**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py tests/test_sch_003_school_onboarding.py tests/test_enh_001_academic_year.py tests/test_sch_school_staff_provisioning.py tests/test_sch_002_bulk_roster_upload.py tests/test_sch_004_career_guidance.py tests/test_sch_005_psychometric_assessment.py tests/test_sch_006_academic_results.py tests/test_sch_009_test_prep_language.py tests/test_sch_010_overseas_bridge.py tests/test_sch_011_entitlements.py tests/test_sch_roster_parent_invite.py tests/test_adm_001_admin_crud.py tests/test_adm_004_directory.py -q`
Expected: PASS, no fewer passes than the Task 0 baseline for the files it covered.

- [ ] **Step 7: Commit** (with approval): `git add apps/api/app/api/admin.py apps/api/tests && git commit -m "feat(enh-003): provision admin-created accounts with an emailed set-password link" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 6: Re-send endpoint (with cooldown), status filter, dashboard count, revoke-on-`active`-change

**Files:**
- Modify: `apps/api/app/api/admin.py` (`dashboard` ~27-43, `users` ~46-59, `update_user` ~272-293, new route after `update_user`, import line)
- Test: `apps/api/tests/test_enh_003_first_time_provisioning.py` (append)

**Interfaces:**
- Consumes: `provisioning_statuses`, `user_ids_with_status`, `issue_welcome_token`, `deliver_welcome_link`, `revoke_welcome_tokens`, `resend_wait_seconds`.
- Produces: `POST /admin/users/{user_id}/welcome-links` → `201 {id, email_status, expires_at[, development_welcome_token]}`; `429` with `Retry-After` inside the 60-second cooldown; `GET /admin/users` rows gain `provisioning_status` plus optional `?provisioning_status=pending_setup|link_expired`; `GET /admin/dashboard` gains `expired_welcome_links: int`; `PATCH /admin/users/{id}` revokes the account's open welcome links whenever `active` actually changes (security review S2/S4).

- [ ] **Step 1: Append the failing tests**

```python
# --- Task 6: Re-send, status, filter, dashboard, revoke -------------------------------

async def _provision_via_api(client, monkeypatch, *, role="counselor", division="overseas"):
    monkeypatch.setattr(settings, "environment", "test")
    email = _email()
    response = await client.post("/api/v1/admin/users", json={"role": role, "division": division, "email": email, "full_name": "Pending"})
    assert response.status_code == 201, response.text
    return response.json()


async def _age_welcome_tokens(db_session, user_id, minutes=2):
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(str(user_id)), PasswordResetToken.purpose == "welcome"))).all()
    for token in tokens:
        token.created_at = datetime.now(UTC) - timedelta(minutes=minutes)
    await db_session.commit()


@pytest.mark.asyncio
async def test_resend_supersedes_the_old_link_and_issues_a_new_72_hour_one(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    old = created["development_welcome_token"]
    response = await client.post(f"/api/v1/admin/users/{created['id']}/welcome-links")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["id"] == created["id"] and body["email_status"] in {"sent", "failed", "not_configured"}
    assert timedelta(hours=71, minutes=59) < datetime.fromisoformat(body["expires_at"]) - datetime.now(UTC) <= timedelta(hours=72)

    assert (await client.post(RESET_URL, json={"token": old, "new_password": NEW_PASSWORD})).status_code == 400
    open_tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(created["id"]), PasswordResetToken.purpose == "welcome", PasswordResetToken.superseded_at.is_(None)))).all()
    assert len(open_tokens) == 1
    assert (await client.post(RESET_URL, json={"token": body["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_a_second_resend_inside_the_cooldown_is_429_with_retry_after_and_lapses(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    url = f"/api/v1/admin/users/{created['id']}/welcome-links"
    assert (await client.post(url)).status_code == 201  # the first Re-send after creation is allowed

    blocked = await client.post(url)
    assert blocked.status_code == 429
    assert 0 < int(blocked.headers["retry-after"]) <= 60 and "wait" in blocked.json()["detail"].lower()
    tokens = (await db_session.scalars(select(PasswordResetToken).where(PasswordResetToken.user_id == uuid.UUID(created["id"]), PasswordResetToken.purpose == "welcome"))).all()
    assert len(tokens) == 2  # the blocked call issued nothing

    await _age_welcome_tokens(db_session, created["id"])
    assert (await client.post(url)).status_code == 201


@pytest.mark.asyncio
async def test_resend_guards_404_403_409_and_non_admin(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    assert (await client.post(f"/api/v1/admin/users/{uuid.uuid4()}/welcome-links")).status_code == 404

    # already active -> 409
    activated = await _make_user(db_session, role="counselor", division="overseas")
    assert (await client.post(f"/api/v1/admin/users/{activated.id}/welcome-links")).status_code == 409
    # deactivated but never set up -> 409
    inactive = await _make_user(db_session, role="counselor", division="overseas", active=False)
    await _seed_token(db_session, inactive)
    assert (await client.post(f"/api/v1/admin/users/{inactive.id}/welcome-links")).status_code == 409

    # another division -> 403
    it_admin = await _make_user(db_session, role="it_admin", division="it")
    assert (await _login(client, it_admin.email, division="it")).status_code == 200
    assert (await client.post(f"/api/v1/admin/users/{created['id']}/welcome-links")).status_code == 403

    # non-admin -> refused
    trainer = await _make_user(db_session, role="trainer", division="it")
    assert (await _login(client, trainer.email, division="it")).status_code == 200
    assert (await client.post(f"/api/v1/admin/users/{created['id']}/welcome-links")).status_code == 403


@pytest.mark.asyncio
async def test_users_list_carries_provisioning_status_and_keeps_its_existing_fields(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    rows = (await client.get("/api/v1/admin/users")).json()
    row = next(r for r in rows if r["id"] == created["id"])
    assert row["provisioning_status"] == "pending_setup"
    assert {"id", "name", "email", "division", "role", "active", "phone", "profile"} <= set(row)
    assert any(r["provisioning_status"] == "active" for r in rows)


@pytest.mark.asyncio
async def test_the_filter_returns_exactly_the_expired_users_in_scope(client, db_session):
    overseas_admin = await _make_user(db_session)
    assert (await _login(client, overseas_admin.email)).status_code == 200
    expired = await _make_user(db_session, role="counselor", division="overseas")
    pending = await _make_user(db_session, role="counselor", division="overseas")
    resent = await _make_user(db_session, role="counselor", division="overseas")
    revoked = await _make_user(db_session, role="counselor", division="overseas")
    inactive = await _make_user(db_session, role="counselor", division="overseas", active=False)
    it_user = await _make_user(db_session, role="trainer", division="it")
    await _seed_token(db_session, expired, expires_in=timedelta(hours=-1))
    await _seed_token(db_session, pending)
    await _seed_token(db_session, resent, expires_in=timedelta(hours=-5), superseded=True, created_at=datetime.now(UTC) - timedelta(hours=100))
    await _seed_token(db_session, resent)  # the Re-send's new open link wins
    await _seed_token(db_session, revoked, superseded=True)  # revoked, nothing newer -> needs a Re-send
    await _seed_token(db_session, inactive, expires_in=timedelta(hours=-1))
    await _seed_token(db_session, it_user, expires_in=timedelta(hours=-1))

    rows = (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()
    ids = {r["id"] for r in rows}
    assert {str(expired.id), str(revoked.id)} <= ids
    assert not ({str(pending.id), str(resent.id), str(inactive.id), str(it_user.id)} & ids)
    assert all(r["provisioning_status"] == "link_expired" for r in rows)
    pending_ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=pending_setup")).json()}
    assert {str(pending.id), str(resent.id)} <= pending_ids and str(expired.id) not in pending_ids
    assert (await client.get("/api/v1/admin/users?provisioning_status=bogus")).status_code == 422

    it_admin = await _make_user(db_session, role="it_admin", division="it")
    assert (await _login(client, it_admin.email, division="it")).status_code == 200
    it_ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert str(it_user.id) in it_ids and str(expired.id) not in it_ids

    super_admin = await _make_user(db_session, role="super_admin", division="global")
    assert (await _login(client, super_admin.email, division="it")).status_code == 200
    all_ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert {str(expired.id), str(it_user.id)} <= all_ids


@pytest.mark.asyncio
async def test_a_later_password_set_via_forgot_password_resolves_the_expired_status(client, db_session):
    admin = await _make_user(db_session)
    assert (await _login(client, admin.email)).status_code == 200
    user = await _make_user(db_session, role="counselor", division="overseas")
    await _seed_token(db_session, user, expires_in=timedelta(hours=-1), created_at=datetime.now(UTC) - timedelta(hours=100))
    ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert str(user.id) in ids
    await _seed_token(db_session, user, purpose="reset", used=True)
    ids = {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}
    assert str(user.id) not in ids


@pytest.mark.asyncio
async def test_dashboard_reports_the_scoped_expired_link_count(client, db_session):
    admin = await _make_user(db_session)
    assert (await _login(client, admin.email)).status_code == 200
    before = (await client.get("/api/v1/admin/dashboard")).json()["expired_welcome_links"]
    assert isinstance(before, int)
    await _seed_token(db_session, await _make_user(db_session, role="counselor", division="overseas"), expires_in=timedelta(hours=-1))
    await _seed_token(db_session, await _make_user(db_session, role="trainer", division="it"), expires_in=timedelta(hours=-1))
    after = (await client.get("/api/v1/admin/dashboard")).json()["expired_welcome_links"]
    assert after == before + 1  # only the overseas one is in this admin's scope


@pytest.mark.asyncio
async def test_changing_active_revokes_the_open_welcome_link_and_reactivation_needs_a_resend(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    old, uid = created["development_welcome_token"], created["id"]

    assert (await client.patch(f"/api/v1/admin/users/{uid}", json={"active": False})).status_code == 200
    assert (await client.post(RESET_URL, json={"token": old, "new_password": NEW_PASSWORD})).status_code == 400
    assert (await client.post(f"/api/v1/admin/users/{uid}/welcome-links")).status_code == 409  # deactivated: reactivate first

    assert (await client.patch(f"/api/v1/admin/users/{uid}", json={"active": True})).status_code == 200
    assert (await client.post(RESET_URL, json={"token": old, "new_password": NEW_PASSWORD})).status_code == 400  # the old link stays dead
    assert uid in {r["id"] for r in (await client.get("/api/v1/admin/users?provisioning_status=link_expired")).json()}

    fresh = await client.post(f"/api/v1/admin/users/{uid}/welcome-links")
    assert fresh.status_code == 201
    assert (await client.post(RESET_URL, json={"token": fresh.json()["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200


@pytest.mark.asyncio
async def test_a_patch_that_leaves_active_unchanged_does_not_revoke_the_link(client, db_session, monkeypatch):
    await _admin_client(client, db_session)
    created = await _provision_via_api(client, monkeypatch)
    assert (await client.patch(f"/api/v1/admin/users/{created['id']}", json={"active": True, "full_name": "Renamed"})).status_code == 200
    assert (await client.post(RESET_URL, json={"token": created["development_welcome_token"], "new_password": NEW_PASSWORD})).status_code == 200
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -k "resend or provisioning_status or filter_returns or later_password or dashboard_reports or changing_active or leaves_active" -v`
Expected: FAIL (404/405 on the new route, missing keys, no revocation).

- [ ] **Step 3: Implement in `apps/api/app/api/admin.py`**

3a. Extend the provisioning import: `from app.services.provisioning import deliver_welcome_link, issue_welcome_token, provisioning_statuses, resend_wait_seconds, revoke_welcome_tokens, unusable_password_hash, user_ids_with_status`.

3b. `dashboard`: add one key after `"overseas_applications": ...,`:

```python
        "expired_welcome_links": len(await user_ids_with_status(db, user, "link_expired")),
```

3c. Replace the whole `users` function with:

```python
@router.get("/users")
async def users(division: str | None = None, role: str | None = None, provisioning_status: str | None = None, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if provisioning_status is not None and provisioning_status not in {"pending_setup", "link_expired"}:
        raise HTTPException(422, "provisioning_status must be pending_setup or link_expired")
    stmt = select(User)
    if user.role != "super_admin":
        stmt = stmt.where(User.division == user.division)
    elif division:
        stmt = stmt.where(User.division == division)
    if role:
        stmt = stmt.where(User.role == role)
    if provisioning_status:
        # Resolve the exact id set first so the 500-row cap below cannot hide a match.
        stmt = stmt.where(User.id.in_(await user_ids_with_status(db, user, provisioning_status)))
    xs = (await db.scalars(stmt.order_by(User.created_at.desc()).limit(500))).all()
    statuses = await provisioning_statuses(db, [x.id for x in xs])
    # ADM-004: "views/edits directory detail records" -- `phone`/`profile` are exposed
    # here so a directory edit form can prefill existing values, not just the flat
    # list ADM-001's activate/deactivate action needed. ENH-003: `provisioning_status` is additive.
    return [
        {"id": x.id, "name": x.full_name, "email": x.email, "division": x.division, "role": x.role, "active": x.active, "phone": x.phone, "profile": x.profile,
         "provisioning_status": statuses[x.id].status if x.id in statuses else "active"}
        for x in xs
    ]
```

3d. `update_user`: directly before the `for k in ("full_name", "phone", "active", "email_verified", "profile"):` loop add:

```python
    if "active" in payload and bool(payload["active"]) != item.active:
        # ENH-003 security review S2: a welcome link mailed to a wrong recipient must not come back to
        # life when the account is (re)activated. Any real change of `active` revokes open welcome
        # links; an admin then Re-sends explicitly. Same transaction, same commit as the update.
        await revoke_welcome_tokens(db, item.id)
```

3e. Add after `update_user` (before `@router.post("/programs"...)`):

```python
@router.post("/users/{user_id}/welcome-links", status_code=201)
async def create_welcome_link(user_id: UUID, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """ENH-003 / DEC-SCOPE-019 Re-send. Only for accounts that never set a password (a pending,
    expired or revoked welcome link), and it only ever mails the account's own address -- so it
    cannot reset an active account. Deliberately not idempotent: each call supersedes the previous
    link; a second call inside the cooldown is refused so the endpoint cannot flood a mailbox."""
    # Lock the row so two concurrent Re-sends serialize and only one welcome token stays open.
    item = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not item:
        raise HTTPException(404, "User not found")
    if user.role != "super_admin" and item.division != user.division:
        raise HTTPException(403, "Cannot manage another division")
    if item.id not in await provisioning_statuses(db, [item.id]):
        raise HTTPException(409, "This account has no pending invitation (its password is already set)")
    if not item.active:
        raise HTTPException(409, "Reactivate this account before re-sending its link")
    wait = await resend_wait_seconds(db, item.id)
    if wait:
        raise HTTPException(429, f"A link was just sent; wait {wait} seconds before re-sending", headers={"Retry-After": str(wait)})
    issued = await issue_welcome_token(db, user=item, issued_by=user)
    await db.commit()
    delivery = await deliver_welcome_link(db, user=item, issued=issued, issued_by=user)
    return {"id": item.id, **delivery}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest tests/test_enh_003_first_time_provisioning.py -v`
Expected: PASS (all). Then the neighbouring suites: `python -m pytest tests/test_adm_001_admin_crud.py tests/test_adm_004_directory.py tests/test_adm_014_super_admin_console.py -q` → PASS.

- [ ] **Step 5: Commit** (with approval): `git add apps/api/app/api/admin.py apps/api/tests/test_enh_003_first_time_provisioning.py && git commit -m "feat(enh-003): add welcome-link re-send with cooldown, status filter, dashboard count and revoke-on-active-change" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 7: UI foundations, create-flow feedback, reset-page recovery, Super Admin table/tile

**Files:**
- Modify: `apps/web/app/controls.css` (append one block)
- Create: `apps/web/lib/welcomeLink.ts`, `apps/web/lib/focus.ts`
- Create: `apps/web/tests/lib/welcomeLink.test.ts`
- Modify: `apps/web/components/AdminSchoolStaffPanel.tsx` (lines 25, 57, 60, 164), `apps/web/components/AdminSchoolCreatePanel.tsx` (lines 19, 42, 45, 89), `apps/web/components/WorkflowPanel.tsx`, `apps/web/components/ResetPasswordForm.tsx`
- Modify: `apps/web/app/admin/[module]/page.tsx`, `apps/web/app/admin/page.tsx`
- Modify: `apps/web/components/Analytics.tsx` (export `gaInlineScript`, skip reset pages), `apps/web/next.config.ts` (headers for the reset routes)
- Create: `apps/web/tests/lib/analytics.test.ts`

**Interfaces (used by Tasks 8-9):**
- `type Tone = "success" | "warning" | "error"`, `type Feedback = { text: string; tone: Tone }`, `toneClass: Record<Tone, string>` (`form-message` / `form-warning` / `form-error`).
- `welcomeLinkFeedback(subject: string, data: WelcomeDelivery): Feedback`; `type WelcomeDelivery = { email_status?: string; expires_at?: string }`.
- `requestWelcomeLink(userId: string): Promise<{ ok: boolean; data: WelcomeDelivery & { detail?: unknown } }>` (never throws; a network failure returns `ok: false` with a readable `detail`).
- `errorText(detail: unknown, fallback: string): string`.
- `refocus(id: string): void` in `lib/focus.ts`.
- CSS classes: `.form-warning`, `.action-card.wide`, `.link-list` (+ `.who`, `.meta`), `.skeleton-line`. Everything else reuses existing classes (`.status`, `.status.pending`, `.status.error`, `.badge`, `.btn.small`, `.form-message`, `.form-error`, `.collection-summary`).

**Design rules for every task below** (from the frontend review; existing design language preserved):
- Reuse `.status` pills for state (text always present, never colour alone), `.badge` for role, `.btn small` for actions, `.collection-summary` for result counts, `.empty`-style copy for empty states.
- One outcome region per panel that is **mounted before** content changes (`role="status" aria-live="polite"`), so announcements are reliable.
- Buttons that repeat per row carry an `aria-label` naming the person. After an action ends, keyboard focus is restored (`refocus`) or moved to the outcome region; never dropped to `<body>`.
- A tone distinguishes success (green), **warning** (amber: account created but email not delivered — partial success, not an error) and error (red).
- No `event.currentTarget` after an `await` (RAID I-05). No new dependency. `DataTable` is not touched.
- `prefers-reduced-motion` respected; touch targets ≥ 44 px on ≤ 640 px.

- [ ] **Step 1: Write the failing unit tests** — `apps/web/tests/lib/welcomeLink.test.ts`

```ts
import { afterEach, describe, expect, it, vi } from "vitest";

import { errorText, requestWelcomeLink, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

afterEach(() => vi.unstubAllGlobals());

describe("welcomeLinkFeedback", () => {
  it("is a success for a sent link and states the 72-hour validity", () => {
    const result = welcomeLinkFeedback("Account created for a@b.co.", { email_status: "sent" });
    expect(result.tone).toBe("success");
    expect(result.text).toContain("Account created for a@b.co.");
    expect(result.text).toContain("72 hours");
  });

  it("is a warning, not an error, when email is not configured", () => {
    const result = welcomeLinkFeedback("Account created.", { email_status: "not_configured" });
    expect(result.tone).toBe("warning");
    expect(result.text).toContain("not configured");
    expect(result.text).toContain("Re-send");
  });

  it("is a warning when the send failed", () => {
    const result = welcomeLinkFeedback("Account created.", { email_status: "failed" });
    expect(result.tone).toBe("warning");
    expect(result.text).toContain("could not be sent");
  });

  it("never mentions a password value", () => {
    expect(welcomeLinkFeedback("x", { email_status: "sent" }).text).not.toMatch(/ChangeMe/);
  });
});

describe("toneClass", () => {
  it("maps tones onto the existing message classes plus form-warning", () => {
    expect(toneClass).toEqual({ success: "form-message", warning: "form-warning", error: "form-error" });
  });
});

describe("errorText", () => {
  it("uses a string detail and falls back otherwise", () => {
    expect(errorText("Nope", "fallback")).toBe("Nope");
    expect(errorText([{ msg: "x" }], "fallback")).toBe("fallback");
    expect(errorText(undefined, "fallback")).toBe("fallback");
  });
});

describe("requestWelcomeLink", () => {
  it("POSTs to the welcome-links endpoint and returns the parsed body", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ email_status: "sent" }), { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await requestWelcomeLink("u1");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/admin/users/u1/welcome-links", { method: "POST" });
    expect(result).toEqual({ ok: true, data: { email_status: "sent" } });
  });

  it("returns ok:false with the server detail on an error status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "no pending invitation" }), { status: 409 })));
    expect(await requestWelcomeLink("u1")).toEqual({ ok: false, data: { detail: "no pending invitation" } });
  });

  it("never throws on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    const result = await requestWelcomeLink("u1");
    expect(result.ok).toBe(false);
    expect(String(result.data.detail)).toContain("Network error");
  });
});
```

- [ ] **Step 2: Run to verify it fails** — from `apps/web`: `npx vitest run tests/lib/welcomeLink.test.ts` → FAIL (module not found).

- [ ] **Step 3: Create the helpers and append the CSS**

`apps/web/lib/welcomeLink.ts`:

```ts
// ENH-003 / DEC-SCOPE-019: shared wording and request helper for the first-time set-password link.
// Never mentions a password value -- admins no longer know or choose one.
export type Tone = "success" | "warning" | "error";
export type Feedback = { text: string; tone: Tone };
export type WelcomeDelivery = { email_status?: string; expires_at?: string };

// Reuses the existing message classes; `form-warning` (controls.css) is the amber sibling used when
// the account WAS created but the email was not delivered -- a partial success, not an error.
export const toneClass: Record<Tone, string> = { success: "form-message", warning: "form-warning", error: "form-error" };

export function welcomeLinkFeedback(subject: string, data: WelcomeDelivery): Feedback {
  if (data.email_status === "sent") {
    return { text: `${subject} A set-password link was emailed and is valid for 72 hours.`, tone: "success" };
  }
  const why = data.email_status === "not_configured" ? "email is not configured on this server" : "the email could not be sent";
  return {
    text: `${subject} The email was not delivered (${why}). Re-send the link from the Users page or dashboard once email works, or ask the user to use "Forgot your password?" on the sign-in page.`,
    tone: "warning",
  };
}

export function errorText(detail: unknown, fallback: string): string {
  return typeof detail === "string" ? detail : fallback;
}

export async function requestWelcomeLink(userId: string): Promise<{ ok: boolean; data: WelcomeDelivery & { detail?: unknown } }> {
  try {
    const response = await fetch(`/api/v1/admin/users/${userId}/welcome-links`, { method: "POST" });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, data };
  } catch {
    return { ok: false, data: { detail: "Network error -- the link was not re-sent. Please try again." } };
  }
}
```

`apps/web/lib/focus.ts`:

```ts
// A control that was disabled while busy loses keyboard focus in most browsers; put it back once
// the request ends so keyboard and screen-reader users keep their place.
export function refocus(id: string): void {
  requestAnimationFrame(() => document.getElementById(id)?.focus());
}
```

Append to `apps/web/app/controls.css` (uses existing tokens; flat colours; no shadows):

```css
/* ENH-003: set-password link UI */
.form-warning{padding:12px 14px;border-radius:10px;background:#fff7ed;color:var(--amber)}
.action-card.wide{grid-column:1/-1}
.link-list{list-style:none;margin:0;padding:0;display:grid}
.link-list li{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px 16px;padding:12px 0;border-bottom:1px solid #edf1f6}
.link-list li:last-child{border-bottom:0}
.link-list .who{display:grid;gap:2px;min-width:0}
.link-list .who span{color:var(--muted);font-size:13px;overflow-wrap:anywhere}
.link-list .who strong{overflow-wrap:anywhere}
.link-list .meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.skeleton-line{height:44px;border-radius:10px;background:#edf1f6;animation:skeleton-pulse 1.2s ease-in-out infinite}
@keyframes skeleton-pulse{50%{opacity:.5}}
@media(prefers-reduced-motion:reduce){.skeleton-line{animation:none}}
@media(max-width:640px){.link-list .meta{width:100%}.link-list .btn{width:100%;min-height:44px}}
```

- [ ] **Step 4: Run to verify it passes** — `npx vitest run tests/lib/welcomeLink.test.ts` → PASS (9 tests).

- [ ] **Step 5: Wire the two create panels to `Feedback`**

`AdminSchoolStaffPanel.tsx`: add `import { type Feedback, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";`, then

| line | old | new |
|---|---|---|
| 25 | `useState<{ text: string; failed: boolean } \| null>(null)` | `useState<Feedback \| null>(null)` |
| 57 | `setMessage({ text: detailMessage(data.detail), failed: true });` | `setMessage({ text: detailMessage(data.detail), tone: "error" });` |
| 60 | `setMessage({ text: \`Account created for ${data.email} (default password: ChangeMe@12345 -- share it securely and ask them to change it).\`, failed: false });` | `setMessage(welcomeLinkFeedback(\`Account created for ${data.email}.\`, data));` |
| 164 | `className={message.failed ? "form-error" : "form-message"}` | `className={toneClass[message.tone]}` |

`AdminSchoolCreatePanel.tsx`: same import, then

| line | old | new |
|---|---|---|
| 19 | `useState<{ text: string; failed: boolean } \| null>(null)` | `useState<Feedback \| null>(null)` |
| 42 | `setMessage({ text: detailMessage(data.detail), failed: true });` | `setMessage({ text: detailMessage(data.detail), tone: "error" });` |
| 45 | `setMessage({ text: \`School created. Coordinator account ready for ${data.coordinator_email} (default password: ChangeMe@12345 -- share it securely and ask them to change it).\`, failed: false });` | `setMessage(welcomeLinkFeedback(\`School created. Coordinator account ready for ${data.coordinator_email}.\`, data));` |
| 89 | `className={message.failed ? "form-error" : "form-message"}` | `className={toneClass[message.tone]}` |

(The e2e specs match `/School created\./` — that text is preserved.)

- [ ] **Step 6: Remove the "Temporary password" field** — in `WorkflowPanel.tsx` replace the exact substring `{ name: "password", label: "Temporary password", type: "password", required: true }, ` with an empty string (exactly one occurrence; `grep -c "Temporary password" apps/web/components/WorkflowPanel.tsx` → `0` afterwards).

- [ ] **Step 7: Reset-page recovery** — `ResetPasswordForm.tsx`:

```tsx
// imports: add
import Link from "next/link";
```

Add state after `const [busy, setBusy] = useState(false);`:

```tsx
  const [expiredLink, setExpiredLink] = useState(false);
```

In `submit`, after `setError("");` add `setExpiredLink(false);` and replace the failure block

```tsx
    if (!response.ok) {
      setError(message(data.detail));
      return;
    }
```

with

```tsx
    if (!response.ok) {
      setError(message(data.detail));
      setExpiredLink(response.status === 400);
      return;
    }
```

Give the hint an id and connect it, then replace the error block. Change `<span className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>` to `<span id="reset-password-hint" className="muted" style={{ fontSize: 12 }}>Use at least 10 characters.</span>`, add `aria-describedby="reset-password-hint"` to `#reset-new-password`, and replace

```tsx
      {error && (
        <div className="form-error" role="alert" aria-live="assertive">
          {error}
        </div>
      )}
```

with

```tsx
      {error && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>{error}</p>
          {expiredLink && (
            <p style={{ margin: "6px 0 0" }}>
              <Link href={`/${division}/forgot-password`} style={{ color: "var(--blue)", fontWeight: 800 }}>Request a new reset link</Link>{" "}
              or, if this was your first-time invitation, ask your administrator to re-send it.
            </p>
          )}
        </div>
      )}
```

(Same link styling `LoginForm` already uses. Recovery is now a real link, not text naming a button.)

- [ ] **Step 8: Super Admin table + tile**

In `apps/web/app/admin/[module]/page.tsx`: line 34 → append the column: replace `["role", "Role"], ["active", "Active"]]);` with `["role", "Role"], ["active", "Active"], ["provisioning_status", "Setup"]]);`. Add above `async function tableData`:

```ts
// ENH-003: humane labels for the derived setup status (DataTable would otherwise print `pending_setup`).
const SETUP_LABEL: Record<string, string> = { active: "Password set", pending_setup: "Awaiting setup", link_expired: "Link expired" };
const withSetupLabels = (rows: Record<string, unknown>[]) => rows.map((row) => ({ ...row, provisioning_status: SETUP_LABEL[String(row.provisioning_status)] ?? row.provisioning_status }));
```

and wrap the three user tables: line 38 `rows: await getRows("/api/v1/admin/users")` → `rows: withSetupLabels(await getRows("/api/v1/admin/users"))`; line 41 `rows: [...it, ...overseas]` → `rows: withSetupLabels([...it, ...overseas])`; line 45 `rows: rows.filter(row => !["it_student", "overseas_student", "super_admin"].includes(String(row.role)))` → `rows: withSetupLabels(rows.filter(row => !["it_student", "overseas_student", "super_admin"].includes(String(row.role))))`.

In `apps/web/app/admin/page.tsx` (single-line file) replace the exact substring `{label:"Universities",value:d.universities}]` with `{label:"Universities",value:d.universities},{label:"Expired welcome links",value:d.expired_welcome_links??0}]`.

- [ ] **Step 8a: Keep set-password links out of Google Analytics** (security review S1). `gtag('config')` reports the full page URL, query string included, so a `/reset-password?token=…` visit would send a live credential to Google whenever `NEXT_PUBLIC_GA_ID` is set. First write `apps/web/tests/lib/analytics.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";

import { gaInlineScript } from "@/components/Analytics";

function gtagCalls(path: string): string[] {
  window.history.pushState({}, "", path);
  (window as unknown as { dataLayer?: unknown[] }).dataLayer = undefined;
  (0, eval)(gaInlineScript("G-TEST"));
  return (window as unknown as { dataLayer: IArguments[] }).dataLayer.map((entry) => String(entry[0]));
}

describe("Analytics inline script", () => {
  beforeEach(() => window.history.pushState({}, "", "/"));

  it("configures GA on ordinary pages", () => {
    expect(gtagCalls("/it/programs")).toContain("config");
  });

  it("never configures GA on reset-password pages, whose URL carries a live token", () => {
    expect(gtagCalls("/overseas/reset-password?token=abc")).not.toContain("config");
    expect(gtagCalls("/it/reset-password?token=abc")).not.toContain("config");
  });
});
```

Run `npx vitest run tests/lib/analytics.test.ts` → FAIL (`gaInlineScript` is not exported). Then replace the whole of `apps/web/components/Analytics.tsx` with:

```tsx
import Script from "next/script";

// ENH-003 security review S1: `gtag('config')` reports the full page URL, query string included.
// A set-password / reset link carries a live credential in its query string, so those pages are
// never configured -- and therefore never reported to Google.
export function gaInlineScript(id: string): string {
  return `window.dataLayer=window.dataLayer||[]
function gtag(){dataLayer.push(arguments)}
gtag('js',new Date())
if(!/\\/reset-password(\\/|$)/.test(window.location.pathname)){gtag('config','${id}',{anonymize_ip:true})}
`;
}

export default function Analytics() {
  const id = process.env.NEXT_PUBLIC_GA_ID;
  if (!id) return null;
  return (
    <>
      <Script src={`https://www.googletagmanager.com/gtag/js?id=${id}`} strategy="afterInteractive" />
      <Script id="ga" strategy="afterInteractive">{gaInlineScript(id)}</Script>
    </>
  );
}
```

Re-run → PASS. (`SchoolAccountInvite` links carry their token in the URL *path* and are reported the same way today; that flow is out of scope for ENH-003 and is only noted in the security findings.)

- [ ] **Step 8b: Never send the reset link as a Referer or cache it** (security review S1/S9). Replace `apps/web/next.config.ts` with:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  typedRoutes: false,
  // ENH-003 security review: the reset / set-password link carries a live token in its query
  // string -- never send it as a Referer and ask for it not to be cached.
  async headers() {
    return [
      {
        source: "/:division(it|overseas)/reset-password",
        headers: [
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "Cache-Control", value: "no-store" },
        ],
      },
    ];
  },
};

export default nextConfig;
```

The Playwright spec (Task 10) asserts `Referrer-Policy`; `Cache-Control` is best-effort because Next may override it for statically prerendered pages, so it is not asserted.

- [ ] **Step 9: Verify** — from `apps/web`: `npx tsc --noEmit` and `npx vitest run` → clean. Check `getByText`-style e2e selectors that match `Active` in the admin tables still hold: `grep -rn "toContainText(\"Active\")" apps/web/tests/e2e` and confirm each is a substring match (a row now reads e.g. "Active Awaiting setup", which still contains "Active").

- [ ] **Step 10: Commit** (with approval): `git add apps/web && git commit -m "feat(enh-003): set-password feedback helpers, warning tone and reset recovery link" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 8: Users directory — status pill, filter with live count, Re-send

**Files:**
- Modify: `apps/web/components/AdminUserManagementPanel.tsx`
- Create: `apps/web/tests/components/AdminUserManagementPanel.test.tsx`

**Interfaces:** consumes `Feedback`, `toneClass`, `welcomeLinkFeedback`, `requestWelcomeLink`, `errorText` (Task 7), `refocus`.

- [ ] **Step 1: Write the failing component tests** (Vitest + Testing Library, `jsdom`, already configured; no live DB, so no RAID I-06/I-07 flake exposure)

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminUserManagementPanel from "@/components/AdminUserManagementPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const base = { division: "overseas", phone: null, profile: {} };
const users = [
  { ...base, id: "a", name: "Asha Active", email: "asha@example.local", role: "counselor", active: true, provisioning_status: "active" },
  { ...base, id: "p", name: "Pia Pending", email: "pia@example.local", role: "academic_team", active: true, provisioning_status: "pending_setup" },
  { ...base, id: "e", name: "Eli Expired", email: "eli@example.local", role: "career_counselor", active: true, provisioning_status: "link_expired" },
  { ...base, id: "d", name: "Dan Deactivated", email: "dan@example.local", role: "counselor", active: false, provisioning_status: "pending_setup" },
];

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init))));
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function renderPanel() {
  stubFetch((url, init) => (init?.method === "POST" ? json({ id: "p", email_status: "sent" }, 201) : json(users)));
  render(<AdminUserManagementPanel />);
  await screen.findByText("Pia Pending");
}

describe("AdminUserManagementPanel setup status", () => {
  it("shows a text pill only for accounts that have not set a password", async () => {
    await renderPanel();
    const pia = screen.getByRole("row", { name: /Pia Pending/ });
    expect(within(pia).getByText("Awaiting setup")).toHaveClass("status", "pending");
    expect(within(screen.getByRole("row", { name: /Eli Expired/ })).getByText("Link expired")).toHaveClass("status", "error");
    expect(within(screen.getByRole("row", { name: /Asha Active/ })).queryByText(/Awaiting setup|Link expired/)).toBeNull();
  });

  it("offers Re-send only for active accounts that are pending or expired, with a per-person accessible name", async () => {
    await renderPanel();
    expect(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Re-send set-password link to Asha Active/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Re-send set-password link to Dan Deactivated/ })).toBeNull();
  });
});

describe("AdminUserManagementPanel setup filter", () => {
  it("narrows the list, announces the count, and offers a way back when nothing matches", async () => {
    await renderPanel();
    const filter = screen.getByLabelText("Account setup");
    fireEvent.change(filter, { target: { value: "link_expired" } });
    expect(screen.getByText("Eli Expired")).toBeInTheDocument();
    expect(screen.queryByText("Pia Pending")).toBeNull();
    expect(screen.getByText("1 account shown")).toHaveAttribute("aria-live", "polite");

    fireEvent.change(screen.getByLabelText("Search by name, email, or role"), { target: { value: "zzz" } });
    expect(screen.getByText("No records match this search.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search by name, email, or role"), { target: { value: "" } });
    fireEvent.change(filter, { target: { value: "pending_setup" } });
    expect(screen.getByText("Pia Pending")).toBeInTheDocument();
  });

  it("shows a specific empty message and 'Show all accounts' when the filter matches nobody", async () => {
    stubFetch(() => json([users[0]]));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Asha Active");
    fireEvent.change(screen.getByLabelText("Account setup"), { target: { value: "link_expired" } });
    expect(screen.getByText("No accounts have an expired link.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show all accounts" }));
    expect(screen.getByText("Asha Active")).toBeInTheDocument();
  });

  it("makes the scrollable table keyboard-reachable", async () => {
    await renderPanel();
    const region = screen.getByRole("region", { name: "Users" });
    expect(region).toHaveAttribute("tabindex", "0");
  });
});

describe("AdminUserManagementPanel Re-send", () => {
  it("re-sends, reports the outcome in a live region, marks the row pending and returns focus to the button", async () => {
    await renderPanel();
    const button = screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" });
    fireEvent.click(button);
    const outcome = await screen.findByText(/New link created for Eli Expired\./);
    expect(outcome).toHaveClass("form-message");
    expect(outcome).toHaveAttribute("aria-live", "polite");
    expect(within(screen.getByRole("row", { name: /Eli Expired/ })).getByText("Awaiting setup")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Re-send set-password link to Eli Expired" })).toHaveFocus());
  });

  it("shows an amber warning, not an error, when the link was created but the email was not sent", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ email_status: "not_configured" }, 201) : json(users)));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Pia Pending");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" }));
    expect(await screen.findByText(/The email was not delivered/)).toHaveClass("form-warning");
  });

  it("shows the server's error, keeps the row and re-enables the button", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ detail: "This account has no pending invitation (its password is already set)" }, 409) : json(users)));
    render(<AdminUserManagementPanel />);
    await screen.findByText("Pia Pending");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" }));
    expect(await screen.findByText(/no pending invitation/)).toHaveClass("form-error");
    expect(screen.getByRole("button", { name: "Re-send set-password link to Pia Pending" })).not.toBeDisabled();
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `npx vitest run tests/components/AdminUserManagementPanel.test.tsx` → FAIL (no pills / no Re-send / no filter).

- [ ] **Step 3: Implement in `AdminUserManagementPanel.tsx`**

3a. Imports (after `import { useRouter } from "next/navigation";`):

```tsx
import { refocus } from "@/lib/focus";
import { type Feedback, errorText, requestWelcomeLink, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";
```

3b. Row type: add `provisioning_status?: "active" | "pending_setup" | "link_expired";` as the last field of `AdminUserRow`.

3c. Message state and existing call sites move to `tone` (same visual result: warning is used for the existing 409 "confirm deactivate" prompt, which is not a failure):

| where | old | new |
|---|---|---|
| state | `useState<{ id: string; text: string; failed: boolean } \| null>(null)` | `useState<({ id: string } & Feedback) \| null>(null)` |
| `toggleActive` 409 | `failed: true });` (the `Click "Confirm deactivate"` message) | `tone: "warning" });` |
| `toggleActive` other error | `setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });` | `setMessage({ id: row.id, text: detailMessage(data.detail), tone: "error" });` |
| `toggleActive` success | `failed: false });` | `tone: "success" });` |
| `saveDetails` error | `setMessage({ id: row.id, text: detailMessage(data.detail), failed: true });` | `setMessage({ id: row.id, text: detailMessage(data.detail), tone: "error" });` |
| `saveDetails` success | `setMessage({ id: row.id, text: "Details updated.", failed: false });` | `setMessage({ id: row.id, text: "Details updated.", tone: "success" });` |
| render | `className={message.failed ? "form-error" : "form-message"}` | `className={toneClass[message.tone]}` |

3d. State + memo:

```tsx
  const [setupFilter, setSetupFilter] = useState<"all" | "pending_setup" | "link_expired">("all");
```

```tsx
  const visible = useMemo(() => {
    if (!users) return [];
    const scoped = scopedRoles ? users.filter((u) => scopedRoles.includes(u.role)) : users;
    const bySetup = setupFilter === "all" ? scoped : scoped.filter((u) => u.provisioning_status === setupFilter);
    const normalized = query.trim().toLowerCase();
    if (!normalized) return bySetup;
    return bySetup.filter((u) => u.name.toLowerCase().includes(normalized) || u.email.toLowerCase().includes(normalized) || u.role.toLowerCase().includes(normalized));
  }, [users, query, scopedRoles, setupFilter]);
```

3e. Handler (after `toggleActive`):

```tsx
  async function resendWelcome(row: AdminUserRow) {
    setBusyId(row.id);
    setMessage(null);
    const { ok, data } = await requestWelcomeLink(row.id);
    setBusyId(null);
    if (!ok) {
      setMessage({ id: row.id, text: errorText(data.detail, "Unable to re-send the link."), tone: "error" });
    } else {
      setMessage({ id: row.id, ...welcomeLinkFeedback(`New link created for ${row.name}.`, data) });
      setUsers((prev) => (prev ? prev.map((u) => (u.id === row.id ? { ...u, provisioning_status: "pending_setup" } : u)) : prev));
      router.refresh();
    }
    refocus(`resend-${row.id}`);
  }
```

3f. Filter + live count, directly after the search `</div>`:

```tsx
      <div className="field" style={{ marginTop: 8 }}>
        <label htmlFor="admin-user-setup">Account setup</label>
        <select id="admin-user-setup" value={setupFilter} onChange={(event) => setSetupFilter(event.target.value as "all" | "pending_setup" | "link_expired")}>
          <option value="all">All accounts</option>
          <option value="pending_setup">Awaiting setup</option>
          <option value="link_expired">Link expired</option>
        </select>
      </div>
      {users.length > 0 && (
        <p className="collection-summary" aria-live="polite" style={{ margin: "8px 0 0" }}>
          {visible.length} {visible.length === 1 ? "account" : "accounts"} shown
        </p>
      )}
```

3g. Empty state — replace `<p className="muted" style={{ marginTop: 12 }}>{users.length === 0 ? "No users found." : "No records match this search."}</p>` with:

```tsx
        <div style={{ marginTop: 12 }}>
          <p className="muted">
            {users.length === 0
              ? "No users found."
              : setupFilter !== "all" && !query.trim()
                ? setupFilter === "pending_setup" ? "No accounts are awaiting setup." : "No accounts have an expired link."
                : "No records match this search."}
          </p>
          {setupFilter !== "all" && (
            <button type="button" className="btn ghost small" onClick={() => setSetupFilter("all")}>Show all accounts</button>
          )}
        </div>
```

3h. Scrollable region: change `<div className="table-wrap" style={{ marginTop: 12 }}>` to `<div className="table-wrap" style={{ marginTop: 12 }} role="region" aria-label={scopedRoles ? "Directory" : "Users"} tabIndex={0}>`.

3i. Status cell — replace `<td>{row.active ? "Active" : "Inactive"}</td>` with:

```tsx
                  <td>
                    {row.active ? "Active" : "Inactive"}
                    {row.provisioning_status === "pending_setup" && <span className="status pending" style={{ marginLeft: 8 }}>Awaiting setup</span>}
                    {row.provisioning_status === "link_expired" && <span className="status error" style={{ marginLeft: 8 }}>Link expired</span>}
                  </td>
```

3j. Re-send button, right after the "Edit details" `</button>`:

```tsx
                    {row.active && (row.provisioning_status === "pending_setup" || row.provisioning_status === "link_expired") && (
                      <>
                        {" "}
                        <button
                          id={`resend-${row.id}`}
                          type="button"
                          className="btn small secondary"
                          disabled={busyId === row.id}
                          aria-label={`Re-send set-password link to ${row.name}`}
                          onClick={() => void resendWelcome(row)}
                        >
                          {busyId === row.id ? "Sending…" : "Re-send link"}
                        </button>
                      </>
                    )}
```

- [ ] **Step 4: Run to verify it passes** — `npx vitest run tests/components/AdminUserManagementPanel.test.tsx` → PASS (8 tests); then `npx tsc --noEmit`.

- [ ] **Step 5: Commit** (with approval): `git add apps/web && git commit -m "feat(enh-003): show setup status, filter and Re-send in the users directory" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 9: `AdminExpiredLinksPanel` (new) + dashboard mount

**Files:**
- Create: `apps/web/components/AdminExpiredLinksPanel.tsx`
- Create: `apps/web/tests/components/AdminExpiredLinksPanel.test.tsx`
- Modify: `apps/web/components/WorkflowPanel.tsx` (import, flag, mount)

**Why a list, not a table:** the shared `.table` forces `min-width:650px`, so on a phone the Re-send action would sit off-screen. A `.link-list` stacks name/email, role and state, and the action becomes a full-width 44 px button at ≤ 640 px. `DataTable` is read-only (no per-row actions) and is deliberately not extended — that would put every portal's tables at risk.

- [ ] **Step 1: Write the failing component tests**

```tsx
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminExpiredLinksPanel from "@/components/AdminExpiredLinksPanel";

const rows = [
  { id: "u1", name: "Asha Rao", email: "asha@example.local", role: "academic_team" },
  { id: "u2", name: "Ben Cole", email: "ben@example.local", role: "career_counselor" },
];
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const mock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminExpiredLinksPanel states", () => {
  it("shows a labelled loading state first, then the list with a count", async () => {
    stubFetch(() => json(rows));
    render(<AdminExpiredLinksPanel />);
    expect(screen.getByText("Loading expired links…")).toBeInTheDocument();
    await screen.findByText("Asha Rao");
    expect(screen.getByRole("heading", { name: "Expired set-password links (2)" })).toBeInTheDocument();
    expect(screen.getByText("academic team")).toHaveClass("badge");
    expect(screen.getAllByText("Link expired")).toHaveLength(2);
  });

  it("shows a calm empty state", async () => {
    stubFetch(() => json([]));
    render(<AdminExpiredLinksPanel />);
    expect(await screen.findByText("No expired links.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Expired set-password links" })).toBeInTheDocument();
  });

  it("shows an alert with 'Try again' that recovers", async () => {
    let calls = 0;
    stubFetch(() => (++calls === 1 ? json({}, 500) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load expired links.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("requests only the expired filter and lays out for keyboard users (native buttons, named per person)", async () => {
    const mock = stubFetch(() => json(rows));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    expect(mock.mock.calls[0][0]).toBe("/api/v1/admin/users?provisioning_status=link_expired");
    expect(screen.getByRole("list", { name: "Accounts with an expired link" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }).tagName).toBe("BUTTON");
  });
});

describe("AdminExpiredLinksPanel Re-send", () => {
  it("removes the row, announces the outcome and moves focus to the outcome region", async () => {
    const mock = stubFetch((url, init) => (init?.method === "POST" ? json({ id: "u1", email_status: "sent" }, 201) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));

    const status = screen.getByRole("status");
    await waitFor(() => expect(within(status).getByText(/New link created for Asha Rao\./)).toHaveClass("form-message"));
    expect(mock).toHaveBeenCalledWith("/api/v1/admin/users/u1/welcome-links", { method: "POST" });
    expect(screen.queryByText("Asha Rao")).toBeNull();
    expect(screen.getByText("Ben Cole")).toBeInTheDocument();
    await waitFor(() => expect(status).toHaveFocus());
  });

  it("shows an amber warning when the link was created but the email was not delivered", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ email_status: "failed" }, 201) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));
    expect(await screen.findByText(/The email was not delivered/)).toHaveClass("form-warning");
  });

  it("keeps the row on a server error, shows it as an error and returns focus to the button", async () => {
    stubFetch((url, init) => (init?.method === "POST" ? json({ detail: "Reactivate this account before re-sending its link" }, 409) : json(rows)));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));
    expect(await screen.findByText("Reactivate this account before re-sending its link")).toHaveClass("form-error");
    const button = screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" });
    expect(button).not.toBeDisabled();
    await waitFor(() => expect(button).toHaveFocus());
  });

  it("survives a network failure without getting stuck busy", async () => {
    let posted = false;
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") { posted = true; return Promise.reject(new TypeError("offline")); }
      return Promise.resolve(json(rows));
    }));
    render(<AdminExpiredLinksPanel />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" }));
    expect(await screen.findByText(/Network error/)).toHaveClass("form-error");
    expect(posted).toBe(true);
    expect(screen.getByRole("button", { name: "Re-send set-password link to Asha Rao" })).not.toBeDisabled();
  });
});
```

- [ ] **Step 2: Run to verify it fails** — `npx vitest run tests/components/AdminExpiredLinksPanel.test.tsx` → FAIL (module not found).

- [ ] **Step 3: Create the panel**

```tsx
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { refocus } from "@/lib/focus";
import { type Feedback, errorText, requestWelcomeLink, toneClass, welcomeLinkFeedback } from "@/lib/welcomeLink";

type ExpiredRow = { id: string; name: string; email: string; role: string };

// ENH-003 / DEC-SCOPE-019: admin-provisioned accounts whose 72-hour set-password link expired
// unused (division-scoped server-side). The list is fetched after first paint, so the dashboard's
// own content is never blocked by it. Loading / empty / error states are explicit; the outcome
// region is mounted from the start so screen readers announce Re-send results reliably.
export default function AdminExpiredLinksPanel() {
  const [rows, setRows] = useState<ExpiredRow[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const feedbackRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoadFailed(false);
    setRows(null);
    try {
      const response = await fetch("/api/v1/admin/users?provisioning_status=link_expired", { signal });
      if (!response.ok) throw new Error(String(response.status));
      setRows(await response.json());
    } catch (error) {
      if ((error as Error).name !== "AbortError") setLoadFailed(true);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  async function resend(row: ExpiredRow) {
    setBusyId(row.id);
    setFeedback(null);
    const { ok, data } = await requestWelcomeLink(row.id);
    setBusyId(null);
    if (!ok) {
      setFeedback({ text: errorText(data.detail, "Unable to re-send the link."), tone: "error" });
      refocus(`expired-resend-${row.id}`);
      return;
    }
    setFeedback(welcomeLinkFeedback(`New link created for ${row.name}.`, data));
    setRows((prev) => (prev ? prev.filter((r) => r.id !== row.id) : prev));
    // The row (and its button) is gone: keep keyboard focus in this panel and let the region announce.
    requestAnimationFrame(() => feedbackRef.current?.focus());
  }

  const count = rows?.length ?? 0;
  return (
    <div className={`action-card${count > 0 ? " wide" : ""}`}>
      <div>
        <h3>Expired set-password links{count > 0 ? ` (${count})` : ""}</h3>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Accounts whose emailed link expired before the user set a password.</p>
      </div>
      <div ref={feedbackRef} tabIndex={-1} role="status" aria-live="polite">
        {feedback && <div className={toneClass[feedback.tone]}>{feedback.text}</div>}
      </div>
      {loadFailed ? (
        <div className="form-error" role="alert">
          <p style={{ margin: 0 }}>Could not load expired links.</p>
          <button type="button" className="btn small secondary" style={{ marginTop: 8 }} onClick={() => void load()}>Try again</button>
        </div>
      ) : rows === null ? (
        <div aria-busy="true">
          <p className="muted" style={{ margin: "0 0 8px" }}>Loading expired links…</p>
          <div className="skeleton-line" aria-hidden="true" />
        </div>
      ) : rows.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No expired links.</p>
      ) : (
        <ul className="link-list" role="list" aria-label="Accounts with an expired link">
          {rows.map((row) => (
            <li key={row.id}>
              <div className="who">
                <strong>{row.name}</strong>
                <span>{row.email}</span>
              </div>
              <div className="meta">
                <span className="badge">{row.role.replace(/_/g, " ")}</span>
                <span className="status error">Link expired</span>
                <button
                  id={`expired-resend-${row.id}`}
                  type="button"
                  className="btn small"
                  disabled={busyId === row.id}
                  aria-label={`Re-send set-password link to ${row.name}`}
                  onClick={() => void resend(row)}
                >
                  {busyId === row.id ? "Sending…" : "Re-send link"}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Mount it in `WorkflowPanel.tsx`**

Add after `import AdminUserManagementPanel from "./AdminUserManagementPanel";`:

```tsx
import AdminExpiredLinksPanel from "./AdminExpiredLinksPanel";
```

Add after the `const showAuditExport = ...;` line:

```tsx
  // ENH-003: expired set-password links on the IT and Overseas admin dashboards (`PortalPage` always
  // renders this panel under the dashboard content). Independent of `isAdmin`, which excludes
  // overseas_admin. The Super Admin's own `/admin` page shows a tile and links to /admin/users.
  const showExpiredLinks = ["it_admin", "overseas_admin", "super_admin"].includes(user.role) && section === "dashboard";
```

In the big `return`, replace `{showAuditExport && <AuditExportPanel/>}` with `{showAuditExport && <AuditExportPanel/>}{showExpiredLinks && <AdminExpiredLinksPanel/>}`.

- [ ] **Step 5: Run to verify it passes** — `npx vitest run tests/components` → PASS (8 + 8); `npx tsc --noEmit` clean.

- [ ] **Step 6: Commit** (with approval): `git add apps/web && git commit -m "feat(enh-003): list expired set-password links on admin dashboards" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 10: Playwright — helper, new spec, migrate 13 existing specs

**Files:**
- Create: `apps/web/tests/e2e/helpers/welcome.ts`
- Create: `apps/web/tests/e2e/enh-003-first-time-provisioning.spec.ts`
- Modify: 13 specs (see table) — every `ChangeMe@12345` occurrence, plus the `adm-*` callers that pass `password`

**Interfaces:** produces `E2E_PASSWORD`, `activateWithToken(request, token, password?)`, `createAndActivate(request, path, data, password?)`.

Division of labour: component behaviour (states, focus, tones, live regions) is covered by the Vitest component tests in Tasks 8-9 — no live DB, no I-06/I-07 flakes. Playwright covers the real end-to-end flows and responsive layout.

- [ ] **Step 1: Create the helper** — `apps/web/tests/e2e/helpers/welcome.ts`

```ts
import type { APIRequestContext } from "@playwright/test";

// ENH-003 / DEC-SCOPE-019: admin-provisioned accounts have no default password. In development/test
// the create response carries `development_welcome_token`; specs set the password with it, exactly
// as a real user would from the emailed link.
export const E2E_PASSWORD = "E2e-Welcome-Pass-1!";

export async function activateWithToken(request: APIRequestContext, token: string, password: string = E2E_PASSWORD) {
  const response = await request.post("/api/v1/auth/reset-password", { data: { token, new_password: password } });
  if (!response.ok()) throw new Error(`welcome activation failed: ${response.status()} ${await response.text()}`);
}

export async function createAndActivate(request: APIRequestContext, path: string, data: Record<string, unknown>, password: string = E2E_PASSWORD) {
  const created = await request.post(path, { data });
  if (!created.ok()) throw new Error(`create failed: ${created.status()} ${await created.text()}`);
  const body = await created.json();
  await activateWithToken(request, body.development_welcome_token, password);
  return body;
}
```

- [ ] **Step 2: Write the new spec** — `apps/web/tests/e2e/enh-003-first-time-provisioning.spec.ts`

```ts
import { expect, test, type Page } from "@playwright/test";

import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";

// ENH-003 / DEC-SCOPE-019 -- first-time provisioning: no default password, emailed 72-hour
// single-use link, admin Re-send. Accounts are throwaway records created through the real admin API.

async function signIn(page: Page, division: "it" | "overseas", email: string, password = "Demo@123") {
  await page.goto(`/${division}/login`);
  await page.fill("#login-email", email);
  await page.fill("#login-password", password);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL(`**/${division}/admin/dashboard`);
}

const overseasAdmin = (page: Page) => signIn(page, "overseas", "overseasadmin@edusphere.local");
const itAdmin = (page: Page) => signIn(page, "it", "itadmin@edusphere.local");

// The retired default password, built in two parts so the repo-wide "no ChangeMe@12345" grep gate
// (AC-19) stays clean while this spec can still prove the old default no longer logs in.
const RETIRED_DEFAULT = "Change" + "Me@12345";

test("a provisioned staff account has no default password and activates from its link", async ({ page }) => {
  await overseasAdmin(page);
  const email = `enh003-staff-${Date.now()}@example.local`;
  const created = await page.request.post("/api/v1/overseas-admin/school-staff", { data: { role: "academic_team", full_name: "ENH-003 Staff", email } });
  expect(created.status()).toBe(201);
  const body = await created.json();
  expect(JSON.stringify(body)).not.toContain("ChangeMe");
  expect(Object.keys(body).some((key) => key.toLowerCase().includes("password"))).toBe(false);

  await page.request.post("/api/v1/auth/logout");
  const denied = await page.request.post("/api/v1/auth/login", { data: { email, password: RETIRED_DEFAULT, division: "overseas" } });
  expect(denied.status()).toBe(401);

  await activateWithToken(page.request, body.development_welcome_token);
  await page.goto("/overseas/login");
  await page.fill("#login-email", email);
  await page.fill("#login-password", E2E_PASSWORD);
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/academic-team/dashboard");
});

test("the admin form reports the link outcome in a live region and never shows a password", async ({ page }) => {
  await overseasAdmin(page);
  await page.goto("/overseas/admin/school-staff");
  await page.selectOption("#staff-role", "career_counselor");
  await page.fill("#staff-name", "ENH-003 Form Staff");
  await page.fill("#staff-email", `enh003-form-${Date.now()}@example.local`);
  await page.getByRole("button", { name: /create/i }).last().click();
  const outcome = page.getByRole("status").filter({ hasText: /Account created for/ });
  await expect(outcome).toBeVisible();
  await expect(outcome).toContainText(/set-password link was emailed|email was not delivered/);
  await expect(page.getByText(/ChangeMe|default password/i)).toHaveCount(0);
});

test("Re-send supersedes the old link and the new one works", async ({ page }) => {
  await overseasAdmin(page);
  const email = `enh003-resend-${Date.now()}@example.local`;
  const created = await (await page.request.post("/api/v1/admin/users", { data: { role: "counselor", division: "overseas", email, full_name: "ENH-003 Resend" } })).json();
  const resent = await page.request.post(`/api/v1/admin/users/${created.id}/welcome-links`);
  expect(resent.status()).toBe(201);
  const fresh = await resent.json();

  // the cooldown (security review S4): a second Re-send right away is throttled and issues nothing
  const again = await page.request.post(`/api/v1/admin/users/${created.id}/welcome-links`);
  expect(again.status()).toBe(429);
  expect(Number(again.headers()["retry-after"])).toBeGreaterThan(0);

  const stale = await page.request.post("/api/v1/auth/reset-password", { data: { token: created.development_welcome_token, new_password: E2E_PASSWORD } });
  expect(stale.status()).toBe(400);
  await activateWithToken(page.request, fresh.development_welcome_token);
  const login = await page.request.post("/api/v1/auth/login", { data: { email, password: E2E_PASSWORD, division: "overseas" } });
  expect(login.status()).toBe(200);
});

test("an invalid link offers a real recovery link, and the page fits a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/overseas/reset-password?token=not-a-real-token");
  await page.fill("#reset-new-password", E2E_PASSWORD);
  await page.getByRole("button", { name: "Reset password" }).click();
  const alert = page.getByRole("alert");
  await expect(alert).toContainText("Reset token is invalid or expired");
  await expect(alert).toContainText("ask your administrator to re-send it");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await alert.getByRole("link", { name: "Request a new reset link" }).click();
  await page.waitForURL("**/overseas/forgot-password");
});

test("the users directory shows the setup status and Re-send works from the keyboard", async ({ page }) => {
  await itAdmin(page);
  const name = `ENH-003 Directory ${Date.now()}`;
  const created = await page.request.post("/api/v1/admin/users", { data: { role: "trainer", division: "it", email: `enh003-dir-${Date.now()}@example.local`, full_name: name } });
  expect(created.status()).toBe(201);

  await page.goto("/it/admin/users");
  const panel = page.locator(".action-card", { has: page.getByRole("heading", { name: "Manage users" }) });
  await panel.getByLabel("Search by name, email, or role").fill(name);
  const row = panel.locator("tr", { hasText: name });
  await expect(row).toContainText("Active");
  await expect(row.getByText("Awaiting setup")).toBeVisible();

  await panel.getByLabel("Account setup").selectOption("link_expired");
  await expect(row).toBeHidden();
  await panel.getByRole("button", { name: "Show all accounts" }).click();
  await expect(row).toBeVisible();

  const resend = row.getByRole("button", { name: `Re-send set-password link to ${name}` });
  await resend.focus();
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("status").filter({ hasText: `New link created for ${name}.` })).toBeVisible();
  await expect(resend).toBeFocused();
});

test("the expired-links panel is present on the admin dashboard and fits a phone", async ({ page }) => {
  await itAdmin(page);
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/it/admin/dashboard");
  const heading = page.getByRole("heading", { name: /Expired set-password links/ });
  await expect(heading).toBeVisible();
  const card = page.locator(".action-card", { has: heading });
  await expect(card.getByText(/No expired links\.|Link expired|Loading expired links/).first()).toBeVisible();
  const box = await card.boundingBox();
  expect(box && box.x >= 0 && box.x + box.width <= 375).toBe(true);
});

test("the reset page never leaks its token in a Referer", async ({ page }) => {
  const response = await page.goto("/overseas/reset-password?token=not-a-real-token");
  expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
});
```

Before running, confirm the staff-form submit label: `grep -n "<button" apps/web/components/AdminSchoolStaffPanel.tsx | tail -3`; adjust `{ name: /create/i }` if the real label differs.

- [ ] **Step 3: Run the new spec** (user's stack up) — from `apps/web`: `npx playwright test tests/e2e/enh-003-first-time-provisioning.spec.ts` → 7 passed.

- [ ] **Step 4: Migrate the existing specs.** Find every occurrence:

```bash
grep -rn "ChangeMe@12345" apps/web/tests/e2e
```

Two shapes exist. Import once per file: `import { E2E_PASSWORD, activateWithToken } from "./helpers/welcome";`

**Shape A — account created through the API** (e.g. `sch-008` creating staff with `page.request.post("/api/v1/overseas-admin/school-staff", { data: { role, full_name: email, email } })`): capture the response body, activate, and change the login password.

```ts
// before
const created = await page.request.post("/api/v1/overseas-admin/school-staff", { data: { role, full_name: email, email } });
// ... later ...
await page.fill("#login-password", "ChangeMe@12345");

// after
const created = await page.request.post("/api/v1/overseas-admin/school-staff", { data: { role, full_name: email, email } });
await activateWithToken(page.request, (await created.json()).development_welcome_token);
// ... later ...
await page.fill("#login-password", E2E_PASSWORD);
```

**Shape B — account created through the UI form** (e.g. `sch-team-management`'s `onboardSchoolWithFullTeam`, which fills `#school-name` … and clicks "Create school + seed Coordinator"): the UI never shows the token, so create through the API instead and keep one UI check of the form (already in the new spec).

```ts
// before
await page.goto("/overseas/admin/schools");
await page.fill("#school-name", `E2E SCH-Team School ${unique}`);
await page.fill("#school-coordinator-name", "E2E Coordinator");
await page.fill("#school-coordinator-email", coordinatorEmail);
await page.click('button:has-text("Create school + seed Coordinator")');
await expect(page.getByText(/School created\./)).toBeVisible();
// ... coordinator login with "ChangeMe@12345"

// after
const school = await page.request.post("/api/v1/overseas-admin/schools", { data: { name: `E2E SCH-Team School ${unique}`, coordinator_full_name: "E2E Coordinator", coordinator_email: coordinatorEmail } });
expect(school.status()).toBe(201);
await activateWithToken(page.request, (await school.json()).development_welcome_token);
// ... coordinator login with E2E_PASSWORD
```

Per-file worklist (occurrence counts; apply the matching shape, then run that spec alone before moving on):

| Spec | # | Spec | # |
|---|---|---|---|
| `sch-008-student-timeline.spec.ts` | 8 | `sch-team-management.spec.ts` | 2 |
| `sch-004-005-006-service-delivery.spec.ts` | 7 | `sch-reports.spec.ts` | 2 |
| `sch-roster-parent-invite.spec.ts` | 3 | `sch-007-parent-portal.spec.ts` | 2 |
| `sch-010-overseas-bridge.spec.ts` | 3 | `sch-003-school-onboarding.spec.ts` | 2 |
| `sch-009-test-prep-language.spec.ts` | 3 | `sch-001-school-portal-access.spec.ts` | 2 |
| `sch-011-entitlements.spec.ts` | 1 | `sch-002-bulk-roster-upload.spec.ts` | 1 |
| `enh-001-academic-year.spec.ts` | 1 | | |

Also update the stale comment in `sch-008-student-timeline.spec.ts` (~line 91-92, "carries that endpoint's own default (`ChangeMe@12345`)") to describe the welcome-link activation. Callers of `POST /admin/users` that pass `password: "Sup3r-Secret-Pass!"` (`adm-001`, `adm-003`, `adm-004`, `adm-007`, `adm-008`) now get `422`: replace each with `createAndActivate(page.request, "/api/v1/admin/users", { ...without password }, "Sup3r-Secret-Pass!")` (`request` in the specs that use the `request` fixture) and keep every later login as-is. `adm-001`'s row assertion `toContainText("Active")` still holds (the row now reads "Active Awaiting setup"). `sch-010`'s single call that relied on the default follows Shape A.

- [ ] **Step 5: Run each migrated spec, then the gate**

```bash
npx playwright test tests/e2e/sch-008-student-timeline.spec.ts   # repeat per file in the worklist and the adm-* specs above
grep -rn "ChangeMe@12345" apps/web && echo "STILL PRESENT" || echo "clean"
```

Expected: every spec passes and the grep prints `clean` (the new spec builds the retired string in two parts, so it does not trip the gate). RAID I-04/I-06 contention flakes may appear in full-suite runs; confirm any failing spec passes alone before treating it as a regression.

- [ ] **Step 6: Commit** (with approval): `git add apps/web/tests && git commit -m "test(enh-003): move e2e specs to welcome-link activation and cover the new flows" -m "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"`

---

### Task 11: Docs, graph, full verification

**Files:**
- Modify: `docs/architecture/API_CONTRACT.md` (lines ~50-51 auth rows, ~131 admin row, §12A school rows)
- Modify: `docs/architecture/DATA_MODEL.md`, `docs/architecture/SECURITY_CONTROLS.md`, `docs/quality/RTM.md`, `docs/ux/SCREEN_CATALOG.md`
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` (mark ENH-003 implemented)

- [ ] **Step 1: API contract** — in `API_CONTRACT.md`:
  - replace the `POST /auth/reset-password` row's note with: `Token single-use, hashed at rest. Forgot-password links expire in 30 minutes; admin-provisioned welcome links (DEC-SCOPE-019) in 72 hours and also set email_verified. Used/expired/superseded/unknown all return the same 400.`
  - extend the `GET/POST/PATCH /admin/users …` row: create rejects any `password` with 422 and returns `email_status`, `expires_at`; `GET` rows add `provisioning_status` and accept `?provisioning_status=pending_setup|link_expired`.
  - add rows (auth: admin, division-scoped): `POST /admin/users/{id}/welcome-links` (201; 404, 403, 409 — pending accounts only; not idempotent, supersedes the previous link) and note `expired_welcome_links` on `GET /admin/dashboard`.
  - in §12A note `POST /overseas-admin/schools` and `/overseas-admin/school-staff` reject `coordinator_password`/`password` (422) and return `email_status`, `expires_at`.
  - document the new `422` cases (malformed email on the three create routes; password over 128 characters on reset), `429` + `Retry-After` on `POST /admin/users/{id}/welcome-links`, and that any real change of `active` via `PATCH /admin/users/{id}` revokes open welcome links.
  - cite `DEC-SCOPE-019`/`ENH-003`, **not** `AC-nn`.
- [ ] **Step 2:** `DATA_MODEL.md` — find `password_reset_tokens` (`grep -n "password_reset_tokens" docs/architecture/DATA_MODEL.md`); add `purpose` (`reset|welcome`, default `reset`) and `superseded_at`. `SECURITY_CONTROLS.md` — under credential/auth controls add: no admin-known or default credentials; welcome links single-use, SHA-256 at rest, 72 h; raw token never stored or logged; dev token gated to development/test; welcome links refused for inactive accounts and revoked on any `active` change; 60-second Re-send cooldown; reset page excluded from Google Analytics and served with `Referrer-Policy: no-referrer`. Add a **deployment checklist** item: the API's `ENVIRONMENT` must be `production` outside local development — the API reads it from `.env` (code default and `.env.example` are `development`; the compose file's `production` default applies only to the *web* service). Otherwise responses carry `development_welcome_token`, and the pre-existing `forgot_password` returns `development_reset_token` to anonymous callers.
- [ ] **Step 3:** `RTM.md` — `grep -n "ENH-001" docs/quality/RTM.md`; mirror that row's format for an `ENH-003` row (evidence: `DEC-SCOPE-019`; tests: `test_enh_003_first_time_provisioning.py`, `enh-003-first-time-provisioning.spec.ts`, `welcomeLink.test.ts`; status **COMPLETE** only after Step 6 passes). `SCREEN_CATALOG.md` — add the expired-links panel (IT/Overseas dashboards), the directory's setup status/filter/Re-send, the Super Admin tile/"Setup" column, and the reset-page recovery hint; note the panels' loading/empty/error states.
- [ ] **Step 4:** `ENHANCEMENT_BACKLOG.md` — under ENH-003 add "Implemented <date>; see DEC-SCOPE-019 and the spec/plan."
- [ ] **Step 5: Refresh the graph** — `graphify update .` (AST only).
- [ ] **Step 6: Final verification (user's stack up)**

```bash
# backend: ONE full regression, because admin.py and auth.py are shared
cd apps/api && python -m pytest -q
# frontend
cd ../web && npx tsc --noEmit && npx vitest run
npx playwright test tests/e2e/enh-003-first-time-provisioning.spec.ts tests/e2e/auth-001-login.spec.ts tests/e2e/adm-001-admin-crud.spec.ts tests/e2e/adm-004-directory.spec.ts tests/e2e/adm-014-super-admin-console.spec.ts
# gates
grep -rn "ChangeMe@12345" apps docs/architecture docs/ux | grep -v "^docs/decisions\|^docs/delivery" && echo "STILL PRESENT" || echo "clean"
git diff --stat
```

Expected: pytest passes with no failure outside the 17 pre-existing ones recorded in `docs/quality/RTM.md`'s SCH addendum (compare against the Task 0 baseline and that list, do not assume); vitest and tsc clean; the listed Playwright specs pass; grep prints `clean` for code (the string may remain in the decision register/backlog as history); diff touches only files named in this plan.

- [ ] **Step 7: Report** to the user: results per suite (actual counts, actual failures), anything skipped, the pre-existing forgot-password `development_reset_token` exposure whenever the API's `ENVIRONMENT` is left at `development` (report only — not changed here), the `NEEDS_CONFIRMATION` items still open (read-only legacy default-password audit script; `overseas_admin` can Re-send pending-but-unexpired accounts only through an API caller until the link expires, because the directory panel is gated by `isAdmin` = `it_admin`/`super_admin`), and offer the commit(s).

---

## Self-review (against the spec)

- **Spec coverage:** §4 data model → Task 1. §5 service + mailer → Tasks 2–3. §6.1 create routes/`422`/`IntegrityError` → Task 5. §6.2 atomic consume + `email_verified` → Task 4. §6.3 Re-send → Task 6. §6.4 status/filter/dashboard → Task 6. §8 frontend → Tasks 7–9. §9 AC-01…20 → AC-01/02/03/04/05/06/16/20 in Task 5 (+3), 07/08/09 Task 4, 10/11 Task 6, 12/13/14 Tasks 3+6, 15 Tasks 5/11, 17 Task 1, 18/19 Tasks 7–10. §10 test plan → Tasks 1–10; §12 docs → Task 11.
- **Placeholders:** none. Task 10 Step 4 is a mechanical migration across 13 files driven by two fully-shown patterns, an exact worklist and a `grep` gate, because reading and rewriting all 37 call sites in the plan would only restate the same two transformations.
- **Type/name consistency:** `issue_welcome_token(db, *, user, issued_by)`, `deliver_welcome_link(db, *, user, issued, issued_by)`, `provisioning_statuses`, `user_ids_with_status(db, actor, status)`, `IssuedWelcome(raw, expires_at, token_id)`, `send_welcome_email(...)`, `welcomeLinkFeedback(subject, data)`, `requestWelcomeLink(userId)`, `toneClass`, `refocus(id)` are used identically in every task. One intentional deviation from the spec, noted in Task 3: `user_ids_with_status` generalizes the spec's `expired_welcome_link_user_ids`, and `issue_welcome_token` takes `issued_by` for its audit row.
- **Security review (2026-09-19, user-approved):** S1 → Task 7 steps 8a/8b + Task 10 Referrer test; S2 → Tasks 4 and 6 (inactive check, revoke-on-`active`-change) and the latest-token status rule in Task 3; S3 → Task 2 (mailer inside `try`), Task 3 (`return_exceptions`) and Task 5 (`_valid_email`); S4 → Tasks 3 and 6 (60-second cooldown) and Task 10; S5 → Task 3 (`_redact`); S8 → Task 4 (128-character cap); deployment note → Task 11. Spec §13 and `AC-21`…`AC-29` carry the criteria.
