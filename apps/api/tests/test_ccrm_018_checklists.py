"""ccrm-018 (DEC-SCOPE-248, CL1) -- document checklist templates: Overseas Admin CRUD, counselor read, validation, the one-active-
template-per-scope rule, the version guard, and resolution (most specific template wins). Spec:
docs/superpowers/specs/2026-10-23-ccrm-018-document-checklist-templates-design.md."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import AuditLog, OverseasCourse, University
from tests.agn001_helpers import client_for, mk_user, uniq
from tests.agn008_helpers import mk_application
from tests.ccrm012_helpers import mk_university

URL = "/api/v1/overseas-admin/checklists"
RESOLVE = URL + "/resolve"


def body(country_id, **overrides) -> dict:
    data = {
        "name": "UK Masters admission",
        "kind": "admission",
        "country_id": str(country_id),
        "university_id": None,
        "course_level": None,
        "intake": None,
        "gate_mode": "block",
        "notes": None,
        "items": [
            {"document_type": "Passport", "label": None, "required": True, "allowed_statuses": [], "notes": None},
            {"document_type": "CV", "label": None, "required": False, "allowed_statuses": ["draft", "review", "approved"], "notes": "Latest"},
        ],
    }
    data.update(overrides)
    return data


async def mk_course(db, university, level: str) -> OverseasCourse:
    course = OverseasCourse(university_id=university.id, title=uniq("Course"), level=level, category="Engineering", duration="1 year", tuition_fee="", intake="Sep")
    db.add(course)
    await db.commit()
    return course


@pytest_asyncio.fixture
async def world(db_session):
    uk = await mk_university(db_session, "United Kingdom")
    other_uk = University(country_id=uk.country_id, slug=uniq("ccrm018-u"), name=uniq("Other UK Uni"), city="Leeds", overview="", eligibility="", requirements=[], deadlines=[], scholarships=[])
    db_session.add(other_uk)
    await db_session.commit()
    elsewhere = await mk_university(db_session, "Canada")
    admin = await mk_user(db_session, role="overseas_admin", full_name="Checklist Admin")
    counselor = await mk_user(db_session, role="counselor", full_name="Checklist Counselor")
    other_counselor = await mk_user(db_session, role="counselor")
    student = await mk_user(db_session, role="overseas_student")
    masters = await mk_course(db_session, other_uk, "Masters")  # a legacy spelling: matches PG
    app = await mk_application(db_session, agent=None, university=other_uk, student=student, course_id=masters.id, counselor_id=counselor.id, intake="September 2027")
    return {
        "uk": uk,
        "other_uk": other_uk,
        "elsewhere": elsewhere,
        "admin": admin,
        "counselor": counselor,
        "other_counselor": other_counselor,
        "student": student,
        "app": app,
        "country": uk.country_id,
    }


@pytest.mark.asyncio
async def test_admin_creates_reads_and_lists_a_template(world, db_session):
    async with client_for(world["admin"].email) as c:
        created = await c.post(URL, json=body(world["country"], course_level="PG"))
        assert created.status_code == 201, created.text
        data = created.json()
        assert data["version"] == 1 and data["active"] is True and data["gate_mode"] == "block" and data["course_level"] == "PG"
        assert data["country_name"].startswith("United Kingdom")
        assert [i["document_type"] for i in data["items"]] == ["Passport", "CV"]
        assert data["items"][0]["allowed_statuses"][0] == "pending" and len(data["items"][0]["allowed_statuses"]) == 9  # empty -> standard
        assert data["items"][1]["allowed_statuses"] == ["draft", "review", "approved"]
        listed = await c.get(URL, params={"country_id": str(world["country"])})
        assert listed.status_code == 200
        assert [t["id"] for t in listed.json()["items"]] == [data["id"]] and listed.json()["items"][0]["item_count"] == 2
        assert (await c.get(f"{URL}/{data['id']}")).json()["name"] == "UK Masters admission"
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "checklist_template.create", AuditLog.entity_id == data["id"]))
    assert audit is not None


@pytest.mark.asyncio
async def test_counselor_reads_but_cannot_write(world):
    async with client_for(world["admin"].email) as c:
        made = (await c.post(URL, json=body(world["country"]))).json()
    async with client_for(world["counselor"].email) as c:
        assert (await c.get(URL)).status_code == 200
        assert (await c.get(f"{URL}/{made['id']}")).status_code == 200
        assert (await c.post(URL, json=body(world["country"], intake="Jan"))).status_code == 403
        assert (await c.put(f"{URL}/{made['id']}", json=body(world["country"]) | {"version": 1, "active": True})).status_code == 403


@pytest.mark.asyncio
async def test_other_roles_and_signed_out_are_refused(world, db_session, client):
    assert (await client.get(URL)).status_code == 401
    for role in ("overseas_student", "agent", "university_rep", "bdm"):
        user = await mk_user(db_session, role=role)
        async with client_for(user.email) as c:
            assert (await c.get(URL)).status_code == 403, role


@pytest.mark.asyncio
async def test_validation(world):
    async with client_for(world["admin"].email) as c:
        assert (await c.post(URL, json=body(world["country"], kind="finance"))).status_code == 422
        assert (await c.post(URL, json=body(world["country"], gate_mode="soft"))).status_code == 422
        assert (await c.post(URL, json=body(world["country"], course_level="Masters"))).status_code == 422
        assert (await c.post(URL, json=body(world["country"], items=[]))).status_code == 422
        assert (await c.post(URL, json=body(world["country"], name="   "))).status_code == 422
        other = [{"document_type": "Other", "label": None, "required": True, "allowed_statuses": [], "notes": None}]
        assert (await c.post(URL, json=body(world["country"], items=other))).status_code == 422
        bad_status = [{"document_type": "SOP", "label": None, "required": True, "allowed_statuses": ["lost"], "notes": None}]
        assert (await c.post(URL, json=body(world["country"], items=bad_status))).status_code == 422
        twice = [{"document_type": "SOP", "label": None, "required": True, "allowed_statuses": [], "notes": None}] * 2
        assert (await c.post(URL, json=body(world["country"], items=twice))).status_code == 422
        assert (await c.post(URL, json=body(world["country"]) | {"extra": 1})).status_code == 422
        wrong_country = await c.post(URL, json=body(world["country"], university_id=str(world["elsewhere"].id)))
        assert wrong_country.status_code == 422 and "country" in wrong_country.json()["detail"].lower()
        assert (await c.post(URL, json=body(uuid.uuid4()))).status_code == 422


@pytest.mark.asyncio
async def test_one_active_template_per_scope(world):
    async with client_for(world["admin"].email) as c:
        first = (await c.post(URL, json=body(world["country"], intake="September 2027"))).json()
        dup = await c.post(URL, json=body(world["country"], name="Copy", intake="september 2027 "))
        assert dup.status_code == 409
        assert (await c.post(URL, json=body(world["country"], kind="visa"))).status_code == 201  # another kind is another scope
        off = await c.put(f"{URL}/{first['id']}", json=body(world["country"], intake="September 2027") | {"version": 1, "active": False})
        assert off.status_code == 200 and off.json()["active"] is False
        assert (await c.post(URL, json=body(world["country"], name="Replacement", intake="September 2027"))).status_code == 201
        back = await c.put(f"{URL}/{first['id']}", json=body(world["country"], intake="September 2027") | {"version": 2, "active": True})
        assert back.status_code == 409  # the replacement holds the scope now


@pytest.mark.asyncio
async def test_edit_bumps_version_replaces_items_and_refuses_a_stale_version(world, db_session):
    async with client_for(world["admin"].email) as c:
        made = (await c.post(URL, json=body(world["country"]))).json()
        items = [{"document_type": "Transcripts", "label": None, "required": True, "allowed_statuses": [], "notes": None}]
        edited = await c.put(f"{URL}/{made['id']}", json=body(world["country"], gate_mode="warn", items=items) | {"version": 1, "active": True})
        assert edited.status_code == 200, edited.text
        assert edited.json()["version"] == 2 and edited.json()["gate_mode"] == "warn"
        assert [i["document_type"] for i in edited.json()["items"]] == ["Transcripts"]
        stale = await c.put(f"{URL}/{made['id']}", json=body(world["country"]) | {"version": 1, "active": True})
        assert stale.status_code == 409
        assert (await c.put(f"{URL}/{uuid.uuid4()}", json=body(world["country"]) | {"version": 1, "active": True})).status_code == 404
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "checklist_template.update", AuditLog.entity_id == made["id"]))
    assert audit is not None and audit.metadata_json["version"] == 2


@pytest.mark.asyncio
async def test_most_specific_template_applies(world):
    """Acceptance: a UK/Masters template applies to a UK Masters application; a university-specific one overrides it."""
    app = world["app"]
    async with client_for(world["admin"].email) as c:
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json() == {"template": None}
        country_wide = (await c.post(URL, json=body(world["country"], name="UK any"))).json()
        masters = (await c.post(URL, json=body(world["country"], name="UK Masters", course_level="PG"))).json()
        await c.post(URL, json=body(world["country"], name="UK UG", course_level="UG"))
        await c.post(URL, json=body(world["country"], name="Other uni", university_id=str(world["uk"].id)))
        await c.post(URL, json=body(world["elsewhere"].country_id, name="Canada PG", course_level="PG"))
        await c.post(URL, json=body(world["country"], name="UK visa", kind="visa", course_level="PG", intake="September 2027"))
        resolved = (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json()["template"]
        assert resolved["id"] == masters["id"] and [i["document_type"] for i in resolved["items"]] == ["Passport", "CV"]
        intake = (await c.post(URL, json=body(world["country"], name="UK Sep", intake="SEPTEMBER 2027"))).json()
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json()["template"]["id"] == masters["id"]
        uni = (await c.post(URL, json=body(world["country"], name="This uni", university_id=str(world["other_uk"].id)))).json()
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json()["template"]["id"] == uni["id"]
        await c.put(f"{URL}/{uni['id']}", json=body(world["country"], name="This uni", university_id=str(world["other_uk"].id)) | {"version": 1, "active": False})
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json()["template"]["id"] == masters["id"]
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "visa"})).json()["template"]["name"] == "UK visa"
        assert country_wide["id"] and intake["id"]


@pytest.mark.asyncio
async def test_an_application_without_a_course_matches_only_level_free_templates(world, db_session):
    app = await mk_application(db_session, agent=None, university=world["other_uk"], student=world["student"], counselor_id=world["counselor"].id)
    async with client_for(world["admin"].email) as c:
        await c.post(URL, json=body(world["country"], name="UK Masters", course_level="PG"))
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json() == {"template": None}
        anyone = (await c.post(URL, json=body(world["country"], name="UK any"))).json()
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).json()["template"]["id"] == anyone["id"]


@pytest.mark.asyncio
async def test_resolve_is_scoped_to_the_counselors_applications(world):
    app = world["app"]
    async with client_for(world["counselor"].email) as c:
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).status_code == 200
    async with client_for(world["other_counselor"].email) as c:
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "admission"})).status_code == 403
    async with client_for(world["admin"].email) as c:
        assert (await c.get(RESOLVE, params={"application_id": str(uuid.uuid4()), "kind": "admission"})).status_code == 404
        assert (await c.get(RESOLVE, params={"application_id": str(app.id), "kind": "nope"})).status_code == 422
