"""ENH-018 -- school activity feedback (docs/superpowers/specs/2026-09-23-enh-018-school-activity-feedback-design.md).

A School Coordinator records one feedback per completed Edusphere activity of their own school (`School CRM.md §31`); the
principal reads it; Edusphere admins read every school's. Two routers, like `school_transfers.py`, so `schools.py` and
`admin.py` do not grow. The caller's school always comes from their server-owned profile, never from a request."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schools import _own_school_id, _require_coordinator_user
from app.core.database import get_db
from app.core.logging import get_logger, request_id_ctx
from app.models import AuditLog, SchoolActivity, SchoolActivityAttendance, SchoolActivityFeedback, User
from app.schemas import ActivityFeedbackCreate, ActivityFeedbackOut, ActivityParticipation

coordinator_router = APIRouter(prefix="/school", tags=["school-feedback"])
admin_router = APIRouter(prefix="/overseas-admin", tags=["school-feedback"])
logger = get_logger("app.school.feedback")

# The `detail` strings are a contract (spec §5.1): a client may match on them.
ACTIVITY_NOT_FOUND = "Activity not found"
NOT_EDUSPHERE_ACTIVITY = "Feedback is only collected for Edusphere activities"
NOT_YET_HELD = "Feedback opens once the activity has taken place"
ALREADY_SUBMITTED = "Feedback has already been submitted for this activity"
UNIQUE_CONSTRAINT = "uq_activity_feedback_activity"
ACTION_SUBMIT = "school.activity_feedback_submit"
NO_ATTENDANCE = ActivityParticipation(present=0, marked=0)


def _feedback_out(feedback: SchoolActivityFeedback, submitter_name: str) -> ActivityFeedbackOut:
    return ActivityFeedbackOut(
        id=feedback.id, activity_id=feedback.activity_id, trainer_name=feedback.trainer_name, rating=feedback.rating, satisfaction=feedback.satisfaction,
        feedback=feedback.feedback, suggestions=feedback.suggestions, submitted_by_name=submitter_name, submitted_at=feedback.created_at,
    )


async def _participation(db: AsyncSession, activity_ids: list[UUID]) -> dict[UUID, ActivityParticipation]:
    """Present-of-marked per activity for one page, in ONE grouped query (D4: computed, never stored)."""
    if not activity_ids:
        return {}
    rows = await db.execute(
        select(SchoolActivityAttendance.activity_id, func.count(), func.count().filter(SchoolActivityAttendance.present.is_(True)))
        .where(SchoolActivityAttendance.activity_id.in_(activity_ids))
        .group_by(SchoolActivityAttendance.activity_id)
    )
    return {activity_id: ActivityParticipation(present=present, marked=marked) for activity_id, marked, present in rows.all()}


def _refuse(status: int, detail: str, reason: str, context: dict) -> HTTPException:
    logger.info("activity_feedback_rejected", extra={"extra_fields": {**context, "reason": reason}})
    return HTTPException(status, detail)


@coordinator_router.post("/activities/{activity_id}/feedback", status_code=201, response_model=ActivityFeedbackOut)
async def submit_activity_feedback(activity_id: UUID, payload: ActivityFeedbackCreate, user: User = Depends(_require_coordinator_user), db: AsyncSession = Depends(get_db)):
    """One feedback per activity, then immutable (D5). The activity is loaded together with the caller's own school, so another
    school's activity is the same 404 as a missing one. No existence pre-check: the unique constraint decides a race, and the
    feedback row and its audit row commit together or not at all."""
    school_id = _own_school_id(user)
    context = {"actor_id": str(user.id), "school_id": str(school_id), "activity_id": str(activity_id)}
    activity = await db.scalar(select(SchoolActivity).where(SchoolActivity.id == activity_id, SchoolActivity.school_id == school_id))
    if activity is None:
        raise _refuse(404, ACTIVITY_NOT_FOUND, "not_found", context)
    if activity.activity_type is None:
        raise _refuse(422, NOT_EDUSPHERE_ACTIVITY, "untyped", context)
    if activity.scheduled_at > datetime.now(UTC):
        raise _refuse(422, NOT_YET_HELD, "not_yet_held", context)
    feedback = SchoolActivityFeedback(activity_id=activity.id, school_id=school_id, submitted_by_user_id=user.id, **payload.model_dump())
    db.add(feedback)
    try:
        await db.flush()
        db.add(
            AuditLog(
                user_id=user.id, action=ACTION_SUBMIT, entity_type="school_activity", entity_id=str(activity.id),
                metadata_json={"school_id": str(school_id), "feedback_id": str(feedback.id), "rating": feedback.rating, "satisfaction": feedback.satisfaction, "request_id": request_id_ctx.get()},
            )
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        if UNIQUE_CONSTRAINT not in str(exc.orig):
            raise
        logger.info("activity_feedback_duplicate", extra={"extra_fields": context})
        raise HTTPException(409, ALREADY_SUBMITTED) from exc
    await db.refresh(feedback, ["created_at"])
    logger.info("activity_feedback_submitted", extra={"extra_fields": {**context, "feedback_id": str(feedback.id), "rating": feedback.rating, "satisfaction": feedback.satisfaction}})
    return _feedback_out(feedback, user.full_name)
