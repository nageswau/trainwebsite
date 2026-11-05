"""hrc-025 (DEC-SCOPE-402, spec docs/superpowers/specs/2026-11-05-hrc-025-website-registrations-workspace-design.md): the New Website
Registrations workspace -- the candidates the website created (source Website, N1), newest first, with when they were first contacted,
the next follow-up, how far they converted and the contact SLA.

Everything is derived in the page query (N5-N8): correlated sub-queries on indexed columns, so a call or message logged a moment ago shows
on the next request (AC1/AC3) and nothing can drift. Read only; nothing here writes. No contact details leave this module (N2)."""

from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Candidate, CandidateDuplicate, CandidateSkill, CandidateTask, CareerApplication, JobApplication, RecCandidateSource, RecruiterCall, RecruiterMessage, Skill, User
from app.services import candidate_engagement, candidate_ownership, candidate_search
from app.services import candidates as svc
from app.services.recruiter import ROLE
from app.services.website_intake import SOURCE

SLA_HOURS = 24  # N8 (Q-26 a, NEEDS_CONFIRMATION): registration to first call or message
ALL_READERS = svc.READERS | {"hr_manager"}  # N2: the HR Manager reads this list only (no candidate screen)
SKILLS_SHOWN = 3
ENGAGEMENT_VIEWS = ("new", "contacted", "screened", "active", "inactive")  # N3: hrc-021's derived status (schemas.WEBSITE_REGISTRATION_VIEWS)


def require_reader(user: User) -> None:
    if user.role not in ALL_READERS:
        raise HTTPException(403, "Your role cannot view website registrations")


def first_contact():
    """N5: the earliest logged call or message (LEAST skips NULLs; both NULL = never contacted)."""
    call = select(func.min(RecruiterCall.occurred_at)).where(RecruiterCall.candidate_id == Candidate.id).scalar_subquery()
    message = select(func.min(RecruiterMessage.sent_at)).where(RecruiterMessage.candidate_id == Candidate.id).scalar_subquery()
    return func.least(call, message)


def next_follow_up():
    """N6: the earliest due date of an open hrc-016 task about the candidate."""
    return select(func.min(CandidateTask.due_at)).where(CandidateTask.candidate_id == Candidate.id, CandidateTask.status == "open").scalar_subquery()


def conversion():
    """N7: registered -> applied -> placed (placed as hrc-021 counts it: an application joined, or the stored status)."""
    applications = select(JobApplication.id).where(JobApplication.candidate_id == Candidate.id)
    joined = applications.where(JobApplication.status == "joined").exists()
    website = select(CareerApplication.id).where(CareerApplication.candidate_id == Candidate.id).exists()
    return case((or_(joined, Candidate.status == "placed"), "placed"), (or_(applications.exists(), website), "applied"), else_="registered")


def in_review():
    """N3: an open hrc-014 duplicate pair names the candidate on either side."""
    pair = CandidateDuplicate
    return exists().where(pair.status == "open", or_(pair.candidate_id == Candidate.id, pair.other_id == Candidate.id))


def contact_sla(first):
    """N8 on the database clock: met within the target, pending while it runs, breached otherwise."""
    due = Candidate.created_at + timedelta(hours=SLA_HOURS)
    return case((first.is_(None), case((func.now() <= due, "pending"), else_="breached")), (first <= due, "met"), else_="breached")


def _filters(user: User, view: str | None) -> list:
    filters = [*svc.pool_filter(), Candidate.archived_at.is_(None), func.lower(RecCandidateSource.name) == SOURCE.lower()]
    if user.role == ROLE:  # N2: a recruiter sees their own and the unassigned queue
        filters.append(or_(candidate_ownership.mine(user.id), Candidate.owner_user_id.is_(None)))
    if view == "unassigned":
        filters.append(Candidate.owner_user_id.is_(None))
    elif view == "duplicate_review":
        filters.append(in_review())
    elif view in ENGAGEMENT_VIEWS:
        filters.append(candidate_engagement.expression() == view)
    return filters


async def _skills(db: AsyncSession, ids: list[UUID]) -> dict[UUID, list[str]]:
    rows = (await db.execute(select(CandidateSkill.candidate_id, Skill.name).join(Skill, Skill.id == CandidateSkill.skill_id)
                             .where(CandidateSkill.candidate_id.in_(ids))
                             .order_by(CandidateSkill.candidate_id, CandidateSkill.is_primary.desc(), Skill.name))).all()  # fmt: skip
    found: dict[UUID, list[str]] = {}
    for candidate_id, name in rows:
        found.setdefault(candidate_id, []).append(name)
    return found


async def page(db: AsyncSession, user: User, view: str | None, *, limit: int, offset: int) -> dict:
    base = select(Candidate).join(RecCandidateSource, RecCandidateSource.id == Candidate.source_id).where(*_filters(user, view))
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    first = first_contact()
    stmt = base.add_columns(candidate_engagement.expression(), candidate_search.completeness(), first, next_follow_up(), conversion(),
                            contact_sla(first), in_review())  # fmt: skip
    rows = (await db.execute(stmt.order_by(Candidate.created_at.desc(), Candidate.id.desc()).limit(limit).offset(offset))).all()
    people = await candidate_ownership.owners(db, [row[0] for row in rows])
    skills = await _skills(db, [row[0].id for row in rows])
    can_open = user.role in svc.READERS
    items = [
        {"id": c.id, "candidate_code": c.candidate_code, "name": c.name, "registered_at": c.created_at, "location": c.city or c.location,
         "skills": skills.get(c.id, [])[:SKILLS_SHOWN], "skill_count": len(skills.get(c.id, [])), "completeness": int(score),
         "owner": candidate_ownership.owner_out(people, c), "engagement": candidate_engagement.out(engagement), "first_contact_at": first_at,
         "next_follow_up_at": follow_up, "conversion": converted, "contact_sla": sla, "duplicate_review": review, "can_open": can_open}
        for c, engagement, score, first_at, follow_up, converted, sla, review in rows
    ]  # fmt: skip
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset, "sla_hours": SLA_HOURS}
