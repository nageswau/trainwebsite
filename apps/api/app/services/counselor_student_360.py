"""ccrm-009 (DEC-SCOPE-253) -- the reads behind the counselor's student 360: overview, documents, activities and history. Read-only;
the caller has already passed `student_profiles.staff_student` (csc-001 scope or the Overseas Admin).

V1: the page shows ALL the student's applications, current documents and history, each application marked `mine`; every write and
download keeps its own route's rule, so `can_download` mirrors `GET /workflows/overseas/documents/{id}/download` for a counselor.
B3: history = the applications' status history (ccrm-016, staff view) + audit rows about the student + document uploads, reviews and
replacements; field names only, never values.
ccrm-039 (DEC-SCOPE-275): finance = the student's fees and payments, each application's university deposit and the refunds; read-only."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app import student_journey as journey
from app.application_outcome import label as outcome_label
from app.application_sub_status import label as sub_status_label
from app.document_checklists import STATUS_LABELS as DOCUMENT_STATUS_LABELS
from app.document_checklists import review_status
from app.lead_stages import label as lead_stage_label
from app.models import (
    ApplicationDeposit,
    ApplicationDepositRecord,
    ApplicationStatusHistory,
    Appointment,
    AuditLog,
    Enquiry,
    Invoice,
    OverseasApplication,
    OverseasCourse,
    OverseasStudentCounselor,
    Payment,
    Receipt,
    StudentDocument,
    University,
    User,
)  # fmt: skip
from app.services import agent_deposits
from app.services import application_outcomes as outcomes
from app.services import overseas_consents, student_archive
from app.services.agent_applications import stage_label
from app.services.application_deposit_records import STATUS_LABELS as DEPOSIT_RECORD_LABELS
from app.services.application_offers import money
from app.services.counselor_students import ASSIGNED as COUNSELOR_ASSIGNED
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
    COUNSELOR_ASSIGNED: "Counselor assigned",
    student_archive.ARCHIVED: "Archived",  # ccrm-040 (DEC-SCOPE-276 AR4)
    student_archive.RESTORED: "Restored",
    overseas_consents.ACCEPTED: "Consent given",
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


async def _journey(db: AsyncSession, student: User, rows: list, linked) -> dict:
    """ccrm-017 (DEC-SCOPE-258): the derived journey stage. J4: engaged = a csc-001 counselor link or an appointment still on."""
    engaged = linked is not None or bool(await db.scalar(select(Appointment.id).where(Appointment.student_id == student.id, Appointment.status.not_in(("cancelled", "no_show"))).limit(1)))
    university = {a.id: name for a, name, *_ in rows}
    stage, best, note = journey.derive([a for a, *_ in rows], engaged=engaged)
    return {
        "stage": stage, "label": journey.LABELS[stage], "steps": journey.steps(stage), "note": note,
        "application": {"id": best.id, "application_code": best.application_code, "university": university[best.id]} if best else None,
    }  # fmt: skip


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
    archive = await student_archive.read(db, student.id)
    return {
        "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code, "email": student.email, "phone": student.phone},
        "account_status": "deactivated" if not student.active else setup or "active",
        "counselor": {"id": linked.id, "full_name": linked.full_name} if linked else None,
        "journey": await _journey(db, student, rows, linked),
        "applications": applications,
        "counts": {"applications": len(applications), "open_applications": sum(a["open"] for a in applications), "documents_to_review": to_review or 0},
        "next_actions": [
            {"application_id": a["id"], "application_code": a["application_code"], "university": a["university"], "next_action": a["next_action"]}
            for a in applications
            if a["open"] and a["next_action"]
        ],
        # ccrm-040 (DEC-SCOPE-276): the archive banner, what the reader may do, and the student's consents (CN4)
        "archive": archive,
        "permissions": await student_archive.permissions(db, user, student, archive is not None),
        "consents": overseas_consents.staff_view(await overseas_consents.status(db, student.id)),
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
    # The download route's counselor rule: the document's application is theirs, or (no application, ccrm-045) the student is in their
    # caseload -- which staff_student has already checked.
    return {
        "items": [
            {
                "id": d.id, "document_type": d.document_type, "document_label": d.document_label, "application_code": code,
                "status": d.verification_status, "status_label": DOCUMENT_STATUS_LABELS.get(d.verification_status, d.verification_status),
                "expiry_date": d.expiry_date, "reviewer": reviewer, "reviewed_at": d.reviewed_at, "uploaded_at": d.created_at,
                "can_download": admin or not d.application_id or owner == user.id,
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
                "application_code": apps.get(doc.application_id) if doc else None, "notes": None,
                # ccrm-033: a counselor reassignment's reason, ccrm-040: an archive's (staff only: this History is the counselor's and the admin's)
                "reason": (log.metadata_json or {}).get("reason") if log.action in (COUNSELOR_ASSIGNED, student_archive.ARCHIVED) else None,
            }
        )  # fmt: skip
    items.sort(key=lambda i: i["at"], reverse=True)
    return {"items": items[:HISTORY_LIMIT]}


PAYMENT_LABELS = {"pending": "Pending", "overdue": "Overdue", "paid": "Paid", "succeeded": "Paid", "failed": "Failed", "refunded": "Refunded", "cancelled": "Cancelled"}
AGENCY_DEPOSIT_LABELS = {"not_required": "Not required", "pending": "Pending", "paid": "Paid via EduSphere", "remitted": "Remitted to the university", "refunded": "Refunded"}


def _humanize(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _payment_description(p: Payment) -> str:
    text = _humanize(p.reference_type)
    return f"{text} (instalment {p.installment_no})" if p.installment_no else text


async def finance(db: AsyncSession, user: User, student: User) -> dict:
    """ccrm-039 (DEC-SCOPE-275). F5: a download is offered only where its route allows the reader -- the invoice/receipt route takes the
    payer and the division's admin; a deposit receipt is a student document (the documents tab's rule). F7: an agency's deposit payment
    is the agency's and is shown on the deposit. Never a `file_url`."""
    admin = user.role == "overseas_admin"  # staff_student already admitted only the overseas division's admin
    payments = (
        await db.execute(
            select(Payment, Invoice.invoice_no, Receipt.receipt_no)
            .outerjoin(Invoice, Invoice.payment_id == Payment.id)
            .outerjoin(Receipt, Receipt.payment_id == Payment.id)
            .where(Payment.user_id == student.id, Payment.reference_type != agent_deposits.REFERENCE_TYPE)
            .order_by(Payment.created_at.desc(), Payment.id)
        )
    ).all()
    apps = await _applications(db, student.id)
    ids = [a.id for a, *_ in apps]
    records = {r.application_id: r for r in (await db.scalars(select(ApplicationDepositRecord).where(ApplicationDepositRecord.application_id.in_(ids)))).all()}
    agency = {d.application_id: d for d in (await db.scalars(select(ApplicationDeposit).where(ApplicationDeposit.application_id.in_(ids)))).all()}
    receipt_ids = [r.receipt_document_id for r in records.values() if r.receipt_document_id]
    receipts = {d.id: d for d in (await db.scalars(select(StudentDocument).where(StudentDocument.id.in_(receipt_ids)))).all()}

    deposits, refunds = [], []
    for a, university, *_ in apps:
        base = {"application_id": a.id, "application_code": a.application_code, "university": university, "mine": a.counselor_id == user.id}
        if record := records.get(a.id):
            doc = receipts.get(record.receipt_document_id)
            deposits.append(base | {
                "source": "counselor", "required": record.required, "amount": money(record.amount), "currency": record.currency, "due_date": record.due_date,
                "status": record.payment_status, "status_label": DEPOSIT_RECORD_LABELS[record.payment_status], "paid_on": record.paid_on, "refund": None,
                "receipt": {"id": doc.id, "name": doc.document_label or doc.document_type, "can_download": admin or a.counselor_id == user.id} if doc else None,
            })  # fmt: skip
        elif deposit := agency.get(a.id):
            refund = {"amount": money(deposit.refund_amount), "refunded_on": deposit.refunded_at, "reason": deposit.refund_reason} if deposit.refunded_at else None
            deposits.append(base | {
                "source": "agency", "required": deposit.required, "amount": money(deposit.amount), "currency": deposit.currency, "due_date": deposit.due_date,
                "status": deposit.status, "status_label": AGENCY_DEPOSIT_LABELS[deposit.status], "paid_on": deposit.paid_at.date() if deposit.paid_at else None,
                "refund": refund, "receipt": None,
            })  # fmt: skip
            if refund:
                refunds.append({"kind": "deposit", "description": f"University deposit — {university}", "amount": refund["amount"], "currency": deposit.currency, "refunded_on": refund["refunded_on"], "application_code": a.application_code})  # fmt: skip
    # F6: a gateway refund has no date of its own; the payment's last update is when it was marked refunded
    refunds += [
        {"kind": "payment", "description": _payment_description(p), "amount": money(p.amount), "currency": p.currency, "refunded_on": p.updated_at.date(), "application_code": None}
        for p, *_ in payments
        if p.status == "refunded"
    ]  # fmt: skip
    refunds.sort(key=lambda r: r["refunded_on"], reverse=True)
    return {
        "payments": [
            {
                "id": p.id, "description": _payment_description(p), "amount": money(p.amount), "currency": p.currency, "status": p.status,
                "status_label": PAYMENT_LABELS.get(p.status) or _humanize(p.status), "due_date": p.due_date, "created_at": p.created_at, "installment_no": p.installment_no,
                "invoice_no": invoice_no, "receipt_no": receipt_no, "can_download": admin,
            }
            for p, invoice_no, receipt_no in payments
        ],
        "deposits": deposits,
        "refunds": refunds,
    }  # fmt: skip
