"""itc-022 (DEC-SCOPE-365; spec 2026-11-03-itc-022-modules-progress-remediation-design.md): programme modules/topics, per-student topic
completion, the computed progress %, its override, and remediation plans.

- Plans (P1/P2): the IT Admin saves a programme's whole plan; kept ids survive, missing ones go (their completions cascade).
- Formula (P3): weights per programme summing to 100; computed only with weights AND >= 1 topic, else progress stays manual. Components
  are topics done/total, assignments graded/published (labs included) and assessments passed/counted -- the nehn-010 figures certificates
  already use; a component with nothing in the batch drops out and the rest are re-weighted; half-up to a whole percent.
- Materialised (P4): `refresh` writes the result to `enrollments.progress_percent` for the batch's ACTIVE seats without an override, in the
  caller's transaction, so certificates, reports, KPIs, the portal and the 360 keep reading the one column.
- Remediation (P9): only for an active enrolment (AC3); the owner is the batch trainer, the student's itc-003 counselor or an IT Admin.

Logs and audit rows carry ids and counts only.
"""

import logging
from datetime import date, datetime
from fractions import Fraction
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Assignment,
    Batch,
    Enrollment,
    ItProgressFormula,
    ItStudentCounselor,
    Program,
    ProgramModule,
    ProgramTopic,
    RemediationPlan,
    StudentRiskFlag,
    Submission,
    TopicCompletion,
    User,
)
from app.schemas import ProgressPlanIn, RemediationPlanIn, RemediationPlanPatch, TopicCompletionIn
from app.services import it_at_risk, it_student_notes, training_progress
from app.services.audit_changes import audit_change

logger = logging.getLogger(__name__)
INDIA = ZoneInfo("Asia/Kolkata")
COMPONENTS = ("topics", "assignments", "assessments")
CLOSED = ("completed", "cancelled")
BATCH_STAFF = "Only the batch's trainer or the IT Admin can do this"
OUTSIDE_BATCH = "Batch is outside your assigned batches"
REASON_REQUIRED = "Give a reason for overriding the computed progress"
PLAN_NOT_FOUND, ENROLLMENT_NOT_FOUND, TOPIC_NOT_FOUND = "Remediation plan not found", "Enrollment not found", "Topic not found"


def _today() -> date:
    return datetime.now(INDIA).date()


def _is_admin(user: User) -> bool:
    return user.role == "super_admin" or (user.role == "it_admin" and user.division == "it")


def _require_staff(user: User) -> None:
    if not (_is_admin(user) or (user.role == "trainer" and user.division == "it")):
        raise HTTPException(403, BATCH_STAFF)


async def staff_batch(db: AsyncSession, user: User, batch_id: UUID) -> Batch:
    """The batch for its trainer or an IT Admin (the nehn-028 batch-progress rule: another trainer's batch is 403)."""
    _require_staff(user)
    batch = await db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(404, "Batch not found")
    if not _is_admin(user) and batch.trainer_id != user.id:
        raise HTTPException(403, OUTSIDE_BATCH)
    return batch


# --- the formula ---------------------------------------------------------------------------------------------------------------------
def formula(weights: dict[str, int], parts: dict[str, tuple[int, int]]) -> int | None:
    """P3: Σ wᵢ·doneᵢ/totalᵢ / Σ wᵢ over the weighted components with a total, as a half-up whole percent; None when none has one."""
    used = [(weights[key], Fraction(min(done, total), total)) for key, (done, total) in parts.items() if total > 0 and weights[key] > 0]
    weight = sum(w for w, _ in used)
    if not weight:
        return None
    value = sum(w * share for w, share in used) * 100 / weight
    return int(value + Fraction(1, 2))


async def _weights(db: AsyncSession, program_id: UUID) -> dict[str, int] | None:
    """The programme's weights when progress is computed (a formula AND >= 1 topic), else None (manual)."""
    row = await db.get(ItProgressFormula, program_id)
    if row is None:
        return None
    topics = await db.scalar(select(func.count(ProgramTopic.id)).join(ProgramModule, ProgramModule.id == ProgramTopic.module_id).where(ProgramModule.program_id == program_id))
    if not topics:
        return None
    return {"topics": row.topics_weight, "assignments": row.assignments_weight, "assessments": row.assessments_weight}


async def is_computed(db: AsyncSession, batch: Batch) -> bool:
    return await _weights(db, batch.program_id) is not None


async def components(db: AsyncSession, batch: Batch, enrollments: list[Enrollment], seats: dict[UUID, dict] | None = None) -> dict[UUID, dict]:
    """Per enrolment: topics/labs done and total, the nehn-010 seat figures, and `computed_percent` (None on a manual programme).
    Batched for the whole list: the five `seats` queries (or the caller's) plus four."""
    if not enrollments:
        return {}
    weights = await _weights(db, batch.program_id)
    seats = seats if seats is not None else await training_progress.seats(db, batch.id, [e.student_id for e in enrollments])
    topics_total = await db.scalar(select(func.count(ProgramTopic.id)).join(ProgramModule, ProgramModule.id == ProgramTopic.module_id).where(ProgramModule.program_id == batch.program_id)) or 0
    done = dict(
        (await db.execute(
            select(TopicCompletion.enrollment_id, func.count())
            .join(ProgramTopic, ProgramTopic.id == TopicCompletion.topic_id)
            .join(ProgramModule, ProgramModule.id == ProgramTopic.module_id)
            .where(ProgramModule.program_id == batch.program_id, TopicCompletion.enrollment_id.in_([e.id for e in enrollments]))
            .group_by(TopicCompletion.enrollment_id)
        )).all()
    )  # fmt: skip
    labs = select(Assignment.id).where(Assignment.batch_id == batch.id, Assignment.published.is_(True), Assignment.assignment_type == "lab")
    labs_total = await db.scalar(select(func.count()).select_from(labs.subquery())) or 0
    labs_graded = dict(
        (await db.execute(
            select(Submission.student_id, func.count()).where(Submission.assignment_id.in_(labs), Submission.status == "graded")
            .group_by(Submission.student_id)
        )).all()
    )  # fmt: skip
    result = {}
    for e in enrollments:
        seat = seats.get(e.student_id) or {"assignments_graded": 0, "assignments_total": 0, "assessments_passed": 0, "assessments_total": 0}
        parts = {
            "topics": (done.get(e.id, 0), topics_total),
            "assignments": (seat["assignments_graded"], seat["assignments_total"]),
            "assessments": (seat["assessments_passed"], seat["assessments_total"]),
        }
        result[e.id] = {
            "topics_completed": parts["topics"][0], "topics_total": topics_total,
            "labs_graded": labs_graded.get(e.student_id, 0), "labs_total": labs_total,
            "computed_percent": formula(weights, parts) if weights else None,
        }  # fmt: skip
    return result


async def refresh(db: AsyncSession, batch_id: UUID) -> int:
    """P4: write the computed % to the batch's active, non-overridden seats (no commit -- the caller's transaction). Returns rows changed."""
    batch = await db.get(Batch, batch_id)
    if batch is None or not await is_computed(db, batch):
        return 0
    seats = list(await db.scalars(select(Enrollment).where(Enrollment.batch_id == batch.id, Enrollment.status == "active", Enrollment.progress_override_reason.is_(None))))
    figures = await components(db, batch, seats)
    changed = 0
    for enrollment in seats:
        computed = figures[enrollment.id]["computed_percent"]
        if computed is not None and enrollment.progress_percent != computed:
            enrollment.progress_percent = computed
            changed += 1
    if changed:
        logger.info("it_progress_refreshed", extra={"extra_fields": {"batch_id": str(batch.id), "changed": changed}})
    return changed


async def _refresh_program(db: AsyncSession, program_id: UUID) -> None:
    for batch_id in await db.scalars(select(Batch.id).where(Batch.program_id == program_id)):
        await refresh(db, batch_id)


# --- plans (IT Admin) ----------------------------------------------------------------------------------------------------------------
def _weights_out(row: ItProgressFormula | None) -> dict | None:
    return {"topics": row.topics_weight, "assignments": row.assignments_weight, "assessments": row.assessments_weight} if row else None


async def _modules(db: AsyncSession, program_id: UUID) -> list[dict]:
    modules = list(await db.scalars(select(ProgramModule).where(ProgramModule.program_id == program_id).order_by(ProgramModule.position, ProgramModule.id)))
    topics = (
        await db.scalars(select(ProgramTopic).where(ProgramTopic.module_id.in_([m.id for m in modules])).order_by(ProgramTopic.position, ProgramTopic.id))
        if modules else []
    )  # fmt: skip
    by_module: dict[UUID, list[dict]] = {}
    for topic in topics:
        by_module.setdefault(topic.module_id, []).append({"id": topic.id, "title": topic.title})
    return [{"id": m.id, "title": m.title, "topics": by_module.get(m.id, [])} for m in modules]


def _copy_source(program: Program) -> list[dict]:
    """P1: what "Copy from syllabus" fills in -- the PUB-025 manual syllabus, else one module per curriculum line."""
    if program.syllabus_source == "manual" and program.syllabus_modules:
        return [{"title": m["title"], "topics": list(m.get("topics", []))} for m in program.syllabus_modules]
    return [{"title": str(line), "topics": []} for line in (program.curriculum or []) if str(line).strip()]


async def list_plans(db: AsyncSession) -> list[dict]:
    counts = (
        select(ProgramModule.program_id, func.count(func.distinct(ProgramModule.id)).label("modules"), func.count(ProgramTopic.id).label("topics"))
        .outerjoin(ProgramTopic, ProgramTopic.module_id == ProgramModule.id).group_by(ProgramModule.program_id).subquery()
    )  # fmt: skip
    rows = await db.execute(
        select(Program, ItProgressFormula, counts.c.modules, counts.c.topics)
        .outerjoin(ItProgressFormula, ItProgressFormula.program_id == Program.id).outerjoin(counts, counts.c.program_id == Program.id)
        .order_by(Program.title, Program.id)
    )  # fmt: skip
    return [
        {"program_id": p.id, "program": p.title, "active": p.active, "modules": modules or 0, "topics": topics or 0, "weights": _weights_out(f),
         "computed": bool(f and topics)}
        for p, f, modules, topics in rows.all()
    ]  # fmt: skip


async def read_plan(db: AsyncSession, program_id: UUID) -> dict:
    program = await db.get(Program, program_id)
    if program is None:
        raise HTTPException(404, it_at_risk.PROGRAM_NOT_FOUND)
    formula_row = await db.get(ItProgressFormula, program_id)
    modules = await _modules(db, program_id)
    return {
        "program_id": program.id, "program": program.title, "modules": modules, "weights": _weights_out(formula_row),
        "computed": bool(formula_row and any(m["topics"] for m in modules)), "copy_source": _copy_source(program),
    }  # fmt: skip


async def save_plan(db: AsyncSession, user: User, program_id: UUID, payload: ProgressPlanIn) -> dict:
    """P2: replace the plan in one transaction (the programme row is locked, so two saves serialise), then refresh its batches."""
    program = await db.get(Program, program_id, with_for_update=True)
    if program is None:
        raise HTTPException(404, it_at_risk.PROGRAM_NOT_FOUND)
    existing = await _modules(db, program_id)
    module_ids = {m["id"] for m in existing}
    topic_ids = {t["id"]: m["id"] for m in existing for t in m["topics"]}
    sent_modules = {m.id for m in payload.modules if m.id}
    sent_topics = {t.id for m in payload.modules for t in m.topics if t.id}
    if sent_modules - module_ids or sent_topics - set(topic_ids):
        raise HTTPException(422, "A module or topic does not belong to this programme; reload the plan and try again")
    before = {"modules": len(existing), "topics": len(topic_ids), "weights": _weights_out(await db.get(ItProgressFormula, program_id))}

    if gone := set(topic_ids) - sent_topics:
        await db.execute(delete(ProgramTopic).where(ProgramTopic.id.in_(gone)))
    if gone := module_ids - sent_modules:
        await db.execute(delete(ProgramModule).where(ProgramModule.id.in_(gone)))
    for m_pos, module_in in enumerate(payload.modules, start=1):
        module = await db.get(ProgramModule, module_in.id) if module_in.id else None
        if module is None:
            module = ProgramModule(program_id=program_id)
            db.add(module)
        module.title, module.position = module_in.title, m_pos
        await db.flush()
        for t_pos, topic_in in enumerate(module_in.topics, start=1):
            topic = await db.get(ProgramTopic, topic_in.id) if topic_in.id else None
            if topic is None:
                topic = ProgramTopic()
                db.add(topic)
            topic.module_id, topic.title, topic.position = module.id, topic_in.title, t_pos

    formula_row = await db.get(ItProgressFormula, program_id)
    if payload.weights is None:
        if formula_row is not None:
            await db.delete(formula_row)
    else:
        if formula_row is None:
            formula_row = ItProgressFormula(program_id=program_id)
            db.add(formula_row)
        formula_row.topics_weight, formula_row.assignments_weight, formula_row.assessments_weight = payload.weights.topics, payload.weights.assignments, payload.weights.assessments
        formula_row.updated_by_id = user.id
    await db.flush()
    after = {"modules": len(payload.modules), "topics": sum(len(m.topics) for m in payload.modules), "weights": payload.weights.model_dump() if payload.weights else None}
    audit_change(db, user, "it.progress_plan.update", "program", program_id, before, after)
    await _refresh_program(db, program_id)
    await db.commit()
    logger.info("it_progress_plan_saved", extra={"extra_fields": {"actor_id": str(user.id), "program_id": str(program_id), **{k: after[k] for k in ("modules", "topics")}}})
    return await read_plan(db, program_id)


# --- topic completion (trainer / IT Admin) -------------------------------------------------------------------------------------------
async def batch_topics(db: AsyncSession, user: User, batch_id: UUID) -> dict:
    batch = await staff_batch(db, user, batch_id)
    modules = await _modules(db, batch.program_id)
    rows = await db.execute(select(TopicCompletion.topic_id, TopicCompletion.enrollment_id).join(Enrollment, Enrollment.id == TopicCompletion.enrollment_id).where(Enrollment.batch_id == batch.id))
    completed: dict[UUID, list[UUID]] = {}
    for topic_id, enrollment_id in rows.all():
        completed.setdefault(topic_id, []).append(enrollment_id)
    for module in modules:
        for topic in module["topics"]:
            topic["completed_enrollment_ids"] = completed.get(topic["id"], [])
    return {"batch_id": batch.id, "computed": await is_computed(db, batch), "modules": modules}


async def set_completions(db: AsyncSession, user: User, batch_id: UUID, topic_id: UUID, payload: TopicCompletionIn) -> dict:
    """P6: mark or unmark one topic for many students of the batch at once; idempotent; one audit row; the batch's progress refreshed."""
    batch = await staff_batch(db, user, batch_id)
    topic = await db.scalar(select(ProgramTopic).join(ProgramModule, ProgramModule.id == ProgramTopic.module_id).where(ProgramTopic.id == topic_id, ProgramModule.program_id == batch.program_id))
    if topic is None:
        raise HTTPException(404, TOPIC_NOT_FOUND)
    wanted = set(payload.enrollment_ids)
    active = set(await db.scalars(select(Enrollment.id).where(Enrollment.id.in_(wanted), Enrollment.batch_id == batch.id, Enrollment.status == "active")))
    if missing := len(wanted - active):
        raise HTTPException(422, f"{missing} of the selected students {'is' if missing == 1 else 'are'} not an active student of this batch")
    if payload.completed:
        await db.execute(
            insert(TopicCompletion).values([{"topic_id": topic.id, "enrollment_id": e, "completed_by_id": user.id} for e in sorted(wanted)])
            .on_conflict_do_nothing(constraint="uq_topic_completions_topic_enrollment")
        )  # fmt: skip
    else:
        await db.execute(delete(TopicCompletion).where(TopicCompletion.topic_id == topic.id, TopicCompletion.enrollment_id.in_(wanted)))
    audit_change(db, user, "it.topic_completion.update", "program_topic", topic.id, {}, {"completed": payload.completed, "students": len(wanted)}, metadata={"batch_id": str(batch.id)})
    await refresh(db, batch.id)
    await db.commit()
    done = list(
        await db.scalars(
            select(TopicCompletion.enrollment_id).join(Enrollment, Enrollment.id == TopicCompletion.enrollment_id).where(TopicCompletion.topic_id == topic.id, Enrollment.batch_id == batch.id)
        )
    )
    return {"topic_id": topic.id, "completed_enrollment_ids": done}


# --- the override (P5) ---------------------------------------------------------------------------------------------------------------
async def override(db: AsyncSession, user: User, enrollment: Enrollment, batch: Batch, percent: int, reason: str | None) -> None:
    """On a computed programme: the trainer's figure sticks, with a reason (required), audited before/after. No commit."""
    if not reason:
        raise HTTPException(422, REASON_REQUIRED)
    before = {"progress_percent": enrollment.progress_percent, "progress_override_reason": enrollment.progress_override_reason}
    enrollment.progress_percent, enrollment.progress_override_reason = percent, reason
    audit_change(db, user, "enrollment.progress_override", "enrollment", enrollment.id, before, {"progress_percent": percent, "progress_override_reason": reason}, metadata={"batch_id": str(batch.id)})


async def clear_override(db: AsyncSession, user: User, enrollment: Enrollment, batch: Batch) -> None:
    before = {"progress_percent": enrollment.progress_percent, "progress_override_reason": enrollment.progress_override_reason}
    enrollment.progress_override_reason = None
    await db.flush()
    await refresh(db, batch.id)
    audit_change(
        db,
        user,
        "enrollment.progress_override",
        "enrollment",
        enrollment.id,
        before,
        {"progress_percent": enrollment.progress_percent, "progress_override_reason": None},
        metadata={"batch_id": str(batch.id)},
    )


# --- remediation plans (P9) ----------------------------------------------------------------------------------------------------------
async def _counselor_id(db: AsyncSession, student_id: UUID) -> UUID | None:
    return await db.scalar(select(ItStudentCounselor.counselor_user_id).where(ItStudentCounselor.student_user_id == student_id).limit(1))


async def _owner_options(db: AsyncSession, user: User, student_id: UUID) -> list[dict]:
    """Who may own a plan for the student: the trainers of their active batches, their itc-003 counselor, and the caller if an IT Admin."""
    ids = set(
        await db.scalars(
            select(Batch.trainer_id).join(Enrollment, Enrollment.batch_id == Batch.id).where(Enrollment.student_id == student_id, Enrollment.status == "active", Batch.trainer_id.is_not(None))
        )
    )
    if counselor := await _counselor_id(db, student_id):
        ids.add(counselor)
    if _is_admin(user):
        ids.add(user.id)
    users = await db.scalars(select(User).where(User.id.in_(ids), User.active.is_(True)).order_by(User.full_name, User.id)) if ids else []
    return [{"id": u.id, "name": u.full_name, "role": u.role} for u in users]


async def _check_owner(db: AsyncSession, owner_id: UUID, batch: Batch, student_id: UUID) -> None:
    if owner_id == batch.trainer_id or owner_id == await _counselor_id(db, student_id):
        return
    owner = await db.get(User, owner_id)
    if owner is None or not owner.active or not (owner.role == "it_admin" and owner.division == "it"):
        raise HTTPException(422, "The owner must be the batch's trainer, the student's IT counselor or an IT Admin")


def _check_due(due: date) -> None:
    if due < _today():
        raise HTTPException(422, "The due date cannot be in the past")


async def _editable(db: AsyncSession, user: User, plan_id: UUID) -> tuple[RemediationPlan, Enrollment, Batch]:
    """The plan for its batch's trainer, an IT Admin, or its owner; anyone else in a staff role gets the same 404 as a missing plan."""
    if user.role not in ("trainer", "it_admin", "super_admin", "counselor") or (not _is_admin(user) and user.division != "it"):
        raise HTTPException(403, BATCH_STAFF)
    row = (
        await db.execute(
            select(RemediationPlan, Enrollment, Batch).join(Enrollment, Enrollment.id == RemediationPlan.enrollment_id).join(Batch, Batch.id == Enrollment.batch_id)
            .where(RemediationPlan.id == plan_id).with_for_update(of=RemediationPlan)
        )
    ).first()  # fmt: skip
    if row is None or not (_is_admin(user) or row[2].trainer_id == user.id or row[0].owner_user_id == user.id):
        raise HTTPException(404, PLAN_NOT_FOUND)
    return row[0], row[1], row[2]


def _plan_out(plan: RemediationPlan, owner: User | None, batch: Batch, *, staff: bool) -> dict:
    out = {"id": plan.id, "actions": plan.actions, "due_date": plan.due_date, "status": plan.status, "owner_name": owner.full_name if owner else None,
           "batch": batch.name, "created_at": plan.created_at, "updated_at": plan.updated_at}  # fmt: skip
    if staff:
        out |= {"enrollment_id": plan.enrollment_id, "owner_user_id": plan.owner_user_id, "risk_flag_id": plan.risk_flag_id}
    return out


async def _plans(db: AsyncSession, student_id: UUID, *, staff: bool) -> list[dict]:
    rows = await db.execute(
        select(RemediationPlan, User, Batch).join(Enrollment, Enrollment.id == RemediationPlan.enrollment_id).join(Batch, Batch.id == Enrollment.batch_id)
        .outerjoin(User, User.id == RemediationPlan.owner_user_id).where(RemediationPlan.student_id == student_id)
        .order_by(RemediationPlan.status.in_(CLOSED), RemediationPlan.due_date, RemediationPlan.created_at.desc())
    )  # fmt: skip
    return [_plan_out(plan, owner, batch, staff=staff) for plan, owner, batch in rows.all()]


async def student_plans(db: AsyncSession, user: User, student_id: UUID) -> dict:
    """Staff read: the itc-028 scope (trainer seated, counselor linked, IT Admin) minus HR. `can_create` and the owner options for writers."""
    if user.role not in ("trainer", "counselor", "it_admin", "super_admin"):
        raise HTTPException(403, "Only the student's trainer, IT counselor or the IT Admin can see remediation plans")
    student = await it_student_notes.staff_student(db, user, student_id) if user.role != "super_admin" else await db.get(User, student_id)
    if student is None:
        raise HTTPException(404, it_student_notes.STUDENT_NOT_FOUND)
    enrollments = (
        await db.execute(
            select(Enrollment, Batch).join(Batch, Batch.id == Enrollment.batch_id)
            .where(Enrollment.student_id == student.id, Enrollment.status == "active").order_by(Enrollment.enrolled_on, Enrollment.id)
        )
    ).all()  # fmt: skip
    creatable = [{"enrollment_id": e.id, "batch": b.name} for e, b in enrollments if _is_admin(user) or b.trainer_id == user.id]
    return {
        "student": {"id": student.id, "full_name": student.full_name, "student_code": student.student_code},
        "items": await _plans(db, student.id, staff=True),
        "enrollments": creatable,
        "owner_options": await _owner_options(db, user, student.id) if creatable else [],
        "viewer_id": user.id,  # QA-04: the page offers an owner the status buttons and names the caller "(me)"
    }


async def create_plan(db: AsyncSession, user: User, enrollment_id: UUID, payload: RemediationPlanIn) -> dict:
    _require_staff(user)
    enrollment = await db.get(Enrollment, enrollment_id)
    batch = await db.get(Batch, enrollment.batch_id) if enrollment else None
    if enrollment is None or batch is None or not (_is_admin(user) or batch.trainer_id == user.id):
        raise HTTPException(404, ENROLLMENT_NOT_FOUND)
    if enrollment.status != "active":
        raise HTTPException(422, "A remediation plan can only be created for an actively enrolled student")
    _check_due(payload.due_date)
    owner_id = payload.owner_user_id or user.id
    await _check_owner(db, owner_id, batch, enrollment.student_id)
    flag = await db.scalar(select(StudentRiskFlag.id).where(StudentRiskFlag.enrollment_id == enrollment.id, StudentRiskFlag.cleared_at.is_(None)))
    plan = RemediationPlan(enrollment_id=enrollment.id, student_id=enrollment.student_id, risk_flag_id=flag, actions=payload.actions,
                           owner_user_id=owner_id, due_date=payload.due_date, status="open", created_by_id=user.id)  # fmt: skip
    db.add(plan)
    await db.flush()
    audit_change(db, user, "it.remediation_plan.create", "remediation_plan", plan.id, {}, {"status": "open", "due_date": plan.due_date, "owner_user_id": owner_id},
                 metadata={"enrollment_id": str(enrollment.id)})  # fmt: skip
    await db.commit()
    await db.refresh(plan)
    logger.info("it_remediation_plan_created", extra={"extra_fields": {"actor_id": str(user.id), "plan_id": str(plan.id)}})
    return _plan_out(plan, await db.get(User, owner_id), batch, staff=True)


async def update_plan(db: AsyncSession, user: User, plan_id: UUID, payload: RemediationPlanPatch) -> dict:
    plan, enrollment, batch = await _editable(db, user, plan_id)
    changes = payload.model_dump(exclude_unset=True)
    if None in changes.values():
        raise HTTPException(422, "A field cannot be cleared")
    if not (_is_admin(user) or batch.trainer_id == user.id) and set(changes) - {"status"}:
        raise HTTPException(403, "The plan's owner can change only its status")
    if plan.status in CLOSED:
        raise HTTPException(409, "This plan is closed")
    if "due_date" in changes and changes["due_date"] != plan.due_date:
        _check_due(changes["due_date"])
    if "owner_user_id" in changes and changes["owner_user_id"] != plan.owner_user_id:
        await _check_owner(db, changes["owner_user_id"], batch, enrollment.student_id)
    before = {k: getattr(plan, k) for k in changes}
    for key, value in changes.items():
        setattr(plan, key, value)
    audit_change(db, user, "it.remediation_plan.update", "remediation_plan", plan.id, before, changes, metadata={"enrollment_id": str(enrollment.id)})
    await db.commit()
    await db.refresh(plan)
    return _plan_out(plan, await db.get(User, plan.owner_user_id), batch, staff=True)


# --- the student's view (P10) --------------------------------------------------------------------------------------------------------
async def my_progress(db: AsyncSession, user: User) -> dict:
    """The student's own active/completed enrolments: progress, how it is worked out, topics with ticks, their remediation plans."""
    if user.role != "it_student":
        raise HTTPException(403, "Only an IT student has course progress")
    rows = (
        await db.execute(
            select(Enrollment, Batch, Program).join(Batch, Batch.id == Enrollment.batch_id).join(Program, Program.id == Batch.program_id)
            .where(Enrollment.student_id == user.id, Enrollment.status.in_(("active", "completed"))).order_by(Enrollment.enrolled_on.desc(), Enrollment.id)
        )
    ).all()  # fmt: skip
    courses = []
    for enrollment, batch, program in rows:
        figures = (await components(db, batch, [enrollment]))[enrollment.id]
        seat = await training_progress.seat(db, user.id, batch.id)
        weights = await _weights(db, program.id)
        done = set(await db.scalars(select(TopicCompletion.topic_id).where(TopicCompletion.enrollment_id == enrollment.id)))
        modules = [
            {"title": m["title"], "topics": [{"title": t["title"], "completed": t["id"] in done} for t in m["topics"]]}
            for m in await _modules(db, program.id)
        ]  # fmt: skip
        courses.append({
            "enrollment_id": enrollment.id, "course": program.title, "batch": batch.name, "status": enrollment.status,
            "progress_percent": enrollment.progress_percent,
            "mode": "manual" if weights is None else "override" if enrollment.progress_override_reason else "computed",
            "weights": weights, "topics_completed": figures["topics_completed"], "topics_total": figures["topics_total"],
            "labs_graded": figures["labs_graded"], "labs_total": figures["labs_total"],
            "assignments_graded": seat["assignments_graded"], "assignments_total": seat["assignments_total"],
            "assessments_passed": seat["assessments_passed"], "assessments_total": seat["assessments_total"],
            "modules": modules,
        })  # fmt: skip
    return {"courses": courses, "remediation_plans": await _plans(db, user.id, staff=False)}
