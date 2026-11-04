"""hrc-008 (DEC-SCOPE-383 V5): which open jobs a public visitor or a student may see and apply to. Staff readers do not call this -- they
see every job. A job outside the caller's visibility is answered exactly like a missing one (the readers' own 404).

`segment` jobs reach the members of their talent pool, computed on read through the rec-015 rule (V2): one query for the student's
candidate, one resolution of the referenced active pools' terms, one FILTERed count per pool."""

from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, Job, TalentPool, User
from app.services import candidate_search, talent_pools

PORTAL = ("portal", "public")  # every student; plus the segments they belong to


def public_filter():
    return Job.visibility == "public"


async def _member_pools(db: AsyncSession, student: User, pool_ids: set[UUID] | None = None) -> list[UUID]:
    """The active pools (those named by a segment job, or `pool_ids`) whose rule the student's candidate meets."""
    candidate_id = await db.scalar(select(Candidate.id).where(Candidate.user_id == student.id))
    if candidate_id is None:
        return []
    named = select(Job.segment_pool_id).where(Job.visibility == "segment") if pool_ids is None else sorted(pool_ids)
    pools = (await db.scalars(select(TalentPool).where(TalentPool.id.in_(named), TalentPool.active.is_(True)))).all()
    if not pools:
        return []
    terms = await talent_pools.resolve(db, list(pools))
    columns = [func.count().filter(and_(*candidate_search.filters(talent_pools.rule(p), terms))) for p in pools]
    row = (await db.execute(select(*columns).select_from(Candidate).where(Candidate.id == candidate_id))).one()
    return [p.id for i, p in enumerate(pools) if row[i]]


async def student_filter(db: AsyncSession, student: User):
    """Only a segment job names a pool (ck_jobs_segment_pool), so a member pool's id is enough; no pools = an empty, false IN."""
    return or_(Job.visibility.in_(PORTAL), Job.segment_pool_id.in_(await _member_pools(db, student)))


async def visible_to_student(db: AsyncSession, student: User, job: Job) -> bool:
    if job.visibility in PORTAL:
        return True
    return job.visibility == "segment" and job.segment_pool_id in await _member_pools(db, student, {job.segment_pool_id})
