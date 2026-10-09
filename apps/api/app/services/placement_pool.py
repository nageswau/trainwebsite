"""rec-010 (DEC-SCOPE-138, spec §3): an IT student opts in to -- or out of -- the placement candidate pool, and who employers see.

`candidates.opted_in` is the gate (R4): recruiter reads (services/candidates.pool_filter), EMP-003 and the EMP-004 shortlist all follow it.
Each change of it adds a `candidate_consents` row. Functions only; nothing here commits -- the route owns the transaction. Logs and audit
rows carry ids, never a name, email or phone."""

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, Batch, Candidate, CandidateConsent, CandidateSkill, Enrollment, PlacementProfile, Program, User
from app.services import candidates
from app.services import skills as skills_master
from app.services.applications import candidate_for_student
from app.services.candidate_skills import MAX_SKILLS

logger = logging.getLogger("app.placement_pool")

# OI2: the wording the student agrees to. A new wording gets a new version, so every consent row names the text it was given against.
CONSENT_VERSION = "v1"
CONSENT_TEXT = (
    "I agree that EduSphere may add my name, email, phone, course and skills to its placement candidate pool. EduSphere recruiters may "
    "contact me about jobs, and registered employers may see my name, course, skills and availability, never my email or phone. I can "
    "leave the pool at any time; my existing job applications continue."
)
HISTORY_LIMIT = 20
SEED_LEVEL = "beginner"  # OI3: the student's own claim; a recruiter adjusts it


def require_student(user: User) -> None:
    """OI1: any active IT student (an inactive account never authenticates)."""
    if user.role != "it_student" or user.division != "it":
        raise HTTPException(403, "Only IT students can join the placement candidate pool")


def employer_visible() -> list:
    """OI4: what EMP-003 lists and EMP-004 may shortlist -- an opted-in, non-archived candidate of an active IT student whose
    PlacementProfile is missing or not withdrawn (ADM-007-AC02). The caller joins User on Candidate.user_id and outer-joins PlacementProfile."""
    return [
        Candidate.opted_in.is_(True),
        Candidate.archived_at.is_(None),
        User.role == "it_student",
        User.division == "it",
        User.active.is_(True),
        or_(PlacementProfile.id.is_(None), PlacementProfile.withdrawn.is_(False)),
    ]


async def latest_courses(db: AsyncSession, student_ids: list[UUID]) -> dict[UUID, str]:
    """{student id: the program title of their newest enrolment}."""
    if not student_ids:
        return {}
    rows = await db.execute(
        select(Enrollment.student_id, Program.title)
        .join(Batch, Batch.id == Enrollment.batch_id)
        .join(Program, Program.id == Batch.program_id)
        .where(Enrollment.student_id.in_(student_ids))
        .order_by(Enrollment.student_id, Enrollment.created_at.desc())
    )
    courses: dict[UUID, str] = {}
    for student_id, title in rows:
        courses.setdefault(student_id, title)
    return courses


async def _history(db: AsyncSession, candidate: Candidate | None) -> list[CandidateConsent]:
    if candidate is None:
        return []
    stmt = select(CandidateConsent).where(CandidateConsent.candidate_id == candidate.id)
    return list((await db.scalars(stmt.order_by(CandidateConsent.created_at.desc(), CandidateConsent.id.desc()).limit(HISTORY_LIMIT))).all())


async def state(db: AsyncSession, user: User) -> dict:
    """What the student's card shows. Reading creates nothing."""
    candidate = await db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    return {
        "opted_in": bool(candidate and candidate.opted_in),
        "consent": {"version": CONSENT_VERSION, "text": CONSENT_TEXT},
        "history": [{"action": c.action, "consent_version": c.consent_version, "created_at": c.created_at} for c in await _history(db, candidate)],
    }


async def _lock(db: AsyncSession, user: User) -> None:
    """The student's own row FOR UPDATE: two clicks or two tabs run one after the other, so candidate_for_student never races itself."""
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())


async def _seed(db: AsyncSession, user: User, candidate: Candidate) -> int:
    """OI3: fill what is empty -- never overwrite a recruiter's value. The course becomes the source detail; each profile skill the Skills
    Master knows (name or alias, active) becomes a claimed skill. Returns how many skills were added."""
    if not candidate.source_detail:
        course = (await latest_courses(db, [user.id])).get(user.id)
        candidate.source_detail = course[:200] if course else None
    mobile_key, email_key = candidates.keys(user.phone, user.email)
    if candidate.email is None and email_key and not await candidates.find_matches(db, None, email_key, exclude_id=candidate.id):
        candidate.email = user.email
    if candidate.mobile_normalized is None and mobile_key and not await candidates.find_matches(db, mobile_key, None, exclude_id=candidate.id):
        candidate.mobile, candidate.mobile_normalized = user.phone, mobile_key
    have = set((await db.scalars(select(CandidateSkill.skill_id).where(CandidateSkill.candidate_id == candidate.id))).all())
    added = 0
    for text in (user.profile or {}).get("skills", []):
        skill = await skills_master.resolve(db, text) if isinstance(text, str) else None
        if skill is None or skill.id in have or len(have) >= MAX_SKILLS:
            continue
        db.add(CandidateSkill(candidate_id=candidate.id, skill_id=skill.id, level=SEED_LEVEL, added_by_user_id=user.id))
        have.add(skill.id)
        added += 1
    return added


def _record(db: AsyncSession, user: User, candidate: Candidate, action: str, ip: str | None, metadata: dict) -> None:
    db.add(CandidateConsent(candidate_id=candidate.id, user_id=user.id, action=action, consent_version=CONSENT_VERSION, ip_address=ip))
    db.add(AuditLog(user_id=user.id, action=f"placement_pool.{action}", entity_type="candidates", entity_id=str(candidate.id), metadata_json=metadata))
    logger.info("placement_pool.%s user=%s candidate=%s", action, user.id, candidate.id)


async def opt_in(db: AsyncSession, user: User, version: str, ip: str | None) -> None:
    if version != CONSENT_VERSION:
        raise HTTPException(409, "The consent wording has changed. Review it and try again.")
    await _lock(db, user)
    candidate = await candidate_for_student(db, user)
    latest = await _history(db, candidate)
    if candidate.opted_in and latest and latest[0].action == "opt_in":
        return  # already in, with the consent on record: a second click adds nothing
    candidate.opted_in = True
    added = await _seed(db, user, candidate)
    _record(db, user, candidate, "opt_in", ip, {"consent_version": CONSENT_VERSION, "skills_added": added})


async def opt_out(db: AsyncSession, user: User, ip: str | None) -> None:
    """Applications, interviews and offers are untouched; only pool search, matching and EMP-003 stop seeing the student."""
    await _lock(db, user)
    candidate = await db.scalar(select(Candidate).where(Candidate.user_id == user.id))
    if candidate is None or not candidate.opted_in:
        return
    candidate.opted_in = False
    _record(db, user, candidate, "opt_out", ip, {"consent_version": CONSENT_VERSION})
