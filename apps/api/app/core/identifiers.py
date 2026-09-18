import secrets
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

STUDENT_CODE_LENGTH = 8


def generate_student_code() -> str:
    """8-character uppercase alphanumeric business-facing Student ID (PRD_OPEN_ITEMS.md
    item 66 / CLIENT_QUESTIONS.md D-09). Reuses this codebase's own existing short-code
    convention (secrets.token_hex(N).upper(), see enrollment_code/certificate_no in
    workflows.py) rather than inventing a new alphabet -- hex naturally excludes the most
    commonly confused letters (I/O/L don't appear), which also serves the "memorable/
    searchable" intent from the original request without adding bespoke encoding rules
    nobody asked for.
    """
    return secrets.token_hex(STUDENT_CODE_LENGTH // 2).upper()


async def unique_student_code(db: AsyncSession, column) -> str:
    """Generate a student_code guaranteed unique for the given mapped column (e.g.
    User.student_code, SchoolStudent.student_code), retrying on collision rather than
    assuming the ~4.3 billion-code space can't ever repeat."""
    for _ in range(10):
        code = generate_student_code()
        if not await db.scalar(select(column).where(column == code)):
            return code
    raise RuntimeError("Could not generate a unique student code after 10 attempts")


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
