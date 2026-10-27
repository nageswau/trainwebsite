"""nehn-012 (DEC-SCOPE-298): what the admin and telecaller lead lists share -- the India-time created range, the counselor filter and the
fixed-column Excel table of the filtered list (nehn-008's per-role column policy is not built yet, so this is the admin / manager set).

Functions only; the route owns the scope, the transaction and the export step (`crm_exports.export`)."""

from datetime import date
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Enquiry, LeadCall, LeadFollowUp, LeadMessage
from app.services import bdm_leads
from app.services.application_filters import DATE_ORDER
from app.services.bdm_activities import day_range
from app.services.telecaller_reports import SOURCE_LABELS

COLUMNS = (
    ("lead_code", "Lead ID"), ("name", "Name"), ("phone", "Phone"), ("email", "Email"), ("source", "Source"), ("interest", "Course interest"),
    ("stage", "Stage"), ("telecaller", "Telecaller"), ("counselor", "Counselor"), ("created", "Created"), ("last_contact", "Last contact"),
    ("next_follow_up", "Next follow-up"),
)  # fmt: skip


def filters(created_from: date | None, created_to: date | None, owner_id: UUID | None) -> list:
    """Inclusive India-time calendar days on `created_at` (half-open instants, so the index is used) and the assigned counselor. A
    reversed range is 422; the typed query parameters already refuse a malformed date or id."""
    if created_from and created_to and created_from > created_to:
        raise HTTPException(422, DATE_ORDER)
    clauses = []
    if created_from:
        clauses.append(Enquiry.created_at >= day_range(created_from)[0])
    if created_to:
        clauses.append(Enquiry.created_at < day_range(created_to)[1])
    if owner_id:
        clauses.append(Enquiry.owner_id == owner_id)
    return clauses


def audited(q: str | None, **values) -> dict:
    """The filters for the audit row: ids, keys and dates as given; the search text only as set (never personal data)."""
    given = {key: str(value) for key, value in values.items() if value}
    return {"q": True, **given} if q else given


async def table(db: AsyncSession, where: list, limit: int) -> dict:
    """The list's rows in the list's order, with the latest logged call or message and the earliest open follow-up -- three queries."""
    rows = (await db.execute(bdm_leads.admin_rows().where(*where).order_by(*bdm_leads.NEWEST).limit(limit))).all()
    ids = [row[0].id for row in rows]
    calls = dict((await db.execute(select(LeadCall.lead_id, func.max(LeadCall.occurred_at)).where(LeadCall.lead_id.in_(ids)).group_by(LeadCall.lead_id))).all())
    messages = dict((await db.execute(select(LeadMessage.lead_id, func.max(LeadMessage.sent_at)).where(LeadMessage.lead_id.in_(ids)).group_by(LeadMessage.lead_id))).all())
    due = dict((await db.execute(select(LeadFollowUp.lead_id, func.min(LeadFollowUp.due_at)).where(LeadFollowUp.lead_id.in_(ids), LeadFollowUp.status == "open")
                                 .group_by(LeadFollowUp.lead_id))).all())  # fmt: skip
    items = []
    for row in rows:
        x = bdm_leads.admin_out(row)
        contacts = [at for at in (calls.get(x["id"]), messages.get(x["id"])) if at]
        items.append({
            "lead_code": x["lead_code"], "name": x["name"], "phone": x["phone"], "email": x["email"], "source": SOURCE_LABELS.get(x["source"], x["source"]),
            "interest": (x["product"] or {}).get("name") or x["subject"], "stage": x["status_label"], "telecaller": (x["telecaller"] or {}).get("full_name"),
            "counselor": (x["counselor"] or {}).get("full_name"), "created": x["created_at"], "last_contact": max(contacts, default=None),
            "next_follow_up": due.get(x["id"]),
        })  # fmt: skip
    return {"columns": [{"key": key, "label": label} for key, label in COLUMNS], "items": items, "totals": None}
