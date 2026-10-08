"""upc-001 (DEC-SCOPE-116 PU9, backlog U2): who may see university commission data -- terms, per-course commission, expected and
received, and the commission search filter. Every other role gets those fields stripped server-side; upc-016 adds `strip_commission`
with the fields it owns, and Management M3 adds the `partner` role here when that role exists."""

from app.models import User

COMMISSION_ROLES = frozenset({"super_admin", "partnership_manager", "partnership_head"})


def can_see_commission(user: User) -> bool:
    return user.role in COMMISSION_ROLES
