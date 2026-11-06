"""pob-020 -- question bank, requirement forms, screening sessions, scorecard and comparison (DEC-SCOPE-412 S1-S14,
docs/superpowers/specs/2026-11-06-pob-020-screening-forms-design.md). Names are unique per test (the database is shared)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Company, JobApplication, ScreeningSession
from app.services import application_screening as checklist
from app.services import candidate_engagement, candidates, screening_forms
from tests.rec001_helpers import as_role, login, make_user
from tests.test_rec_017_tracking import APPS, REQ, _add, _candidate, _move, _requirement, _team

BANK = "/api/v1/recruiter/screening/questions"
TEMPLATES = "/api/v1/recruiter/screening/templates"


def _q(text="Years with Java?", category="technical", fmt="text", **extra):
    return {"category": category, "text": text, "format": fmt, **extra}


def _knockout(text="Has a valid work permit?", **extra):
    return _q(text, "availability", "yes_no", is_knockout=True, **extra)


async def _world(client, db, status="sourced"):
    manager, recruiter = await _team(client, db)
    job = await _requirement(db, recruiter)
    app_id = (await _add(client, job, await _candidate(db, recruiter), status=status)).json()["application"]["id"]
    return manager, recruiter, job, app_id


async def _second_application(client, db, recruiter, job):
    return (await _add(client, job, await _candidate(db, recruiter))).json()["application"]["id"]


async def _form(client, job, questions=None):
    """The requirement's form from the default template, then the given questions as a new version."""
    created = await client.post(f"{REQ}/{job.id}/screening-form", json={})
    assert created.status_code == 201, created.text
    if questions is None:
        return created.json()["form"]
    saved = await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": questions})
    assert saved.status_code == 200, saved.text
    return saved.json()["form"]


async def _approve(client, db, manager, recruiter, job, version):
    await login(client, manager)
    response = await client.post(f"{REQ}/{job.id}/screening-form/approve-knockouts", json={"version": version})
    assert response.status_code == 200, response.text
    await login(client, recruiter)
    return response.json()["form"]


def _body(form, answers, recommendation="pass", **extra):
    by_text = {q["text"]: q for q in form["questions"]}
    rows = [{"question_id": by_text[text]["id"], **values} for text, values in answers.items()]
    return {"form_version": form["version"], "answers": rows, "recommendation": recommendation, **extra}


async def _run(client, app_id, body):
    return await client.post(f"{APPS}/{app_id}/screening-sessions", json=body)


# --- AC1 / S1: the template ----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac1_a_five_question_form_is_created_from_the_default_template(client, db_session):
    _, _, job, _ = await _world(client, db_session)
    assert (await client.get(f"{REQ}/{job.id}/screening-form")).json()["form"] is None
    form = await _form(client, job)
    assert form["version"] == 1 and len(form["questions"]) == 5
    assert sorted(q["category"] for q in form["questions"]) == ["availability", "communication", "compensation", "experience", "technical"]
    assert form["knockout_status"] == "none"
    again = await client.post(f"{REQ}/{job.id}/screening-form", json={})
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_a_form_can_be_created_from_a_named_template_and_tailored(client, db_session):
    _, _, job, _ = await _world(client, db_session)
    name = f"Java {uuid.uuid4().hex[:8]}"
    template = await client.post(TEMPLATES, json={"name": name, "questions": [_q(), _q("Rate their English", "communication", "rating")]})
    assert template.status_code == 201, template.text
    created = await client.post(f"{REQ}/{job.id}/screening-form", json={"template_id": template.json()["template"]["id"]})
    assert created.status_code == 201 and created.json()["form"]["name"] == name and len(created.json()["form"]["questions"]) == 2
    tailored = await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_q("Spring Boot projects?")]})
    assert tailored.status_code == 200 and tailored.json()["form"]["version"] == 2


@pytest.mark.asyncio
async def test_an_archived_template_is_refused_and_not_offered(client, db_session):
    _, _, job, _ = await _world(client, db_session)
    name = f"Old {uuid.uuid4().hex[:8]}"
    template = (await client.post(TEMPLATES, json={"name": name, "questions": [_q()]})).json()["template"]
    assert (await client.patch(f"{TEMPLATES}/{template['id']}", json={"archived": True})).status_code == 200
    assert (await client.post(f"{REQ}/{job.id}/screening-form", json={"template_id": template["id"]})).status_code == 422
    listed = (await client.get(f"{REQ}/{job.id}/screening-form")).json()["templates"]
    assert name not in [t["name"] for t in listed]


@pytest.mark.asyncio
async def test_a_template_is_renamed_and_its_questions_edited_into_a_new_version(client, db_session):
    _, _, job, _ = await _world(client, db_session)
    name = f"Edit {uuid.uuid4().hex[:8]}"
    template = (await client.post(TEMPLATES, json={"name": name, "questions": [_q("Before?")]})).json()["template"]
    edited = await client.patch(f"{TEMPLATES}/{template['id']}", json={"name": f"{name} new", "questions": [_q("After?"), _knockout()]})
    assert edited.status_code == 200, edited.text
    body = edited.json()["template"]
    assert body["name"] == f"{name} new" and body["version"] == 2 and [q["text"] for q in body["questions"]] == ["After?", "Has a valid work permit?"]
    created = await client.post(f"{REQ}/{job.id}/screening-form", json={"template_id": template["id"]})
    assert created.status_code == 201 and created.json()["form"]["knockout_status"] == "pending"  # S7: approval is per requirement


@pytest.mark.asyncio
async def test_the_default_template_cannot_be_archived(client, db_session):
    await _world(client, db_session)
    default = next(t for t in (await client.get(TEMPLATES, params={"limit": 200})).json()["items"] if t["is_default"])
    assert len(default["questions"]) == 5
    assert (await client.patch(f"{TEMPLATES}/{default['id']}", json={"archived": True})).status_code == 409


@pytest.mark.asyncio
async def test_a_duplicate_template_name_is_409(client, db_session):
    await _world(client, db_session)
    name = f"Same {uuid.uuid4().hex[:8]}"
    assert (await client.post(TEMPLATES, json={"name": name, "questions": [_q()]})).status_code == 201
    assert (await client.post(TEMPLATES, json={"name": name.upper(), "questions": [_q()]})).status_code == 409


# --- the bank --------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_the_bank_adds_edits_filters_and_archives(client, db_session):
    await _world(client, db_session)
    text = f"Why this role {uuid.uuid4().hex[:8]}?"
    created = await client.post(BANK, json=_q(text, "experience", "choice", choices=["A", "B"], evaluation_criteria="Clear reason", expected_answer="A"))
    assert created.status_code == 201, created.text
    question = created.json()["question"]
    assert question["choices"] == ["A", "B"] and question["evaluation_criteria"] == "Clear reason" and question["active"] is True
    assert (await client.post(BANK, json=_q(text, "experience", "text"))).status_code == 409
    found = (await client.get(BANK, params={"q": text, "category": "experience"})).json()
    assert [i["id"] for i in found["items"]] == [question["id"]] and {c["key"] for c in found["categories"]} >= {"compensation"}
    assert (await client.get(BANK, params={"q": text, "category": "technical"})).json()["items"] == []
    edited = await client.patch(f"{BANK}/{question['id']}", json={"expected_answer": "B"})
    assert edited.status_code == 200 and edited.json()["question"]["expected_answer"] == "B"
    assert (await client.patch(f"{BANK}/{question['id']}", json={"active": False})).json()["question"]["active"] is False
    assert (await client.get(BANK, params={"q": text})).json()["items"] == []
    assert len((await client.get(BANK, params={"q": text, "include_archived": True})).json()["items"]) == 1
    assert (await client.patch(f"{BANK}/{uuid.uuid4()}", json={"active": False})).status_code == 404


@pytest.mark.asyncio
async def test_editing_the_bank_does_not_change_a_form_that_copied_the_question(client, db_session):
    _, _, job, _ = await _world(client, db_session)
    text = f"Copied {uuid.uuid4().hex[:8]}?"
    question = (await client.post(BANK, json=_q(text))).json()["question"]
    await _form(client, job, [{"question_id": question["id"]}])
    await client.patch(f"{BANK}/{question['id']}", json={"text": f"{text} changed"})
    assert (await client.get(f"{REQ}/{job.id}/screening-form")).json()["form"]["questions"][0]["text"] == text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        _q(category="nope"),
        _q(fmt="essay"),
        _q(text="   "),
        _q(text="x" * 501),
        _q(fmt="choice"),
        _q(fmt="choice", choices=["only one"]),
        _q(fmt="choice", choices=["same", "same"]),
        _q(fmt="text", choices=["a", "b"]),
        _q(extra_field=1),
    ],
)
async def test_bank_validation_is_422(client, db_session, bad):
    await _world(client, db_session)
    assert (await client.post(BANK, json=bad)).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "questions",
    [
        [],
        [_q(is_knockout=True)],  # S6: yes/no only
        [_q("Salary above budget?", "compensation", "yes_no", is_knockout=True)],  # S6: never compensation
        [_knockout(expected_answer="maybe")],
        [_q(), _q()],  # the same question twice
        [{"question_id": str(uuid.uuid4())}],
        [_q() | {"text": f"Q{i}"} for i in range(21)],
    ],
)
async def test_form_validation_is_422(client, db_session, questions):
    _, _, job, _ = await _world(client, db_session)
    await _form(client, job)
    response = await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": questions})
    assert response.status_code == 422, response.text


# --- AC2 / S6-S8: knock-outs ---------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac2_an_approved_knockout_no_forces_reject_unless_overridden(client, db_session):
    manager, recruiter, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_knockout(), _q()])
    assert form["knockout_status"] == "pending"
    form = await _approve(client, db_session, manager, recruiter, job, form["version"])
    assert form["knockout_status"] == "approved" and form["knockout_approved_by"]["id"] == str(manager.id)

    forced = await _run(client, app_id, _body(form, {"Has a valid work permit?": {"answer": "no"}}, "pass"))
    assert forced.status_code == 201, forced.text
    session = forced.json()["session"]
    assert session["recommendation"] == "reject" and session["knockout_triggered"] is True and session["knockout_overridden"] is False

    kept = await _run(client, app_id, _body(form, {"Has a valid work permit?": {"answer": "no"}}, "pass", knockout_override=True, override_reason="Permit renewal confirmed"))
    assert kept.status_code == 201 and kept.json()["session"]["recommendation"] == "pass"
    assert kept.json()["session"]["knockout_overridden"] is True and kept.json()["session"]["override_reason"] == "Permit renewal confirmed"

    passed = await _run(client, app_id, _body(form, {"Has a valid work permit?": {"answer": "yes"}}, "pass"))
    assert passed.json()["session"]["recommendation"] == "pass" and passed.json()["session"]["knockout_triggered"] is False


@pytest.mark.asyncio
async def test_a_knockout_can_expect_no(client, db_session):
    manager, recruiter, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_knockout("Under a bond?", expected_answer="no")])
    form = await _approve(client, db_session, manager, recruiter, job, form["version"])
    assert (await _run(client, app_id, _body(form, {"Under a bond?": {"answer": "yes"}}, "pass"))).json()["session"]["recommendation"] == "reject"
    assert (await _run(client, app_id, _body(form, {"Under a bond?": {"answer": "no"}}, "pass"))).json()["session"]["recommendation"] == "pass"


@pytest.mark.asyncio
async def test_a_pending_knockout_is_an_ordinary_question(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_knockout()])
    response = await _run(client, app_id, _body(form, {"Has a valid work permit?": {"answer": "no"}}, "pass"))
    assert response.status_code == 201 and response.json()["session"]["recommendation"] == "pass" and response.json()["session"]["knockout_triggered"] is False
    assert (await _run(client, app_id, _body(form, {}, "hold"))).status_code == 201


@pytest.mark.asyncio
async def test_an_approved_knockout_must_be_answered_and_override_rules_hold(client, db_session):
    manager, recruiter, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_knockout()])
    form = await _approve(client, db_session, manager, recruiter, job, form["version"])
    assert (await _run(client, app_id, _body(form, {}, "pass"))).status_code == 422
    no = {"Has a valid work permit?": {"answer": "no"}}
    assert (await _run(client, app_id, _body(form, no, "pass", knockout_override=True))).status_code == 422  # no reason
    assert (await _run(client, app_id, _body(form, no, "pass", knockout_override=True, override_reason="   "))).status_code == 422
    yes = {"Has a valid work permit?": {"answer": "yes"}}
    assert (await _run(client, app_id, _body(form, yes, "pass", knockout_override=True, override_reason="Nothing to override"))).status_code == 422
    rows = await db_session.scalar(select(func.count()).select_from(ScreeningSession).where(ScreeningSession.application_id == uuid.UUID(app_id)))
    assert rows == 0


@pytest.mark.asyncio
async def test_only_a_team_lead_approves_and_a_stale_version_is_409(client, db_session):
    manager, recruiter, job, _ = await _world(client, db_session)
    form = await _form(client, job, [_knockout()])
    assert (await client.post(f"{REQ}/{job.id}/screening-form/approve-knockouts", json={"version": form["version"]})).status_code == 403
    await login(client, manager)
    assert (await client.post(f"{REQ}/{job.id}/screening-form/approve-knockouts", json={"version": form["version"] - 1})).status_code == 409
    read = (await client.get(f"{REQ}/{job.id}/screening-form")).json()
    assert read["can_approve"] is True and read["can_edit"] is True
    assert (await client.post(f"{REQ}/{job.id}/screening-form/approve-knockouts", json={"version": form["version"]})).status_code == 200
    assert (await client.post(f"{REQ}/{job.id}/screening-form/approve-knockouts", json={"version": form["version"]})).status_code == 409  # nothing pending


@pytest.mark.asyncio
async def test_approval_survives_an_unrelated_edit_but_not_a_knockout_change(client, db_session):
    manager, recruiter, job, _ = await _world(client, db_session)
    form = await _form(client, job, [_knockout(), _q()])
    await _approve(client, db_session, manager, recruiter, job, form["version"])
    kept = await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_knockout(), _q("Another question?")]})
    assert kept.json()["form"]["knockout_status"] == "approved"
    changed = await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_knockout("Can start this month?")]})
    assert changed.json()["form"]["knockout_status"] == "pending" and changed.json()["form"]["knockout_approved_by"] is None
    removed = await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_q()]})
    assert removed.json()["form"]["knockout_status"] == "none"


# --- AC3 / S9 / S11: sessions --------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac3_two_sessions_keep_their_history_and_the_status_does_not_move(client, db_session):
    _, recruiter, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("Years with Java?", fmt="numeric"), _q("Rate their English", "communication", "rating")])
    first = await _run(client, app_id, _body(form, {"Years with Java?": {"answer": "4", "score": 3}}, "hold", notes="Call back Friday"))
    assert first.status_code == 201, first.text
    second = await _run(client, app_id, _body(form, {"Years with Java?": {"answer": "4.5", "score": 5}, "Rate their English": {"answer": "4"}}, "pass"))
    assert second.status_code == 201, second.text
    read = (await client.get(f"{APPS}/{app_id}/screening-sessions")).json()
    assert read["can_run"] is True and read["form"]["version"] == form["version"]
    newest, oldest = read["sessions"]
    assert oldest["notes"] == "Call back Friday" and oldest["recommendation"] == "hold" and oldest["answers"][0]["answer"] == "4"
    assert oldest["scorecard"] == {"total": 3, "max": 5, "percent": 60}
    assert newest["recommendation_label"] == "Pass" and newest["screened_by"]["id"] == str(recruiter.id)
    assert newest["scorecard"] == {"total": 9, "max": 10, "percent": 90}  # S10: the rating scored itself
    application = await db_session.get(JobApplication, uuid.UUID(app_id))
    await db_session.refresh(application)
    assert application.status == "sourced"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fmt", "extra", "answer"),
    [("yes_no", {}, "maybe"), ("numeric", {}, "four"), ("numeric", {}, "NaN"), ("choice", {"choices": ["A", "B"]}, "C"), ("rating", {}, "6"), ("rating", {}, "2.5"), ("text", {}, "x" * 2001), ("text", {}, "   ")],
)
async def test_an_answer_must_fit_its_format(client, db_session, fmt, extra, answer):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("The question?", fmt=fmt, **extra)])
    assert (await _run(client, app_id, _body(form, {"The question?": {"answer": answer}}))).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("patch", [{"score": 6}, {"score": -1}, {"score": 2.5}])
async def test_a_score_must_be_0_to_5(client, db_session, patch):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("The question?")])
    assert (await _run(client, app_id, _body(form, {"The question?": {"answer": "ok", **patch}}))).status_code == 422


@pytest.mark.asyncio
async def test_foreign_duplicate_or_stale_questions_are_refused(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("The question?")])
    qid = form["questions"][0]["id"]
    foreign = {"form_version": form["version"], "recommendation": "hold", "answers": [{"question_id": str(uuid.uuid4()), "answer": "x"}]}
    assert (await _run(client, app_id, foreign)).status_code == 422
    twice = {"form_version": form["version"], "recommendation": "hold", "answers": [{"question_id": qid, "answer": "x"}, {"question_id": qid, "answer": "y"}]}
    assert (await _run(client, app_id, twice)).status_code == 422
    assert (await _run(client, app_id, {"form_version": form["version"], "recommendation": "maybe", "answers": []})).status_code == 422
    assert (await _run(client, app_id, {**_body(form, {}, "hold"), "notes": "x" * 2001})).status_code == 422


@pytest.mark.asyncio
async def test_edge_a_form_change_keeps_earlier_sessions_on_their_own_version(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    v1 = await _form(client, job, [_q("First question?")])
    assert (await _run(client, app_id, _body(v1, {"First question?": {"answer": "old", "score": 2}}, "hold"))).status_code == 201
    v2 = (await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_q("Second question?")]})).json()["form"]
    assert v2["version"] == v1["version"] + 1
    stale = await _run(client, app_id, _body(v1, {"First question?": {"answer": "late"}}, "hold"))
    assert stale.status_code == 409 and "changed" in stale.json()["detail"]
    assert (await _run(client, app_id, _body(v2, {"Second question?": {"answer": "new"}}, "pass"))).status_code == 201
    newest, oldest = (await client.get(f"{APPS}/{app_id}/screening-sessions")).json()["sessions"]
    assert oldest["form_version"] == v1["version"] and oldest["answers"][0]["question"] == "First question?" and oldest["answers"][0]["answer"] == "old"
    assert newest["form_version"] == v2["version"] and newest["answers"][0]["question"] == "Second question?"


@pytest.mark.asyncio
async def test_a_session_needs_a_form_and_an_open_application(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    assert (await _run(client, app_id, {"form_version": 1, "answers": [], "recommendation": "hold"})).status_code == 409
    form = await _form(client, job, [_q("The question?")])
    assert (await _move(client, app_id, "withdrawn", "Closed")).status_code == 200
    closed = await _run(client, app_id, _body(form, {}, "hold"))
    assert closed.status_code == 409 and closed.json()["detail"] == checklist.NOT_OPEN
    assert (await client.get(f"{APPS}/{app_id}/screening-sessions")).json()["can_run"] is False


@pytest.mark.asyncio
async def test_a_form_cannot_change_on_a_closed_requirement(client, db_session):
    _, _, job, _ = await _world(client, db_session)
    job.status = "cancelled"
    await db_session.commit()
    assert (await client.post(f"{REQ}/{job.id}/screening-form", json={})).status_code == 409
    assert (await client.get(f"{REQ}/{job.id}/screening-form")).json()["can_edit"] is False


@pytest.mark.asyncio
async def test_audit_and_timeline_carry_the_recommendation_never_the_answers(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("The question?")])
    secret = f"secret-{uuid.uuid4().hex}"
    assert (await _run(client, app_id, _body(form, {"The question?": {"answer": secret}}, "pass", notes=secret))).status_code == 201
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.entity_id == app_id, AuditLog.action == checklist.AUDIT))
    assert audit.metadata_json["result"] == "pass" and secret not in str(audit.metadata_json)
    candidate_id = (await db_session.get(JobApplication, uuid.UUID(app_id))).candidate_id
    timeline = await client.get(f"/api/v1/recruiter/candidates/{candidate_id}/timeline")
    assert timeline.status_code == 200 and secret not in timeline.text
    assert any(i.get("kind") == "screening" and i.get("to_label") == "Pass" for i in timeline.json()["items"])


@pytest.mark.asyncio
async def test_s14_a_form_session_alone_counts_as_screened(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    application = await db_session.get(JobApplication, uuid.UUID(app_id))
    candidate_id = application.candidate_id
    assert (await _move(client, app_id, "withdrawn", "Closed")).status_code == 200
    await db_session.refresh(application)
    application.updated_at = datetime.now(UTC) - timedelta(days=60)  # past the "active" window, so only the screening can decide
    await db_session.commit()
    assert (await candidate_engagement.of(db_session, [candidate_id]))[candidate_id] != "screened"
    form = await _form(client, job, [_q("The question?")])
    recruiter = application.added_by_user_id
    db_session.add(ScreeningSession(application_id=application.id, kind="form", form_id=uuid.UUID(form["id"]), form_version=form["version"], screened_by_user_id=recruiter, recommendation="hold"))
    await db_session.commit()
    assert (await candidate_engagement.of(db_session, [candidate_id]))[candidate_id] == "screened"


# --- S2 / S3: the checklist's history ------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_each_changed_checklist_save_appends_a_legacy_session(client, db_session):
    _, _, _, app_id = await _world(client, db_session)
    url = f"{APPS}/{app_id}/screening"
    assert (await client.put(url, json={"result": "hold", "notice_days": 60, "remarks": "Waiting", "expected_salary": 500000})).status_code == 200
    assert (await client.put(url, json={"result": "hold", "notice_days": 60, "remarks": "Waiting", "expected_salary": 500000})).status_code == 200  # unchanged
    assert (await client.put(url, json={"result": "need_more_info", "notice_days": 30})).status_code == 200
    newest, oldest = (await client.get(f"{APPS}/{app_id}/screening-sessions")).json()["sessions"]
    assert oldest["kind"] == "legacy" and oldest["recommendation"] == "hold" and oldest["notes"] == "Waiting"
    assert oldest["checklist"]["notice_days"] == 60 and oldest["checklist"]["expected_salary"] == 500000.0 and oldest["checklist"]["result_label"] == "Hold"
    assert newest["checklist"]["notice_days"] == 30 and newest["recommendation"] == "hold" and newest["checklist"]["result_label"] == "Need More Information"
    assert newest["answers"] == [] and newest["scorecard"] is None


# --- AC4: comparison -----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_ac4_the_comparison_shows_each_candidates_latest_scores_best_first(client, db_session):
    _, recruiter, job, first = await _world(client, db_session)
    second = await _second_application(client, db_session, recruiter, job)
    unscreened = await _second_application(client, db_session, recruiter, job)
    form = await _form(client, job, [_q("Java?"), _q("English?", "communication")])
    await _run(client, first, _body(form, {"Java?": {"answer": "weak", "score": 1}}, "hold"))
    await _run(client, first, _body(form, {"Java?": {"answer": "better", "score": 2}, "English?": {"answer": "ok", "score": 2}}, "hold"))
    await _run(client, second, _body(form, {"Java?": {"answer": "strong", "score": 5}, "English?": {"answer": "good", "score": 4}}, "pass"))
    response = await client.get(f"{REQ}/{job.id}/screening-comparison")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == form["version"] and body["versions"] == [2, 1] and body["truncated"] is False  # 1 = the template's copy
    assert [q["text"] for q in body["questions"]] == ["Java?", "English?"]
    assert [r["application_id"] for r in body["rows"]] == [second, first]
    assert unscreened not in [r["application_id"] for r in body["rows"]]
    best, other = body["rows"]
    assert best["scorecard"] == {"total": 9, "max": 10, "percent": 90} and best["recommendation_label"] == "Pass" and best["candidate"]["name"]
    java = body["questions"][0]["id"]
    assert best["answers"][java] == {"answer": "strong", "score": 5} and other["answers"][java]["score"] == 2  # the latest session


@pytest.mark.asyncio
async def test_comparison_is_per_version_and_empty_states_are_clean(client, db_session):
    _, recruiter, job, app_id = await _world(client, db_session)
    empty = await client.get(f"{REQ}/{job.id}/screening-comparison")
    assert empty.status_code == 200 and empty.json() == {"version": None, "versions": [], "questions": [], "rows": [], "truncated": False}
    v1 = await _form(client, job, [_q("Old?")])
    await _run(client, app_id, _body(v1, {"Old?": {"answer": "a", "score": 4}}, "pass"))
    v2 = (await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_q("New?")]})).json()["form"]
    current = (await client.get(f"{REQ}/{job.id}/screening-comparison")).json()
    assert current["version"] == v2["version"] and current["rows"] == [] and current["versions"] == [v2["version"], v1["version"], 1]
    old = (await client.get(f"{REQ}/{job.id}/screening-comparison", params={"version": v1["version"]})).json()
    assert [q["text"] for q in old["questions"]] == ["Old?"] and old["rows"][0]["scorecard"]["total"] == 4
    assert (await client.get(f"{REQ}/{job.id}/screening-comparison", params={"version": 99})).status_code == 404


@pytest.mark.asyncio
async def test_comparison_caps_at_fifty_candidates(client, db_session, monkeypatch):
    monkeypatch.setattr(screening_forms, "COMPARISON_LIMIT", 1)
    _, recruiter, job, first = await _world(client, db_session)
    second = await _second_application(client, db_session, recruiter, job)
    form = await _form(client, job, [_q("Java?")])
    await _run(client, first, _body(form, {"Java?": {"answer": "a", "score": 1}}, "hold"))
    await _run(client, second, _body(form, {"Java?": {"answer": "b", "score": 5}}, "pass"))
    body = (await client.get(f"{REQ}/{job.id}/screening-comparison")).json()
    assert len(body["rows"]) == 1 and body["truncated"] is True


# --- S12: compensation ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_compensation_answers_follow_the_grant(client, db_session):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("Expected package?", "compensation"), _q("Java?")])
    sent = _body(form, {"Expected package?": {"answer": "987654 per year", "score": 3}, "Java?": {"answer": "yes"}}, "pass")
    assert (await _run(client, app_id, sent)).status_code == 201
    await client.put(f"{APPS}/{app_id}/screening", json={"result": "hold", "expected_salary": 987654})
    bdm = await make_user(db_session, "bdm", "global")
    (await db_session.get(Company, job.company_id)).assigned_bdm_user_id = bdm.id
    await db_session.commit()
    await login(client, bdm)
    read = await client.get(f"{APPS}/{app_id}/screening-sessions")
    assert read.status_code == 200 and "987654" not in read.text
    answers = [s for s in read.json()["sessions"] if s["kind"] == "form"][0]["answers"]
    hidden = next(a for a in answers if a["question"] == "Expected package?")
    assert hidden["answer"] is None and hidden["answer_hidden"] is True and hidden["score"] == 3
    compared = await client.get(f"{REQ}/{job.id}/screening-comparison")
    assert compared.status_code == 200 and "987654" not in compared.text


@pytest.mark.asyncio
async def test_a_writer_without_the_grant_cannot_answer_compensation(client, db_session, monkeypatch):
    _, _, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("Expected package?", "compensation"), _q("Java?")])

    async def no(_db, _user):
        return False

    monkeypatch.setattr(candidates, "sees_compensation", no)
    refused = await _run(client, app_id, _body(form, {"Expected package?": {"answer": "1"}}, "hold"))
    assert refused.status_code == 403
    assert (await _run(client, app_id, _body(form, {"Java?": {"answer": "yes"}}, "hold"))).status_code == 201


# --- RBAC (S13) ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manager_edits_the_form_and_bank_but_cannot_run_a_session(client, db_session):
    manager, recruiter, job, app_id = await _world(client, db_session)
    form = await _form(client, job, [_q("The question?")])
    await login(client, manager)
    assert (await client.put(f"{REQ}/{job.id}/screening-form", json={"questions": [_q("Manager's?")]})).status_code == 200
    assert (await client.post(BANK, json=_q(f"Manager {uuid.uuid4().hex[:8]}?"))).status_code == 201
    read = (await client.get(f"{APPS}/{app_id}/screening-sessions")).json()
    assert read["can_run"] is False and read["form"] is not None
    assert (await _run(client, app_id, {"form_version": form["version"] + 1, "answers": [], "recommendation": "hold"})).status_code == 403


@pytest.mark.asyncio
async def test_another_recruiters_requirement_is_404(client, db_session):
    _, recruiter = await _team(client, db_session)
    _, other = await _team(client, db_session)
    await login(client, other)
    job = await _requirement(db_session, other)
    app_id = (await _add(client, job, await _candidate(db_session, other))).json()["application"]["id"]
    await login(client, recruiter)
    assert (await client.get(f"{REQ}/{job.id}/screening-form")).status_code == 404
    assert (await client.post(f"{REQ}/{job.id}/screening-form", json={})).status_code == 404
    assert (await client.get(f"{REQ}/{job.id}/screening-comparison")).status_code == 404
    assert (await client.get(f"{APPS}/{app_id}/screening-sessions")).status_code == 404
    assert (await client.post(f"{APPS}/{app_id}/screening-sessions", json={"form_version": 1, "answers": [], "recommendation": "hold"})).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("employer", "it"), ("hr_team", "it"), ("overseas_admin", "overseas"), ("telecaller", "global"), ("bdm", "global")])
async def test_outsiders_cannot_touch_the_bank(client, db_session, role, division):
    await as_role(client, db_session, role, division)
    assert (await client.get(BANK)).status_code == 403
    assert (await client.post(BANK, json=_q())).status_code == 403
    assert (await client.get(TEMPLATES)).status_code == 403
    assert (await client.post(TEMPLATES, json={"name": "x", "questions": [_q()]})).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("it_student", "it"), ("employer", "it"), ("hr_team", "it")])
async def test_outsiders_cannot_read_a_requirements_form_or_sessions(client, db_session, role, division):
    _, _, job, app_id = await _world(client, db_session)
    await as_role(client, db_session, role, division)
    assert (await client.get(f"{REQ}/{job.id}/screening-form")).status_code == 403
    assert (await client.get(f"{REQ}/{job.id}/screening-comparison")).status_code == 403
    assert (await client.get(f"{APPS}/{app_id}/screening-sessions")).status_code == 403


@pytest.mark.asyncio
async def test_signed_out_is_401(client):
    for path in (BANK, TEMPLATES, f"{REQ}/{uuid.uuid4()}/screening-form", f"{REQ}/{uuid.uuid4()}/screening-comparison", f"{APPS}/{uuid.uuid4()}/screening-sessions"):
        assert (await client.get(path)).status_code == 401
