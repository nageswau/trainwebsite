"""upc-017 (DEC-SCOPE-145 CO14, Q-21): a university's course CSV -- each row is created, reported as a duplicate (CO12's key, against the
university's courses and earlier rows) or reported invalid with its reason. Every row goes through `CourseIn` and the master's rules, as a
manual add does. Commission and scholarships are per-record decisions and are not imported. Functions only; the route commits."""

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import COUNSELING_CURRENCIES, COURSE_LEVELS, COURSE_MONTHS, ENGLISH_TESTS, CourseImportBatch, OverseasCourse, University, User
from app.schemas import CourseIn, validation_message
from app.services import university_courses as svc

COLUMNS = (
    "title", "level", "category", "duration", "intakes", "tuition_amount", "tuition_currency", "application_fee", "application_fee_currency",
    "english_test", "english_score", "entry_requirements", "application_process", "deadline", "active",
)  # fmt: skip
REQUIRED = ("title", "level", "category", "duration")
MAX_ROWS = 1000
TEXT_LIMIT = 200  # how much of the given title / level the report keeps
# A value list accepts its code in any case ("pg" = "PG", "ielts" = "IELTS", "sep" = "Sep").
_CANONICAL = {
    field: {v.casefold(): v for v in values}
    for field, values in {
        "level": COURSE_LEVELS, "tuition_currency": COUNSELING_CURRENCIES, "application_fee_currency": COUNSELING_CURRENCIES,
        "english_test": ENGLISH_TESTS, "intakes": COURSE_MONTHS,
    }.items()
}  # fmt: skip
_YES = {"yes": True, "y": True, "true": True, "1": True, "active": True, "no": False, "n": False, "false": False, "0": False, "inactive": False}


def _choice(field: str, value: str) -> str:
    return _CANONICAL[field].get(value.casefold(), value) if field in _CANONICAL else value


def parse_row(cells: dict[str, str]) -> dict | str:
    """The validated row as columns, or the reason it is invalid."""
    values: dict = {}
    for field, value in cells.items():
        if not value:
            continue
        if field == "intakes":
            values[field] = [_choice(field, part.strip()) for part in value.split(";") if part.strip()]
        elif field == "active":
            if value.casefold() not in _YES:
                return "active must be yes or no"
            values[field] = _YES[value.casefold()]
        else:
            values[field] = _choice(field, value)
    try:
        state = CourseIn.model_validate(values).model_dump(exclude={"commission"})
        svc.check_rules(state)
    except ValidationError as exc:
        return validation_message(exc)
    except HTTPException as exc:
        return exc.detail
    return state


def _result(line: int, cells: dict[str, str]) -> dict:
    return {"row_number": line, "status": "invalid", "title": cells.get("title", "")[:TEXT_LIMIT], "level": cells.get("level", "")[:TEXT_LIMIT], "course_id": None, "reason": None}


async def run(db: AsyncSession, user: User, uni: University, batch: CourseImportBatch, filled: list[tuple[int, dict[str, str]]]) -> list[dict]:
    """Each row's outcome, in file order; called under the university row lock, so a manual add cannot race a key (CO16)."""
    taken = await svc.existing_keys(db, uni.id)
    first_row: dict[tuple[str, str], int] = {}
    results = []
    for line, cells in filled:
        result = _result(line, cells)
        results.append(result)
        state = parse_row(cells)
        if isinstance(state, str):
            result["reason"] = state
            continue
        key = svc.title_key(state["title"], state["level"])
        if key in first_row:
            result.update(status="duplicate", reason=f"Repeats row {first_row[key]} of this file")
            continue
        first_row[key] = line
        if key in taken:
            result.update(status="duplicate", reason=svc.DUPLICATE)
            continue
        course = OverseasCourse(university_id=uni.id, tuition_fee="", intake="", **state)
        svc.derive_texts(course, set(state))
        db.add(course)
        await db.flush()
        svc.record(db, user, course, "create", import_batch_id=str(batch.id))
        result.update(status="created", course_id=str(course.id))
    return results


def summary(batch: CourseImportBatch, uploader: User) -> dict:
    return {
        "id": batch.id,
        "university_id": batch.university_id,
        "uploaded_by": {"id": uploader.id, "full_name": uploader.full_name},
        **{k: getattr(batch, k) for k in ("total_rows", "created_count", "duplicate_count", "invalid_count", "created_at")},
    }
