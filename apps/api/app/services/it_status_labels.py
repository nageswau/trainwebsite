"""itc-005 (DEC-SCOPE-362; API §12JH) -- the IT team's labels, order and enable/disable of the fixed lead and lifecycle stages.

The state machines never change (S1): a row in `it_status_labels` only overrides how a code reads, where it sorts and -- for the states a
person chooses (S4) -- whether it is offered. No row = the code default. Lifecycle labels are resolved here for the it_lifecycle payloads
(S8); lead labels are resolved by the screens from `catalogue` (the lead payloads keep the canonical `status_label`). Every save is
audited with its before/after (S9). Nothing here commits except `save`."""

import logging

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import lead_stages
from app.models import Enquiry, Enrollment, ItStatusLabel, User
from app.services.audit_changes import audit_change

logger = logging.getLogger("app.it_status_labels")

TEAM = "it"
ACTION = "it.status_label.update"
LIFECYCLE_DEFAULTS = {
    "enrolled": "Enrolled", "fee_pending": "Fee pending", "partially_paid": "Partially paid", "paid": "Paid", "training_active": "Training active",
    "at_risk": "At risk", "completed": "Completed", "resume_submitted": "Resume submitted", "hr_screening": "HR screening", "interview": "Interview",
    "placed": "Placed", "not_placed": "Not placed", "closed": "Closed",
}  # fmt: skip
DEFAULTS: dict[str, dict[str, str]] = {"lead": lead_stages.STAGE_LABELS, "lifecycle": LIFECYCLE_DEFAULTS}
# S4: only what a person chooses may be turned off -- never Follow-up (the reopen and return target) nor a state the records decide
SWITCHABLE = {
    "lead": (lead_stages.MANUAL | lead_stages.COUNSELOR_MANUAL | lead_stages.CLOSED) - {lead_stages.REOPEN_TO},
    "lifecycle": frozenset({"not_placed", "closed"}),
}
STAFF_ONLY = "Only IT staff can read the status labels"
ADMIN_ONLY = "Only the IT Admin can change the status labels"
NOT_FOUND = "Status not found"
CANNOT_DISABLE = "This status is set by the system, so it cannot be turned off"
LABEL_TAKEN = "Another status already uses this label"
TURNED_OFF = "This status is turned off by the IT Admin"


def require_reader(user: User) -> None:
    if user.role != "super_admin" and (user.division != TEAM or user.role == "it_student"):
        raise HTTPException(403, STAFF_ONLY)


def require_admin(user: User) -> None:
    if (user.role, user.division) != ("it_admin", TEAM):
        raise HTTPException(403, ADMIN_ONLY)


async def _rows(db: AsyncSession, kind: str | None = None) -> dict[tuple[str, str], ItStatusLabel]:
    stmt = select(ItStatusLabel).where(ItStatusLabel.team == TEAM).execution_options(populate_existing=True)
    if kind:
        stmt = stmt.where(ItStatusLabel.kind == kind)
    return {(r.kind, r.code): r for r in (await db.scalars(stmt)).all()}


def _entry(kind: str, position: int, code: str, row: ItStatusLabel | None) -> dict:
    default = DEFAULTS[kind][code]
    return {
        "code": code, "label": row.label if row else default, "default_label": default, "sort_order": row.sort_order if row else (position + 1) * 10,
        "enabled": row.enabled if row else True, "can_disable": code in SWITCHABLE[kind],
    }  # fmt: skip


def _entries(kind: str, rows: dict) -> list[dict]:
    out = [(_entry(kind, i, code, rows.get((kind, code))), i) for i, code in enumerate(DEFAULTS[kind])]
    return [e for e, _ in sorted(out, key=lambda pair: (pair[0]["sort_order"], pair[1]))]


async def catalogue(db: AsyncSession) -> dict:
    """{lead: [...], lifecycle: [...]}, each ordered by sort_order, then catalogue position."""
    rows = await _rows(db)
    return {kind: _entries(kind, rows) for kind in DEFAULTS}


async def admin_catalogue(db: AsyncSession) -> dict:
    """The catalogue plus `in_use` (S5: IT leads in the stage / enrolments carrying the override) and who changed it last."""
    rows = await _rows(db)
    leads = dict((await db.execute(select(Enquiry.status, func.count()).where(Enquiry.division == TEAM).group_by(Enquiry.status))).all())
    overrides = dict((await db.execute(select(Enrollment.lifecycle_override, func.count()).where(Enrollment.lifecycle_override.is_not(None)).group_by(Enrollment.lifecycle_override))).all())
    by_ids = {r.updated_by_user_id for r in rows.values() if r.updated_by_user_id}
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_(by_ids)))).all()} if by_ids else {}
    out = {}
    for kind, counts in (("lead", leads), ("lifecycle", overrides)):
        out[kind] = [{**e, **_meta(rows.get((kind, e["code"])), people), "in_use": counts.get(e["code"], 0)} for e in _entries(kind, rows)]
    return out


def _meta(row: ItStatusLabel | None, people: dict) -> dict:
    by = people.get(row.updated_by_user_id) if row and row.updated_by_user_id else None
    return {"updated_at": row.updated_at if row else None, "updated_by": {"id": by.id, "full_name": by.full_name} if by else None}


async def labels(db: AsyncSession, kind: str) -> dict[str, str]:
    """{code: label} for every code of the kind -- one query; the caller resolves a whole payload with it (S8, per-call cache)."""
    rows = await _rows(db, kind)
    return {code: (rows[(kind, code)].label if (kind, code) in rows else default) for code, default in DEFAULTS[kind].items()}


async def is_enabled(db: AsyncSession, kind: str, code: str) -> bool:
    """False when the IT Admin turned the state off (S6). The caller raises its own refusal."""
    return await db.scalar(select(ItStatusLabel.enabled).where(ItStatusLabel.team == TEAM, ItStatusLabel.kind == kind, ItStatusLabel.code == code)) is not False


async def save(db: AsyncSession, actor: User, kind: str, code: str, label: str, sort_order: int, enabled: bool) -> dict:
    """Commits. An idempotent upsert of the override; 404 unknown status, 422 a clashing label or turning off a system state; audited."""
    require_admin(actor)
    if kind not in DEFAULTS or code not in DEFAULTS[kind]:
        raise HTTPException(404, NOT_FOUND)
    if not enabled and code not in SWITCHABLE[kind]:
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "enabled"), "msg": CANNOT_DISABLE, "input": enabled}])
    current = await labels(db, kind)
    if any(other != code and text.casefold() == label.casefold() for other, text in current.items()):
        raise RequestValidationError([{"type": "value_error", "loc": ("body", "label"), "msg": LABEL_TAKEN, "input": label}])
    row = (await _rows(db, kind)).get((kind, code))
    before = {k: _entry(kind, list(DEFAULTS[kind]).index(code), code, row)[k] for k in ("label", "sort_order", "enabled")}
    after = {"label": label, "sort_order": sort_order, "enabled": enabled}
    if before != after:
        values = {"team": TEAM, "kind": kind, "code": code, **after, "updated_by_user_id": actor.id}
        stmt = insert(ItStatusLabel).values(**values)
        await db.execute(stmt.on_conflict_do_update(index_elements=["team", "kind", "code"], set_={**after, "updated_by_user_id": actor.id, "updated_at": func.now()}))
        audit_change(db, actor, ACTION, "it_status_label", f"{kind}:{code}", before, after)
        logger.info("it_status_label_saved", extra={"extra_fields": {"actor_id": str(actor.id), "kind": kind, "code": code, "enabled": enabled}})
    await db.commit()
    return next(e for e in (await admin_catalogue(db))[kind] if e["code"] == code)
