from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models import (
    BlogPost,
    CareerApplication,
    CareerPath,
    Certificate,
    Company,
    Country,
    Enquiry,
    Event,
    GalleryItem,
    Job,
    OverseasCourse,
    Program,
    RealProject,
    Scholarship,
    Testimonial,
    University,
    User,
    WebinarRegistration,
)
from app.schemas import CareerPathOut, CountryOut, EnquiryIn, ProgramOut, RealProjectOut, TestimonialOut, UniversityOut, WebinarRegistrationIn
from app.worker import sync_enquiry_to_crm_task

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/home")
async def home(db: AsyncSession = Depends(get_db)):
    programs = (await db.scalars(select(Program).where(Program.active.is_(True)).limit(6))).all()
    testimonials = (await db.scalars(select(Testimonial).limit(6))).all()
    events = (await db.scalars(select(Event).order_by(Event.starts_at).limit(6))).all()
    partners = (await db.scalars(select(Company).limit(12))).all()
    return {
        "hero": {"title": "Welcome to EduSphere", "tagline": "Empowering Careers. Building Global Opportunities."},
        "verticals": [{"key": "it", "title": "IT Training & Placement", "href": "/it"}, {"key": "overseas", "title": "Overseas Education", "href": "/overseas"}],
        "stats": {"learners": 1250, "placements": 830, "university_partners": 75, "visa_success_rate": 96},
        "programs": [ProgramOut.model_validate(x).model_dump() for x in programs],
        "testimonials": [{"name": x.person_name, "headline": x.headline, "quote": x.quote, "division": x.division} for x in testimonials],
        "events": [{"id": x.id, "title": x.title, "division": x.division, "starts_at": x.starts_at, "location": x.location} for x in events],
        "partners": [{"id": x.id, "name": x.name, "type": x.partner_type} for x in partners],
    }


@router.get("/programs", response_model=list[ProgramOut])
async def programs(category: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Program).where(Program.active.is_(True))
    if category:
        stmt = stmt.where(Program.category == category)
    if q:
        stmt = stmt.where(or_(Program.title.ilike(f"%{q}%"), Program.summary.ilike(f"%{q}%")))
    return (await db.scalars(stmt.order_by(Program.category, Program.title))).all()


@router.get("/programs/{slug}", response_model=ProgramOut)
async def program(slug: str, db: AsyncSession = Depends(get_db)):
    x = await db.scalar(select(Program).where(Program.slug == slug, Program.active.is_(True)))
    if not x:
        raise HTTPException(404, "Program not found")
    return x


@router.get("/career-paths", response_model=list[CareerPathOut])
async def career_paths(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(CareerPath).where(CareerPath.published.is_(True))
    if division:
        stmt = stmt.where(CareerPath.division == division)
    return (await db.scalars(stmt.order_by(CareerPath.title))).all()


@router.get("/career-paths/{slug}", response_model=CareerPathOut)
async def career_path(slug: str, db: AsyncSession = Depends(get_db)):
    x = await db.scalar(select(CareerPath).where(CareerPath.slug == slug, CareerPath.published.is_(True)))
    if not x:
        raise HTTPException(404, "Career path not found")
    return x


@router.get("/real-projects", response_model=list[RealProjectOut])
async def real_projects(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(RealProject).where(RealProject.published.is_(True))
    if division:
        stmt = stmt.where(RealProject.division == division)
    return (await db.scalars(stmt.order_by(RealProject.title))).all()


@router.get("/real-projects/{slug}", response_model=RealProjectOut)
async def real_project(slug: str, db: AsyncSession = Depends(get_db)):
    x = await db.scalar(select(RealProject).where(RealProject.slug == slug, RealProject.published.is_(True)))
    if not x:
        raise HTTPException(404, "Real project not found")
    return x


@router.get("/testimonials", response_model=list[TestimonialOut])
async def testimonials(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Testimonial)
    if division:
        stmt = stmt.where(Testimonial.division == division)
    return (await db.scalars(stmt.order_by(Testimonial.person_name))).all()


@router.get("/testimonials/{testimonial_id}", response_model=TestimonialOut)
async def testimonial(testimonial_id: UUID, db: AsyncSession = Depends(get_db)):
    x = await db.get(Testimonial, testimonial_id)
    if not x:
        raise HTTPException(404, "Success story not found")
    return x


@router.get("/countries", response_model=list[CountryOut])
async def countries(db: AsyncSession = Depends(get_db)):
    return (await db.scalars(select(Country).order_by(Country.name))).all()


@router.get("/countries/{slug}")
async def country(slug: str, db: AsyncSession = Depends(get_db)):
    c = await db.scalar(select(Country).where(Country.slug == slug))
    if not c:
        raise HTTPException(404, "Country not found")
    us = (await db.scalars(select(University).where(University.country_id == c.id).limit(20))).all()
    ss = (await db.scalars(select(Scholarship).where(Scholarship.country_id == c.id, Scholarship.active.is_(True)).limit(20))).all()
    return {
        "country": CountryOut.model_validate(c),
        "universities": [UniversityOut.model_validate(u) for u in us],
        "scholarships": [{"id": s.id, "title": s.title, "amount": s.amount, "eligibility": s.eligibility, "deadline": s.deadline} for s in ss],
    }


@router.get("/universities", response_model=list[UniversityOut])
async def universities(country: str | None = None, q: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(University).join(Country)
    if country:
        stmt = stmt.where(Country.slug == country)
    if q:
        stmt = stmt.where(or_(University.name.ilike(f"%{q}%"), University.city.ilike(f"%{q}%")))
    return (await db.scalars(stmt.order_by(University.name))).all()


@router.get("/universities/{slug}")
async def university(slug: str, db: AsyncSession = Depends(get_db)):
    u = await db.scalar(select(University).where(University.slug == slug))
    if not u:
        raise HTTPException(404, "University not found")
    cs = (await db.scalars(select(OverseasCourse).where(OverseasCourse.university_id == u.id))).all()
    return {
        "university": UniversityOut.model_validate(u),
        "courses": [{"id": c.id, "title": c.title, "level": c.level, "category": c.category, "duration": c.duration, "tuition_fee": c.tuition_fee, "intake": c.intake} for c in cs],
    }


@router.get("/overseas-courses")
async def overseas_courses(category: str | None = None, level: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(OverseasCourse, University, Country)
        .join(University, OverseasCourse.university_id == University.id)
        .join(Country, University.country_id == Country.id)
    )
    if category:
        stmt = stmt.where(OverseasCourse.category == category)
    if level:
        stmt = stmt.where(OverseasCourse.level == level)
    rows = (await db.execute(stmt.limit(100))).all()
    return [
        {"id": c.id, "title": c.title, "level": c.level, "category": c.category, "duration": c.duration, "tuition_fee": c.tuition_fee, "intake": c.intake, "university": u.name, "country": co.name}
        for c, u, co in rows
    ]


@router.get("/jobs")
async def jobs(db: AsyncSession = Depends(get_db)):
    # EMP-002-AC02: a posting past its own closing date is not shown as open, even if
    # the Employer never explicitly closed it -- `status` alone was previously trusted.
    rows = (
        await db.execute(select(Job, Company).join(Company).where(Job.status == "open", or_(Job.closes_on.is_(None), Job.closes_on >= date.today())).order_by(Job.created_at.desc()))
    ).all()
    return [{"id": j.id, "title": j.title, "company": c.name, "location": j.location, "skills": j.skills, "closes_on": j.closes_on} for j, c in rows]


@router.get("/events")
async def events(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(Event)
    if division:
        stmt = stmt.where(Event.division == division)
    xs = (await db.scalars(stmt.order_by(Event.starts_at))).all()
    return [{"id": x.id, "division": x.division, "title": x.title, "event_type": x.event_type, "starts_at": x.starts_at, "location": x.location, "description": x.description} for x in xs]


@router.get("/webinars")
async def webinars(division: str = "it", db: AsyncSession = Depends(get_db)):
    # PUB-004: reuses Event (no dedicated Webinar table -- see DATA_MODEL.md §2.4
    # correction / alembic 0009). Upcoming/past split is computed here rather than
    # stored, since "past" is just "starts_at has elapsed," not a field to invent.
    xs = (await db.scalars(select(Event).where(Event.division == division).order_by(Event.starts_at))).all()
    now = datetime.now(UTC)
    return [
        {
            "id": x.id,
            "division": x.division,
            "title": x.title,
            "event_type": x.event_type,
            "starts_at": x.starts_at,
            "location": x.location,
            "description": x.description,
            "is_past": x.starts_at < now,
        }
        for x in xs
    ]


@router.get("/webinars/{event_id}")
async def webinar_detail(event_id: UUID, db: AsyncSession = Depends(get_db)):
    x = await db.get(Event, event_id)
    if not x:
        raise HTTPException(404, "Webinar not found")
    now = datetime.now(UTC)
    return {
        "id": x.id,
        "division": x.division,
        "title": x.title,
        "event_type": x.event_type,
        "starts_at": x.starts_at,
        "location": x.location,
        "description": x.description,
        "registration_url": x.registration_url,
        "is_past": x.starts_at < now,
    }


@router.post("/webinars/{event_id}/register", status_code=201)
async def webinar_register(event_id: UUID, payload: WebinarRegistrationIn, db: AsyncSession = Depends(get_db)):
    event = await db.get(Event, event_id)
    if not event:
        raise HTTPException(404, "Webinar not found")
    if event.starts_at < datetime.now(UTC):
        # AC02's edge case (SCR-PUB-016): a past/closed webinar shows a closed state,
        # not an open form -- enforced server-side, not just hidden in the UI.
        raise HTTPException(409, "Registration is closed for this webinar")
    # Capacity/waitlist rule is a documented open item (PUB-004-AC02, DATA_MODEL.md §2.4)
    # -- accept unconditionally rather than inventing an unspecified cap.
    x = WebinarRegistration(event_id=event_id, full_name=payload.full_name, email=payload.email, phone=payload.phone)
    db.add(x)
    await db.commit()
    await db.refresh(x)
    return {"id": x.id, "event_id": x.event_id, "status": "registered"}


@router.get("/scholarships")
async def scholarships(db: AsyncSession = Depends(get_db)):
    xs = (await db.scalars(select(Scholarship).where(Scholarship.active.is_(True)).order_by(Scholarship.deadline))).all()
    return [{"id": x.id, "title": x.title, "eligibility": x.eligibility, "amount": x.amount, "deadline": x.deadline} for x in xs]


@router.get("/search")
async def search(q: str = Query(min_length=2), db: AsyncSession = Depends(get_db)):
    ps = (await db.scalars(select(Program).where(or_(Program.title.ilike(f"%{q}%"), Program.summary.ilike(f"%{q}%"))).limit(10))).all()
    us = (await db.scalars(select(University).where(or_(University.name.ilike(f"%{q}%"), University.city.ilike(f"%{q}%"))).limit(10))).all()
    bs = (await db.scalars(select(BlogPost).where(or_(BlogPost.title.ilike(f"%{q}%"), BlogPost.summary.ilike(f"%{q}%"))).limit(10))).all()
    return {
        "programs": [{"title": x.title, "href": f"/it/programs/{x.slug}"} for x in ps],
        "universities": [{"title": x.name, "href": f"/overseas/universities/{x.slug}"} for x in us],
        "articles": [{"title": x.title, "href": f"/news/{x.slug}"} for x in bs],
    }


@router.post("/enquiries", status_code=201)
async def create_enquiry(payload: EnquiryIn, db: AsyncSession = Depends(get_db)):
    x = Enquiry(
        division=payload.division,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        subject=payload.subject,
        message=payload.message,
        source=payload.source,
        metadata_json=payload.metadata,
        crm_sync_status="pending",
    )
    db.add(x)
    await db.commit()
    await db.refresh(x)
    # Outbox pattern (INTEGRATION_CONTRACTS.md §1): the enquiry is already committed above
    # -- the webhook attempt is queued for the background worker so a slow/unreachable
    # CRM endpoint can never block or lose this response (PUB-002-AC02).
    sync_enquiry_to_crm_task.delay(str(x.id))
    return {"id": x.id, "status": x.status, "crm_sync_status": x.crm_sync_status}


@router.get("/posts")
async def post_list(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(BlogPost).where(BlogPost.published.is_(True))
    if division:
        stmt = stmt.where(BlogPost.division == division)
    rows = (await db.scalars(stmt.order_by(BlogPost.created_at.desc()).limit(100))).all()
    return [{"id": x.id, "division": x.division, "slug": x.slug, "title": x.title, "summary": x.summary, "category": x.category, "created_at": x.created_at} for x in rows]


@router.get("/posts/{slug}")
async def post_detail(slug: str, db: AsyncSession = Depends(get_db)):
    x = await db.scalar(select(BlogPost).where(BlogPost.slug == slug, BlogPost.published.is_(True)))
    if not x:
        raise HTTPException(404, "Post not found")
    return {"id": x.id, "division": x.division, "slug": x.slug, "title": x.title, "summary": x.summary, "body": x.body, "category": x.category, "created_at": x.created_at}


@router.get("/gallery")
async def gallery(division: str | None = None, db: AsyncSession = Depends(get_db)):
    stmt = select(GalleryItem).where(GalleryItem.published.is_(True))
    if division:
        stmt = stmt.where(GalleryItem.division == division)
    rows = (await db.scalars(stmt.order_by(GalleryItem.created_at.desc()).limit(100))).all()
    return [{"id": x.id, "division": x.division, "title": x.title, "image_url": x.image_url, "alt_text": x.alt_text, "category": x.category} for x in rows]


@router.post("/jobs/{job_id}/apply", status_code=201)
async def public_job_apply(job_id: UUID, payload: dict, db: AsyncSession = Depends(get_db)):
    import secrets

    job = await db.get(Job, job_id)
    # EMP-002-AC02: a posting past its own closing date is not open, even if the
    # Employer never explicitly closed it -- applies here too, not just to the listing.
    if not job or job.status != "open" or (job.closes_on and job.closes_on < date.today()):
        raise HTTPException(404, "Open job not found")
    for required in ("full_name", "email", "resume_url"):
        if not payload.get(required):
            raise HTTPException(422, f"{required} is required")
    code = "EDU-CAREER-" + secrets.token_hex(5).upper()
    item = CareerApplication(
        job_id=job_id,
        full_name=payload["full_name"],
        email=payload["email"].lower(),
        phone=payload.get("phone"),
        resume_url=payload["resume_url"],
        cover_note=payload.get("cover_note"),
        status="submitted",
        tracking_code=code,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "tracking_code": item.tracking_code, "status": item.status}


@router.get("/career-applications/{tracking_code}")
async def public_job_tracking(tracking_code: str, email: str, db: AsyncSession = Depends(get_db)):
    item = await db.scalar(select(CareerApplication).where(CareerApplication.tracking_code == tracking_code, CareerApplication.email == email.lower()))
    if not item:
        raise HTTPException(404, "Application not found")
    job = await db.get(Job, item.job_id)
    return {"tracking_code": item.tracking_code, "status": item.status, "job_title": job.title if job else "Job", "updated_at": item.updated_at}


@router.get("/certificates/{verification_code}")
async def verify_certificate(verification_code: str, db: AsyncSession = Depends(get_db)):
    row = (
        await db.execute(
            select(Certificate, User, Program)
            .join(User, User.id == Certificate.student_id)
            .join(Program, Program.id == Certificate.program_id)
            .where(Certificate.verification_code == verification_code, Certificate.status == "issued")
        )
    ).first()
    if not row:
        raise HTTPException(404, "Valid certificate not found")
    certificate, student, program = row
    return {"valid": True, "certificate_no": certificate.certificate_no, "student": student.full_name, "program": program.title, "issued_on": certificate.issued_on}


@router.post("/career-upload", status_code=201)
async def career_upload(file: UploadFile = File(...)):
    import uuid
    from pathlib import Path

    import boto3

    allowed = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Resume must be PDF, DOC or DOCX")
    data = await file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Resume is limited to 5 MB")
    suffix = Path(file.filename or "resume.pdf").suffix.lower()
    key = f"career-resumes/{uuid.uuid4().hex}{suffix}"
    if settings.aws_s3_bucket:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.put_object(Bucket=settings.aws_s3_bucket, Key=key, Body=data, ContentType=file.content_type, ServerSideEncryption="AES256")
        return {"url": f"s3://{settings.aws_s3_bucket}/{key}", "storage": "s3", "size": len(data)}
    dest = Path(settings.local_upload_dir) / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return {"url": f"/local-files/{key}", "storage": "local", "size": len(data)}
