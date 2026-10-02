"""AGN-010 test helpers: AGN-008's agency world plus one application and its offer letter (an AGN-009 document of type
"Offer letter" attached to it)."""

from datetime import date, timedelta

from sqlalchemy import func, select

from app.models import ApplicationStatusHistory, AuditLog
from tests.agn008_helpers import APPS, agency_world, mk_application
from tests.agn009_helpers import mk_doc

OFFER_LETTER = "Offer letter"
OFFER_DATE = date.today() - timedelta(days=3)


def offer_url(app_id) -> str:
    return f"{APPS}/{app_id}/offer"


def offer_body(**overrides) -> dict:
    """A valid conditional offer; `None` values are sent as JSON null, so pass a key only to change it."""
    body = {"offer_type": "conditional", "offer_date": OFFER_DATE.isoformat(), "offer_deadline": (OFFER_DATE + timedelta(days=30)).isoformat(), "conditions": "IELTS 6.5 overall"}
    body.update({k: (v.isoformat() if isinstance(v, date) else str(v) if k == "offer_document_id" and v is not None else v) for k, v in overrides.items()})
    return body


async def offer_world(db, *, status: str = "university_selection") -> dict:
    w = await agency_world(db)
    w["app"] = await mk_application(db, agent=w["master"], university=w["university"], record=w["record"], status=status)
    w["letter"] = await mk_doc(db, record=w["record"], application=w["app"], document_type=OFFER_LETTER)
    return w


async def history_of(db, app_id) -> list[ApplicationStatusHistory]:
    stmt = select(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app_id).order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
    return list((await db.scalars(stmt.execution_options(populate_existing=True))).all())


async def offer_audits(db, app_id) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_id == str(app_id), AuditLog.action == "overseas.application.offer").order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


async def writes_for(db, app_id) -> tuple[int, int]:
    """(history rows, audit rows) for the application -- a refused request leaves both unchanged."""
    history = await db.scalar(select(func.count()).select_from(ApplicationStatusHistory).where(ApplicationStatusHistory.application_id == app_id))
    audits = await db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.entity_id == str(app_id)))
    return history, audits
