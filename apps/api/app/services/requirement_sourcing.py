"""pob-017 (DEC-SCOPE-429, the spec's S1-S12): a requirement's sourcing plan -- target profile, Boolean strings, planned channels, linked saved
searches, targets, deadline and source owner -- and its source funnel (found -> screened -> suitable -> submitted -> rejected, by source).

Functions only; nothing here commits, and the caller holds the requirement's row lock for a save. The routes decide who may act (S9). Audit rows
carry field names only, never the plan's text (S10)."""

from datetime import date

from fastapi import HTTPException
from sqlalchemy import distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ApplicationScreening,
    AuditLog,
    Candidate,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    JobAssignment,
    JobSourcingChannel,
    JobSourcingPlan,
    JobSourcingSearch,
    ProfileShareItem,
    RecCandidateSource,
    SavedCandidateSearch,
    User,
)
from app.schemas import RecSourcingPlanIn
from app.services import candidates, saved_searches
from app.services.applications import SUBMITTED
from app.services.bdm_appointments import db_now, today_ist
from app.services.recruiter_companies import person

# S5: how far an application has got; a status reached at some point counts even after it moved on (or was rejected)
RANK = {status: i for i, status in enumerate(("sourced", "screened", "shortlisted", *SUBMITTED))}
SCREENED, SUITABLE, SUBMITTED_RANK = RANK["screened"], RANK["shortlisted"], RANK[SUBMITTED[0]]
STAGES = ("found", "screened", "suitable", "submitted", "rejected")
TARGETS = (("found", "target_found"), ("screened", "target_screened"), ("submitted", "target_submitted"))
FIELDS = ("target_profile", "boolean_strings", "target_found", "target_screened", "target_submitted", "deadline", "source_owner_user_id")
NOT_ON_TEAM = "The source owner must be one of this requirement's owners"
NO_SOURCE = "Choose planned channels from the active candidate sources"
NO_SEARCH = "Link only saved searches you can see"
NO_LINKING = "Your role cannot link saved candidate searches"


# --- the funnel (S5, S6) ------------------------------------------------------------------------------------------------------------
async def funnel(db: AsyncSession, job_id, planned: list[RecCandidateSource]) -> dict:
    """One row per source with an application or a planned channel. An application counts under its source at submission, else the
    candidate's current source (S6). The rows add up to the total in every stage (AC2)."""
    reached = (select(func.array_agg(distinct(JobApplicationStatusHistory.to_status))).where(JobApplicationStatusHistory.application_id == JobApplication.id)
               .correlate(JobApplication).scalar_subquery())  # fmt: skip
    stmt = (
        select(
            func.coalesce(JobApplication.submitted_source_id, Candidate.source_id),
            JobApplication.status,
            reached,
            exists().where(ApplicationScreening.application_id == JobApplication.id),
            exists().where(ProfileShareItem.application_id == JobApplication.id),
        )
        .join(Candidate, Candidate.id == JobApplication.candidate_id)
        .where(JobApplication.job_id == job_id)
    )
    counts: dict = {s.id: dict.fromkeys(STAGES, 0) for s in planned}
    for source_id, status, history, screening, shared in (await db.execute(stmt)).all():
        rank = max(RANK.get(s, -1) for s in {status, *(history or ())})
        row = counts.setdefault(source_id, dict.fromkeys(STAGES, 0))
        row["found"] += 1
        row["screened"] += rank >= SCREENED or screening
        row["suitable"] += rank >= SUITABLE
        row["submitted"] += rank >= SUBMITTED_RANK or shared
        row["rejected"] += status == "rejected"
    sources = {s.id: s for s in (await db.scalars(select(RecCandidateSource).where(RecCandidateSource.id.in_(counts)))).all()} if counts else {}
    planned_ids = {s.id for s in planned}
    rows = [{"source": {"id": sid, "name": sources[sid].name, "active": sources[sid].active}, "planned": sid in planned_ids, **row, "conversion": _rate(row)}
            for sid, row in counts.items()]  # fmt: skip
    rows.sort(key=lambda r: (-r["found"], r["source"]["name"].lower()))
    total = {stage: sum(r[stage] for r in rows) for stage in STAGES}
    return {"rows": rows, "total": {**total, "conversion": _rate(total)}}


def _rate(row: dict) -> float | None:
    """Appendix B: submitted / found, per source."""
    return row["submitted"] / row["found"] if row["found"] else None


def progress(plan: JobSourcingPlan | None, total: dict, today: date) -> dict:
    """S7 / AC3: each set target against its count; `breached` once the deadline has passed with a target short."""
    figures = {stage: {"actual": total[stage], "target": getattr(plan, column, None)} for stage, column in TARGETS}
    short = [stage for stage, f in figures.items() if f["target"] is not None and f["actual"] < f["target"]]
    deadline = plan.deadline if plan else None
    if all(f["target"] is None for f in figures.values()):
        state = "no_targets"
    elif not short:
        state = "met"
    elif deadline is not None and deadline < today:
        state = "breached"
    else:
        state = "on_track"
    return {"state": state, "short": short, "deadline": deadline, "days_left": (deadline - today).days if deadline else None, **figures}


# --- reading ------------------------------------------------------------------------------------------------------------------------
async def _channels(db: AsyncSession, job_id) -> list[RecCandidateSource]:
    stmt = select(RecCandidateSource).join(JobSourcingChannel, JobSourcingChannel.source_id == RecCandidateSource.id).where(JobSourcingChannel.job_id == job_id)
    return list((await db.scalars(stmt.order_by(func.lower(RecCandidateSource.name)))).all())


async def _linked(db: AsyncSession, job_id) -> list[tuple[SavedCandidateSearch, str]]:
    stmt = (select(SavedCandidateSearch, User.full_name).join(JobSourcingSearch, JobSourcingSearch.saved_search_id == SavedCandidateSearch.id)
            .join(User, User.id == SavedCandidateSearch.owner_user_id).where(JobSourcingSearch.job_id == job_id)
            .order_by(func.lower(SavedCandidateSearch.name), SavedCandidateSearch.id))  # fmt: skip
    return [(row, name) for row, name in (await db.execute(stmt)).all()]


def _sees(user: User, row: SavedCandidateSearch) -> bool:
    """S3: as hrc-020's list -- the owner's own and every shared one."""
    return row.owner_user_id == user.id or row.shared


async def view(db: AsyncSession, user: User, job: Job) -> dict:
    plan = await db.get(JobSourcingPlan, job.id, populate_existing=True)
    channels = await _channels(db, job.id)
    linked = await _linked(db, job.id)
    shown = [(row, name) for row, name in linked if _sees(user, row)] if user.role in candidates.READERS else []
    compensation = await candidates.sees_compensation(db, user) if shown else False
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id.in_([plan.source_owner_user_id, plan.updated_by_user_id])))).all()} if plan else {}
    counted = await funnel(db, job.id, channels)
    return {
        "plan": {
            "target_profile": plan.target_profile if plan else None,
            "boolean_strings": plan.boolean_strings if plan else [],
            **{column: getattr(plan, column, None) for _, column in TARGETS},
            "deadline": plan.deadline if plan else None,
            "source_owner": person(people.get(plan.source_owner_user_id)) if plan else None,
            "updated_by": person(people.get(plan.updated_by_user_id)) if plan else None,
            "updated_at": plan.updated_at if plan else None,
        },
        "channels": [{"id": s.id, "name": s.name, "active": s.active} for s in channels],
        "searches": [saved_searches.out(row, name, user, compensation) for row, name in shown],
        "hidden_searches": len(linked) - len(shown),
        "funnel": counted,
        "progress": progress(plan, counted["total"], today_ist(await db_now(db))),
    }


# --- saving (S1-S3, S8, S10) --------------------------------------------------------------------------------------------------------
async def _team(db: AsyncSession, job: Job) -> set:
    assignees = (await db.scalars(select(JobAssignment.user_id).where(JobAssignment.job_id == job.id))).all()
    return {job.assigned_recruiter_user_id, job.backup_owner_user_id, *assignees} - {None}


async def _check_channels(db: AsyncSession, wanted: set, current: set) -> None:
    """S2: a new channel is an active source; one already planned stays even if it has since been switched off."""
    new = wanted - current
    if new and len((await db.scalars(select(RecCandidateSource.id).where(RecCandidateSource.id.in_(new), RecCandidateSource.active.is_(True)))).all()) != len(new):
        raise HTTPException(422, NO_SOURCE)


async def _check_searches(db: AsyncSession, user: User, wanted: set, current: set) -> None:
    """S3: a new link is a search the caller sees, added by a candidate reader."""
    new = wanted - current
    if not new:
        return
    if user.role not in candidates.READERS:
        raise HTTPException(403, NO_LINKING)
    found = (await db.scalars(select(SavedCandidateSearch.id).where(SavedCandidateSearch.id.in_(new), saved_searches.visible(user)))).all()
    if len(found) != len(new):
        raise HTTPException(422, NO_SEARCH)


async def save(db: AsyncSession, user: User, job: Job, body: RecSourcingPlanIn) -> bool:
    """Replaces the plan, its channels and the caller's visible links; links the caller cannot see are kept (S3). Returns whether anything changed."""
    plan = await db.get(JobSourcingPlan, job.id, populate_existing=True)
    before = {f: getattr(plan, f) for f in FIELDS} if plan else dict.fromkeys(FIELDS)
    before["boolean_strings"] = before["boolean_strings"] or []
    after = {**body.model_dump(include=set(FIELDS)), "boolean_strings": [s.model_dump() for s in body.boolean_strings]}
    if after["source_owner_user_id"] not in (None, before["source_owner_user_id"]) and after["source_owner_user_id"] not in await _team(db, job):
        raise HTTPException(422, NOT_ON_TEAM)

    current_channels = set((await db.scalars(select(JobSourcingChannel.source_id).where(JobSourcingChannel.job_id == job.id))).all())
    wanted_channels = set(body.channel_ids)
    await _check_channels(db, wanted_channels, current_channels)

    linked = [row for row, _ in await _linked(db, job.id)]
    hidden = {row.id for row in linked if not _sees(user, row)}
    current_searches = {row.id for row in linked}
    wanted_searches = set(body.saved_search_ids) | hidden
    await _check_searches(db, user, wanted_searches, current_searches)

    changed = [f for f in FIELDS if before[f] != after[f]]
    if wanted_channels != current_channels:
        changed.append("channels")
        for source_id in current_channels - wanted_channels:
            await db.delete(await db.get(JobSourcingChannel, (job.id, source_id)))
        db.add_all(JobSourcingChannel(job_id=job.id, source_id=s) for s in wanted_channels - current_channels)
    if wanted_searches != current_searches:
        changed.append("saved_searches")
        for search_id in current_searches - wanted_searches:
            await db.delete(await db.get(JobSourcingSearch, (job.id, search_id)))
        db.add_all(JobSourcingSearch(job_id=job.id, saved_search_id=s) for s in wanted_searches - current_searches)
    if not changed:
        return False
    if plan is None:
        plan = JobSourcingPlan(job_id=job.id, updated_by_user_id=user.id)
        db.add(plan)
    for field in FIELDS:
        setattr(plan, field, after[field])
    plan.updated_by_user_id = user.id
    plan.updated_at = func.now()  # a channel- or link-only change still dates the plan
    db.add(AuditLog(user_id=user.id, action="requirement_sourcing_plan.update", entity_type="job", entity_id=str(job.id), metadata_json={"fields": changed}))
    await db.flush()
    return True
