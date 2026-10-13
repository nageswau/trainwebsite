"""dtu-001 (DEC-SCOPE-209 §5, DT4/DT5/DT13): who sees and edits the agent commission -- what EduSphere pays an agent Master for a
university (DT2). Not upc-016's university commission: `partnership_access` stays as it is (DT7). The key is added only for a viewer,
so every other caller's payload has no `agent_commission` key at all."""

from app.core.rbac import agent_denial_reason, is_agent_staff
from app.models import University, User


def can_edit_agent_commission(user: User) -> bool:
    return user.role == "super_admin" or (user.role == "overseas_admin" and user.division == "overseas")


def can_view_agent_commission(user: User) -> bool:
    if can_edit_agent_commission(user):
        return True
    return user.role == "agent" and user.division == "overseas" and not is_agent_staff(user) and not agent_denial_reason(user)


def _money(value) -> str | None:
    return None if value is None else f"{value:.2f}"


def agent_commission_out(uni: University) -> dict | None:
    if uni.agent_commission_percent is None and uni.agent_commission_amount is None:
        return None
    return {
        "percent": _money(uni.agent_commission_percent),
        "amount": _money(uni.agent_commission_amount),
        "currency": uni.agent_commission_currency,
        "note": uni.agent_commission_note,
    }


def with_agent_commission(user: User, uni: University, payload: dict) -> dict:
    return {**payload, "agent_commission": agent_commission_out(uni)} if can_view_agent_commission(user) else payload
