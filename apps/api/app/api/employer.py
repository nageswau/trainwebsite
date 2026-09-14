from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import _set_auth_cookies, _sync_role_assignment
from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.models import AuditLog, Batch, Company, EmployerProfile, Enrollment, Interview, Job, JobApplication, PlacementProfile, Program, User
from app.schemas import EmployerInterviewCreate, EmployerJobCreate, EmployerJobUpdate, EmployerRegistrationRequest, EmployerShortlistCreate, UserOut

router = APIRouter(prefix="/employer", tags=["employer"])


@router.post("/register")
async def register_employer(payload: EmployerRegistrationRequest, response: Response, db: AsyncSession = Depends(get_db)):
    # EMP-001-AC02: no partial state -- User, Company, and EmployerProfile are all created
    # (or none are) in one transaction, then committed together.
    email = payload.email.lower().strip()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    company_name = payload.company_name.strip()
    if await db.scalar(select(Company).where(Company.name == company_name)):
        raise HTTPException(409, "A company with this name is already registered")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        role="employer",
        division="it",
        phone=payload.phone,
        active=True,
        email_verified=False,
        profile={"registration_source": "employer_self_service"},
    )
    db.add(user)
    await db.flush()

    company = Company(name=company_name, website=payload.company_website, partner_type="employer", owner_type="employer_self_service", employer_user_id=user.id)
    db.add(company)
    await db.flush()

    # registration_status stays null -- approval-before-activation is an open item
    # (FEATURE_QUESTIONS.md #7); this account is active and usable immediately.
    db.add(EmployerProfile(user_id=user.id, company_id=company.id, registration_status=None))
    await _sync_role_assignment(db, user)
    db.add(AuditLog(user_id=user.id, action="employer.register", entity_type="user", entity_id=str(user.id), metadata_json={"company_id": str(company.id)}))
    await db.commit()

    loaded = await db.scalar(select(User).where(User.id == user.id).options(selectinload(User.role_assignments)))
    assert loaded is not None
    _set_auth_cookies(response, loaded)
    return {"user": UserOut.model_validate(loaded), "company": {"id": company.id, "name": company.name}, "expires_in_minutes": settings.access_token_minutes}


async def _own_profile(user: User, db: AsyncSession) -> tuple[EmployerProfile, Company]:
    if user.role != "employer":
        raise HTTPException(403, "Employer role required")
    profile = await db.scalar(select(EmployerProfile).where(EmployerProfile.user_id == user.id))
    if not profile:
        raise HTTPException(404, "Employer profile not found")
    company = await db.get(Company, profile.company_id)
    return profile, company


@router.get("/profile")
async def get_employer_profile(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile, company = await _own_profile(user, db)
    return {"full_name": user.full_name, "email": user.email, "phone": user.phone, "company_name": company.name, "company_website": company.website, "logo_url": company.logo_url, "registration_status": profile.registration_status}


@router.patch("/profile")
async def update_employer_profile(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    profile, company = await _own_profile(user, db)
    if "company_website" in payload:
        company.website = payload["company_website"]
    if "full_name" in payload:
        user.full_name = payload["full_name"].strip()
    if "phone" in payload:
        user.phone = payload["phone"]
    db.add(AuditLog(user_id=user.id, action="employer.profile.update", entity_type="company", entity_id=str(company.id), metadata_json={"fields": list(payload)}))
    await db.commit()
    return {"full_name": user.full_name, "email": user.email, "phone": user.phone, "company_name": company.name, "company_website": company.website, "registration_status": profile.registration_status}


def _job_out(job: Job) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "location": job.location,
        "description": job.description,
        "skills": job.skills,
        "status": job.status,
        "closes_on": job.closes_on,
        # EMP-002-AC02: a posting past its own closing date is never shown to Students
        # as open, even if the Employer never explicitly closed it -- surfaced here too
        # so the Employer's own listing doesn't imply it's still visible when it isn't.
        "visible_to_students": job.status == "open" and (job.closes_on is None or job.closes_on >= date.today()),
    }


@router.post("/jobs", status_code=201)
async def create_employer_job(payload: EmployerJobCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # API_CONTRACT.md #6: a posting starts "draft" -- whether it needs staff
    # pending_review before publishing is an open mediation question, so no such gate is
    # invented here; the Employer publishes their own draft by setting status "open"
    # themselves via the update endpoint below, same as EMP-001's own "no invented
    # approval gate" precedent.
    _, company = await _own_profile(user, db)
    job = Job(company_id=company.id, title=payload.title, location=payload.location, description=payload.description, skills=payload.skills, status="draft", closes_on=payload.closes_on)
    db.add(job)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="employer.job.create", entity_type="job", entity_id=str(job.id)))
    await db.commit()
    await db.refresh(job)
    return _job_out(job)


@router.get("/jobs")
async def list_employer_jobs(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, company = await _own_profile(user, db)
    rows = (await db.scalars(select(Job).where(Job.company_id == company.id).order_by(Job.created_at.desc()))).all()
    return [_job_out(job) for job in rows]


@router.patch("/jobs/{job_id}")
async def update_employer_job(job_id: UUID, payload: EmployerJobUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, company = await _own_profile(user, db)
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    # EMP-002-AC03: an Employer cannot act on a posting outside their own company, even
    # via a direct job id -- the same class of assigned-scope check this session's
    # Overseas work (CNS-001-AC02, etc.) already applies elsewhere.
    if job.company_id != company.id:
        raise HTTPException(403, "Job is outside your own postings")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(job, key, value)
    # `date` values aren't JSON-serializable directly -- the JSON column's own
    # serializer would fail at commit time otherwise.
    audit_changes = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in changes.items()}
    db.add(AuditLog(user_id=user.id, action="employer.job.update", entity_type="job", entity_id=str(job.id), metadata_json=audit_changes))
    await db.commit()
    await db.refresh(job)
    return _job_out(job)


@router.get("/candidates")
async def search_candidates(q: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # EMP-003-AC02/AC03: reads `PlacementProfile`, per API_CONTRACT.md #6, and returns
    # only a conservative allowlist -- name, course, skills, availability -- never raw
    # contact info (email/phone), pending confirmation of the exact GDPR-approved field
    # set. Excludes only withdrawn candidates by default, the same "active pool" rule
    # ADM-007-AC02 already established (`available=False` means temporarily unavailable,
    # still an active candidate -- surfaced as a real field below, not filtered out).
    if user.role != "employer":
        raise HTTPException(403, "Employer role required")
    stmt = (
        select(User, PlacementProfile)
        .join(PlacementProfile, PlacementProfile.student_id == User.id)
        .where(User.division == "it", User.role == "it_student", User.active.is_(True), PlacementProfile.withdrawn.is_(False))
        .order_by(User.full_name)
    )
    rows = (await db.execute(stmt)).all()
    student_ids = [student.id for student, _ in rows]
    latest_course: dict[UUID, str] = {}
    if student_ids:
        enrollment_rows = (
            await db.execute(
                select(Enrollment.student_id, Program.title)
                .join(Batch, Batch.id == Enrollment.batch_id)
                .join(Program, Program.id == Batch.program_id)
                .where(Enrollment.student_id.in_(student_ids))
                .order_by(Enrollment.student_id, Enrollment.created_at.desc())
            )
        ).all()
        for student_id, title in enrollment_rows:
            latest_course.setdefault(student_id, title)
    results = []
    for student, profile in rows:
        skills = student.profile.get("skills", [])
        course = latest_course.get(student.id)
        if q:
            haystack = f"{student.full_name} {course or ''} {' '.join(skills)}".lower()
            if q.lower() not in haystack:
                continue
        results.append({"student_id": student.id, "name": student.full_name, "course": course, "skills": skills, "availability": profile.available})
    return results


async def _own_job(job_id, company: Company, db: AsyncSession) -> Job:
    job = await db.get(Job, job_id)
    if not job or job.company_id != company.id:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/shortlist")
async def list_shortlist(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, company = await _own_profile(user, db)
    rows = (
        await db.execute(
            select(JobApplication, User, Job)
            .join(User, User.id == JobApplication.student_id)
            .join(Job, Job.id == JobApplication.job_id)
            .where(Job.company_id == company.id)
            .order_by(JobApplication.created_at.desc())
        )
    ).all()
    return [{"id": application.id, "candidate": student.full_name, "job_title": job.title, "status": application.status} for application, student, job in rows]


@router.post("/shortlist", status_code=201)
async def shortlist_candidate(payload: EmployerShortlistCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # EMP-004-AC03: an Employer can only shortlist against their own posting, even via a
    # direct job id -- same IDOR discipline as the job-update endpoint above.
    _, company = await _own_profile(user, db)
    await _own_job(payload.job_id, company, db)
    student = await db.get(User, payload.student_id)
    if not student or student.role != "it_student":
        raise HTTPException(422, "Valid student candidate is required")
    existing = await db.scalar(select(JobApplication).where(JobApplication.job_id == payload.job_id, JobApplication.student_id == payload.student_id))
    if existing:
        raise HTTPException(409, "This candidate is already shortlisted/applied for this posting")
    item = JobApplication(job_id=payload.job_id, student_id=payload.student_id, status="shortlisted")
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="employer.shortlist", entity_type="job_application", entity_id=str(item.id)))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "job_id": item.job_id, "student_id": item.student_id, "status": item.status}


@router.post("/interviews", status_code=201)
async def schedule_interview(payload: EmployerInterviewCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, company = await _own_profile(user, db)
    application = await db.get(JobApplication, payload.application_id)
    if not application:
        raise HTTPException(404, "Shortlisted application not found")
    # EMP-004-AC03: own candidates only -- verified via the application's own job,
    # even via a direct application id.
    await _own_job(application.job_id, company, db)
    # EMP-004-AC02: flagged (409), not silently double-booked -- no `duration` field
    # exists anywhere on `Interview` to compute a true overlap window, so the only
    # honestly detectable conflict, without inventing an assumed duration, is another
    # interview already scheduled for this same candidate at the exact same instant.
    conflict = await db.scalar(
        select(Interview.id)
        .join(JobApplication, JobApplication.id == Interview.application_id)
        .where(JobApplication.student_id == application.student_id, Interview.scheduled_at == payload.scheduled_at)
    )
    if conflict:
        raise HTTPException(409, "This candidate already has an interview scheduled at this time")
    item = Interview(application_id=application.id, scheduled_at=payload.scheduled_at, mode=payload.mode, meeting_url=payload.meeting_url)
    db.add(item)
    await db.flush()
    if application.status == "applied":
        application.status = "shortlisted"
    db.add(AuditLog(user_id=user.id, action="employer.interview.schedule", entity_type="interview", entity_id=str(item.id)))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "application_id": item.application_id, "scheduled_at": item.scheduled_at, "mode": item.mode}


@router.get("/interviews")
async def list_employer_interviews(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, company = await _own_profile(user, db)
    rows = (
        await db.execute(
            select(Interview, JobApplication, User, Job)
            .join(JobApplication, JobApplication.id == Interview.application_id)
            .join(User, User.id == JobApplication.student_id)
            .join(Job, Job.id == JobApplication.job_id)
            .where(Job.company_id == company.id)
            .order_by(Interview.scheduled_at.desc())
        )
    ).all()
    return [
        {"id": interview.id, "candidate": student.full_name, "job_title": job.title, "scheduled_at": interview.scheduled_at, "mode": interview.mode, "meeting_url": interview.meeting_url, "result": interview.result}
        for interview, _application, student, job in rows
    ]
