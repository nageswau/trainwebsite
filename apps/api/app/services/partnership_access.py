"""upc-001 (DEC-SCOPE-118 PU9, backlog U2): who may see university commission data -- terms, per-course commission, expected and
received, and the commission search filter. Every other role gets those fields stripped server-side. upc-016 (DEC-SCOPE-144 CM12) adds
`strip_commission` with the fields it owns (upc-017 adds the course `commission`), and Management M3 adds the `partner` role here when that
role exists."""

from app.models import User

COMMISSION_ROLES = frozenset({"super_admin", "partnership_manager", "partnership_head"})
COMMISSION_FIELDS = frozenset({"commission_terms", "commission"})  # upc-016: an agreement's terms; upc-017 (CO2): a course's commission


def can_see_commission(user: User) -> bool:
    return user.role in COMMISSION_ROLES


def strip_commission(user: User, payload: dict) -> dict:
    """The payload as this user may see it: unchanged for a commission role, otherwise a copy without the commission fields."""
    if can_see_commission(user):
        return payload
    return {k: v for k, v in payload.items() if k not in COMMISSION_FIELDS}
