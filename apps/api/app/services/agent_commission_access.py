"""dtu-001 (DEC-SCOPE-209 §5, DT4/DT5/DT13): who sees and edits the agent commission -- what EduSphere pays an agent Master for a
university (DT2). Not upc-016's university commission: `partnership_access` stays as it is (DT7). The key is added only for a viewer,
so every other caller's payload has no `agent_commission` key at all."""

from app.core.rbac import agent_denial_reason, is_agent_staff
from app.models import OverseasCourse, University, User

AGENT_COMMISSION_REFUSAL = "Only a super admin or an overseas admin can change the agent commission"


def can_edit_agent_commission(user: User) -> bool:
    return user.role == "super_admin" or (user.role == "overseas_admin" and user.division == "overseas")


def can_view_agent_commission(user: User) -> bool:
    if can_edit_agent_commission(user):
        return True
    return user.role == "agent" and user.division == "overseas" and not is_agent_staff(user) and not agent_denial_reason(user)


def _money(value) -> str | None:
    return None if value is None else f"{value:.2f}"


def agent_commission_out(row: University | OverseasCourse) -> dict | None:
    """A university's or (ccrm-051) a course's own value; None when it has none."""
    if row.agent_commission_percent is None and row.agent_commission_amount is None:
        return None
    return {
        "percent": _money(row.agent_commission_percent),
        "amount": _money(row.agent_commission_amount),
        "currency": row.agent_commission_currency,
        "note": row.agent_commission_note,
    }


def effective_agent_commission(course: OverseasCourse, uni: University) -> dict | None:
    """ccrm-051 (DEC-SCOPE-327): the course's value overrides the university's; `source` says which one applies."""
    for source, row in (("course", course), ("university", uni)):
        if (value := agent_commission_out(row)) is not None:
            return {**value, "source": source}
    return None


def with_agent_commission(user: User, row: University | OverseasCourse, payload: dict) -> dict:
    return {**payload, "agent_commission": agent_commission_out(row)} if can_view_agent_commission(user) else payload
