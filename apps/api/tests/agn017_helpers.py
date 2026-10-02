"""AGN-017 test helpers. The tests' world is AGN-008's `agency_world` (Master, two staff, a student with no login and a linked one,
both assigned to `staff`; another agency)."""

from sqlalchemy import select

from app.models import AgentOrg, AgentOrgMember, Notification, NotificationDelivery, User


async def notices(db, user: User) -> list[Notification]:
    """The user's notifications, newest first (fresh from the database). Rows only -- `populate_existing`, not `expire_all()`, so
    the caller's other objects stay loaded."""
    query = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc(), Notification.id)
    return list(await db.scalars(query.execution_options(populate_existing=True)))


async def titled(db, user: User, title: str) -> list[Notification]:
    return [n for n in await notices(db, user) if n.title == title]


async def channels_of(db, notification: Notification) -> list[str]:
    return sorted(await db.scalars(select(NotificationDelivery.channel).where(NotificationDelivery.notification_id == notification.id)))


async def deactivate(db, member: AgentOrgMember) -> None:
    """AGN-002's deactivation shape: the membership and the login both off."""
    member = await db.get(AgentOrgMember, member.id, populate_existing=True)
    member.status = "deactivated"
    (await db.get(User, member.user_id, populate_existing=True)).active = False
    await db.commit()


async def set_org_status(db, org: AgentOrg, status: str) -> None:
    org = await db.get(AgentOrg, org.id, populate_existing=True)
    org.status = status
    await db.commit()


async def all_text(db) -> str:
    """Every notification title and body in the database, for 'never appears anywhere' assertions."""
    rows = await db.execute(select(Notification.title, Notification.body))
    return "\n".join(f"{t}\n{b}" for t, b in rows.all())
