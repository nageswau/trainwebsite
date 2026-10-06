"""tel-007 test builders. Every value is unique per call: the test database is shared and never truncated, so rules use fresh products
and cities, and round-robin tests narrow the team's pool inside an uncommitted transaction (`only_eligible`) that the test rolls back."""

import uuid

from sqlalchemy import update

from app.models import Enquiry, TelDistributionRule, TelProduct, User
from tests.tel004_helpers import login, make_telecaller, make_tl_manager, make_user

__all__ = ["city", "lead", "login", "make_telecaller", "make_tl_manager", "make_user", "only_eligible", "product", "rule"]

RULES, UNASSIGNED, ASSIGNED, ASSIGN = (
    "/api/v1/telecaller/distribution-rules", "/api/v1/telecaller/leads/unassigned", "/api/v1/telecaller/leads/assigned", "/api/v1/telecaller/leads/assign",
)


def city() -> str:
    return f"City {uuid.uuid4().hex[:8]}"


async def product(db, *, group: str = "it", team: str | None = "it", active: bool = True) -> TelProduct:
    row = TelProduct(product_group=group, name=f"Product {uuid.uuid4().hex[:8]}", team=team, active=active)
    db.add(row)
    await db.commit()
    return row


async def rule(db, telecaller: User, *, team: str = "it", product_id=None, city_name: str | None = None) -> TelDistributionRule:
    row = TelDistributionRule(team=team, kind="product" if product_id else "city", product_id=product_id, city=city_name, telecaller_user_id=telecaller.id)
    db.add(row)
    await db.commit()
    return row


async def lead(db, *, division: str = "it", product_id=None, city_name: str | None = None, telecaller: User | None = None, status: str = "new") -> Enquiry:
    row = Enquiry(division=division, name=f"Lead {uuid.uuid4().hex[:6]}", email=f"{uuid.uuid4().hex[:8]}@example.local", subject="Python",
                  message="Hello", source="website", status=status, product_id=product_id, city=city_name,
                  telecaller_user_id=telecaller.id if telecaller else None)
    db.add(row)
    await db.commit()
    return row


async def only_eligible(db, team: str, keep: list[User]) -> None:
    """Uncommitted: every other telecaller on `team` is inactive for the rest of this transaction. The caller must roll back."""
    keep_ids = [u.id for u in keep] or [uuid.uuid4()]
    await db.execute(update(User).where(User.role == "telecaller", User.division == team, User.id.not_in(keep_ids)).values(active=False))
