"""hrc-009 (DEC-SCOPE-390): an eligibility change of a vacancy flags its open applications for review instead of silently changing who
fits (source §4.3), and tells the vacancy's owners once with the count (§12/§13). Nothing here moves or rejects an application.

Every job edit path takes `matching.eligibility` before its change and calls `flag` after it, in its own transaction (nothing here
commits). `confirm` is the "keep it where it is" answer; a status move (`applications._record`) is the other one."""

import logging

from fastapi import HTTPException
from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobApplication, User
from app.notifications.events import notify
from app.services import applications, matching, requirement_owners

logger = logging.getLogger("app.recruiter")
EVENT = "it.requirement.review_needed"
NOT_FLAGGED = "This application does not need a review"


async def flag(db: AsyncSession, actor: User, job: Job, before: tuple) -> int:
    """R1-R6: when eligibility changed, one bounded UPDATE flags the job's open applications not already flagged (an earlier flag keeps
    its time and is not counted again), then each owner but the editor gets one notice with that count. Returns the count."""
    await db.flush()
    if await matching.eligibility(db, job) == before:
        return 0
    flagged = (await db.scalars(
        update(JobApplication)
        .where(JobApplication.job_id == job.id, JobApplication.status.in_(applications.OPEN), JobApplication.needs_review_since.is_(None))
        .values(needs_review_since=func.now())
        .returning(JobApplication.id)
        .execution_options(synchronize_session=False)
    )).all()  # fmt: skip
    if not flagged:
        return 0
    owners = await requirement_owners.people(db, job, without=(actor.id,))
    await notify(db, owners, EVENT, job.id, action_url=f"/recruiter/requirements/{job.id}", count=len(flagged))
    logger.info("application_review_flagged", extra={"extra_fields": {"actor_id": str(actor.id), "job_id": str(job.id), "flagged": len(flagged),
                                                                      "notified": len(owners)}})  # fmt: skip
    return len(flagged)


async def notify_changed(db: AsyncSession, actor: User, job: Job, before: tuple | None = None) -> None:
    """hrc-032 (N3): the caller changed the vacancy. With `before` (its eligibility), `flag` first: an owner told to review the applications
    gets only that notice for this save. Otherwise every owner but the editor is told the vacancy changed."""
    if before is None or not await flag(db, actor, job, before):
        await notify(db, await requirement_owners.people(db, job, without=(actor.id,)), "it.requirement.changed", job.id, action_url=f"/recruiter/requirements/{job.id}")


def confirm(db: AsyncSession, actor: User, application: JobApplication) -> None:
    """R4: the reviewer keeps the application where it is. The caller locked the row and checked the writer."""
    if application.needs_review_since is None:
        raise HTTPException(409, NOT_FLAGGED)
    flagged_at = application.needs_review_since
    application.needs_review_since = None
    applications.audit(db, actor, "review_confirmed", application, {"status": application.status, "needs_review_since": flagged_at.isoformat()})
