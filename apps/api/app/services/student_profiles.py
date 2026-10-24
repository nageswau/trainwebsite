"""ccrm-007 (DEC-SCOPE-249, P1-P6): the structured overseas student profile -- personal and passport details, qualifications, work
experience, study preferences and English tests. The overseas counselor reads and writes it for the students in their csc-001 scope, the
Overseas Admin for any overseas student, and the student for themselves (P1: every field). Last write wins (CC5); each save is audited
with the changed field names only, never their values. The agency reads it without the passport (P2/P3)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Country, OverseasStudentEnglishTest, OverseasStudentProfile, OverseasStudentQualification, User
from app.schemas import StudentProfileSave
from app.services.counselor_students import STUDENT_NOT_FOUND, is_visible_student

NOT_ALLOWED = "Only an overseas counselor or the Overseas Admin can see student profiles"
STUDENTS_ONLY = "Only an overseas student has this profile"
CHOOSE_LISTED_COUNTRY = "Choose a listed country"
UPDATED = "overseas_student_profile.update"
PASSPORT_FIELDS = ("passport_number", "passport_expiry")
SCALARS = (
    "date_of_birth", "nationality", "city", "state", "passport_number", "passport_expiry", "work_experience_months", "work_experience_details",
    "preferred_course", "preferred_level", "preferred_intake", "study_mode", "budget_min", "budget_max", "budget_currency",
)  # fmt: skip
QUALIFICATION_FIELDS = ("level", "qualification_name", "institution", "board_university", "year_completed", "score_type", "score", "backlogs")
TEST_FIELDS = ("test_type", "status", "overall_score", "test_date", "valid_until", "remarks")
LEVEL_LABELS = {"class_10": "Class 10", "class_12": "Class 12", "diploma": "Diploma", "bachelor": "Bachelor's degree", "master": "Master's degree", "phd": "PhD", "other": "Other"}
STATUS_LABELS = {"not_taken": "not taken", "booked": "booked", "taken": "taken"}


def _is_admin(user: User) -> bool:
    return user.role == "overseas_admin" and user.division == "overseas"


async def staff_student(db: AsyncSession, user: User, student_id: UUID) -> User:
    """The overseas student the counselor or admin may see; anything else is the same 404 (no disclosure)."""
    admin = _is_admin(user)
    if not admin and (user.role != "counselor" or user.division != "overseas"):  # an IT counselor works leads only (tel-017)
        raise HTTPException(403, NOT_ALLOWED)
    student = await db.scalar(select(User).where(User.id == student_id, User.role == "overseas_student"))
    if student is None or (not admin and not await is_visible_student(db, user, student_id)):
        raise HTTPException(404, STUDENT_NOT_FOUND)
    return student


def require_student(user: User) -> User:
    if user.role != "overseas_student" or user.division != "overseas":
        raise HTTPException(403, STUDENTS_ONLY)
    return user


def _number(value: Decimal | None) -> str | None:
    return None if value is None else str(value)  # exact, as stored ("8.20"); FastAPI would turn a Decimal into a float


async def _rows(db: AsyncSession, student_id: UUID):
    profile = await db.get(OverseasStudentProfile, student_id)
    if profile is None:
        return None, [], []
    qualifications = (await db.scalars(select(OverseasStudentQualification).where(OverseasStudentQualification.student_user_id == student_id).order_by(OverseasStudentQualification.position))).all()
    tests = (await db.scalars(select(OverseasStudentEnglishTest).where(OverseasStudentEnglishTest.student_user_id == student_id).order_by(OverseasStudentEnglishTest.position))).all()
    return profile, qualifications, tests


async def read(db: AsyncSession, student_id: UUID, *, passport: bool = True) -> dict:
    """The profile as the UI shows it; an unsaved profile reads as empty (`exists: false`)."""
    profile, qualifications, tests = await _rows(db, student_id)
    out: dict = {field: getattr(profile, field, None) for field in SCALARS}
    out |= {"budget_min": _number(out["budget_min"]), "budget_max": _number(out["budget_max"]), "exists": profile is not None}
    country_ids = [UUID(c) for c in (profile.preferred_country_ids if profile else [])]
    names = dict((await db.execute(select(Country.id, Country.name).where(Country.id.in_(country_ids)))).all()) if country_ids else {}
    out["preferred_countries"] = [{"id": cid, "name": names[cid]} for cid in country_ids if cid in names]
    out["qualifications"] = [{field: getattr(q, field) for field in QUALIFICATION_FIELDS} | {"score": _number(q.score)} for q in qualifications]
    today = date.today()
    out["english_tests"] = [{field: getattr(t, field) for field in TEST_FIELDS} | {"overall_score": _number(t.overall_score), "expired": bool(t.valid_until and t.valid_until < today)} for t in tests]
    author = await db.get(User, profile.updated_by_user_id) if profile and profile.updated_by_user_id else None
    out |= {"updated_at": profile.updated_at if profile else None, "updated_by_name": author.full_name if author else None}
    if not passport:
        for field in PASSPORT_FIELDS:
            out.pop(field)
    return out


def _as_saved(profile, qualifications, tests) -> dict:
    """The stored profile in the shape of a save, so a save can name the fields it changed."""
    if profile is None:
        return StudentProfileSave().model_dump()
    current = {field: getattr(profile, field) for field in SCALARS} | {"preferred_country_ids": [UUID(c) for c in profile.preferred_country_ids]}
    current["qualifications"] = [{field: getattr(q, field) for field in QUALIFICATION_FIELDS} for q in qualifications]
    current["english_tests"] = [{field: getattr(t, field) for field in TEST_FIELDS} for t in tests]
    return current


async def save(db: AsyncSession, actor: User, student: User, payload: StudentProfileSave) -> dict:
    """Commits. The student's row is locked first, so two first saves cannot both insert the profile (last write wins after that)."""
    actor_id, student_id = actor.id, student.id
    await db.execute(select(User.id).where(User.id == student_id).with_for_update())
    if payload.preferred_country_ids:
        found = await db.scalar(select(func.count()).select_from(Country).where(Country.id.in_(payload.preferred_country_ids)))
        if found != len(payload.preferred_country_ids):
            raise HTTPException(422, CHOOSE_LISTED_COUNTRY)
    profile, qualifications, tests = await _rows(db, student_id)
    before, after = _as_saved(profile, qualifications, tests), payload.model_dump()
    changed = sorted(field for field in after if before[field] != after[field])
    if profile is None:
        profile = OverseasStudentProfile(student_user_id=student_id)
        db.add(profile)
    for field in SCALARS:
        setattr(profile, field, after[field])
    profile.preferred_country_ids = [str(c) for c in payload.preferred_country_ids]
    profile.updated_by_user_id = actor_id
    profile.updated_at = func.now()  # an unchanged save still records who saved last
    await db.flush()
    await db.execute(delete(OverseasStudentQualification).where(OverseasStudentQualification.student_user_id == student_id))
    await db.execute(delete(OverseasStudentEnglishTest).where(OverseasStudentEnglishTest.student_user_id == student_id))
    db.add_all(OverseasStudentQualification(student_user_id=student_id, position=i, **q) for i, q in enumerate(after["qualifications"]))
    db.add_all(OverseasStudentEnglishTest(student_user_id=student_id, position=i, **t) for i, t in enumerate(after["english_tests"]))
    db.add(AuditLog(user_id=actor_id, action=UPDATED, entity_type="user", entity_id=str(student_id), metadata_json={"fields": changed, "role": actor.role}))
    await db.commit()
    await db.refresh(profile)
    return await read(db, student_id)


def summary(profile: dict) -> dict:
    """The student portal's Profile section rows (once the old JSON keys; now the table)."""
    ranked = sorted(profile["qualifications"], key=lambda q: -1 if q["level"] == "other" else list(LEVEL_LABELS).index(q["level"]))
    top = ranked[-1] if ranked else None
    highest = " — ".join(filter(None, (LEVEL_LABELS[top["level"]], top["qualification_name"]))) if top else None
    test = profile["english_tests"][0] if profile["english_tests"] else None
    english = None
    if test:
        english = " ".join(filter(None, (test["test_type"], test["overall_score"], f"({STATUS_LABELS[test['status']]})" if test["status"] else None)))
        english = f"{english} — {test['remarks']}" if test["remarks"] else english
    return {
        "Highest qualification": highest,
        "Preferred countries": ", ".join(c["name"] for c in profile["preferred_countries"]) or None,
        "Preferred intake": profile["preferred_intake"],
        "English test": english,
    }
