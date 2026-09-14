from uuid import UUID

from fastapi import HTTPException


def uuid_reference(value: object, label: str = "reference", *, required: bool = True) -> UUID | None:
    """Return a UUID from an API or profile value with a user-facing validation error."""
    if value is None or value == "":
        if required:
            raise HTTPException(422, f"A valid {label} is required")
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        if required:
            raise HTTPException(422, f"A valid {label} is required") from exc
        return None
