"""tel-018 test builders. Every value is unique per call: the test database is shared and never truncated."""

import datetime
import uuid

from app.models import Batch, Enrollment, OverseasApplication, Program, User, VisaCase
from tests.agn003_helpers import mk_university
from tests.bdm017_helpers import as_user
from tests.tel004_helpers import make_user
from tests.tel016_helpers import make_counselor, setup

__all__ = ["as_user", "enrol", "apply_overseas", "handover", "handover_url", "make_counselor", "make_student", "setup", "c_url"]

COUNSELOR_LEADS = "/api/v1/counselor/leads"


def handover_url(lead_id) -> str:
    return f"/api/v1/telecaller/leads/{lead_id}/handover"


def c_url(lead_id, tail: str = "") -> str:
    return f"{COUNSELOR_LEADS}/{lead_id}{tail}"


async def handover(client, actor: User, lead, counselor: User):
    await as_user(client, actor)
    return await client.post(handover_url(lead.id), json={"counselor_id": str(counselor.id)})


async def make_student(db, division: str = "it", *, active: bool = True, phone: str | None = None) -> User:
    student = await make_user(db, f"{division}_student", division, active=active)
    if phone:
        student.phone = phone
        await db.commit()
    return student


async def enrol(db, student: User, *, status: str = "active") -> Enrollment:
    program = Program(slug=f"tel018-{uuid.uuid4().hex[:8]}", category="Software Development", title=f"Python {uuid.uuid4().hex[:6]}",
                      summary="", duration="8 weeks", eligibility="", fees=1000, certification="", curriculum=[], placement_assistance="",
                      trainer_name="T", active=True)
    db.add(program)
    await db.flush()
    batch = Batch(program_id=program.id, name=f"Batch-{uuid.uuid4().hex[:6]}", start_date=datetime.date.today(),
                  end_date=datetime.date.today() + datetime.timedelta(days=60), schedule="Mon-Fri", capacity=20, enrollment_open=True, status="active")
    db.add(batch)
    await db.flush()
    row = Enrollment(student_id=student.id, batch_id=batch.id, enrollment_code=f"EDU-T18-{uuid.uuid4().hex[:8]}", status=status)
    db.add(row)
    await db.commit()
    return row


async def apply_overseas(db, student: User, *, status: str = "enquiry", visa: str | None = None) -> OverseasApplication:
    university = await mk_university(db)
    row = OverseasApplication(student_id=student.id, university_id=university.id, intake="Fall 2027", status=status)
    db.add(row)
    await db.flush()
    if visa:
        db.add(VisaCase(application_id=row.id, status=visa))
    await db.commit()
    return row
