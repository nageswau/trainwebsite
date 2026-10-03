"""AGN-015 test helpers: the two URLs and direct builders for history, audit and deposit rows (the AGN-009 world supplies the rest)."""

from app.models import ApplicationDeposit, ApplicationStatusHistory, AuditLog
from tests.agn004_helpers import RECORDS


def journey_url(student_id) -> str:
    return f"{RECORDS}/{student_id}/journey"


def timeline_url(student_id, **params) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{RECORDS}/{student_id}/timeline" + (f"?{query}" if query else "")


async def mk_history(db, app, *, to_status, from_status=None, by=None, notes=None) -> ApplicationStatusHistory:
    row = ApplicationStatusHistory(application_id=app.id, from_status=from_status, to_status=to_status, changed_by_id=by.id if by else None, notes=notes)
    db.add(row)
    await db.commit()
    return row


async def mk_audit(db, *, user, action, entity_type, entity_id, metadata=None) -> AuditLog:
    row = AuditLog(user_id=user.id if user else None, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata or {})
    db.add(row)
    await db.commit()
    return row


async def mk_deposit(db, app, *, by, status="pending", **fields) -> ApplicationDeposit:
    """`pending` / `not_required` only: paid states need a Payment (the pure step tests cover them)."""
    required = status != "not_required"
    row = ApplicationDeposit(
        application_id=app.id, required=required, amount=fields.pop("amount", 5000 if required else None), status=status, created_by_user_id=by.id, updated_by_user_id=by.id, **fields
    )
    db.add(row)
    await db.commit()
    return row
