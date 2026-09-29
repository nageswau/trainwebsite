"""ENH-016 test builders. Every school/user/student gets a random suffix, so tests never collide on the shared database."""

import uuid

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import Country, School, SchoolStudent, University, User, UserRoleAssignment

PASSWORD = "Sup3r-Secret-Pass!"
SCHOOL_ROLES = ("school_coordinator", "school_principal", "school_teacher", "school_parent")
OTHER_ROLES = {"academic_team": "overseas", "career_counselor": "overseas", "psychometric_team": "overseas", "overseas_admin": "overseas", "super_admin": "global", "it_admin": "it"}


def _user(role: str, division: str, school_id=None) -> User:
    return User(
        email=f"enh016-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=f"Test {role}",
        role=role, division=division, active=True, profile={"school_id": str(school_id)} if school_id else {},
    )


async def make_school(db, *, tier: str | None = "platinum", **fields) -> dict:
    """A school plus one account per school role (linked by profile.school_id) and one per Edusphere role. Not committed."""
    ctx: dict = {name: _user(name, division) for name, division in OTHER_ROLES.items()}
    db.add_all(ctx.values())
    await db.flush()
    school = School(name=fields.pop("name", f"ENH016 School {uuid.uuid4().hex[:6]}"), created_by_user_id=ctx["overseas_admin"].id, tier=tier, **fields)
    db.add(school)
    await db.flush()
    ctx["school"] = school
    for role in SCHOOL_ROLES:
        user = _user(role, "overseas", school.id)
        db.add(user)
        await db.flush()
        db.add(UserRoleAssignment(user_id=user.id, division="overseas", role=role, is_active=True, assigned_by_user_id=ctx["overseas_admin"].id, approval_status="approved"))
        ctx[role] = user
    await db.flush()
    return ctx


async def make_student(db, ctx: dict, *, name: str | None = None, grade_level: int | None = None, grade_or_class: str | None = None, **fields) -> SchoolStudent:
    student = SchoolStudent(
        school_id=ctx["school"].id, student_code=await unique_student_code(db, SchoolStudent.student_code), full_name=name or f"Student {uuid.uuid4().hex[:6]}",
        grade_level=grade_level, grade_or_class=grade_or_class, created_by_user_id=ctx["school_coordinator"].id, **fields,
    )
    db.add(student)
    await db.flush()
    return student


async def make_university(db) -> University:
    suffix = uuid.uuid4().hex[:8]
    country = Country(slug=f"enh016-c-{suffix}", name="C", overview="o", tuition="t", living_expenses="l", visa_process=[], work_opportunities="w", post_study_work="p", pr_opportunities="r", faq=[])
    db.add(country)
    await db.flush()
    university = University(country_id=country.id, slug=f"enh016-u-{suffix}", name="U", city="c", overview="o", eligibility="e", requirements=[], deadlines=[], scholarships=[])
    db.add(university)
    await db.flush()
    return university


async def login(client, user: User) -> None:
    division = "it" if user.division == "it" else "overseas"
    response = await client.post("/api/v1/auth/login", json={"email": user.email, "password": PASSWORD, "division": division})
    assert response.status_code == 200, response.text
