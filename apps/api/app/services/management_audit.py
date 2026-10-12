"""mgmt-002 (DEC-SCOPE-187 MA1-MA10): the management audit trail, EVID-017 §2's "who did what".

Every management write calls `record` in its own transaction, so the record and its audit row commit together. The read side lists
only the kinds the caller's M13 tier may see. Spec: docs/superpowers/specs/2026-10-12-mgmt-002-management-audit-trail-design.md.
"""

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.services.management_access import can_view_finance, can_view_operational, can_view_partner_only

IST = ZoneInfo("Asia/Kolkata")  # MA6: the date filter's days are India calendar days

# MA1: entity_type -> (label, tier). Each later mgmt item registers its own kind here.
KINDS: dict[str, tuple[str, str]] = {
    "mgmt.task": ("Task", "operational"),
    "mgmt.plan": ("Plan & target", "operational"),
    "mgmt.decision": ("Decision", "operational"),
    "mgmt.ledger": ("Ledger entry", "finance"),
    "mgmt.investment": ("Investment", "partner_only"),
    "mgmt.capital": ("Capital account", "partner_only"),
}
VERBS = frozenset({"create", "update", "approve", "complete", "decide", "import"})  # MA2
_CAN_VIEW = {"operational": can_view_operational, "finance": can_view_finance, "partner_only": can_view_partner_only}


def _value(value) -> str | None:
    return None if value is None else str(value)


def record(db: AsyncSession, actor: User, kind: str, verb: str, entity_id: str | None, *, fields: Sequence[str] = (),
           values: dict[str, tuple] | None = None, count: int | None = None) -> AuditLog:
    """Adds one audit row to the caller's session (no commit, MA10). Field names always; before/after values only for finance and
    partner-only kinds and only for the fields named (MA3, Q-33 interim). A bulk write is one row with a `count` (MA4)."""
    if kind not in KINDS:
        raise ValueError(f"Unregistered management kind: {kind}")
    if verb not in VERBS:
        raise ValueError(f"Unknown management verb: {verb}")
    metadata: dict = {"fields": list(fields)}
    if values:
        if KINDS[kind][1] == "operational":
            raise ValueError(f"{kind} records field names only")
        if not set(values) <= set(fields):
            raise ValueError("A value is recorded only for a field the entry names")
        metadata["values"] = {name: {"before": _value(before), "after": _value(after)} for name, (before, after) in values.items()}
    if count is not None:
        metadata["count"] = count
    row = AuditLog(user_id=actor.id, action=f"{kind}.{verb}", entity_type=kind, entity_id=entity_id, metadata_json=metadata)
    db.add(row)
    return row


def visible_kinds(user: User) -> list[str]:
    """MA5: the kinds whose tier the caller can view."""
    return [kind for kind, (_, tier) in KINDS.items() if _CAN_VIEW[tier](user)]


def hidden_from_admin_audit():
    """MA8: the clause GET /admin/audit and its export add, leaving out finance and partner-only management rows (M13)."""
    return AuditLog.entity_type.not_in([kind for kind, (_, tier) in KINDS.items() if tier != "operational"])


def _ist_start(day: date) -> datetime:
    return datetime.combine(day, time.min, IST)


async def activity(db: AsyncSession, user: User, *, actor_id=None, kind: str | None = None, date_from: date | None = None,
                   date_to: date | None = None, limit: int = 25, offset: int = 0) -> dict:
    """MA5-MA7: newest first. A `kind` outside the caller's tiers is simply empty; the route has already refused an unknown one."""
    kinds = visible_kinds(user)
    selected = [k for k in kinds if k == kind] if kind else kinds
    where = [AuditLog.entity_type.in_(selected)]
    if actor_id:
        where.append(AuditLog.user_id == actor_id)
    if date_from:
        where.append(AuditLog.created_at >= _ist_start(date_from))
    if date_to:
        where.append(AuditLog.created_at < _ist_start(date_to + timedelta(days=1)))
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*where))
    query = (select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id).where(*where)
             .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset))
    rows = (await db.execute(query)).all()
    actors = (await db.execute(
        select(User.id, User.full_name, User.role).where(User.id.in_(select(AuditLog.user_id).where(AuditLog.entity_type.in_(kinds)))).order_by(User.full_name)
    )).all()
    return {
        "items": [
            {
                "id": row.id, "at": row.created_at, "kind": row.entity_type, "kind_label": KINDS[row.entity_type][0],
                "verb": row.action.rsplit(".", 1)[-1], "entity_id": row.entity_id,
                "actor": {"id": who.id, "full_name": who.full_name, "role": who.role} if who else None,
                "fields": row.metadata_json.get("fields", []), "values": row.metadata_json.get("values"), "count": row.metadata_json.get("count"),
            }
            for row, who in rows
        ],
        "total": total, "limit": limit, "offset": offset,
        "kinds": [{"value": k, "label": KINDS[k][0]} for k in kinds],
        "actors": [{"id": i, "full_name": n, "role": r} for i, n, r in actors],
    }
