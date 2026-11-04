"""itc-001 (DEC-SCOPE-335): field-change audit with before and after values -- a generalised `management_audit.record`.

`audit_change` adds one `AuditLog` row to the caller's session (no commit, so the change and its row commit or roll back together) with
`metadata_json["changes"] = {field: [old, new]}` for the fields that actually changed, and writes nothing when none did. Personal data
(phone, email, notes, remarks and reason text) is never stored as a value: such a field is recorded as `"changed"`.
"""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

# A field whose name is one of these, or ends in `_<one of these>` (e.g. `parent_phone`), is personal data.
PII_FIELDS = frozenset({"phone", "email", "notes", "remarks", "reason"})


def _is_pii(field: str) -> bool:
    return field in PII_FIELDS or any(field.endswith(f"_{name}") for name in PII_FIELDS)


def _json_value(value):
    """A JSON-safe value: dates and datetimes as ISO 8601, anything else non-primitive (Decimal, UUID) as its exact string."""
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return value.isoformat() if isinstance(value, date) else str(value)


def changes(before: dict, after: dict, *, redact: frozenset | set = frozenset()) -> dict:
    """`{field: [old, new]}` for each field whose value differs; `{}` when nothing changed. A field missing on one side, None and ""
    are all the same empty value (QA-01: a form sends "" for an empty note). `redact` names extra fields recorded as "changed"
    (hrc-004: a caller's compensation and contact fields)."""
    diff: dict = {}
    for field in dict.fromkeys([*before, *after]):
        old, new = before.get(field), after.get(field)
        if old != new and not (old in (None, "") and new in (None, "")):
            diff[field] = "changed" if _is_pii(field) or field in redact else [_json_value(old), _json_value(new)]
    return diff


def audit_change(db: AsyncSession, actor: User, action: str, entity_type: str, entity_id, before: dict, after: dict, *, metadata: dict | None = None) -> AuditLog | None:
    """One audit row with the changed fields (plus the caller's ids-only `metadata`), or None and no row when nothing changed."""
    diff = changes(before, after)
    if not diff:
        return None
    row = AuditLog(user_id=actor.id, action=action, entity_type=entity_type, entity_id=str(entity_id), metadata_json={**(metadata or {}), "changes": diff})
    db.add(row)
    return row
