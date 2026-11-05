"""hrc-004 (DEC-SCOPE-376): before/after values in the recruitment audit rows, and a record's change history.

The write sites keep their audit metadata (`fields`, `from`/`to`, ids -- hrc-003's `require_fresh` reads `fields`) and add itc-001's
`changes` diff from `diff()`. Compensation, contact and free-text feedback are recorded as "changed", never as values (B4)."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.services import audit_changes, candidates

# B4: on top of itc-001's personal-data names (phone, email, notes, remarks, reason and `*_<those>`).
REDACTED = frozenset({
    "salary", "salary_min", "salary_max", "salary_currency", "salary_period", "benefits", *candidates.COMPENSATION,  # hrc-005 V7: a job's pay  # compensation (a JD's free-text salary; hrc-011's package detail)
    "mobile", "linkedin", "meeting_url", "contact_id",  # contact
    "strengths", "weaknesses", "recruiter_comments", "company_feedback",  # interview feedback text
    # pob-002 (DEC-SCOPE-407 R8/R12): the History card is read by every requirement reader, so client terms and the decision-maker are
    # recorded as "changed" (their values live in the commercial-gated revisions)
    "payment_trigger", "payment_days", "payment_terms", "replacement_terms", "decision_maker_contact",
})


def diff(before: dict, after: dict) -> dict:
    return audit_changes.changes(before, after, redact=REDACTED)


async def history(db: AsyncSession, entity_type: str, entity_id, prefixes: tuple[str, ...], *, limit: int, offset: int) -> dict:
    """B6: the record's own audit rows (these action prefixes; downloads are reads, not changes), newest first, on
    `ix_audit_logs_entity`. Only the diff and the field names leave -- never the raw metadata (ids, notes)."""
    where = (
        AuditLog.entity_type == entity_type,
        AuditLog.entity_id == str(entity_id),
        or_(*(AuditLog.action.startswith(prefix) for prefix in prefixes)),
        ~AuditLog.action.endswith("download"),
        ~AuditLog.action.endswith("_link"),  # hrc-015: a signed link issued is a read too
    )
    total = await db.scalar(select(func.count()).select_from(AuditLog).where(*where))
    rows = (await db.execute(
        select(AuditLog, User).outerjoin(User, User.id == AuditLog.user_id).where(*where)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    )).all()
    return {"items": [_item(row, actor) for row, actor in rows], "total": total or 0, "limit": limit, "offset": offset}


def _item(row: AuditLog, actor: User | None) -> dict:
    metadata = row.metadata_json or {}
    changes, fields = metadata.get("changes"), metadata.get("fields")
    return {
        "id": row.id,
        "action": row.action,
        "created_at": row.created_at,
        "actor": {"id": actor.id, "full_name": actor.full_name} if actor else None,
        "changes": changes if isinstance(changes, dict) and changes else None,  # older rows: list-shaped or absent
        "fields": fields if isinstance(fields, list) and all(isinstance(f, str) for f in fields) else None,
    }
