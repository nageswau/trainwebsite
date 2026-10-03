"""AGN-019 -- staff performance and the student funnel (DEC-SCOPE-063; spec §4-§5).

Master only (the route refuses staff). Students count for their current owner (P1), selected by the day their agency record was
created (P4). Read-only: nothing here writes, locks or commits."""

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentOrgMember, User

TABLE = ("students", "applications", "offers", "visa_applications", "visa_approvals", "enrollments")
STAGES = ("students", "applications", "submitted", "offers", "visa", "enrolled")
NONE = (0,) * 6


def _counts(table: tuple, funnel: tuple) -> dict:
    return {**dict(zip(TABLE, table, strict=True)), "funnel": dict(zip(STAGES, funnel, strict=True))}


def _any(counts: dict) -> bool:
    return any(counts[k] for k in TABLE) or any(counts["funnel"].values())


def _sum(parts: list[dict]) -> dict:
    return {**{k: sum(p[k] for p in parts) for k in TABLE}, "funnel": {k: sum(p["funnel"][k] for p in parts) for k in STAGES}}


async def performance(db: AsyncSession, user: User, start: date | None, end: date | None) -> dict:
    """The AGN-019 payload (spec §5.3). Rows (P6): every active staff member; a deactivated one only while they have counts."""
    table: dict = {}
    funnel: dict = {}

    def counts(key) -> dict:
        return _counts(table.get(key, NONE), funnel.get(key, NONE))

    members = await db.execute(
        select(AgentOrgMember, User.full_name)
        .join(User, User.id == AgentOrgMember.user_id)
        .where(AgentOrgMember.org_id == user.agent_membership.org_id, AgentOrgMember.role == "staff")
        .order_by(AgentOrgMember.seq)
    )
    rows = []
    for member, name in members.all():
        row = counts(member.id)
        active = member.status == "active"
        if active or _any(row):
            rows.append({"code": member.code, "name": name, "active": active, **row})
    unassigned = counts(None)
    unassigned = unassigned if _any(unassigned) else None
    parts = [*rows, *([unassigned] if unassigned else [])]
    return {
        "date_from": start,
        "date_to": end,
        "rows": rows,
        "unassigned": unassigned,
        "total": _sum(parts) if parts else _counts(NONE, NONE),
        "as_of": datetime.now(UTC),
    }
