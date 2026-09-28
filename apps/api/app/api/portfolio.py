"""ENH-012 -- Digital Portfolio Module.

docs/superpowers/specs/2026-09-22-enh-012-digital-portfolio-design.md. Kept out of schools.py
deliberately: schools.py already has an unrelated existing meaning for "portfolio"
(_student_in_portfolio/_portfolio_school_ids/list_portfolio_students -- a staff member's
assigned-schools caseload). This module only imports and calls those, never modifies them.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.school_student_profile import _digest
from app.api.schools import _career_records_out, _entitlement_denial, _load_student_for_reader, _today_ist, require_school_entitlement
from app.core.database import get_db
from app.core.logging import get_logger
from app.models import (
    AuditLog,
    PortfolioEntry,
    PortfolioProfile,
    School,
    SchoolAcademicResult,
    SchoolCareerRecord,
    SchoolLanguageRecord,
    SchoolPsychometricRecord,
    SchoolStudent,
    User,
)
from app.schemas import (
    DATE_RANGE_ERROR,
    INTERNSHIP_FIELD_KEYS,
    INTERNSHIP_ONLY_ERROR,
    PORTFOLIO_SECTIONS,
    PersonalStatementOut,
    PersonalStatementUpdate,
    PortfolioEntryCreate,
    PortfolioEntryOut,
    PortfolioEntryUpdate,
    date_range_is_invalid,
    internship_rule_error,
    skill_india_error,
)
from app.services.storage import storage

router = APIRouter(prefix="/school", tags=["school-portfolio"])
logger = get_logger("app.portfolio")

WRITE_ROLES = {"school_coordinator", "school_teacher", "academic_team"}
CERTIFICATE_PREFIX = "portfolio-certificates"  # ENH-021: every internship certificate object key starts with this


def _entry_service_key(section: str, tracking_sent: bool) -> str:
    """ENH-021 I6: Platinum `internships` to create an internship entry or to set its tracking fields; everything else keeps
    ENH-012's Gold `digital_portfolio_creation`, so a Gold school keeps control of internship entries it already has."""
    return "internships" if section == "internship" and tracking_sent else "digital_portfolio_creation"


def discard_certificate(key: str, entry_id) -> None:
    """Delete a certificate object after its row change committed. Only keys this module generated are ever deleted (S5); a
    failure leaves an orphan, logged by key digest (never the key)."""
    fields = {"entry_id": str(entry_id), "key_digest": _digest(key)}
    if not key.startswith(f"{CERTIFICATE_PREFIX}/"):
        logger.error("internship_certificate_discard_refused", extra={"extra_fields": fields})
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("internship_certificate_orphaned", extra={"extra_fields": fields})
# Read scope: `schools._load_student_for_reader` -- this module's original loader, moved there unchanged by ENH-013 so the
# Student 360° view shares it (the 4 School roles via `_load_readable_student`, the 3 service roles via `_student_in_portfolio`).


def _can_edit_portfolio(user: User, student: SchoolStudent) -> bool:
    """Called only after `_load_student_for_reader` has already confirmed the caller can READ this
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
        "certification_type": entry.certification_type, "certification_status": entry.certification_status,
        "certificate_number": entry.certificate_number, "issued_on": entry.issued_on,
        **{key: getattr(entry, key) for key in INTERNSHIP_FIELD_KEYS},  # ENH-021, same keys as PortfolioEntryOut (A3)
        "has_certificate": entry.has_certificate, "certificate_content_type": entry.certificate_content_type,
        "created_by_user_id": entry.created_by_user_id, "updated_by_user_id": entry.updated_by_user_id,
        "created_at": entry.created_at, "updated_at": entry.updated_at,
    }


def _cert_audit(entry: PortfolioEntry) -> dict:
    """ENH-024 D16: the tag for a Skill India entry's audit row and log line; nothing for any other entry, so their audit rows
    stay exactly as before. Never the certificate number."""
    return {"certification_type": entry.certification_type} if entry.certification_type else {}


@router.get("/students/{student_id}/portfolio")
async def get_portfolio(student_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """No `response_model` -- matches `student_timeline()`'s own convention for a computed aggregate
    endpoint (schools.py:1040), the closest existing precedent this feature is modeled on."""
    student = await _load_student_for_reader(db, user, student_id)
    return await portfolio_payload(db, user, student)


async def portfolio_payload(db: AsyncSession, user: User, student: SchoolStudent) -> dict:
    """The portfolio body for an already scope-checked student -- extracted unchanged from `get_portfolio` so ENH-013's
    Student 360° view can reuse it. `user` only decides `can_edit`; it widens nothing."""
    can_edit = _can_edit_portfolio(user, student)
    profile_complete = _profile_complete(student)
    # ENH-021 QA-08: tell the page up front whether this viewer may create/track internships (Platinum `internships`), using the
    # same tier rule the write routes enforce, so the UI never offers what the server will refuse.
    school = await db.get(School, student.school_id)
    can_track_internships = bool(can_edit and school is not None and _entitlement_denial(school.tier, school.tier_valid_until, "internships", _today_ist()) is None)

    entries_by_section: dict[str, list[dict]] = {section: [] for section in sorted(PORTFOLIO_SECTIONS)}
    rows = (await db.scalars(select(PortfolioEntry).where(PortfolioEntry.school_student_id == student.id).order_by(PortfolioEntry.date_from.desc().nullslast(), PortfolioEntry.created_at.desc()))).all()
    for row in rows:
        # Guard against a stored `section` value that isn't in PORTFOLIO_SECTIONS today (forward/
        # backward compatibility: a future deploy could add a section and then roll back) -- skip
        # rather than KeyError -> uncaught 500.
        if row.section in entries_by_section:
            entries_by_section[row.section].append(_entry_out(row))

    academic = (await db.scalars(select(SchoolAcademicResult).where(SchoolAcademicResult.school_student_id == student.id, SchoolAcademicResult.status == "published"))).all()
    psychometric = (await db.scalars(select(SchoolPsychometricRecord).where(SchoolPsychometricRecord.school_student_id == student.id))).all()
    career = (await db.scalars(select(SchoolCareerRecord).where(SchoolCareerRecord.school_student_id == student.id))).all()
    languages = (await db.scalars(select(SchoolLanguageRecord).where(SchoolLanguageRecord.school_student_id == student.id))).all()

    profile_row = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
    personal_statement = profile_row.personal_statement if profile_row else None

    completion_components = [
        profile_complete,
        len(academic) > 0, len(psychometric) > 0, len(career) > 0, len(languages) > 0,
        *(len(entries_by_section[s]) > 0 for s in PORTFOLIO_SECTIONS),
        bool(personal_statement and personal_statement.strip()),
    ]
    completion_percentage = round(sum(completion_components) / len(completion_components) * 100)

    return {
        "student": {"id": student.id, "full_name": student.full_name},
        "completion_percentage": completion_percentage,
        "can_edit": can_edit,
        "can_track_internships": can_track_internships,
        "profile_complete": profile_complete,
        "academic_achievements": [{"id": r.id, "term": r.term, "subject": r.subject, "grade": r.grade, "published_at": r.published_at} for r in academic],
        "psychometric_report": [{"id": r.id, "assessment_type": r.assessment_type, "report_url": r.report_url, "created_at": r.created_at} for r in psychometric],
        # ENH-026 QA-02: the shared serializer, so the 360 Career Guidance tab gets the §7 fields the overview already shows.
        "career_guidance": await _career_records_out(db, career),
        "languages": [{"id": r.id, "language": r.language, "level": r.level, "certification_status": r.certification_status, "created_at": r.created_at} for r in languages],
        "entries": entries_by_section,
        "personal_statement": personal_statement,
    }


@router.post("/students/{student_id}/portfolio/entries", status_code=201, response_model=PortfolioEntryOut)
async def create_portfolio_entry(student_id: UUID, payload: PortfolioEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)
    await require_school_entitlement(db, user, student.school_id, _entry_service_key(payload.section, payload.section == "internship"))
    entry = PortfolioEntry(
        school_student_id=student.id, section=payload.section, title=payload.title,
        description=payload.description, organization=payload.organization,
        date_from=payload.date_from, date_to=payload.date_to,
        certification_type=payload.certification_type, certification_status=payload.certification_status,
        certificate_number=payload.certificate_number, issued_on=payload.issued_on,
        **{key: getattr(payload, key) for key in INTERNSHIP_FIELD_KEYS},
        created_by_user_id=user.id, updated_by_user_id=user.id,
    )
    db.add(entry)
    await db.flush()
    audit = {"section": entry.section, "school_student_id": str(student.id), **_cert_audit(entry)}
    if entry.certification_type:
        audit["certification_status"] = entry.certification_status
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_create", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json=audit))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_create", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id), "section": entry.section, **_cert_audit(entry)}})
    return entry


async def _load_portfolio_entry(db: AsyncSession, student_id: UUID, entry_id: UUID, *, for_update: bool = False) -> PortfolioEntry:
    stmt = select(PortfolioEntry).where(PortfolioEntry.id == entry_id)
    if for_update:  # ENH-021: edits, deletes and certificate changes on one entry serialize (spec §5.2)
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    entry = await db.scalar(stmt)
    if not entry or entry.school_student_id != student_id:
        raise HTTPException(404, "Portfolio entry not found")
    return entry


@router.patch("/students/{student_id}/portfolio/entries/{entry_id}", response_model=PortfolioEntryOut)
async def update_portfolio_entry(student_id: UUID, entry_id: UUID, payload: PortfolioEntryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)  # role/scope checked before the entry lookup below (spec §6)
    entry = await _load_portfolio_entry(db, student.id, entry_id, for_update=True)
    tracking_sent = bool(payload.model_fields_set & set(INTERNSHIP_FIELD_KEYS))
    if tracking_sent and entry.section != "internship":
        raise HTTPException(422, INTERNSHIP_ONLY_ERROR)
    # ENH-023 D8: editing an entry that existed before a downgrade finishes existing work. ENH-021 I6: tracking fields need Platinum.
    await require_school_entitlement(db, user, student.school_id, _entry_service_key(entry.section, tracking_sent), grandfathered_since=entry.created_at)
    old_status = entry.certification_status
    # `model_fields_set` distinguishes "field explicitly present in the request payload" (apply it, even
    # when the value is None -- that's the clear-the-field case) from "field omitted" (leave the entry's
    # existing value untouched). A plain `if value is not None` check (the previous logic) could never
    # tell those two apart, so there was no way to ever clear description/organization/date_from/date_to
    # via PATCH -- an explicit `null` looked identical to "didn't send this field". (`title`'s NOT NULL
    # constraint is guarded at the schema layer -- PortfolioEntryUpdate rejects an explicit null there,
    # before this handler ever runs -- so nothing special-cases it in this merge loop.)
    fields_set = payload.model_fields_set
    for field in ("title", "description", "organization", "date_from", "date_to", "certification_status", "certificate_number", "issued_on", *INTERNSHIP_FIELD_KEYS):
        if field in fields_set:
            setattr(entry, field, getattr(payload, field))
    # Date-range merge-validation: after merging payload fields onto entry, validate the merged result --
    # a payload-only schema validator can't see the entry's already-stored values, so this re-checks the
    # same rule (schemas.py's date_range_is_invalid/DATE_RANGE_ERROR) against the post-merge state.
    if date_range_is_invalid(entry.date_from, entry.date_to):
        raise HTTPException(422, DATE_RANGE_ERROR)
    # ENH-024: the same Skill India rule as a create, on the merged state (the tag itself is never in the payload -- D8).
    cert_error = skill_india_error(entry.certification_type, entry.certification_status, entry.certificate_number, entry.issued_on)
    if cert_error:
        raise HTTPException(422, cert_error)
    if entry.section == "internship":  # ENH-021 I4, same post-merge reasoning as the date range above
        error = internship_rule_error(entry.organization, entry.completion_status, entry.date_to)
        if error:
            raise HTTPException(422, error)
        if entry.certificate_key and entry.completion_status != "completed":
            raise HTTPException(422, "Remove the certificate first")
    entry.updated_by_user_id = user.id
    await db.flush()
    audit = {"section": entry.section, "school_student_id": str(student.id), **_cert_audit(entry)}
    if entry.certification_status != old_status:
        audit.update(old_status=old_status, new_status=entry.certification_status)
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_update", entity_type="portfolio_entry", entity_id=str(entry.id), metadata_json=audit))
    await db.commit()
    await db.refresh(entry)
    logger.info("portfolio_entry_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": str(entry.id), **_cert_audit(entry)}})
    return entry


@router.delete("/students/{student_id}/portfolio/entries/{entry_id}", status_code=204)
async def delete_portfolio_entry(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)  # role/scope checked before the entry lookup below (spec §6)
    entry = await _load_portfolio_entry(db, student.id, entry_id, for_update=True)
    # ENH-023 D8: removing an entry that existed before a downgrade finishes existing work.
    await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation", grandfathered_since=entry.created_at)
    section, entry_id_str, certificate_key, cert = entry.section, str(entry.id), entry.certificate_key, _cert_audit(entry)
    await db.delete(entry)
    db.add(AuditLog(user_id=user.id, action="school.portfolio_entry_delete", entity_type="portfolio_entry", entity_id=entry_id_str, metadata_json={"section": section, "school_student_id": str(student.id), "had_certificate": certificate_key is not None, **cert}))
    await db.commit()
    if certificate_key:  # ENH-021: the object goes only after the row's deletion committed
        discard_certificate(certificate_key, entry_id_str)
    logger.info("portfolio_entry_delete", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id), "entry_id": entry_id_str, **cert}})


@router.patch("/students/{student_id}/portfolio/personal-statement", response_model=PersonalStatementOut)
async def update_personal_statement(student_id: UUID, payload: PersonalStatementUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Upsert via the same begin_nested()/IntegrityError idiom as school_transfers.py:277-284, but
    resolved as an update-on-conflict rather than a 409: a second concurrent "set the statement" is not
    a duplicate-intent conflict like a transfer filing (spec §6)."""
    student = await _load_student_for_reader(db, user, student_id)
    _require_portfolio_write(user, student)
    # ENH-023 D8: a statement already started is existing work; the first one ever is new work.
    started = await db.scalar(select(PortfolioProfile.created_at).where(PortfolioProfile.school_student_id == student.id))
    await require_school_entitlement(db, user, student.school_id, "digital_portfolio_creation", grandfathered_since=started)
    statement = payload.personal_statement.strip() if payload.personal_statement else None
    row = None
    try:
        async with db.begin_nested():
            row = PortfolioProfile(school_student_id=student.id, personal_statement=statement, updated_by_user_id=user.id)
            db.add(row)
            await db.flush()
    except IntegrityError:
        row = await db.scalar(select(PortfolioProfile).where(PortfolioProfile.school_student_id == student.id))
        if row is None:
            # The IntegrityError wasn't the expected unique-constraint collision on
            # school_student_id (a concurrent first insert) -- re-raise rather than fall through to an
            # AttributeError on `row.personal_statement` below.
            raise
        row.personal_statement = statement
        row.updated_by_user_id = user.id
        await db.flush()
    db.add(AuditLog(user_id=user.id, action="school.portfolio_personal_statement_update", entity_type="portfolio_profile", entity_id=str(row.id), metadata_json={"school_student_id": str(student.id)}))
    await db.commit()
    await db.refresh(row)
    logger.info("portfolio_personal_statement_update", extra={"extra_fields": {"actor_id": str(user.id), "student_id": str(student.id)}})
    return {"personal_statement": row.personal_statement, "updated_at": row.updated_at}
