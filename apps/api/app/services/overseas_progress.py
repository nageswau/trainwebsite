"""nehn-033 (DEC-SCOPE-332) -- an overseas student's Progress page: each application's stepper (app/overseas_progress.py), the
documents they still have to upload and their next actions. Read-only: no lock, no write. One query per source, every one keyed on the
student's own id; never the visa refusal reason, outcome reasons, file keys or counselor notes. Spec:
docs/superpowers/specs/2026-10-29-nehn-033-overseas-progress-design.md."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application_checklists import item_status, status_label
from app.models import (
    ApplicationChecklistItem,
    ApplicationChecklistItemDocument,
    ApplicationDepositRecord,
    ApplicationOffer,
    ApplicationStatusHistory,
    OverseasApplication,
    StudentDocument,
    University,
    VisaCase,
)
from app.overseas_progress import progress
from app.services import student_document_requests as requests

UPLOAD_URL = "/overseas/student/documents"
# The statuses that mean the student has something to upload (an uploaded document awaiting review is not missing).
TO_UPLOAD = frozenset({"missing", "requested", "incomplete", "reupload_required", "expired"})
NOT_UPLOADED = "not_uploaded"
_OPEN_VISA = frozenset({"not_started", "preparing"})


def _missing(name: str, source: str, app, university: str | None, label: str, due=None, overdue: bool = False) -> dict:
    return {
        "name": name,
        "source": source,
        "application_code": app.application_code if app else None,
        "university": university,
        "status_label": label,
        "due_date": due,
        "overdue": overdue,
        "upload_url": UPLOAD_URL,
    }


async def build(db: AsyncSession, student_id: UUID) -> dict:
    rows = (
        await db.execute(
            select(OverseasApplication, University.name)
            .join(University, University.id == OverseasApplication.university_id)
            .where(OverseasApplication.student_id == student_id)
            .order_by(OverseasApplication.updated_at.desc(), OverseasApplication.id)
        )
    ).all()
    ids = [a.id for a, _ in rows]
    visas: dict[UUID, VisaCase] = {}
    latest: dict[tuple, str] = {}
    reached: dict[UUID, str | None] = {}
    if ids:
        for case in await db.scalars(select(VisaCase).where(VisaCase.application_id.in_(ids)).order_by(VisaCase.created_at.desc(), VisaCase.id.desc())):
            visas[case.application_id] = case  # descending, so the oldest wins (agent_visa.load_case, V7)
        docs = await db.execute(
            select(StudentDocument.application_id, StudentDocument.document_type, StudentDocument.verification_status)
            .where(StudentDocument.student_id == student_id, StudentDocument.application_id.in_(ids), StudentDocument.archived_at.is_(None))
            .order_by(StudentDocument.created_at, StudentDocument.id)
        )
        latest = {(application_id, document_type): status for application_id, document_type, status in docs}  # ascending: the newest wins
        withdrawn = [a.id for a, _ in rows if a.status == "withdrawn"]
        if withdrawn:
            history = await db.execute(
                select(ApplicationStatusHistory.application_id, ApplicationStatusHistory.from_status)
                .where(ApplicationStatusHistory.application_id.in_(withdrawn), ApplicationStatusHistory.to_status == "withdrawn")
                .order_by(ApplicationStatusHistory.created_at, ApplicationStatusHistory.id)
            )
            reached = dict(history.all())

    applications, live = [], []
    for app, university in rows:
        case = visas.get(app.id)
        checklist = list(case.checklist or []) if case else []
        result = progress(
            app.status,
            reached=reached.get(app.id),
            submitted=app.submitted_on is not None,
            offer_type=app.offer_type,
            visa_status=case.visa_status if case else None,
            visa_decision=case.decision if case else None,
            docs_complete=bool(checklist) and all(latest.get((app.id, item)) == "verified" for item in checklist),
            outcome=app.outcome,
        )
        applications.append({"id": app.id, "application_code": app.application_code, "university": university, "intake": app.intake} | result)
        if not result["closed"] and app.status != "enrolled":
            live.append((app, university))
    applications.sort(key=lambda a: a["closed"])  # stable: live first, each group newest first

    by_id = {app.id: (app, university) for app, university in rows}
    live_ids = [app.id for app, _ in live]
    missing = []
    open_requests = (await requests.page(db, student_id, status="open", limit=100, offset=0))["items"]
    for r in open_requests:
        app, university = by_id.get(r["application_id"], (None, None))
        if app is None or app.id in live_ids:
            missing.append(_missing(r["name"], "Document request", app, university, "Requested", r["due_date"], r["overdue"]))
    requested_items = {r["checklist_item_id"] for r in open_requests}
    if live_ids:
        items = list(
            (
                await db.scalars(
                    select(ApplicationChecklistItem)
                    .where(ApplicationChecklistItem.application_id.in_(live_ids), ApplicationChecklistItem.required.is_(True))
                    .order_by(ApplicationChecklistItem.application_id, ApplicationChecklistItem.position)
                )
            ).all()
        )
        linked: dict[UUID, list[str]] = {i.id: [] for i in items}
        if items:
            links = await db.execute(
                select(ApplicationChecklistItemDocument.item_id, StudentDocument.verification_status)
                .join(StudentDocument, StudentDocument.id == ApplicationChecklistItemDocument.document_id)
                .where(ApplicationChecklistItemDocument.item_id.in_(linked), StudentDocument.archived_at.is_(None))
            )
            for item_id, status in links:
                linked[item_id].append(status)
        for item in items:
            status = item_status(item.mark, linked[item.id])
            if status in TO_UPLOAD and item.id not in requested_items:
                app, university = by_id[item.application_id]
                missing.append(_missing(item.label or item.document_type, "Admission checklist", app, university, status_label(status)))
    for app, university in live:
        case = visas.get(app.id)
        if case is None or case.decision:
            continue
        for item in case.checklist or []:
            status = latest.get((app.id, item), NOT_UPLOADED)
            if status == NOT_UPLOADED or status in TO_UPLOAD:
                missing.append(_missing(item, "Visa checklist", app, university, "Not uploaded" if status == NOT_UPLOADED else status_label(status)))

    actions = []
    if missing:
        actions.append({"text": f"Upload {len(missing)} missing document{'' if len(missing) == 1 else 's'}", "href": UPLOAD_URL})
    if live_ids:
        offers = {
            o.application_id: o
            for o in await db.scalars(select(ApplicationOffer).where(ApplicationOffer.application_id.in_(live_ids), ApplicationOffer.status == "active", ApplicationOffer.decision == "considering"))
        }
        deposits = {
            d.application_id: d
            for d in await db.scalars(
                select(ApplicationDepositRecord).where(
                    ApplicationDepositRecord.application_id.in_(live_ids), ApplicationDepositRecord.required.is_(True), ApplicationDepositRecord.payment_status == "pending"
                )
            )
        }
        for app, university in live:
            if app.next_action:
                actions.append({"text": app.next_action, "href": None})
            if offer := offers.get(app.id):
                by = f" by {offer.offer_deadline:%d %b %Y}" if offer.offer_deadline else ""
                actions.append({"text": f"Tell your counselor whether you accept the offer from {university}{by}", "href": None})
            if deposit := deposits.get(app.id):
                by = f" by {deposit.due_date:%d %b %Y}" if deposit.due_date else ""
                actions.append({"text": f"Pay the deposit for {university}{by}", "href": "/overseas/student/payments"})
            case = visas.get(app.id)
            if case and not case.decision:
                if case.visa_status in _OPEN_VISA and case.appointment_date is None:
                    actions.append({"text": f"Book your visa appointment ({university})", "href": None})
                elif case.visa_status == "additional_info_requested":
                    actions.append({"text": f"Send the additional information the visa office asked for ({university})", "href": None})
    return {"applications": applications, "missing_documents": missing, "next_actions": actions}
