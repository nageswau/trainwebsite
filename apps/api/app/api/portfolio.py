"""ENH-012 -- Digital Portfolio Module.

docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md. Kept out of schools.py
deliberately: schools.py already has an unrelated existing meaning for "portfolio"
(_student_in_portfolio/_portfolio_school_ids/list_portfolio_students -- a staff member's
assigned-schools caseload). This module only imports and calls those, never modifies them.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schools import _load_readable_student, _student_in_portfolio
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    AuditLog,
    PortfolioEntry,
    PortfolioProfile,
    SchoolAcademicResult,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolStudent,
    User,
)
from app.schemas import (
    PORTFOLIO_SECTIONS,
    PersonalStatementOut,
    PersonalStatementUpdate,
    PortfolioEntryCreate,
    PortfolioEntryOut,
    PortfolioEntryUpdate,
)

router = APIRouter(prefix="/school", tags=["school-portfolio"])
logger = get_logger("app.portfolio")

PORTFOLIO_SCOPED_ROLES = {"academic_team", "career_counselor", "psychometric_team"}
WRITE_ROLES = {"school_coordinator", "school_teacher", "academic_team"}


async def _load_portfolio_student(db: AsyncSession, user: User, student_id: UUID) -> SchoolStudent:
    """Read-scope loader: the 4 institution/assigned/own-child roles reuse `_load_readable_student()`
    unchanged; the 3 portfolio-scoped service-delivery roles reuse `_student_in_portfolio()` unchanged.
    Neither existing helper is modified -- only called (spec §6, §8)."""
    if user.role in PORTFOLIO_SCOPED_ROLES:
        return await _student_in_portfolio(db, user, student_id)
    return await _load_readable_student(db, user, student_id)


def _can_edit_portfolio(user: User, student: SchoolStudent) -> bool:
    """Called only after `_load_portfolio_student` has already confirmed the caller can READ this
    student -- this narrows that to the 3 write-capable roles. `school_teacher` gets the extra
    assigned-only check `_load_readable_student` already enforced for read, repeated here because a
    boolean helper must not assume its caller re-derives it."""
    if user.role not in WRITE_ROLES:
        return False
    if user.role == "school_teacher":
        return student.assigned_teacher_user_id == user.id
    return True


def _require_portfolio_write(user: User, student: SchoolStudent) -> None:
    if not _can_edit_portfolio(user, student):
        raise HTTPException(403, "You do not have write access to this student's portfolio")


def _profile_complete(student: SchoolStudent) -> bool:
    # Field audit, spec §13.1 (resolved in Task 1): the only two nullable profile-shaped fields on
    # SchoolStudent today. ENH-025 (mandatory full field coverage) is a separate, not-yet-built item.
    return student.date_of_birth is not None and student.grade_or_class is not None


def _entry_out(entry: PortfolioEntry) -> dict:
    return {
        "id": entry.id, "school_student_id": entry.school_student_id, "section": entry.section,
        "title": entry.title, "description": entry.description, "organization": entry.organization,
        "date_from": entry.date_from, "date_to": entry.date_to,
        "created_by_user_id": entry.created_by_user_id, "updated_by_user_id": entry.updated_by_user_id,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


@router.get("/students/{student_id}/portfolio")
async def get_portfolio(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """No `response_model` -- matches `student_timeline()`'s own convention for a computed aggregate
    endpoint (schools.py:1040), the closest existing precedent this feature is modeled on."""
    student = await _load_portfolio_student(db, user, student_id)
    can_edit = _can_edit_portfolio(user, student)

    entries_by_section: dict[str, list[dict]] = {section: [] for section in sorted(PORTFOLIO_SECTIONS)}
    rows = (await db.scalars(select(PortfolioEntry).where(PortfolioEntry.school_student_id == student.id).order_by(PortfolioEntry.date_from.desc().nullslast(), PortfolioEntry.created_at.desc()))).all()
    for row in rows:
        entries_by_section[row.section].append(_entry_out(row))

    academic = (await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == student.id, SchoolAcademicResult.status == "published"))).all()
    psychometric = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id == student.id))).all()
    career = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == student.id))).all()
    languages = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id == student.id))).all()

    profile_row = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    personal_statement = profile_row.personal_statement if profile_row else None

    filled = sum([
        _profile_complete(student),
        len(academic) > 0, len(psychometric) > 0, len(career) > 0, len(languages) > 0,
        *(len(entries_by_section[s]) > 0 for s in PORTFOLIO_SECTIONS),
        bool(personal_statement and personal_statement.strip()),
    ])
    completion_percentage = round(filled / 16 * 100)

    return {
        "student": {"id": student.id, "full_name": student.full_name},
        "completion_percentage": completion_percentage,
        "can_edit": can_edit,
        "profile_complete": _profile_complete(student),
        "academic_achievements": [{"id": r.id, "term": r.term, "subject": r.subject, "grade": r.grade, "published_at": r.published_at} for r in academic],
        "psychometric_report": [{"id": r.id, "assessment_type": r.assessment_type, "report_url": r.report_url, "created_at": r.created_at} for r in psychometric],
        "career_guidance": [{"id": r.id, "record_type": r.record_type, "notes": r.notes, "created_at": r.created_at} for r in career],
        "languages": [{"id": r.id, "language": r.language, "level": r.level, "certification_status": r.certification_status, "created_at": r.created_at} for r in languages],
        "entries": entries_by_section,
        "personal_statement": personal_statement,
    }


@router.post("/students/{student_id}/portfolio/entries", status_code=201, response_model=PortfolioEntryOut)
async def create_portfolio_entry(student_id: UUID, payload: PortfolioEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_portfolio_student(db, user, student_id)
    _require_portfolio_write(user, student)
    entry = PortfolioEntry(
        school_student_id=student.id, section=payload.section, title=payload.title,
        description=payload.description, organization=payload.organization,
        date_from=payload.date_from, date_to=payload.date_to,
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(entry)
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_create", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"section": entry.section, "school_student_id": str(student.id)}))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_create", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id), "section": entry.section}})
    return _entry_out(entry)


async def _load_portfolio_entry(db: AsyncSession, student_id: UUID, entry_id: UUID) -> PortfolioEntry:
    entry = await db.get(PortfolioEntry, entry_id)
    if not entry or entry.school_student_id != student_id:
        raise HTTPException(404, "Portfolio entry not found")
    return entry


@router.patch("/students/{student_id}/portfolio/entries/{entry_id}", response_model=PortfolioEntryOut)
async def update_portfolio_entry(student_id: UUID, entry_id: UUID, payload: PortfolioEntryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_portfolio_student(db, user, student_id)
    _require_portfolio_write(user, student)  # role/scope checked before the entry lookup below (spec §6)
    entry = await _load_portfolio_entry(db, student.id, entry_id)
    for field in ("title", "description", "organization", "date_from", "date_to"):
        value = getattr(payload, field)
        if value is not None:
            setattr(entry, field, value)
    # Date-range merge-validation fix: after merging payload fields onto entry, validate the merged result
    # if both date_from and date_to are now set and date_to < date_from, reject the update
    if entry.date_from is not None and entry.date_to is not None and entry.date_to < entry.date_from:
        raise HTTPException(422, "date_to must not be before date_from")
    entry.updated_by_user_id = user.id
    await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_update", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json={"section": entry.section, "school_student_id": str(student.id)}))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id)}})
    return _entry_out(entry)
