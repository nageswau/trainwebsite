"""ccrm-009 (DEC-SCOPE-253) -- the reads behind the counselor's student 360: overview, documents, activities and history. Read-only;
the caller has already passed `student_profiles.staff_student` (csc-001 scope or the Overseas Admin).

V1: the page shows ALL the student's applications, current documents and history, each application marked `mine`; every write and
download keeps its own route's rule, so `can_download` mirrors `GET /workflows/overseas/documents/{id}/download` for a counselor.
B3: history = the applications' status history (ccrm-016, staff view) + audit rows about the student + document uploads, reviews and
replacements; field names only, never values."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.application_outcome import label as outcome_label
from app.application_sub_status import label as sub_status_label
from app.document_checklists import STATUS_LABELS as DOCUMENT_STATUS_LABELS
from app.document_checklists import review_status
from app.lead_stages import label as lead_stage_label
from app.models import (
    ApplicationStatusHistory,
    Appointment,
    AuditLog,
    Enquiry,
    OverseasApplication,
    OverseasCourse,
    OverseasStudentCounselor,
    StudentDocument,
    University,
    User,
)  # fmt: skip
from app.services import application_outcomes as outcomes
from app.services.agent_applications import stage_label
from app.services.provisioning import provisioning_statuses

Staff = aliased(User)
TO_REVIEW = ("pending", "uploaded", "under_review")  # ccrm-021 S1: uploaded and waiting for the counselor
HISTORY_LIMIT = 200
DOCUMENT_ACTIONS = {"document.upload": "Uploaded", "document.verify": "Reviewed", "document.replace": "Replaced with a new version"}
ACCOUNT_ACTIONS = {
    "overseas_student_profile.update": "Profile updated",
    "counselor.student_update": "Account details updated",
    "counselor.student_create": "Account created by the counselor",
    "counselor.student_resend": "Set-password link re-sent",
    "overseas.student.counselor_assign": "Counselor assigned",
}


async def _applications(db: AsyncSession, student_id: UUID):
    return (
        await db.execute(
            select(OverseasApplication, University.name, OverseasCourse.title, Staff.full_name)
            .join(University, University.id == OverseasApplication.university_id)
            .outerjoin(OverseasCourse, OverseasCourse.id == OverseasApplication.course_id)
            .outerjoin(Staff, Staff.id == OverseasApplication.counselor_id)
            .where(OverseasApplication.student_id == student_id)
            .order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id)
        )
    ).all()


def _is_open(app: OverseasApplication) -> bool:
    return not outcomes.is_closed(app) and app.status != "enrolled"


async def overview(db: AsyncSession, user: User, student: User) -> dict:
    rows = await _applications(db, student.id)
    events = await outcomes.latest(db, [a.id for a, *_ in rows if a.outcome])
    applications = [
        {
            "id": a.id, "application_code": a.application_code, "university": university, "course": course, "intake": a.intake,
            "status": a.status, "status_label": stage_label(a.status), "sub_status_label": sub_status_label(a.sub_status),
            "outcome_summary": outcomes.summary(a, events.get(a.id)), "next_action": a.next_action, "counselor": counselor,
            "is_agency": a.agent_id is not None, "mine": a.counselor_id == user.id, "open": _is_open(a),
        }
        for a, university, course, counselor in rows
    ]  # fmt: skip
    linked = (
        await db.execute(
            select(User.id, User.full_name).join(OverseasStudentCounselor, OverseasStudentCounselor.counselor_user_id == User.id).where(OverseasStudentCounselor.student_user_id == student.id)
        )
    ).first()
    to_review = await db.scalar(
        select(func.count()).select_from(StudentDocument).where(StudentDocument.student_id == student.id, StudentDocument.archived_at.is_(None), StudentDocument.verification_status.in_(TO_REVIEW))
    )
    setup = (await provisioning_statuses(db, [student.id])).get(student.id)
    return {
        "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code, "email": student.email, "phone": student.phone},
        "account_status": "deactivated" if not student.active else setup or "active",
        "counselor": {"id": linked.id, "full_name": linked.full_name} if linked else None,
        "applications": applications,
        "counts": {"applications": len(applications), "open_applications": sum(a["open"] for a in applications), "documents_to_review": to_review or 0},
        "next_actions": [
            {"application_id": a["id"], "application_code": a["application_code"], "university": a["university"], "next_action": a["next_action"]}
            for a in applications
            if a["open"] and a["next_action"]
        ],
    }


async def documents(db: AsyncSession, user: User, student: User) -> dict:
    rows = (
        await db.execute(
            select(StudentDocument, OverseasApplication.application_code, OverseasApplication.counselor_id, Staff.full_name)
            .outerjoin(OverseasApplication, OverseasApplication.id == StudentDocument.application_id)
            .outerjoin(Staff, Staff.id == StudentDocument.verified_by_id)
            .where(StudentDocument.student_id == student.id, StudentDocument.archived_at.is_(None))  # ccrm-021 S3: current versions
            .order_by(StudentDocument.updated_at.desc(), StudentDocument.id)
        )
    ).all()
    admin = user.role == "overseas_admin"  # staff_student already admitted only the overseas division's admin
    # The download route's counselor rule: the document's application is theirs, or (no application) any of the student's is.
    has_own = admin or bool(await db.scalar(select(OverseasApplication.id).where(OverseasApplication.student_id == student.id, OverseasApplication.counselor_id == user.id).limit(1)))
    return {
        "items": [
            {
                "id": d.id, "document_type": d.document_type, "document_label": d.document_label, "application_code": code,
                "status": d.verification_status, "status_label": DOCUMENT_STATUS_LABELS.get(d.verification_status, d.verification_status),
                "expiry_date": d.expiry_date, "reviewer": reviewer, "reviewed_at": d.reviewed_at, "uploaded_at": d.created_at,
                "can_download": admin or (owner == user.id if d.application_id else has_own),
            }
            for d, code, owner, reviewer in rows
        ]
    }  # fmt: skip


async def activities(db: AsyncSession, user: User, student: User) -> dict:
    appointments = (
        await db.execute(select(Appointment, Staff.full_name).outerjoin(Staff, Staff.id == Appointment.staff_id).where(Appointment.student_id == student.id).order_by(Appointment.scheduled_at.desc()))
    ).all()
    leads = (await db.execute(select(Enquiry, Staff.full_name).outerjoin(Staff, Staff.id == Enquiry.owner_id).where(Enquiry.converted_user_id == student.id).order_by(Enquiry.created_at.desc()))).all()
    return {
        "appointments": [{"id": a.id, "type": a.appointment_type, "scheduled_at": a.scheduled_at, "mode": a.mode, "status": a.status, "staff": staff} for a, staff in appointments],
        # B2: the counselor's lead page opens only the leads they own
        "leads": [
            {
                "id": lead.id, "lead_code": lead.lead_code, "stage": lead.status, "stage_label": lead_stage_label(lead.status), "owner": owner,
                "href": f"/overseas/counselor/leads/{lead.id}" if lead.owner_id == user.id else None,
            }
            for lead, owner in leads
        ],
    }  # fmt: skip


def _status_summary(h: ApplicationStatusHistory) -> str:
    parts = []
    if h.to_status != h.from_status:
        parts.append(f"Stage: {stage_label(h.from_status) + ' → ' if h.from_status else ''}{stage_label(h.to_status)}")
    if h.to_sub_status != h.from_sub_status and h.to_sub_status:
        parts.append(f"Sub-status: {sub_status_label(h.to_sub_status)}")
    if h.outcome:
        parts.append(f"Outcome: {outcome_label(h.outcome)}")
    return " · ".join(parts) or f"Updated at {stage_label(h.to_status)}"


def _audit_summary(log: AuditLog, document_type: str | None) -> str:
    meta = log.metadata_json or {}
    if document_type is not None:
        text = f"{DOCUMENT_ACTIONS[log.action]}: {document_type}"
        status = meta.get("verification_status")
        return f"{text} — {DOCUMENT_STATUS_LABELS.get(review_status(status), status)}" if log.action == "document.verify" and status else text
    fields = meta.get("fields")
    text = ACCOUNT_ACTIONS[log.action]
    return f"{text}: {', '.join(f.replace('_', ' ') for f in fields)}" if fields else text


async def history(db: AsyncSession, student: User) -> dict:
    apps = {a.id: a.application_code for a in (await db.scalars(select(OverseasApplication).where(OverseasApplication.student_id == student.id))).all()}
    statuses = (
        await db.execute(
            select(ApplicationStatusHistory, Staff.full_name)
            .outerjoin(Staff, Staff.id == ApplicationStatusHistory.changed_by_id)
            .where(ApplicationStatusHistory.application_id.in_(list(apps)))
            .order_by(ApplicationStatusHistory.created_at.desc())
            .limit(HISTORY_LIMIT)
        )
    ).all() if apps else []  # fmt: skip
    docs = {str(d.id): d for d in (await db.scalars(select(StudentDocument).where(StudentDocument.student_id == student.id))).all()}  # archived versions too
    account = (AuditLog.entity_type == "user") & (AuditLog.entity_id == str(student.id)) & AuditLog.action.in_(ACCOUNT_ACTIONS)
    document = (AuditLog.entity_type == "student_document") & AuditLog.entity_id.in_(list(docs)) & AuditLog.action.in_(DOCUMENT_ACTIONS)
    logs = (
        await db.execute(
            select(AuditLog, Staff.full_name).outerjoin(Staff, Staff.id == AuditLog.user_id).where(account | document if docs else account).order_by(AuditLog.created_at.desc()).limit(HISTORY_LIMIT)
        )
    ).all()
    items = [
        {
            "at": h.created_at, "kind": "status", "summary": _status_summary(h), "actor": actor, "application_code": apps.get(h.application_id),
            "notes": h.notes, "reason": h.reason,
        }
        for h, actor in statuses
    ]  # fmt: skip
    for log, actor in logs:
        doc = docs.get(log.entity_id) if log.entity_type == "student_document" else None
        items.append(
            {
                "at": log.created_at, "kind": "document" if doc else "audit", "summary": _audit_summary(log, doc.document_type if doc else None), "actor": actor,
                "application_code": apps.get(doc.application_id) if doc else None, "notes": None, "reason": None,
            }
        )  # fmt: skip
    items.sort(key=lambda i: i["at"], reverse=True)
    return {"items": items[:HISTORY_LIMIT]}
