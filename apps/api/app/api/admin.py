import json
import logging
import re
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.identifiers import unique_student_code, uuid_reference
from app.models import AcademicYear, AgentCommission, AuditLog, Batch, Company, Country, DataSubjectRequest, Enquiry, Enrollment, Job, JobApplication, Notification, NotificationDelivery, OverseasApplication, Payment, Program, School, SchoolStaffAssignment, SchoolStudent, University, User, UserRoleAssignment
from app.schemas import BatchCreate, SchoolCreate, SchoolOut, SchoolUpdate, SchoolUpdateOut, TierChangeOut
from app.services.provisioning import deliver_welcome_link, issue_welcome_token, provisioning_statuses, resend_wait_seconds, revoke_welcome_tokens, unusable_password_hash, user_ids_with_status
from app.services.storage import storage

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("app.admin")


async def ensure_admin(user: User = Depends(get_current_user)):
    if user.role not in {"super_admin", "it_admin", "overseas_admin"}:
        raise HTTPException(403, "Admin role required")
    return user


def _reject_supplied_password(payload: dict, actor: User, route: str, field: str) -> None:
    """ENH-003 / DEC-SCOPE-019: an admin never supplies or knows a credential for an account they
    provision -- the user sets their own via the emailed link. Logged as a WARNING (actor and route
    only, never the value): a caller still sending one is a stale client or a misuse worth seeing."""
    if field in payload:
        logger.warning("provisioning_password_field_rejected", extra={"extra_fields": {"actor_id": str(actor.id), "route": route}})
        raise HTTPException(422, "A password cannot be supplied; the user sets their own via the emailed set-password link")


# Cap on the unfiltered directory list; named so tests can lower it. A `provisioning_status` filter is NOT capped:
# it is the exact set of accounts that still need an admin's action.
USER_LIST_CAP = 500

# The same email shape the registration schemas already use (no whitespace, so a CR/LF header-injection
# attempt cannot pass). The address is the only delivery channel for a credential-setting link, so these
# routes no longer accept arbitrary strings.
EMAIL_PATTERN = re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")


def _valid_email(raw) -> str:
    email = str(raw or "").lower().strip()
    if len(email) > 255 or not EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(422, "A valid email address is required")
    return email


def _fit(value, label: str, limit: int):
    """A value longer than its column is a 422 that names the field, never a database 500 (QA-001).
    Validates only: the value is returned unchanged, so accepted input is stored exactly as before."""
    if value is not None and len(str(value)) > limit:
        raise HTTPException(422, f"{label} must be at most {limit} characters")
    return value


async def _school_out(db: AsyncSession, school: "School") -> "SchoolOut":
    """ENH-009 / DEC-SCOPE-025: the one place that assembles a School's full profile response,
    including the fields that are deliberately computed rather than stored -- student/teacher
    counts, and the Principal/Coordinator/Career Counsellor names, all of which are derived from
    role assignments rather than duplicated onto `School` itself (see the design doc §2).

    A thin, single-record wrapper over `_school_outs_batch()` -- kept as its own function because
    every call site here wants one `SchoolOut`, not a list, but the query logic lives in exactly
    one place (simplification pass, ENH-009)."""
    return (await _school_outs_batch(db, [school]))[0]


async def _school_outs_batch(db: AsyncSession, schools: list["School"]) -> list["SchoolOut"]:
    """Same shape as _school_out(), batched across many schools in O(1) queries instead of
    O(N) -- used by list_schools(), where N is unbounded (final-review finding, ENH-009)."""
    if not schools:
        return []
    ids = [s.id for s in schools]
    str_ids = [str(i) for i in ids]

    student_counts = dict((await db.execute(
        select(SchoolStudent.school_id, func.count()).where(SchoolStudent.school_id.in_(ids)).group_by(SchoolStudent.school_id)
    )).all())

    # Grouped by the *label*, not by a second copy of the JSON-path expression: re-rendering it
    # emits a different bind parameter for the `'school_id'` key, which PostgreSQL then treats as
    # a distinct expression ("column users.profile must appear in the GROUP BY clause").
    school_key = User.profile["school_id"].as_string().label("school_key")
    teacher_rows = (await db.execute(
        select(school_key, func.count()).where(
            User.role == "school_teacher", User.profile["school_id"].as_string().in_(str_ids)
        ).group_by(school_key)
    )).all()
    teacher_counts = {row[0]: row[1] for row in teacher_rows}

    role_rows = (await db.scalars(
        select(User).where(User.role.in_(["school_principal", "school_coordinator"]), User.profile["school_id"].as_string().in_(str_ids))
    )).all()
    principal_by_school: dict[str, str] = {}
    coordinator_by_school: dict[str, str] = {}
    for u in role_rows:
        sid = (u.profile or {}).get("school_id")
        if u.role == "school_principal":
            principal_by_school[sid] = u.full_name
        elif u.role == "school_coordinator":
            coordinator_by_school[sid] = u.full_name

    counsellor_rows = (await db.execute(
        select(SchoolStaffAssignment.school_id, User)
        .join(User, User.id == SchoolStaffAssignment.user_id)
        .where(SchoolStaffAssignment.school_id.in_(ids), SchoolStaffAssignment.role == "career_counselor")
    )).all()
    counsellors_by_school: dict = {}
    for sid, u in counsellor_rows:
        counsellors_by_school.setdefault(sid, []).append(u.full_name)

    results = []
    for school in schools:
        sid_str = str(school.id)
        results.append(SchoolOut(
            id=school.id, name=school.name, city=school.city, state=school.state,
            tier=school.tier, tier_valid_until=school.tier_valid_until,
            school_code=school.school_code, branch=school.branch, address=school.address,
            contact_number=school.contact_number, email=school.email, website=school.website,
            grades_available=school.grades_available, board=school.board,
            partnership_date=school.partnership_date, mou_reference=school.mou_reference,
            edusphere_bdm=school.edusphere_bdm, monthly_visit_schedule=school.monthly_visit_schedule,
            vice_principal_name=school.vice_principal_name,
            student_count=student_counts.get(school.id, 0), teacher_count=teacher_counts.get(sid_str, 0),
            principal_name=principal_by_school.get(sid_str), school_coordinator_name=coordinator_by_school.get(sid_str),
            career_counsellor_names=counsellors_by_school.get(school.id, []),
            created_at=school.created_at,
        ))
    return results


async def _flush_unique_email(db: AsyncSession) -> None:
    """Flush a new account; two simultaneous creates for one email are settled by the unique
    constraint (409 for the loser, never a 500). Rolling back also drops anything created with it."""
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Email already exists") from None


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
        # ENH-003: admin-provisioned accounts whose 72-hour set-password link expired unused.
        "expired_welcome_links": len(await user_ids_with_status(db, user, "link_expired")),
    }


@router.get("/users")
async def users(division: str | None = None, role: str | None = None, provisioning_status: str | None = None, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    if provisioning_status is not None and provisioning_status not in {"pending_setup", "link_expired"}:
        raise HTTPException(422, "provisioning_status must be pending_setup or link_expired")
    stmt = select(User)
    if user.role != "super_admin":
        stmt = stmt.where(User.division == user.division)
    elif division:
        stmt = stmt.where(User.division == division)
    if role:
        stmt = stmt.where(User.role == role)
    if provisioning_status:
        # Resolve the exact id set first; the cap below is skipped for a filtered request so it cannot hide a match.
        stmt = stmt.where(User.id.in_(await user_ids_with_status(db, user, provisioning_status)))
    ordered = stmt.order_by(User.created_at.desc())
    xs = (await db.scalars(ordered if provisioning_status else ordered.limit(USER_LIST_CAP))).all()
    statuses = await provisioning_statuses(db, [x.id for x in xs])
    # ADM-004: "views/edits directory detail records" -- `phone`/`profile` are exposed
    # here so a directory edit form can prefill existing values, not just the flat
    # list ADM-001's activate/deactivate action needed. ENH-003: `provisioning_status` is additive.
    return [
        {
            "id": x.id,
            "name": x.full_name,
            "email": x.email,
            "division": x.division,
            "role": x.role,
            "active": x.active,
            "phone": x.phone,
            "profile": x.profile,
            "provisioning_status": statuses.get(x.id, "active"),
        }
        for x in xs
    ]


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
    from app.models import AuditLog

    division = payload.get("division", user.division)
    role = payload["role"]
    if user.role != "super_admin" and division != user.division:
        raise HTTPException(403, "Cannot create users in another division")
    _reject_supplied_password(payload, user, "/api/v1/admin/users", "password")
    allowed_by_division = {
        "it": {"it_student", "trainer", "placement_team", "hr_team", "it_admin"},
        "overseas": {"overseas_student", "counselor", "university_rep", "agent", "overseas_admin"},
        "global": {"super_admin"},
    }
    if role not in allowed_by_division.get(division, set()):
        raise HTTPException(422, "Role is not valid for the selected division")
    email = _valid_email(payload.get("email"))
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    item = User(
        email=email,
        password_hash=unusable_password_hash(),
        full_name=_fit(payload["full_name"], "Full name", 160),
        role=role,
        division=division,
        phone=payload.get("phone"),
        active=payload.get("active", True),
        email_verified=payload.get("email_verified", False),
        profile=payload.get("profile", {}),
    )
    db.add(item)
    await _flush_unique_email(db)
    issued = await issue_welcome_token(db, user=item, issued_by=user)
    db.add(AuditLog(user_id=user.id, action="user.create", entity_type="user", entity_id=str(item.id), metadata_json={"role": role, "division": division}))
    await db.commit()
    delivery = await deliver_welcome_link(user=item, issued=issued, issued_by=user)
    return {"id": item.id, "email": item.email, "role": item.role, "division": item.division, **delivery}


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
    if "active" in payload and bool(payload["active"]) != item.active:
        # ENH-003 security review: a welcome link mailed to a wrong recipient must not come back to
        # life when the account is (re)activated. Any real change of `active` revokes open welcome
        # links; an admin then Re-sends explicitly. Same transaction and commit as the update below.
        await revoke_welcome_tokens(db, item.id)
        logger.info("welcome_links_revoked_on_active_change", extra={"extra_fields": {"actor_id": str(user.id), "user_id": str(item.id), "active": bool(payload["active"])}})
    for k in ("full_name", "phone", "active", "email_verified", "profile"):
        if k in payload:
            setattr(item, k, payload[k])
    db.add(AuditLog(user_id=user.id, action="user.update", entity_type="user", entity_id=str(item.id), metadata_json={k: v for k, v in payload.items() if k != "password"}))
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/welcome-links", status_code=201)
async def create_welcome_link(user_id: UUID, user: User = Depends(ensure_admin), db: AsyncSession = Depends(get_db)):
    """ENH-003 / DEC-SCOPE-019 Re-send. Only for accounts that never set a password (a pending,
    expired or revoked welcome link), and it only ever mails the account's own address -- so it
    cannot reset an active account. Deliberately not idempotent: each call supersedes the previous
    link; a second call inside the cooldown is refused so the endpoint cannot flood a mailbox."""
    # Lock the row so two concurrent Re-sends serialize and only one welcome token stays open.
    item = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not item:
        raise HTTPException(404, "User not found")
    if user.role != "super_admin" and item.division != user.division:
        raise HTTPException(403, "Cannot manage another division")
    if item.id not in await provisioning_statuses(db, [item.id]):
        raise HTTPException(409, "This account has no pending invitation (its password is already set)")
    if not item.active:
        raise HTTPException(409, "Reactivate this account before re-sending its link")
    wait = await resend_wait_seconds(db, item.id)
    if wait:
        logger.warning("welcome_link_resend_throttled", extra={"extra_fields": {"actor_id": str(user.id), "user_id": str(item.id), "wait_seconds": wait}})
        raise HTTPException(429, f"A link was just sent; wait {wait} seconds before re-sending", headers={"Retry-After": str(wait)})
    issued = await issue_welcome_token(db, user=item, issued_by=user)
    await db.commit()
    logger.info("welcome_link_resent", extra={"extra_fields": {"actor_id": str(user.id), "user_id": str(item.id)}})
    delivery = await deliver_welcome_link(user=item, issued=issued, issued_by=user)
    return {"id": item.id, **delivery}


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
async def create_school(payload: SchoolCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    # SchoolCreate's `extra="forbid"` already rejects a supplied `coordinator_password` at the
    # Pydantic layer, before this function body runs at all -- an explicit
    # _reject_supplied_password() call here would be unreachable dead code (simplification pass,
    # ENH-009). This does lose the WARNING-level `provisioning_password_field_rejected` telemetry
    # that call used to emit; already noted and accepted in DEC-SCOPE-025's addendum.
    email = _valid_email(payload.coordinator_email)
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    if payload.tier and payload.tier not in {"bronze", "silver", "gold", "platinum"}:
        raise HTTPException(422, "tier must be one of bronze, silver, gold, platinum")
    school_code = await unique_student_code(db, School.school_code)
    school = School(
        name=payload.name, city=payload.city, state=payload.state,
        created_by_user_id=user.id, tier=payload.tier, tier_valid_until=payload.tier_valid_until,
        school_code=school_code,
        branch=payload.branch, address=payload.address, contact_number=payload.contact_number,
        email=payload.email, website=payload.website, grades_available=payload.grades_available,
        board=payload.board, partnership_date=payload.partnership_date,
        mou_reference=payload.mou_reference, edusphere_bdm=payload.edusphere_bdm,
        monthly_visit_schedule=payload.monthly_visit_schedule,
        vice_principal_name=payload.vice_principal_name,
    )
    db.add(school)
    await db.flush()
    coordinator = User(
        email=email, password_hash=unusable_password_hash(),
        full_name=_fit(payload.coordinator_full_name, "Coordinator name", 160),
        role="school_coordinator", division="overseas", active=True, email_verified=False,
        profile={"school_id": str(school.id)},
    )
    db.add(coordinator)
    await _flush_unique_email(db)  # a lost race also rolls back the school created above
    issued = await issue_welcome_token(db, user=coordinator, issued_by=user)
    # DATA_MODEL.md §6.12: `UserRoleAssignment` is created eagerly here (not lazily on
    # first login like `auth._sync_role_assignment`) so `created_by_user_id`/`assigned_by_
    # user_id` records the acting Overseas Admin from the moment the account exists,
    # satisfying the provisioning audit trail (RBAC_MATRIX.md §3) without waiting for the
    # Coordinator's first login.
    db.add(UserRoleAssignment(user_id=coordinator.id, division="overseas", role="school_coordinator", is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    db.add(AuditLog(user_id=user.id, action="school.create", entity_type="school", entity_id=str(school.id), metadata_json={"name": school.name, "school_code": school_code}))
    db.add(AuditLog(user_id=user.id, action="school.coordinator_seed", entity_type="user", entity_id=str(coordinator.id), metadata_json={"school_id": str(school.id)}))
    await db.commit()
    delivery = await deliver_welcome_link(user=coordinator, issued=issued, issued_by=user)
    out = await _school_out(db, school)
    return {**out.model_dump(mode="json"), "coordinator_id": coordinator.id, "coordinator_email": coordinator.email, **delivery}


@agents_router.get("/schools")
async def list_schools(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    rows = (await db.scalars(select(School).order_by(School.created_at.desc()))).all()
    return await _school_outs_batch(db, rows)


INVALID_TIER = "tier must be one of bronze, silver, gold, platinum"
NOTIFICATION_TITLE_MAX = 180  # Notification.title is String(180); a school name alone may be 200 (ENH-023 §9)
SCHOOL_ENTITLEMENTS_URL = {"school_coordinator": "/school/coordinator/entitlements", "school_principal": "/school/principal/entitlements"}


def _tier_notices(school_name: str, change: dict) -> tuple[tuple[str, str], tuple[str, str]]:
    """((school title, body), (admin title, body)) for a change that moved the tier (ENH-023 spec §4.4)."""
    from app.api.schools import _tier_name  # noqa: PLC0415

    before, after = _tier_name(change["from_tier"]), _tier_name(change["to_tier"])
    if change["direction"] == "upgrade":
        labels = ", ".join(s["label"] for s in change["gained"])
        school = (f"Your partnership is now {after}", f"{school_name} has moved from {before} to {after}. Newly available: {labels}.")
        admin_body = f"Newly available: {labels}."
    else:
        labels = ", ".join(s["label"] for s in change["lost"])
        school = (f"Your partnership changed from {before} to {after}", f"These services are no longer available for new work: {labels}. Work already started for them can still be completed.")
        admin_body = f"No longer available for new work: {labels}. Work already started for them can still be completed."
    admin_title = f"Tier change recorded: {school_name}, {before} → {after}"
    return (school[0][:NOTIFICATION_TITLE_MAX], school[1]), (admin_title[:NOTIFICATION_TITLE_MAX], admin_body)


async def _notify_tier_change(db: AsyncSession, school_id: UUID, school_name: str, actor_id: UUID, change: dict) -> None:
    """ENH-023 (D5/D9), for a tier change that has ALREADY committed: the school's active Coordinators and Principals, then the
    acting admin, each get an in-app notice plus the email channel. Each recipient is tried and committed alone; a failure is
    logged and swallowed, never undoing or failing the tier change (SCH-007-AC04 pattern, school_skills._notify_after_commit)."""
    from app.api.schools import _notify_parent  # noqa: PLC0415 -- takes any User: in-app row, email attempt, NotificationDelivery

    (school_title, school_body), (admin_title, admin_body) = _tier_notices(school_name, change)
    staff = (
        await db.execute(
            select(User.id, User.role).where(User.role.in_(list(SCHOOL_ENTITLEMENTS_URL)), User.active.is_(True), User.profile["school_id"].as_string() == str(school_id))
        )
    ).all()
    notices = [(user_id, school_title, school_body, SCHOOL_ENTITLEMENTS_URL[role]) for user_id, role in staff]
    notices.append((actor_id, admin_title, admin_body, None))
    for user_id, title, body, action_url in notices:
        try:
            recipient = await db.get(User, user_id, populate_existing=True)
            await _notify_parent(db, recipient, school_name=school_name, title=title, body=body, action_url=action_url)
            await db.commit()
        except Exception as exc:  # noqa: BLE001 -- the tier change has committed; see docstring
            await db.rollback()
            # No exc_info (security review S1): SMTP errors can carry the recipient's address. NotificationDelivery keeps the detail.
            logger.warning("tier_change_notification_failed", extra={"extra_fields": {"school_id": str(school_id), "recipient_id": str(user_id), "error_type": type(exc).__name__}})


@agents_router.patch("/schools/{school_id}", response_model=SchoolUpdateOut)
async def update_school(school_id: UUID, payload: SchoolUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DEC-SCOPE-017 / ENH-009 (DEC-SCOPE-025) -- Overseas Admin updates a School's partnership
    tier and/or profile fields. `name`/`city`/`state`/`coordinator_*` stay out of scope for this
    endpoint -- they were never editable before and no acceptance criterion asks for that.
    ENH-023 (DEC-SCOPE-030): a tier change is recorded as a transition (old -> new, gained/lost), returned as
    `tier_change`, guarded by the optional `expected_tier` precondition (D12), and told to the school after the commit."""
    from app.api.schools import TIER_ORDER, TIER_UPDATE, _tier_name, tier_change_payload  # noqa: PLC0415 -- lazy, like the bridge import below

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    # ENH-023 §8: the row lock queues concurrent tier changes, so each one's `from_tier` is the tier committed before it.
    school = await db.scalar(select(School).where(School.id == school_id).with_for_update())
    if not school:
        raise HTTPException(404, "School not found")
    fields = payload.model_dump(exclude_unset=True)
    for key in ("tier", "expected_tier"):  # D13: "" is no tier, stored and compared as null
        if key in fields:
            fields[key] = fields[key] or None
            if fields[key] is not None and fields[key] not in TIER_ORDER:
                raise HTTPException(422, INVALID_TIER)
    if "expected_tier" in fields and fields.pop("expected_tier") != (school.tier or None):
        # D12, checked under the lock: the tier moved since the caller looked, so what they confirmed is not what would happen.
        raise HTTPException(409, f"This school's tier changed to {_tier_name(school.tier)} since you looked it up. Look it up again before changing the tier.")
    old_tier, old_valid_until = school.tier, school.tier_valid_until
    if "tier" in fields:
        school.tier = fields["tier"]
    if "tier_valid_until" in fields:
        school.tier_valid_until = fields["tier_valid_until"]
    tier_change = None
    if "tier" in fields or "tier_valid_until" in fields:
        tier_change = tier_change_payload(old_tier, school.tier)
        metadata = {
            "tier": school.tier,
            "from_tier": old_tier,
            "to_tier": school.tier,
            "direction": tier_change["direction"],
            "gained": [s["key"] for s in tier_change["gained"]],
            "lost": [s["key"] for s in tier_change["lost"]],
            "tier_valid_until": school.tier_valid_until.isoformat() if school.tier_valid_until else None,
            "previous_tier_valid_until": old_valid_until.isoformat() if old_valid_until else None,
        }
        # clock_timestamp(), not the transaction-start now(): a record created by a transaction that still saw the old tier
        # sorts before this row, so grandfathering (schools._lost_since) treats it as existing work (ENH-023 §8).
        db.add(AuditLog(user_id=user.id, action=TIER_UPDATE, entity_type="school", entity_id=str(school.id), metadata_json=metadata, created_at=func.clock_timestamp()))
    profile_fields = [k for k in fields if k not in {"tier", "tier_valid_until"}]
    for key in profile_fields:
        setattr(school, key, fields[key])
    if profile_fields:
        db.add(AuditLog(user_id=user.id, action="school.profile_update", entity_type="school", entity_id=str(school.id), metadata_json={"changed_fields": sorted(profile_fields)}))
    await db.commit()
    out = await _school_out(db, school)
    if tier_change and tier_change["direction"] != "unchanged":
        await _notify_tier_change(db, school.id, school.name, user.id, tier_change)
    return {**out.model_dump(mode="json"), "tier_change": tier_change}


@agents_router.get("/schools/{school_id}/tier-change-preview", response_model=TierChangeOut)
async def preview_school_tier_change(school_id: UUID, tier: str | None = None, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-023 -- what a tier change would gain or lose, so the admin UI can confirm a downgrade before it happens. Read-only:
    no lock, no write. An empty or absent `tier` means removing the tier."""
    from app.api.schools import TIER_ORDER, tier_change_payload  # noqa: PLC0415 -- lazy, like update_school

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    school = await db.get(School, school_id)
    if not school:
        raise HTTPException(404, "School not found")
    new_tier = tier or None
    if new_tier is not None and new_tier not in TIER_ORDER:
        raise HTTPException(422, INVALID_TIER)
    return tier_change_payload(school.tier, new_tier)


ACADEMIC_YEAR_STATUSES = ["draft", "active", "closed"]


@agents_router.post("/academic-years", status_code=201)
async def create_academic_year(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-001 -- global, admin-only academic-year calendar. Mirrors create_school's
    shape; unlike create_school's duplicate-email check, this inserts directly and lets
    the unique constraint on `label` pick the winner (spec's security review item 1 --
    a pre-check SELECT is a race, not a guard)."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    raw_label = payload.get("label", "")
    if not isinstance(raw_label, str):
        # Review finding fix: `str(payload.get("label", ""))` used to silently coerce a
        # non-string value (e.g. `true`, `123`) into a valid-looking label instead of
        # rejecting it -- inconsistent with this same endpoint's own strictness for
        # `grade_level` elsewhere in this feature.
        raise HTTPException(422, "label must be a string")
    label = raw_label.strip()
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
    # Review finding fix: `db.get(...)` followed by a plain UPDATE is an unlocked
    # read-check-write -- two concurrent PATCH requests on the same row (e.g. one
    # draft->active, one draft->closed) can both read the same starting status and
    # each locally believe its own transition is forward-only, then commit in either
    # order and silently undo one another. `SELECT ... FOR UPDATE` serializes any
    # concurrent PATCH on this same row for the life of this transaction; it does not
    # lock any other row, so unrelated academic years are unaffected.
    year = await db.scalar(select(AcademicYear).where(AcademicYear.id == year_id).with_for_update())
    if not year:
        raise HTTPException(404, "Academic year not found")
    if "status" in payload:
        new_status = payload["status"]
        if new_status not in ACADEMIC_YEAR_STATUSES:
            raise HTTPException(422, f"status must be one of {ACADEMIC_YEAR_STATUSES}")
        if ACADEMIC_YEAR_STATUSES.index(new_status) < ACADEMIC_YEAR_STATUSES.index(year.status):
            raise HTTPException(409, f"cannot move status backward from '{year.status}' to '{new_status}'")
        year.status = new_status
        # Review finding fix: this audit-log write used to happen unconditionally, so a
        # PATCH with no `status` key (a no-op) still wrote a false "status changed"
        # record. Only log/commit when a status change was actually applied.
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
    from app.models import SchoolStaffAssignment

    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    _reject_supplied_password(payload, user, "/api/v1/overseas-admin/school-staff", "password")
    role = payload.get("role")
    if role not in SCHOOL_SERVICE_ROLES:
        raise HTTPException(422, f"role must be one of {sorted(SCHOOL_SERVICE_ROLES)}")
    email = str(payload.get("email", "")).lower().strip()
    full_name = str(payload.get("full_name", "")).strip()
    if not email or not full_name:
        raise HTTPException(422, "email and full_name are required")
    _fit(full_name, "Full name", 160)
    email = _valid_email(email)
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    school_ids = payload.get("school_ids") or []
    schools = (await db.scalars(select(School).where(School.id.in_(school_ids)))).all() if school_ids else []
    if len(schools) != len(set(school_ids)):
        raise HTTPException(422, "One or more school_ids do not exist")

    staff = User(
        email=email,
        password_hash=unusable_password_hash(),
        full_name=full_name,
        role=role,
        division="overseas",
        active=True,
        email_verified=False,
        profile={},
    )
    db.add(staff)
    await _flush_unique_email(db)
    issued = await issue_welcome_token(db, user=staff, issued_by=user)
    db.add(UserRoleAssignment(user_id=staff.id, division="overseas", role=role, is_active=True, assigned_by_user_id=user.id, approval_status="approved"))
    for school in schools:
        db.add(SchoolStaffAssignment(user_id=staff.id, school_id=school.id, role=role, assigned_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.staff_create", entity_type="user", entity_id=str(staff.id), metadata_json={"role": role, "school_ids": [str(s.id) for s in schools]}))
    await db.commit()
    delivery = await deliver_welcome_link(user=staff, issued=issued, issued_by=user)
    return {"id": staff.id, "email": staff.email, "role": staff.role, "school_ids": [str(s.id) for s in schools], **delivery}


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


@agents_router.get("/schools/lookup")
async def lookup_school_by_code(code: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-009 / DEC-SCOPE-025 -- resolves a School's business-facing `school_code` to its full
    profile, for the admin edit panel. Deliberately narrower than the analogous
    `school-students/lookup` endpoint: Counselor has a real reason to look up a School *student*
    (the School->Overseas bridge, DEC-SCOPE-018) but no legitimate reason to see or edit a
    School's own profile."""
    if user.role not in {"overseas_admin", "super_admin"}:
        raise HTTPException(403, "Overseas Admin role required")
    school = await db.scalar(select(School).where(School.school_code == code.strip().upper()))
    if not school:
        raise HTTPException(404, "No school found with that School ID")
    return await _school_out(db, school)


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
    from app.api.schools import _notify_student_parents, require_school_entitlement
    from app.models import ApplicationStatusHistory, SchoolStudent

    if user.role not in {"overseas_admin", "counselor", "super_admin"}:
        raise HTTPException(403, "Overseas Admin or Counselor role required")
    student = await db.get(SchoolStudent, school_student_id)
    if not student:
        raise HTTPException(404, "School student not found")
    # ENH-022 (D4/D9): the school's entitlement applies whoever acts -- a bridged application is Gold's application support.
    await require_school_entitlement(db, user, student.school_id, "application_support")
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
