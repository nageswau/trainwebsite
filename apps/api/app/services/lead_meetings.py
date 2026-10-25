"""ccrm-004 (DEC-SCOPE-259 LG3): meetings the lead's counselor records -- when, how and notes. Append-only (as ccrm-002 notes). The route
has applied the counselor's scope and locked the lead; this module never decides who may write. The notes are never logged nor put in the
audit row (LG8)."""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lead_stages import CLOSED
from app.models import AuditLog, Enquiry, LeadMeeting, User
from app.schemas import LeadMeetingIn
from app.services.bdm_activities import BACKDATE_DAYS
from app.services.lead_calls import check_time

logger = logging.getLogger("app.leads")

LEAD_CLOSED = "This lead is closed, so no meeting can be recorded"
FUTURE = "The meeting time can't be in the future"
TOO_OLD = f"Meetings can be recorded up to {BACKDATE_DAYS} days back"


def _out(meeting: LeadMeeting, author: User) -> dict:
    return {"id": meeting.id, "occurred_at": meeting.occurred_at, "mode": meeting.mode, "notes": meeting.notes,
            "author": {"id": author.id, "full_name": author.full_name}, "created_at": meeting.created_at}


async def page(db: AsyncSession, lead_id: UUID, limit: int, offset: int) -> dict:
    """Newest meeting first; `id` breaks a tie so paging never repeats or skips one."""
    where = LeadMeeting.lead_id == lead_id
    total = await db.scalar(select(func.count()).select_from(LeadMeeting).where(where))
    rows = await db.execute(select(LeadMeeting, User).join(User, User.id == LeadMeeting.author_user_id).where(where)
                            .order_by(LeadMeeting.occurred_at.desc(), LeadMeeting.id.desc()).limit(limit).offset(offset))
    return {"items": [_out(m, author) for m, author in rows.all()], "total": total or 0, "limit": limit, "offset": offset}


async def add(db: AsyncSession, user: User, lead: Enquiry, payload: LeadMeetingIn, now: datetime) -> dict:
    """On a locked lead: closed -> 409; the call time rules (no future, up to 7 days back); the row and its audit row. Commits."""
    if lead.status in CLOSED:
        raise HTTPException(409, LEAD_CLOSED)
    meeting = LeadMeeting(lead_id=lead.id, author_user_id=user.id, occurred_at=check_time(payload.occurred_at, now, FUTURE, TOO_OLD), mode=payload.mode,
                          notes=payload.notes)
    db.add(meeting)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="lead_meeting.create", entity_type="enquiry", entity_id=str(lead.id),
                    metadata_json={"meeting_id": str(meeting.id), "mode": meeting.mode}))
    await db.commit()
    await db.refresh(meeting)
    logger.info("lead_meeting_added", extra={"extra_fields": {"actor_id": str(user.id), "lead_id": str(lead.id), "meeting_id": str(meeting.id)}})
    return _out(meeting, user)
