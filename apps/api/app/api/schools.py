"""SCH-003/SCH-001/SCH-002/SCH-004/SCH-005/SCH-006 -- School partner onboarding, role-based
roster/activity access, bulk roster upload, and the three service-delivery modules (career
guidance, psychometric assessment, academic results).

Net-new router. `POST /overseas-admin/schools`/`GET /overseas-admin/schools` (Overseas
Admin creates the School + seed Coordinator, SCH-003) and `POST`/`GET /overseas-admin/
school-staff` (Overseas Admin/Super Admin creates an academic_team/career_counselor/
psychometric_team account and assigns its school portfolio, SCH-004/005/006, DEC-SCOPE-014)
live in `admin.py`'s `agents_router` (`/overseas-admin` namespace) -- this file covers
everything under the `/school` prefix, per `API_CONTRACT.md` §12A.
"""

import csv
import hashlib
import io
import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import _set_auth_cookies
from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    AcademicYear,
    AuditLog,
    Notification,
    NotificationDelivery,
    OverseasApplication,
    School,
    SchoolAcademicResult,
    SchoolAccountInvite,
    SchoolActivity,
    SchoolActivityAttendance,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolParentLink,
    SchoolPsychometricRecord,
    SchoolResultStatusHistory,
    SchoolRosterUploadBatch,
    SchoolRosterUploadRow,
    SchoolStaffAssignment,
    SchoolStudent,
    SchoolTestPrepRecord,
    University,
    User,
    UserRoleAssignment,
    VisaCase,
)
from app.services.integrations import send_notification
from app.services.mailer import send_parent_notification_email, send_school_invite_email

router = APIRouter(prefix="/school", tags=["school"])
SERVICE_DELIVERY_ROLES = {"academic_team", "career_counselor", "psychometric_team"}

SCHOOL_DOMAIN_ROLES = {
    "school_coordinator", "school_principal", "school_teacher", "school_parent",
    "academic_team", "career_counselor", "psychometric_team", "school_partnership_manager",
    "edusphere_school_manager", "overseas_admin", "super_admin",
}

INVITABLE_ROLES = {"school_principal", "school_teacher", "school_parent"}
INVITE_EXPIRY_DAYS = 7
OVERSEAS_APPLICATION_STAGES = ["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]
OFFER_ONWARD_STATUSES = {"offer", "offer_received", "accepted", "visa_documentation", "status_tracking", "enrolled"}
UNTRACKED_SCHOOL_DASHBOARD_KPIS = {
    "digital_portfolios_created": "No confirmed School digital-portfolio model exists yet.",
    "internships": "No confirmed School internship model exists yet.",
}
UNTRACKED_SCHOOL_DASHBOARD_CHARTS = [
    {"key": "skills_training", "label": "Skills training", "note": "No confirmed School soft-skills training model exists yet."},
    {"key": "internships", "label": "Internships", "note": "No confirmed School internship model exists yet."},
    {"key": "student_participation_by_program", "label": "Student participation by program", "note": "No confirmed School program-participation model exists yet."},
]


def _require_coordinator(user: User) -> UUID:
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = user.profile.get("school_id") if user.profile else None
    if not school_id:
        raise HTTPException(403, "This account is not linked to a school")
    return UUID(str(school_id))


async def _create_and_send_invite(db: AsyncSession, *, school: School, role: str, email: str, full_name: str, inviter: User) -> dict:
    """Shared by the Team page (Teacher/Principal/Parent) and the roster's parent_email
    field (Parent only) -- one code path, one email template, for every School invite.
    Real SMTP send via `mailer.send_school_invite_email`; the generic webhook-forwarding
    `send_notification` call stays alongside it for parity with the rest of the platform's
    notification architecture (`NOT-001`), even though the SMTP result is the one that
    actually determines whether the recipient got anything.
    """
    raw = secrets.token_urlsafe(32)
    invite = SchoolAccountInvite(
        school_id=school.id,
        role=role,
        invited_by_user_id=inviter.id,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=email,
        full_name=full_name,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(days=INVITE_EXPIRY_DAYS),
    )
    db.add(invite)
    await db.flush()
    from app.core.config import settings

    accept_url = f"{settings.frontend_url}/school/invite/{raw}/accept"
    webhook_status, webhook_error = await send_notification("email", {"to": email, "template": "school_invite", "role": role, "school_id": str(school.id), "invite_token": raw})
    smtp_status, smtp_error = await send_school_invite_email(
        to_email=email, recipient_name=full_name, role=role, school_name=school.name, accept_url=accept_url,
        coordinator_name=inviter.full_name, coordinator_email=inviter.email, expires_at=invite.expires_at,
    )
    db.add(AuditLog(
        user_id=inviter.id, action="school.invite_create", entity_type="school_account_invite", entity_id=str(invite.id),
        metadata_json={"role": role, "school_id": str(school.id), "webhook_status": webhook_status, "webhook_error": webhook_error, "smtp_status": smtp_status, "smtp_error": smtp_error},
    ))
    response = {"id": invite.id, "role": invite.role, "email": invite.email, "status": invite.status, "expires_at": invite.expires_at, "email_status": smtp_status}
    if settings.environment in ("development", "test"):
        response["development_invite_token"] = raw
    return response


@router.post("/team/invites", status_code=201)
async def create_invite(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _require_coordinator(user)
    role = payload.get("role")
    if role not in INVITABLE_ROLES:
        raise HTTPException(422, f"role must be one of {sorted(INVITABLE_ROLES)}")
    email = str(payload.get("email", "")).lower().strip()
    full_name = str(payload.get("full_name", "")).strip()
    if not email or not full_name:
        raise HTTPException(422, "email and full_name are required")
    if await db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already exists")
    school = await db.get(School, school_id)
    response = await _create_and_send_invite(db, school=school, role=role, email=email, full_name=full_name, inviter=user)
    await db.commit()
    return response


@router.get("/team")
async def list_team(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _require_coordinator(user)
    accounts = (
        await db.scalars(select(User).where(User.role.in_(("school_principal", "school_teacher", "school_parent", "school_coordinator"))))
    ).all()
    accounts = [a for a in accounts if (a.profile or {}).get("school_id") == str(school_id)]
    invites = (
        await db.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.school_id == school_id, SchoolAccountInvite.status == "pending").order_by(SchoolAccountInvite.created_at.desc()))
    ).all()
    return {
        "accounts": [{"id": a.id, "name": a.full_name, "email": a.email, "role": a.role, "active": a.active} for a in accounts],
        "pending_invites": [{"id": i.id, "role": i.role, "email": i.email, "full_name": i.full_name, "expires_at": i.expires_at} for i in invites],
    }


@router.patch("/team/accounts/{user_id}")
async def update_team_account(user_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Coordinator activate/deactivate for their own school's Principal/Teacher/Parent
    accounts (EVID-014 "School Master" §33/§2 -- treated as the same role as
    school_coordinator per direct user confirmation). Deliberately no cascade guard like
    ADM-001-AC02's trainer/batch check: a deactivated Teacher's existing
    assigned_teacher_user_id links are left unchanged (not unsafe by themselves, no
    batch-like scheduling dependency in this domain); the Teacher picker (SchoolStudentsPanel)
    excludes inactive teachers from new assignments instead.
    """
    school_id = _require_coordinator(user)
    if "active" not in payload or not isinstance(payload["active"], bool):
        raise HTTPException(422, "active (boolean) is required")
    target = await db.get(User, user_id)
    if not target:
        raise HTTPException(404, "Account not found")
    # INVITABLE_ROLES doubles as the guard against targeting a Coordinator, self or peer.
    if target.role not in INVITABLE_ROLES:
        raise HTTPException(403, "Can only activate/deactivate Principal, Teacher, or Parent accounts")
    if (target.profile or {}).get("school_id") != str(school_id):
        raise HTTPException(403, "This account is not at your institution")
    target.active = payload["active"]
    db.add(AuditLog(
        user_id=user.id, action="school.team_account_update", entity_type="user", entity_id=str(target.id),
        metadata_json={"school_id": str(school_id), "role": target.role, "active": target.active},
    ))
    await db.commit()
    return {"id": target.id, "active": target.active}


@router.post("/invites/{token}/accept", status_code=201)
async def accept_invite(token: str, payload: dict, response: Response, db: AsyncSession = Depends(get_db)):
    digest = hashlib.sha256(token.encode()).hexdigest()
    invite = await db.scalar(select(SchoolAccountInvite).where(SchoolAccountInvite.token_hash == digest))
    if not invite or invite.status != "pending":
        raise HTTPException(409, "This invite has already been used, expired, or was revoked")
    if invite.expires_at < datetime.now(UTC):
        invite.status = "expired"
        await db.commit()
        raise HTTPException(409, "This invite has already been used, expired, or was revoked")
    password = str(payload.get("password", ""))
    if len(password) < 10:
        raise HTTPException(422, "Password must be at least 10 characters")
    if await db.scalar(select(User).where(User.email == invite.email)):
        raise HTTPException(409, "Email already exists")
    # SCH-003-AC06 / DATA_MODEL.md §6.15: the resulting account's `school_id` is always the
    # invite's own `school_id`, never a value supplied at acceptance time -- closes the
    # same class of IDOR risk `AGT-002`/`UNI-001` already guard against, applied here to
    # account creation.
    account = User(
        email=invite.email,
        password_hash=hash_password(password),
        full_name=invite.full_name,
        role=invite.role,
        division="overseas",
        active=True,
        email_verified=False,
        profile={"school_id": str(invite.school_id)},
    )
    db.add(account)
    await db.flush()
    db.add(UserRoleAssignment(user_id=account.id, division="overseas", role=invite.role, is_active=True, assigned_by_user_id=invite.invited_by_user_id, approval_status="approved"))
    invite.status = "accepted"
    invite.accepted_at = datetime.now(UTC)
    invite.accepted_by_user_id = account.id
    if invite.role == "school_parent":
        # Roster-driven invite (parent_email on one or more SchoolStudent rows): link every
        # student that named this exact email, not just the one that triggered the invite --
        # covers a second child added to the roster while the first invite was still pending.
        pending_students = (
            await db.scalars(select(SchoolStudent).where(SchoolStudent.school_id == invite.school_id, SchoolStudent.pending_parent_email == invite.email))
        ).all()
        for s in pending_students:
            db.add(SchoolParentLink(parent_user_id=account.id, school_student_id=s.id, linked_by_user_id=invite.invited_by_user_id))
            s.pending_parent_email = None
    db.add(AuditLog(user_id=account.id, action="school.invite_accept", entity_type="school_account_invite", entity_id=str(invite.id), metadata_json={"role": invite.role, "school_id": str(invite.school_id)}))
    await db.commit()
    _set_auth_cookies(response, account)
    return {"id": account.id, "email": account.email, "role": account.role}


# ---------------------------------------------------------------------------------------
# SCH-001 -- School Portal role-based access (Principal/Coordinator/Teacher/Parent)
# ---------------------------------------------------------------------------------------

SCHOOL_ROLES = {"school_principal", "school_coordinator", "school_teacher", "school_parent"}


def _own_school_id(user: User) -> UUID:
    if user.role not in SCHOOL_ROLES:
        raise HTTPException(403, "School role required")
    school_id = (user.profile or {}).get("school_id")
    if not school_id:
        raise HTTPException(403, "This account is not linked to a school")
    return UUID(str(school_id))


def _school_dashboard_kpi(key: str, label: str, value: int | None, *, tracked: bool = True, note: str | None = None) -> dict:
    return {"key": key, "label": label, "value": value, "tracked": tracked, "note": note}


def _stage_at_or_after(status: str, stage: str) -> bool:
    if status not in OVERSEAS_APPLICATION_STAGES or stage not in OVERSEAS_APPLICATION_STAGES:
        return False
    return OVERSEAS_APPLICATION_STAGES.index(status) >= OVERSEAS_APPLICATION_STAGES.index(stage)


async def _school_dashboard_payload(db: AsyncSession, school_id: UUID) -> dict:
    """Complete School CRM dashboard aggregation for Coordinator/Principal views.

    Every tracked value is computed from live School-domain rows. Items from
    `School CRM.md` point 1 that still have no confirmed module stay visible as
    `tracked=False` instead of being represented by a fabricated zero.
    """
    students = (await db.scalars(select(SchoolStudent).where(SchoolStudent.school_id == school_id))).all()
    student_ids = [s.id for s in students]
    total_students = len(students)

    grade_counts: dict[str, int] = {}
    grade_level_counts = {str(n): 0 for n in range(8, 13)}
    for student in students:
        label = student.grade_or_class or "Unspecified"
        grade_counts[label] = grade_counts.get(label, 0) + 1
        if student.grade_level is not None and str(student.grade_level) in grade_level_counts:
            grade_level_counts[str(student.grade_level)] += 1
    grade_breakdown = [{"grade": g, "count": c} for g, c in sorted(grade_counts.items())]
    students_with_teacher = sum(1 for s in students if s.assigned_teacher_user_id)

    school_accounts = (await db.scalars(select(User).where(User.role.in_(("school_principal", "school_teacher", "school_parent"))))).all()
    school_accounts = [a for a in school_accounts if (a.profile or {}).get("school_id") == str(school_id)]
    teacher_count = sum(1 for a in school_accounts if a.role == "school_teacher")
    parent_count = sum(1 for a in school_accounts if a.role == "school_parent")
    principal_count = sum(1 for a in school_accounts if a.role == "school_principal")
    pending_invite_count = len((await db.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.school_id == school_id, SchoolAccountInvite.status == "pending"))).all())

    career_rows: list[SchoolCareerRecord] = []
    psych_rows: list[SchoolPsychometricRecord] = []
    published_students: set = set()
    test_prep_rows: list[SchoolTestPrepRecord] = []
    language_rows: list[SchoolLanguageRecord] = []
    applications: list[OverseasApplication] = []
    visas: list[VisaCase] = []
    if student_ids:
        career_rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id.in_(student_ids)))).all()
        psych_rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id.in_(student_ids)))).all()
        published_students = set(
            (await db.scalars(select(SchoolAcademicResult.school_student_id).where(SchoolAcademicResult.school_student_id.in_(student_ids), SchoolAcademicResult.status == "published"))).all()
        )
        test_prep_rows = (await db.scalars(select(SchoolTestPrepRecord).where(SchoolTestPrepRecord.school_student_id.in_(student_ids)))).all()
        language_rows = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id.in_(student_ids)))).all()
        applications = (await db.scalars(select(OverseasApplication).where(OverseasApplication.school_student_id.in_(student_ids)))).all()
        application_ids = [application.id for application in applications]
        if application_ids:
            visas = (await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(application_ids)))).all()

    career_students = {r.school_student_id for r in career_rows}
    guidance_students = {r.school_student_id for r in career_rows if r.record_type == "guidance_session"}
    counselling_students = {r.school_student_id for r in career_rows if r.record_type == "counselling_note"}
    psych_completed_students = {r.school_student_id for r in psych_rows if r.status == "completed"}
    psych_assigned_students = {r.school_student_id for r in psych_rows} - psych_completed_students
    ielts_students = {r.school_student_id for r in test_prep_rows if r.test_type == "ielts"}
    sat_students = {r.school_student_id for r in test_prep_rows if r.test_type == "sat"}
    language_students = {r.school_student_id for r in language_rows}
    global_students = {a.school_student_id for a in applications if a.school_student_id}
    shortlisted_students = {a.school_student_id for a in applications if a.school_student_id and _stage_at_or_after(a.status, "university_selection")}
    admitted_students = {a.school_student_id for a in applications if a.school_student_id and a.status == "enrolled"}
    applications_in_progress = [a for a in applications if a.status not in {"withdrawn", "rejected", "enrolled"}]
    offers = [a for a in applications if a.status in OFFER_ONWARD_STATUSES or a.offer_letter_url]
    application_by_id = {a.id: a for a in applications}
    visa_student_ids = {
        application_by_id[v.application_id].school_student_id
        for v in visas
        if v.application_id in application_by_id and application_by_id[v.application_id].school_student_id
    }

    activities = (await db.scalars(select(SchoolActivity).where(SchoolActivity.school_id == school_id))).all()
    now = datetime.now(UTC)
    upcoming_count = sum(1 for a in activities if a.scheduled_at >= now)
    upcoming = sorted((a for a in activities if a.scheduled_at >= now), key=lambda a: a.scheduled_at)[:10]
    activity_ids = [a.id for a in activities]
    attendance_present = 0
    attendance_total = 0
    if activity_ids:
        attendance_rows = (await db.scalars(select(SchoolActivityAttendance).where(SchoolActivityAttendance.activity_id.in_(activity_ids)))).all()
        attendance_total = len(attendance_rows)
        attendance_present = sum(1 for r in attendance_rows if r.present)

    stage_labels = {
        "enquiry": "Interested in global education",
        "eligibility_evaluation": "Profile evaluation",
        "university_selection": "University shortlisted",
        "offer": "Offers",
        "visa_documentation": "Visa documentation",
        "status_tracking": "Visa/status tracking",
        "enrolled": "Admitted",
    }
    application_pipeline = [
        {"key": stage, "label": stage_labels[stage], "count": sum(1 for a in applications if a.status == stage)}
        for stage in OVERSEAS_APPLICATION_STAGES
    ]
    visa_counts: dict[str, int] = {}
    for visa in visas:
        visa_counts[visa.status] = visa_counts.get(visa.status, 0) + 1
    visa_status = [{"status": status, "count": count} for status, count in sorted(visa_counts.items())]

    return {
        "student_count": total_students,
        "students_with_teacher": students_with_teacher,
        "teacher_count": teacher_count,
        "parent_count": parent_count,
        "principal_count": principal_count,
        "pending_invite_count": pending_invite_count,
        "grade_breakdown": grade_breakdown,
        "career_guidance": {"students_covered": len(career_students), "total_students": total_students},
        "psychometric": {"completed": len(psych_completed_students), "assigned_only": len(psych_assigned_students), "total_students": total_students},
        "results_published": {"students_covered": len(published_students), "total_students": total_students},
        "activities": {"total": len(activities), "upcoming": upcoming_count, "past": len(activities) - upcoming_count},
        "attendance": {"present": attendance_present, "total": attendance_total},
        "upcoming_activities": [{"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at} for a in upcoming],
        "school_crm_kpis": [
            _school_dashboard_kpi("total_students", "Total Students", total_students),
            _school_dashboard_kpi("grade_8", "Grade 8", grade_level_counts["8"]),
            _school_dashboard_kpi("grade_9", "Grade 9", grade_level_counts["9"]),
            _school_dashboard_kpi("grade_10", "Grade 10", grade_level_counts["10"]),
            _school_dashboard_kpi("grade_11", "Grade 11", grade_level_counts["11"]),
            _school_dashboard_kpi("grade_12", "Grade 12", grade_level_counts["12"]),
            _school_dashboard_kpi("career_guidance_completed", "Career Guidance Completed", len(guidance_students)),
            _school_dashboard_kpi("psychometric_tests_completed", "Psychometric Tests Completed", len(psych_completed_students)),
            _school_dashboard_kpi("individual_counselling_completed", "Individual Counselling Completed", len(counselling_students)),
            _school_dashboard_kpi("students_in_global_education_pathway", "Students in Global Education Pathway", len(global_students)),
            _school_dashboard_kpi("ielts_training", "IELTS Training", len(ielts_students)),
            _school_dashboard_kpi("sat_preparation", "SAT Preparation", len(sat_students)),
            _school_dashboard_kpi("foreign_language_students", "Foreign Language Students", len(language_students)),
            _school_dashboard_kpi("digital_portfolios_created", "Digital Portfolios Created", None, tracked=False, note=UNTRACKED_SCHOOL_DASHBOARD_KPIS["digital_portfolios_created"]),
            _school_dashboard_kpi("university_shortlisting", "University Shortlisting", len(shortlisted_students)),
            _school_dashboard_kpi("applications_in_progress", "Applications in Progress", len(applications_in_progress)),
            _school_dashboard_kpi("offers_received", "Offers Received", len(offers)),
            _school_dashboard_kpi("visa_applications", "Visa Applications", len(visa_student_ids)),
            _school_dashboard_kpi("students_admitted", "Students Admitted", len(admitted_students)),
            _school_dashboard_kpi("internships", "Internships", None, tracked=False, note=UNTRACKED_SCHOOL_DASHBOARD_KPIS["internships"]),
        ],
        "completion": [
            {"key": "career_guidance", "label": "Career guidance completion", "value": len(guidance_students), "total": total_students, "tracked": True},
            {"key": "psychometric", "label": "Psychometric completion", "value": len(psych_completed_students), "total": total_students, "tracked": True},
            {"key": "counselling", "label": "Counselling completion", "value": len(counselling_students), "total": total_students, "tracked": True},
            {"key": "ielts", "label": "IELTS training", "value": len(ielts_students), "total": total_students, "tracked": True},
            {"key": "sat", "label": "SAT preparation", "value": len(sat_students), "total": total_students, "tracked": True},
            {"key": "foreign_language", "label": "Foreign language students", "value": len(language_students), "total": total_students, "tracked": True},
        ],
        "global_education": {
            "students": len(global_students),
            "university_shortlisting": len(shortlisted_students),
            "applications_in_progress": len(applications_in_progress),
            "offers_received": len(offers),
            "visa_applications": len(visa_student_ids),
            "students_admitted": len(admitted_students),
        },
        "application_pipeline": application_pipeline,
        "visa_status": visa_status,
        "untracked_charts": UNTRACKED_SCHOOL_DASHBOARD_CHARTS,
    }


def _validate_grade_level(value) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 12):
        raise HTTPException(422, "grade_level must be an integer between 1 and 12")
    return value


async def _current_academic_year_id(db: AsyncSession) -> UUID | None:
    year = await db.scalar(select(AcademicYear).where(AcademicYear.status == "active").order_by(AcademicYear.start_date.desc()))
    return year.id if year else None


def _student_out(s: SchoolStudent) -> dict:
    return {
        "id": s.id,
        "student_code": s.student_code,
        "full_name": s.full_name,
        "date_of_birth": s.date_of_birth,
        "grade_or_class": s.grade_or_class,
        "assigned_teacher_user_id": s.assigned_teacher_user_id,
        "pending_parent_email": s.pending_parent_email,
        "academic_year_id": s.academic_year_id,
        "grade_level": s.grade_level,
    }


# --- SCH-007: Parent Portal notifications ---------------------------------------------------
# Every trigger below writes the in-app `Notification` row first (what the Parent Portal
# lists), then records one `NotificationDelivery` for the email copy (`NOT-001`'s per-channel
# contract). Real SMTP via `mailer.send_parent_notification_email`; when SMTP isn't
# configured the platform's generic webhook channel is tried instead, and whichever
# outcome results is persisted -- a failed or unconfigured send never blocks the write
# that triggered it (SCH-007-AC04).

async def _notify_parent(db: AsyncSession, parent: User, *, school_name: str, title: str, body: str, action_url: str | None) -> None:
    item = Notification(user_id=parent.id, title=title, body=body, read=False, action_url=action_url)
    db.add(item)
    await db.flush()
    status, error = await send_parent_notification_email(to_email=parent.email, recipient_name=parent.full_name, school_name=school_name, title=title, body=body, action_url=action_url)
    if status == "not_configured":
        status, error = await send_notification("email", {"to": parent.email, "title": title, "body": body, "action_url": action_url})
    db.add(NotificationDelivery(notification_id=item.id, channel="email", status=status, error=error, sent_at=datetime.now(UTC) if status == "sent" else None))


async def _notify_student_parents(db: AsyncSession, student: SchoolStudent, *, title: str, body: str, action_url: str | None) -> int:
    """Notify every active Parent linked to this one student (own-child scope, SCH-001-AC03 --
    a Parent linked to a different student at the same school is never included)."""
    parents = (
        await db.scalars(
            select(User).join(SchoolParentLink, SchoolParentLink.parent_user_id == User.id).where(SchoolParentLink.school_student_id == student.id, User.active.is_(True))
        )
    ).all()
    if not parents:
        return 0
    school = await db.get(School, student.school_id)
    for parent in parents:
        await _notify_parent(db, parent, school_name=school.name if school else "your school", title=title, body=body, action_url=action_url)
    return len(parents)


async def _notify_school_parents(db: AsyncSession, school_id: UUID, *, title: str, body: str, action_url: str | None) -> int:
    """Notify every active Parent linked to any student at this school, once each (a parent
    of two children here still gets one notification). Used for school-wide sessions, since
    a `SchoolActivity` has no grade/section targeting in the confirmed model."""
    # Distinct on the id subquery, not on the User row -- Postgres cannot DISTINCT a JSON
    # column (`users.profile`), so `select(User).distinct()` would fail outright.
    parent_ids = (
        select(SchoolParentLink.parent_user_id)
        .join(SchoolStudent, SchoolStudent.id == SchoolParentLink.school_student_id)
        .where(SchoolStudent.school_id == school_id)
        .distinct()
    )
    parents = (await db.scalars(select(User).where(User.id.in_(parent_ids), User.active.is_(True)))).all()
    if not parents:
        return 0
    school = await db.get(School, school_id)
    for parent in parents:
        await _notify_parent(db, parent, school_name=school.name if school else "your school", title=title, body=body, action_url=action_url)
    return len(parents)


async def _parent_email_conflict(db: AsyncSession, *, school_id: UUID, parent_email: str) -> str | None:
    """None means the email is safe to use as a parent_email (either genuinely new, or
    already a school_parent at this same school); a string explains why it can't be --
    an existing account under that email with a different role, or a Parent at a
    different school. Shared by single-add/edit (raises 422) and bulk upload (rejects
    just that row, `SCH-002-AC04`'s never-block-the-batch discipline)."""
    existing_user = await db.scalar(select(User).where(User.email == parent_email))
    if existing_user and (existing_user.role != "school_parent" or (existing_user.profile or {}).get("school_id") != str(school_id)):
        return f"parent_email '{parent_email}' belongs to an existing account that is not a Parent at this school"
    return None


async def _link_or_invite_parent(db: AsyncSession, *, school: School, student: SchoolStudent, parent_email: str, parent_name: str | None, coordinator: User) -> tuple[str, str | None, str | None]:
    """Roster-driven parent linkage (single-add, edit, or bulk upload all call this).
    Returns (status, error, development_invite_token): status is "linked" (an existing
    school_parent account at this school was linked immediately, no email sent), "invited"
    (no account existed yet, a new invite was created and emailed), or "invite_reused"
    (another roster row already triggered a pending invite for this exact email -- reused,
    no duplicate email sent). "rejected" + an error message means the email belongs to an
    account that can't be this student's parent (wrong role, or a Parent at a different
    school) -- never invented. The token is only ever non-None in a development
    environment and only for "invited" -- same dev-only exposure as `/team/invites`.
    """
    parent_email = parent_email.lower().strip()
    conflict = await _parent_email_conflict(db, school_id=school.id, parent_email=parent_email)
    if conflict:
        return "rejected", conflict, None
    existing_user = await db.scalar(select(User).where(User.email == parent_email))
    if existing_user:
        already = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == existing_user.id, SchoolParentLink.school_student_id == student.id))
        if not already:
            db.add(SchoolParentLink(parent_user_id=existing_user.id, school_student_id=student.id, linked_by_user_id=coordinator.id))
        return "linked", None, None
    student.pending_parent_email = parent_email
    pending_invite = await db.scalar(
        select(SchoolAccountInvite).where(SchoolAccountInvite.school_id == school.id, SchoolAccountInvite.email == parent_email, SchoolAccountInvite.role == "school_parent", SchoolAccountInvite.status == "pending")
    )
    if pending_invite:
        return "invite_reused", None, None
    invite_response = await _create_and_send_invite(db, school=school, role="school_parent", email=parent_email, full_name=(parent_name or f"Parent of {student.full_name}").strip(), inviter=coordinator)
    return "invited", None, invite_response.get("development_invite_token")


async def _scoped_students_query(db: AsyncSession, user: User, school_id: UUID):
    """SCH-001-AC02/AC03: every query is filtered server-side by the acting role's own
    scope -- own institution for Principal/Coordinator, own institution + assigned only for
    Teacher, own institution + own child(ren) only for Parent. Never a client-supplied
    filter, and a narrower-than-institution scope is a distinct check from the
    institution check itself, not implied by it (same class as `DEC-SCOPE-013`'s
    portfolio-vs-institution distinction for the School service-delivery roles)."""
    stmt = select(SchoolStudent).where(SchoolStudent.school_id == school_id)
    if user.role == "school_teacher":
        stmt = stmt.where(SchoolStudent.assigned_teacher_user_id == user.id)
    elif user.role == "school_parent":
        linked = select(SchoolParentLink.school_student_id).where(SchoolParentLink.parent_user_id == user.id)
        stmt = stmt.where(SchoolStudent.id.in_(linked))
    return stmt


@router.get("/dashboard")
async def school_dashboard(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"school_coordinator", "school_principal"}:
        raise HTTPException(403, "School Coordinator or Principal role required")
    school_id = _own_school_id(user)
    return await _school_dashboard_payload(db, school_id)


@router.get("/reports")
async def school_reports(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Coordinator/Principal reporting view -- real, computed-from-live-data figures only,
    never a fabricated placeholder (DATA_MODEL.md §8's rule, named for RPT-001 and applied
    here identically). A Draft/Verified academic result's very existence is sensitive to
    these two roles (SCH-006-AC02) -- this report counts Published results only, never
    leaks a draft/verified count even in aggregate.
    """
    if user.role not in {"school_coordinator", "school_principal"}:
        raise HTTPException(403, "School Coordinator or Principal role required")
    school_id = _own_school_id(user)
    return await _school_dashboard_payload(db, school_id)

    students = (await db.scalars(select(SchoolStudent).where(SchoolStudent.school_id == school_id))).all()
    student_ids = [s.id for s in students]
    total_students = len(students)

    grade_counts: dict[str, int] = {}
    for s in students:
        label = s.grade_or_class or "Unspecified"
        grade_counts[label] = grade_counts.get(label, 0) + 1
    grade_breakdown = [{"grade": g, "count": c} for g, c in sorted(grade_counts.items())]
    students_with_teacher = sum(1 for s in students if s.assigned_teacher_user_id)

    school_accounts = (await db.scalars(select(User).where(User.role.in_(("school_principal", "school_teacher", "school_parent"))))).all()
    school_accounts = [a for a in school_accounts if (a.profile or {}).get("school_id") == str(school_id)]
    teacher_count = sum(1 for a in school_accounts if a.role == "school_teacher")
    parent_count = sum(1 for a in school_accounts if a.role == "school_parent")
    principal_count = sum(1 for a in school_accounts if a.role == "school_principal")
    pending_invite_count = len((await db.scalars(select(SchoolAccountInvite).where(SchoolAccountInvite.school_id == school_id, SchoolAccountInvite.status == "pending"))).all())

    career_students: set = set()
    psych_rows: list = []
    published_students: set = set()
    if student_ids:
        career_students = set((await db.scalars(select(SchoolCareerRecord.school_student_id).where(SchoolCareerRecord.school_student_id.in_(student_ids)))).all())
        psych_rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id.in_(student_ids)))).all()
        published_students = set(
            (await db.scalars(select(SchoolAcademicResult.school_student_id).where(SchoolAcademicResult.school_student_id.in_(student_ids), SchoolAcademicResult.status == "published"))).all()
        )
    psych_completed_students = {r.school_student_id for r in psych_rows if r.status == "completed"}
    psych_assigned_students = {r.school_student_id for r in psych_rows} - psych_completed_students

    activities = (await db.scalars(select(SchoolActivity).where(SchoolActivity.school_id == school_id))).all()
    now = datetime.now(UTC)
    upcoming_count = sum(1 for a in activities if a.scheduled_at >= now)
    activity_ids = [a.id for a in activities]
    attendance_present = 0
    attendance_total = 0
    if activity_ids:
        attendance_rows = (await db.scalars(select(SchoolActivityAttendance).where(SchoolActivityAttendance.activity_id.in_(activity_ids)))).all()
        attendance_total = len(attendance_rows)
        attendance_present = sum(1 for r in attendance_rows if r.present)

    return {
        "student_count": total_students,
        "students_with_teacher": students_with_teacher,
        "teacher_count": teacher_count,
        "parent_count": parent_count,
        "principal_count": principal_count,
        "pending_invite_count": pending_invite_count,
        "grade_breakdown": grade_breakdown,
        "career_guidance": {"students_covered": len(career_students), "total_students": total_students},
        "psychometric": {"completed": len(psych_completed_students), "assigned_only": len(psych_assigned_students), "total_students": total_students},
        "results_published": {"students_covered": len(published_students), "total_students": total_students},
        "activities": {"total": len(activities), "upcoming": upcoming_count, "past": len(activities) - upcoming_count},
        "attendance": {"present": attendance_present, "total": attendance_total},
    }


TIER_ORDER = ["bronze", "silver", "gold", "platinum"]
# DEC-SCOPE-017 (2026-09-15): cumulative per the brochure's own image -- each tier lists
# only what it *adds* over the previous one.
TIER_SERVICES: dict[str, list[tuple[str, str]]] = {
    "bronze": [
        ("career_seminar", "Career seminar"),
        ("career_awareness_session", "Student career awareness session"),
        ("parent_orientation", "Parent orientation"),
        ("psychometric_test", "Psychometric test"),
        ("soft_skills", "Soft skills"),
    ],
    "silver": [
        ("individual_counselling", "Individual counselling"),
        ("web_designing", "Web designing"),
    ],
    "gold": [
        ("application_support", "Application support"),
        ("scholarship_assistance", "Scholarship assistance"),
        ("ielts_coaching", "IELTS coaching"),
        ("sat_coaching", "SAT coaching"),
        ("foreign_language_classes", "Foreign language classes"),
        ("digital_portfolio_creation", "Digital portfolio creation"),
    ],
    "platinum": [
        ("dedicated_counselor", "Dedicated EduSphere counselor"),
        ("monthly_campus_visits", "Monthly campus visits"),
        ("internships", "Internships"),
        ("visa_support", "Visa support"),
        ("loan_assistance", "Loan assistance"),
        ("alumni_network", "Alumni network"),
        ("parent_help_desk", "Parent help desk"),
    ],
}


def _cumulative_services(tier: str | None) -> list[tuple[str, str]]:
    if not tier or tier not in TIER_ORDER:
        return []
    services: list[tuple[str, str]] = []
    for t in TIER_ORDER[: TIER_ORDER.index(tier) + 1]:
        services.extend(TIER_SERVICES[t])
    return services


@router.get("/entitlements")
async def school_entitlements(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """DEC-SCOPE-017 -- what this school's partnership tier includes, with a REAL usage
    count wherever a confirmed module produces one, and `used: None` ("not yet tracked")
    for the rest -- never a fabricated 0 or an invented cap (the user explicitly confirmed
    "included = unlimited, count usage" -- no numeric entitlement ever existed in any
    source, School CRM.md's own table was illustrative only).
    """
    if user.role not in {"school_coordinator", "school_principal"}:
        raise HTTPException(403, "School Coordinator or Principal role required")
    school_id = _own_school_id(user)
    school = await db.get(School, school_id)
    services = _cumulative_services(school.tier if school else None)
    if not services:
        return {"tier": school.tier if school else None, "tier_valid_until": school.tier_valid_until if school else None, "services": []}

    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id == school_id))).all()

    async def _activity_count(activity_type: str) -> int:
        return len((await db.scalars(select(SchoolActivity.id).where(SchoolActivity.school_id == school_id, SchoolActivity.activity_type == activity_type))).all())

    usage: dict[str, int | bool | None] = {}
    if student_ids:
        usage["psychometric_test"] = len((await db.scalars(select(SchoolPsychometricRecord.id).where(SchoolPsychometricRecord.school_student_id.in_(student_ids)))).all())
        usage["individual_counselling"] = len(
            (await db.scalars(select(SchoolCareerRecord.id).where(SchoolCareerRecord.school_student_id.in_(student_ids), SchoolCareerRecord.record_type == "counselling_note"))).all()
        )
        usage["ielts_coaching"] = len((await db.scalars(select(SchoolTestPrepRecord.id).where(SchoolTestPrepRecord.school_student_id.in_(student_ids), SchoolTestPrepRecord.test_type == "ielts"))).all())
        usage["sat_coaching"] = len((await db.scalars(select(SchoolTestPrepRecord.id).where(SchoolTestPrepRecord.school_student_id.in_(student_ids), SchoolTestPrepRecord.test_type == "sat"))).all())
        usage["foreign_language_classes"] = len((await db.scalars(select(SchoolLanguageRecord.id).where(SchoolLanguageRecord.school_student_id.in_(student_ids)))).all())
        application_ids = (await db.scalars(select(OverseasApplication.id).where(OverseasApplication.school_student_id.in_(student_ids)))).all()
        usage["application_support"] = len(application_ids)
        usage["visa_support"] = len((await db.scalars(select(VisaCase.id).where(VisaCase.application_id.in_(application_ids)))).all()) if application_ids else 0
    else:
        usage.update({"psychometric_test": 0, "individual_counselling": 0, "ielts_coaching": 0, "sat_coaching": 0, "foreign_language_classes": 0, "application_support": 0, "visa_support": 0})
    usage["career_seminar"] = await _activity_count("career_seminar")
    usage["career_awareness_session"] = await _activity_count("career_awareness_session")
    usage["parent_orientation"] = await _activity_count("parent_orientation")
    usage["monthly_campus_visits"] = await _activity_count("campus_visit")
    usage["dedicated_counselor"] = bool(await db.scalar(select(SchoolStaffAssignment.id).where(SchoolStaffAssignment.school_id == school_id)))

    return {
        "tier": school.tier if school else None,
        "tier_valid_until": school.tier_valid_until if school else None,
        "services": [{"key": key, "label": label, "included": True, "used": usage.get(key)} for key, label in services],
    }


@router.get("/students")
async def list_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    school_id = _own_school_id(user)
    stmt = await _scoped_students_query(db, user, school_id)
    rows = (await db.scalars(stmt.order_by(SchoolStudent.full_name.asc()))).all()
    return [_student_out(s) for s in rows]


@router.get("/students/roster-template")
async def roster_template(user: User = Depends(get_current_user)):
    # Registered before /students/{student_id} below: FastAPI/Starlette match routes in
    # registration order, so a static "roster-template" segment must be declared ahead of
    # a dynamic {student_id} path parameter on the same GET prefix, or every request here
    # would instead 422 trying (and failing) to parse "roster-template" as a UUID.
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(ROSTER_TEMPLATE_HEADERS)
    writer.writerow(["Jane Doe", "2015-04-12", "Grade 5", "", "Jane's Parent", "", "9"])
    return Response(content=buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=school-roster-template.csv"})


@router.get("/academic-years/active")
async def active_academic_year(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """ENH-001. Explicit role allowlist rather than "any authenticated user" -- least
    privilege even though this data isn't sensitive (spec's security review)."""
    if user.role not in SCHOOL_DOMAIN_ROLES:
        raise HTTPException(403, "Not a School-domain role")
    year = await db.scalar(select(AcademicYear).where(AcademicYear.status == "active").order_by(AcademicYear.start_date.desc()))
    if not year:
        return None
    return {"id": year.id, "label": year.label, "start_date": year.start_date, "end_date": year.end_date, "status": year.status}


async def _load_readable_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """One student, checked against the acting School role's own scope (SCH-001-AC02/AC03):
    own institution for every role, plus assigned-only for Teacher and own-child-only for
    Parent -- the same rule as the list, applied to a direct record ID."""
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    if user.role == "school_teacher" and student.assigned_teacher_user_id != user.id:
        raise HTTPException(403, "This student is not assigned to you")
    if user.role == "school_parent":
        linked = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == user.id, SchoolParentLink.school_student_id == student.id))
        if not linked:
            raise HTTPException(403, "This student is not linked to your account")
    return student


@router.get("/students/{student_id}")
async def get_student(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_readable_student(db, user, student_id)
    return _student_out(student)


@router.get("/students/{student_id}/overview")
async def student_overview(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SCH-007 -- one child's complete picture for the Parent Portal (and, by the same scope
    rule, for Teacher/Coordinator/Principal): profile, career guidance status, counselling,
    recommended careers, psychometric status, published results, activities attended,
    upcoming sessions, test prep, foreign language, and (once linked) global education
    progress. Pure read over the already-built tables -- no new tables beyond `SCH-009`'s
    own two and the `DEC-SCOPE-018` bridge fields. Results are Published-only, same as
    everywhere else (SCH-006-AC02). Skills and portfolio remain NOT here: still no
    confirmed module produces that data (`DEC-SCOPE-015` items 79/80) -- omitted rather
    than faked. Overseas-education progress is now included (`DEC-SCOPE-018`, closes item
    77) once an Overseas Admin/Counselor has linked this student to a real application."""
    student = await _load_readable_student(db, user, student_id)
    school = await db.get(School, student.school_id)
    teacher = await db.get(User, student.assigned_teacher_user_id) if student.assigned_teacher_user_id else None
    career_rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == student.id).order_by(SchoolCareerRecord.created_at.desc()))).all()
    psych_rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id == student.id).order_by(SchoolPsychometricRecord.created_at.desc()))).all()
    test_prep_rows = (await db.scalars(select(SchoolTestPrepRecord).where(SchoolTestPrepRecord.school_student_id == student.id).order_by(SchoolTestPrepRecord.created_at.desc()))).all()
    language_rows = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id == student.id).order_by(SchoolLanguageRecord.created_at.desc()))).all()
    result_rows = (
        await db.scalars(
            select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == student.id, SchoolAcademicResult.status == "published").order_by(SchoolAcademicResult.published_at.desc())
        )
    ).all()
    attended_rows = (
        await db.execute(
            select(SchoolActivityAttendance, SchoolActivity)
            .join(SchoolActivity, SchoolActivity.id == SchoolActivityAttendance.activity_id)
            .where(SchoolActivityAttendance.school_student_id == student.id)
            .order_by(SchoolActivity.scheduled_at.desc())
        )
    ).all()
    upcoming_rows = (
        await db.scalars(
            select(SchoolActivity).where(SchoolActivity.school_id == student.school_id, SchoolActivity.scheduled_at >= datetime.now(UTC)).order_by(SchoolActivity.scheduled_at.asc()).limit(10)
        )
    ).all()
    application_rows = (
        await db.execute(
            select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id).where(OverseasApplication.school_student_id == student.id).order_by(OverseasApplication.created_at.desc())
        )
    ).all()
    application_ids = [a.id for a, _u in application_rows]
    visa_by_application = {}
    if application_ids:
        visa_rows = (await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(application_ids)))).all()
        visa_by_application = {v.application_id: v for v in visa_rows}

    def _career(rows: list) -> list[dict]:
        return [{"id": r.id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in rows]

    guidance = [r for r in career_rows if r.record_type == "guidance_session"]
    counselling = [r for r in career_rows if r.record_type == "counselling_note"]
    recommendations = [r for r in career_rows if r.record_type == "recommendation"]
    psych_statuses = {r.status for r in psych_rows}
    psychometric_status = "completed" if "completed" in psych_statuses else ("assigned" if psych_rows else "not_started")
    test_prep_statuses = {r.status for r in test_prep_rows}
    test_prep_status = "completed" if test_prep_statuses and test_prep_statuses == {"completed"} else ("in_progress" if test_prep_rows else "not_started")
    language_statuses = {r.certification_status for r in language_rows}
    language_status = "certified" if "certified" in language_statuses else ("in_progress" if language_rows else "not_started")
    return {
        "student": {**_student_out(student), "school_name": school.name if school else None, "assigned_teacher_name": teacher.full_name if teacher else None},
        "career_guidance": {"status": "completed" if guidance else "not_started", "sessions": _career(guidance)},
        "counselling": {"status": "completed" if counselling else "not_started", "notes": _career(counselling)},
        "recommended_careers": _career(recommendations),
        "psychometric": {"status": psychometric_status, "assessments": [{"id": r.id, "assessment_type": r.assessment_type, "status": r.status, "created_at": r.created_at} for r in psych_rows]},
        "test_prep": {"status": test_prep_status, "records": [_test_prep_out(r) for r in test_prep_rows]},
        "foreign_language": {"status": language_status, "records": [_language_out(r) for r in language_rows]},
        "results": [_result_out(r) for r in result_rows],
        "activities": {
            "attended": [{"activity_id": a.id, "title": a.title, "scheduled_at": a.scheduled_at, "present": att.present} for att, a in attended_rows],
            "upcoming": [{"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at} for a in upcoming_rows],
        },
        "global_education": {
            "status": "linked" if application_rows else "not_started",
            "applications": [
                {"id": a.id, "university_name": u.name, "status": a.status, "visa_status": visa_by_application[a.id].status if a.id in visa_by_application else None}
                for a, u in application_rows
            ],
        },
    }


CAREER_RECORD_TIMELINE = {
    "guidance_session": ("career", "Career guidance session"),
    "counselling_note": ("career", "Counselling note added"),
    "recommendation": ("career", "Career recommendation added"),
}


@router.get("/students/{student_id}/timeline")
async def student_timeline(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """SCH-008 -- narrow Student Journey Timeline: a chronological list of events already
    recorded for one student, built only from already-built modules (`SCH-001`/`004`/`005`/
    `006`/`009`), plus (once linked, `DEC-SCOPE-018`) real Overseas application/visa stage
    changes. No invented University Planning/Soft-Skills steps -- those remain unconfirmed
    (`DEC-SCOPE-015` items 79/80). Same own-scope loader as the overview (`_load_readable_student`), so
    a Parent gets their own child's timeline only, a Teacher their assigned student's, and
    Coordinator/Principal their own institution's -- identical to `SCH-001-AC02`/`AC03`
    and `SCH-007-AC02`. Read-only, no new tables: every event is derived from an existing
    row's own timestamp, nothing synthesized."""
    student = await _load_readable_student(db, user, student_id)
    events: list[dict] = [{
        "date": student.created_at, "category": "profile", "type": "profile_created",
        "title": "Student profile created", "detail": f"Added to {student.grade_or_class}" if student.grade_or_class else None,
    }]
    # Distinct loop-variable names per query (career_r/psych_r/result_r, not a shared `r`) --
    # a reused loop variable across differently-typed queries left MyPy inferring every
    # loop from the first one's type, misreporting real attributes (assessment_type,
    # published_at, ...) as missing from the wrong model. Runtime was already correct;
    # this only fixes static-analysis clarity, found while preparing this branch for CI.
    career_rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == student.id))).all()
    for career_r in career_rows:
        category, title = CAREER_RECORD_TIMELINE[career_r.record_type]
        events.append({"date": career_r.created_at, "category": category, "type": career_r.record_type, "title": title, "detail": career_r.notes})
    psych_rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id == student.id))).all()
    for psych_r in psych_rows:
        events.append({"date": psych_r.created_at, "category": "psychometric", "type": "psychometric_assigned", "title": "Psychometric assessment assigned", "detail": psych_r.assessment_type})
        if psych_r.report_url:
            events.append({"date": psych_r.updated_at, "category": "psychometric", "type": "psychometric_report", "title": "Psychometric report uploaded", "detail": psych_r.assessment_type})
    result_rows = (
        await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == student.id, SchoolAcademicResult.status == "published"))
    ).all()
    for result_r in result_rows:
        events.append({"date": result_r.published_at, "category": "academic", "type": "result_published", "title": "Academic result published", "detail": f"{result_r.term} {result_r.subject} -- {result_r.grade}" if result_r.grade else f"{result_r.term} {result_r.subject}"})
    attended_rows = (
        await db.execute(
            select(SchoolActivityAttendance, SchoolActivity)
            .join(SchoolActivity, SchoolActivity.id == SchoolActivityAttendance.activity_id)
            .where(SchoolActivityAttendance.school_student_id == student.id, SchoolActivityAttendance.present.is_(True))
        )
    ).all()
    for _att, a in attended_rows:
        events.append({"date": a.scheduled_at, "category": "activity", "type": "activity_attended", "title": f"Attended {a.title}", "detail": None})
    test_prep_rows = (await db.scalars(select(SchoolTestPrepRecord).where(SchoolTestPrepRecord.school_student_id == student.id))).all()
    for tp_r in test_prep_rows:
        events.append({"date": tp_r.created_at, "category": "test_prep", "type": "test_prep_started", "title": f"{tp_r.test_type.upper()} preparation started", "detail": tp_r.target_score})
        if tp_r.status == "completed":
            events.append({"date": tp_r.updated_at, "category": "test_prep", "type": "test_prep_completed", "title": f"{tp_r.test_type.upper()} result recorded", "detail": tp_r.actual_score})
    language_rows = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id == student.id))).all()
    for lang_r in language_rows:
        events.append({"date": lang_r.created_at, "category": "foreign_language", "type": "language_started", "title": f"{lang_r.language} classes started", "detail": lang_r.level})
        if lang_r.certification_status == "certified":
            events.append({"date": lang_r.updated_at, "category": "foreign_language", "type": "language_certified", "title": f"{lang_r.language} certification earned", "detail": None})
    application_rows = (
        await db.execute(select(OverseasApplication, University).join(University, University.id == OverseasApplication.university_id).where(OverseasApplication.school_student_id == student.id))
    ).all()
    for app_r, uni_r in application_rows:
        events.append({"date": app_r.created_at, "category": "global_education", "type": "application_linked", "title": f"Overseas application started: {uni_r.name}", "detail": app_r.status})
        visa_r = await db.scalar(select(VisaCase).where(VisaCase.application_id == app_r.id))
        if visa_r:
            events.append({"date": visa_r.updated_at, "category": "global_education", "type": "visa_status", "title": f"Visa status: {visa_r.status}", "detail": uni_r.name})
    events.sort(key=lambda e: e["date"])
    return {"student": {"id": student.id, "full_name": student.full_name}, "events": events}


@router.post("/students", status_code=201)
async def create_student(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    full_name = str(payload.get("full_name", "")).strip()
    if not full_name:
        raise HTTPException(422, "full_name is required")
    # assigned_teacher_user_id (picker) takes precedence over assigned_teacher_email
    # (kept for SCH-002's bulk-upload CSV path, which only ever has an email column).
    assigned_teacher_user_id = None
    teacher_id = payload.get("assigned_teacher_user_id")
    teacher_email = payload.get("assigned_teacher_email")
    if teacher_id:
        teacher = await db.get(User, UUID(str(teacher_id)))
        if not teacher or teacher.role != "school_teacher" or (teacher.profile or {}).get("school_id") != str(school_id):
            raise HTTPException(422, "assigned_teacher_user_id must be an existing Teacher at your own school")
        assigned_teacher_user_id = teacher.id
    elif teacher_email:
        teacher = await db.scalar(select(User).where(User.email == str(teacher_email).lower().strip(), User.role == "school_teacher"))
        if not teacher or (teacher.profile or {}).get("school_id") != str(school_id):
            raise HTTPException(422, "assigned_teacher_email must be an existing Teacher at your own school")
        assigned_teacher_user_id = teacher.id
    dob = payload.get("date_of_birth")
    student = SchoolStudent(
        school_id=school_id,
        student_code=await unique_student_code(db, SchoolStudent.student_code),
        full_name=full_name,
        date_of_birth=date.fromisoformat(dob) if dob else None,
        grade_or_class=payload.get("grade_or_class"),
        grade_level=_validate_grade_level(payload.get("grade_level")),
        academic_year_id=await _current_academic_year_id(db),
        created_by_user_id=user.id,
        assigned_teacher_user_id=assigned_teacher_user_id,
    )
    db.add(student)
    await db.flush()
    parent_status = None
    dev_token = None
    parent_email = payload.get("parent_email")
    if parent_email:
        school = await db.get(School, school_id)
        parent_status, error, dev_token = await _link_or_invite_parent(db, school=school, student=student, parent_email=str(parent_email), parent_name=payload.get("parent_name"), coordinator=user)
        if error:
            raise HTTPException(422, error)
    db.add(AuditLog(user_id=user.id, action="school.student_create", entity_type="school_student", entity_id=str(student.id), metadata_json={"school_id": str(school_id), "parent_status": parent_status}))
    await db.commit()
    out = {**_student_out(student), "parent_status": parent_status}
    if dev_token:
        out["development_invite_token"] = dev_token
    return out


@router.patch("/students/{student_id}")
async def update_student(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if student.school_id != school_id:
        raise HTTPException(403, "This student is at a different institution")
    if "full_name" in payload and payload["full_name"]:
        student.full_name = payload["full_name"]
    if "grade_or_class" in payload:
        student.grade_or_class = payload["grade_or_class"]
    if "grade_level" in payload:
        student.grade_level = _validate_grade_level(payload["grade_level"])
    if "date_of_birth" in payload:
        student.date_of_birth = date.fromisoformat(payload["date_of_birth"]) if payload["date_of_birth"] else None
    if "assigned_teacher_user_id" in payload:
        teacher_id = payload["assigned_teacher_user_id"]
        if teacher_id:
            teacher = await db.get(User, UUID(str(teacher_id)))
            if not teacher or teacher.role != "school_teacher" or (teacher.profile or {}).get("school_id") != str(school_id):
                raise HTTPException(422, "assigned_teacher_user_id must be an existing Teacher at your own school")
            student.assigned_teacher_user_id = teacher.id
        else:
            student.assigned_teacher_user_id = None
    elif "assigned_teacher_email" in payload:
        teacher_email = payload["assigned_teacher_email"]
        if teacher_email:
            teacher = await db.scalar(select(User).where(User.email == str(teacher_email).lower().strip(), User.role == "school_teacher"))
            if not teacher or (teacher.profile or {}).get("school_id") != str(school_id):
                raise HTTPException(422, "assigned_teacher_email must be an existing Teacher at your own school")
            student.assigned_teacher_user_id = teacher.id
        else:
            student.assigned_teacher_user_id = None
    parent_status = None
    dev_token = None
    if "parent_email" in payload and payload["parent_email"]:
        school = await db.get(School, school_id)
        parent_status, error, dev_token = await _link_or_invite_parent(db, school=school, student=student, parent_email=str(payload["parent_email"]), parent_name=payload.get("parent_name"), coordinator=user)
        if error:
            raise HTTPException(422, error)
    db.add(AuditLog(user_id=user.id, action="school.student_update", entity_type="school_student", entity_id=str(student.id), metadata_json={"parent_status": parent_status}))
    await db.commit()
    out = {**_student_out(student), "parent_status": parent_status}
    if dev_token:
        out["development_invite_token"] = dev_token
    return out


@router.post("/students/{student_id}/parents", status_code=201)
async def link_parent(student_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    student = await db.get(SchoolStudent, student_id)
    if not student or student.school_id != school_id:
        raise HTTPException(404, "Student not found")
    parent_email = str(payload.get("parent_email", "")).lower().strip()
    parent = await db.scalar(select(User).where(User.email == parent_email, User.role == "school_parent"))
    if not parent or (parent.profile or {}).get("school_id") != str(school_id):
        raise HTTPException(422, "parent_email must be an existing Parent at your own school")
    existing = await db.scalar(select(SchoolParentLink).where(SchoolParentLink.parent_user_id == parent.id, SchoolParentLink.school_student_id == student.id))
    if existing:
        raise HTTPException(409, "This parent is already linked to this student")
    link = SchoolParentLink(parent_user_id=parent.id, school_student_id=student.id, linked_by_user_id=user.id)
    db.add(link)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.parent_link", entity_type="school_parent_link", entity_id=str(link.id), metadata_json={"student_id": str(student.id), "parent_id": str(parent.id)}))
    await db.commit()
    return {"id": link.id, "parent_user_id": parent.id, "school_student_id": student.id}


@router.get("/activities")
async def list_activities(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    rows = (await db.scalars(select(SchoolActivity).where(SchoolActivity.school_id == school_id).order_by(SchoolActivity.scheduled_at.desc()))).all()
    return [{"id": a.id, "title": a.title, "scheduled_at": a.scheduled_at, "activity_type": a.activity_type} for a in rows]


@router.post("/activities", status_code=201)
async def create_activity(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    title = str(payload.get("title", "")).strip()
    scheduled_at = payload.get("scheduled_at")
    if not title or not scheduled_at:
        raise HTTPException(422, "title and scheduled_at are required")
    activity_type = payload.get("activity_type")
    # DEC-SCOPE-017: optional entitlement-tracking category -- lets an Entitlements-tracked
    # activity (career seminar, parent orientation, campus visit, ...) actually feed
    # `GET /school/entitlements`'s usage counts; free-text activities keep working unset.
    if activity_type and activity_type not in {"career_seminar", "career_awareness_session", "parent_orientation", "campus_visit"}:
        raise HTTPException(422, "activity_type must be one of career_seminar, career_awareness_session, parent_orientation, campus_visit")
    activity = SchoolActivity(school_id=school_id, title=title, scheduled_at=datetime.fromisoformat(scheduled_at), created_by_user_id=user.id, activity_type=activity_type)
    db.add(activity)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.activity_create", entity_type="school_activity", entity_id=str(activity.id), metadata_json={"school_id": str(school_id)}))
    # SCH-007 "Workshop" trigger: every linked Parent at this school hears about a new session.
    await _notify_school_parents(
        db, school_id, title=f"Upcoming session: {activity.title}",
        body=f"{activity.title} is scheduled for {activity.scheduled_at.strftime('%d %b %Y, %H:%M')}.", action_url="/school/parent/dashboard",
    )
    await db.commit()
    return {"id": activity.id, "title": activity.title, "scheduled_at": activity.scheduled_at, "activity_type": activity.activity_type}


@router.post("/activities/{activity_id}/attendance")
async def mark_attendance(activity_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    activity = await db.get(SchoolActivity, activity_id)
    if not activity or activity.school_id != school_id:
        raise HTTPException(404, "Activity not found")
    records = payload.get("records", [])
    if not isinstance(records, list) or not records:
        raise HTTPException(422, "records must be a non-empty list of {student_id, present}")
    student_ids = {UUID(str(r["student_id"])) for r in records}
    own_students = set((await db.scalars(select(SchoolStudent.id).where(SchoolStudent.id.in_(student_ids), SchoolStudent.school_id == school_id))).all())
    if own_students != student_ids:
        raise HTTPException(422, "One or more students are not on your own institution's roster")
    for r in records:
        sid = UUID(str(r["student_id"]))
        existing = await db.scalar(select(SchoolActivityAttendance).where(SchoolActivityAttendance.activity_id == activity.id, SchoolActivityAttendance.school_student_id == sid))
        if existing:
            existing.present = bool(r.get("present", True))
            existing.marked_by_user_id = user.id
        else:
            db.add(SchoolActivityAttendance(activity_id=activity.id, school_student_id=sid, present=bool(r.get("present", True)), marked_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.attendance_mark", entity_type="school_activity", entity_id=str(activity.id), metadata_json={"count": len(records)}))
    await db.commit()
    return {"activity_id": activity.id, "marked": len(records)}


# ---------------------------------------------------------------------------------------
# SCH-002 -- School Coordinator bulk student roster upload (template-download-first)
# ---------------------------------------------------------------------------------------

# API_CONTRACT.md §12A flags the exact template column schema as Contracts-phase detail,
# not fixed by DATA_MODEL.md §6.13 -- resolved here as technical contract design, mapped
# directly from SCH-001's own already-built SchoolStudent creation fields (POST /school/
# students), not an invented field list.
ROSTER_TEMPLATE_HEADERS = ["full_name", "date_of_birth", "grade_or_class", "assigned_teacher_email", "parent_name", "parent_email", "grade_level"]


async def _batch_report(db: AsyncSession, batch: SchoolRosterUploadBatch) -> dict:
    rows = (
        await db.scalars(select(SchoolRosterUploadRow).where(SchoolRosterUploadRow.batch_id == batch.id).order_by(SchoolRosterUploadRow.row_number.asc()))
    ).all()
    return {
        "id": batch.id,
        "status": batch.status,
        "total_rows": batch.total_rows,
        "accepted_count": batch.accepted_count,
        "rejected_count": batch.rejected_count,
        "rows": [{"row_number": r.row_number, "status": r.status, "error_message": r.error_message, "created_student_id": r.created_student_id} for r in rows],
    }


@router.post("/students/bulk-upload", status_code=201)
async def bulk_upload_students(
    file: UploadFile = File(...),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    if not idempotency_key:
        raise HTTPException(422, "Idempotency-Key header is required")
    school_id = _own_school_id(user)

    # A repeat with the same key replays the original batch's result rather than
    # re-processing the file -- API_CONTRACT.md §0.2's idempotency convention, same shape
    # as PAY-001's checkout replay.
    existing_batch = await db.scalar(select(SchoolRosterUploadBatch).where(SchoolRosterUploadBatch.idempotency_key == idempotency_key))
    if existing_batch:
        if existing_batch.school_id != school_id:
            raise HTTPException(403, "This upload batch belongs to a different institution")
        return await _batch_report(db, existing_batch)

    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    rows = list(csv.DictReader(io.StringIO(raw)))

    batch = SchoolRosterUploadBatch(school_id=school_id, uploaded_by_user_id=user.id, idempotency_key=idempotency_key, total_rows=len(rows), status="processing")
    db.add(batch)
    await db.flush()

    school = await db.get(School, school_id)
    accepted = 0
    rejected = 0
    # Hoisted out of the per-row loop below: this is a loop-invariant query (the "current"
    # academic year does not change mid-request), so it's issued once for the whole batch
    # rather than once per accepted row.
    current_year_id = await _current_academic_year_id(db)
    for i, row in enumerate(rows, start=1):
        full_name = (row.get("full_name") or "").strip()
        error = None
        student_dob = None
        assigned_teacher_user_id = None
        parent_email = None
        parent_name = None
        if not full_name:
            error = "full_name is required"
        if not error:
            dob_raw = (row.get("date_of_birth") or "").strip()
            if dob_raw:
                try:
                    student_dob = date.fromisoformat(dob_raw)
                except ValueError:
                    error = f"date_of_birth '{dob_raw}' is not a valid date (expected YYYY-MM-DD)"
        if not error:
            teacher_email = (row.get("assigned_teacher_email") or "").strip().lower()
            if teacher_email:
                teacher = await db.scalar(select(User).where(User.email == teacher_email, User.role == "school_teacher"))
                if not teacher or (teacher.profile or {}).get("school_id") != str(school_id):
                    error = f"assigned_teacher_email '{teacher_email}' is not an existing Teacher at your own school"
                else:
                    assigned_teacher_user_id = teacher.id
        if not error:
            parent_email = (row.get("parent_email") or "").strip().lower() or None
            parent_name = (row.get("parent_name") or "").strip() or None
            if parent_email:
                error = await _parent_email_conflict(db, school_id=school_id, parent_email=parent_email)
        grade_level = None
        if not error:
            raw_grade_level = (row.get("grade_level") or "").strip()
            if raw_grade_level:
                try:
                    grade_level = _validate_grade_level(int(raw_grade_level))
                except (ValueError, HTTPException):
                    error = f"grade_level '{raw_grade_level}' must be an integer between 1 and 12"
        # SCH-002-AC04: a row that fails validation is recorded and skipped -- it never
        # blocks or discards the rows around it.
        if error:
            db.add(SchoolRosterUploadRow(batch_id=batch.id, row_number=i, status="rejected", error_message=error))
            rejected += 1
            continue
        student = SchoolStudent(
            school_id=school_id, student_code=await unique_student_code(db, SchoolStudent.student_code), full_name=full_name, date_of_birth=student_dob,
            grade_or_class=(row.get("grade_or_class") or "").strip() or None,
            created_by_user_id=user.id, assigned_teacher_user_id=assigned_teacher_user_id,
            grade_level=grade_level, academic_year_id=current_year_id,
        )
        db.add(student)
        await db.flush()
        if parent_email:
            # Already validated above (no conflicting account) -- this call only ever
            # links or invites here, it does not reject.
            await _link_or_invite_parent(db, school=school, student=student, parent_email=parent_email, parent_name=parent_name, coordinator=user)
        db.add(SchoolRosterUploadRow(batch_id=batch.id, row_number=i, status="accepted", created_student_id=student.id))
        accepted += 1

    batch.accepted_count = accepted
    batch.rejected_count = rejected
    batch.status = "completed"
    db.add(AuditLog(user_id=user.id, action="school.roster_bulk_upload", entity_type="school_roster_upload_batch", entity_id=str(batch.id), metadata_json={"total": len(rows), "accepted": accepted, "rejected": rejected}))
    await db.commit()
    return await _batch_report(db, batch)


@router.get("/roster-uploads/{batch_id}")
async def get_roster_upload(batch_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "school_coordinator":
        raise HTTPException(403, "School Coordinator role required")
    school_id = _own_school_id(user)
    batch = await db.get(SchoolRosterUploadBatch, batch_id)
    if not batch or batch.school_id != school_id:
        raise HTTPException(404, "Upload batch not found")
    return await _batch_report(db, batch)


# ---------------------------------------------------------------------------------------
# SCH-004/005/006 -- Career Guidance & Counselling, Psychometric Assessment, Academic
# Results. All three specialized roles are scoped to a school portfolio (DEC-SCOPE-013),
# not a single institution.
# ---------------------------------------------------------------------------------------


async def _portfolio_school_ids(db: AsyncSession, user: User) -> set:
    rows = (await db.scalars(select(SchoolStaffAssignment.school_id).where(SchoolStaffAssignment.user_id == user.id))).all()
    return set(rows)


async def _student_in_portfolio(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    student = await db.get(SchoolStudent, student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    portfolio = await _portfolio_school_ids(db, user)
    if student.school_id not in portfolio:
        raise HTTPException(403, "This student is at a school outside your own portfolio")
    return student


async def _readable_students(db: AsyncSession, user: User) -> set:
    """The set of school_student_id values this reading role (Coordinator/Principal/
    Teacher/Parent) may see published/visible service-delivery content for -- reuses the
    exact same scoping as SCH-001's own roster access, since it's the same underlying
    own-institution/assigned/own-child rule (SCH-001-AC02/AC03)."""
    school_id = _own_school_id(user)
    stmt = await _scoped_students_query(db, user, school_id)
    return set((await db.scalars(stmt.with_only_columns(SchoolStudent.id))).all())


@router.get("/portfolio-students")
async def list_portfolio_students(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Shared across the three specialized roles -- their own school portfolio's students,
    with each student's own school name for clarity since a portfolio can span several
    schools (unlike SCH-001's own-institution-only roles)."""
    if user.role not in SERVICE_DELIVERY_ROLES:
        raise HTTPException(403, "Academic Team, Career Counselor, or Psychometric Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    rows = (
        await db.execute(select(SchoolStudent, School).join(School, School.id == SchoolStudent.school_id).where(SchoolStudent.school_id.in_(portfolio)).order_by(SchoolStudent.full_name.asc()))
    ).all()
    return [{"id": s.id, "full_name": s.full_name, "school_id": s.school_id, "school_name": sc.name} for s, sc in rows]


# --- SCH-004: Career Guidance & Counselling ---------------------------------------------

@router.post("/career-counselor/records", status_code=201)
async def create_career_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    record_type = payload.get("record_type")
    if record_type not in {"guidance_session", "counselling_note", "recommendation"}:
        raise HTTPException(422, "record_type must be one of guidance_session, counselling_note, recommendation")
    notes = str(payload.get("notes", "")).strip()
    if not notes:
        raise HTTPException(422, "notes is required")
    record = SchoolCareerRecord(school_student_id=student.id, career_counselor_user_id=user.id, record_type=record_type, notes=notes)
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.career_record_create", entity_type="school_career_record", entity_id=str(record.id), metadata_json={"record_type": record_type}))
    # SCH-007 "Counselling" trigger (guidance session / counselling note / recommendation).
    label = {"guidance_session": "Career guidance session recorded", "counselling_note": "Counselling note added", "recommendation": "Career recommendation added"}[record_type]
    await _notify_student_parents(db, student, title=f"{label} for {student.full_name}", body=f"A Career Counselor has added a new {record_type.replace('_', ' ')} to {student.full_name}'s career profile.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return {"id": record.id, "school_student_id": record.school_student_id, "record_type": record.record_type, "notes": record.notes, "created_at": record.created_at}


@router.get("/career-counselor/records")
async def list_career_counselor_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "career_counselor":
        raise HTTPException(403, "Career Counselor role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id.in_(student_ids)).order_by(SchoolCareerRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in rows]


@router.get("/career-records")
async def list_readable_career_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Read-only for School Coordinator/Principal/Teacher/Parent, own scope -- no
    Draft/Published gate for this content, unlike results (visible as soon as created)."""
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id.in_(readable)).order_by(SchoolCareerRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in rows]


# --- SCH-005: Psychometric Assessment ----------------------------------------------------

@router.post("/psychometric-team/records", status_code=201)
async def create_psychometric_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "psychometric_team":
        raise HTTPException(403, "Psychometric Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    assessment_type = str(payload.get("assessment_type", "")).strip()
    if not assessment_type:
        raise HTTPException(422, "assessment_type is required")
    record = SchoolPsychometricRecord(
        school_student_id=student.id, psychometric_team_user_id=user.id, assessment_type=assessment_type,
        report_url=payload.get("report_url"), status="completed" if payload.get("report_url") else "assigned",
    )
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.psychometric_record_create", entity_type="school_psychometric_record", entity_id=str(record.id), metadata_json={"assessment_type": assessment_type}))
    # SCH-007 "Assessment" trigger: assigned (or completed at once, when a report came with it).
    if record.status == "completed":
        await _notify_student_parents(db, student, title=f"Psychometric report ready for {student.full_name}", body=f"The {assessment_type} report for {student.full_name} is now available.", action_url=f"/school/parent/children/{student.id}")
    else:
        await _notify_student_parents(db, student, title=f"Psychometric assessment assigned to {student.full_name}", body=f"{student.full_name} has been assigned a {assessment_type}.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return {"id": record.id, "school_student_id": record.school_student_id, "assessment_type": record.assessment_type, "report_url": record.report_url, "status": record.status, "created_at": record.created_at}


@router.patch("/psychometric-team/records/{record_id}")
async def update_psychometric_record(record_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "psychometric_team":
        raise HTTPException(403, "Psychometric Team role required")
    record = await db.get(SchoolPsychometricRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    await _student_in_portfolio(db, user, record.school_student_id)
    became_completed = False
    if "report_url" in payload:
        record.report_url = payload["report_url"]
        if payload["report_url"] and record.status != "completed":
            record.status = "completed"
            became_completed = True
    db.add(AuditLog(user_id=user.id, action="school.psychometric_record_update", entity_type="school_psychometric_record", entity_id=str(record.id), metadata_json={}))
    if became_completed:
        student = await db.get(SchoolStudent, record.school_student_id)
        if student is None:
            raise HTTPException(404, "Student not found")
        await _notify_student_parents(db, student, title=f"Psychometric report ready for {student.full_name}", body=f"The {record.assessment_type} report for {student.full_name} is now available.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return {"id": record.id, "school_student_id": record.school_student_id, "assessment_type": record.assessment_type, "report_url": record.report_url, "status": record.status}


@router.get("/psychometric-team/records")
async def list_psychometric_team_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "psychometric_team":
        raise HTTPException(403, "Psychometric Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id.in_(student_ids)).order_by(SchoolPsychometricRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "assessment_type": r.assessment_type, "report_url": r.report_url, "status": r.status, "created_at": r.created_at} for r in rows]


@router.get("/psychometric-records")
async def list_readable_psychometric_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id.in_(readable)).order_by(SchoolPsychometricRecord.created_at.desc()))).all()
    return [{"id": r.id, "school_student_id": r.school_student_id, "assessment_type": r.assessment_type, "status": r.status, "created_at": r.created_at} for r in rows]


# --- SCH-009: Test Preparation (IELTS/SAT) -----------------------------------------------
# Resolved 2026-09-15 (`DEC-SCOPE-018`, closes `DEC-SCOPE-015` item 78) -- delivered by the
# existing `academic_team` role, same "no Draft/Published gate" shape as SCH-004/005, not
# SCH-006's formal-results gate.

def _test_prep_out(r: SchoolTestPrepRecord) -> dict:
    return {"id": r.id, "school_student_id": r.school_student_id, "test_type": r.test_type, "mock_scores": r.mock_scores, "target_score": r.target_score, "actual_score": r.actual_score, "status": r.status, "created_at": r.created_at}


@router.post("/academic-team/test-prep-records", status_code=201)
async def create_test_prep_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    test_type = payload.get("test_type")
    if test_type not in {"ielts", "sat"}:
        raise HTTPException(422, "test_type must be one of ielts, sat")
    record = SchoolTestPrepRecord(school_student_id=student.id, academic_team_user_id=user.id, test_type=test_type, target_score=payload.get("target_score"))
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.test_prep_record_create", entity_type="school_test_prep_record", entity_id=str(record.id), metadata_json={"test_type": test_type}))
    await _notify_student_parents(db, student, title=f"{test_type.upper()} preparation started for {student.full_name}", body=f"{student.full_name} has started {test_type.upper()} preparation.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return _test_prep_out(record)


@router.patch("/academic-team/test-prep-records/{record_id}")
async def update_test_prep_record(record_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    record = await db.get(SchoolTestPrepRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    await _student_in_portfolio(db, user, record.school_student_id)
    became_completed = False
    if "mock_scores" in payload:
        record.mock_scores = payload["mock_scores"] or []
    if "actual_score" in payload:
        record.actual_score = payload["actual_score"]
        if payload["actual_score"] and record.status != "completed":
            record.status = "completed"
            became_completed = True
    db.add(AuditLog(user_id=user.id, action="school.test_prep_record_update", entity_type="school_test_prep_record", entity_id=str(record.id), metadata_json={}))
    if became_completed:
        student = await db.get(SchoolStudent, record.school_student_id)
        if student is None:
            raise HTTPException(404, "Student not found")
        await _notify_student_parents(db, student, title=f"{record.test_type.upper()} result recorded for {student.full_name}", body=f"{student.full_name}'s {record.test_type.upper()} result is now available.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return _test_prep_out(record)


@router.get("/academic-team/test-prep-records")
async def list_academic_team_test_prep_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolTestPrepRecord).where(SchoolTestPrepRecord.school_student_id.in_(student_ids)).order_by(SchoolTestPrepRecord.created_at.desc()))).all()
    return [_test_prep_out(r) for r in rows]


@router.get("/test-prep-records")
async def list_readable_test_prep_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (await db.scalars(select(SchoolTestPrepRecord).where(SchoolTestPrepRecord.school_student_id.in_(readable)).order_by(SchoolTestPrepRecord.created_at.desc()))).all()
    return [_test_prep_out(r) for r in rows]


# --- SCH-009: Foreign Language Classes ----------------------------------------------------

def _language_out(r: SchoolLanguageRecord) -> dict:
    return {"id": r.id, "school_student_id": r.school_student_id, "language": r.language, "level": r.level, "classes_attended": r.classes_attended, "assessment_score": r.assessment_score, "certification_status": r.certification_status, "created_at": r.created_at}


@router.post("/academic-team/language-records", status_code=201)
async def create_language_record(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    language = str(payload.get("language", "")).strip()
    if not language:
        raise HTTPException(422, "language is required")
    record = SchoolLanguageRecord(school_student_id=student.id, academic_team_user_id=user.id, language=language, level=payload.get("level"))
    db.add(record)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.language_record_create", entity_type="school_language_record", entity_id=str(record.id), metadata_json={"language": language}))
    await _notify_student_parents(db, student, title=f"{language} classes started for {student.full_name}", body=f"{student.full_name} has started {language} classes.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return _language_out(record)


@router.patch("/academic-team/language-records/{record_id}")
async def update_language_record(record_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    record = await db.get(SchoolLanguageRecord, record_id)
    if not record:
        raise HTTPException(404, "Record not found")
    await _student_in_portfolio(db, user, record.school_student_id)
    became_certified = False
    if "classes_attended" in payload:
        record.classes_attended = int(payload["classes_attended"])
    if "assessment_score" in payload:
        record.assessment_score = payload["assessment_score"]
    if "certification_status" in payload:
        if payload["certification_status"] not in {"not_started", "in_progress", "certified"}:
            raise HTTPException(422, "certification_status must be one of not_started, in_progress, certified")
        if payload["certification_status"] == "certified" and record.certification_status != "certified":
            became_certified = True
        record.certification_status = payload["certification_status"]
    db.add(AuditLog(user_id=user.id, action="school.language_record_update", entity_type="school_language_record", entity_id=str(record.id), metadata_json={}))
    if became_certified:
        student = await db.get(SchoolStudent, record.school_student_id)
        if student is None:
            raise HTTPException(404, "Student not found")
        await _notify_student_parents(db, student, title=f"{record.language} certification earned by {student.full_name}", body=f"{student.full_name} has been certified in {record.language}.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return _language_out(record)


@router.get("/academic-team/language-records")
async def list_academic_team_language_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id.in_(student_ids)).order_by(SchoolLanguageRecord.created_at.desc()))).all()
    return [_language_out(r) for r in rows]


@router.get("/language-records")
async def list_readable_language_records(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id.in_(readable)).order_by(SchoolLanguageRecord.created_at.desc()))).all()
    return [_language_out(r) for r in rows]


# --- SCH-006: Academic Results (Draft -> Verified -> Published) -------------------------

def _result_out(r: SchoolAcademicResult) -> dict:
    percentage = round(float(r.marks_obtained) / float(r.max_marks) * 100, 2) if float(r.max_marks) else None
    return {
        "id": r.id, "school_student_id": r.school_student_id, "academic_year": r.academic_year, "term": r.term,
        "subject": r.subject, "max_marks": float(r.max_marks), "marks_obtained": float(r.marks_obtained),
        "percentage": percentage, "grade": r.grade, "status": r.status,
        "uploaded_by_user_id": r.uploaded_by_user_id, "verified_by_user_id": r.verified_by_user_id,
        "published_by_user_id": r.published_by_user_id,
    }


@router.post("/academic-team/results", status_code=201)
async def create_academic_result(payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    student_id = payload.get("school_student_id")
    if not student_id:
        raise HTTPException(422, "school_student_id is required")
    student = await _student_in_portfolio(db, user, UUID(str(student_id)))
    try:
        max_marks = float(payload.get("max_marks"))
        marks_obtained = float(payload.get("marks_obtained"))
    except (TypeError, ValueError):
        raise HTTPException(422, "max_marks and marks_obtained must be numbers")
    subject = str(payload.get("subject", "")).strip()
    academic_year = str(payload.get("academic_year", "")).strip()
    term = str(payload.get("term", "")).strip()
    if not subject or not academic_year or not term:
        raise HTTPException(422, "academic_year, term, and subject are required")
    result = SchoolAcademicResult(
        school_student_id=student.id, academic_year=academic_year, term=term, subject=subject,
        max_marks=max_marks, marks_obtained=marks_obtained, grade=payload.get("grade"),
        status="draft", uploaded_by_user_id=user.id,
    )
    db.add(result)
    await db.flush()
    db.add(SchoolResultStatusHistory(result_id=result.id, from_status="none", to_status="draft", changed_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action="school.result_create", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={"subject": subject}))
    await db.commit()
    return _result_out(result)


@router.patch("/academic-team/results/{result_id}")
async def update_academic_result(result_id: UUID, payload: dict, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    result = await db.get(SchoolAcademicResult, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    await _student_in_portfolio(db, user, result.school_student_id)
    if result.status != "draft":
        raise HTTPException(409, "Only a Draft result can be edited")
    for field in ("subject", "academic_year", "term", "grade"):
        if field in payload:
            setattr(result, field, payload[field])
    for field in ("max_marks", "marks_obtained"):
        if field in payload:
            setattr(result, field, float(payload[field]))
    db.add(AuditLog(user_id=user.id, action="school.result_update", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={}))
    await db.commit()
    return _result_out(result)


async def _advance_result(result_id: UUID, target: str, user: User, db: AsyncSession) -> SchoolAcademicResult:
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    result = await db.get(SchoolAcademicResult, result_id)
    if not result:
        raise HTTPException(404, "Result not found")
    await _student_in_portfolio(db, user, result.school_student_id)
    expected_from = "draft" if target == "verified" else "verified"
    if result.status != expected_from:
        raise HTTPException(409, f"A result must be {expected_from} before it can be moved to {target} -- no skip-stage transition")
    # DEC-ROLE-007: the uploader may never also verify or publish their own entry.
    if result.uploaded_by_user_id == user.id:
        raise HTTPException(403, "A different Academic Team member must perform this step -- you cannot verify or publish your own upload")
    from_status = result.status
    result.status = target
    if target == "verified":
        result.verified_by_user_id = user.id
        result.verified_at = datetime.now(UTC)
    else:
        result.published_by_user_id = user.id
        result.published_at = datetime.now(UTC)
    db.add(SchoolResultStatusHistory(result_id=result.id, from_status=from_status, to_status=target, changed_by_user_id=user.id))
    db.add(AuditLog(user_id=user.id, action=f"school.result_{target}", entity_type="school_academic_result", entity_id=str(result.id), metadata_json={}))
    if target == "published":
        # SCH-007: only the Published transition reaches a Parent -- a Draft/Verified step
        # never does, so the gate's existence is not leaked through a notification either.
        student = await db.get(SchoolStudent, result.school_student_id)
        if student is None:
            raise HTTPException(404, "Student not found")
        await _notify_student_parents(db, student, title=f"{result.term} {result.subject} result published for {student.full_name}", body=f"{student.full_name}'s {result.academic_year} {result.term} result for {result.subject} is now available.", action_url=f"/school/parent/children/{student.id}")
    await db.commit()
    return result


@router.post("/academic-team/results/{result_id}/verify")
async def verify_academic_result(result_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await _advance_result(result_id, "verified", user, db)
    return _result_out(result)


@router.post("/academic-team/results/{result_id}/publish")
async def publish_academic_result(result_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await _advance_result(result_id, "published", user, db)
    return _result_out(result)


@router.get("/academic-team/results")
async def list_academic_team_results(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role != "academic_team":
        raise HTTPException(403, "Academic Team role required")
    portfolio = await _portfolio_school_ids(db, user)
    if not portfolio:
        return []
    student_ids = (await db.scalars(select(SchoolStudent.id).where(SchoolStudent.school_id.in_(portfolio)))).all()
    rows = (await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id.in_(student_ids)).order_by(SchoolAcademicResult.created_at.desc()))).all()
    return [_result_out(r) for r in rows]


@router.get("/results")
async def list_readable_results(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Read-only for School Coordinator/Principal/Teacher/Parent, own scope -- filtered to
    status='published' only. A Draft/Verified result is never returned, even indirectly
    (SCH-006-AC02)."""
    if user.role not in {"school_coordinator", "school_principal", "school_teacher", "school_parent"}:
        raise HTTPException(403, "School role required")
    readable = await _readable_students(db, user)
    if not readable:
        return []
    rows = (
        await db.scalars(
            select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id.in_(readable), SchoolAcademicResult.status == "published").order_by(SchoolAcademicResult.published_at.desc())
        )
    ).all()
    return [_result_out(r) for r in rows]
