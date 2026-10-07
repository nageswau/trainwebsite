"""AGN-023 test helpers: the AGN-009 agency world (a Master, a Verify staff member assigned the no-login student, another agency) plus
an Overseas Admin, two active overseas counselors, an inactive one, an IT counselor, an agency application and a direct one."""

from sqlalchemy import select

from app.models import ApplicationStatusHistory, AuditLog, Notification, OverseasApplication
from tests.agn001_helpers import mk_user, uniq
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import world as documents_world

ASSIGN = "/api/v1/workflows/overseas/applications/{}/counselor"
UPDATE = "/api/v1/workflows/overseas/applications/{}"
ADVANCE = "/api/v1/workflows/overseas/applications/{}/advance"
PORTAL = "/api/v1/portal/overseas/{}/{}"


async def assign_world(db, *, status: str = "offer") -> dict:
    w = await documents_world(db)
    w["admin"] = await mk_user(db, role="overseas_admin", full_name=f"Admin {uniq()}")
    w["counselor"] = await mk_user(db, role="counselor", full_name=f"Counsellor A {uniq()}")
    w["counselor2"] = await mk_user(db, role="counselor", full_name=f"Counsellor B {uniq()}")
    w["inactive"] = await mk_user(db, role="counselor", full_name=f"Inactive {uniq()}", active=False)
    w["it_counselor"] = await mk_user(db, role="counselor", division="it", full_name=f"IT {uniq()}")
    w["app"] = await mk_application(db, agent=w["master"], university=w["university"], record=w["record"], status=status)
    w["direct_student"] = await mk_user(db, role="overseas_student", full_name=f"Direct {uniq()}")
    w["direct_app"] = await mk_application(db, agent=None, university=w["university"], student=w["direct_student"], status=status)
    return w


async def notices(db, user) -> list[Notification]:
    stmt = select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def fresh(db, app) -> OverseasApplication:
    return await db.get(OverseasApplication, app.id, populate_existing=True)


async def history_notes(db, app) -> list[str | None]:
    stmt = select(ApplicationStatusHistory.notes).where(ApplicationStatusHistory.application_id == app.id).order_by(ApplicationStatusHistory.created_at)
    return list((await db.scalars(stmt)).all())


async def assign_audits(db, app) -> list[dict]:
    stmt = select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action == "overseas.application.counselor_assign").order_by(AuditLog.created_at)
    return [row.metadata_json for row in (await db.scalars(stmt)).all()]
