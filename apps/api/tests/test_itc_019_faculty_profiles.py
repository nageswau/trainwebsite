"""itc-019 (DEC-SCOPE-347) -- trainer profiles (trainer edits own, IT Admin edits any) and the student faculty view: hidden fields are
never serialised (AC1), the photo goes through the upload policy (AC2), a student sees only their own active batches' trainers (404)."""

import datetime as dt
import uuid

import pytest
from sqlalchemy import select

from app.models import AuditLog, Batch, Enrollment, Program, TrainerProfile
from app.services import trainer_profiles
from app.services.storage import storage
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, make_student
from tests.test_nehn_035_university_logos import png

OWN = "/api/v1/it/trainer/profile"
MINE = "/api/v1/it/student/faculty"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def admin_url(trainer_id, tail: str = "") -> str:
    return f"/api/v1/it/trainers/{trainer_id}/profile{tail}"


def faculty_url(trainer_id) -> str:
    return f"/api/v1/it/faculty/{trainer_id}"


def body(**extra) -> dict:
    return {"designation": "Senior Python Trainer", "expertise": ["Python", "Django"], "bio": "Ten years of teaching.", "office_hours": "Mon–Fri 6–7 pm",
            "contact_route": "in_app", "show_email": False, "show_phone": False, "show_photo": True, "show_bio": True, "show_office_hours": True, **extra}  # fmt: skip


async def make_trainer(db, phone: str | None = "+919800000019"):
    trainer = await make_user(db, "trainer", "it")
    trainer.phone = phone
    await db.commit()
    return trainer


async def make_batch(db, trainer=None) -> Batch:
    program = Program(slug=f"itc019-{uuid.uuid4().hex[:8]}", category="Software Development", title=f"Python {uuid.uuid4().hex[:6]}", summary="",
                      duration="8 weeks", eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="", trainer_name="T", active=True)  # fmt: skip
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, name=f"PY-{uuid.uuid4().hex[:6]}", start_date=dt.date.today(), end_date=dt.date.today() + dt.timedelta(days=60),
                  schedule="Mon/Wed/Fri 7-9 pm", capacity=20, enrollment_open=True, status="active", trainer_id=trainer.id if trainer else None)  # fmt: skip
    db.add(batch)
    await db.commit()
    return batch


async def seat(db, student, batch, status="active") -> None:
    db.add(Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-019-{uuid.uuid4().hex[:8]}", status=status))
    await db.commit()


async def profiled_trainer(client, db, **extra):
    trainer = await make_trainer(db)
    await as_user(client, trainer)
    response = await client.put(OWN, json=body(**extra))
    assert response.status_code == 200, response.text
    return trainer


# --- trainer edits own -----------------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_trainer_without_a_profile_gets_private_defaults(client, db_session):
    trainer = await make_trainer(db_session)
    await as_user(client, trainer)
    data = (await client.get(OWN)).json()
    assert data["designation"] is None and data["expertise"] == [] and data["photo_url"] is None
    assert data["contact_route"] == "in_app" and data["show_email"] is False and data["show_phone"] is False  # F1: personal fields hidden
    assert data["account_email"] == trainer.email and data["account_phone"] == trainer.phone


@pytest.mark.asyncio
async def test_plus_the_trainer_sets_office_hours_and_it_is_saved_and_audited(client, db_session):
    trainer = await profiled_trainer(client, db_session, expertise=[" Python ", "python", "", "SQL"])
    data = (await client.get(OWN)).json()
    assert data["office_hours"] == "Mon–Fri 6–7 pm" and data["designation"] == "Senior Python Trainer"
    assert data["expertise"] == ["Python", "SQL"]  # trimmed, blank and case-insensitive duplicates dropped
    row = await db_session.scalar(select(AuditLog).where(AuditLog.action == "trainer.profile.update", AuditLog.entity_id == str(trainer.id)))
    assert row is not None and "office_hours" in row.metadata_json["fields"] and "Mon" not in str(row.metadata_json)  # names only


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "patch",
    [{"designation": "x" * 121}, {"office_hours": "x" * 161}, {"bio": "x" * 2001}, {"expertise": ["x" * 61]}, {"expertise": [f"t{i}" for i in range(13)]},
     {"contact_route": "fax"}, {"nickname": "Sam"}],
)  # fmt: skip
async def test_invalid_profile_fields_are_422(client, db_session, patch):
    trainer = await make_trainer(db_session)
    await as_user(client, trainer)
    assert (await client.put(OWN, json=body(**patch))).status_code == 422


@pytest.mark.asyncio
async def test_a_contact_route_needs_its_channel_visible_and_present(client, db_session):
    trainer = await make_trainer(db_session, phone=None)
    await as_user(client, trainer)
    assert (await client.put(OWN, json=body(contact_route="email"))).status_code == 422  # email hidden
    assert (await client.put(OWN, json=body(contact_route="phone", show_phone=True))).status_code == 422  # no phone on the account
    assert (await client.put(OWN, json=body(contact_route="email", show_email=True))).status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_student", "counselor", "hr_team"])
async def test_other_roles_cannot_use_the_trainer_profile_routes(client, db_session, role):
    await as_user(client, await make_user(db_session, role, "it"))
    assert (await client.get(OWN)).status_code == 403
    assert (await client.put(OWN, json=body())).status_code == 403


# --- AC2: the photo goes through the upload policy ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac2_a_valid_photo_is_stored_privately_and_replacing_or_removing_deletes_the_old_file(client, db_session):
    trainer = await make_trainer(db_session)
    await as_user(client, trainer)
    first = await client.put(f"{OWN}/photo", files={"file": ("me.png", png(200, 200), "image/png")})
    assert first.status_code == 200, first.text
    key_one = await db_session.scalar(select(TrainerProfile.photo_key).where(TrainerProfile.user_id == trainer.id).execution_options(populate_existing=True))
    assert key_one.startswith(trainer_profiles.PREFIX + "/") and first.json()["photo_url"]
    assert (await client.get(first.json()["photo_url"])).status_code == 200  # the signed link serves the image
    await client.put(f"{OWN}/photo", files={"file": ("me2.png", png(300, 300), "image/png")})
    with pytest.raises(FileNotFoundError):
        storage.read_bytes(key_one)
    removed = await client.delete(f"{OWN}/photo")
    assert removed.status_code == 200 and removed.json()["photo_url"] is None
    assert await db_session.scalar(select(AuditLog).where(AuditLog.action == "trainer.profile.photo", AuditLog.entity_id == str(trainer.id))) is not None


@pytest.mark.asyncio
async def test_ac2_invalid_photos_are_refused(client, db_session):
    await as_user(client, await make_trainer(db_session))
    put = lambda data, ct="image/png": client.put(f"{OWN}/photo", files={"file": ("p.png", data, ct)})  # noqa: E731
    assert (await put(png(64, 64))).status_code == 422  # below 120 px
    assert (await put(b"<svg onload=alert(1)>", "image/svg+xml")).status_code == 415
    assert (await put(PDF, "application/pdf")).status_code == 415
    assert (await put(PDF, "image/png")).status_code == 415  # bytes do not match the claimed type
    assert (await put(png() + b"0" * (2 * 1024 * 1024))).status_code == 413


# --- IT Admin edits any trainer ----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_it_admin_edits_a_trainers_profile_and_non_trainers_are_404(client, db_session):
    trainer = await make_trainer(db_session)
    await as_user(client, await make_user(db_session, "it_admin", "it"))
    assert (await client.put(admin_url(trainer.id), json=body(designation="Lead Trainer"))).status_code == 200
    assert (await client.get(admin_url(trainer.id))).json()["designation"] == "Lead Trainer"
    student = await make_student(db_session)
    assert (await client.get(admin_url(student.id))).status_code == 404
    assert (await client.get(admin_url(uuid.uuid4()))).status_code == 404
    assert (await client.put(admin_url(trainer.id, "/photo"), files={"file": ("a.png", png(200, 200), "image/png")})).status_code == 200


@pytest.mark.asyncio
async def test_a_trainer_cannot_use_the_admin_routes(client, db_session):
    other = await make_trainer(db_session)
    await as_user(client, await make_trainer(db_session))
    assert (await client.put(admin_url(other.id), json=body())).status_code == 403


# --- student view: AC1, −, E -----------------------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac1_a_hidden_phone_and_email_never_appear_in_any_student_response(client, db_session):
    trainer = await profiled_trainer(client, db_session, show_bio=False)
    batch = await make_batch(db_session, trainer)
    student = await make_student(db_session)
    await seat(db_session, student, batch)
    await as_user(client, student)
    mine = await client.get(MINE)
    one = await client.get(faculty_url(trainer.id))
    course = await client.get("/api/v1/portal/it/student/course")
    for response in (mine, one, course):
        assert response.status_code == 200, response.text
        assert trainer.phone not in response.text and trainer.email not in response.text
    faculty = mine.json()["items"][0]["faculty"]
    assert faculty["name"] == trainer.full_name and faculty["office_hours"] == "Mon–Fri 6–7 pm"
    assert {"phone", "email", "bio"}.isdisjoint(faculty) and {"phone", "email", "bio"}.isdisjoint(one.json())  # omitted, not null
    assert course.json()["rows"][0]["trainer"] == trainer.full_name  # the course payload names the trainer


@pytest.mark.asyncio
async def test_a_visible_phone_is_shown_to_the_student(client, db_session):
    trainer = await profiled_trainer(client, db_session, show_phone=True, contact_route="phone")
    batch = await make_batch(db_session, trainer)
    student = await make_student(db_session)
    await seat(db_session, student, batch)
    await as_user(client, student)
    data = (await client.get(faculty_url(trainer.id))).json()
    assert data["phone"] == trainer.phone and data["contact_route"] == "phone" and "email" not in data


@pytest.mark.asyncio
async def test_minus_a_student_of_another_batch_gets_404(client, db_session):
    trainer = await profiled_trainer(client, db_session)
    await make_batch(db_session, trainer)
    other = await make_student(db_session)
    await seat(db_session, other, await make_batch(db_session, await make_trainer(db_session)))
    await as_user(client, other)
    assert (await client.get(faculty_url(trainer.id))).status_code == 404
    assert (await client.get(faculty_url(uuid.uuid4()))).status_code == 404
    assert all(item["faculty"]["trainer_id"] != str(trainer.id) for item in (await client.get(MINE)).json()["items"])


@pytest.mark.asyncio
async def test_an_inactive_enrolment_does_not_open_the_profile(client, db_session):
    trainer = await profiled_trainer(client, db_session)
    student = await make_student(db_session)
    await seat(db_session, student, await make_batch(db_session, trainer), status="pending")
    await as_user(client, student)
    assert (await client.get(faculty_url(trainer.id))).status_code == 404
    assert (await client.get(MINE)).json()["items"] == []


@pytest.mark.asyncio
async def test_e_a_batch_with_no_trainer_lists_no_faculty(client, db_session):
    student = await make_student(db_session)
    batch = await make_batch(db_session)
    await seat(db_session, student, batch)
    await as_user(client, student)
    items = (await client.get(MINE)).json()["items"]
    assert items == [{"batch_id": str(batch.id), "batch": batch.name, "program": items[0]["program"], "faculty": None}]


@pytest.mark.asyncio
async def test_a_trainer_without_a_profile_shows_name_only_to_the_student(client, db_session):
    trainer = await make_trainer(db_session)
    student = await make_student(db_session)
    await seat(db_session, student, await make_batch(db_session, trainer))
    await as_user(client, student)
    data = (await client.get(faculty_url(trainer.id))).json()
    assert data == {"trainer_id": str(trainer.id), "name": trainer.full_name, "designation": None, "expertise": [], "contact_route": "in_app"}


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["trainer", "counselor", "it_admin"])
async def test_the_student_faculty_routes_are_for_students_only(client, db_session, role):
    await as_user(client, await make_user(db_session, role, "it"))
    assert (await client.get(MINE)).status_code == 403
    assert (await client.get(faculty_url(uuid.uuid4()))).status_code == 403


@pytest.mark.asyncio
async def test_a_hidden_photo_and_a_dead_contact_route_degrade_safely(client, db_session):
    trainer = await profiled_trainer(client, db_session, show_photo=False, show_phone=True, contact_route="phone")
    await client.put(f"{OWN}/photo", files={"file": ("me.png", png(200, 200), "image/png")})
    trainer_row = await db_session.get(type(trainer), trainer.id)
    trainer_row.phone = None  # the account phone was cleared after the route was chosen
    await db_session.commit()
    student = await make_student(db_session)
    await seat(db_session, student, await make_batch(db_session, trainer))
    await as_user(client, student)
    data = (await client.get(faculty_url(trainer.id))).json()
    assert "photo_url" not in data and "phone" not in data and data["contact_route"] == "in_app"
