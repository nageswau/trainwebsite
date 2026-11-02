"""itc-001 (DEC-SCOPE-335): field-change audit with before and after values -- a generalised `management_audit.record`.

`audit_change` adds one `AuditLog` row to the caller's session (no commit, so the change and its row commit or roll back together) with
`metadata_json["changes"] = {field: [old, new]}` for the fields that actually changed, and writes nothing when none did. Personal data
(phone, email, notes, remarks and reason text) is never stored as a value: such a field is recorded as `"changed"`.
"""

from datetime import date, datetime
from enum import Enum

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

# A field whose name is one of these, or ends in `_<one of these>` (e.g. `parent_phone`), is personal data.
PII_FIELDS = frozenset({"phone", "email", "notes", "remarks", "reason"})


def _is_pii(field: str) -> bool:
    return field in PII_FIELDS or any(field.endswith(f"_{name}") for name in PII_FIELDS)


def _json_value(value):
    """A JSON-safe value: dates as ISO 8601, enums as their value, anything else (Decimal, UUID) as its exact string."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Enum):
        return _json_value(value.value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return str(value)


def changes(before: dict, after: dict) -> dict:
    """`{field: [old, new]}` for each field whose value differs (a field missing on one side counts as None); `{}` when nothing changed."""
    diff: dict = {}
    for field in dict.fromkeys([*before, *after]):
        old, new = before.get(field), after.get(field)
        if old != new:
            diff[field] = "changed" if _is_pii(field) else [_json_value(old), _json_value(new)]
    return diff


def audit_change(db: AsyncSession, actor: User | None, action: str, entity_type: str, entity_id, before: dict, after: dict, *, metadata: dict | None = None) -> AuditLog | None:
    """One audit row with the changed fields (plus the caller's ids-only `metadata`), or None and no row when nothing changed."""
    diff = changes(before, after)
    if not diff:
        return None
    row = AuditLog(
        user_id=actor.id if actor else None, action=action, entity_type=entity_type, entity_id=None if entity_id is None else str(entity_id), metadata_json={**(metadata or {}), "changes": diff}
    )
    db.add(row)
    return row
