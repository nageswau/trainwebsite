"""hrc-003 (DEC-SCOPE-370): "this record changed since you opened it". A form sends the token it was given (`updated_at`, or a JD's
version number); a different one is a 409 `record_changed` telling the user who changed what and when, with the current record, so a
stale form never silently overwrites someone else's save. No token = no check (S2: optional until every client sends it).

Callers check under the row lock they already hold, after scope and role, before any business rule (S5)."""

from collections.abc import Awaitable, Callable
from datetime import datetime

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

MESSAGE = "This record changed since you opened it"


async def require_fresh(
    db: AsyncSession,
    *,
    stored,
    expected,
    entity: tuple[str, object],
    action_prefix: str,
    since: datetime | None,
    current: Callable[[], Awaitable[dict]],
    fields: list[str] | None = None,
) -> None:
    """S4: who/what/when from the record's own audit rows written after `since` (when the client's version was written; None = all).
    `entity` = those rows' (entity_type, entity_id). `fields` overrides the audit's field names when the caller can diff exactly."""
    if expected is None or expected == stored:
        return
    entity_type, entity_id = entity
    query = select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id).where(
        AuditLog.entity_type == entity_type, AuditLog.entity_id == str(entity_id), AuditLog.action.startswith(action_prefix),
        ~AuditLog.action.endswith("download"),  # a read, not a change
        ~AuditLog.action.endswith("_link"),  # hrc-015: a signed link issued is a read too
    )
    if since is not None:
        query = query.where(AuditLog.created_at > since)
    rows = (await db.execute(query.order_by(AuditLog.created_at))).all()
    if fields is None:
        fields = []
        for audit, _actor in rows:
            named = (audit.metadata_json or {}).get("fields")
            fields += [f for f in (named if isinstance(named, list) else [audit.action.rsplit(".", 1)[-1]]) if f not in fields]
    last, actor = rows[-1] if rows else (None, None)
    raise HTTPException(409, jsonable_encoder({
        "code": "record_changed",
        "message": MESSAGE,
        "changed_by": {"id": actor.id, "full_name": actor.full_name} if actor else None,
        "changed_at": last.created_at if last else (stored if isinstance(stored, datetime) else None),
        "changed_fields": fields,
        "current": await current(),
    }))
