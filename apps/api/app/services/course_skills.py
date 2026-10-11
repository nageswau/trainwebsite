"""rec-036 (DEC-SCOPE-176, spec §1-§3): IT training ↔ recruiter. A program's skill tags (CI1), the "Course completed" skills an opted-in
student gets for each program they hold an issued certificate of (CI2-CI6), and the candidate's §27 journey (CI7).

Functions only; nothing here commits -- the route owns the transaction. Audit rows and logs carry ids, never a name."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.lookups import _pattern as like_pattern
from app.models import (
    AuditLog,
    Batch,
    Candidate,
    CandidateConsent,
    CandidateSkill,
    Certificate,
    Company,
    Enquiry,
    Enrollment,
    Job,
    JobApplication,
    JobOffer,
    Program,
    ProgramSkill,
    Skill,
    SkillAlias,
    SkillCategory,
    User,
)
from app.services.candidate_skills import MAX_SKILLS

logger = logging.getLogger("app.course_skills")

EDITORS = frozenset({"it_admin", "super_admin"})  # CI1
MAX_PROGRAM_SKILLS = 30
OPTION_LIMIT = 20
SOURCE = "course_completed"
LEVEL = "beginner"  # CI4: a recruiter adjusts it


def require_editor(user: User) -> None:
    if user.role not in EDITORS:
        raise HTTPException(403, "IT administrator required")


# --- program skill tags (CI1) ------------------------------------------------------------------------------------------------------
async def program_for_update(db: AsyncSession, program_id: UUID) -> Program:
    """Locked, so two saves of one program's tags run one after the other (the primary key never races)."""
    program = await db.scalar(select(Program).where(Program.id == program_id).with_for_update())
    if program is None:
        raise HTTPException(404, "Program not found")
    return program


async def program_skills_out(db: AsyncSession, program_id: UUID) -> list[dict]:
    rows = await db.execute(
        select(Skill, SkillCategory.name)
        .join(ProgramSkill, ProgramSkill.skill_id == Skill.id)
        .join(SkillCategory, SkillCategory.id == Skill.category_id)
        .where(ProgramSkill.program_id == program_id)
        .order_by(func.lower(Skill.name), Skill.id)
    )
    return [{"id": skill.id, "name": skill.name, "active": skill.active, "category": category} for skill, category in rows]


async def set_program_skills(db: AsyncSession, user: User, program: Program, skill_ids: list[UUID]) -> list[UUID]:
    """Replace the program's tags with `skill_ids` (repeats ignored). Every skill must be an active Skills Master skill, read FOR SHARE so
    a concurrent merge or deactivation waits for this commit. Returns the newly added skill ids."""
    wanted = list(dict.fromkeys(skill_ids))
    if len(wanted) > MAX_PROGRAM_SKILLS:
        raise HTTPException(422, f"A program can have at most {MAX_PROGRAM_SKILLS} skills")
    found = set((await db.scalars(select(Skill.id).where(Skill.id.in_(wanted), Skill.active.is_(True)).with_for_update(read=True))).all()) if wanted else set()
    if len(found) != len(wanted):
        raise HTTPException(422, "Pick active skills from the Skills Master")
    current = set((await db.scalars(select(ProgramSkill.skill_id).where(ProgramSkill.program_id == program.id))).all())
    added = [s for s in wanted if s not in current]
    removed = sorted(current - set(wanted), key=str)
    if removed:
        await db.execute(delete(ProgramSkill).where(ProgramSkill.program_id == program.id, ProgramSkill.skill_id.in_(removed)))
    db.add_all(ProgramSkill(program_id=program.id, skill_id=s, added_by_user_id=user.id) for s in added)
    db.add(
        AuditLog(
            user_id=user.id,
            action="program.skills_update",
            entity_type="program",
            entity_id=str(program.id),
            metadata_json={"added": [str(s) for s in added], "removed": [str(s) for s in removed]},
        )
    )
    await db.flush()
    return added


async def skill_options(db: AsyncSession, q: str | None) -> list[dict]:
    """The tag editor's picker: active skills by name or alias. it_admin is not a Skills Master reader (Q-28), so this lists names only."""
    stmt = select(Skill, SkillCategory.name).join(SkillCategory, SkillCategory.id == Skill.category_id).where(Skill.active.is_(True))
    pattern = like_pattern(q)
    if pattern:
        alias_hit = select(SkillAlias.id).where(SkillAlias.skill_id == Skill.id, SkillAlias.alias.ilike(pattern, escape="\\")).exists()
        stmt = stmt.where(or_(Skill.name.ilike(pattern, escape="\\"), alias_hit))
    rows = await db.execute(stmt.order_by(func.lower(Skill.name), Skill.id).limit(OPTION_LIMIT))
    return [{"id": skill.id, "name": skill.name, "category": category} for skill, category in rows]


# --- course-completed skills (CI2-CI6) ---------------------------------------------------------------------------------------------
async def grant(db: AsyncSession, actor: User, *, student_id: UUID | None = None, program_id: UUID | None = None, skill_ids: list[UUID] | None = None) -> int:
    """Give opted-in, non-archived candidates the tagged skills of every program they hold an issued certificate of -- narrowed to one
    student, one program and/or some skills. The candidates are locked FOR UPDATE in id order first, so this serialises with rec-011's
    writes. A new row is `beginner`; a `claimed` row is upgraded (CI5); verified and assessed rows are kept. Returns candidates changed."""
    certified = select(Certificate.student_id).where(Certificate.status == "issued")
    if program_id is not None:
        certified = certified.where(Certificate.program_id == program_id)
    lock = select(Candidate.id).where(Candidate.opted_in.is_(True), Candidate.archived_at.is_(None), Candidate.user_id.in_(certified))
    if student_id is not None:
        lock = lock.where(Candidate.user_id == student_id)
    candidate_ids = list((await db.scalars(lock.order_by(Candidate.id).with_for_update())).all())
    if not candidate_ids:
        return 0
    pairs = (
        select(Candidate.id, ProgramSkill.skill_id, Certificate.approved_by_id)
        .join(Certificate, Certificate.student_id == Candidate.user_id)
        .join(ProgramSkill, ProgramSkill.program_id == Certificate.program_id)
        .join(Skill, Skill.id == ProgramSkill.skill_id)
        .where(Candidate.id.in_(candidate_ids), Certificate.status == "issued", Skill.active.is_(True))
        .order_by(Certificate.issued_on.desc())
    )
    if program_id is not None:
        pairs = pairs.where(Certificate.program_id == program_id)
    if skill_ids is not None:
        pairs = pairs.where(ProgramSkill.skill_id.in_(skill_ids))
    approvers: dict[tuple[UUID, UUID], UUID | None] = {}
    for candidate_id, skill_id, approver_id in await db.execute(pairs):
        if approvers.get((candidate_id, skill_id)) is None:  # the newest certificate with an approver vouches (CI4)
            approvers[(candidate_id, skill_id)] = approver_id
    existing = {(r.candidate_id, r.skill_id): r for r in (await db.scalars(select(CandidateSkill).where(CandidateSkill.candidate_id.in_(candidate_ids)))).all()}
    counts = {c: 0 for c in candidate_ids}
    for candidate_id, _ in existing:
        counts[candidate_id] += 1
    now = datetime.now(UTC)
    changed: dict[UUID, list[str]] = {}
    for (candidate_id, skill_id), approver_id in approvers.items():
        row = existing.get((candidate_id, skill_id))
        status, verifier, verified_at = ("verified", approver_id, now) if approver_id else ("claimed", None, None)
        if row is None:
            if counts[candidate_id] >= MAX_SKILLS:
                continue
            counts[candidate_id] += 1
            db.add(
                CandidateSkill(
                    candidate_id=candidate_id, skill_id=skill_id, level=LEVEL, source=SOURCE, status=status, verified_by_user_id=verifier, verified_at=verified_at, added_by_user_id=actor.id
                )
            )
        elif row.status == "claimed" and (row.source != SOURCE or approver_id is not None):
            row.source, row.status, row.verified_by_user_id, row.verified_at = SOURCE, status, verifier, verified_at
            row.updated_by_user_id = actor.id
        else:
            continue
        changed.setdefault(candidate_id, []).append(str(skill_id))
    for candidate_id, granted in changed.items():
        db.add(
            AuditLog(
                user_id=actor.id,
                action="candidate.skill_course_grant",
                entity_type="candidates",
                entity_id=str(candidate_id),
                metadata_json={"skill_ids": sorted(granted), "program_id": str(program_id) if program_id else None},
            )
        )
    if changed:
        await db.flush()
        logger.info("course_skills_granted", extra={"extra_fields": {"actor_id": str(actor.id), "candidates": len(changed), "program_id": str(program_id) if program_id else None}})
    return len(changed)


# --- journey (CI7) -----------------------------------------------------------------------------------------------------------------
async def journey(db: AsyncSession, candidate: Candidate) -> dict:
    """EVID-018 §27: lead → IT student → trained → recruiter candidate → placed, each with its dates. Only ids, codes, titles and dates of
    the lead and the training are returned -- never the lead's phone, email or messages."""
    lead, enrolments, certificates = None, [], []
    if candidate.user_id is not None:
        row = (await db.execute(select(Enquiry.lead_code, Enquiry.source, Enquiry.created_at, Enquiry.converted_at).where(Enquiry.converted_user_id == candidate.user_id))).first()
        lead = dict(row._mapping) if row else None
        enrolments = [
            dict(r._mapping)
            for r in await db.execute(
                select(Program.title.label("program"), Batch.name.label("batch"), Enrollment.enrolled_on, Enrollment.status)
                .join(Batch, Batch.id == Enrollment.batch_id)
                .join(Program, Program.id == Batch.program_id)
                .where(Enrollment.student_id == candidate.user_id)
                .order_by(Enrollment.enrolled_on, Enrollment.id)
            )
        ]
        certificates = [
            dict(r._mapping)
            for r in await db.execute(
                select(Program.title.label("program"), Certificate.certificate_no, Certificate.issued_on)
                .join(Program, Program.id == Certificate.program_id)
                .where(Certificate.student_id == candidate.user_id, Certificate.status == "issued")
                .order_by(Certificate.issued_on, Certificate.id)
            )
        ]
    opted_in_at = await db.scalar(select(func.max(CandidateConsent.created_at)).where(CandidateConsent.candidate_id == candidate.id, CandidateConsent.action == "opt_in"))
    count, first_at = (await db.execute(select(func.count(JobApplication.id), func.min(JobApplication.created_at)).where(JobApplication.candidate_id == candidate.id))).one()
    placements = [
        {"company": company, "position": position, "joined_on": joined_on}
        for company, position, joined_on in await db.execute(
            select(Company.name, JobOffer.position, JobOffer.actual_joining_date)
            .join(JobApplication, JobApplication.id == JobOffer.application_id)
            .join(Job, Job.id == JobApplication.job_id)
            .join(Company, Company.id == Job.company_id)
            .where(JobApplication.candidate_id == candidate.id, JobOffer.joining_status == "joined")
            .order_by(JobOffer.actual_joining_date, JobOffer.id)
        )
    ]
    return {
        "lead": lead,
        "enrolments": enrolments,
        "certificates": certificates,
        "candidate": {"added_at": candidate.created_at, "opted_in_at": opted_in_at},
        "applications": {"count": count, "first_at": first_at},
        "placements": placements,
    }
