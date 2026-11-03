"""itc-027 (DEC-SCOPE-354; backlog §itc-027, source §5 steps 2-6): the HR resume-review task of an IT student.

- Opening (H2): a resume version shared with HR (itc-026 `visibility='hr'`) of a student in the nehn-017 HR population creates the
  student's one task, or updates its version; a closed task re-opens at `resume_received`, and so does `changes_requested` (the student
  acted). It runs inside the upload's transaction, which already holds the student's user row lock, so two uploads serialise.
- Owner (H3): whenever a shared upload finds no active owner -- the programme rule of the student's newest active enrolment, else the
  active HR user whose last assignment is oldest (round-robin without a cursor), else nobody (the IT Admin assigns).
- Work (H1/H6): only the owner (404 for anyone else, H4) saves stage and fields; a stage change writes history; every save writes one
  itc-001 audit row (notes as "changed"); a closed task takes no save (409) until it re-opens.
- Audiences (H7): `_full` (owner, IT Admin), `_staff` (linked counselor, IT Admin's student record: no notes, preferences or checklist)
  and `_student` (the safe label only).
- Notices (H8) are itc-002's fixed, preview-safe events. Logs carry ids only.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import HR_REVIEW_OPEN_STAGES, Batch, Enrollment, HrAssignmentRule, HrReviewStageHistory, HrReviewTask, ItStudentCounselor, Program, User
from app.notifications.events import notify
from app.schemas import HR_REVIEW_CHECKLIST, HrReviewPatch
from app.services import hr_students
from app.services import it_student_profiles as profiles
from app.services.audit_changes import audit_change

logger = logging.getLogger("app.hr_reviews")

CLOSED = ("completed", "withdrawn")
STAGE_LABELS = {
    "resume_received": "Resume received", "under_review": "Under review", "changes_requested": "Changes requested",
    "screening": "Screening", "interview_ready": "Interview ready", "completed": "Completed", "withdrawn": "Withdrawn",
}  # fmt: skip
SAFE_LABELS = {
    "resume_received": "Resume received", "under_review": "Under review", "changes_requested": "Action required: update your resume",
    "screening": "Screening scheduled", "interview_ready": "Ready for interviews", "completed": "Review complete", "withdrawn": "Review closed",
}  # fmt: skip
STUDENT_ACTIONS = {"changes_requested": "Upload an updated resume on your Profile page; HR reviews the new version."}
NEXT_ACTIONS = {
    "resume_received": "HR to start the review", "under_review": "HR is reviewing the resume",
    "changes_requested": "Student to upload an updated resume", "screening": "HR screening call", "interview_ready": "Schedule interviews",
    "completed": "No action: review complete", "withdrawn": "No action: withdrawn from placement",
}  # fmt: skip
FIELDS = ("stage", "screening_date", "role_preferences", "skill_gap_notes", "checklist")
HR_ONLY = "Only HR can work resume reviews"
ADMIN_ONLY = "Only the IT Admin can manage HR reviews"
STUDENTS_ONLY = "Only an IT student has a resume review"
NOT_FOUND = "Review task not found"
CLOSED_MESSAGE = "This review is closed. A new resume version shared with HR re-opens it."
CHOOSE_HR = "Choose an active HR user"
HISTORY_LIMIT = 50
OWNER = aliased(User)  # a task's HR owner, beside the student in list queries


# --- gates -----------------------------------------------------------------------------------------------------------------------
def require_hr(user: User) -> None:
    if (user.role, user.division) != ("hr_team", "it"):
        raise HTTPException(403, HR_ONLY)


def require_admin(user: User) -> None:
    if (user.role, user.division) != ("it_admin", "it"):
        raise HTTPException(403, ADMIN_ONLY)


def _active_hr() -> list:
    return [User.role == "hr_team", User.division == "it", User.active.is_(True)]


async def _hr_user(db: AsyncSession, user_id: UUID) -> User:
    hr = await db.scalar(select(User).where(User.id == user_id, *_active_hr()))
    if hr is None:
        raise HTTPException(422, CHOOSE_HR)
    return hr


# --- opening and assignment ------------------------------------------------------------------------------------------------------
async def _pick_owner(db: AsyncSession, student_id: UUID) -> User | None:
    ruled = (
        select(User).join(HrAssignmentRule, HrAssignmentRule.hr_user_id == User.id).join(Batch, Batch.program_id == HrAssignmentRule.program_id)
        .join(Enrollment, and_(Enrollment.batch_id == Batch.id, Enrollment.student_id == student_id, Enrollment.status == "active"))
        .where(*_active_hr()).order_by(Enrollment.created_at.desc(), Enrollment.id).limit(1)
    )  # fmt: skip
    if owner := await db.scalar(ruled):
        return owner
    last = select(HrReviewTask.owner_user_id, func.max(HrReviewTask.assigned_at).label("at")).group_by(HrReviewTask.owner_user_id).subquery()
    return await db.scalar(select(User).outerjoin(last, last.c.owner_user_id == User.id).where(*_active_hr()).order_by(last.c.at.asc().nulls_first(), User.id).limit(1))


def _move(db: AsyncSession, task: HrReviewTask, stage: str, actor: User | None, reason: str, now: datetime, *, first: bool = False) -> None:
    db.add(HrReviewStageHistory(task_id=task.id, from_stage=None if first else task.stage, to_stage=stage, actor_user_id=actor.id if actor else None, reason=reason))
    task.stage, task.closed_at = stage, now if stage in CLOSED else None


async def _counselor(db: AsyncSession, student_id: UUID) -> User | None:
    return await db.scalar(select(User).join(ItStudentCounselor, ItStudentCounselor.counselor_user_id == User.id).where(ItStudentCounselor.student_user_id == student_id))


async def on_resume_shared(db: AsyncSession, actor: User, student: User, resume_id: UUID, version: int) -> None:
    """Called by itc-026's upload, before its commit, for an `hr` version. No commit here."""
    if await db.scalar(select(User.id).where(User.id == student.id, User.id.in_(hr_students.population()))) is None:
        return  # outside the HR population (withdrawn from placement): HR can't open the student, so no task
    now = datetime.now(UTC)
    task = await db.scalar(select(HrReviewTask).where(HrReviewTask.student_user_id == student.id).with_for_update())
    if task is None:
        task = HrReviewTask(student_user_id=student.id, stage="resume_received", resume_version=version, checklist=[])
        db.add(task)
        await db.flush()
        _move(db, task, "resume_received", None, "upload", now, first=True)
    else:
        task.resume_version = version
        if task.stage in (*CLOSED, "changes_requested"):
            _move(db, task, "resume_received", None, "upload", now)
    owner = await db.get(User, task.owner_user_id) if task.owner_user_id else None
    if owner is None or not owner.active:
        owner = await _pick_owner(db, student.id)
        task.owner_user_id, task.assigned_at = (owner.id, now) if owner else (None, None)
    await db.flush()
    counselor = await _counselor(db, student.id)
    await notify(db, [owner], "it.resume.uploaded", resume_id, action_url=f"/it/hr/students/{student.id}")
    await notify(db, [counselor if counselor and counselor.id != actor.id else None], "it.resume.uploaded", resume_id, action_url=f"/it/counselor/students/{student.id}/profile")
    logger.info("hr_review_opened", extra={"extra_fields": {"task_id": str(task.id), "student_id": str(student.id), "owner_id": str(owner.id) if owner else None, "version": version}})


async def close_for_withdrawal(db: AsyncSession, student_id: UUID) -> None:
    """H9: the student left placement (rec-010 opt-out, or the placement profile marked withdrawn). No commit, no notice."""
    task = await db.scalar(select(HrReviewTask).where(HrReviewTask.student_user_id == student_id, HrReviewTask.stage.in_(HR_REVIEW_OPEN_STAGES)).with_for_update())
    if task is not None:
        _move(db, task, "withdrawn", None, "withdrawn", datetime.now(UTC))
        logger.info("hr_review_withdrawn", extra={"extra_fields": {"task_id": str(task.id)}})


# --- serializers (one per audience) ----------------------------------------------------------------------------------------------
def _person(user: User | None, *, active: bool = False) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "full_name": user.full_name, **({"active": user.active} if active else {})}


def _summary(task: HrReviewTask, student: User, owner: User | None) -> dict:
    return {
        "id": task.id, "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code},
        "owner": _person(owner, active=True), "stage": task.stage, "stage_label": STAGE_LABELS[task.stage], "resume_version": task.resume_version,
        "screening_date": task.screening_date, "assigned_at": task.assigned_at, "closed_at": task.closed_at, "updated_at": task.updated_at,
    }  # fmt: skip


async def _full(db: AsyncSession, task: HrReviewTask) -> dict:
    student, owner = await db.get_one(User, task.student_user_id), await db.get(User, task.owner_user_id) if task.owner_user_id else None
    actor = aliased(User)
    rows = await db.execute(
        select(HrReviewStageHistory, actor.full_name).outerjoin(actor, actor.id == HrReviewStageHistory.actor_user_id)
        .where(HrReviewStageHistory.task_id == task.id).order_by(HrReviewStageHistory.created_at.desc(), HrReviewStageHistory.id).limit(HISTORY_LIMIT)
    )  # fmt: skip
    history = [{"from_stage": h.from_stage, "to_stage": h.to_stage, "reason": h.reason, "actor": name, "created_at": h.created_at} for h, name in rows.all()]
    return {**_summary(task, student, owner), "role_preferences": task.role_preferences, "skill_gap_notes": task.skill_gap_notes, "checklist": task.checklist, "history": history}


def _staff(task: HrReviewTask, owner: User | None) -> dict:
    return {
        "stage": task.stage, "stage_label": STAGE_LABELS[task.stage], "owner": {"full_name": owner.full_name} if owner else None,
        "next_action": NEXT_ACTIONS[task.stage], "screening_date": task.screening_date, "resume_version": task.resume_version,
        "closed": task.closed_at is not None, "updated_at": task.updated_at,
    }  # fmt: skip


# --- HR: the owner's queue and work ----------------------------------------------------------------------------------------------
def _listing(stage: str | None) -> Select:
    stmt = select(HrReviewTask, User, OWNER).join(User, User.id == HrReviewTask.student_user_id).outerjoin(OWNER, OWNER.id == HrReviewTask.owner_user_id)
    return stmt.where(HrReviewTask.stage == stage) if stage else stmt.where(HrReviewTask.stage.in_(HR_REVIEW_OPEN_STAGES))


async def _page(db: AsyncSession, stmt: Select, limit: int, offset: int) -> dict:
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await db.execute(stmt.order_by(HrReviewTask.updated_at.desc(), HrReviewTask.id).limit(limit).offset(offset))).tuples().all()
    items = [_summary(task, student, owner) for task, student, owner in rows]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


async def queue(db: AsyncSession, hr: User, stage: str | None, limit: int, offset: int) -> dict:
    require_hr(hr)
    mine = HrReviewTask.owner_user_id == hr.id
    counts = dict((await db.execute(select(HrReviewTask.stage, func.count()).where(mine).group_by(HrReviewTask.stage))).all())
    page = await _page(db, _listing(stage).where(mine), limit, offset)
    return {**page, "counts": {s: counts.get(s, 0) for s in STAGE_LABELS}}


async def _owned(db: AsyncSession, hr: User, student_id: UUID, *, lock: bool = False) -> HrReviewTask:
    require_hr(hr)
    stmt = select(HrReviewTask).where(HrReviewTask.student_user_id == student_id, HrReviewTask.owner_user_id == hr.id)
    task = await db.scalar(stmt.with_for_update() if lock else stmt)
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    return task


async def read(db: AsyncSession, hr: User, student_id: UUID) -> dict:
    return await _full(db, await _owned(db, hr, student_id))


async def save(db: AsyncSession, hr: User, student_id: UUID, payload: HrReviewPatch) -> dict:
    task = await _owned(db, hr, student_id, lock=True)
    if task.closed_at is not None:
        raise HTTPException(409, CLOSED_MESSAGE)
    sent = payload.model_dump(exclude_unset=True)
    if "checklist" in sent:
        sent["checklist"] = [key for key in HR_REVIEW_CHECKLIST if key in sent["checklist"]]  # catalogue order, no repeats
    for key in ("role_preferences", "skill_gap_notes"):
        if key in sent and not sent[key]:
            sent[key] = None
    before = {field: getattr(task, field) for field in FIELDS}
    stage = sent.pop("stage", task.stage)
    moved = stage != task.stage
    if moved:
        _move(db, task, stage, hr, "manual", datetime.now(UTC))
    for field, value in sent.items():
        setattr(task, field, value)
    task.updated_by_user_id = hr.id
    audit_change(db, hr, "it.hr_review.update", "hr_review_task", task.id, before, {field: getattr(task, field) for field in FIELDS})
    if moved:
        student = await db.get_one(User, task.student_user_id)
        await notify(db, [student], "it.placement.updated", student.id, action_url="/it/student/placement-status")
        await notify(db, [await _counselor(db, student.id)], "it.hr_review.updated", task.id, action_url=f"/it/counselor/students/{student.id}/profile")
    await db.commit()
    await db.refresh(task)
    logger.info("hr_review_saved", extra={"extra_fields": {"task_id": str(task.id), "actor_id": str(hr.id), "stage": task.stage, "moved": moved}})
    return await _full(db, task)


# --- the IT Admin: every task, reassignment, rules -------------------------------------------------------------------------------
async def admin_tasks(db: AsyncSession, admin: User, stage: str | None, unassigned: bool, limit: int, offset: int) -> dict:
    require_admin(admin)
    stmt = _listing(stage)
    if unassigned:  # no owner, or one who was deactivated (the edge case: reassign their open tasks)
        stmt = stmt.where(or_(HrReviewTask.owner_user_id.is_(None), OWNER.active.is_(False)))
    return await _page(db, stmt, limit, offset)


async def assign(db: AsyncSession, admin: User, task_id: UUID, hr_user_id: UUID) -> dict:
    require_admin(admin)
    task = await db.get(HrReviewTask, task_id, with_for_update=True)
    if task is None:
        raise HTTPException(404, NOT_FOUND)
    hr = await _hr_user(db, hr_user_id)
    if task.owner_user_id != hr.id:
        audit_change(db, admin, "it.hr_review.assign", "hr_review_task", task.id, {"owner_user_id": task.owner_user_id}, {"owner_user_id": hr.id})
        task.owner_user_id, task.assigned_at, task.updated_by_user_id = hr.id, datetime.now(UTC), admin.id
        await notify(db, [hr], "it.hr_review.assigned", task.id, action_url=f"/it/hr/students/{task.student_user_id}")
        await db.commit()
        await db.refresh(task)
    return _summary(task, await db.get_one(User, task.student_user_id), hr)


async def rules(db: AsyncSession, admin: User) -> dict:
    require_admin(admin)
    rows = await db.execute(
        select(Program, User).outerjoin(HrAssignmentRule, HrAssignmentRule.program_id == Program.id).outerjoin(User, User.id == HrAssignmentRule.hr_user_id)
        .order_by(Program.title, Program.id)
    )  # fmt: skip
    hr_users = await db.scalars(select(User).where(*_active_hr()).order_by(User.full_name, User.id))
    return {
        "programs": [_rule_out(program, hr) for program, hr in rows.all()],
        "hr_users": [_person(u) for u in hr_users],
    }


def _rule_out(program: Program, hr: User | None) -> dict:
    return {"program_id": program.id, "program": program.title, "active": program.active, "hr_user": _person(hr, active=True)}


async def save_rule(db: AsyncSession, admin: User, program_id: UUID, hr_user_id: UUID | None) -> dict:
    require_admin(admin)
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(404, "Programme not found")
    hr = await _hr_user(db, hr_user_id) if hr_user_id else None
    row = await db.get(HrAssignmentRule, program_id, with_for_update=True)
    before = {"hr_user_id": row.hr_user_id if row else None}
    if hr is None and row is not None:
        await db.delete(row)
    elif hr is not None:
        if row is None:
            row = HrAssignmentRule(program_id=program_id, hr_user_id=hr.id)
            db.add(row)
        row.hr_user_id, row.updated_by_user_id = hr.id, admin.id
    audit_change(db, admin, "it.hr_review.rule_update", "program", program_id, before, {"hr_user_id": hr.id if hr else None})
    await db.commit()
    return _rule_out(program, hr)


# --- read-only views: counselor / IT Admin student record, and the student ------------------------------------------------------
async def staff_view(db: AsyncSession, user: User, student_id: UUID, portal: str) -> dict:
    student = await profiles.staff_student(db, user, student_id, portal=portal)
    return await staff_task(db, student.id)


async def staff_task(db: AsyncSession, student_id: UUID) -> dict:
    """The `_staff` view of the student's task (`{"task": None}` when there is none); the caller has applied its own scope (itc-029)."""
    task = await db.scalar(select(HrReviewTask).where(HrReviewTask.student_user_id == student_id))
    if task is None:
        return {"task": None}
    return {"task": _staff(task, await db.get(User, task.owner_user_id) if task.owner_user_id else None)}


async def student_view(db: AsyncSession, user: User) -> dict:
    if (user.role, user.division) != ("it_student", "it"):
        raise HTTPException(403, STUDENTS_ONLY)
    task = await db.scalar(select(HrReviewTask).where(HrReviewTask.student_user_id == user.id))
    if task is None:
        return {"status": None}
    moved_at = await db.scalar(select(func.max(HrReviewStageHistory.created_at)).where(HrReviewStageHistory.task_id == task.id))
    return {"status": {"label": SAFE_LABELS[task.stage], "action": STUDENT_ACTIONS.get(task.stage), "updated_at": moved_at}}
