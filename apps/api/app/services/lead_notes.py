"""ccrm-002 (DEC-SCOPE-242): append-only lead notes. The route has applied its own scope (telecaller T23, the counselor's, the admin's) and
passes a lead id it may read; this module never decides who may write. The body is never logged nor put in the audit row (spec Security)."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, LeadNote, User

logger = logging.getLogger("app.leads")


def _out(note: LeadNote, author: User) -> dict:
    return {"id": note.id, "at": note.created_at, "author": {"id": author.id, "full_name": author.full_name}, "body": note.body}


async def page(db: AsyncSession, lead_id: UUID, limit: int, offset: int) -> dict:
    """Newest first; `id` breaks a tie so paging never repeats or skips a note."""
    total = await db.scalar(select(func.count()).select_from(LeadNote).where(LeadNote.lead_id == lead_id))
    rows = await db.execute(select(LeadNote, User).join(User, User.id == LeadNote.author_user_id).where(LeadNote.lead_id == lead_id)
                            .order_by(LeadNote.created_at.desc(), LeadNote.id.desc()).limit(limit).offset(offset))
    return {"items": [_out(note, author) for note, author in rows.all()], "total": total or 0, "limit": limit, "offset": offset}


async def add(db: AsyncSession, user: User, lead_id: UUID, body: str) -> dict:
    """N1/N2: any writer the route let through adds a note -- on a closed or handed-over lead too (notes are history). Commits."""
    note = LeadNote(lead_id=lead_id, author_user_id=user.id, body=body)
    db.add(note)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="lead_note.create", entity_type="enquiry", entity_id=str(lead_id), metadata_json={"note_id": str(note.id)}))
    await db.commit()
    await db.refresh(note)
    logger.info("lead_note_added", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead_id), "note_id": str(note.id)}})
    return _out(note, user)
