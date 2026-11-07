"""hrc-034 (DEC-SCOPE-416 I2/I3/I5, spec docs/superpowers/specs/2026-11-06-hrc-034-recruitment-insights-design.md): skill demand, portal analytics and
data quality. Reads only. Each data-quality figure's value and its rows come from one source, so they cannot disagree. No row carries a candidate's
name, contact details or pay."""

from datetime import UTC, date, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import Text, and_, case, cast, distinct, exists, func, literal, or_, select, type_coerce
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.models import (
    JOB_OPEN_STATUSES,
    Candidate,
    CandidateEducation,
    CandidateImportBatch,
    CandidateImportRow,
    CandidateResume,
    CandidateSkill,
    Company,
    Job,
    JobSkill,
    PortalEvent,
    Skill,
    SkillCategory,
    User,
)
from app.services import candidate_duplicates, matching, notification_exceptions, portal_events, telecaller_performance
from app.services.bdm_appointments import IST, today_ist
from app.services.candidate_portal import ROLE as PORTAL_ROLE
from app.services.candidate_profile import COMPLETENESS
from app.services.candidates import pool_filter

MAX_VACANCIES_CHECKED = 200  # I2: matching runs per job, so the report is bounded and says when more exist
INCOMPLETE_BELOW = 60  # I5 (NEEDS_CONFIRMATION)
BANDS = ((0, 24), (25, 49), (50, 74), (75, 99), (100, 100))
FUNNEL = ((portal_events.JOB_VIEW, "Viewed a job"), (portal_events.APPLY_START, "Started an application"), (portal_events.APPLY_SUBMIT, "Submitted an application"))


def _active_pool() -> list[ColumnElement]:
    return [*pool_filter(), Candidate.archived_at.is_(None), Candidate.merged_into_id.is_(None)]


def _open_job() -> ColumnElement:
    return Job.status.in_(JOB_OPEN_STATUSES)


def _listed(column) -> ColumnElement:
    """A JSON list column holds something (JSON null and [] do not count)."""
    return and_(column.is_not(None), cast(column, Text).not_in(("null", "[]")))


def completeness_expr() -> ColumnElement:
    """hrc-010's `candidate_profile.completeness` as SQL, from its own weights; a test holds the two equal."""
    weight = {key: value for key, _, value in COMPLETENESS}
    met = {
        "contact_verified": Candidate.email_verified_at.is_not(None),
        "education": exists().where(CandidateEducation.candidate_id == Candidate.id),
        "skills": select(func.count()).select_from(CandidateSkill).where(CandidateSkill.candidate_id == Candidate.id).scalar_subquery() >= 3,
        "experience": Candidate.experience_months.is_not(None),
        "preferences": and_(_listed(Candidate.preferred_roles), _listed(Candidate.preferred_locations)),
        "resume": exists().where(CandidateResume.candidate_id == Candidate.id),
        "compensation": Candidate.expected_salary.is_not(None),
    }
    total = literal(0)
    for key, condition in met.items():
        total = total + case((condition, weight[key]), else_=0)
    return type_coerce(total, Candidate.experience_months.type)


# --- I2: skill demand -------------------------------------------------------------------------------------------------------------------
async def skill_demand(db: AsyncSession, *, sort: str, limit: int, offset: int) -> dict:
    required = case((JobSkill.kind == "required", JobSkill.job_id))
    preferred = case((JobSkill.kind == "preferred", JobSkill.job_id))
    demand = (
        select(JobSkill.skill_id.label("skill_id"), func.count(distinct(required)).label("required_jobs"), func.count(distinct(preferred)).label("preferred_jobs"), func.count(distinct(JobSkill.job_id)).label("open_jobs"))
        .join(Job, Job.id == JobSkill.job_id)
        .where(_open_job(), JobSkill.skill_id.is_not(None))
        .group_by(JobSkill.skill_id)
        .subquery()
    )
    held = (
        select(CandidateSkill.skill_id.label("skill_id"), func.count(distinct(CandidateSkill.candidate_id)).label("supply"))
        .join(Candidate, Candidate.id == CandidateSkill.candidate_id)
        .where(*_active_pool())
        .group_by(CandidateSkill.skill_id)
        .subquery()
    )
    open_jobs, supply = func.coalesce(demand.c.open_jobs, 0), func.coalesce(held.c.supply, 0)
    used = or_(demand.c.skill_id.is_not(None), held.c.skill_id.is_not(None))
    order = (supply.desc(), open_jobs.desc()) if sort == "supply" else (open_jobs.desc(), supply.asc())
    rows = await db.execute(
        select(Skill.id, Skill.name, SkillCategory.name.label("category"), func.coalesce(demand.c.required_jobs, 0).label("required_jobs"),
               func.coalesce(demand.c.preferred_jobs, 0).label("preferred_jobs"), open_jobs.label("open_jobs"), supply.label("supply"))
        .join(SkillCategory, SkillCategory.id == Skill.category_id)
        .outerjoin(demand, demand.c.skill_id == Skill.id)
        .outerjoin(held, held.c.skill_id == Skill.id)
        .where(used)
        .order_by(*order, func.lower(Skill.name), Skill.id)
        .limit(limit)
        .offset(offset)
    )  # fmt: skip
    total = await db.scalar(select(func.count()).select_from(Skill).outerjoin(demand, demand.c.skill_id == Skill.id).outerjoin(held, held.c.skill_id == Skill.id).where(used))
    zero = await db.scalar(select(func.count()).select_from(demand.outerjoin(held, held.c.skill_id == demand.c.skill_id)).where(held.c.skill_id.is_(None)))
    free_text = await db.scalar(select(func.count()).select_from(JobSkill).join(Job, Job.id == JobSkill.job_id).where(_open_job(), JobSkill.skill_id.is_(None)))
    jobs = await db.scalar(select(func.count()).select_from(Job).where(_open_job()))
    figures = [
        {"key": "open_jobs", "label": "Open jobs", "value": jobs, "definition": "Requirements in an open status, right now."},
        {"key": "zero_supply", "label": "Skills with zero supply", "value": zero, "definition": "Skills that open jobs ask for and no active candidate in the pool holds."},
        {"key": "free_text", "label": "Skills not in the Skills Master", "value": free_text, "definition": "Free-text skills on open jobs. They have no supply figure until they are linked to the Skills Master."},
    ]
    items = [{"skill_id": str(r.id), "name": r.name, "category": r.category, "required_jobs": r.required_jobs, "preferred_jobs": r.preferred_jobs,
              "open_jobs": r.open_jobs, "supply": r.supply, "zero_supply": r.open_jobs > 0 and r.supply == 0} for r in rows.all()]  # fmt: skip
    return {"figures": figures, "items": items, "total": total, "limit": limit, "offset": offset, "sort": sort}


async def thin_vacancies(db: AsyncSession, *, n: int, limit: int, offset: int) -> dict:
    """Appendix B: open jobs with fewer than N candidates through the hard filters -- `matching.matches`, the requirement's own Matching page count."""
    rows = (await db.execute(select(Job, Company.name).join(Company, Company.id == Job.company_id).where(_open_job()).order_by(Job.created_at.desc(), Job.id.desc()).limit(MAX_VACANCIES_CHECKED))).all()
    open_total = await db.scalar(select(func.count()).select_from(Job).where(_open_job()))
    found = []
    for job, company in rows:
        result = await matching.matches(db, job, limit=0, offset=0, amounts=False)
        if result["total"] < n:
            found.append({"id": str(job.id), "code": job.requirement_code, "title": job.title, "company": company, "matches": result["total"], "reason": result["reason"]})
    found.sort(key=lambda r: r["matches"])  # stable: newest first among equals
    return {"n": n, "items": found[offset: offset + limit], "total": len(found), "limit": limit, "offset": offset, "checked": len(rows), "open_jobs": open_total}  # fmt: skip


# --- I3: portal analytics ---------------------------------------------------------------------------------------------------------------
async def portal_analytics(db: AsyncSession, *, date_from: date | None, date_to: date | None) -> dict:
    first, last = telecaller_performance.date_range(date_from, date_to, today_ist(datetime.now(UTC)))
    start, end = datetime.combine(first, time.min, IST), datetime.combine(last + timedelta(days=1), time.min, IST)
    portal = [Candidate.user_id == User.id, User.role == PORTAL_ROLE]
    signups = await db.execute(
        select(func.count(), func.count(Candidate.email_verified_at)).select_from(Candidate).join(User, and_(*portal))
        .where(Candidate.merged_into_id.is_(None), Candidate.created_at >= start, Candidate.created_at < end)
    )  # fmt: skip
    total, verified = signups.one()
    percent = completeness_expr().label("percent")
    scored = select(percent).select_from(Candidate).join(User, and_(*portal)).where(*_active_pool()).subquery()
    band = await db.execute(select(*(func.count().filter(scored.c.percent.between(low, high)).label(f"b{low}") for low, high in BANDS)).select_from(scored))
    bands = band.one()
    steps = await db.execute(
        select(PortalEvent.kind, func.count(), func.count(distinct(PortalEvent.user_id))).where(PortalEvent.day >= first, PortalEvent.day <= last).group_by(PortalEvent.kind)
    )
    by_kind = {kind: (events, people) for kind, events, people in steps.all()}
    funnel, previous = [], None
    for key, label in FUNNEL:
        events, people = by_kind.get(key, (0, 0))
        funnel.append({"key": key, "label": label, "events": events, "people": people, "dropped": None if previous is None else max(previous - people, 0)})
        previous = people
    return {
        "from": first, "to": last, "registrations": {"total": total, "verified": verified},
        "completion": [{"label": f"{low}%" if low == high else f"{low}-{high}%", "count": count} for (low, high), count in zip(BANDS, bands, strict=True)],
        "funnel": funnel, "first_recorded": await db.scalar(select(func.min(PortalEvent.day))),
    }  # fmt: skip


# --- I5: data quality -------------------------------------------------------------------------------------------------------------------
FIGURES = {
    "duplicates": {"label": "Duplicate queue", "definition": "Open pairs of possible duplicates; the same count as Duplicate Review.",
                   "grant": ("candidates", "merge"), "href": "/recruiter/candidates/duplicates",
                   "columns": (("candidate", "Candidate"), ("other", "Possible duplicate"), ("created_at", "Queued"))},
    "failed_imports": {"label": "Failed imports", "definition": "Candidate file rows that could not be imported. Correct the row and upload it again.",
                       "grant": ("candidates", "import"), "href": "/recruiter/candidates/import",
                       "columns": (("file_name", "File"), ("row_number", "Row"), ("reason", "Reason"), ("created_at", "Imported"))},
    "failed_notifications": {"label": "Failed notifications", "definition": "Recruitment notices and recruiter emails whose delivery failed; the same count as Delivery exceptions.",
                             "grant": ("notifications", "retry"), "href": "/recruiter/notification-exceptions",
                             "columns": (("type_label", "Type"), ("channel", "Channel"), ("attempts", "Attempts"), ("failed_at", "Failed"))},
    "incomplete_profiles": {"label": "Incomplete profiles", "definition": f"Active pool candidates under {INCOMPLETE_BELOW}% profile completeness.",
                            "grant": None, "href": None, "columns": (("candidate_code", "Candidate"), ("percent", "Complete %"))},
    "jobs_missing_fields": {"label": "Jobs missing fields", "definition": "Open jobs without a required skill, description, on-site location, qualification, minimum experience, employment type or vacancies.",
                            "grant": None, "href": None, "columns": (("code", "Requirement"), ("title", "Title"), ("company", "Company"), ("missing", "Missing"))},
}  # fmt: skip


def _blank(column) -> ColumnElement:
    return func.coalesce(func.trim(column), "") == ""


def _missing_conditions() -> dict[str, ColumnElement]:
    has_skill = exists().where(JobSkill.job_id == Job.id, JobSkill.kind == "required")
    return {
        "required skill": ~has_skill,
        "description": _blank(Job.description),
        "on-site location": and_(func.coalesce(Job.work_mode, "") != "remote", _blank(Job.location)),
        "qualification": _blank(Job.qualification),
        "minimum experience": Job.experience_min_months.is_(None),
        "employment type": Job.employment_type.is_(None),
        "vacancies": Job.vacancies.is_(None),
    }


def _failed_import_rows():
    return (
        select(CandidateImportBatch.file_name, CandidateImportRow.row_number, CandidateImportRow.reason, CandidateImportBatch.created_at, CandidateImportRow.id)
        .join(CandidateImportBatch, CandidateImportBatch.id == CandidateImportRow.batch_id)
        .where(CandidateImportRow.status == "error")
    )


def _incomplete_rows():
    percent = completeness_expr()
    return select(Candidate.candidate_code, percent.label("percent")).where(*_active_pool(), percent < INCOMPLETE_BELOW)


def _job_rows():
    conditions = _missing_conditions()
    flags = [condition.label(f"m{i}") for i, condition in enumerate(conditions.values())]
    return select(Job.requirement_code, Job.title, Company.name, *flags).join(Company, Company.id == Job.company_id).where(_open_job(), or_(*conditions.values()))


async def _count(db: AsyncSession, stmt) -> int:
    return await db.scalar(select(func.count()).select_from(stmt.subquery()))


async def _value(db: AsyncSession, key: str) -> int:
    if key == "duplicates":
        return (await candidate_duplicates.queue(db, "open", 1, 0))["total"]
    if key == "failed_notifications":
        return (await notification_exceptions.page(db, None, None, 1, 0))["total"]
    return await _count(db, {"failed_imports": _failed_import_rows, "incomplete_profiles": _incomplete_rows, "jobs_missing_fields": _job_rows}[key]())


async def data_quality(db: AsyncSession, holds) -> dict:
    """`holds(resource, action)` says whether the caller may open a figure's action page."""
    figures = []
    for key, meta in FIGURES.items():
        href = meta["href"] if meta["grant"] and await holds(*meta["grant"]) else None
        figures.append({"key": key, "label": meta["label"], "definition": meta["definition"], "value": await _value(db, key), "href": href})
    return {"figures": figures}


async def _rows(db: AsyncSession, key: str, limit: int, offset: int) -> list[dict]:
    if key == "duplicates":
        items = (await candidate_duplicates.queue(db, "open", limit, offset))["items"]
        return [{"candidate": row["candidate"]["candidate_code"], "other": row["other"]["candidate_code"], "created_at": row["created_at"]} for row in items]
    if key == "failed_notifications":
        items = (await notification_exceptions.page(db, None, None, limit, offset))["items"]
        return [{"type_label": row["type_label"], "channel": row["channel"], "attempts": row["attempts"], "failed_at": row["failed_at"]} for row in items]
    if key == "failed_imports":
        rows = await db.execute(_failed_import_rows().order_by(CandidateImportBatch.created_at.desc(), CandidateImportRow.row_number, CandidateImportRow.id).limit(limit).offset(offset))
        return [{"file_name": r.file_name, "row_number": r.row_number, "reason": r.reason, "created_at": r.created_at} for r in rows.all()]
    if key == "incomplete_profiles":
        rows = await db.execute(_incomplete_rows().order_by(completeness_expr(), Candidate.candidate_code).limit(limit).offset(offset))
        return [{"candidate_code": r.candidate_code, "percent": r.percent} for r in rows.all()]
    names = list(_missing_conditions())
    rows = await db.execute(_job_rows().order_by(Job.created_at.desc(), Job.id.desc()).limit(limit).offset(offset))
    return [{"code": r.requirement_code, "title": r.title, "company": r.name, "missing": [name for i, name in enumerate(names) if getattr(r, f"m{i}")]} for r in rows.all()]


async def drill(db: AsyncSession, key: str, limit: int, offset: int) -> dict:
    meta = FIGURES.get(key)
    if meta is None:
        raise HTTPException(404, "Figure not found")
    return {
        "figure": {"key": key, "label": meta["label"], "definition": meta["definition"]},
        "columns": [{"key": k, "label": label} for k, label in meta["columns"]],
        "items": await _rows(db, key, limit, offset), "total": await _value(db, key), "limit": limit, "offset": offset,
    }  # fmt: skip
