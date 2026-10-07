"""bdm-016 test builders. A past IST month (fully elapsed) keeps every instant exactly inside or outside the window. Unique values per call:
the test database is shared and never truncated."""

import uuid
from datetime import UTC, date, datetime, timedelta

from app.models import Enquiry, Enrollment, PlacementProfile, School, SchoolCareerRecord, SchoolPsychometricRecord, SchoolStudent
from app.services.bdm_metrics import month_range
from app.services.bdm_travel import india_today
from tests.bdm001_helpers import make_user
from tests.test_bdm_021_business import batch

TARGETS = "/api/v1/bdm/targets"
TEAM_TARGETS = "/api/v1/bdm/manager/targets"
COPY = "/api/v1/bdm/manager/targets/copy"


def month_of(day: date) -> date:
    return day.replace(day=1)


def this_month() -> date:
    return month_of(india_today())


def shift(month: date, months: int) -> date:
    index = month.year * 12 + month.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def ym(month: date) -> str:
    return month.strftime("%Y-%m")


def inside(month: date, days: int = 9) -> datetime:
    return month_range(month)[0] + timedelta(days=days, hours=10)


def before(month: date) -> datetime:
    return month_range(month)[0] - timedelta(seconds=1)


def after(month: date) -> datetime:
    return month_range(month)[1]


def by_key(items: list[dict]) -> dict:
    return {i["key"]: (i["achieved"] if i["tracked"] else "not tracked") for i in items}


async def school(db, owner_id, *, tier: str | None = "gold", valid_until: date | None = None) -> School:
    row = School(name=f"School {uuid.uuid4().hex[:8]}", created_by_user_id=owner_id, tier=tier, tier_valid_until=valid_until)
    db.add(row)
    await db.commit()
    return row


async def school_student(db, school_id, owner_id, created_at: datetime | None = None) -> SchoolStudent:
    row = SchoolStudent(school_id=school_id, student_code=uuid.uuid4().hex[:8].upper(), full_name="Priya Student", created_by_user_id=owner_id)
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    await db.commit()
    return row


async def career(db, student_id, counselor_id, *, status: str | None = "completed", completed_on: date | None = None, created_at: datetime | None = None,
                 record_type: str = "guidance_session") -> None:
    row = SchoolCareerRecord(school_student_id=student_id, career_counselor_user_id=counselor_id, record_type=record_type, notes="-", status=status,
                             completed_on=completed_on)
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    await db.commit()


async def psychometric(db, student_id, team_id, *, status: str = "completed", test_date: date | None = None, created_at: datetime | None = None) -> None:
    row = SchoolPsychometricRecord(school_student_id=student_id, psychometric_team_user_id=team_id, assessment_type="Aptitude", status=status, test_date=test_date)
    if created_at is not None:
        row.created_at = created_at
    db.add(row)
    await db.commit()


async def converted_lead(db, bdm_id, org_id):
    """A lead the BDM entered, converted to a student account: an attributed user (R10)."""
    student = await make_user(db, "it_student", "it")
    db.add(
        Enquiry(
            division="it", name="Lead", email=f"lead-{uuid.uuid4().hex[:10]}@example.local", subject="Python", message="-", source="bdm",
            bdm_organization_id=org_id, bdm_user_id=bdm_id, converted_user_id=student.id, converted_at=datetime.now(UTC), converted_by_user_id=bdm_id,
        )
    )
    await db.commit()
    return student


async def enroll(db, student_id, created_at: datetime) -> None:
    b = await batch(db)
    row = Enrollment(student_id=student_id, batch_id=b.id, enrollment_code=f"B016-{uuid.uuid4().hex[:10]}")
    row.created_at = created_at
    db.add(row)
    await db.commit()


async def placement(db, student_id, created_at: datetime) -> None:
    row = PlacementProfile(student_id=student_id)
    row.created_at = created_at
    db.add(row)
    await db.commit()
