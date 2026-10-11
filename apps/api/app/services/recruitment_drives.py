"""rec-029 (DEC-SCOPE-178, spec §1-§3): campus recruitment drives -- rules, reads, the funnel and the drive tag on a new application.

A drive belongs to its company: every read and write goes through rec-003's company scope (`caller_scope` / `load_scoped`), so another
recruiter's drive is the same 404 as a missing one (DR8). Writes need the company's `can_edit` and lock the company, then the drive. The
funnel is computed from the applications that carry the drive (DR7, Appendix B C4-C7) in one query. Functions only; nothing here commits.
Logs and audit carry ids and field names only."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    RECRUITMENT_DRIVE_CODE_SEQ,
    AuditLog,
    BdmOrganization,
    Candidate,
    Company,
    DriveRequirement,
    Interview,
    Job,
    JobApplication,
    JobApplicationStatusHistory,
    RecruitmentDrive,
    User,
)
from app.schemas import RecDriveCreate, RecDriveUpdate
from app.services import applications
from app.services import recruiter_companies as companies
from app.services.recruiter import ROLE
from app.services.recruiter_meetings import field_error
from app.services.recruiter_requirements import ENDED

logger = logging.getLogger("app.recruiter")

NOT_FOUND = "Drive not found"
CANCELLED = "This drive was cancelled"
COLLEGE_ONE = "Choose a college from the list or type its name"
COLLEGE_INVALID = "Choose a college from the list"
REQUIREMENTS_INVALID = "Choose open requirements of this drive's company"
ATTENDED_ABOVE = "Students attended cannot be more than students registered"
REQUIREMENT_IN_USE = "A requirement with candidates added through this drive cannot be removed"
DRIVE_INVALID = "Choose a drive that includes this requirement"
STATUS_LABELS = {"planned": "Planned", "completed": "Completed", "cancelled": "Cancelled"}
COLLEGE_ORG_TYPES = ("college", "university")  # DR2: BDM organisations a college can be
REACHED_SHORTLISTED = ("shortlisted", "profile_shared", "interview", "selected", "joined")  # C4
REACHED_SELECTED = ("selected", "joined")  # C6
INTERVIEW_DONE = ("completed", "selected", "rejected")  # C5: a held interview (no_show and open ones are not)

D = RecruitmentDrive
A = JobApplication
H = JobApplicationStatusHistory


# --- reads ---------------------------------------------------------------------------------------------------------------------------
def _reached(statuses: tuple[str, ...]):
    """The application is at one of `statuses` now, or was at one (its history), so a later rejection keeps it counted."""
    return or_(A.status.in_(statuses), exists().where(H.application_id == A.id, H.to_status.in_(statuses)))


async def funnel(db: AsyncSession, drive_id: UUID) -> dict:
    """DR7 / AC1: the typed counts and the computed ones, in one statement."""
    interviewed = exists().where(Interview.application_id == A.id, Interview.status.in_(INTERVIEW_DONE))
    row = (await db.execute(
        select(
            D.students_registered, D.students_attended, func.count(A.id), func.count(A.id).filter(_reached(REACHED_SHORTLISTED)),
            func.count(A.id).filter(interviewed), func.count(A.id).filter(_reached(REACHED_SELECTED)), func.count(A.id).filter(A.status == "joined"),
        ).select_from(D).outerjoin(A, A.drive_id == D.id).where(D.id == drive_id).group_by(D.id)
    )).one()
    return dict(zip(("registered", "attended", "tagged", "shortlisted", "interviewed", "selected", "joined"), row, strict=True))


def _college(drive: D, org: BdmOrganization | None) -> dict:
    if org is None:
        return {"org_id": None, "code": None, "name": drive.college_name, "city": None}
    return {"org_id": org.id, "code": org.code, "name": org.name, "city": org.city}


def _out(user: User, drive: D, company: Company, org: BdmOrganization | None) -> dict:
    return {
        "id": drive.id, "code": drive.drive_code, "status": drive.status, "status_label": STATUS_LABELS[drive.status], "drive_date": drive.drive_date,
        "job_role": drive.job_role, "vacancies": drive.vacancies, "eligibility": drive.eligibility,
        "students_registered": drive.students_registered, "students_attended": drive.students_attended,
        "company": {"id": company.id, "code": company.company_code, "name": company.name}, "college": _college(drive, org),
        "can_edit": drive.status != "cancelled" and companies.permissions(user, company)["can_edit"],
        "created_at": drive.created_at, "updated_at": drive.updated_at,
    }


def _rows():
    return select(D, Company, BdmOrganization).join(Company, Company.id == D.company_id).outerjoin(BdmOrganization, BdmOrganization.id == D.college_org_id)


async def list_page(db: AsyncSession, user: User, pattern: str | None, status: str | None, limit: int, offset: int) -> dict:
    """The caller's companies' drives, latest drive date first; `pattern` matches the code, role, college and company."""
    where: list = await companies.caller_scope(db, user)
    if status:
        where.append(D.status == status)
    if pattern:
        where.append(or_(*(c.ilike(pattern) for c in (D.drive_code, D.job_role, D.college_name, BdmOrganization.name, Company.name))))
    base = _rows().where(*where)
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    count = select(func.count()).where(DriveRequirement.drive_id == D.id).scalar_subquery()
    rows = (await db.execute(base.add_columns(count).order_by(D.drive_date.desc(), D.drive_code.desc()).limit(limit).offset(offset))).all()
    return {
        "items": [{**_out(user, d, c, o), "requirement_count": n} for d, c, o, n in rows], "total": total or 0, "limit": limit, "offset": offset,
        "can_create": user.role in (ROLE, "super_admin"),
    }


async def detail(db: AsyncSession, user: User, drive_id: UUID) -> dict:
    drive, company, org = (await db.execute(_rows().where(D.id == drive_id).execution_options(populate_existing=True))).one()
    requirements = (await db.execute(
        select(Job.id, Job.requirement_code, Job.title, Job.status).join(DriveRequirement, DriveRequirement.job_id == Job.id)
        .where(DriveRequirement.drive_id == drive_id).order_by(func.lower(Job.title), Job.id)
    )).all()
    return {
        **_out(user, drive, company, org), "funnel": await funnel(db, drive_id),
        "requirements": [{"id": i, "code": code, "title": title, "status": status, "open": status not in ENDED} for i, code, title, status in requirements],
        "statuses": applications.catalogue(),
    }


async def candidates_page(db: AsyncSession, drive_id: UUID, limit: int, offset: int) -> dict:
    """The applications tagged with the drive, by candidate name."""
    where = A.drive_id == drive_id
    total = await db.scalar(select(func.count()).select_from(A).where(where))
    rows = (await db.execute(
        select(A, Candidate, Job).join(Candidate, Candidate.id == A.candidate_id).join(Job, Job.id == A.job_id).where(where)
        .order_by(func.lower(Candidate.name), A.id).limit(limit).offset(offset)
    )).all()
    return {
        "items": [{
            "application_id": a.id, "candidate": {"id": c.id, "code": c.candidate_code, "name": c.name},
            "requirement": {"id": j.id, "code": j.requirement_code, "title": j.title}, "status": a.status, "status_label": applications.label(a.status),
        } for a, c, j in rows],
        "total": total or 0, "limit": limit, "offset": offset,
    }


async def college_options(db: AsyncSession, pattern: str | None, limit: int) -> dict:
    """DR2's picker: live BDM college and university organisations -- code, name and city only."""
    where: list = [BdmOrganization.org_type.in_(COLLEGE_ORG_TYPES), BdmOrganization.archived_at.is_(None)]
    if pattern:
        where.append(or_(BdmOrganization.name.ilike(pattern), BdmOrganization.code.ilike(pattern)))
    total = await db.scalar(select(func.count()).select_from(BdmOrganization).where(*where))
    rows = (await db.scalars(select(BdmOrganization).where(*where).order_by(func.lower(BdmOrganization.name), BdmOrganization.id).limit(limit))).all()
    return {"items": [{"id": o.id, "code": o.code, "name": o.name, "city": o.city} for o in rows], "total": total or 0}


# --- scope -----------------------------------------------------------------------------------------------------------------------------
async def load(db: AsyncSession, user: User, drive_id: UUID, *, lock: bool = False) -> tuple[Company, D]:
    """In the caller's company scope, else 404 (other roles 403 from the scope). With `lock`, the company and then the drive are locked."""
    company_id = await db.scalar(select(D.company_id).where(D.id == drive_id))
    if company_id is None:
        raise HTTPException(404, NOT_FOUND)
    try:
        company = await companies.load_scoped(db, user, company_id, lock=lock)
    except HTTPException as exc:
        raise HTTPException(404, NOT_FOUND) if exc.status_code == 404 else exc from None
    stmt = select(D).where(D.id == drive_id).execution_options(populate_existing=True)
    drive = await db.scalar(stmt.with_for_update() if lock else stmt)
    if drive is None:  # never in practice (drives are not deleted); narrows the type without an assert
        raise HTTPException(404, NOT_FOUND)
    return company, drive


# --- rules -----------------------------------------------------------------------------------------------------------------------------
async def _check_college(db: AsyncSession, values: dict, changed: bool) -> None:
    """DR2: exactly one of the two; a newly picked org must be a live BDM college or university (a kept one stays when archived)."""
    org_id = values["college_org_id"]
    if (org_id is None) == (values["college_name"] is None):
        raise field_error("college_org_id", COLLEGE_ONE)
    if changed and org_id is not None and await db.scalar(select(BdmOrganization.id).where(
        BdmOrganization.id == org_id, BdmOrganization.org_type.in_(COLLEGE_ORG_TYPES), BdmOrganization.archived_at.is_(None),
    )) is None:
        raise field_error("college_org_id", COLLEGE_INVALID, str(org_id))


def _check_counts(values: dict) -> None:
    """DR6 / AC2, on the merged values."""
    if values["students_attended"] > values["students_registered"]:
        raise field_error("students_attended", ATTENDED_ABOVE, values["students_attended"])


async def _check_requirements(db: AsyncSession, company_id: UUID, added: set[UUID]) -> None:
    """DR4: each added requirement is a live requirement of the drive's company."""
    if added and await db.scalar(select(func.count()).select_from(Job).where(Job.id.in_(added), Job.company_id == company_id, Job.status.not_in(ENDED))) != len(added):
        raise field_error("requirement_ids", REQUIREMENTS_INVALID)


# --- writes ----------------------------------------------------------------------------------------------------------------------------
async def create(db: AsyncSession, user: User, company: Company, payload: RecDriveCreate) -> D:
    """The caller locked the company and checked `can_edit`."""
    values = payload.model_dump(exclude={"company_id", "requirement_ids"})
    await _check_college(db, values, changed=True)
    _check_counts(values)
    wanted = set(payload.requirement_ids)
    await _check_requirements(db, company.id, wanted)
    code = f"DRV-{await db.scalar(select(RECRUITMENT_DRIVE_CODE_SEQ.next_value())):06d}"
    drive = D(drive_code=code, company_id=company.id, created_by_user_id=user.id, **values)
    db.add(drive)
    await db.flush()
    db.add_all([DriveRequirement(drive_id=drive.id, job_id=job_id) for job_id in wanted])
    audit(db, user, "create", drive.id, {"company_id": str(company.id), "college_org": drive.college_org_id is not None, "requirements": len(wanted)})
    return drive


async def update(db: AsyncSession, user: User, drive: D, payload: RecDriveUpdate) -> list[str]:
    """DR3-DR6 on the merged values; only changed values count (no audit for none). Returns the changed field names."""
    if drive.status == "cancelled":
        raise HTTPException(409, CANCELLED)
    changes = payload.model_dump(exclude_unset=True, exclude={"requirement_ids"})
    if payload.model_fields_set & {"college_org_id", "college_name"}:
        changes |= {"college_org_id": payload.college_org_id, "college_name": payload.college_name}
    changed = [key for key, value in changes.items() if getattr(drive, key) != value]
    merged = {key: changes.get(key, getattr(drive, key)) for key in ("college_org_id", "college_name", "students_registered", "students_attended")}
    await _check_college(db, merged, changed="college_org_id" in changed)
    _check_counts(merged)
    if payload.requirement_ids is not None:
        wanted = set(payload.requirement_ids)
        stored = set((await db.scalars(select(DriveRequirement.job_id).where(DriveRequirement.drive_id == drive.id))).all())
        if wanted != stored:
            removed = stored - wanted
            if removed and await db.scalar(select(A.id).where(A.drive_id == drive.id, A.job_id.in_(removed)).limit(1)):
                raise HTTPException(409, REQUIREMENT_IN_USE)
            await _check_requirements(db, drive.company_id, wanted - stored)
            if removed:
                await db.execute(delete(DriveRequirement).where(DriveRequirement.drive_id == drive.id, DriveRequirement.job_id.in_(removed)))
            db.add_all([DriveRequirement(drive_id=drive.id, job_id=job_id) for job_id in wanted - stored])
            changed.append("requirement_ids")
    for key in changed:
        if key != "requirement_ids":
            setattr(drive, key, changes[key])
    changed.sort()
    if changed:
        audit(db, user, "update", drive.id, {"fields": changed})
    return changed


async def check_tag(db: AsyncSession, user: User, job: Job, drive_id: UUID) -> None:
    """DR9, for rec-017's add: a drive in the caller's scope that includes this requirement (else 422 on `drive_id`), not cancelled (409).
    The drive row is share-locked so it cannot be cancelled under the add."""
    drive = await db.scalar(
        select(D).join(Company, Company.id == D.company_id)
        .where(D.id == drive_id, *await companies.caller_scope(db, user), exists().where(DriveRequirement.drive_id == D.id, DriveRequirement.job_id == job.id))
        .with_for_update(read=True, of=D)
    )
    if drive is None:
        raise field_error("drive_id", DRIVE_INVALID, str(drive_id))
    if drive.status == "cancelled":
        raise HTTPException(409, CANCELLED)


def audit(db: AsyncSession, user: User, action: str, drive_id, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=user.id, action=f"recruitment_drive.{action}", entity_type="recruitment_drive", entity_id=str(drive_id), metadata_json=metadata or {}))


def log(event: str, user: User, drive_id, **extra) -> None:
    logger.info(event, extra={"extra_fields": {"actor_id": str(user.id), "drive_id": str(drive_id), **extra}})
