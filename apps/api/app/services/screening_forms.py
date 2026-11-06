"""pob-020 (DEC-SCOPE-412): the question bank, form templates, a requirement's versioned form, screening sessions, the scorecard and the
side-by-side comparison.

Functions only; nothing here commits -- the route owns the transaction and has already locked the job or application. Audit rows and logs
carry ids, versions and the recommendation, never an answer or a note. Answers in the compensation category follow hrc-001 H2 (S12)."""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    SCREENING_RECOMMENDATIONS,
    AuditLog,
    Candidate,
    Job,
    JobApplication,
    ScreeningAnswer,
    ScreeningForm,
    ScreeningFormQuestion,
    ScreeningQuestion,
    ScreeningSession,
    User,
)
from app.services import application_screening as checklist
from app.services import applications, candidates
from app.services import recruiter_requirements as requirements
from app.services.recruiter import MANAGER_ROLE, ROLE

CATEGORY_LABELS = {
    "experience": "Experience and qualification", "technical": "Technical skills", "communication": "Communication",
    "availability": "Availability and location", "compensation": "Compensation",
}
FORMAT_LABELS = {"text": "Text", "yes_no": "Yes / No", "numeric": "Number", "choice": "Choice", "rating": "Rating (1-5)"}
KNOCKOUT_LABELS = {"none": "No knock-outs", "pending": "Knock-outs awaiting Team Lead approval", "approved": "Knock-outs approved"}
COMPENSATION = "compensation"
MANAGERS = (ROLE, MANAGER_ROLE, "super_admin")  # S13: bank, templates and requirement forms
APPROVERS = (MANAGER_ROLE, "super_admin")  # S5: Team Lead = placement_manager
COMPARISON_LIMIT = 50
COPIED_FIELDS = ("category", "question", "format", "choices", "evaluation_criteria", "expected_answer")

NO_FORM = "This requirement has no screening form yet"
FORM_EXISTS = "This requirement already has a screening form"
FORM_CHANGED = "The screening form has changed. Reload and answer the current version."
ENDED_FORM = "A closed or cancelled requirement's screening form cannot change"


def can_manage(user: User) -> bool:
    return user.role in MANAGERS


def require_manager(user: User) -> None:
    if not can_manage(user):
        raise HTTPException(403, "Only a recruiter or Team Lead can manage screening questions and forms")


def can_approve(user: User) -> bool:
    return user.role in APPROVERS


def _catalogue() -> dict:
    return {
        "categories": [{"key": k, "label": v} for k, v in CATEGORY_LABELS.items()],
        "formats": [{"key": k, "label": v} for k, v in FORMAT_LABELS.items()],
    }


def _audit(db: AsyncSession, user: User, action: str, entity_type: str, entity_id, metadata: dict) -> None:
    db.add(AuditLog(user_id=user.id, action=f"screening.{action}", entity_type=entity_type, entity_id=str(entity_id), metadata_json=metadata))


# --- the bank ---------------------------------------------------------------------------------------------------------------------------
def question_out(row: ScreeningQuestion) -> dict:
    return {
        "id": row.id, "category": row.category, "category_label": CATEGORY_LABELS[row.category], "text": row.question, "format": row.format,
        "format_label": FORMAT_LABELS[row.format], "choices": row.choices, "evaluation_criteria": row.evaluation_criteria,
        "expected_answer": row.expected_answer, "active": row.active,
    }


async def list_questions(db: AsyncSession, q: str | None, category: str | None, include_archived: bool, limit: int, offset: int) -> dict:
    where = []
    if q and q.strip():
        where.append(func.strpos(func.lower(ScreeningQuestion.question), q.strip().lower()) > 0)
    if category:
        where.append(ScreeningQuestion.category == category)
    if not include_archived:
        where.append(ScreeningQuestion.active.is_(True))
    rows = (await db.scalars(select(ScreeningQuestion).where(*where).order_by(ScreeningQuestion.category, ScreeningQuestion.question, ScreeningQuestion.id).limit(limit).offset(offset))).all()
    total = await db.scalar(select(func.count()).select_from(ScreeningQuestion).where(*where))
    return {"items": [question_out(r) for r in rows], "total": total, **_catalogue()}


async def _flush_unique(db: AsyncSession, message: str) -> None:
    """The unique index is the rule: a concurrent or repeated name is the same 409."""
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, message) from None


DUPLICATE_QUESTION = "This question is already in the bank"
DUPLICATE_TEMPLATE = "A template with this name already exists"


async def create_question(db: AsyncSession, user: User, sent: dict) -> ScreeningQuestion:
    _check_choices(sent["format"], sent["choices"])
    row = ScreeningQuestion(question=sent.pop("text"), **sent, created_by_user_id=user.id)
    db.add(row)
    await _flush_unique(db, DUPLICATE_QUESTION)
    _audit(db, user, "question_create", "screening_question", row.id, {"category": row.category, "format": row.format})
    return row


async def update_question(db: AsyncSession, user: User, question_id: UUID, sent: dict) -> ScreeningQuestion:
    row = await db.scalar(select(ScreeningQuestion).where(ScreeningQuestion.id == question_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Question not found")
    changes = {("question" if k == "text" else k): v for k, v in sent.items()}
    for required in ("category", "question", "format", "active"):  # these columns have no "cleared" state
        if required in changes and changes[required] is None:
            raise HTTPException(422, f"{required.replace('_', ' ').capitalize()} cannot be empty")
    for field, value in changes.items():
        setattr(row, field, value)
    _check_choices(row.format, row.choices)
    await _flush_unique(db, DUPLICATE_QUESTION)
    _audit(db, user, "question_update", "screening_question", row.id, {"fields": sorted(changes)})
    return row


def _check_choices(fmt: str, choices: list | None) -> None:
    if fmt == "choice":
        if not choices or len(choices) < 2 or len(set(choices)) != len(choices):
            raise HTTPException(422, "A choice question needs at least two different choices")
    elif choices:
        raise HTTPException(422, "Only a choice question has choices")


# --- forms and templates ----------------------------------------------------------------------------------------------------------------
async def _rows_of(db: AsyncSession, form_id: UUID, version: int) -> list[ScreeningFormQuestion]:
    stmt = select(ScreeningFormQuestion).where(ScreeningFormQuestion.form_id == form_id, ScreeningFormQuestion.version == version).order_by(ScreeningFormQuestion.position)
    return list((await db.scalars(stmt)).all())


def _form_question_out(row: ScreeningFormQuestion) -> dict:
    return {
        "id": row.id, "question_id": row.question_id, "position": row.position, "category": row.category, "category_label": CATEGORY_LABELS[row.category],
        "text": row.question, "format": row.format, "format_label": FORMAT_LABELS[row.format], "choices": row.choices,
        "evaluation_criteria": row.evaluation_criteria, "expected_answer": row.expected_answer, "is_knockout": row.is_knockout,
    }


async def form_out(db: AsyncSession, form: ScreeningForm) -> dict:
    approver = await db.get(User, form.knockout_approved_by_user_id) if form.knockout_approved_by_user_id else None
    return {
        "id": form.id, "name": form.name, "version": form.version, "knockout_status": form.knockout_status,
        "knockout_status_label": KNOCKOUT_LABELS[form.knockout_status],
        "knockout_approved_by": {"id": approver.id, "full_name": approver.full_name} if approver else None,
        "knockout_approved_at": form.knockout_approved_at,
        "questions": [_form_question_out(r) for r in await _rows_of(db, form.id, form.version)],
    }


async def _specs(db: AsyncSession, questions: list[dict]) -> list[dict]:
    """The sent questions as column values: a bank question is copied, S6's knock-out rules are checked, and a repeat is refused."""
    ids = [q["question_id"] for q in questions if q["question_id"]]
    bank = {r.id: r for r in (await db.scalars(select(ScreeningQuestion).where(ScreeningQuestion.id.in_(ids), ScreeningQuestion.active.is_(True)))).all()} if ids else {}
    specs = []
    for sent in questions:
        source = bank.get(sent["question_id"]) if sent["question_id"] else None
        if sent["question_id"] and source is None:
            raise HTTPException(422, "Choose an active question from the bank")
        values = {f: getattr(source, f) for f in COPIED_FIELDS} if source else {**{f: sent[f] for f in COPIED_FIELDS if f != "question"}, "question": sent["text"]}
        _check_choices(values["format"], values["choices"])
        spec = {**values, "question_id": sent["question_id"], "is_knockout": sent["is_knockout"]}
        if spec["is_knockout"]:
            if spec["format"] != "yes_no":
                raise HTTPException(422, "A knock-out must be a yes/no question")
            if spec["category"] == COMPENSATION:
                raise HTTPException(422, "A compensation question cannot be a knock-out")
            spec["expected_answer"] = spec["expected_answer"] or "yes"
            if spec["expected_answer"] not in ("yes", "no"):
                raise HTTPException(422, "A knock-out's expected answer is yes or no")
        specs.append(spec)
    if len({s["question"].lower() for s in specs}) != len(specs):
        raise HTTPException(422, "The same question appears twice")
    return specs


def _write_rows(db: AsyncSession, form: ScreeningForm, specs: list[dict]) -> None:
    for position, spec in enumerate(specs, start=1):
        db.add(ScreeningFormQuestion(form_id=form.id, version=form.version, position=position, **spec))


def _spec_of(row: ScreeningFormQuestion) -> dict:
    return {**{f: getattr(row, f) for f in COPIED_FIELDS}, "question_id": row.question_id, "is_knockout": row.is_knockout}


def _knockouts(specs: list[dict]) -> set[tuple]:
    """A knock-out's identity for S7: its wording and expected answer."""
    return {(s["question"].lower(), s["expected_answer"]) for s in specs if s["is_knockout"]}


def _same_questions(a: list[dict], b: list[dict]) -> bool:
    """question_id is only where a copy came from, so it does not make a new version."""
    return [{k: v for k, v in s.items() if k != "question_id"} for s in a] == [{k: v for k, v in s.items() if k != "question_id"} for s in b]


async def _new_version(db: AsyncSession, form: ScreeningForm, specs: list[dict]) -> bool:
    """S4: identical questions change nothing. S7: an approval survives unless the knock-outs changed. Returns whether a version was written."""
    current = [_spec_of(r) for r in await _rows_of(db, form.id, form.version)]
    if _same_questions(current, specs):
        return False
    wanted = _knockouts(specs)
    if wanted != _knockouts(current) or form.knockout_status != "approved":
        form.knockout_status = "pending" if wanted else "none"
        form.knockout_approved_by_user_id = form.knockout_approved_at = None
    form.version += 1
    _write_rows(db, form, specs)
    return True


async def _templates(db: AsyncSession, include_archived: bool = False, limit: int = 100) -> list[ScreeningForm]:
    where = [ScreeningForm.job_id.is_(None)]
    if not include_archived:
        where.append(ScreeningForm.archived_at.is_(None))
    return list((await db.scalars(select(ScreeningForm).where(*where).order_by(ScreeningForm.is_default.desc(), func.lower(ScreeningForm.name)).limit(limit))).all())


async def list_templates(db: AsyncSession, include_archived: bool, limit: int) -> dict:
    forms = await _templates(db, include_archived, limit)
    join = and_(ScreeningForm.id == ScreeningFormQuestion.form_id, ScreeningForm.version == ScreeningFormQuestion.version)
    rows = (await db.scalars(select(ScreeningFormQuestion).join(ScreeningForm, join).where(ScreeningForm.id.in_([f.id for f in forms])).order_by(ScreeningFormQuestion.position))).all()
    by_form: dict[UUID, list] = {}
    for row in rows:
        by_form.setdefault(row.form_id, []).append(_form_question_out(row))
    return {"items": [template_out(f, by_form.get(f.id, [])) for f in forms], **_catalogue()}


def template_out(form: ScreeningForm, questions: list[dict]) -> dict:
    return {"id": form.id, "name": form.name, "is_default": form.is_default, "version": form.version, "archived": form.archived_at is not None, "questions": questions}


async def create_template(db: AsyncSession, user: User, name: str, questions: list[dict]) -> dict:
    specs = await _specs(db, questions)
    form = ScreeningForm(name=name, created_by_user_id=user.id)
    db.add(form)
    await _flush_unique(db, DUPLICATE_TEMPLATE)
    _write_rows(db, form, specs)
    await db.flush()
    _audit(db, user, "template_create", "screening_form", form.id, {"questions": len(specs)})
    return template_out(form, [_form_question_out(r) for r in await _rows_of(db, form.id, form.version)])


async def update_template(db: AsyncSession, user: User, template_id: UUID, sent: dict) -> dict:
    form = await db.scalar(select(ScreeningForm).where(ScreeningForm.id == template_id, ScreeningForm.job_id.is_(None)).with_for_update())
    if form is None:
        raise HTTPException(404, "Template not found")
    if sent["archived"] is not None:
        if sent["archived"] and form.is_default:
            raise HTTPException(409, "The default template cannot be archived")
        form.archived_at = (await db.scalar(select(func.now()))) if sent["archived"] else None
    if sent["name"]:
        form.name = sent["name"]
    await _flush_unique(db, DUPLICATE_TEMPLATE)
    if sent["questions"]:
        await _new_version(db, form, await _specs(db, sent["questions"]))
        form.knockout_status, form.knockout_approved_by_user_id, form.knockout_approved_at = "none", None, None  # S7: approval is per requirement
        await db.flush()
    _audit(db, user, "template_update", "screening_form", form.id, {"fields": sorted(k for k, v in sent.items() if v is not None), "version": form.version})
    return template_out(form, [_form_question_out(r) for r in await _rows_of(db, form.id, form.version)])


async def requirement_form(db: AsyncSession, job_id: UUID) -> ScreeningForm | None:
    return await db.scalar(select(ScreeningForm).where(ScreeningForm.job_id == job_id).execution_options(populate_existing=True))


async def read_form(db: AsyncSession, user: User, job: Job) -> dict:
    form = await requirement_form(db, job.id)
    templates = await _templates(db)
    return {
        "form": await form_out(db, form) if form else None,
        "templates": [{"id": t.id, "name": t.name, "is_default": t.is_default} for t in templates],
        "can_edit": can_manage(user) and job.status not in requirements.ENDED,
        "can_approve": can_approve(user) and job.status not in requirements.ENDED,
        **_catalogue(),
    }


def _require_editable(user: User, job: Job) -> None:
    require_manager(user)
    if job.status in requirements.ENDED:
        raise HTTPException(409, ENDED_FORM)


async def create_form(db: AsyncSession, user: User, job: Job, template_id: UUID | None) -> ScreeningForm:
    """AC1: from the named template, or the default one (S1)."""
    _require_editable(user, job)
    if await requirement_form(db, job.id):
        raise HTTPException(409, FORM_EXISTS)
    where = ScreeningForm.id == template_id if template_id else ScreeningForm.is_default.is_(True)
    template = await db.scalar(select(ScreeningForm).where(where, ScreeningForm.job_id.is_(None), ScreeningForm.archived_at.is_(None)))
    if template is None:
        raise HTTPException(422, "Choose an active template")
    rows = await _rows_of(db, template.id, template.version)
    form = ScreeningForm(job_id=job.id, name=template.name, created_by_user_id=user.id, knockout_status="pending" if any(r.is_knockout for r in rows) else "none")
    db.add(form)
    await db.flush()
    _write_rows(db, form, [_spec_of(r) for r in rows])
    _audit(db, user, "form_create", "job", job.id, {"form_id": str(form.id), "template_id": str(template.id)})
    return form


async def save_form(db: AsyncSession, user: User, job: Job, questions: list[dict]) -> ScreeningForm:
    _require_editable(user, job)
    form = await requirement_form(db, job.id)
    if form is None:
        raise HTTPException(409, NO_FORM)
    if await _new_version(db, form, await _specs(db, questions)):
        _audit(db, user, "form_version", "job", job.id, {"form_id": str(form.id), "version": form.version, "knockout_status": form.knockout_status})
    return form


async def approve_knockouts(db: AsyncSession, user: User, job: Job, version: int) -> ScreeningForm:
    """S5/S7: the Team Lead approves the version on their screen; anything else on it is a 409."""
    if not can_approve(user):
        raise HTTPException(403, "Only a Team Lead can approve knock-out questions")
    form = await requirement_form(db, job.id)
    if form is None:
        raise HTTPException(409, NO_FORM)
    if version != form.version:
        raise HTTPException(409, FORM_CHANGED)
    if form.knockout_status != "pending":
        raise HTTPException(409, "No knock-out questions are awaiting approval")
    form.knockout_status, form.knockout_approved_by_user_id, form.knockout_approved_at = "approved", user.id, await db.scalar(select(func.now()))
    _audit(db, user, "knockouts_approved", "job", job.id, {"form_id": str(form.id), "version": form.version})
    return form


# --- sessions ---------------------------------------------------------------------------------------------------------------------------
RECOMMENDATION_LABELS = checklist.RECOMMENDATION_LABELS
assert tuple(RECOMMENDATION_LABELS) == SCREENING_RECOMMENDATIONS


def _check_answer(question: ScreeningFormQuestion, answer: str) -> None:
    fmt, ok = question.format, True
    if fmt == "yes_no":
        ok = answer in ("yes", "no")
    elif fmt == "rating":
        ok = answer in ("1", "2", "3", "4", "5")
    elif fmt == "choice":
        ok = answer in (question.choices or [])
    elif fmt == "numeric":
        try:
            ok = Decimal(answer).is_finite()
        except InvalidOperation:
            ok = False
    if not ok:
        raise HTTPException(422, f"The answer to \"{question.question}\" does not fit its format")


async def record(db: AsyncSession, user: User, application: JobApplication, job: Job, sent: dict) -> ScreeningSession:
    """AC2/AC3: S8's knock-out rule, S10's score, S11's checks. Never moves the application's status (S9)."""
    if application.status not in applications.OPEN:
        raise HTTPException(409, checklist.NOT_OPEN)
    form = await requirement_form(db, job.id)
    if form is None:
        raise HTTPException(409, NO_FORM)
    if sent["form_version"] != form.version:
        raise HTTPException(409, FORM_CHANGED)
    questions = {q.id: q for q in await _rows_of(db, form.id, form.version)}
    answers = {a["question_id"]: a for a in sent["answers"]}
    if unknown := set(answers) - set(questions):
        raise HTTPException(422, f"{len(unknown)} answer(s) are not for this form")
    sees = await candidates.sees_compensation(db, user)
    for question_id, answer in answers.items():
        if questions[question_id].category == COMPENSATION and not sees:
            raise HTTPException(403, candidates.NO_COMPENSATION)
        _check_answer(questions[question_id], answer["answer"])

    active_knockouts = [q for q in questions.values() if q.is_knockout] if form.knockout_status == "approved" else []
    if any(q.id not in answers for q in active_knockouts):
        raise HTTPException(422, "Answer every knock-out question")
    triggered = any(answers[q.id]["answer"] != q.expected_answer for q in active_knockouts)
    if sent["knockout_override"] and not triggered:
        raise HTTPException(422, "There is no failed knock-out to override")

    session = ScreeningSession(
        application_id=application.id, kind="form", form_id=form.id, form_version=form.version, screened_by_user_id=user.id, notes=sent["notes"],
        recommendation="reject" if triggered and not sent["knockout_override"] else sent["recommendation"], knockout_triggered=triggered,
        knockout_overridden=sent["knockout_override"], override_reason=sent["override_reason"] if sent["knockout_override"] else None,
    )
    db.add(session)
    await db.flush()
    for question_id, answer in answers.items():
        score = answer["score"]
        if score is None and questions[question_id].format == "rating":
            score = int(answer["answer"])
        db.add(ScreeningAnswer(session_id=session.id, form_question_id=question_id, answer=answer["answer"], score=score))
    meta = {"result": session.recommendation, "session_id": str(session.id), "form_version": form.version, "knockout_triggered": triggered, "knockout_overridden": session.knockout_overridden}
    applications.audit(db, user, "screening", application, meta)
    await db.flush()
    return session


def scorecard(scores: list[int | None]) -> dict | None:
    """S10: over the answers that have a score; None when nothing was scored."""
    scored = [s for s in scores if s is not None]
    if not scored:
        return None
    total, maximum = sum(scored), 5 * len(scored)
    return {"total": total, "max": maximum, "percent": round(total * 100 / maximum)}


async def _answers_by_session(db: AsyncSession, session_ids: list[UUID]) -> dict[UUID, list[tuple[ScreeningAnswer, ScreeningFormQuestion]]]:
    if not session_ids:
        return {}
    rows = (
        await db.execute(
            select(ScreeningAnswer, ScreeningFormQuestion)
            .join(ScreeningFormQuestion, ScreeningFormQuestion.id == ScreeningAnswer.form_question_id)
            .where(ScreeningAnswer.session_id.in_(session_ids))
            .order_by(ScreeningFormQuestion.position)
        )
    ).all()
    grouped: dict[UUID, list] = {}
    for answer, question in rows:
        grouped.setdefault(answer.session_id, []).append((answer, question))
    return grouped


def _visible_answer(answer: ScreeningAnswer, question: ScreeningFormQuestion, sees: bool) -> dict:
    """S12: the score stays; the words of a compensation answer need the grant."""
    if question.category == COMPENSATION and not sees:
        return {"answer": None, "answer_hidden": True, "score": answer.score}
    return {"answer": answer.answer, "score": answer.score}


def _session_out(session: ScreeningSession, by: User, answers: list[tuple[ScreeningAnswer, ScreeningFormQuestion]], sees: bool) -> dict:
    snapshot = None
    if session.legacy_snapshot is not None:
        snapshot = {**session.legacy_snapshot, "result_label": checklist.LABELS[session.legacy_snapshot["result"]]}
        if not sees:
            snapshot.pop("expected_salary", None)
    return {
        "id": session.id, "kind": session.kind, "form_version": session.form_version, "screened_by": {"id": by.id, "full_name": by.full_name},
        "created_at": session.created_at, "notes": session.notes, "recommendation": session.recommendation, "recommendation_label": RECOMMENDATION_LABELS[session.recommendation],
        "knockout_triggered": session.knockout_triggered, "knockout_overridden": session.knockout_overridden, "override_reason": session.override_reason,
        "answers": [
            {"question_id": q.id, "question": q.question, "category": q.category, "format": q.format, "is_knockout": q.is_knockout, **_visible_answer(a, q, sees)}
            for a, q in answers
        ],
        "scorecard": scorecard([a.score for a, _ in answers]),
        "checklist": snapshot,
    }


async def sessions_out(db: AsyncSession, user: User, application_id: UUID, only: UUID | None = None) -> list[dict]:
    """Newest first (AC3)."""
    where = ScreeningSession.id == only if only else ScreeningSession.application_id == application_id
    rows = (await db.execute(select(ScreeningSession, User).join(User, User.id == ScreeningSession.screened_by_user_id).where(where).order_by(ScreeningSession.created_at.desc(), ScreeningSession.id))).all()
    answers = await _answers_by_session(db, [s.id for s, _ in rows])
    sees = await candidates.sees_compensation(db, user)
    return [_session_out(s, by, answers.get(s.id, []), sees) for s, by in rows]


async def read_sessions(db: AsyncSession, user: User, application: JobApplication, job: Job) -> dict:
    form = await requirement_form(db, job.id)
    return {
        "form": await form_out(db, form) if form else None,
        "sessions": await sessions_out(db, user, application.id),
        "can_run": checklist.can_edit(user, application) and form is not None,
        "sees_compensation": await candidates.sees_compensation(db, user),
        "recommendations": [{"key": k, "label": v} for k, v in RECOMMENDATION_LABELS.items()],
    }


# --- comparison -------------------------------------------------------------------------------------------------------------------------
async def comparison(db: AsyncSession, user: User, job: Job, version: int | None) -> dict:
    """AC4: each candidate's latest session on one form version, best score first. At most COMPARISON_LIMIT rows, most recently screened
    first when capped; two queries however many candidates."""
    empty = {"version": None, "versions": [], "questions": [], "rows": [], "truncated": False}
    form = await requirement_form(db, job.id)
    if form is None:
        if version is not None:
            raise HTTPException(404, "That form version does not exist")
        return empty
    versions = list((await db.scalars(select(ScreeningFormQuestion.version).where(ScreeningFormQuestion.form_id == form.id).distinct().order_by(ScreeningFormQuestion.version.desc()))).all())
    chosen = version if version is not None else form.version
    if chosen not in versions:
        raise HTTPException(404, "That form version does not exist")
    latest = (
        select(ScreeningSession.id)
        .join(JobApplication, JobApplication.id == ScreeningSession.application_id)
        .where(ScreeningSession.form_id == form.id, ScreeningSession.form_version == chosen, JobApplication.job_id == job.id)
        .ext(distinct_on(ScreeningSession.application_id))
        .order_by(ScreeningSession.application_id, ScreeningSession.created_at.desc(), ScreeningSession.id)
    )
    rows = (
        await db.execute(
            select(ScreeningSession, JobApplication, Candidate)
            .join(JobApplication, JobApplication.id == ScreeningSession.application_id)
            .join(Candidate, Candidate.id == JobApplication.candidate_id)
            .where(ScreeningSession.id.in_(latest))
            .order_by(ScreeningSession.created_at.desc(), ScreeningSession.id)
            .limit(COMPARISON_LIMIT + 1)
        )
    ).all()
    truncated = len(rows) > COMPARISON_LIMIT
    rows = rows[:COMPARISON_LIMIT]
    answers = await _answers_by_session(db, [s.id for s, _, _ in rows])
    sees = await candidates.sees_compensation(db, user)
    out = []
    for session, application, candidate in rows:
        pairs = answers.get(session.id, [])
        out.append({
            "application_id": application.id, "candidate": {"id": candidate.id, "code": candidate.candidate_code, "name": candidate.name},
            "status_label": applications.label(application.status), "session_id": session.id, "created_at": session.created_at,
            "recommendation": session.recommendation, "recommendation_label": RECOMMENDATION_LABELS[session.recommendation],
            "knockout_triggered": session.knockout_triggered, "knockout_overridden": session.knockout_overridden,
            "scorecard": scorecard([a.score for a, _ in pairs]), "answers": {str(q.id): _visible_answer(a, q, sees) for a, q in pairs},
        })
    out.sort(key=lambda row: -(row["scorecard"]["percent"] if row["scorecard"] else -1))
    questions = [_form_question_out(r) for r in await _rows_of(db, form.id, chosen)]
    return {"version": chosen, "versions": versions, "questions": questions, "rows": out, "truncated": truncated}
