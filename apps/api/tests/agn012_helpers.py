"""AGN-012 test helpers: the AGN-009 world (a Master, a Verify staff member who is assigned the students, a plain staff member, an
unassigned student, another agency) plus an application at `offer` for the no-login student, and direct builders for visa cases."""

from sqlalchemy import func, select

from app.models import AuditLog, VisaCase
from tests.agn008_helpers import APPS, mk_application
from tests.agn009_helpers import mk_doc
from tests.agn009_helpers import world as documents_world

VISA = APPS + "/{}/visa"


async def visa_world(db, *, status: str = "offer") -> dict:
    w = await documents_world(db)
    w["app"] = await mk_application(db, agent=w["master"], university=w["university"], record=w["record"], status=status)
    return w


async def mk_case(db, app, **fields) -> VisaCase:
    case = VisaCase(application_id=app.id, status=fields.pop("status", "checklist"), checklist=fields.pop("checklist", []), **fields)
    db.add(case)
    await db.commit()
    return case


async def case_of(db, app) -> VisaCase | None:
    return await db.scalar(select(VisaCase).where(VisaCase.application_id == app.id).execution_options(populate_existing=True))


async def visa_audits(db, app) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_id == str(app.id), AuditLog.action.like("overseas.application.visa%")).order_by(AuditLog.created_at)
    return list((await db.scalars(stmt)).all())


async def count_cases(db, app) -> int:
    return await db.scalar(select(func.count()).select_from(VisaCase).where(VisaCase.application_id == app.id))


async def verified(db, w, *types: str, status: str = "verified") -> None:
    for document_type in types:
        await mk_doc(db, record=w["record"], application=w["app"], status=status, document_type=document_type)
