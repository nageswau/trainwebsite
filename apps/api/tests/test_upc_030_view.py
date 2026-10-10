"""upc-030 -- University 360 view for other roles (DEC-SCOPE-161 UV1-UV12; spec AC1-AC7).

The slicing is the confidentiality boundary: each slice is an allow-list, so the snapshot tests pin the exact key sets."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from app.models import AuditLog, OverseasApplication, OverseasCourse, University, UniversityContact
from tests.bdm001_helpers import login as bdm_login
from tests.bdm001_helpers import make_manager
from tests.bdm002_helpers import make_bdm
from tests.test_rec_009_resumes import PDF
from tests.upc003_helpers import as_role, catalogue_country, create, login, make_head, make_pm, make_user, url

PROFILE_KEYS = {
    "id", "university_code", "name", "institution_type", "ownership_type", "country", "state_region", "city", "website", "overview",
    "eligibility", "course_levels", "popular_programs", "rankings",
}  # fmt: skip
CONTACT_KEYS = {"id", "name", "designation", "department", "role", "email", "phone", "whatsapp", "linkedin", "preferred_channel", "is_primary"}
COURSE_KEYS = {
    "id", "title", "level", "category", "duration", "tuition_fee", "tuition_amount", "tuition_currency", "application_fee",
    "application_fee_currency", "intakes", "intake", "entry_requirements", "english_test", "english_score", "scholarships",
    "application_process", "deadline",
}  # fmt: skip
DOCUMENT_KEYS = {"id", "kind", "title", "current_version", "updated_at"}
APPLICATION_KEYS = {"id", "reference", "student_name", "intake", "status", "next_action", "updated_at"}
SLICE_KEYS = {
    "counselor": {"slice", "university", "partnership", "contacts", "courses", "documents", "applications"},
    "overseas_admin": {"slice", "university", "partnership", "contacts", "courses", "documents", "applications"},
    "bdm": {"slice", "university", "partnership", "manager"},
    "university_rep": {"slice", "university", "courses"},
}


def view_url(university_id) -> str:
    return f"/api/v1/universities/{university_id}/view"


def view_file_url(university_id, document_id) -> str:
    return f"{view_url(university_id)}/documents/{document_id}/file"


async def _upload(client, university_id, kind: str, title: str) -> dict:
    response = await client.post(url(university_id, "documents"), data={"kind": kind, "title": title}, files={"file": ("f.pdf", PDF, "application/octet-stream")})
    assert response.status_code == 201, response.text
    return response.json()["document"]


async def _world(client, db, *, published: bool = True):
    """A published university managed by `pm`, with a shareable and an internal contact, an active course with commission and an
    inactive one, a shareable document, an internal one and a commission agreement. Returns a dict of the pieces."""
    head = await make_head(db)
    pm = await make_pm(db, head, name=f"Priya Manager {uuid.uuid4().hex[:4]}")
    await login(client, head)
    uni = await create(client, (await catalogue_country(db)).id)
    assert (await client.post(url(uni["id"], "assign"), json={"primary_manager_user_id": str(pm.id)})).status_code == 200
    uid = uuid.UUID(uni["id"])
    await db.execute(update(University).where(University.id == uid).values(catalogue_visible=published))
    shared = UniversityContact(university_id=uid, name="Asha Admissions", email="asha@abc.example", is_primary=True, shareable=True, notes="secret note", relationship_strength="strong")
    internal = UniversityContact(university_id=uid, name="Victor VP", email="victor@abc.example", shareable=False)
    course = OverseasCourse(
        university_id=uid,
        title="MSc Data Science",
        level="PG",
        category="Computing",
        duration="1 year",
        tuition_fee="GBP 20,000",
        intake="Sep",
        english_test="IELTS",
        english_score=Decimal("6.5"),
        entry_requirements="A 2:1 degree",
        commission_percent=Decimal("15"),
    )
    old = OverseasCourse(university_id=uid, title="BA Retired", level="UG", category="Arts", duration="3 years", tuition_fee="-", intake="Sep", active=False)
    db.add_all([shared, internal, course, old])
    await db.commit()
    await login(client, pm)
    docs = {
        "fees": await _upload(client, uni["id"], "fee_structure", "Fees 2026"),
        "mou": await _upload(client, uni["id"], "mou", "MoU"),
        "commission": await _upload(client, uni["id"], "commission_agreement", "Commission"),
    }
    return {"head": head, "pm": pm, "uni": uni, "uid": uid, "shared": shared, "internal": internal, "course": course, "old": old, "docs": docs}


async def _application(db, university_id, counselor_id=None) -> OverseasApplication:
    student = await make_user(db, "overseas_student", "overseas")
    row = OverseasApplication(student_id=student.id, university_id=university_id, counselor_id=counselor_id, intake="Sep 2027", application_reference=f"APP-{uuid.uuid4().hex[:6]}")
    db.add(row)
    await db.commit()
    return row


def _keys_anywhere(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys_anywhere(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys_anywhere(v)}
    return set()


async def _rep_of(db, university_id):
    rep = await make_user(db, "university_rep", "overseas")
    rep.profile = {"university_id": str(university_id)}
    await db.commit()
    return rep


# --- AC1 + AC3: the counselor slice ---------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_slice_has_exactly_its_keys_and_shareable_content(client, db_session):
    w = await _world(client, db_session)
    counselor = await as_role(client, db_session, "counselor", "overseas")
    mine = await _application(db_session, w["uid"], counselor.id)
    await _application(db_session, w["uid"])  # someone else's student
    response = await client.get(view_url(w["uni"]["id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == SLICE_KEYS["counselor"] and body["slice"] == "counselor"
    assert set(body["university"]) == PROFILE_KEYS
    assert set(body["university"]["country"]) == {"name", "iso2", "region"}
    assert body["partnership"] == {"stage": w["uni"]["stage"], "stage_label": w["uni"]["stage_label"], "lost": False}
    assert [c["name"] for c in body["contacts"]] == ["Asha Admissions"] and set(body["contacts"][0]) == CONTACT_KEYS
    assert [c["title"] for c in body["courses"]] == ["MSc Data Science"] and set(body["courses"][0]) == COURSE_KEYS
    assert body["courses"][0]["english_test"] == "IELTS" and body["courses"][0]["english_score"] == "6.5"
    assert [d["id"] for d in body["documents"]] == [w["docs"]["fees"]["id"]] and set(body["documents"][0]) == DOCUMENT_KEYS
    assert [a["id"] for a in body["applications"]] == [str(mine.id)] and set(body["applications"][0]) == APPLICATION_KEYS
    assert body["applications"][0]["reference"] == mine.application_reference


# --- AC1 + AC2: every slice, and no commission or internal field anywhere ---------------------------------------------------------
FORBIDDEN = {
    "commission",
    "commission_terms",
    "notes",
    "relationship_strength",
    "international_office",
    "existing_relationship",
    "priority",
    "partnership_potential",
    "permissions",
    "shareable",
    "catalogue_visible",
}


@pytest.mark.asyncio
async def test_overseas_admin_slice_sees_all_applications_of_the_university(client, db_session):
    w = await _world(client, db_session)
    one, two = await _application(db_session, w["uid"]), await _application(db_session, w["uid"])
    await as_role(client, db_session, "overseas_admin", "overseas")
    body = (await client.get(view_url(w["uni"]["id"]))).json()
    assert set(body) == SLICE_KEYS["overseas_admin"] and body["slice"] == "overseas_admin"
    assert {a["id"] for a in body["applications"]} == {str(one.id), str(two.id)}
    assert not _keys_anywhere(body) & FORBIDDEN


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["bdm", "bdm_manager"])
async def test_bdm_slice_is_profile_stage_and_manager(client, db_session, role):
    w = await _world(client, db_session, published=False)  # BDMs see internal (prospect) universities too (UV3)
    manager = await make_manager(db_session)
    user = await make_bdm(db_session, manager) if role == "bdm" else manager
    await bdm_login(client, user)
    body = (await client.get(view_url(w["uni"]["id"]))).json()
    assert set(body) == SLICE_KEYS["bdm"] and body["slice"] == "bdm"
    assert set(body["university"]) == PROFILE_KEYS
    assert body["manager"] == {"full_name": w["pm"].full_name, "email": w["pm"].email}
    assert not _keys_anywhere(body) & FORBIDDEN


@pytest.mark.asyncio
async def test_bdm_manager_is_null_when_unassigned(client, db_session):
    await login(client, await make_head(db_session))
    uni = await create(client, (await catalogue_country(db_session)).id)
    await bdm_login(client, await make_manager(db_session))
    assert (await client.get(view_url(uni["id"]))).json()["manager"] is None


@pytest.mark.asyncio
async def test_bdm_without_a_profile_is_403(client, db_session):
    w = await _world(client, db_session)
    await as_role(client, db_session, "bdm", "it")
    assert (await client.get(view_url(w["uni"]["id"]))).status_code == 403


# --- AC5: university_rep -------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_university_rep_reads_own_profile_and_courses_only(client, db_session):
    w = await _world(client, db_session, published=False)
    await login(client, await _rep_of(db_session, w["uid"]))
    body = (await client.get(view_url(w["uni"]["id"]))).json()
    assert set(body) == SLICE_KEYS["university_rep"] and body["slice"] == "university_rep"
    assert [c["title"] for c in body["courses"]] == ["MSc Data Science"]
    assert not _keys_anywhere(body) & FORBIDDEN


@pytest.mark.asyncio
async def test_university_rep_of_x_reading_y_is_404(client, db_session):
    x, y = await _world(client, db_session), await _world(client, db_session)
    await login(client, await _rep_of(db_session, x["uid"]))
    assert (await client.get(view_url(y["uni"]["id"]))).status_code == 404
    unlinked = await make_user(db_session, "university_rep", "overseas")
    await login(client, unlinked)
    assert (await client.get(view_url(x["uni"]["id"]))).status_code == 404


# --- AC4: counselor scope ------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_cannot_see_unpublished_inactive_or_unknown_universities(client, db_session):
    internal = await _world(client, db_session, published=False)
    inactive = await _world(client, db_session)
    await db_session.execute(update(University).where(University.id == inactive["uid"]).values(active=False))
    await db_session.commit()
    await as_role(client, db_session, "counselor", "overseas")
    for uid in (internal["uid"], inactive["uid"], uuid.uuid4()):
        response = await client.get(view_url(uid))
        assert response.status_code == 404 and response.json()["detail"] == "University not found"


# --- AC6: roles ------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "division"), [("counselor", "it"), ("overseas_student", "overseas"), ("agent", "overseas"), ("super_admin", "global"), ("overseas_admin", "it")])
async def test_other_roles_are_403(client, db_session, role, division):
    w = await _world(client, db_session)
    await as_role(client, db_session, role, division)
    response = await client.get(view_url(w["uni"]["id"]))
    assert response.status_code == 403 and response.json()["detail"] == "University view access required"


@pytest.mark.asyncio
async def test_partnership_manager_is_403_and_signed_out_is_401(client, db_session):
    w = await _world(client, db_session)  # logged in as the pm
    assert (await client.get(view_url(w["uni"]["id"]))).status_code == 403
    await client.post("/api/v1/auth/logout")
    client.cookies.clear()
    assert (await client.get(view_url(w["uni"]["id"]))).status_code == 401


# --- AC7: documents ----------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_downloads_a_shareable_document_and_it_is_audited(client, db_session):
    w = await _world(client, db_session)
    counselor = await as_role(client, db_session, "counselor", "overseas")
    response = await client.get(view_file_url(w["uni"]["id"], w["docs"]["fees"]["id"]))
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-disposition"].startswith('attachment; filename="')
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.user_id == counselor.id, AuditLog.action == "university_document.download"))
    assert audit is not None and audit.metadata_json["role"] == "counselor"
    for hidden in (w["docs"]["mou"], w["docs"]["commission"]):
        assert (await client.get(view_file_url(w["uni"]["id"], hidden["id"]))).status_code == 404
    assert (await client.get(view_file_url(w["uni"]["id"], uuid.uuid4()))).status_code == 404


@pytest.mark.asyncio
async def test_document_download_follows_the_view_scope(client, db_session):
    w = await _world(client, db_session, published=False)
    await as_role(client, db_session, "counselor", "overseas")
    assert (await client.get(view_file_url(w["uni"]["id"], w["docs"]["fees"]["id"]))).status_code == 404
    await bdm_login(client, await make_manager(db_session))
    assert (await client.get(view_file_url(w["uni"]["id"], w["docs"]["fees"]["id"]))).status_code == 403
    await login(client, await _rep_of(db_session, w["uid"]))
    assert (await client.get(view_file_url(w["uni"]["id"], w["docs"]["fees"]["id"]))).status_code == 403
