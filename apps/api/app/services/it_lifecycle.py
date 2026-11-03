"""itc-031 (DEC-SCOPE-358; backlog §itc-031, PDF §3 student lifecycle) -- one lifecycle stage per IT enrolment, derived from the source
records on every read so it can never disagree with them (AC3). Nothing stores the current stage.

Components (L2), each from its own record:
- fee       the itc-013 account: not billed -> enrolled, then fee_pending / partially_paid / paid
- training  seated (active/completed) and the effective start date reached (IST) -> training_active; an open itc-023 flag -> at_risk;
            status `completed` or an issued certificate for the enrolment -> completed
- placement only on the student's newest seated enrolment (HR review and applications are per student): an application `joined` ->
            placed; `interview`/`selected`, or HR `interview_ready`/`completed` -> interview; HR review stages -> hr_screening /
            resume_submitted
Display precedence (L3, Q-30): an ended enrolment or the override "closed" -> closed; placed; the override "not_placed"; then the furthest
track -- placement, training, fee. The components travel with the stage, so concurrent states (Training Active with Fee Pending) stay
visible. Only "not_placed" and "closed" are set by hand (L4), by the IT Admin, with a reason.

`sync` (L6) is the history writer the fee, enrolment, certificate, HR, application and risk writers call before their commit: it locks
the enrolment rows, derives, and appends a transition row when the stage differs from the last one. The itc-023 daily sweep ends with
`sync_all` (L7) for transitions no writer causes (a start date arriving). Derivation is a fixed number of queries for any list (`derive_many`).
"""

import logging
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Batch, Certificate, Enrollment, EnrollmentLifecycleHistory, HrReviewTask, JobApplication, Program, StudentRiskFlag, User
from app.schemas import IT_LIFECYCLE_STAGES, ItLifecycleOverrideIn
from app.services import fee_accounts
from app.services.audit_changes import audit_change

logger = logging.getLogger("app.it_lifecycle")

STAGES = IT_LIFECYCLE_STAGES
LABELS = {
    "enrolled": "Enrolled", "fee_pending": "Fee pending", "partially_paid": "Partially paid", "paid": "Paid", "training_active": "Training active",
    "at_risk": "At risk", "completed": "Completed", "resume_submitted": "Resume submitted", "hr_screening": "HR screening", "interview": "Interview",
    "placed": "Placed", "not_placed": "Not placed", "closed": "Closed",
}  # fmt: skip
SAFE = {"at_risk": "training_active"}  # L8: the student never sees "At risk"
OVERRIDABLE = ("not_placed", "closed")
ENDED = ("rejected", "withdrawn", "dropped")
SEATED = ("active", "completed")
FEE_STAGES = {"not_billed": "enrolled", "enrolled_pending_payment": "fee_pending", "partially_paid": "partially_paid", "fully_paid": "paid"}
HR_STAGES = {
    "resume_received": "resume_submitted", "under_review": "hr_screening", "changes_requested": "hr_screening", "screening": "hr_screening",
    "interview_ready": "interview", "completed": "interview",
}  # fmt: skip
APPLICATION_STAGES = {"joined": "placed", "selected": "interview", "interview": "interview"}
IST = ZoneInfo("Asia/Kolkata")
HISTORY_LIMIT = 50
CHUNK = 500
OVERRIDE_ACTION = "it.enrollment.lifecycle_override"
NOT_FOUND = "Enrolment not found"
PLACED_BY_JOINING = "Placed is set by a joining record, never by hand"
DERIVED_ONLY = "Only Not placed or Closed can be set by hand; every other stage is worked out from the records"
ALREADY_PLACED = "The student has a joining record, so the stage is Placed"


def view(stage: str, *, safe: bool = False) -> dict:
    stage = SAFE.get(stage, stage) if safe else stage
    return {"stage": stage, "stage_label": LABELS[stage]}


def _stage(status: str, override: str | None, c: dict) -> str:
    if status in ENDED or override == "closed":
        return "closed"
    if c["placement"] == "placed":
        return "placed"
    if override == "not_placed":
        return "not_placed"
    return c["placement"] or c["training"] or c["fee"]


async def _placement(db: AsyncSession, student_ids: set[UUID]) -> dict[UUID, str]:
    """Each student's placement component (absent = none): the furthest application, else the HR review stage."""
    out = {
        sid: HR_STAGES[stage]
        for sid, stage in (await db.execute(select(HrReviewTask.student_user_id, HrReviewTask.stage).where(HrReviewTask.student_user_id.in_(student_ids)))).all()
        if stage in HR_STAGES
    }
    applied = (await db.execute(select(JobApplication.student_id, JobApplication.status).where(JobApplication.student_id.in_(student_ids), JobApplication.status.in_(APPLICATION_STAGES)))).all()
    for sid, status in applied:
        if out.get(sid) != "placed":
            out[sid] = APPLICATION_STAGES[status]
    return out


async def derive_many(db: AsyncSession, enrollment_ids: list[UUID]) -> dict[UUID, dict]:
    """{enrolment id: {"stage", "components": {fee, training, placement}}} in seven queries, whatever the number of enrolments."""
    ids = list(dict.fromkeys(enrollment_ids))
    if not ids:
        return {}
    start = func.coalesce(Enrollment.start_date, Batch.start_date).label("start")
    stmt = select(Enrollment.id, Enrollment.student_id, Enrollment.status, Enrollment.lifecycle_override, start).join(Batch, Batch.id == Enrollment.batch_id)
    rows = (await db.execute(stmt.where(Enrollment.id.in_(ids)))).all()
    students = {r.student_id for r in rows}
    fees = await fee_accounts.balance_for(db, [r.id for r in rows])
    flagged = set((await db.scalars(select(StudentRiskFlag.enrollment_id).where(StudentRiskFlag.enrollment_id.in_(ids), StudentRiskFlag.cleared_at.is_(None)))).all())
    certified = set((await db.scalars(select(Certificate.enrollment_id).where(Certificate.enrollment_id.in_(ids), Certificate.status == "issued"))).all())
    newest = dict(
        (await db.execute(
            select(Enrollment.student_id, Enrollment.id).where(Enrollment.student_id.in_(students), Enrollment.status.in_(SEATED))
            .distinct(Enrollment.student_id).order_by(Enrollment.student_id, Enrollment.created_at.desc(), Enrollment.id.desc())
        )).all()
    )  # fmt: skip
    placement = await _placement(db, students) if newest else {}
    today = datetime.now(IST).date()
    out: dict[UUID, dict] = {}
    for r in rows:
        training = None
        if r.status == "completed" or r.id in certified:
            training = "completed"
        elif r.status in SEATED and r.start <= today:
            training = "at_risk" if r.id in flagged else "training_active"
        c = {"fee": FEE_STAGES[fees[r.id]["state"]], "training": training, "placement": placement.get(r.student_id) if newest.get(r.student_id) == r.id else None}
        out[r.id] = {"stage": _stage(r.status, r.lifecycle_override, c), "components": c}
    return out


# --- the history writer (L6, L7) --------------------------------------------------------------------------------------------------
async def sync(db: AsyncSession, enrollment_ids: list[UUID], *, actor: User | None, cause: str) -> int:
    """No commit. Appends a transition for every enrolment whose derived stage differs from its last history row (the first row has no
    `from_stage`). The enrolment rows are locked in id order, so two writers of one enrolment serialise and never both append."""
    ids = sorted(set(enrollment_ids))
    if not ids:
        return 0
    await db.execute(select(Enrollment.id).where(Enrollment.id.in_(ids)).order_by(Enrollment.id).with_for_update())
    current = await derive_many(db, ids)
    h = EnrollmentLifecycleHistory
    last = dict(
        (await db.execute(
            select(h.enrollment_id, h.to_stage).where(h.enrollment_id.in_(ids)).distinct(h.enrollment_id).order_by(h.enrollment_id, h.created_at.desc(), h.id.desc())
        )).all()
    )  # fmt: skip
    actor_id = actor.id if actor else None
    changed = [eid for eid in ids if eid in current and last.get(eid) != current[eid]["stage"]]
    for eid in changed:  # clock_timestamp: two transitions in one transaction still order correctly
        db.add(h(enrollment_id=eid, from_stage=last.get(eid), to_stage=current[eid]["stage"], cause=cause, actor_user_id=actor_id, created_at=func.clock_timestamp()))
    if changed:
        await db.flush()
        logger.info("it_lifecycle_changed", extra={"extra_fields": {"cause": cause, "actor_id": str(actor_id) if actor_id else None, "count": len(changed)}})
    return len(changed)


async def sync_students(db: AsyncSession, student_ids: list[UUID], *, actor: User | None, cause: str) -> int:
    """No commit. `sync` over every enrolment of these students (the HR review and applications are per student)."""
    ids = list((await db.scalars(select(Enrollment.id).where(Enrollment.student_id.in_(student_ids)))).all()) if student_ids else []
    return await sync(db, ids, actor=actor, cause=cause)


async def sync_all(db: AsyncSession, *, cause: str = "daily_check") -> int:
    """Commits per chunk. The daily catch-up over every enrolment, as the system."""
    total, after = 0, None
    while True:
        stmt = select(Enrollment.id).order_by(Enrollment.id).limit(CHUNK)
        ids = list((await db.scalars(stmt.where(Enrollment.id > after) if after else stmt)).all())
        if not ids:
            return total
        total += await sync(db, ids, actor=None, cause=cause)
        await db.commit()
        after = ids[-1]


# --- readers and the override -----------------------------------------------------------------------------------------------------
async def views_for(db: AsyncSession, enrollment_ids: list[UUID], *, safe: bool = False) -> dict[UUID, dict]:
    """{enrolment id: {stage, stage_label}} for enrolment payloads (`safe` for the student's own)."""
    return {eid: view(d["stage"], safe=safe) for eid, d in (await derive_many(db, enrollment_ids)).items()}


async def staff_lifecycle(db: AsyncSession, student: User) -> dict:
    """The 360's lifecycle card: every enrolment (newest first) with its stage, components, override and last 50 transitions."""
    rows = (
        await db.execute(
            select(Enrollment, Batch.name, Program.title).join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id)
            .where(Enrollment.student_id == student.id).order_by(Enrollment.created_at.desc(), Enrollment.id).execution_options(populate_existing=True)
        )
    ).all()  # fmt: skip
    ids = [e.id for e, _, _ in rows]
    derived = await derive_many(db, ids)
    history: dict[UUID, list] = {eid: [] for eid in ids}
    h = EnrollmentLifecycleHistory
    if ids:
        stmt = select(h, User.full_name).outerjoin(User, User.id == h.actor_user_id).where(h.enrollment_id.in_(ids)).order_by(h.created_at.desc(), h.id.desc())
        for row, actor in (await db.execute(stmt)).all():
            if len(history[row.enrollment_id]) < HISTORY_LIMIT:
                history[row.enrollment_id].append({
                    "from_stage": row.from_stage, "from_label": LABELS.get(row.from_stage) if row.from_stage else None, "to_stage": row.to_stage,
                    "to_label": LABELS.get(row.to_stage, row.to_stage), "cause": row.cause, "actor": actor, "created_at": row.created_at,
                })  # fmt: skip
    return {
        "enrollments": [
            {
                "enrollment_id": e.id, "enrollment_code": e.enrollment_code, "program": program, "batch": batch, **view(derived[e.id]["stage"]),
                "components": {k: view(v) if v else None for k, v in derived[e.id]["components"].items()},
                "override": {"stage": e.lifecycle_override, "stage_label": LABELS[e.lifecycle_override], "reason": e.lifecycle_override_reason} if e.lifecycle_override else None,
                "history": history[e.id],
            }
            for e, batch, program in rows
        ]
    }  # fmt: skip


async def set_override(db: AsyncSession, actor: User, student: User, enrollment_id: UUID, payload: ItLifecycleOverrideIn) -> dict:
    """Commits. 404 for an enrolment that is not this student's; 409 for any stage the records decide; the change is audited (before/after)
    and, when the stage moves, written to the history."""
    enrollment = await db.scalar(select(Enrollment).where(Enrollment.id == enrollment_id, Enrollment.student_id == student.id).with_for_update())
    if enrollment is None:
        raise HTTPException(404, NOT_FOUND)
    target = payload.stage
    if target == "placed":
        raise HTTPException(409, PLACED_BY_JOINING)
    if target is not None and target not in OVERRIDABLE:
        raise HTTPException(409, DERIVED_ONLY)
    if target == "not_placed" and (await derive_many(db, [enrollment.id]))[enrollment.id]["components"]["placement"] == "placed":
        raise HTTPException(409, ALREADY_PLACED)
    before = {"lifecycle_override": enrollment.lifecycle_override, "lifecycle_override_reason": enrollment.lifecycle_override_reason}
    after = {"lifecycle_override": target, "lifecycle_override_reason": payload.reason if target else None}
    enrollment.lifecycle_override, enrollment.lifecycle_override_reason = after["lifecycle_override"], after["lifecycle_override_reason"]
    audit_change(db, actor, OVERRIDE_ACTION, "enrollment", enrollment.id, before, after, metadata={"student_id": str(student.id)})
    await db.flush()
    await sync(db, [enrollment.id], actor=actor, cause="override")
    await db.commit()
    return await staff_lifecycle(db, student)
