import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.identifiers import uuid_reference
from app.models import AcademicYear, AgentCommission, AuditLog, Batch, Company, Country, DataSubjectRequest, Enquiry, Enrollment, Job, JobApplication, Notification, NotificationDelivery, OverseasApplication, Payment, Program, School, University, User, UserRoleAssignment
from app.schemas import BatchCreate
from app.services.storage import storage

router = APIRouter(prefix="/admin", tags=["admin"])


async def ensure_admin(user: User = Depends(get_current_user)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin"}:
        raise HTTPException(403, "Admin role required")
    return user


@router.get("/dashboard")
async def dashboard(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    uq = select(func.count()).select_from(User)
    eq = select(func.count()).select_from(Enquiry)
    rq = select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.status == "paid")
    if user.role != "super_admin":
        uq = uq.where(User.division == user.division)
        eq = eq.where(Enquiry.division == user.division)
        rq = rq.where(Payment.division == user.division)
    return {
        "users": await db.scalar(uq),
        "enquiries": await db.scalar(eq),
        "revenue": float(await db.scalar(rq) or 0),
        "programs": await db.scalar(select(func.count()).select_from(Program)),
        "universities": await db.scalar(select(func.count()).select_from(University)),
        "overseas_applications": await db.scalar(select(func.count()).select_from(OverseasApplication)),
    }


@router.get("/users")
async def users(division: str | None = None, role: str | None = None, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(User)
    if user.role != "super_admin":
        stmt = stmt.where(User.division == user.division)
    elif division:
        stmt = stmt.where(User.division == division)
    if role:
        stmt = stmt.where(User.role == role)
    xs = (await db.scalars(stmt.order_by(User.created_at.desc()).limit(500))).all()
    # ADM-004: "views/edits directory detail records" -- `phone`/`profile` are exposed
    # here so a directory edit form can prefill existing values, not just the flat
    # list ADM-001's activate/deactivate action needed.
    return [{"id": x.id, "name": x.full_name, "email": x.email, "division": x.division, "role": x.role, "active": x.active, "phone": x.phone, "profile": x.profile} for x in xs]


@router.get("/programs")
async def programs(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    rows = (await db.scalars(select(Program).order_by(Program.title))).all()
    return [{"id": x.id, "slug": x.slug, "category": x.category, "title": x.title, "duration": x.duration, "fees": float(x.fees), "active": x.active} for x in rows]


@router.get("/universities")
async def universities(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "overseas_admin"}:
        raise HTTPException(403, "Overseas administrator required")
    rows = (await db.execute(select(University, Country).join(Country, Country.id == University.country_id).order_by(University.name))).all()
    return [{"id": u.id, "slug": u.slug, "name": u.name, "city": u.city, "country": country.name} for u, country in rows]


@router.get("/companies")
async def companies(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(Company).order_by(Company.name))).all()
    return [{"id": x.id, "name": x.name, "website": x.website, "partner_type": x.partner_type} for x in rows]


@router.get("/payments")
async def payment_records(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Payment, User).join(User, User.id == Payment.user_id)
    if user.role != "super_admin":
        stmt = stmt.where(Payment.division == user.division)
    rows = (await db.execute(stmt.order_by(Payment.created_at.desc()).limit(1000))).all()
    return [
        {
            "id": p.id,
            "user_id": target.id,
            "student": target.full_name,
            "division": p.division,
            "type": p.reference_type,
            "amount": float(p.amount),
            "currency": p.currency,
            "provider": p.provider,
            "status": p.status,
            "due_date": p.due_date,
        }
        for p, target in rows
    ]


@router.get("/notifications")
async def notification_records(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Notification, User).join(User, User.id == Notification.user_id)
    if user.role != "super_admin":
        stmt = stmt.where(User.division == user.division)
    rows = (await db.execute(stmt.order_by(Notification.created_at.desc()).limit(500))).all()
    notification_ids = [notification.id for notification, _ in rows]
    deliveries = (
        (
            await db.execute(
                select(NotificationDelivery.notification_id, func.count()).where(NotificationDelivery.notification_id.in_(notification_ids)).group_by(NotificationDelivery.notification_id)
            )
        ).all()
        if notification_ids
        else []
    )
    counts = dict(deliveries)
    return [
        {"id": n.id, "user_id": target.id, "recipient": target.full_name, "division": target.division, "title": n.title, "read": n.read, "deliveries": counts.get(n.id, 0), "created_at": n.created_at}
        for n, target in rows
    ]


@router.get("/applications")
async def applications(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    output = []
    if user.role in {"super_admin", "overseas_admin"}:
        rows = (
            await db.execute(
                select(OverseasApplication, University, User)
                .join(University, University.id == OverseasApplication.university_id)
                .join(User, User.id == OverseasApplication.student_id)
                .order_by(OverseasApplication.updated_at.desc())
                .limit(500)
            )
        ).all()
        output.extend(
            {
                "id": item.id,
                "division": "overseas",
                "student": student.full_name,
                "target": university.name,
                "status": item.status,
                "reference": item.application_reference,
                "updated_at": item.updated_at,
            }
            for item, university, student in rows
        )
    if user.role in {"super_admin", "it_admin"}:
        rows = (
            await db.execute(
                select(JobApplication, Job, Company, User)
                .join(Job, Job.id == JobApplication.job_id)
                .join(Company, Company.id == Job.company_id)
                .join(User, User.id == JobApplication.student_id)
                .order_by(JobApplication.updated_at.desc())
                .limit(500)
            )
        ).all()
        output.extend(
            {"id": item.id, "division": "it", "student": student.full_name, "target": f"{company.name} / {job.title}", "status": item.status, "reference": None, "updated_at": item.updated_at}
            for item, job, company, student in rows
        )
    return sorted(output, key=lambda item: item["updated_at"], reverse=True)


@router.get("/system-status")
async def system_status(user: User = Depends(ensure_admin)):
    return [
        {"service": "Environment", "status": settings.environment},
        {"service": "S3 document storage", "status": "configured" if settings.aws_s3_bucket else "local development storage"},
        {"service": "Google Meet", "status": "configured" if all((settings.google_client_id, settings.google_client_secret, settings.google_refresh_token)) else "manual fallback"},
        {
            "service": "Zoho Meeting",
            "status": "configured"
            if all((settings.zoho_client_id, settings.zoho_client_secret, settings.zoho_refresh_token, settings.zoho_organization_id, settings.zoho_presenter_id))
            else "manual fallback",
        },
        {"service": "Razorpay", "status": "configured" if settings.razorpay_key_id and settings.razorpay_key_secret else "not configured"},
        {"service": "Inbound university email", "status": "configured" if settings.inbound_email_webhook_secret else "not configured"},
    ]


@router.get("/leads")
async def leads(division: str | None = None, status: str | None = None, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(Enquiry)
    if user.role != "super_admin":
        stmt = stmt.where(Enquiry.division == user.division)
    elif division:
        stmt = stmt.where(Enquiry.division == division)
    if status:
        stmt = stmt.where(Enquiry.status == status)
    xs = (await db.scalars(stmt.order_by(Enquiry.created_at.desc()).limit(500))).all()
    return [
        {"id": x.id, "name": x.name, "email": x.email, "phone": x.phone, "division": x.division, "subject": x.subject, "status": x.status, "source": x.source, "crm_sync_status": x.crm_sync_status}
        for x in xs
    ]


@router.patch("/leads/{lead_id}")
async def update_lead(lead_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    x = await db.get(Enquiry, lead_id)
    if not x:
        raise HTTPException(404, "Lead not found")
    if user.role != "super_admin" and x.division != user.division:
        raise HTTPException(403, "Wrong division")
    for f in ("status", "owner_id"):
        if f in payload:
            setattr(x, f, payload[f])
    db.add(AuditLog(user_id=user.id, action="lead.update", entity_type="enquiry", entity_id=str(x.id), metadata_json=payload))
    await db.commit()
    return {"ok": True}


@router.get("/reports/summary")
async def reports(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    ds = ["it", "overseas"] if user.role == "super_admin" else [user.division]
    out = {}
    for d in ds:
        out[d] = {
            "users": await db.scalar(select(func.count()).select_from(User).where(User.division == d)),
            "leads": await db.scalar(select(func.count()).select_from(Enquiry).where(Enquiry.division == d)),
            "revenue": float(await db.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.division == d, Payment.status == "paid")) or 0),
        }
    return out


@router.post("/users", status_code=201)
async def create_user(payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.core.security import hash_password
    from app.models import AuditLog

    division = payload.get("division", user.division)
    role = payload["role"]
    if user.role != "super_admin" and division != user.division:
        raise HTTPException(403, "Cannot create users in another division")
    allowed_by_division = {
        "it": {"it_student", "trainer", "placement_team", "hr_team", "it_admin"},
        "overseas": {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin"},
        "global": {"super_admin"},
    }
    if role not in allowed_by_division.get(division, set()):
        raise HTTPException(422, "Role is not valid for the selected division")
    email = str(payload["email"]).lower().strip()
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    item = User(
        email=email,
        password_hash=hash_password(payload.get("password") or "ChangeMe@12345"),
        full_name=payload["full_name"],
        role=role,
        division=division,
        phone=payload.get("phone"),
        active=payload.get("active", True),
        email_verified=payload.get("email_verified", False),
        profile=payload.get("profile", {}),
    )
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="user.create", entity_type="user", entity_id=str(item.id), metadata_json={"role": role, "division": division}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "email": item.email, "role": item.role, "division": item.division}


@router.patch("/users/{user_id}")
async def update_user(user_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.models import AuditLog

    item = await db.get(User, user_id)
    if not item:
        raise HTTPException(404, "User not found")
    if user.role != "super_admin" and item.division != user.division:
        raise HTTPException(403, "Cannot edit another division")
    # ADM-001-AC02: deactivating a trainer with active/upcoming assigned batches is
    # blocked unless explicitly confirmed -- never a silent operation that would strand
    # those batches without a trainer.
    if payload.get("active") is False and item.active and item.role == "trainer" and not payload.get("confirm_cascade"):
        active_batches = await db.scalar(select(func.count()).select_from(Batch).where(Batch.trainer_id == item.id, Batch.status.in_(("upcoming", "active"))))
        if active_batches:
            raise HTTPException(409, f"This trainer has {active_batches} active/upcoming batch(es) assigned. Pass confirm_cascade to deactivate anyway.")
    for k in ("full_name", "phone", "active", "email_verified", "profile"):
        if k in payload:
            setattr(item, k, payload[k])
    db.add(AuditLog(user_id=user.id, action="user.update", entity_type="user", entity_id=str(item.id), metadata_json={k: v for k, v in payload.items() if k != "password"}))
    await db.commit()
    return {"ok": True}


@router.post("/programs", status_code=201)
async def create_program(payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.models import AuditLog, Program

    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    item = Program(
        slug=payload["slug"],
        category=payload["category"],
        title=payload["title"],
        summary=payload.get("summary", ""),
        duration=payload.get("duration", "TBC"),
        eligibility=payload.get("eligibility", ""),
        fees=payload.get("fees", 0),
        certification=payload.get("certification", "EduSphere Completion Certificate"),
        curriculum=payload.get("curriculum", []),
        placement_assistance=payload.get("placement_assistance", "Placement support subject to programme terms."),
        trainer_name=payload.get("trainer_name", "To be assigned"),
        active=payload.get("active", True),
    )
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="program.create", entity_type="program", entity_id=str(item.id), metadata_json={}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "slug": item.slug}


@router.patch("/programs/{program_id}")
async def update_program(program_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.models import AuditLog, Program

    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    item = await db.get(Program, program_id)
    if not item:
        raise HTTPException(404, "Program not found")
    # ADM-001-AC02: "Deleting/deactivating an entity with active dependents (e.g. a course
    # with active batches) is blocked or requires explicit cascade confirmation, never a
    # silent cascade." The base codebase let `active` flip to False with no check at all.
    if payload.get("active") is False and item.active and not payload.get("confirm_cascade"):
        active_batches = await db.scalar(select(func.count()).select_from(Batch).where(Batch.program_id == item.id, Batch.status.in_(("upcoming", "active"))))
        if active_batches:
            raise HTTPException(409, f"This program has {active_batches} active/upcoming batch(es). Pass confirm_cascade to deactivate anyway.")
    for k in ("category", "title", "summary", "duration", "eligibility", "fees", "certification", "curriculum", "placement_assistance", "trainer_name", "active"):
        if k in payload:
            setattr(item, k, payload[k])
    db.add(AuditLog(user_id=user.id, action="program.update", entity_type="program", entity_id=str(item.id), metadata_json=payload))
    await db.commit()
    return {"ok": True}


@router.post("/universities", status_code=201)
async def create_university(payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.models import AuditLog, Country, University

    if user.role not in {"super_admin", "overseas_admin"}:
        raise HTTPException(403, "Overseas administrator required")
    country = await db.scalar(select(Country).where(Country.slug == payload["country_slug"]))
    if not country:
        raise HTTPException(422, "Unknown country")
    item = University(
        country_id=country.id,
        slug=payload["slug"],
        name=payload["name"],
        city=payload.get("city", ""),
        overview=payload.get("overview", ""),
        eligibility=payload.get("eligibility", ""),
        requirements=payload.get("requirements", []),
        deadlines=payload.get("deadlines", []),
        scholarships=payload.get("scholarships", []),
    )
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="university.create", entity_type="university", entity_id=str(item.id), metadata_json={"country": country.slug}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "slug": item.slug}


@router.get("/batches")
async def batches(program_id: UUID | None = None, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    stmt = select(Batch, Program).join(Program)
    if program_id:
        stmt = stmt.where(Batch.program_id == program_id)
    rows = (await db.execute(stmt.order_by(Batch.start_date.desc()).limit(500))).all()
    counts = dict((await db.execute(select(Enrollment.batch_id, func.count(Enrollment.id)).where(Enrollment.status.in_(("active", "pending_consent"))).group_by(Enrollment.batch_id))).all())
    return [
        {
            "id": b.id,
            "program_id": p.id,
            "program": p.title,
            "trainer_id": b.trainer_id,
            "name": b.name,
            "start_date": b.start_date,
            "end_date": b.end_date,
            "schedule": b.schedule,
            "timezone": b.timezone,
            "capacity": b.capacity,
            "enrolled": counts.get(b.id, 0),
            "available": max(0, b.capacity - counts.get(b.id, 0)),
            "enrollment_open": b.enrollment_open,
            "mode": b.mode,
            "status": b.status,
        }
        for b, p in rows
    ]


@router.post("/batches", status_code=201)
async def create_batch(payload: BatchCreate, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    program = await db.get(Program, payload.program_id)
    if not program:
        raise HTTPException(404, "Program not found")
    if payload.end_date <= payload.start_date:
        raise HTTPException(422, "End date must be after start date")
    if payload.trainer_id:
        trainer = await db.get(User, payload.trainer_id)
        if not trainer or trainer.role != "trainer" or trainer.division != "it":
            raise HTTPException(422, "Valid IT trainer is required")
    if await db.scalar(select(Batch).where(Batch.name == payload.name)):
        raise HTTPException(409, "Batch name already exists")
    item = Batch(**payload.model_dump())
    db.add(item)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="batch.create", entity_type="batch", entity_id=str(item.id), metadata_json={"program_id": item.program_id, "capacity": item.capacity}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "name": item.name, "capacity": item.capacity}


@router.patch("/batches/{batch_id}")
async def update_batch(batch_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    item = await db.scalar(select(Batch).where(Batch.id == batch_id).with_for_update())
    if not item:
        raise HTTPException(404, "Batch not found")
    current = await db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.batch_id == item.id, Enrollment.status.in_(("active", "pending_consent")))) or 0
    if "capacity" in payload:
        # ADM-003-AC02 / DEC-WF-002: 20 students per slot, no more -- the create path
        # already enforces this via BatchCreate's own upper bound; this PATCH path had no
        # such check at all, so a capacity above 20 could be set after the fact.
        if int(payload["capacity"]) > 20:
            raise HTTPException(422, "Capacity cannot exceed 20 students per slot")
        if int(payload["capacity"]) < current:
            raise HTTPException(409, "Capacity cannot be lower than active enrollment")
    if "trainer_id" in payload and payload["trainer_id"] is not None:
        trainer = await db.get(User, uuid_reference(payload["trainer_id"], "trainer reference"))
        if not trainer or trainer.role != "trainer" or trainer.division != "it":
            raise HTTPException(422, "Valid IT trainer is required")
    allowed = {"trainer_id", "name", "start_date", "end_date", "schedule", "timezone", "capacity", "enrollment_open", "mode", "status"}
    for key, value in payload.items():
        if key not in allowed:
            continue
        if key in {"start_date", "end_date"} and isinstance(value, str):
            value = date.fromisoformat(value)
        if key == "trainer_id":
            value = uuid_reference(value, "trainer reference", required=False)
        setattr(item, key, value)
    db.add(AuditLog(user_id=user.id, action="batch.update", entity_type="batch", entity_id=str(item.id), metadata_json={k: v for k, v in payload.items() if k in allowed}))
    await db.commit()
    return {"id": item.id, "status": item.status, "capacity": item.capacity}


@router.get("/enrollments")
async def enrollments(batch_id: UUID | None = None, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    stmt = select(Enrollment, User, Batch).join(User, User.id == Enrollment.student_id).join(Batch, Batch.id == Enrollment.batch_id)
    if batch_id:
        stmt = stmt.where(Enrollment.batch_id == batch_id)
    rows = (await db.execute(stmt.order_by(Enrollment.created_at.desc()).limit(1000))).all()
    return [
        {
            "id": e.id,
            "enrollment_code": e.enrollment_code,
            "student_id": student.id,
            "student": student.full_name,
            "email": student.email,
            "batch_id": batch.id,
            "batch": batch.name,
            "schedule": batch.schedule,
            "status": e.status,
            "progress_percent": e.progress_percent,
            "slot_locked": e.slot_locked,
        }
        for e, student, batch in rows
    ]


@router.patch("/enrollments/{enrollment_id}")
async def update_enrollment(enrollment_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    item = await db.get(Enrollment, enrollment_id)
    if not item:
        raise HTTPException(404, "Enrollment not found")
    target_batch = uuid_reference(payload.get("batch_id"), "batch reference") if "batch_id" in payload else None
    if target_batch and target_batch != item.batch_id:
        target = await db.scalar(select(Batch).where(Batch.id == target_batch).with_for_update())
        if not target or not target.enrollment_open:
            raise HTTPException(409, "Target batch is unavailable")
        count = await db.scalar(select(func.count()).select_from(Enrollment).where(Enrollment.batch_id == target.id, Enrollment.status.in_(("active", "pending_consent")))) or 0
        if count >= target.capacity:
            raise HTTPException(409, "Target batch is full")
        item.batch_id = target.id
    # ADM-005-AC02: rejection is terminal -- the dedicated /approve endpoint already
    # refuses to revive a rejected enrolment; this generic PATCH must not offer a
    # back door to the same "silently proceed to active" outcome.
    if payload.get("status") == "active" and item.status == "rejected":
        raise HTTPException(409, "This enrolment was rejected and cannot be reactivated")
    for key in ("status", "progress_percent", "slot_locked"):
        if key in payload:
            setattr(item, key, payload[key])
    db.add(AuditLog(user_id=user.id, action="enrollment.update", entity_type="enrollment", entity_id=str(item.id), metadata_json=payload))
    await db.commit()
    return {"id": item.id, "batch_id": item.batch_id, "status": item.status, "progress_percent": item.progress_percent}


@router.post("/enrollments/{enrollment_id}/approve")
async def approve_enrollment(enrollment_id: UUID, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """ADM-005: "Admin approves; student enrolment becomes active." """
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    item = await db.get(Enrollment, enrollment_id)
    if not item:
        raise HTTPException(404, "Enrollment not found")
    if item.status == "rejected":
        # ADM-005-AC02: rejection is terminal for that enrolment attempt.
        raise HTTPException(409, "This enrolment was rejected and cannot be approved")
    item.status = "active"
    db.add(AuditLog(user_id=user.id, action="enrollment.approve", entity_type="enrollment", entity_id=str(item.id), metadata_json={}))
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/enrollments/{enrollment_id}/reject")
async def reject_enrollment(enrollment_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """ADM-005-AC02: rejection is terminal -- never silently proceeds to active afterward."""
    if user.role not in {"super_admin", "it_admin"}:
        raise HTTPException(403, "IT administrator required")
    item = await db.get(Enrollment, enrollment_id)
    if not item:
        raise HTTPException(404, "Enrollment not found")
    item.status = "rejected"
    db.add(AuditLog(user_id=user.id, action="enrollment.reject", entity_type="enrollment", entity_id=str(item.id), metadata_json={"reason": payload.get("reason")}))
    await db.commit()
    return {"id": item.id, "status": item.status}


@router.post("/payments", status_code=201)
async def create_payment(payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    from app.api.payments import _ensure_invoice, _ensure_receipt
    from app.models import AuditLog, Payment

    target = await db.get(User, uuid_reference(payload.get("user_id"), "user reference"))
    if not target:
        raise HTTPException(404, "User not found")
    if user.role != "super_admin" and target.division != user.division:
        raise HTTPException(403, "Wrong division")

    due = date.fromisoformat(payload["due_date"]) if payload.get("due_date") else None
    is_manual = payload.get("provider", "manual") == "manual"
    item = Payment(
        user_id=target.id,
        division=target.division,
        reference_type=payload.get("reference_type", "service_fee"),
        reference_id=uuid_reference(payload.get("reference_id"), "payment subject reference", required=False),
        amount=payload["amount"],
        currency=payload.get("currency", "INR"),
        provider=payload.get("provider", "manual"),
        provider_reference=payload.get("provider_reference"),
        status=payload.get("status", "pending"),
        due_date=due,
        is_manual=is_manual,
    )
    db.add(item)
    await db.flush()
    # PRD-PAY-003: an invoice is generated as soon as the bill (Payment) exists; if the Admin
    # recorded it as already paid (the manual/offline path, STU-010-AC02), the receipt is
    # generated in the same step rather than waiting for a webhook that will never arrive.
    await _ensure_invoice(db, item, target)
    if item.status in {"paid", "succeeded"}:
        await _ensure_receipt(db, item, target)
    db.add(AuditLog(user_id=user.id, action="payment.create", entity_type="payment", entity_id=str(item.id), metadata_json={"amount": float(item.amount), "division": item.division}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status}


@router.post("/payments/{payment_id}/discount")
async def discount_payment(payment_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """Applies a written-justification discount to a still-unpaid fee -- same "a
    discretionary change is never silent" pattern as `ADM-006`'s certificate override
    and `AGT-003`'s commission-amount adjustment. Only lowers the amount (never raises
    it -- that's `create_payment`'s own job) and only while nothing has actually been
    collected yet; a paid/succeeded payment is a completed transaction, not something
    this endpoint retroactively rewrites.
    """
    from app.api.payments import _ensure_invoice
    from app.models import Invoice

    item = await db.get(Payment, payment_id)
    if not item:
        raise HTTPException(404, "Payment not found")
    if user.role != "super_admin" and item.division != user.division:
        raise HTTPException(403, "Wrong division")
    if item.status not in {"pending", "overdue"}:
        raise HTTPException(409, "Only a pending or overdue payment can be discounted")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(422, "reason is required to discount a payment")
    try:
        new_amount = float(payload["amount"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, "A valid amount is required")
    if not (0 <= new_amount < float(item.amount)):
        raise HTTPException(422, f"Discounted amount must be between 0 and the current amount ({item.amount})")
    original_amount = float(item.amount)
    item.amount = new_amount
    # The invoice already generated for this still-unpaid bill (PRD-PAY-003: one is
    # generated as soon as a Payment exists) now shows a stale, pre-discount amount --
    # correct it, rather than leaving the wrong figure on file for a bill nobody has
    # paid yet. Never touched once `status` is paid/succeeded (guarded above).
    existing_invoice = await db.scalar(select(Invoice).where(Invoice.payment_id == item.id))
    if existing_invoice:
        await db.delete(existing_invoice)
        await db.flush()
    target = await db.get(User, item.user_id)
    await _ensure_invoice(db, item, target)
    db.add(
        AuditLog(
            user_id=user.id,
            action="payment.discount",
            entity_type="payment",
            entity_id=str(item.id),
            metadata_json={"original_amount": original_amount, "discounted_amount": new_amount, "reason": reason},
        )
    )
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "amount": float(item.amount), "status": item.status}


@router.post("/payments/emi-schedule", status_code=201)
async def create_emi_schedule(payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """Admin-discretionary EMI plan (see `EMISchedule`'s own docstring for why installment
    amounts aren't computed here): the Admin supplies each installment's amount and due date
    explicitly, and each becomes its own `Payment` row linked to the schedule.
    """
    from app.api.payments import _ensure_invoice
    from app.models import EMISchedule, Payment

    target = await db.get(User, uuid_reference(payload.get("user_id"), "user reference"))
    if not target:
        raise HTTPException(404, "User not found")
    if user.role != "super_admin" and target.division != user.division:
        raise HTTPException(403, "Wrong division")
    installments = payload.get("installments")
    if not isinstance(installments, list) or not installments:
        raise HTTPException(422, "At least one installment is required")
    currency = payload.get("currency", "INR")
    total_amount = sum(float(i["amount"]) for i in installments)
    schedule = EMISchedule(
        user_id=target.id,
        division=target.division,
        reference_type=payload.get("reference_type", "service_fee"),
        reference_id=uuid_reference(payload.get("reference_id"), "payment subject reference", required=False),
        total_amount=total_amount,
        currency=currency,
        installment_count=len(installments),
        created_by_id=user.id,
    )
    db.add(schedule)
    await db.flush()
    created_payments = []
    for i, installment in enumerate(installments, start=1):
        due = date.fromisoformat(installment["due_date"]) if installment.get("due_date") else None
        payment = Payment(
            user_id=target.id,
            division=target.division,
            reference_type=payload.get("reference_type", "service_fee"),
            reference_id=schedule.reference_id,
            amount=installment["amount"],
            currency=currency,
            provider="manual",
            status="pending",
            due_date=due,
            is_manual=True,
            emi_schedule_id=schedule.id,
            installment_no=i,
        )
        db.add(payment)
        await db.flush()
        await _ensure_invoice(db, payment, target)
        created_payments.append(payment)
    db.add(AuditLog(user_id=user.id, action="payment.emi_schedule.create", entity_type="emi_schedule", entity_id=str(schedule.id), metadata_json={"installment_count": len(installments), "division": schedule.division}))
    await db.commit()
    return {"id": schedule.id, "installment_count": schedule.installment_count, "total_amount": float(schedule.total_amount), "installments": [{"id": p.id, "installment_no": p.installment_no} for p in created_payments]}


@router.get("/audit")
async def audit(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(500)
    rows = (await db.scalars(stmt)).all()
    # Division admins only see events performed by users from their own division.
    if user.role != "super_admin":
        own_ids = set((await db.scalars(select(User.id).where(User.division == user.division))).all())
        rows = [x for x in rows if x.user_id in own_ids or x.user_id is None]
    return [{"id": x.id, "user_id": x.user_id, "action": x.action, "entity_type": x.entity_type, "entity_id": x.entity_id, "outcome": x.outcome, "metadata": x.metadata_json, "created_at": x.created_at} for x in rows]


@router.post("/audit/export", status_code=201)
async def export_audit_log(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # ADM-014-AC02 / RBAC_MATRIX.md #3 "Cross-division access": exporting the security/
    # audit log is itself a cross-division privileged action -- Super-Admin-only, unlike
    # the read-only `/audit` view above (which division admins already reach, filtered to
    # their own division via `ensure_admin`) -- and it must be self-audit-logged in the
    # same transaction as the export write, per this feature's own AC02 wording ("a
    # cross-division privileged action... is itself audit-logged").
    if user.role != "super_admin":
        raise HTTPException(403, "Super Admin role required")
    rows = (await db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(2000))).all()
    export = [
        {
            "id": str(x.id),
            "user_id": str(x.user_id) if x.user_id else None,
            "action": x.action,
            "entity_type": x.entity_type,
            "entity_id": x.entity_id,
            "outcome": x.outcome,
            "metadata": x.metadata_json,
            "created_at": x.created_at.isoformat(),
        }
        for x in rows
    ]
    key = f"audit-exports/{uuid4()}.json"
    storage.write_bytes(key, json.dumps(export).encode("utf-8"), "application/json")
    db.add(AuditLog(user_id=user.id, action="admin.audit_export", entity_type="audit_log", entity_id=None, outcome="exported", metadata_json={"row_count": len(export)}))
    await db.commit()
    return {"url": storage.presign_download(key), "row_count": len(export), "expires_in": 900 if storage.bucket else None}


@router.get("/data-requests")
async def data_requests(user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    # SEC-002: IT Admin (fulfil). Division admins only review requests from users in their
    # own division; super_admin sees all -- same posture as /audit above.
    stmt = select(DataSubjectRequest).order_by(DataSubjectRequest.created_at.desc()).limit(500)
    rows = (await db.scalars(stmt)).all()
    if user.role != "super_admin":
        own_ids = set((await db.scalars(select(User.id).where(User.division == user.division))).all())
        rows = [x for x in rows if x.requesting_user_id in own_ids]
    return [{"id": x.id, "requesting_user_id": x.requesting_user_id, "type": x.type, "status": x.status, "rejection_reason": x.rejection_reason, "created_at": x.created_at, "fulfilled_at": x.fulfilled_at} for x in rows]


@router.patch("/data-requests/{request_id}")
async def fulfil_data_request(request_id: UUID, payload: dict, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    item = await db.get(DataSubjectRequest, request_id)
    if not item:
        raise HTTPException(404, "Request not found")
    if item.type != "delete" or item.status != "in_progress":
        raise HTTPException(409, "Only an in-progress deletion request can be fulfilled here")
    subject = await db.get(User, item.requesting_user_id)
    if user.role != "super_admin" and subject.division != user.division:
        raise HTTPException(403, "Cross-division data request")
    decision = payload.get("decision")
    if decision not in {"fulfil", "reject"}:
        raise HTTPException(422, "decision must be 'fulfil' or 'reject'")
    if decision == "reject":
        reason = payload.get("reason")
        if not reason:
            raise HTTPException(422, "reason is required to reject a deletion request")
        item.status = "rejected"
        item.rejection_reason = reason
    else:
        # Conservative, bounded redaction: only the User row's own PII fields are
        # touched. Enrollment/Payment/ConsentRecord/AuditLog rows are never mutated here
        # (DATA_MODEL.md #8's "no hard delete of financial/audit/consent records" rule) --
        # the request would already have been rejected above if any of those existed for
        # this user (`_retention_hold_reason` in `account.py`).
        subject.full_name = "Deleted user"
        subject.phone = None
        subject.profile = {}
        subject.email = f"deleted-{subject.id}@deleted.local"
        subject.active = False
        item.status = "fulfilled"
        item.fulfilled_at = datetime.now(UTC)
    item.fulfilled_by_user_id = user.id
    db.add(AuditLog(user_id=user.id, action=f"gdpr.delete.{item.status}", entity_type="data_subject_request", entity_id=str(item.id), metadata_json={}))
    await db.commit()
    await db.refresh(item)
    return {"id": item.id, "status": item.status, "rejection_reason": item.rejection_reason}


# AGT-001: a distinct route namespace from `/admin` per API_CONTRACT.md #7 -- Overseas
# Admin approving/rejecting an Agent's own registration, not a generic IT/Overseas
# administration action.
agents_router = APIRouter(prefix="/overseas-admin", tags=["overseas-admin"])


async def _pending_agent_assignment(agent_id: UUID, user: User, db: AsyncSession) -> tuple[User, UserRoleAssignment]:
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    agent = await db.get(User, agent_id)
    if not agent or agent.role != "agent":
        raise HTTPException(404, "Agent not found")
    assignment = await db.scalar(select(UserRoleAssignment).where(UserRoleAssignment.user_id == agent.id, UserRoleAssignment.role == "agent"))
    if not assignment:
        raise HTTPException(404, "Agent registration not found")
    return agent, assignment


@agents_router.post("/agents/{agent_id}/approve")
async def approve_agent(agent_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, assignment = await _pending_agent_assignment(agent_id, user, db)
    assignment.approval_status = "approved"
    assignment.approved_by_user_id = user.id
    assignment.approved_at = datetime.now(UTC)
    # SEC-001: every Agent-approval action writes an audit record -- fail closed, not
    # open, if this write itself somehow failed (it shares the same transaction as the
    # approval below, so a rollback here rolls back the approval too, never the reverse).
    db.add(AuditLog(user_id=user.id, action="agent.approve", entity_type="user_role_assignment", entity_id=str(assignment.id), outcome="approved"))
    await db.commit()
    return {"id": assignment.id, "approval_status": assignment.approval_status}


@agents_router.post("/agents/{agent_id}/reject")
async def reject_agent(agent_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _, assignment = await _pending_agent_assignment(agent_id, user, db)
    assignment.approval_status = "rejected"
    assignment.approved_by_user_id = user.id
    assignment.approved_at = datetime.now(UTC)
    db.add(AuditLog(user_id=user.id, action="agent.reject", entity_type="user_role_assignment", entity_id=str(assignment.id), outcome="rejected"))
    await db.commit()
    return {"id": assignment.id, "approval_status": assignment.approval_status}


@agents_router.get("/agents")
async def list_agents(status: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    stmt = select(User, UserRoleAssignment).join(UserRoleAssignment, UserRoleAssignment.user_id == User.id).where(User.role == "agent", UserRoleAssignment.role == "agent")
    if status:
        stmt = stmt.where(UserRoleAssignment.approval_status == status)
    rows = (await db.execute(stmt.order_by(User.created_at.desc()))).all()
    return [{"id": agent.id, "name": agent.full_name, "email": agent.email, "approval_status": assignment.approval_status} for agent, assignment in rows]


@agents_router.post("/commissions/{commission_id}/approve-payout")
async def approve_commission_payout(commission_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # AGT-004: net-new -- no equivalent existed in the base codebase
    # (REFERENCE_IMPLEMENTATION_FINDINGS.md #5.4). PRD.md #6.4's confirmed state machine
    # ("...Commission Accrued -> Payout Requested -> Overseas Admin Approval -> Paid")
    # names only two actions -- the Agent's existing claim (already `status="claimed"`)
    # and this one. DATA_MODEL.md #6.7 additionally lists a "payout_pending" status as a
    # net-new intermediate state and states "claimed can never transition directly to
    # paid" -- honored here by genuinely writing the commission through payout_pending
    # (with its own audit row) before advancing to paid, even though both happen within
    # this one approval request, since no third actor/action is named anywhere to trigger
    # that transition independently.
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    item = await db.get(AgentCommission, commission_id)
    if not item:
        raise HTTPException(404, "Commission not found")
    if item.status != "claimed":
        raise HTTPException(409, "Commission must be claimed by the Agent before payout can be approved")
    # NFR-SEC-002 / RBAC_MATRIX.md #2.8 two-gate rule: the Overseas Admin identity who
    # created an admin-manually-entered commission cannot be the sole actor also
    # approving its own payout. Confirmed scope note (not silently widened): RBAC_MATRIX
    # ties this explicitly to `created_by` at creation time ("for system-triggered
    # accrual, any Overseas Admin may approve since no single admin created it") -- a
    # system_trigger-created commission whose amount an Admin later set via AGT-003's
    # `PATCH .../commissions/{id}` is not covered by this confirmed rule as written. That
    # is a real, deliberate gap in the confirmed contract, not something this endpoint
    # invents a stricter rule to close -- see docs/product/PRD_OPEN_ITEMS.md.
    if item.created_by == "admin_manual":
        creator_user_id = await db.scalar(
            select(AuditLog.user_id)
            .where(AuditLog.entity_type == "agent_commission", AuditLog.entity_id == str(item.id), AuditLog.action == "agent.commission_create")
            .order_by(AuditLog.created_at.asc())
            .limit(1)
        )
        if creator_user_id is not None and creator_user_id == user.id:
            raise HTTPException(403, "The Overseas Admin who created this commission cannot also approve its own payout")
    item.status = "payout_pending"
    db.add(AuditLog(user_id=user.id, action="agent.commission_payout_pending", entity_type="agent_commission", entity_id=str(item.id), outcome="pending"))
    item.status = "paid"
    item.paid_at = datetime.now(UTC)
    item.payout_approved_by_user_id = user.id
    item.payout_approved_at = datetime.now(UTC)
    db.add(AuditLog(user_id=user.id, action="agent.commission_payout_approve", entity_type="agent_commission", entity_id=str(item.id), outcome="approved"))
    await db.commit()
    return {"id": item.id, "status": item.status, "paid_at": item.paid_at}


# SCH-003: Overseas Admin creates a School partner record and its seed School Coordinator
# account together, both active immediately -- no approval gate, unlike Agent
# (`DEC-SCOPE-012`). Same `/overseas-admin` namespace as the Agent approval routes above,
# per `API_CONTRACT.md` §12A.
@agents_router.post("/schools", status_code=201)
async def create_school(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.core.security import hash_password

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    email = str(payload.get("coordinator_email", "")).lower().strip()
    if not payload.get("name") or not email or not payload.get("coordinator_full_name"):
        raise HTTPException(422, "School name and Coordinator name/email are required")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    tier = payload.get("tier")
    if tier and tier not in {"bronze", "silver", "gold", "platinum"}:
        raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
    tier_valid_until = date.fromisoformat(payload["tier_valid_until"]) if payload.get("tier_valid_until") else None
    school = School(name=payload["name"], city=payload.get("city"), state=payload.get("state"), created_by_user_id=user.id, tier=tier, tier_valid_until=tier_valid_until)
    db.add(school)
    await db.flush()
    coordinator = User(
        email=email,
        password_hash=hash_password(payload.get("coordinator_password") or "ChangeMe@12345"),
        full_name=payload["coordinator_full_name"],
        role="school_coordinator",
        division="overseas",
        active=True,
        email_verified=False,
        profile={"school_id": str(school.id)},
    )
    db.add(coordinator)
    await db.flush()
    # DATA_MODEL.md §6.12: `UserRoleAssignment` is created eagerly here (not lazily on
    # first login like `auth._sync_role_assignment`) so `created_by_user_id`/`assigned_by_
    # user_id` records the acting Overseas Admin from the moment the account exists,
    # satisfying the provisioning audit trail (RBAC_MATRIX.md §3) without waiting for the
    # Coordinator's first login.
    db.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    db.add(AuditLog(user_id=user.id, action="school.create", entity_type="school", entity_id=str(school.id), metadata_json={"name": school.name}))
    db.add(AuditLog(user_id=user.id, action="school.coordinator_seed", entity_type="user", entity_id=str(coordinator.id), metadata_json={"school_id": str(school.id)}))
    await db.commit()
    return {"id": school.id, "name": school.name, "coordinator_id": coordinator.id, "coordinator_email": coordinator.email}


@agents_router.get("/schools")
async def list_schools(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    rows = (await db.scalars(select(School).order_by(School.created_at.desc()))).all()
    return [{"id": s.id, "name": s.name, "city": s.city, "state": s.state, "tier": s.tier, "tier_valid_until": s.tier_valid_until, "created_at": s.created_at} for s in rows]


@agents_router.patch("/schools/{school_id}")
async def update_school_tier(school_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """`DEC-SCOPE-017` -- Overseas Admin sets/changes a School's partnership tier after
    creation. Deliberately narrow: only tier/tier_valid_until are editable here, not the
    identity fields `create_school` already owns."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")
    if "tier" in payload:
        tier = payload["tier"]
        if tier and tier not in {"bronze", "silver", "gold", "platinum"}:
            raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
        school.tier = tier
    if "tier_valid_until" in payload:
        school.tier_valid_until = date.fromisoformat(payload["tier_valid_until"]) if payload["tier_valid_until"] else None
    db.add(AuditLog(user_id=user.id, action="school.tier_update", entity_type="school", entity_id=str(school.id), metadata_json={"tier": school.tier}))
    await db.commit()
    return {"id": school.id, "tier": school.tier, "tier_valid_until": school.tier_valid_until}


ACADEMIC_YEAR_STATUSES = ["draft", "active", "closed"]


@agents_router.post("/academic-years", status_code=201)
async def create_academic_year(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-001 -- global, admin-only academic-year calendar. Mirrors create_school's
    shape; unlike create_school's duplicate-email check, this inserts directly and lets
    the unique constraint on `label` pick the winner (spec's security review item 1 --
    a pre-check SELECT is a race, not a guard)."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    label = str(payload.get("label", "")).strip()
    if not label:
        raise HTTPException(422, "label is required")
    if len(label) > 20:
        raise HTTPException(422, "label must be at most 20 characters")
    try:
        start_date = date.fromisoformat(payload["start_date"])
        end_date = date.fromisoformat(payload["end_date"])
    except (KeyError, ValueError, TypeError):
        # TypeError covers a non-string value (e.g. JSON `null`, a number) for either
        # field -- `date.fromisoformat` raises TypeError rather than ValueError for
        # those, and an uncaught TypeError would otherwise surface as a 500 instead of
        # the 422 malformed input deserves.
        raise HTTPException(422, "start_date and end_date are required, in YYYY-MM-DD format")
    if end_date <= start_date:
        raise HTTPException(422, "end_date must be after start_date")
    year = AcademicYear(label=label, start_date=start_date, end_date=end_date, status="draft")
    db.add(year)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, f"an academic year with label '{label}' already exists")
    db.add(AuditLog(user_id=user.id, action="school.academic_year_create", entity_type="academic_year", entity_id=str(year.id), metadata_json={"label": year.label, "status": year.status}))
    await db.commit()
    return {"id": year.id, "label": year.label, "start_date": year.start_date, "end_date": year.end_date, "status": year.status}


@agents_router.patch("/academic-years/{year_id}")
async def update_academic_year_status(year_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Note: nothing here (or anywhere else) enforces that at most one AcademicYear
    row has status == "active" at a time -- this endpoint only validates forward-only
    status transitions for the single row it's given. Callers that need "the" active
    year (GET /school/academic-years/active in schools.py, and _current_academic_year_id())
    resolve any such ambiguity by picking the most recent start_date -- a documented
    best-effort convention, not a uniqueness guarantee."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    year = await db.get(AcademicYear, year_id)
    if not year:
        raise HTTPException(404, "Academic year not found")
    if "status" in payload:
        new_status = payload["status"]
        if new_status not in ACADEMIC_YEAR_STATUSES:
            raise HTTPException(422, f"status must be one of {ACADEMIC_YEAR_STATUSES}")
        if ACADEMIC_YEAR_STATUSES.index(new_status) < ACADEMIC_YEAR_STATUSES.index(year.status):
            raise HTTPException(409, f"cannot move status backward from '{year.status}' to '{new_status}'")
        year.status = new_status
    db.add(AuditLog(user_id=user.id, action="school.academic_year_status_change", entity_type="academic_year", entity_id=str(year.id), metadata_json={"label": year.label, "status": year.status}))
    await db.commit()
    return {"id": year.id, "label": year.label, "start_date": year.start_date, "end_date": year.end_date, "status": year.status}


@agents_router.get("/academic-years")
async def list_academic_years(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    rows = (await db.scalars(select(AcademicYear).order_by(AcademicYear.start_date.desc()))).all()
    return [{"id": r.id, "label": r.label, "start_date": r.start_date, "end_date": r.end_date, "status": r.status} for r in rows]


# SCH-004/005/006 (DEC-SCOPE-014): only Overseas Admin or Super Admin creates an
# academic_team/career_counselor/psychometric_team account -- a separate path from
# SCH-003's SchoolAccountInvite flow, which covers only the four school-side roles.
SCHOOL_SERVICE_ROLES = {"academic_team", "career_counselor", "psychometric_team"}


@agents_router.post("/school-staff", status_code=201)
async def create_school_staff(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.core.security import hash_password
    from app.models import SchoolStaffAssignment

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    role = payload.get("role")
    if role not in SCHOOL_SERVICE_ROLES:
        raise HTTPException(422, f"role must be one of {sorted(SCHOOL_SERVICE_ROLES)}")
    email = str(payload.get("email", "")).lower().strip()
    full_name = str(payload.get("full_name", "")).strip()
    if not email or not full_name:
        raise HTTPException(422, "email and full_name are required")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    school_ids = payload.get("school_ids") or []
    schools = (await db.scalars(select(School).where(School.id.in_(school_ids)))).all() if school_ids else []
    if len(schools) != len(set(school_ids)):
        raise HTTPException(422, "One or more school_ids do not exist")

    staff = User(
        email=email,
        password_hash=hash_password(payload.get("password") or "ChangeMe@12345"),
        full_name=full_name,
        role=role,
        division="overseas",
        active=True,
        email_verified=False,
        profile={},
    )
    db.add(staff)
    await db.flush()
    db.add(UserRoleAssignment(user_id=staff.id, division="overseas", role=role, is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    for school in schools:
        db.add(SchoolStaffAssignment(user_id=staff.id, school_id=school.id, role=role, assigned_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.staff_create", entity_type="user", entity_id=str(staff.id), metadata_json={"role": role, "school_ids": [str(s.id) for s in schools]}))
    await db.commit()
    return {"id": staff.id, "email": staff.email, "role": staff.role, "school_ids": [str(s.id) for s in schools]}


@agents_router.get("/school-staff")
async def list_school_staff(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import SchoolStaffAssignment

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    rows = (await db.scalars(select(User).where(User.role.in_(SCHOOL_SERVICE_ROLES)).order_by(User.created_at.desc()))).all()
    assignments = (await db.scalars(select(SchoolStaffAssignment))).all()
    portfolio_by_user: dict = {}
    for a in assignments:
        portfolio_by_user.setdefault(a.user_id, []).append(a.school_id)
    return [{"id": u.id, "name": u.full_name, "email": u.email, "role": u.role, "school_ids": [str(sid) for sid in portfolio_by_user.get(u.id, [])]} for u in rows]


@agents_router.get("/school-students/lookup")
async def lookup_school_student_by_code(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Resolves a School student's business-facing `student_code` (added 2026-09-15,
    `DEC-DATA-003`) to a real record -- exactly the "short, searchable, memorable" lookup
    use case that field was built for, used here so Overseas Admin/Counselor can find a
    School student across every school without a raw internal-id picker."""
    from app.models import School, SchoolStudent

    if user.role not in {"overseas_admin", "counselor", "super_admin"}:
        raise HTTPException(403, "Overseas Admin or Counselor role required")
    student = await db.scalar(select(SchoolStudent).where(SchoolStudent.student_code == code.strip().upper()))
    if not student:
        raise HTTPException(404, "No school student found with that Student ID")
    school = await db.get(School, student.school_id)
    return {"id": student.id, "full_name": student.full_name, "student_code": student.student_code, "school_name": school.name if school else None}


# --- DEC-SCOPE-018: School->Overseas bridge ----------------------------------------------
# Overseas Admin/Counselor (never school_coordinator, per direct user decision) links a
# School-affiliated student to a real Overseas application. `OverseasApplication.
# student_id` is nullable as of this decision specifically for this case --
# `school_student_id` is set instead, since a SchoolStudent never gets a `users` row
# (`DEC-ROLE-004`). Deliberately a new, separate endpoint rather than a branch inside
# `workflows.create_overseas_application`: that endpoint hard-validates a real
# overseas_student User and notifies it directly, neither of which applies here.

@agents_router.post("/school-students/{school_student_id}/applications", status_code=201)
async def create_bridged_application(school_student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.api.schools import _notify_student_parents
    from app.models import ApplicationStatusHistory, SchoolStudent

    if user.role not in {"overseas_admin", "counselor", "super_admin"}:
        raise HTTPException(403, "Overseas Admin or Counselor role required")
    student = await db.get(SchoolStudent, school_student_id)
    if not student:
        raise HTTPException(404, "School student not found")
    university = await db.get(University, uuid_reference(payload.get("university_id"), "university"))
    if not university:
        raise HTTPException(404, "University not found")
    intake = str(payload.get("intake", "")).strip()
    if not intake:
        raise HTTPException(422, "intake is required")
    duplicate = await db.scalar(
        select(OverseasApplication.id).where(
            OverseasApplication.school_student_id == student.id, OverseasApplication.university_id == university.id, OverseasApplication.status != "withdrawn"
        )
    )
    if duplicate:
        raise HTTPException(409, "An application for this university already exists for this student")
    item = OverseasApplication(
        student_id=None,
        school_student_id=student.id,
        university_id=university.id,
        course_id=uuid_reference(payload.get("course_id"), "course", required=False),
        counselor_id=user.id if user.role == "counselor" else None,
        intake=intake,
        status="enquiry",
        next_action="Complete profile and required document checklist",
    )
    db.add(item)
    await db.flush()
    db.add(ApplicationStatusHistory(application_id=item.id, from_status=None, to_status=item.status, next_action=item.next_action, changed_by_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.overseas_application_link", entity_type="overseas_application", entity_id=str(item.id), metadata_json={"school_student_id": str(student.id), "university_id": str(university.id)}))
    await _notify_student_parents(db, student, title=f"Overseas application started for {student.full_name}", body=f"An application to {university.name} has been started for {student.full_name}.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return {"id": item.id, "school_student_id": item.school_student_id, "university_id": item.university_id, "status": item.status}


@agents_router.get("/school-applications")
async def list_bridged_applications(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import SchoolStudent

    if user.role not in {"overseas_admin", "counselor", "super_admin"}:
        raise HTTPException(403, "Overseas Admin or Counselor role required")
    stmt = (
        select(OverseasApplication, SchoolStudent, University)
        .join(SchoolStudent, SchoolStudent.id == OverseasApplication.school_student_id)
        .join(University, University.id == OverseasApplication.university_id)
        .where(OverseasApplication.school_student_id.is_not(None))
        .order_by(OverseasApplication.created_at.desc())
    )
    if user.role == "counselor":
        stmt = stmt.where(OverseasApplication.counselor_id == user.id)
    rows = (await db.execute(stmt)).all()
    return [{"id": a.id, "student_name": s.full_name, "student_code": s.student_code, "university_name": u.name, "status": a.status, "created_at": a.created_at} for a, s, u in rows]


@agents_router.post("/school-staff/{staff_id}/portfolio")
async def add_school_staff_portfolio(staff_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import SchoolStaffAssignment

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    staff = await db.get(User, staff_id)
    if not staff or staff.role not in SCHOOL_SERVICE_ROLES:
        raise HTTPException(404, "Specialized-role staff account not found")
    school_id = payload.get("school_id")
    school = await db.get(School, school_id) if school_id else None
    if not school:
        raise HTTPException(422, "A valid school_id is required")
    existing = await db.scalar(select(SchoolStaffAssignment).where(SchoolStaffAssignment.user_id == staff.id, SchoolStaffAssignment.school_id == school.id))
    if existing:
        raise HTTPException(409, "This school is already in this staff member's portfolio")
    assignment = SchoolStaffAssignment(user_id=staff.id, school_id=school.id, role=staff.role, assigned_by_user_id=user.id)
    db.add(assignment)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.staff_portfolio_add", entity_type="school_staff_assignment", entity_id=str(assignment.id), metadata_json={"staff_id": str(staff.id), "school_id": str(school.id)}))
    await db.commit()
    return {"id": assignment.id, "user_id": staff.id, "school_id": school.id}
