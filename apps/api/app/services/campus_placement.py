"""pob-015 (DEC-SCOPE-426, spec docs/superpowers/specs/2026-11-07-pob-015-vacancy-sharing-campus-design.md): vacancies shared with a
college, the college's campus calendar and its students' outcomes.

Scope is pob-013's (`college_placement.scope` / `editable`). Outcomes never count an institution student the viewer may not see (pob-014
`institution_pool.visible`), so a reader outside the agreement gets smaller figures, never names. Functions only; nothing here commits.
"""

from datetime import date, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import (
    JOB_OPEN_STATUSES,
    BdmOrganization,
    BdmOrgCourse,
    BdmOrgPlacementBatch,
    BdmOrgPlacementEvent,
    Candidate,
    Company,
    InstitutionVacancyShare,
    Interview,
    Job,
    JobApplication,
    JobOffer,
    RecruiterMessageTemplate,
    RecruitmentDrive,
    User,
)
from app.services import calendar_ics, institution_pool
from app.services import college_placement as placement
from app.services import recruiter_messages as messages
from app.services import recruiter_requirements as requirements
from app.services.recruitment_drives import INTERVIEW_DONE, REACHED_SELECTED, REACHED_SHORTLISTED, reached

S, A, D = InstitutionVacancyShare, JobApplication, RecruitmentDrive
SHAREABLE_STATUSES = (*JOB_OPEN_STATUSES, "selected")  # V3: rec-007 live statuses (recruiter_requirements._ACTIVE)
SHARE_PAGE, OPTION_PAGE, TEMPLATE_PAGE, CALENDAR_CAP, MAX_WINDOW_DAYS = 50, 20, 50, 500, 92
NOT_SHAREABLE = "Only open vacancies that are not internal can be shared"
TEMPLATE_CATEGORY = "Choose a College/TPO template"
SHARE_NOT_FOUND = "Shared vacancy not found"
EVENT_LABELS = {"pre_placement_talk": "Pre-placement talk", "campus_drive": "Campus drive", "assessment": "Assessment", "interview": "Interview",
                "exam": "Exam", "holiday": "Holiday", "other": "Other"}  # fmt: skip


def shareable():
    """V3 (hrc-008): a live requirement that is not staff-only."""
    return [Job.status.in_(SHAREABLE_STATUSES), Job.visibility != "internal"]


# --- outcomes (V7) -----------------------------------------------------------------------------------------------------------------------
async def outcomes(db: AsyncSession, viewer_id: UUID, org_ids) -> dict:
    """The applications of the colleges' students -- imported by the college (pob-014) or added through a drive there (rec-029) -- each
    counted once. `org_ids` is a list or a sub-select of organization ids."""
    of_college = or_(Candidate.institution_org_id.in_(org_ids), A.drive_id.in_(select(D.id).where(D.college_org_id.in_(org_ids))))
    interviewed = exists().where(Interview.application_id == A.id, Interview.status.in_(INTERVIEW_DONE))
    offered = or_(exists().where(JobOffer.application_id == A.id), reached(REACHED_SELECTED))
    row = (await db.execute(
        select(
            func.count(A.id), func.count(func.distinct(A.candidate_id)), func.count(A.id).filter(reached(REACHED_SHORTLISTED)),
            func.count(A.id).filter(interviewed), func.count(A.id).filter(offered), func.count(A.id).filter(A.status == "joined"),
            func.count(A.id).filter(Candidate.user_id.is_(None)),
        ).select_from(A).join(Candidate, Candidate.id == A.candidate_id).where(of_college, institution_pool.visible(viewer_id))
    )).one()  # fmt: skip
    return dict(zip(("applications", "students", "shortlisted", "interviewed", "offered", "joined", "external"), row, strict=True))


# --- the college's vacancies view --------------------------------------------------------------------------------------------------------
async def view(db: AsyncSession, user: User, org: BdmOrganization) -> dict:
    """What every route of the college section returns: the latest shares (newest first), their total, the outcomes."""
    sharer, responder = aliased(User), aliased(User)
    rows = (await db.execute(
        select(S, Job.requirement_code, Job.title, RecruiterMessageTemplate.name, sharer.full_name, responder.full_name)
        .join(Job, Job.id == S.job_id).join(sharer, sharer.id == S.shared_by_user_id)
        .outerjoin(RecruiterMessageTemplate, RecruiterMessageTemplate.id == S.template_id).outerjoin(responder, responder.id == S.responded_by_user_id)
        .where(S.organization_id == org.id).order_by(S.shared_on.desc(), S.created_at.desc(), S.id).limit(SHARE_PAGE)
        .execution_options(populate_existing=True)
    )).all()  # fmt: skip
    shares = [
        {"id": s.id, "requirement": {"id": s.job_id, "code": code, "title": title}, "shared_on": s.shared_on, "channel": s.channel,
         "template": {"id": s.template_id, "name": template} if s.template_id else None, "notes": s.notes, "response": s.response,
         "response_note": s.response_note, "responded_at": s.responded_at, "responded_by_name": answered_by, "shared_by_name": by}
        for s, code, title, template, by, answered_by in rows
    ]  # fmt: skip
    return {
        "shares": shares, "share_total": await placement.count(db, S, org.id), "outcomes": await outcomes(db, user.id, [org.id]),
        "can_share": placement.can_edit(user, org),
    }


async def options(db: AsyncSession, user: User, pattern: str | None) -> dict:
    """The requirements the caller may share: in their requirement scope and shareable (V2/V3)."""
    where = [*await requirements.caller_scope(db, user), *shareable()]
    if pattern:
        where.append(or_(Job.title.ilike(pattern), Job.requirement_code.ilike(pattern), Company.name.ilike(pattern)))
    rows = (await db.execute(
        select(Job.id, Job.requirement_code, Job.title, Company.name).join(Company, Company.id == Job.company_id).where(*where)
        .order_by(func.lower(Job.title), Job.id).limit(OPTION_PAGE)
    )).all()  # fmt: skip
    T = RecruiterMessageTemplate  # noqa: N806
    # QA-02: the College/TPO templates the share route would accept (pob-023 usable), so no writer needs the template library route
    templates = (await db.execute(
        select(T.id, T.name).where(messages.usable_where(user), T.category == "college_tpo").order_by(T.updated_at.desc(), T.id).limit(TEMPLATE_PAGE)
    )).all()  # fmt: skip
    return {
        "items": [{"id": i, "code": code, "title": title, "company_name": company} for i, code, title, company in rows],
        "templates": [{"id": i, "name": name} for i, name in templates],
    }


async def shareable_job(db: AsyncSession, user: User, job_id: UUID) -> Job:
    """V2 then V3: out of the caller's requirement scope is 404 (so the visibility rule never reveals a job); then 422."""
    job = await requirements.load_scoped(db, user, job_id)
    if job.status not in SHAREABLE_STATUSES or job.visibility == "internal":
        raise HTTPException(422, NOT_SHAREABLE)
    return job


# --- the campus calendar (V8/V9) ---------------------------------------------------------------------------------------------------------
def window(start: date | None, end: date | None, today: date) -> tuple[date, date]:
    """Default: the current month. At most MAX_WINDOW_DAYS, `to` not before `from` (422)."""
    first = start or today.replace(day=1)
    last = end or (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if last < first:
        raise HTTPException(422, "The end date can't be before the start date")
    if (last - first).days >= MAX_WINDOW_DAYS:
        raise HTTPException(422, f"Choose at most {MAX_WINDOW_DAYS} days")
    return first, last


def _college(org: BdmOrganization) -> dict:
    return {"id": org.id, "code": org.code, "name": org.name}


async def calendar(db: AsyncSession, user: User, first: date, last: date, college_id: UUID | None = None) -> dict:
    """Drives at, placement calendar entries of, and batch pass-out dates of the colleges in the caller's scope, by date."""
    Org = BdmOrganization  # noqa: N806
    where = await placement.scope(db, user)
    if college_id is not None:
        where.append(Org.id == college_id)
    drives = (await db.execute(
        select(D, Org).join(Org, Org.id == D.college_org_id).where(*where, D.drive_date.between(first, last)).limit(CALENDAR_CAP + 1)
    )).all()  # fmt: skip
    E = BdmOrgPlacementEvent  # noqa: N806
    events = (await db.execute(
        select(E, Org).join(Org, Org.id == E.organization_id).where(*where, E.starts_on <= last, func.coalesce(E.ends_on, E.starts_on) >= first)
        .limit(CALENDAR_CAP + 1)
    )).all()  # fmt: skip
    B = BdmOrgPlacementBatch  # noqa: N806
    batches = (await db.execute(
        select(B, BdmOrgCourse.course, Org).join(Org, Org.id == B.organization_id).outerjoin(BdmOrgCourse, BdmOrgCourse.id == B.course_id)
        .where(*where, B.pass_out_date.between(first, last)).limit(CALENDAR_CAP + 1)
    )).all()  # fmt: skip
    base = {"end_date": None, "code": None, "status": None, "event_kind": None, "student_count": None}
    items = [
        *({**base, "kind": "drive", "id": d.id, "date": d.drive_date, "title": d.job_role, "code": d.drive_code, "status": d.status, "college": _college(o)}
          for d, o in drives),
        *({**base, "kind": "event", "id": e.id, "date": e.starts_on, "end_date": e.ends_on, "title": e.title, "event_kind": e.kind, "college": _college(o)}
          for e, o in events),
        *({**base, "kind": "batch", "id": b.id, "date": b.pass_out_date, "title": f"{b.pass_out_year} batch pass-out" + (f" · {course}" if course else ""),
           "student_count": b.student_count, "college": _college(o)} for b, course, o in batches),
    ]  # fmt: skip
    items.sort(key=lambda i: (i["date"], i["kind"], i["title"].casefold(), str(i["id"])))
    return {"from": first, "to": last, "items": items[:CALENDAR_CAP], "truncated": len(items) > CALENDAR_CAP}


def _summary_line(item: dict) -> str:
    if item["kind"] == "drive":
        return f"Campus drive: {item['title']}"
    if item["kind"] == "event":
        return f"{EVENT_LABELS.get(item['event_kind'], 'Placement')}: {item['title']}"
    return item["title"]


def ics(data: dict) -> str:
    events = [
        calendar_ics.all_day_event(uid=f"campus-{i['kind']}-{i['id']}@edusphere", day=i["date"], last_day=i["end_date"], summary=_summary_line(i),
                                   location=i["college"]["name"], description=i["college"]["code"])
        for i in data["items"]
    ]  # fmt: skip
    return calendar_ics.calendar(events, name="Campus calendar")


# --- the TPO widget (V10) ----------------------------------------------------------------------------------------------------------------
async def summary(db: AsyncSession, user: User, today: date) -> dict:
    where = await placement.scope(db, user)
    in_scope = select(BdmOrganization.id).where(*where)
    shares = (await db.execute(
        select(func.count().filter(S.shared_on >= today - timedelta(days=30)), func.count().filter(S.response == "awaiting"))
        .where(S.organization_id.in_(in_scope))
    )).one()  # fmt: skip
    upcoming = await calendar(db, user, today, today + timedelta(days=30))
    return {
        "colleges": await db.scalar(select(func.count()).select_from(BdmOrganization).where(*where)) or 0,
        "shared_30d": shares[0], "awaiting": shares[1], "upcoming_30d": len(upcoming["items"]), "upcoming_truncated": upcoming["truncated"],
        "outcomes": await outcomes(db, user.id, in_scope),
    }


def record_answer(share: InstitutionVacancyShare, user: User, response: str, note: str | None, at: datetime) -> None:
    """V6: an answer records who and when; back to awaiting clears both."""
    share.response, share.response_note = response, note
    share.responded_at, share.responded_by_user_id = (None, None) if response == "awaiting" else (at, user.id)
