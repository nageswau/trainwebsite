"""ccrm-022 (DEC-SCOPE-263) -- the central sensitivity rule for overseas student documents: a document's class (SD1/SD2) and who may
see an identity or financial one (SD3). The download route and the document lists both ask here. Functions only; never commits."""

from collections.abc import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.document_checklists import highest, type_sensitivity
from app.models import ApplicationChecklistItem, ApplicationChecklistItemDocument, StudentDocument, User

# SD3: the student (own), the counselor, the agency and the administrators -- never a university_rep. Each role's own scope rule
# (the download route, the lists) still applies on top of this.
SENSITIVE_READERS = frozenset({"overseas_student", "counselor", "agent", "overseas_admin", "super_admin"})


async def sensitivities(db: AsyncSession, documents: Iterable[StudentDocument]) -> dict[UUID, str]:
    """{document id: class} -- the highest of the type's class and every checklist item the document is linked to (SD2)."""
    documents = list(documents)
    raised: dict[UUID, list[str]] = {}
    if documents:
        rows = await db.execute(
            select(ApplicationChecklistItemDocument.document_id, ApplicationChecklistItem.sensitivity)
            .join(ApplicationChecklistItem, ApplicationChecklistItem.id == ApplicationChecklistItemDocument.item_id)
            .where(ApplicationChecklistItemDocument.document_id.in_([d.id for d in documents]), ApplicationChecklistItem.sensitivity != "standard")
        )
        for document_id, sensitivity in rows:
            raised.setdefault(document_id, []).append(sensitivity)
    return {d.id: highest([type_sensitivity(d.document_type, d.document_label), *raised.get(d.id, ())]) for d in documents}


def may_see(user: User, sensitivity: str) -> bool:
    return sensitivity == "standard" or user.role in SENSITIVE_READERS
