# ENH-014 Multi-Channel Notifications (WhatsApp / SMS), Slice 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Users opt in to WhatsApp/SMS; every trigger that emails today also delivers on the recipient's opted-in channels through Twilio, with all deliveries (email included) queued after commit and sent by Celery.

**Architecture:** A new `app/notifications/` package: `phone.py` (E.164 normalisation), `dispatch.py` (writes `queued` delivery rows; a SQLAlchemy `after_commit` listener publishes them to Celery), `twilio.py` (Messages API over `httpx`), `delivery.py` (worker: atomic claim → send → record → retry; stale sweeper). Three existing helpers (`_notify_parent`, `_notify_user`, `inbound._notify_student`) swap their inline send for `queue_deliveries`, so the ~35 trigger sites are untouched. Preferences live in a new `notification_preferences` table behind `GET/PUT /api/v1/account/notification-preferences`, edited from `/account/profile`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, async SQLAlchemy 2, Alembic, PostgreSQL, Celery + Redis, httpx; Next.js (App Router) + React + TypeScript, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-30-enh-014-notification-channels-design.md` (decision: `DEC-NOT-001` 2026-09-30 extension, D1–D14). Read both before starting any task.

## Global Constraints

- No new runtime or dev dependencies (Python or npm). Twilio is called with the existing `httpx`; no Twilio SDK, no `phonenumbers`, no axe package.
- Additive migration only: no existing row or column is modified; `downgrade()` removes exactly what `upgrade()` adds.
- Existing API contracts unchanged except where the spec says so (§5.3): `PATCH /auth/me` untouched; `/communications/notify` keeps its shape (per-channel statuses become `"queued"`).
- Password reset, set-password, invite and welcome emails stay inline and email-only — `auth.py` forgot-password, `services/mailer.py` and `services/provisioning.py` are not modified (D7).
- In-app-only triggers stay in-app-only: `communications.send_message`, `communications.create_live_session`, the transfer notices in `school_transfers.py:468-549`.
- Logs carry delivery id, channel, status, attempt and error type only — never a phone number, email address, message title/body, or the Twilio token.
- Snake_case JSON; FastAPI `{"detail": ...}` errors; Pydantic models on routes; SQLAlchemy constructs only (no raw SQL strings).
- Retry countdowns 60 s / 300 s / 1500 s after failed attempts 1 / 2 / 3; at most 4 attempts in total (D11).
- Default phone country India: 10-digit numbers starting 6–9 become `+91…` (D14).
- Consent copy version string: `enh014-v1`.
- Backend tests are not transaction-isolated (shared DB, rows left behind): assert on rows the test created, never on global counts.
- Run backend tests with `docker compose exec api python -m pytest -q <file>` after `docker compose build api && docker compose up -d --force-recreate api worker beat` (no source bind mounts — see `AGENTS.md`), or locally from `apps/api` with the venv. Frontend from `apps/web`: `npm test -- <file>`, `npm run typecheck`, `npm run lint`.
- Every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. A phone typed with non-ASCII digits (e.g. Devanagari `९८७६५४३२१०`) or only spaces must be treated as invalid, not "normalised" — Python's `str.isdigit()` accepts those digits. Pinned in Task 2 (`test_non_ascii_digits_and_blank_are_invalid`).
2. A user who opted in and later cleared their phone must still be able to turn WhatsApp/SMS **off**; only a false→true change needs a valid phone. Pinned in Task 3 (`test_turning_off_is_allowed_without_a_phone`) and Task 10 (`keeps a checked channel enabled so it can be turned off without a phone`).
3. A notification with no `action_url` (e.g. the ENH-023 admin notice) must still produce a valid WhatsApp template call — Twilio rejects an empty variable — so the link falls back to the portal home. Pinned in Task 5 (`test_missing_or_offsite_link_falls_back_to_portal_home`).
4. A recipient deactivated between queueing and sending gets `skipped`, not a message. Pinned in Task 6 (`test_inactive_recipient_is_skipped`).
5. A school name, title or body with non-Latin text or newlines (Hindi names, multi-line bodies) must go out as one clean line and never crash the capping. Pinned in Task 5 (`test_variables_are_single_line_and_capped`).

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `apps/api/app/core/config.py` (modify) | Twilio settings | 1 |
| `apps/api/app/models.py` (modify) | `NotificationPreference`; `NotificationDelivery.context` + index | 1 |
| `apps/api/alembic/versions/0046_notification_channels.py` (create) | additive migration | 1 |
| `docker-compose.ci.yml` (modify) | empty `TWILIO_*` values | 1 |
| `apps/api/tests/enh014_helpers.py` (create) | `make_user`, `login`, `set_prefs`, `drain` | 1, 4 |
| `apps/api/app/notifications/phone.py` (create) | `normalise_phone` | 2 |
| `apps/api/app/schemas.py` (modify) | `NotificationPreferencesIn/Out` | 3 |
| `apps/api/app/api/account.py` (modify) | preference endpoints; export includes preferences | 3, 9 |
| `apps/api/app/notifications/dispatch.py` (create) | `queue_deliveries`, after-commit publish, `enqueue` | 4 |
| `apps/api/tests/conftest.py` (modify) | autouse `enqueued` capture fixture | 4 |
| `apps/api/app/notifications/twilio.py` (create) | Twilio Messages API adapter | 5 |
| `apps/api/app/notifications/delivery.py` (create) | `deliver`, `sweep_stale_deliveries` | 6, 7 |
| `apps/api/app/worker.py` (modify) | Celery tasks + beat schedule | 6, 7 |
| `apps/api/app/api/schools.py`, `workflows.py`, `inbound.py`, `communications.py` (modify) | route triggers through `queue_deliveries` | 8 |
| `apps/api/app/api/admin.py` (modify) | erasure deletes preferences | 9 |
| `apps/web/lib/types.ts` (modify) | `NotificationPreferences` | 10 |
| `apps/web/components/NotificationPreferencesForm.tsx` (create) | the preferences form | 10 |
| `apps/web/app/account/profile/page.tsx`, `components/ProfileForm.tsx` (modify) | page section; refresh after phone save | 11 |
| `apps/web/tests/e2e/enh-014-notification-preferences.spec.ts` (create) | E2E | 12 |
| docs (modify) | contracts, catalogue, backlog status | 13 |

---

### Task 1: Settings, models, migration, test helpers

**Files:**
- Modify: `apps/api/app/core/config.py` (after `email_webhook_url`, line 24)
- Modify: `apps/api/app/models.py:711-720` (`NotificationDelivery`) and add `NotificationPreference` after it
- Create: `apps/api/alembic/versions/0046_notification_channels.py`
- Modify: `docker-compose.ci.yml` (the `x-ci-api-environment` block)
- Create: `apps/api/tests/enh014_helpers.py`
- Test: `apps/api/tests/test_enh_014_models.py`

**Interfaces:**
- Produces: `NotificationPreference(user_id, whatsapp_opt_in, sms_opt_in, whatsapp_opted_in_at, sms_opted_in_at)`; `NotificationDelivery.context: dict | None`; settings `twilio_account_sid`, `twilio_auth_token`, `twilio_whatsapp_from`, `twilio_sms_from`, `twilio_whatsapp_content_sid` (all `str | None`); helpers `make_user(db, *, role="school_parent", division="overseas", phone=None, active=True) -> User`, `login(client, email, division="overseas")`, `set_prefs(db, user, *, whatsapp=False, sms=False)`, `PASSWORD`.

- [ ] **Step 1: Write the helpers and the failing test**

`apps/api/tests/enh014_helpers.py`:

```python
"""ENH-014 test helpers (same precedent as enh005_helpers.py)."""

import uuid
from datetime import UTC, datetime

from app.core.security import hash_password
from app.models import NotificationPreference, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"


async def make_user(db, *, role: str = "school_parent", division: str = "overseas", phone: str | None = None, active: bool = True) -> User:
    user = User(
        email=f"enh014-{role}-{uuid.uuid4().hex[:8]}@example.local",
        password_hash=hash_password(PASSWORD),
        full_name="Enh Fourteen",
        role=role,
        division=division,
        active=active,
        phone=phone,
    )
    db.add(user)
    await db.flush()
    db.add(UserRoleAssignment(user_id=user.id, division=division, role=role, is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    await db.commit()
    return user


async def login(client, email: str, division: str = "overseas") -> None:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": division})
    assert response.status_code == 200, response.text


async def set_prefs(db, user: User, *, whatsapp: bool = False, sms: bool = False) -> None:
    now = datetime.now(UTC)
    db.add(NotificationPreference(user_id=user.id, whatsapp_opt_in=whatsapp, sms_opt_in=sms, whatsapp_opted_in_at=now if whatsapp else None, sms_opted_in_at=now if sms else None))
    await db.commit()
```

`apps/api/tests/test_enh_014_models.py`:

```python
"""ENH-014 Task 1 -- the preference row and the delivery render context (spec §4)."""

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models import Notification, NotificationDelivery, NotificationPreference
from tests.enh014_helpers import make_user


@pytest.mark.asyncio
async def test_preference_row_defaults_off(db_session):
    user = await make_user(db_session)
    db_session.add(NotificationPreference(user_id=user.id))
    await db_session.commit()
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    assert (pref.whatsapp_opt_in, pref.sms_opt_in, pref.whatsapp_opted_in_at, pref.sms_opted_in_at) == (False, False, None, None)


@pytest.mark.asyncio
async def test_delivery_keeps_its_render_context(db_session):
    user = await make_user(db_session)
    note = Notification(user_id=user.id, title="t", body="b")
    db_session.add(note)
    await db_session.flush()
    row = NotificationDelivery(notification_id=note.id, channel="email", status="queued", attempt_count=0, context={"kind": "school", "school_name": "Green Valley"})
    db_session.add(row)
    await db_session.commit()
    await db_session.refresh(row)
    assert row.context == {"kind": "school", "school_name": "Green Valley"}


@pytest.mark.asyncio
async def test_sweeper_index_exists(db_session):
    names = await db_session.run_sync(lambda s: {i["name"] for i in sa_inspect(s.connection()).get_indexes("notification_deliveries")})
    assert "ix_notification_deliveries_status_updated_at" in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_models.py`
Expected: FAIL — `ImportError: cannot import name 'NotificationPreference'`.

- [ ] **Step 3: Implement settings, models and migration**

`apps/api/app/core/config.py`, directly after `email_webhook_url: str | None = None`:

```python
    # ENH-014 (DEC-NOT-001, 2026-09-30 extension): Twilio for WhatsApp and SMS. Unset or empty means "not configured";
    # the generic whatsapp_webhook_url / sms_webhook_url above keep working in that case (AC14).
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_whatsapp_from: str | None = None
    twilio_sms_from: str | None = None
    twilio_whatsapp_content_sid: str | None = None
```

`apps/api/app/models.py` — replace the `NotificationDelivery` class and add `NotificationPreference` after it (add `Index` to the existing `from sqlalchemy import ...` line if it is not already imported; `false` too):

```python
class NotificationDelivery(Base, TimestampMixin):
    __tablename__ = "notification_deliveries"
    # ENH-014: the stale-delivery sweeper filters on (status, updated_at).
    __table_args__ = (Index("ix_notification_deliveries_status_updated_at", "status", "updated_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("notifications.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    provider_reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ENH-014: what the worker needs to render the email exactly as the old inline path did --
    # {"kind": "school", "school_name": ...} for the School path, null for the generic path and every pre-ENH-014 row.
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class NotificationPreference(Base, TimestampMixin):
    """ENH-014 (DEC-NOT-001 2026-09-30, D4): opt-in to WhatsApp and SMS. No row means both off; email and in-app are
    always on and are not stored. The *_opted_in_at timestamps are the consent evidence (with the audit log)."""

    __tablename__ = "notification_preferences"
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    sms_opt_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    whatsapp_opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sms_opted_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`apps/api/alembic/versions/0046_notification_channels.py`:

```python
"""ENH-014 -- notification channel preferences and the delivery render context.

Revision ID: 0046_notification_channels
Revises: 0045_psychometric_result_fields

docs/superpowers/specs/2026-09-30-enh-014-notification-channels-design.md §4 (DEC-NOT-001, 2026-09-30 extension).
Additive only: one new table, one nullable column, one index. No existing row is touched. `downgrade()` drops exactly
these three. Guarded like 0045: on a fresh database 0001_initial's create_all() has already built them from the models.
If another branch merges a 0046 first, re-chain this one on top of it (precedent: 0045's note).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0046_notification_channels"
down_revision = "0045_psychometric_result_fields"
branch_labels = None
depends_on = None

TABLE = "notification_preferences"
DELIVERIES = "notification_deliveries"
INDEX = "ix_notification_deliveries_status_updated_at"


def upgrade() -> None:
    offline = op.get_context().as_sql
    inspector = None if offline else sa.inspect(op.get_bind())
    if offline or TABLE not in inspector.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("whatsapp_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("sms_opt_in", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("whatsapp_opted_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("sms_opted_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if offline or "context" not in {c["name"] for c in inspector.get_columns(DELIVERIES)}:
        op.add_column(DELIVERIES, sa.Column("context", postgresql.JSON(), nullable=True))
    if offline or INDEX not in {i["name"] for i in inspector.get_indexes(DELIVERIES)}:
        op.create_index(INDEX, DELIVERIES, ["status", "updated_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=DELIVERIES)
    op.drop_column(DELIVERIES, "context")
    op.drop_table(TABLE)
```

`docker-compose.ci.yml`, after `EMAIL_WEBHOOK_URL: ""`:

```yaml
  TWILIO_ACCOUNT_SID: ""
  TWILIO_AUTH_TOKEN: ""
  TWILIO_WHATSAPP_FROM: ""
  TWILIO_SMS_FROM: ""
  TWILIO_WHATSAPP_CONTENT_SID: ""
```

- [ ] **Step 4: Migrate and verify the migration round-trips**

Run: `docker compose build api && docker compose up -d --force-recreate api worker beat` (the API entrypoint runs `alembic upgrade head`), then
`docker compose exec api alembic downgrade 0045_psychometric_result_fields && docker compose exec api alembic upgrade head`
Expected: both commands exit 0; `docker compose exec api alembic current` prints `0046_notification_channels (head)`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `docker compose exec api python -m pytest -q tests/test_enh_014_models.py`
Expected: `3 passed`.

- [ ] **Step 6: Lint and commit**

Run: `cd apps/api && python -m ruff check . && python -m mypy app` — expected: no errors.

```bash
git add apps/api/app/core/config.py apps/api/app/models.py apps/api/alembic/versions/0046_notification_channels.py docker-compose.ci.yml apps/api/tests/enh014_helpers.py apps/api/tests/test_enh_014_models.py
git commit -m "feat(enh-014): notification preferences table, delivery context, Twilio settings"
```

---

### Task 2: Phone normalisation

**Files:**
- Create: `apps/api/app/notifications/phone.py`
- Test: `apps/api/tests/test_enh_014_phone.py`

**Interfaces:**
- Produces: `normalise_phone(raw: str | None) -> str | None` — E.164 (`+` and 8–15 ASCII digits) or `None`.

- [ ] **Step 1: Write the failing test**

```python
"""ENH-014 Task 2 -- E.164 normalisation, default country India (spec §6.3, D14). No I/O: plain unit tests."""

import pytest

from app.notifications.phone import normalise_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("+91 98765 43210", "+919876543210"),
        ("+44 (20) 7946-0958", "+442079460958"),
        ("98765 43210", "+919876543210"),
        ("098765-43210", "+919876543210"),
        ("91 9876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("+1.415.555.2671", "+14155552671"),
    ],
)
def test_valid_numbers_normalise_to_e164(raw, expected):
    assert normalise_phone(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", "12345", "5876543210", "+12", "+1234567890123456", "call me", "+91 98765 4321x", "++919876543210"])
def test_invalid_numbers_return_none(raw):
    assert normalise_phone(raw) is None


def test_non_ascii_digits_and_blank_are_invalid():
    # Review Focus 1: str.isdigit() accepts Devanagari digits; they must not pass as a number.
    assert normalise_phone("९८७६५४३२१०") is None
    assert normalise_phone("+९१९८७६५४३२१०") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_phone.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications.phone'`.

- [ ] **Step 3: Implement**

`apps/api/app/notifications/phone.py`:

```python
"""ENH-014 (spec §6.3, D14): normalise a stored phone number to E.164 for Twilio. Format check only -- no OTP.

ASCII digits only ([0-9], never \\d or str.isdigit(), which accept e.g. Devanagari digits). Default country India."""

import re

_SEPARATORS = re.compile(r"[\s\-().]")
_INTERNATIONAL = re.compile(r"\+[0-9]{8,15}")
_INDIAN_MOBILE = re.compile(r"(?:0|91)?([6-9][0-9]{9})")


def normalise_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    compact = _SEPARATORS.sub("", raw)
    if _INTERNATIONAL.fullmatch(compact):
        return compact
    match = _INDIAN_MOBILE.fullmatch(compact)
    return f"+91{match.group(1)}" if match else None
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_phone.py`
Expected: all pass (19 cases).

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/notifications/phone.py apps/api/tests/test_enh_014_phone.py
git commit -m "feat(enh-014): E.164 phone normalisation with India default"
```

---

### Task 3: Preference endpoints

**Files:**
- Modify: `apps/api/app/schemas.py` (add `ConfigDict` to the pydantic import on line 8; add the two models after `ProfileUpdate`)
- Modify: `apps/api/app/api/account.py` (imports; two routes after `_retention_hold_reason`)
- Test: `apps/api/tests/test_enh_014_preferences.py`

**Interfaces:**
- Consumes: `normalise_phone` (Task 2); `NotificationPreference` (Task 1).
- Produces: `GET/PUT /api/v1/account/notification-preferences` → `{"whatsapp": bool, "sms": bool, "phone_valid": bool}`; audit action `notification_preference.update`; constant `CONSENT_TEXT_VERSION = "enh014-v1"` in `account.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-014 Task 3 -- GET/PUT /account/notification-preferences (spec §5.1-5.2; AC01-AC03, AC15)."""

import asyncio

import pytest
from sqlalchemy import select

from app.models import AuditLog, NotificationPreference
from tests.enh014_helpers import login, make_user, set_prefs

URL = "/api/v1/account/notification-preferences"


@pytest.mark.asyncio
async def test_both_routes_require_a_session(client):
    assert (await client.get(URL)).status_code == 401
    assert (await client.put(URL, json={"whatsapp": False, "sms": False})).status_code == 401


@pytest.mark.asyncio
async def test_defaults_are_off_and_phone_validity_is_reported(client, db_session):
    user = await make_user(db_session, phone="98765 43210")
    await login(client, user.email)
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json() == {"whatsapp": False, "sms": False, "phone_valid": True}


@pytest.mark.asyncio
async def test_turning_on_without_a_valid_phone_is_422_and_writes_nothing(client, db_session):
    user = await make_user(db_session, phone="12345")
    await login(client, user.email)
    response = await client.put(URL, json={"whatsapp": True, "sms": False})
    assert response.status_code == 422
    assert response.json() == {"detail": "Add a valid mobile number to your profile first"}
    assert await db_session.get(NotificationPreference, user.id) is None


@pytest.mark.asyncio
async def test_turning_off_is_allowed_without_a_phone(client, db_session):
    # Review Focus 2: opted in, then cleared the phone -- turning channels off must still work.
    user = await make_user(db_session, phone=None)
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    await login(client, user.email)
    response = await client.put(URL, json={"whatsapp": True, "sms": False})  # WhatsApp unchanged, SMS off
    assert response.status_code == 200, response.text
    assert response.json() == {"whatsapp": True, "sms": False, "phone_valid": False}


@pytest.mark.asyncio
async def test_opt_in_and_out_set_and_clear_timestamps_and_audit_once(client, db_session):
    user = await make_user(db_session, phone="+91 98765 43210")
    await login(client, user.email)
    on = await client.put(URL, json={"whatsapp": True, "sms": False})
    assert on.status_code == 200 and on.json() == {"whatsapp": True, "sms": False, "phone_valid": True}
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    first_opt_in = pref.whatsapp_opted_in_at
    assert first_opt_in is not None and pref.sms_opted_in_at is None

    again = await client.put(URL, json={"whatsapp": True, "sms": False})  # no change: timestamp kept, no audit
    assert again.status_code == 200
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    assert pref.whatsapp_opted_in_at == first_opt_in

    off = await client.put(URL, json={"whatsapp": False, "sms": False})
    assert off.status_code == 200
    pref = await db_session.get(NotificationPreference, user.id, populate_existing=True)
    assert pref.whatsapp_opt_in is False and pref.whatsapp_opted_in_at is None

    audits = (await db_session.scalars(select(AuditLog).where(AuditLog.user_id == user.id, AuditLog.action == "notification_preference.update").order_by(AuditLog.created_at))).all()
    assert [a.metadata_json for a in audits] == [
        {"before": {"whatsapp": False, "sms": False}, "after": {"whatsapp": True, "sms": False}, "consent_text": "enh014-v1"},
        {"before": {"whatsapp": True, "sms": False}, "after": {"whatsapp": False, "sms": False}, "consent_text": "enh014-v1"},
    ]
    assert all("98765" not in str(a.metadata_json) for a in audits)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"whatsapp": "yes", "sms": False}, {"whatsapp": 1, "sms": False}, {"whatsapp": True}, {"whatsapp": False, "sms": False, "user_id": "x"}, {"whatsapp": False, "sms": False, "whatsapp_opted_in_at": "2020-01-01T00:00:00Z"}])
async def test_only_two_strict_booleans_are_accepted(client, db_session, body):
    user = await make_user(db_session, phone="9876543210")
    await login(client, user.email)
    assert (await client.put(URL, json=body)).status_code == 422
    assert await db_session.get(NotificationPreference, user.id) is None


@pytest.mark.asyncio
async def test_a_user_changes_only_their_own_row(client, db_session):
    other = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, other, whatsapp=True)
    me = await make_user(db_session, phone="9876543211")
    await login(client, me.email)
    assert (await client.put(URL, json={"whatsapp": False, "sms": True})).status_code == 200
    theirs = await db_session.get(NotificationPreference, other.id, populate_existing=True)
    assert (theirs.whatsapp_opt_in, theirs.sms_opt_in) == (True, False)


@pytest.mark.asyncio
async def test_concurrent_saves_leave_exactly_one_row(client, db_session):
    user = await make_user(db_session, phone="9876543210")
    await login(client, user.email)
    responses = await asyncio.gather(*(client.put(URL, json={"whatsapp": i % 2 == 0, "sms": True}) for i in range(6)))
    assert all(r.status_code == 200 for r in responses)
    rows = (await db_session.scalars(select(NotificationPreference).where(NotificationPreference.user_id == user.id))).all()
    assert len(rows) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_preferences.py`
Expected: FAIL — GET returns 404 (route missing).

- [ ] **Step 3: Implement schemas and routes**

`apps/api/app/schemas.py` — add `ConfigDict` to the `from pydantic import ...` line, then after `ProfileUpdate`:

```python
class NotificationPreferencesIn(BaseModel):
    """ENH-014 (spec §5.2): the only two writable values. Strict booleans; any other field is a 422 (AC15)."""

    model_config = ConfigDict(extra="forbid")
    whatsapp: StrictBool
    sms: StrictBool


class NotificationPreferencesOut(BaseModel):
    whatsapp: bool
    sms: bool
    phone_valid: bool
```

`apps/api/app/api/account.py` — imports:

```python
from sqlalchemy.dialects.postgresql import insert

from app.models import AuditLog, Certificate, ConsentRecord, DataSubjectRequest, Enrollment, NotificationPreference, Payment, User, UserRoleAssignment
from app.notifications.phone import normalise_phone
from app.schemas import NotificationPreferencesIn, NotificationPreferencesOut
```

Routes (after `_retention_hold_reason`):

```python
# --- ENH-014: notification channel preferences (spec §5.1-5.2) ------------------------------------------------------
# Self-only: the user always comes from the session and there is no id in the path, so no admin or other user can set
# anyone's consent (D4). PUT + JSON under the SameSite=Lax session cookie is not sendable by a cross-site form.
CONSENT_TEXT_VERSION = "enh014-v1"


def _preferences_out(pref: NotificationPreference | None, user: User) -> NotificationPreferencesOut:
    return NotificationPreferencesOut(whatsapp=bool(pref and pref.whatsapp_opt_in), sms=bool(pref and pref.sms_opt_in), phone_valid=normalise_phone(user.phone) is not None)


@router.get("/notification-preferences", response_model=NotificationPreferencesOut)
async def get_notification_preferences(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return _preferences_out(await db.get(NotificationPreference, user.id), user)


@router.put("/notification-preferences", response_model=NotificationPreferencesOut)
async def put_notification_preferences(payload: NotificationPreferencesIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current = await db.get(NotificationPreference, user.id)
    before = {"whatsapp": bool(current and current.whatsapp_opt_in), "sms": bool(current and current.sms_opt_in)}
    after = {"whatsapp": payload.whatsapp, "sms": payload.sms}
    # Only a false->true change needs a number: a user whose phone was cleared can still turn channels off.
    if any(after[c] and not before[c] for c in after) and normalise_phone(user.phone) is None:
        raise HTTPException(422, "Add a valid mobile number to your profile first")
    now = datetime.now(UTC)

    def since(channel: str, previous: datetime | None) -> datetime | None:
        if not after[channel]:
            return None
        return previous if before[channel] and previous else now

    values = {
        "whatsapp_opt_in": after["whatsapp"],
        "sms_opt_in": after["sms"],
        "whatsapp_opted_in_at": since("whatsapp", current.whatsapp_opted_in_at if current else None),
        "sms_opted_in_at": since("sms", current.sms_opted_in_at if current else None),
    }
    await db.execute(insert(NotificationPreference).values(user_id=user.id, **values).on_conflict_do_update(index_elements=[NotificationPreference.user_id], set_={**values, "updated_at": now}))
    if after != before:
        db.add(AuditLog(user_id=user.id, action="notification_preference.update", entity_type="user", entity_id=str(user.id), metadata_json={"before": before, "after": after, "consent_text": CONSENT_TEXT_VERSION}))
    await db.commit()
    return _preferences_out(await db.get(NotificationPreference, user.id, populate_existing=True), user)
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_preferences.py`
Expected: all pass. If `test_concurrent_saves_leave_exactly_one_row` shows audit duplicates that is acceptable (last-write-wins, spec §5.2); the assertion is on row count only.

- [ ] **Step 5: Lint and commit**

Run: `python -m ruff check . && python -m mypy app`

```bash
git add apps/api/app/schemas.py apps/api/app/api/account.py apps/api/tests/test_enh_014_preferences.py
git commit -m "feat(enh-014): self-only notification preference endpoints with audited opt-in"
```

---

### Task 4: Dispatch — queue rows, publish after commit

**Files:**
- Create: `apps/api/app/notifications/dispatch.py`
- Modify: `apps/api/tests/conftest.py` (append the `enqueued` fixture)
- Modify: `apps/api/tests/enh014_helpers.py` (append `drain`)
- Test: `apps/api/tests/test_enh_014_dispatch.py`

**Interfaces:**
- Consumes: `NotificationPreference`, `NotificationDelivery.context` (Task 1).
- Produces:
  - `async queue_deliveries(db: AsyncSession, notification: Notification, recipient: User, *, context: dict | None = None, channels: list[str] | None = None) -> list[NotificationDelivery]`
  - `enqueue(delivery_id: UUID | str, countdown: int = 0) -> None` (never raises)
  - `_publish(delivery_id: str, countdown: int) -> None` (the only function that touches Celery; tests replace it)
  - fixture `enqueued: list[tuple[str, int]]`; helper `async drain(enqueued, limit=50) -> None` (uses `deliver` from Task 6 — the helper is added now, first used in Task 6).

- [ ] **Step 1: Add the capture fixture and write the failing tests**

Append to `apps/api/tests/conftest.py`:

```python
@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    """ENH-014: no Redis in tests. Every delivery published after a commit is captured here as (delivery_id, countdown);
    `tests.enh014_helpers.drain` sends them in-process."""
    from app.notifications import dispatch

    captured: list[tuple[str, int]] = []
    monkeypatch.setattr(dispatch, "_publish", lambda delivery_id, countdown: captured.append((delivery_id, countdown)))
    return captured
```

Append to `apps/api/tests/enh014_helpers.py`:

```python
async def drain(enqueued: list, limit: int = 50) -> None:
    """Run every captured delivery (including re-enqueued retries, countdown ignored) until the queue is empty."""
    from uuid import UUID

    from app.notifications.delivery import deliver

    for _ in range(limit):
        if not enqueued:
            return
        delivery_id, _countdown = enqueued.pop(0)
        await deliver(UUID(delivery_id))
    raise AssertionError("delivery queue did not drain")
```

`apps/api/tests/test_enh_014_dispatch.py`:

```python
"""ENH-014 Task 4 -- queue_deliveries and the after-commit publish (spec §6.1; AC04, AC05)."""

import pytest
from sqlalchemy import select

from app.models import Notification, NotificationDelivery
from app.notifications import dispatch
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user, set_prefs


async def _notice(db, user) -> Notification:
    note = Notification(user_id=user.id, title="Result published", body="Term 1 Maths is available.", action_url="/school/parent/dashboard")
    db.add(note)
    await db.flush()
    return note


async def _rows(db, note) -> list[NotificationDelivery]:
    return list((await db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note.id).order_by(NotificationDelivery.channel))).all())


@pytest.mark.asyncio
async def test_without_opt_in_only_email_is_queued(db_session, enqueued):
    user = await make_user(db_session, phone="9876543210")
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user, context={"kind": "school", "school_name": "Green Valley"})
    await db_session.commit()
    [row] = await _rows(db_session, note)
    assert (row.channel, row.status, row.attempt_count, row.context) == ("email", "queued", 0, {"kind": "school", "school_name": "Green Valley"})
    assert enqueued == [(str(row.id), 0)]


@pytest.mark.asyncio
async def test_opted_in_channels_are_queued_alongside_email(db_session, enqueued):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    await db_session.commit()
    assert [r.channel for r in await _rows(db_session, note)] == ["email", "sms", "whatsapp"]
    assert len(enqueued) == 3


@pytest.mark.asyncio
async def test_explicit_channels_never_bypass_opt_in(db_session, enqueued):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user, channels=["email", "whatsapp", "sms", "fax"])
    await db_session.commit()
    assert [r.channel for r in await _rows(db_session, note)] == ["email", "sms"]


@pytest.mark.asyncio
async def test_publish_happens_only_after_commit(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    assert enqueued == []  # flushed, not committed: nothing published yet
    await db_session.commit()
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_a_rolled_back_write_queues_and_publishes_nothing(db_session, enqueued):
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    note_id = note.id
    await queue_deliveries(db_session, note, user)
    await db_session.rollback()
    await db_session.commit()  # a later, unrelated commit must not publish the discarded ids
    assert enqueued == []
    assert (await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id == note_id))).all() == []


@pytest.mark.asyncio
async def test_a_broker_failure_never_fails_the_commit(db_session, enqueued, monkeypatch):
    def broken(delivery_id, countdown):
        raise ConnectionError("redis down")

    monkeypatch.setattr(dispatch, "_publish", broken)
    user = await make_user(db_session)
    note = await _notice(db_session, user)
    await queue_deliveries(db_session, note, user)
    await db_session.commit()  # must not raise
    [row] = await _rows(db_session, note)
    assert row.status == "queued"  # left for the sweeper (Task 7)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_dispatch.py`
Expected: ERROR at setup — `ModuleNotFoundError: No module named 'app.notifications.dispatch'` (the autouse fixture imports it; every test in the suite errors until Step 3, so do Step 3 immediately).

- [ ] **Step 3: Implement**

`apps/api/app/notifications/dispatch.py`:

```python
"""ENH-014 (spec §6.1): queue a notification's deliveries; publish them to Celery only after the business write commits.

`queue_deliveries` writes one `queued` NotificationDelivery per allowed channel (email always; WhatsApp/SMS only when the
recipient opted in -- D4) and remembers the ids on the session. The `after_commit` listener publishes them; a rollback
discards them, so a rolled-back write never sends anything and the worker never looks for an uncommitted row. A delivery
inside a rolled-back SAVEPOINT stays in the list; the worker's claim then finds no row and exits, which is harmless."""

import logging
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models import Notification, NotificationDelivery, NotificationPreference, User

logger = logging.getLogger(__name__)

PENDING_KEY = "enh014_pending_deliveries"


async def queue_deliveries(db: AsyncSession, notification: Notification, recipient: User, *, context: dict | None = None, channels: list[str] | None = None) -> list[NotificationDelivery]:
    """`channels` (admin /communications/notify only) narrows the allowed set; it can never add an un-opted-in channel."""
    await db.flush()  # the notification needs its id
    pref = await db.get(NotificationPreference, recipient.id)
    allowed = ["email"] + [c for c, on in (("whatsapp", pref and pref.whatsapp_opt_in), ("sms", pref and pref.sms_opt_in)) if on]
    chosen = allowed if channels is None else [c for c in allowed if c in channels]
    rows = [NotificationDelivery(notification_id=notification.id, channel=c, status="queued", attempt_count=0, context=context) for c in chosen]
    db.add_all(rows)
    await db.flush()
    db.sync_session.info.setdefault(PENDING_KEY, []).extend(r.id for r in rows)
    return rows


@event.listens_for(Session, "after_commit")
def _publish_after_commit(session: Session) -> None:
    for delivery_id in session.info.pop(PENDING_KEY, []):
        enqueue(delivery_id)


@event.listens_for(Session, "after_rollback")
def _discard_after_rollback(session: Session) -> None:
    session.info.pop(PENDING_KEY, None)


def enqueue(delivery_id: UUID | str, countdown: int = 0) -> None:
    """Never raises: a broker outage must not fail the request that already committed. The row stays queued/retrying and
    the stale sweeper (delivery.sweep_stale_deliveries) publishes it again."""
    try:
        _publish(str(delivery_id), countdown)
    except Exception as exc:  # noqa: BLE001 -- see docstring
        logger.warning("notification_enqueue_failed", extra={"extra_fields": {"delivery_id": str(delivery_id), "error_type": type(exc).__name__}})


def _publish(delivery_id: str, countdown: int) -> None:
    from app.worker import deliver_notification_task  # noqa: PLC0415 -- the worker module imports this package

    # retry=False: fail fast instead of blocking the request in Celery's publish-retry loop when Redis is down.
    deliver_notification_task.apply_async((delivery_id,), countdown=countdown, retry=False)
```

Add a temporary stub so the lazy import resolves until Task 6 replaces it — append to `apps/api/app/worker.py`:

```python
@celery.task
def deliver_notification_task(delivery_id: str):
    """ENH-014: replaced with the real body in Task 6."""
    raise NotImplementedError
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_dispatch.py tests/test_enh_014_models.py tests/test_enh_014_preferences.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/notifications/dispatch.py apps/api/app/worker.py apps/api/tests/conftest.py apps/api/tests/enh014_helpers.py apps/api/tests/test_enh_014_dispatch.py
git commit -m "feat(enh-014): queue deliveries per opted-in channel and publish after commit"
```

---

### Task 5: Twilio adapter

**Files:**
- Create: `apps/api/app/notifications/twilio.py`
- Test: `apps/api/tests/test_enh_014_twilio.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) SendResult(status: str, provider_reference: str | None = None, error: str | None = None, transient: bool = False)` — `status` ∈ `sent | failed | skipped | not_configured`.
  - `configured(channel: str) -> bool`
  - `async send_whatsapp(to: str, title: str, body: str, action_url: str | None, *, client: httpx.AsyncClient | None = None) -> SendResult`
  - `async send_sms(to: str, title: str, body: str, action_url: str | None, *, client: httpx.AsyncClient | None = None) -> SendResult`
  - `plain(text: str | None, limit: int = 500) -> str`; `portal_link(action_url: str | None) -> str`

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-014 Task 5 -- Twilio Messages API adapter (spec §6.4; AC16). httpx.MockTransport: no network."""

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.config import settings
from app.notifications import twilio

SID = "SM" + "a" * 32


@pytest.fixture(autouse=True)
def _twilio_settings(monkeypatch):
    for key, value in {
        "twilio_account_sid": "AC123",
        "twilio_auth_token": "secret-token",
        "twilio_whatsapp_from": "+14155238886",
        "twilio_sms_from": "+15005550006",
        "twilio_whatsapp_content_sid": "HX123",
        "frontend_url": "https://portal.example",
    }.items():
        monkeypatch.setattr(settings, key, value)


def _client(status: int, body, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body) if not isinstance(body, str) else httpx.Response(status, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _form(request: httpx.Request) -> dict:
    return {k: v[0] for k, v in parse_qs(request.content.decode()).items()}


@pytest.mark.asyncio
async def test_whatsapp_uses_the_template_with_basic_auth():
    seen = []
    result = await twilio.send_whatsapp("+919876543210", "Result published", "Maths is out.", "/school/parent/dashboard", client=_client(201, {"sid": SID}, seen))
    assert result == twilio.SendResult("sent", provider_reference=SID)
    [request] = seen
    assert str(request.url) == "https://api.twilio.com/2010-04-01/Accounts/AC123/Messages.json"
    assert request.headers["authorization"] == "Basic " + base64.b64encode(b"AC123:secret-token").decode()
    form = _form(request)
    assert (form["From"], form["To"], form["ContentSid"]) == ("whatsapp:+14155238886", "whatsapp:+919876543210", "HX123")
    assert json.loads(form["ContentVariables"]) == {"1": "Result published", "2": "Maths is out.", "3": "https://portal.example/school/parent/dashboard"}


@pytest.mark.asyncio
async def test_sms_is_one_capped_line_with_the_link():
    seen = []
    await twilio.send_sms("+919876543210", "Result", "x" * 1000, "/school/parent/dashboard", client=_client(201, {"sid": SID}, seen))
    form = _form(seen[0])
    assert (form["From"], form["To"]) == ("+15005550006", "+919876543210")
    assert len(form["Body"]) <= 320 and form["Body"].startswith("Result — x") and form["Body"].endswith(" https://portal.example/school/parent/dashboard")


@pytest.mark.parametrize("action_url", [None, "", "https://evil.example/x", "//evil.example", "/\\evil.example", "javascript:alert(1)"])
def test_missing_or_offsite_link_falls_back_to_portal_home(action_url):
    # Review Focus 3 + spec §6.4: never an off-site link, and never an empty template variable.
    assert twilio.portal_link(action_url) == "https://portal.example/"


def test_variables_are_single_line_and_capped():
    # Review Focus 5: newlines/tabs collapse (WhatsApp rejects them in variables); non-Latin text survives the cap.
    assert twilio.plain("विद्यालय\n\n  परिणाम\tघोषित") == "विद्यालय परिणाम घोषित"
    assert len(twilio.plain("अ" * 900)) == 500


@pytest.mark.asyncio
@pytest.mark.parametrize(("status", "transient"), [(429, True), (500, True), (503, True), (400, False), (401, False)])
async def test_failures_are_classified_and_redacted(status, transient):
    body = {"code": 21211, "message": "The 'To' number +919876543210 is not a valid phone number."}
    result = await twilio.send_sms("+919876543210", "t", "b", None, client=_client(status, body, []))
    assert result.status == "failed" and result.transient is transient
    assert result.error.startswith("twilio:21211 ")
    assert "9876543210" not in result.error and "secret-token" not in result.error


@pytest.mark.asyncio
async def test_network_errors_are_transient_and_carry_no_detail():
    def handler(request):
        raise httpx.ConnectTimeout("timed out talking to https://AC123:secret-token@api.twilio.com")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    result = await twilio.send_whatsapp("+919876543210", "t", "b", None, client=client)
    assert (result.status, result.transient, result.error) == ("failed", True, "twilio:network ConnectTimeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"sid": "not-a-sid"}, {}, "<html>ok</html>", ["SM"]])
async def test_an_unrecognised_success_body_is_a_permanent_failure(body):
    # Accepted-but-unparseable must not be retried: a retry could send the message twice.
    result = await twilio.send_sms("+919876543210", "t", "b", None, client=_client(201, body, []))
    assert (result.status, result.transient, result.error) == ("failed", False, "twilio:unexpected response")


def test_configured_needs_every_value(monkeypatch):
    assert twilio.configured("whatsapp") and twilio.configured("sms")
    monkeypatch.setattr(settings, "twilio_whatsapp_content_sid", "")
    assert not twilio.configured("whatsapp") and twilio.configured("sms")
    monkeypatch.setattr(settings, "twilio_auth_token", None)
    assert not twilio.configured("sms")
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_twilio.py`
Expected: FAIL — `ImportError: cannot import name 'twilio' from 'app.notifications'`.

- [ ] **Step 3: Implement**

`apps/api/app/notifications/twilio.py`:

```python
"""ENH-014 (spec §6.4; DEC-NOT-001 2026-09-30 D2, D13): Twilio WhatsApp + SMS over the Messages REST API with httpx.

The Twilio response is untrusted: only `sid` (shape-checked) and the numeric error `code` are read. Stored errors have
runs of 6+ digits redacted (Twilio messages can echo the recipient's number). The auth token is sent only as basic auth
and never appears in an error or a log."""

import json
import re
from dataclasses import dataclass

import httpx

from app.core.config import settings

API = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
TIMEOUT_SECONDS = 10
VARIABLE_MAX = 500
SMS_MAX = 320
_SID = re.compile(r"(SM|MM)[0-9a-f]{32}")
_DIGIT_RUN = re.compile(r"[0-9]{6,}")


@dataclass(frozen=True)
class SendResult:
    status: str  # "sent" | "failed" | "skipped" | "not_configured"
    provider_reference: str | None = None
    error: str | None = None
    transient: bool = False


def configured(channel: str) -> bool:
    sender = settings.twilio_whatsapp_from if channel == "whatsapp" else settings.twilio_sms_from
    template_ok = bool(settings.twilio_whatsapp_content_sid) if channel == "whatsapp" else True
    return bool(settings.twilio_account_sid and settings.twilio_auth_token and sender and template_ok)


def plain(text: str | None, limit: int = VARIABLE_MAX) -> str:
    return " ".join((text or "").split())[:limit]


def portal_link(action_url: str | None) -> str:
    base = settings.frontend_url.rstrip("/")
    internal = bool(action_url) and action_url.startswith("/") and not action_url.startswith(("//", "/\\"))
    return base + (action_url if internal else "/")


async def send_whatsapp(to: str, title: str, body: str, action_url: str | None, *, client: httpx.AsyncClient | None = None) -> SendResult:
    variables = {"1": plain(title), "2": plain(body), "3": portal_link(action_url)}
    data = {"From": f"whatsapp:{settings.twilio_whatsapp_from}", "To": f"whatsapp:{to}", "ContentSid": settings.twilio_whatsapp_content_sid, "ContentVariables": json.dumps(variables, ensure_ascii=False)}
    return await _post(data, client)


async def send_sms(to: str, title: str, body: str, action_url: str | None, *, client: httpx.AsyncClient | None = None) -> SendResult:
    link = portal_link(action_url)
    text = plain(f"{plain(title)} — {plain(body)}", max(0, SMS_MAX - len(link) - 1))
    return await _post({"From": settings.twilio_sms_from, "To": to, "Body": f"{text} {link}"}, client)


async def _post(data: dict, client: httpx.AsyncClient | None) -> SendResult:
    url = API.format(sid=settings.twilio_account_sid)
    auth = (settings.twilio_account_sid or "", settings.twilio_auth_token or "")
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as own:
                response = await own.post(url, data=data, auth=auth)
        else:
            response = await client.post(url, data=data, auth=auth)
    except httpx.HTTPError as exc:
        return SendResult("failed", error=f"twilio:network {type(exc).__name__}", transient=True)
    payload = _json_object(response)
    if response.is_success:
        sid = payload.get("sid")
        if isinstance(sid, str) and _SID.fullmatch(sid):
            return SendResult("sent", provider_reference=sid)
        return SendResult("failed", error="twilio:unexpected response")
    code, message = payload.get("code"), payload.get("message")
    detail = f"twilio:{code if isinstance(code, int) else response.status_code}"
    if isinstance(message, str):
        detail += " " + _DIGIT_RUN.sub("…", message)
    return SendResult("failed", error=detail[:500], transient=response.status_code == 429 or response.status_code >= 500)


def _json_object(response: httpx.Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_twilio.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/notifications/twilio.py apps/api/tests/test_enh_014_twilio.py
git commit -m "feat(enh-014): Twilio WhatsApp/SMS adapter over httpx with link allow-list and error redaction"
```

---

### Task 6: Worker delivery — claim, send, record, retry

**Files:**
- Create: `apps/api/app/notifications/delivery.py`
- Modify: `apps/api/app/worker.py` (replace the Task 4 stub)
- Test: `apps/api/tests/test_enh_014_delivery.py`

**Interfaces:**
- Consumes: `enqueue` (Task 4), `twilio.SendResult/configured/send_whatsapp/send_sms` (Task 5), `normalise_phone` (Task 2), `send_notification` (`services/integrations.py`), `send_parent_notification_email` (`services/mailer.py`).
- Produces: `async deliver(delivery_id: UUID) -> str | None` (final status, or `None` if the claim found nothing); `RETRY_COUNTDOWNS = {1: 60, 2: 300, 3: 1500}`; `MAX_ATTEMPTS = 4`; Celery task `deliver_notification_task(delivery_id: str)`.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-014 Task 6 -- deliver(): claim, send per channel, record, retry (spec §6.5; AC07-AC10, AC12, AC14)."""

import asyncio

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models import Notification, NotificationDelivery, NotificationPreference, User
from app.notifications import delivery, twilio
from app.notifications.delivery import deliver
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user, set_prefs

SID = "SM" + "b" * 32


@pytest.fixture
def twilio_on(monkeypatch):
    for key, value in {"twilio_account_sid": "AC1", "twilio_auth_token": "t", "twilio_whatsapp_from": "+1415", "twilio_sms_from": "+1500", "twilio_whatsapp_content_sid": "HX1"}.items():
        monkeypatch.setattr(settings, key, value)


@pytest.fixture
def sent(monkeypatch):
    """Records every outbound call; each channel answers 'sent' unless a test overrides it."""
    calls: list[tuple] = []

    async def whatsapp(to, title, body, action_url, **_):
        calls.append(("whatsapp", to, title))
        return twilio.SendResult("sent", provider_reference=SID)

    async def sms(to, title, body, action_url, **_):
        calls.append(("sms", to, title))
        return twilio.SendResult("sent", provider_reference=SID)

    async def webhook(channel, payload):
        calls.append((f"webhook:{channel}", payload.get("to"), payload.get("title")))
        return "not_configured", None

    async def smtp(**kwargs):
        calls.append(("smtp", kwargs["to_email"], kwargs["school_name"]))
        return "sent", None

    monkeypatch.setattr(twilio, "send_whatsapp", whatsapp)
    monkeypatch.setattr(twilio, "send_sms", sms)
    monkeypatch.setattr(delivery, "send_notification", webhook)
    monkeypatch.setattr(delivery, "send_parent_notification_email", smtp)
    return calls


async def _queued(db, user: User, *, context=None) -> dict[str, NotificationDelivery]:
    note = Notification(user_id=user.id, title="Result published", body="Maths is out.", action_url="/school/parent/dashboard")
    db.add(note)
    await db.flush()
    rows = await queue_deliveries(db, note, user, context=context)
    await db.commit()
    return {r.channel: r for r in rows}


async def _row(db, row_id) -> NotificationDelivery:
    return await db.get(NotificationDelivery, row_id, populate_existing=True)


@pytest.mark.asyncio
async def test_whatsapp_is_sent_with_the_normalised_number(db_session, twilio_on, sent):
    user = await make_user(db_session, phone="98765 43210")
    await set_prefs(db_session, user, whatsapp=True)
    rows = await _queued(db_session, user)
    assert await deliver(rows["whatsapp"].id) == "sent"
    row = await _row(db_session, rows["whatsapp"].id)
    assert (row.status, row.attempt_count, row.provider_reference, row.error) == ("sent", 1, SID, None) and row.sent_at is not None
    assert ("whatsapp", "+919876543210", "Result published") in sent


@pytest.mark.asyncio
async def test_school_email_keeps_the_smtp_path_with_the_school_name(db_session, sent):
    user = await make_user(db_session)
    rows = await _queued(db_session, user, context={"kind": "school", "school_name": "Green Valley"})
    assert await deliver(rows["email"].id) == "sent"
    assert sent == [("smtp", user.email, "Green Valley")]


@pytest.mark.asyncio
async def test_school_email_falls_back_to_the_webhook_when_smtp_is_not_configured(db_session, sent, monkeypatch):
    async def smtp_off(**kwargs):
        return "not_configured", None

    monkeypatch.setattr(delivery, "send_parent_notification_email", smtp_off)
    user = await make_user(db_session)
    rows = await _queued(db_session, user, context={"kind": "school", "school_name": "Green Valley"})
    assert await deliver(rows["email"].id) == "not_configured"
    assert sent == [("webhook:email", user.email, "Result published")]


@pytest.mark.asyncio
async def test_generic_email_uses_the_email_webhook(db_session, sent):
    user = await make_user(db_session, role="it_student", division="it")
    rows = await _queued(db_session, user)
    assert await deliver(rows["email"].id) == "not_configured"
    assert sent == [("webhook:email", user.email, "Result published")]


@pytest.mark.asyncio
async def test_invalid_phone_fails_that_delivery_only_and_is_not_retried(db_session, twilio_on, sent, enqueued):
    bad = await make_user(db_session, phone="12345")
    good = await make_user(db_session, phone="9876543210")
    for u in (bad, good):
        await set_prefs(db_session, u, whatsapp=True)
    bad_rows, good_rows = await _queued(db_session, bad), await _queued(db_session, good)
    enqueued.clear()
    assert await deliver(bad_rows["whatsapp"].id) == "failed"
    assert await deliver(good_rows["whatsapp"].id) == "sent"
    row = await _row(db_session, bad_rows["whatsapp"].id)
    assert (row.status, row.error) == ("failed", "invalid_phone") and enqueued == []


@pytest.mark.asyncio
async def test_transient_failures_retry_at_60_300_1500_then_fail(db_session, twilio_on, monkeypatch, enqueued):
    async def flaky(*args, **kwargs):
        return twilio.SendResult("failed", error="twilio:503", transient=True)

    monkeypatch.setattr(twilio, "send_sms", flaky)
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    row_id = (await _queued(db_session, user))["sms"].id
    enqueued.clear()
    for expected_countdown in (60, 300, 1500):
        assert await deliver(row_id) == "retrying"
        assert enqueued.pop() == (str(row_id), expected_countdown)
    assert await deliver(row_id) == "failed"
    row = await _row(db_session, row_id)
    assert (row.status, row.attempt_count, row.error) == ("failed", 4, "twilio:503") and enqueued == []


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried(db_session, twilio_on, monkeypatch, enqueued):
    async def rejected(*args, **kwargs):
        return twilio.SendResult("failed", error="twilio:21211 invalid", transient=False)

    monkeypatch.setattr(twilio, "send_whatsapp", rejected)
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    row_id = (await _queued(db_session, user))["whatsapp"].id
    enqueued.clear()
    assert await deliver(row_id) == "failed" and enqueued == []


@pytest.mark.asyncio
async def test_a_duplicate_task_sends_once(db_session, twilio_on, sent):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    row_id = (await _queued(db_session, user))["sms"].id
    results = await asyncio.gather(deliver(row_id), deliver(row_id))
    assert sorted(results, key=str) == sorted(["sent", None], key=str)
    assert [c for c in sent if c[0] == "sms"] == [("sms", "+919876543210", "Result published")]


@pytest.mark.asyncio
async def test_opting_out_after_queueing_skips(db_session, twilio_on, sent):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    row_id = (await _queued(db_session, user))["whatsapp"].id
    pref = await db_session.get(NotificationPreference, user.id)
    pref.whatsapp_opt_in = False
    await db_session.commit()
    assert await deliver(row_id) == "skipped"
    assert (await _row(db_session, row_id)).error == "opted_out" and not [c for c in sent if c[0] == "whatsapp"]


@pytest.mark.asyncio
async def test_inactive_recipient_is_skipped(db_session, sent):
    # Review Focus 4.
    user = await make_user(db_session)
    row_id = (await _queued(db_session, user))["email"].id
    user.active = False
    await db_session.commit()
    assert await deliver(row_id) == "skipped" and sent == []


@pytest.mark.asyncio
async def test_without_twilio_the_legacy_webhook_is_used_else_not_configured(db_session, sent, monkeypatch):
    for key in ("twilio_account_sid", "twilio_auth_token", "twilio_whatsapp_from", "twilio_sms_from", "twilio_whatsapp_content_sid"):
        monkeypatch.setattr(settings, key, None)  # a developer's local .env may carry sandbox values
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    rows = await _queued(db_session, user)
    assert await deliver(rows["whatsapp"].id) == "not_configured"  # fake webhook answers not_configured
    assert ("webhook:whatsapp", user.email, "Result published") in sent


@pytest.mark.asyncio
async def test_a_claimed_or_finished_row_is_left_alone(db_session, sent):
    user = await make_user(db_session)
    row_id = (await _queued(db_session, user))["email"].id
    assert await deliver(row_id) is not None
    assert await deliver(row_id) is None  # already final: no second send
    assert len(sent) == 1


@pytest.mark.asyncio
async def test_logs_never_carry_contact_details_or_text(db_session, twilio_on, sent, caplog):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    rows = await _queued(db_session, user)
    with caplog.at_level("INFO"):
        for row in rows.values():
            await deliver(row.id)
    text = caplog.text + " ".join(str(getattr(r, "extra_fields", "")) for r in caplog.records)
    assert "9876543210" not in text and user.email not in text and "Maths is out." not in text
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_delivery.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.notifications.delivery'`.

- [ ] **Step 3: Implement `delivery.py`**

```python
"""ENH-014 (spec §6.5): the worker side. Claim one queued delivery atomically, send it on its channel, record the outcome,
and re-enqueue transient failures with the D11 countdowns. The row -- not the broker -- is the source of truth, so a
duplicate task, a redelivered message or a concurrent worker can never send twice (the claim lets exactly one through)."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update

from app.core.database import SessionLocal
from app.models import Notification, NotificationDelivery, NotificationPreference, User
from app.notifications import twilio
from app.notifications.dispatch import enqueue
from app.notifications.phone import normalise_phone
from app.services.integrations import send_notification
from app.services.mailer import send_parent_notification_email

logger = logging.getLogger(__name__)

RETRY_COUNTDOWNS = {1: 60, 2: 300, 3: 1500}  # seconds, after failed attempt n (D11)
MAX_ATTEMPTS = 4  # the first try plus three retries
CLAIMABLE = ("queued", "retrying")


@dataclass(frozen=True)
class _Snapshot:
    """Plain values read before any network call, so no transaction is held open while a provider is slow."""

    title: str
    body: str
    action_url: str | None
    email: str
    full_name: str
    phone: str | None
    active: bool
    whatsapp_opt_in: bool
    sms_opt_in: bool


async def deliver(delivery_id: UUID) -> str | None:
    async with SessionLocal() as db:
        claimed = (
            await db.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.id == delivery_id, NotificationDelivery.status.in_(CLAIMABLE))
                .values(status="sending", attempt_count=NotificationDelivery.attempt_count + 1)
                .returning(NotificationDelivery.channel, NotificationDelivery.notification_id, NotificationDelivery.attempt_count, NotificationDelivery.context)
            )
        ).one_or_none()
        await db.commit()
        if claimed is None:
            return None
        channel, notification_id, attempt, context = claimed
        snapshot = await _snapshot(db, notification_id)
        await db.commit()  # end the read transaction before sending

    result = await _send(channel, snapshot, context)
    status = "retrying" if result.status == "failed" and result.transient and attempt < MAX_ATTEMPTS else result.status
    async with SessionLocal() as db:
        await db.execute(
            update(NotificationDelivery)
            .where(NotificationDelivery.id == delivery_id, NotificationDelivery.status == "sending")  # the sweeper may have given up on it
            .values(status=status, error=result.error[:500] if result.error else None, provider_reference=result.provider_reference, sent_at=datetime.now(UTC) if status == "sent" else None)
        )
        await db.commit()
    if status == "retrying":
        enqueue(delivery_id, countdown=RETRY_COUNTDOWNS[attempt])
    logger.info("notification_delivery", extra={"extra_fields": {"delivery_id": str(delivery_id), "channel": channel, "status": status, "attempt": attempt}})
    return status


async def _snapshot(db, notification_id: UUID) -> _Snapshot | None:
    note = await db.get(Notification, notification_id)
    user = await db.get(User, note.user_id) if note else None
    if note is None or user is None:
        return None
    pref = await db.get(NotificationPreference, user.id)
    return _Snapshot(note.title, note.body, note.action_url, user.email, user.full_name, user.phone, bool(user.active), bool(pref and pref.whatsapp_opt_in), bool(pref and pref.sms_opt_in))


async def _send(channel: str, s: _Snapshot | None, context: dict | None) -> twilio.SendResult:
    if s is None or not s.active:
        return twilio.SendResult("skipped", error="recipient unavailable")
    if channel == "email":
        return await _send_email(s, context)
    if not (s.whatsapp_opt_in if channel == "whatsapp" else s.sms_opt_in):
        return twilio.SendResult("skipped", error="opted_out")
    phone = normalise_phone(s.phone)
    if phone is None:
        return twilio.SendResult("failed", error="invalid_phone")
    if twilio.configured(channel):
        send = twilio.send_whatsapp if channel == "whatsapp" else twilio.send_sms
        return await send(phone, s.title, s.body, s.action_url)
    status, error = await send_notification(channel, {"to": s.email, "phone": phone, "title": s.title, "body": s.body, "action_url": s.action_url})
    return twilio.SendResult(status, error=error, transient=status == "failed")


async def _send_email(s: _Snapshot, context: dict | None) -> twilio.SendResult:
    """Exactly the two email paths that existed inline before ENH-014 (AC12)."""
    if context and context.get("kind") == "school":
        status, error = await send_parent_notification_email(to_email=s.email, recipient_name=s.full_name, school_name=context.get("school_name") or "your school", title=s.title, body=s.body, action_url=s.action_url)
        if status == "not_configured":
            status, error = await send_notification("email", {"to": s.email, "title": s.title, "body": s.body, "action_url": s.action_url})
    else:
        status, error = await send_notification("email", {"to": s.email, "phone": s.phone, "title": s.title, "body": s.body, "action_url": s.action_url})
    return twilio.SendResult(status, error=error, transient=status == "failed")
```

Note: `twilio.send_whatsapp` / `twilio.send_sms` are looked up on the module at call time, which is what lets the tests replace them.

- [ ] **Step 4: Replace the worker stub**

In `apps/api/app/worker.py`, replace the Task 4 stub with:

```python
@celery.task
def deliver_notification_task(delivery_id: str):
    """ENH-014 (spec §6.5): send one queued NotificationDelivery. Retries are re-enqueued by `deliver` itself with the D11
    countdowns (not Celery autoretry), so attempts are counted on the row. Each run is a fresh event loop, so the pooled
    asyncpg connections from the previous loop are disposed first (same reason as tests/conftest.py)."""

    async def _run():
        from app.core.database import engine
        from app.notifications.delivery import deliver

        await engine.dispose()
        return await deliver(UUID(delivery_id))

    return asyncio.run(_run())
```

- [ ] **Step 5: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_delivery.py tests/test_enh_014_dispatch.py`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

Run: `python -m ruff check . && python -m mypy app`

```bash
git add apps/api/app/notifications/delivery.py apps/api/app/worker.py apps/api/tests/test_enh_014_delivery.py
git commit -m "feat(enh-014): worker delivery with atomic claim, opt-in recheck and D11 retries"
```

---

### Task 7: Stale-delivery sweeper

**Files:**
- Modify: `apps/api/app/notifications/delivery.py` (append)
- Modify: `apps/api/app/worker.py` (task + beat schedule)
- Test: `apps/api/tests/test_enh_014_sweeper.py`

**Interfaces:**
- Consumes: `enqueue` (Task 4).
- Produces: `async sweep_stale_deliveries(now: datetime | None = None) -> dict[str, int]` returning `{"requeued": n, "interrupted": m}`; Celery task `sweep_stale_deliveries_task`; beat entry `enh014-sweep-stale-deliveries` every 300 s.

- [ ] **Step 1: Write the failing tests**

```python
"""ENH-014 Task 7 -- the stale-delivery sweeper (spec §6.5). The test DB is shared, so assert on this test's rows only."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.models import Notification, NotificationDelivery
from app.notifications.delivery import sweep_stale_deliveries
from app.notifications.dispatch import queue_deliveries
from tests.enh014_helpers import make_user


async def _row(db, *, status: str, age: timedelta) -> NotificationDelivery:
    user = await make_user(db)
    note = Notification(user_id=user.id, title="t", body="b")
    db.add(note)
    await db.flush()
    [row] = await queue_deliveries(db, note, user)
    await db.commit()
    await db.execute(update(NotificationDelivery).where(NotificationDelivery.id == row.id).values(status=status, updated_at=datetime.now(UTC) - age))
    await db.commit()
    return row


@pytest.mark.asyncio
async def test_stale_queued_and_retrying_rows_are_published_again(db_session, enqueued):
    queued = await _row(db_session, status="queued", age=timedelta(minutes=31))
    retrying = await _row(db_session, status="retrying", age=timedelta(minutes=45))
    fresh = await _row(db_session, status="queued", age=timedelta(minutes=5))
    enqueued.clear()
    await sweep_stale_deliveries()
    published = {d for d, _ in enqueued}
    assert {str(queued.id), str(retrying.id)} <= published and str(fresh.id) not in published
    row = await db_session.get(NotificationDelivery, queued.id, populate_existing=True)
    assert row.status == "queued" and row.updated_at > datetime.now(UTC) - timedelta(minutes=1)  # touched: not re-published every sweep


@pytest.mark.asyncio
async def test_a_stuck_sending_row_is_failed_never_resent(db_session, enqueued):
    stuck = await _row(db_session, status="sending", age=timedelta(minutes=16))
    recent = await _row(db_session, status="sending", age=timedelta(minutes=2))
    enqueued.clear()
    await sweep_stale_deliveries()
    assert (await db_session.get(NotificationDelivery, stuck.id, populate_existing=True)).status == "failed"
    assert (await db_session.get(NotificationDelivery, stuck.id)).error == "worker interrupted"
    assert (await db_session.get(NotificationDelivery, recent.id, populate_existing=True)).status == "sending"
    assert str(stuck.id) not in {d for d, _ in enqueued}
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_sweeper.py`
Expected: FAIL — `ImportError: cannot import name 'sweep_stale_deliveries'`.

- [ ] **Step 3: Implement**

Append to `apps/api/app/notifications/delivery.py` (add `timedelta` to the datetime import):

```python
STALE_QUEUED = timedelta(minutes=30)  # longer than the largest retry countdown (25 min)
STALE_SENDING = timedelta(minutes=15)


async def sweep_stale_deliveries(now: datetime | None = None) -> dict[str, int]:
    """Publish queued/retrying rows nobody picked up (broker outage, lost message) again, touching `updated_at` so the
    next sweep does not re-publish them at once; a duplicate publish is harmless because the claim lets one through.
    A row stuck in `sending` has an unknown outcome (the worker died mid-send): it is failed, never resent -- Twilio has
    no idempotency key, and a duplicate message to a parent is worse than a missed copy (email and in-app remain)."""
    now = now or datetime.now(UTC)
    async with SessionLocal() as db:
        requeue = (
            await db.scalars(
                update(NotificationDelivery)
                .where(NotificationDelivery.status.in_(CLAIMABLE), NotificationDelivery.updated_at < now - STALE_QUEUED)
                .values(updated_at=now)
                .returning(NotificationDelivery.id)
            )
        ).all()
        interrupted = (
            await db.execute(
                update(NotificationDelivery)
                .where(NotificationDelivery.status == "sending", NotificationDelivery.updated_at < now - STALE_SENDING)
                .values(status="failed", error="worker interrupted")
            )
        ).rowcount
        await db.commit()
    for delivery_id in requeue:
        enqueue(delivery_id)
    counts = {"requeued": len(requeue), "interrupted": interrupted or 0}
    logger.info("notification_sweep", extra={"extra_fields": counts})
    return counts
```

Append to `apps/api/app/worker.py`:

```python
@celery.task
def sweep_stale_deliveries_task():
    """ENH-014 (spec §6.5): every 5 minutes via beat."""

    async def _run():
        from app.core.database import engine
        from app.notifications.delivery import sweep_stale_deliveries

        await engine.dispose()
        return await sweep_stale_deliveries()

    return asyncio.run(_run())


celery.conf.beat_schedule = {"enh014-sweep-stale-deliveries": {"task": "app.worker.sweep_stale_deliveries_task", "schedule": 300.0}}
```

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_sweeper.py`
Expected: `2 passed`.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/notifications/delivery.py apps/api/app/worker.py apps/api/tests/test_enh_014_sweeper.py
git commit -m "feat(enh-014): beat sweeper re-publishes stale deliveries and fails interrupted sends"
```

---

### Task 8: Route the existing triggers through the queue

**Files:**
- Modify: `apps/api/app/api/schools.py:720-738` (`_notify_parent` and the SCH-007 comment block above it)
- Modify: `apps/api/app/api/workflows.py:118-124` (`_notify_user`) and the two call sites passing `["email"]` (currently lines 1256 and 1415)
- Modify: `apps/api/app/api/inbound.py:70-78` (`_notify_student`)
- Modify: `apps/api/app/api/communications.py:72-104` (`notify`)
- Modify (intended behaviour change, spec §10): `apps/api/tests/test_sch_007_parent_portal.py:163-164`, `apps/api/tests/test_ovs_004_status_tracking.py:115-137`
- Test: `apps/api/tests/test_enh_014_triggers.py`

**Interfaces:**
- Consumes: `queue_deliveries` (Task 4), `drain` (Task 4), `deliver` (Task 6).
- Produces: nothing new; helper signatures unchanged.

- [ ] **Step 1: Write the failing trigger tests**

```python
"""ENH-014 Task 8 -- existing triggers deliver on opted-in channels (AC04-AC06, AC11). Reuses SCH-007's school builder."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import Notification, NotificationDelivery
from tests.enh014_helpers import drain, login, make_user, set_prefs
from tests.test_sch_007_parent_portal import _login as sch_login
from tests.test_sch_007_parent_portal import _notifications_for, _school, _staff


async def _channels(db, notes) -> list[tuple[str, str]]:
    rows = (await db.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id.in_([n.id for n in notes])))).all()
    return sorted((r.channel, r.status) for r in rows)


async def _publish_result(client, db, ctx) -> None:
    uploader, approver = await _staff(db, ctx, "academic_team"), await _staff(db, ctx, "academic_team")
    await sch_login(client, uploader.email)
    created = await client.post("/api/v1/school/academic-team/results", json={"school_student_id": str(ctx["student_a"].id), "academic_year": "2026-27", "term": "Term 1", "subject": "Mathematics", "max_marks": 100, "marks_obtained": 88})
    assert created.status_code == 201, created.text
    await sch_login(client, approver.email)
    assert (await client.post(f"/api/v1/school/academic-team/results/{created.json()['id']}/verify")).status_code == 200
    assert (await client.post(f"/api/v1/school/academic-team/results/{created.json()['id']}/publish")).status_code == 200


@pytest.mark.asyncio
async def test_result_publish_reaches_an_opted_in_parent_on_whatsapp(client, db_session, enqueued, monkeypatch):
    from app.notifications import twilio

    whatsapp_calls = []

    async def fake_whatsapp(to, title, body, action_url, **_):
        whatsapp_calls.append((to, title))
        return twilio.SendResult("sent", provider_reference="SM" + "c" * 32)

    monkeypatch.setattr(twilio, "send_whatsapp", fake_whatsapp)
    monkeypatch.setattr(twilio, "configured", lambda channel: True)
    ctx = await _school(db_session)
    ctx["parent_a"].phone = "9876543210"
    await db_session.commit()
    await set_prefs(db_session, ctx["parent_a"], whatsapp=True)

    await _publish_result(client, db_session, ctx)
    await drain(enqueued)

    notes = await _notifications_for(db_session, ctx["parent_a"])
    channels = await _channels(db_session, notes)
    assert ("whatsapp", "sent") in channels and [c for c, _ in channels] == ["email", "whatsapp"]
    assert whatsapp_calls == [("+919876543210", "Term 1 Mathematics result published for Child A")]
    assert await _notifications_for(db_session, ctx["parent_b"]) == []


@pytest.mark.asyncio
async def test_a_parent_who_did_not_opt_in_gets_email_only(client, db_session, enqueued):
    ctx = await _school(db_session)
    ctx["parent_a"].phone = "9876543210"
    await db_session.commit()
    await _publish_result(client, db_session, ctx)
    notes = await _notifications_for(db_session, ctx["parent_a"])
    assert [c for c, _ in await _channels(db_session, notes)] == ["email"]


@pytest.mark.asyncio
async def test_session_scheduling_queues_for_each_parent_and_returns_before_sending(client, db_session, enqueued):
    ctx = await _school(db_session)
    await set_prefs(db_session, ctx["parent_b"], sms=True)
    ctx["parent_b"].phone = "9876543211"
    await db_session.commit()
    await sch_login(client, ctx["coordinator"].email)
    when = (datetime.now(UTC) + timedelta(days=3)).replace(microsecond=0).isoformat()
    response = await client.post("/api/v1/school/activities", json={"title": "Career Workshop", "scheduled_at": when})
    assert response.status_code == 201, response.text
    a = await _channels(db_session, await _notifications_for(db_session, ctx["parent_a"]))
    b = await _channels(db_session, await _notifications_for(db_session, ctx["parent_b"]))
    assert a == [("email", "queued")] and b == [("email", "queued"), ("sms", "queued")]  # AC05: sent later, by the worker


@pytest.mark.asyncio
async def test_it_triggers_follow_preferences_including_the_former_email_only_calls(db_session, enqueued):
    from app.api.workflows import _notify_user

    student = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, student, sms=True)
    await _notify_user(db_session, student, "Certificate issued", "Your certificate is ready.", "/it/student/certificates")
    await db_session.commit()
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == student.id))).all()
    assert [c for c, _ in await _channels(db_session, [note])] == ["email", "sms"]


@pytest.mark.asyncio
async def test_password_reset_stays_inline_and_email_only(client, db_session, enqueued, monkeypatch):
    import app.api.auth as auth_module

    async def fake_send(channel, payload):
        return "sent", None

    monkeypatch.setattr(auth_module, "send_notification", fake_send)
    user = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True, sms=True)
    assert (await client.post("/api/v1/auth/forgot-password", json={"email": user.email})).status_code == 202
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == user.id))).all()
    assert await _channels(db_session, [note]) == [("email", "sent")] and enqueued == []  # AC11


@pytest.mark.asyncio
async def test_admin_notify_queues_only_opted_in_channels(client, db_session, enqueued):
    admin = await make_user(db_session, role="overseas_admin")
    target = await make_user(db_session, role="overseas_student", phone="9876543210")
    await set_prefs(db_session, target, sms=True)
    await login(client, admin.email)
    response = await client.post("/api/v1/communications/notify", json={"user_id": str(target.id), "title": "Hello", "body": "Update", "channels": ["email", "whatsapp", "sms"]})
    assert response.status_code == 202, response.text
    assert response.json() == {"queued": True, "channels": {"email": "queued", "sms": "queued"}}
    [note] = (await db_session.scalars(select(Notification).where(Notification.user_id == target.id))).all()
    assert [c for c, _ in await _channels(db_session, [note])] == ["email", "sms"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest -q tests/test_enh_014_triggers.py`
Expected: FAIL — rows still `email`-only with inline statuses (e.g. `("email", "not_configured")`), no `whatsapp`/`sms` rows.

- [ ] **Step 3: Change the helper bodies**

`apps/api/app/api/schools.py` — replace the SCH-007 comment block and `_notify_parent`:

```python
# --- SCH-007: Parent Portal notifications ---------------------------------------------------
# Every trigger below writes the in-app `Notification` row, then queues one `NotificationDelivery` per channel -- email
# always, WhatsApp/SMS when the recipient opted in (ENH-014, DEC-NOT-001 2026-09-30). The worker sends them after the
# triggering write commits (app/notifications/delivery.py): real SMTP via `mailer.send_parent_notification_email`, the
# generic email webhook when SMTP isn't configured, Twilio for WhatsApp/SMS. A failed or unconfigured send never blocks
# or reverts the write that triggered it (SCH-007-AC04).

async def _notify_parent(db: AsyncSession, parent: User, *, school_name: str, title: str, body: str, action_url: str | None) -> None:
    item = Notification(user_id=parent.id, title=title, body=body, read=False, action_url=action_url)
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, parent, context={"kind": "school", "school_name": school_name})
```

Add `from app.notifications.dispatch import queue_deliveries` to the imports. Then run `python -m ruff check app/api/schools.py`; remove `send_parent_notification_email` from the `app.services.mailer` import and `NotificationDelivery`/`send_notification` from their imports **only if** ruff reports them unused (`F401`).

`apps/api/app/api/workflows.py`:

```python
async def _notify_user(db: AsyncSession, recipient: User, title: str, body: str, action_url: str | None, channels: list[str] | None = None):
    """ENH-014: in-app row plus queued deliveries (email + the recipient's opted-in channels), sent after commit.
    `channels` can only narrow that set (admin sends); it never adds a channel the recipient did not opt in to."""
    item = Notification(user_id=recipient.id, title=title, body=body, read=False, action_url=action_url)
    db.add(item)
    await db.flush()
    await queue_deliveries(db, item, recipient, channels=channels)
```

Remove the trailing `, ["email"]` argument from the two calls:

```python
    await _notify_user(db, student, "Certificate issued", f"Your {program.title} certificate is ready.", "/it/student/certificates")
```

```python
    await _notify_user(db, student, "Your question has a new reply", f'"{thread.subject}" was answered.', "/it/student/questions")
```

Add the `queue_deliveries` import; drop now-unused imports only as ruff reports them.

`apps/api/app/api/inbound.py` — `_notify_student` body after the `student` check:

```python
    notification = Notification(user_id=student.id, title="University update received", body=email.subject, read=False, action_url="/overseas/student/university-communication")
    db.add(notification)
    await db.flush()
    await queue_deliveries(db, notification, student)
```

`apps/api/app/api/communications.py` — replace the body of `notify` from `recipient_id = payload.get("user_id")` to the audit line:

```python
    recipient_id = payload.get("user_id")
    channels = payload.get("channels", ["email"])
    statuses: dict[str, str] = {}
    if recipient_id:
        recipient = await db.get(User, uuid_reference(recipient_id, "recipient reference"))
        if not recipient:
            raise HTTPException(404, "Recipient not found")
        if user.role != "super_admin" and recipient.division != user.division:
            raise HTTPException(403, "Cross-division notification is not allowed")
        notification = Notification(user_id=recipient.id, title=payload["title"], body=payload["body"], action_url=payload.get("action_url"))
        db.add(notification)
        await db.flush()
        # ENH-014: queued per channel, sent after commit; WhatsApp/SMS only for a recipient who opted in.
        statuses = {row.channel: row.status for row in await queue_deliveries(db, notification, recipient, channels=channels)}
    else:
        for channel in channels:
            status, _error = await send_notification(channel, {"user_id": None, "to": None, "phone": None, "title": payload["title"], "body": payload["body"], "metadata": payload.get("metadata", {})})
            statuses[channel] = status
```

(The audit line and `return {"queued": True, "channels": statuses}` stay as they are.)

- [ ] **Step 4: Update the two existing tests whose behaviour intentionally changed**

`tests/test_sch_007_parent_portal.py` — the psychometric test (line ~150): add `enqueued` to its parameters, and replace lines 162-164 with:

```python
    # NOT-001 + ENH-014: one email delivery per notification, queued, then sent by the worker (no SMTP/webhook in tests).
    await drain(enqueued)
    deliveries = (await db_session.scalars(select(NotificationDelivery).where(NotificationDelivery.notification_id.in_([n.id for n in a_notes])))).all()
    assert len(deliveries) == 2 and all(d.channel == "email" and d.status in {"not_configured", "sent", "failed"} for d in deliveries)
```

and add `from tests.enh014_helpers import drain` to its imports.

`tests/test_ovs_004_status_tracking.py` — in the forced-failure test (line ~113), add `enqueued` to its parameters, patch the worker's sender instead of the removed inline call, and drain before asserting:

```python
    import app.notifications.delivery as delivery_module

    async def failing_send(channel, payload):
        return "failed", "Connection timed out after 10s"

    monkeypatch.setattr(delivery_module, "send_notification", failing_send)
```

then immediately before `delivery = await db_session.scalar(...)`:

```python
    await drain(enqueued)  # ENH-014: sent by the worker after the status change committed; retries exhaust to "failed"
```

and add `from tests.enh014_helpers import drain`. The asserted `status == "failed"` and error text are unchanged.

Then find other callers asserting the old inline statuses:

Run: `grep -rn "communications/notify\|NotificationDelivery" apps/api/tests --include=*.py -l`
For each file not already handled above, run it; any assertion that expects an inline `sent`/`not_configured`/`failed` for a trigger routed through `_notify_parent`/`_notify_user`/`inbound`/`/communications/notify` gets `enqueued` + `await drain(enqueued)` before it (intended change, spec §5.3/§10). `test_enh_023_tier_change.py:222` counts email rows and needs no change.

- [ ] **Step 5: Run to verify**

Run: `python -m pytest -q tests/test_enh_014_triggers.py tests/test_sch_007_parent_portal.py tests/test_ovs_004_status_tracking.py tests/test_enh_023_tier_change.py tests/test_not_001_email_notifications.py tests/test_sch_006_academic_results.py tests/test_sch_009_test_prep_language.py tests/test_enh_011_enrollments.py tests/test_enh_005_approve.py tests/test_stu_005_support_tickets.py tests/test_uni_001_university_rep_portal.py`
Expected: all pass.

- [ ] **Step 6: Lint and commit**

Run: `python -m ruff check . && python -m mypy app`

```bash
git add apps/api/app/api/schools.py apps/api/app/api/workflows.py apps/api/app/api/inbound.py apps/api/app/api/communications.py apps/api/tests/
git commit -m "feat(enh-014): route every emailing trigger through the delivery queue"
```

---

### Task 9: Privacy — erasure and export

**Files:**
- Modify: `apps/api/app/api/admin.py` (GDPR delete branch, line ~957-966)
- Modify: `apps/api/app/api/account.py` (`_build_export`)
- Test: `apps/api/tests/test_enh_014_privacy.py`

**Interfaces:**
- Consumes: `NotificationPreference` (Task 1).
- Produces: export key `"notification_preferences": {"whatsapp": bool, "sms": bool, "whatsapp_opted_in_at": iso | None, "sms_opted_in_at": iso | None}`.

- [ ] **Step 1: Write the failing tests**

The erasure flow mirrors `tests/test_sec_002_gdpr_data_requests.py::test_admin_can_fulfil_a_queued_deletion_request`.

```python
"""ENH-014 Task 9 -- erasure deletes preferences; export includes them (AC13)."""

import uuid

import pytest

from app.api.account import _build_export
from app.models import NotificationPreference
from tests.enh014_helpers import login, make_user, set_prefs


async def _request_and_fulfil_erasure(client, db_session, user) -> None:
    await login(client, user.email, division="it")
    created = await client.post("/api/v1/account/data-requests", json={"type": "delete"}, headers={"Idempotency-Key": uuid.uuid4().hex})
    assert created.status_code in (201, 202), created.text
    admin = await make_user(db_session, role="it_admin", division="it")
    await login(client, admin.email, division="it")
    response = await client.patch(f"/api/v1/admin/data-requests/{created.json()['id']}", json={"decision": "fulfil"})
    assert response.status_code == 200 and response.json()["status"] == "fulfilled", response.text


@pytest.mark.asyncio
async def test_export_includes_notification_preferences(db_session):
    user = await make_user(db_session, phone="9876543210")
    await set_prefs(db_session, user, whatsapp=True)
    exported = await _build_export(db_session, user)
    prefs = exported["notification_preferences"]
    assert (prefs["whatsapp"], prefs["sms"], prefs["sms_opted_in_at"]) == (True, False, None) and prefs["whatsapp_opted_in_at"]


@pytest.mark.asyncio
async def test_export_without_a_row_reports_both_off(db_session):
    user = await make_user(db_session)
    assert (await _build_export(db_session, user))["notification_preferences"] == {"whatsapp": False, "sms": False, "whatsapp_opted_in_at": None, "sms_opted_in_at": None}


@pytest.mark.asyncio
async def test_fulfilled_erasure_deletes_the_preference_row(client, db_session):
    user = await make_user(db_session, role="it_student", division="it", phone="9876543210")
    await set_prefs(db_session, user, sms=True)
    await _request_and_fulfil_erasure(client, db_session, user)
    assert await db_session.get(NotificationPreference, user.id, populate_existing=True) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest -q tests/test_enh_014_privacy.py`
Expected: FAIL — `KeyError: 'notification_preferences'`, and the row still exists after erasure.

- [ ] **Step 3: Implement**

`account.py` `_build_export` — read the row and add the key to the returned dict:

```python
    pref = await db.get(NotificationPreference, user.id)
```

```python
        "notification_preferences": {
            "whatsapp": bool(pref and pref.whatsapp_opt_in),
            "sms": bool(pref and pref.sms_opt_in),
            "whatsapp_opted_in_at": pref.whatsapp_opted_in_at.isoformat() if pref and pref.whatsapp_opted_in_at else None,
            "sms_opted_in_at": pref.sms_opted_in_at.isoformat() if pref and pref.sms_opted_in_at else None,
        },
```

`admin.py` — in the erasure branch, after `subject.phone = None`:

```python
        # ENH-014 (D9): consent state goes with the contact details it applied to.
        await db.execute(delete(NotificationPreference).where(NotificationPreference.user_id == subject.id))
```

Add `delete` to the `from sqlalchemy import ...` line and `NotificationPreference` to the `app.models` import.

- [ ] **Step 4: Run to verify it passes**

Run: `python -m pytest -q tests/test_enh_014_privacy.py` and the existing GDPR test file.
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/api/admin.py apps/api/app/api/account.py apps/api/tests/test_enh_014_privacy.py
git commit -m "feat(enh-014): erasure removes notification preferences; export includes them"
```

---

### Task 10: `NotificationPreferencesForm` component

**Files:**
- Modify: `apps/web/lib/types.ts` (after `User`)
- Create: `apps/web/components/NotificationPreferencesForm.tsx`
- Test: `apps/web/tests/components/NotificationPreferencesForm.test.tsx`

**Interfaces:**
- Consumes: `PUT /api/v1/account/notification-preferences` (Task 3); `FormMessage` (`components/FormMessage.tsx`).
- Produces: `export type NotificationPreferences = { whatsapp: boolean; sms: boolean; phone_valid: boolean }`; `export function isNotificationPreferences(value: unknown): value is NotificationPreferences`; default export `NotificationPreferencesForm({ initial, phone }: { initial: NotificationPreferences; phone: string | null })`.

- [ ] **Step 1: Write the failing tests**

```tsx
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificationPreferencesForm from "@/components/NotificationPreferencesForm";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const off = { whatsapp: false, sms: false, phone_valid: true };
const save = () => fireEvent.click(screen.getByRole("button", { name: "Save notification settings" }));
const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });

describe("NotificationPreferencesForm (ENH-014)", () => {
  it("shows email and in-app as always on and not changeable", () => {
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    for (const name of ["Email", "In-app"]) {
      const box = screen.getByRole("checkbox", { name: new RegExp(`^${name}`) });
      expect(box).toBeChecked();
      expect(box).toBeDisabled();
    }
    expect(screen.getAllByText("Always on")).toHaveLength(2);
    expect(screen.getByText("Messages go to +91 98765 43210")).toBeInTheDocument();
  });

  it("disables turning WhatsApp or SMS on without a valid phone and explains why", () => {
    render(<NotificationPreferencesForm initial={{ ...off, phone_valid: false }} phone={null} />);
    const whatsapp = screen.getByRole("checkbox", { name: /^WhatsApp/ });
    expect(whatsapp).toBeDisabled();
    expect(whatsapp).toHaveAttribute("aria-describedby", "notification-phone-hint");
    expect(screen.getByRole("link", { name: "Add a mobile number" })).toHaveAttribute("href", "#profile-phone");
  });

  it("keeps a checked channel enabled so it can be turned off without a phone", () => {
    render(<NotificationPreferencesForm initial={{ whatsapp: true, sms: false, phone_valid: false }} phone={null} />);
    expect(screen.getByRole("checkbox", { name: /^WhatsApp/ })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: /^SMS/ })).toBeDisabled();
  });

  it("PUTs exactly the two booleans and announces success", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ whatsapp: true, sms: false, phone_valid: true }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    fireEvent.click(screen.getByRole("checkbox", { name: /^WhatsApp/ }));
    save();
    expect(await screen.findByRole("status")).toHaveTextContent("Notification settings saved.");
    const [url, init] = vi.mocked(global.fetch).mock.calls[0];
    expect(url).toBe("/api/v1/account/notification-preferences");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({ whatsapp: true, sms: false });
    expect(screen.getByRole("button", { name: "Save notification settings" })).toHaveFocus();
  });

  it("ignores a second submit while saving and marks the form busy", async () => {
    let resolve: (r: Response) => void = () => undefined;
    vi.mocked(global.fetch).mockReturnValue(new Promise((r) => (resolve = r)));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    save();
    save();
    expect(global.fetch).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("form", { name: "Notification settings" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("button", { name: "Saving…" })).toHaveAttribute("aria-disabled", "true");
    resolve(ok(off));
    await screen.findByText("Notification settings saved.");
  });

  it("shows the server's 422 message and reverts the checkboxes", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "Add a valid mobile number to your profile first" }), { status: 422 }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    const sms = screen.getByRole("checkbox", { name: /^SMS/ });
    fireEvent.click(sms);
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Add a valid mobile number to your profile first");
    expect(sms).not.toBeChecked();
  });

  it("shows a retryable message on a network error or a 5xx and reverts", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(new Response("oops", { status: 500 }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    const whatsapp = screen.getByRole("checkbox", { name: /^WhatsApp/ });
    for (let i = 0; i < 2; i += 1) {
      fireEvent.click(whatsapp);
      save();
      expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save your settings. Check your connection and try again.");
      await waitFor(() => expect(whatsapp).not.toBeChecked());
    }
  });

  it("shows the session-expired block on 401", async () => {
    vi.mocked(global.fetch).mockResolvedValue(new Response("{}", { status: 401 }));
    render(<NotificationPreferencesForm initial={off} phone="+91 98765 43210" />);
    save();
    expect(await screen.findByText("Your session has expired. Sign in again to change your notification settings.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/web && npm test -- tests/components/NotificationPreferencesForm.test.tsx`
Expected: FAIL — cannot resolve `@/components/NotificationPreferencesForm`.

- [ ] **Step 3: Implement**

`apps/web/lib/types.ts`, after the `User` type:

```ts
// ENH-014 (spec §5.1): GET/PUT /api/v1/account/notification-preferences.
export type NotificationPreferences = { whatsapp: boolean; sms: boolean; phone_valid: boolean };
export function isNotificationPreferences(value: unknown): value is NotificationPreferences {
  const v = value as Partial<NotificationPreferences> | null;
  return !!v && typeof v.whatsapp === "boolean" && typeof v.sms === "boolean" && typeof v.phone_valid === "boolean";
}
```

`apps/web/components/NotificationPreferencesForm.tsx`:

```tsx
"use client";

import { type CSSProperties, type FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { isNotificationPreferences, type NotificationPreferences } from "@/lib/types";

// ENH-014 (spec §7): WhatsApp/SMS opt-in. Consent is deliberate, so toggles never autosave -- the user presses Save.
// Same patterns as ProfileForm: a ref guards double submits, "Saving…" is announced but visually hidden, focus returns
// to the button after a save. Server-side validation is the source of truth (a 422 message is shown as-is).
const VISUALLY_HIDDEN: CSSProperties = { position: "absolute", width: 1, height: 1, overflow: "hidden", clip: "rect(0 0 0 0)", whiteSpace: "nowrap" };
const NEXT = encodeURIComponent("/account/profile");
const HINT_ID = "notification-phone-hint";
const SAVE_FAILED = "Couldn't save your settings. Check your connection and try again.";

type Channel = "whatsapp" | "sms";
type Choice = Record<Channel, boolean>;

export default function NotificationPreferencesForm({ initial, phone }: { initial: NotificationPreferences; phone: string | null }) {
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState<Choice>({ whatsapp: initial.whatsapp, sms: initial.sms });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);
  const [signedOut, setSignedOut] = useState(false);
  const [focusTick, setFocusTick] = useState(0);
  const submitting = useRef(false);
  const saveButton = useRef<HTMLButtonElement>(null);

  // A phone saved in ProfileForm triggers router.refresh(); the server sends new props (phone_valid may change).
  useEffect(() => {
    setSaved(initial);
    setDraft({ whatsapp: initial.whatsapp, sms: initial.sms });
  }, [initial.whatsapp, initial.sms, initial.phone_valid]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (focusTick) saveButton.current?.focus();
  }, [focusTick]);

  function finish(next: FormMessageState | null) {
    setMessage(next);
    submitting.current = false;
    setBusy(false);
    setFocusTick((t) => t + 1);
  }

  function revert(text: string) {
    setDraft({ whatsapp: saved.whatsapp, sms: saved.sms });
    finish({ text, failed: true });
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setMessage(null);
    setSignedOut(false);
    let response: Response;
    try {
      response = await fetch("/api/v1/account/notification-preferences", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(draft) });
    } catch {
      revert(SAVE_FAILED);
      return;
    }
    const body: unknown = await response.json().catch(() => null);
    if (response.ok && isNotificationPreferences(body)) {
      setSaved(body);
      setDraft({ whatsapp: body.whatsapp, sms: body.sms });
      finish({ text: "Notification settings saved.", failed: false });
      return;
    }
    if (response.status === 401) {
      setSignedOut(true);
      setDraft({ whatsapp: saved.whatsapp, sms: saved.sms });
      finish(null);
      return;
    }
    const detail = (body as { detail?: unknown } | null)?.detail;
    revert(response.status === 422 && typeof detail === "string" ? detail : SAVE_FAILED);
  }

  const canTurnOn = saved.phone_valid;
  const channels: { key: Channel; label: string; detail: string }[] = [
    { key: "whatsapp", label: "WhatsApp", detail: phone ? `Messages go to ${phone}` : "" },
    { key: "sms", label: "SMS", detail: phone ? `Texts go to ${phone}` : "" },
  ];

  return (
    <form className="form" onSubmit={submit} aria-label="Notification settings" aria-busy={busy} noValidate>
      <fieldset className="form-section">
        <legend>Send me updates by</legend>
        {[
          { id: "notify-email", label: "Email" },
          { id: "notify-in-app", label: "In-app" },
        ].map((row) => (
          <label key={row.id} className="pf-check" htmlFor={row.id}>
            <input id={row.id} type="checkbox" checked disabled readOnly aria-describedby={`${row.id}-hint`} />
            <span>
              {row.label} <span id={`${row.id}-hint`} className="field-hint">Always on</span>
            </span>
          </label>
        ))}
        {channels.map(({ key, label, detail }) => {
          const locked = !canTurnOn && !draft[key];
          return (
            <label key={key} className="pf-check" htmlFor={`notify-${key}`}>
              <input
                id={`notify-${key}`}
                type="checkbox"
                checked={draft[key]}
                disabled={locked}
                aria-describedby={canTurnOn ? undefined : HINT_ID}
                onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.checked }))}
              />
              <span>
                {label} {detail && <span className="field-hint">{detail}</span>}
              </span>
            </label>
          );
        })}
        {!canTurnOn && (
          <p id={HINT_ID} className="field-hint">
            <a href="#profile-phone">Add a mobile number</a> in your profile above to turn on WhatsApp or SMS.
          </p>
        )}
        <p className="field-hint">By turning on WhatsApp or SMS you agree to receive these messages from EduSphere. You can turn them off here at any time.</p>
      </fieldset>
      {message && <FormMessage message={message} />}
      {signedOut && (
        <div className="form-error" role="alert" aria-live="assertive">
          <p style={{ margin: 0 }}>Your session has expired. Sign in again to change your notification settings.</p>
          <p style={{ margin: "6px 0 0" }}>
            <Link href={`/it/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>IT Training sign in</Link>{" "}
            <Link href={`/overseas/login?next=${NEXT}`} style={{ color: "var(--blue)", fontWeight: 800 }}>Overseas Education sign in</Link>
          </p>
        </div>
      )}
      {busy && (
        <div role="status" aria-live="polite" style={VISUALLY_HIDDEN}>
          Saving your notification settings…
        </div>
      )}
      <button ref={saveButton} className="btn" aria-disabled={busy}>
        {busy ? "Saving…" : "Save notification settings"}
      </button>
    </form>
  );
}
```

Note: while `busy`, the visually hidden status is the only `role="status"` — the success test's `findByRole("status")` resolves after saving finishes. If Testing Library finds two status regions, scope it with `findByText("Notification settings saved.")` instead.

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- tests/components/NotificationPreferencesForm.test.tsx && npm run typecheck && npm run lint`
Expected: all pass, no type or lint errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/lib/types.ts apps/web/components/NotificationPreferencesForm.tsx apps/web/tests/components/NotificationPreferencesForm.test.tsx
git commit -m "feat(enh-014): notification preferences form with consent copy and full states"
```

---

### Task 11: Profile page section and phone refresh

**Files:**
- Modify: `apps/web/app/account/profile/page.tsx`
- Modify: `apps/web/components/ProfileForm.tsx`
- Modify: `apps/web/tests/components/AccountProfilePage.test.tsx`, `apps/web/tests/components/ProfileForm.test.tsx`

**Interfaces:**
- Consumes: `NotificationPreferencesForm`, `isNotificationPreferences`, `NotificationPreferences` (Task 10); `serverApi` (`lib/api`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/components/AccountProfilePage.test.tsx` (import `NotificationPreferencesForm` at the top):

```tsx
const prefs = { whatsapp: true, sms: false, phone_valid: true };
function byPath(overrides: { me?: unknown; prefs?: unknown | Error } = {}) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/account/notification-preferences") {
      if (overrides.prefs instanceof Error) throw overrides.prefs;
      return overrides.prefs ?? prefs;
    }
    return overrides.me ?? user();
  });
}

describe("/account/profile notification section (ENH-014)", () => {
  it("renders the preferences form with the saved values and the user's phone", async () => {
    byPath();
    const tree = await render();
    const form = tree.find((el) => el.type === NotificationPreferencesForm)!;
    expect(form.props.initial).toEqual(prefs);
    expect(form.props.phone).toBe("+91 90000 00000");
    expect(text(tree.find((el) => el.type === "h2")!)).toBe("Notifications");
  });

  it("shows a section-only error when preferences fail to load, keeping the profile form", async () => {
    byPath({ prefs: new Error("boom") });
    const tree = await render();
    expect(tree.find((el) => el.type === ProfileForm)).toBeDefined();
    expect(tree.find((el) => el.type === NotificationPreferencesForm)).toBeUndefined();
    expect(tree.some((el) => text(el) === "We couldn't load your notification settings right now.")).toBe(true);
  });

  it("treats a malformed preferences body as a load failure", async () => {
    byPath({ prefs: { whatsapp: "yes" } });
    const tree = await render();
    expect(tree.find((el) => el.type === NotificationPreferencesForm)).toBeUndefined();
  });
});
```

Add to `tests/components/ProfileForm.test.tsx` (top of file):

```tsx
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));
```

and a test:

```tsx
  it("refreshes the page once after a successful save (ENH-014: phone validity for the notification section)", async () => {
    refresh.mockClear();
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ full_name: "Asha Rao", phone: "+91 98765 43210" }), { status: 200 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("Your profile was updated.");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh after a failed save", async () => {
    refresh.mockClear();
    vi.mocked(global.fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "bad" }), { status: 422 }));
    render(<ProfileForm fullName="Asha Rao" phone={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("bad");
    expect(refresh).not.toHaveBeenCalled();
  });
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- tests/components/AccountProfilePage.test.tsx tests/components/ProfileForm.test.tsx`
Expected: the new tests FAIL (no `NotificationPreferencesForm` in the tree; `refresh` not called). Existing tests still pass.

- [ ] **Step 3: Implement**

`components/ProfileForm.tsx` — add `import { useRouter } from "next/navigation";`, `const router = useRouter();` at the top of the component, and in the `response.ok` branch after `setNotice(...)`:

```tsx
      // ENH-014: the notification section below reads phone validity from the server; refresh it after a phone change.
      router.refresh();
```

`app/account/profile/page.tsx` — imports:

```tsx
import NotificationPreferencesForm from "@/components/NotificationPreferencesForm";
import { isNotificationPreferences, type NotificationPreferences, type User } from "@/lib/types";
```

After the `/auth/me` try/catch succeeds (so today's signed-out and unavailable branches are unchanged), load preferences without blocking the page on failure:

```tsx
  let preferences: NotificationPreferences | null = null;
  try {
    const loaded: unknown = await serverApi<unknown>("/api/v1/account/notification-preferences");
    preferences = isNotificationPreferences(loaded) ? loaded : null;
  } catch {
    preferences = null; // this section only; the profile form still renders
  }
```

and after the existing profile `action-card`:

```tsx
          <h2 style={{ marginTop: 28 }}>Notifications</h2>
          <p className="muted">Choose where we send updates about results, sessions and applications.</p>
          <div className="action-card">
            {preferences ? (
              <NotificationPreferencesForm initial={preferences} phone={user.phone ?? null} />
            ) : (
              <div className="form-error" role="alert">
                <p style={{ margin: 0 }}>We couldn&apos;t load your notification settings right now.</p>
                <p style={{ margin: "6px 0 0" }}>
                  <a href="/account/profile" style={{ color: "var(--blue)", fontWeight: 800 }}>Try again</a>
                </p>
              </div>
            )}
          </div>
```

(The spec's `Promise.allSettled` is replaced by a sequential second call after `/auth/me` succeeds: it keeps the existing `/auth/me` error branches byte-for-byte and adds one short round-trip only for signed-in users. If profiling shows it matters, parallelise later without changing behaviour.)

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- tests/components/AccountProfilePage.test.tsx tests/components/ProfileForm.test.tsx tests/components/NotificationPreferencesForm.test.tsx && npm run typecheck && npm run lint && npm run build`
Expected: all pass; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add apps/web/app/account/profile/page.tsx apps/web/components/ProfileForm.tsx apps/web/tests/components/AccountProfilePage.test.tsx apps/web/tests/components/ProfileForm.test.tsx
git commit -m "feat(enh-014): notification settings section on the profile page"
```

---

### Task 12: End-to-end

**Files:**
- Create: `apps/web/tests/e2e/enh-014-notification-preferences.spec.ts`

**Interfaces:**
- Consumes: the running stack (`docker compose up`, seeded: `school.parent@edusphere.local` / `Demo@123`, `apps/api/app/seed.py:627`).

- [ ] **Step 1: Write the spec**

```ts
import { test, expect, type Page } from "@playwright/test";

// ENH-014 -- notification preferences on /account/profile. Uses the seeded School Parent and restores its phone and
// preferences at the end (shared seeded state, AGENTS.md "Test caveats").
const PREFS = "/api/v1/account/notification-preferences";

async function signIn(page: Page) {
  await page.goto("/overseas/login");
  await page.fill("#login-email", "school.parent@edusphere.local");
  await page.fill("#login-password", "Demo@123");
  await page.click("button:has-text('Sign in securely')");
  await page.waitForURL("**/school/parent/**");
  await page.goto("/account/profile");
}

async function restore(page: Page, phone: string) {
  await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
  await page.request.patch("/api/v1/auth/me", { data: { phone: phone || null } });
}

test("a parent adds a phone, turns on WhatsApp, and it persists", async ({ page }) => {
  await signIn(page);
  const originalPhone = await page.locator("#profile-phone").inputValue();
  try {
    await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
    await page.request.patch("/api/v1/auth/me", { data: { phone: null } });
    await page.reload();

    const whatsapp = page.getByRole("checkbox", { name: /^WhatsApp/ });
    await expect(whatsapp).toBeDisabled();
    await expect(page.getByText("in your profile above to turn on WhatsApp or SMS.")).toBeVisible();

    await page.fill("#profile-phone", "+91 98765 43210");
    await page.click("button:has-text('Save changes')");
    await expect(page.getByText("Your profile was updated.")).toBeVisible();
    await expect(whatsapp).toBeEnabled(); // router.refresh(), no manual reload

    await whatsapp.check();
    await page.getByRole("button", { name: "Save notification settings" }).click();
    await expect(page.getByText("Notification settings saved.")).toBeVisible();
    await page.reload();
    await expect(page.getByRole("checkbox", { name: /^WhatsApp/ })).toBeChecked();
    await expect(page.getByRole("checkbox", { name: /^Email/ })).toBeDisabled();
  } finally {
    await restore(page, originalPhone);
  }
});

test("keyboard only: tab to SMS, toggle with Space, save with Enter", async ({ page }) => {
  await signIn(page);
  const originalPhone = await page.locator("#profile-phone").inputValue();
  try {
    await page.request.patch("/api/v1/auth/me", { data: { phone: "+91 98765 43210" } });
    await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
    await page.reload();
    const sms = page.getByRole("checkbox", { name: /^SMS/ });
    await sms.focus();
    await page.keyboard.press("Space");
    await expect(sms).toBeChecked();
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Save notification settings" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Notification settings saved.")).toBeVisible();
    await expect(page.getByRole("button", { name: "Save notification settings" })).toBeFocused();
  } finally {
    await restore(page, originalPhone);
  }
});

for (const width of [320, 1440]) {
  test(`fits ${width}px with no horizontal scroll and labelled controls`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await signIn(page);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
    await expect(page.getByRole("heading", { level: 2, name: "Notifications" })).toBeVisible();
    await expect(page.getByRole("group", { name: "Send me updates by" })).toBeVisible();
    for (const name of [/^Email/, /^In-app/, /^WhatsApp/, /^SMS/]) {
      const box = page.getByRole("checkbox", { name });
      await expect(box).toBeVisible();
      const row = await box.locator("xpath=ancestor::label").boundingBox();
      expect(row!.height).toBeGreaterThanOrEqual(44);
    }
  });
}

test("a failed save shows a retryable alert, reverts the box, and leaves the profile form usable", async ({ page }) => {
  await signIn(page);
  const originalPhone = await page.locator("#profile-phone").inputValue();
  try {
    await page.request.patch("/api/v1/auth/me", { data: { phone: "+91 98765 43210" } });
    await page.request.put(PREFS, { data: { whatsapp: false, sms: false } });
    await page.reload();
    // Only the browser's PUT is intercepted; the server-rendered GET (and page.request) are not.
    await page.route(`**${PREFS}`, (route) => (route.request().method() === "PUT" ? route.fulfill({ status: 500, body: "{}" }) : route.continue()));
    const sms = page.getByRole("checkbox", { name: /^SMS/ });
    await sms.check();
    await page.getByRole("button", { name: "Save notification settings" }).click();
    await expect(page.getByRole("alert")).toContainText("Couldn't save your settings. Check your connection and try again.");
    await expect(sms).not.toBeChecked();
    await expect(page.locator("#profile-full-name")).toBeEditable();
  } finally {
    await page.unroute(`**${PREFS}`);
    await restore(page, originalPhone);
  }
});
```

(The server-side load failure is covered by the Task 11 unit test; Playwright can only intercept browser requests.)

- [ ] **Step 2: Rebuild and run**

Run: `docker compose build api web && docker compose up -d --force-recreate api worker beat web`, then `cd apps/web && npx playwright test tests/e2e/enh-014-notification-preferences.spec.ts --workers=1`
Expected: 5 passed. A first-run failure right after a web rebuild: re-run once before diagnosing (AGENTS.md caveat).

- [ ] **Step 3: Run the impacted existing specs**

Run: `npx playwright test tests/e2e/enh-007-profile-self-service.spec.ts tests/e2e/sch-007-parent-portal.spec.ts tests/e2e/enh-023-tier-change.spec.ts tests/e2e/enh-005-school-transfer.spec.ts tests/e2e/ovs-004-status-tracking.spec.ts tests/e2e/sec-002-gdpr-data-requests.spec.ts --workers=1`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add apps/web/tests/e2e/enh-014-notification-preferences.spec.ts
git commit -m "test(enh-014): e2e for notification preferences, keyboard and responsive"
```

---

### Task 13: Worker smoke check, documentation, full regression

**Files:**
- Modify: `docs/architecture/API_CONTRACT.md` (account section: the two routes; `/communications/notify` status note)
- Modify: `docs/architecture/DATA_MODEL.md` (§7.1: `notification_preferences`, `notification_deliveries.context`, status values)
- Modify: `docs/architecture/INTEGRATION_CONTRACTS.md` §4 (Twilio adapter, retry policy D11, no delivery callbacks in slice 1)
- Modify: `docs/features/MASTER_FEATURE_CATALOG.md` and `docs/features/FEATURE_ACCEPTANCE_CRITERIA.md` (ENH-014-AC01…AC16; NOT-002/NOT-003 no longer credential-blocked for sandbox)
- Modify: `docs/ux/SCREEN_CATALOG.md` (`/account/profile` Notifications section and its states)
- Modify: `docs/product/PRD_OPEN_ITEMS.md` item 13 and `BRD_OPEN_ITEMS.md` items 13/14 (resolved by `DEC-NOT-001` 2026-09-30 for slice 1)
- Modify: `docs/delivery/ENHANCEMENT_BACKLOG.md` §ENH-014 (status: slice 1 complete; help desk, Student/Teacher recipients, push, delivery callbacks as follow-ups)
- Modify: `.env.example` if it exists (add the five `TWILIO_*` keys with empty values)

- [ ] **Step 1: Worker smoke check against the running stack (sandbox or unconfigured)**

With the stack up, as a coordinator create a school activity in the UI (or `POST /api/v1/school/activities`), then:

Run: `docker compose exec api python -c "import asyncio; from sqlalchemy import select; from app.core.database import SessionLocal; from app.models import NotificationDelivery as D;
async def m():
    async with SessionLocal() as db:
        rows = (await db.scalars(select(D).order_by(D.created_at.desc()).limit(5))).all()
        print([(r.channel, r.status, r.attempt_count) for r in rows])
asyncio.run(m())"`
Expected: within a few seconds the newest rows move from `queued` to a final status (`not_configured` without SMTP/Twilio, `sent` with sandbox credentials), `attempt_count` 1. Repeat once more to prove a second task in the same worker process also completes (the event-loop/pool disposal). `docker compose logs worker --tail 50` shows `notification_delivery` lines with no phone, email or text.

If Twilio sandbox credentials are available (D8): set the five `TWILIO_*` values in the local `.env` (never committed), recreate `api worker beat`, opt a sandbox-joined test phone in, publish a result, and confirm the WhatsApp message arrives and the row holds an `SM…` `provider_reference`. Record the outcome (not the number) in the release evidence.

- [ ] **Step 2: Update the documents listed above**

Each update states what changed and cites the spec section and `DEC-NOT-001` (2026-09-30). Do not modify `docs/sources/`.

- [ ] **Step 3: Full regression (cross-cutting change — AGENTS.md step 4)**

Run: `docker compose exec api python -m pytest -q` then `cd apps/web && npm test && npm run typecheck && npm run lint && npm run build`
Expected: all pass. Report failures with their output; known shared-DB flakes are re-run alone per `pending.md` before being classified.

- [ ] **Step 4: Commit**

```bash
git add docs/ .env.example
git commit -m "docs(enh-014): contracts, data model, catalogue and backlog for notification channels slice 1"
```

---

## Spec coverage map

| Spec | Task |
|---|---|
| §4 data model, index, classification | 1 |
| §5.1–5.2 preference API, CSRF/rate-limit rationale | 3 |
| §5.3 `/communications/notify`, export | 8, 9 |
| §6.1 dispatch, after-commit, `retry=False` | 4 |
| §6.2 helper bodies, erasure | 8, 9 |
| §6.3 phone | 2 |
| §6.4 Twilio adapter, link allow-list, redaction | 5 |
| §6.5 worker, retries, sweeper | 6, 7 |
| §7 frontend | 10, 11 |
| §8 / §8.1 transactions, races, security | 3, 4, 5, 6, 7 |
| §9 AC01–AC16 | 3 (01–03, 15), 4 (04–05), 8 (04–06, 11), 6 (07–10, 12, 14), 5 (16), 9 (13) |
| §10 tests | every task; 12 (E2E); 13 (regression) |
