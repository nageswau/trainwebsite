"""Shared builders for the ENH-005 database tests (docs/superpowers/plans/2026-09-21-enh-005-student-school-transfer.md).

Each test builds its own throwaway schools with unique names/emails, like ENH-004's tests, so runs never collide."""

import uuid

from sqlalchemy import update

from app.core.identifiers import unique_student_code
from app.core.security import hash_password
from app.models import (
    School,
    SchoolAcademicResult,
    SchoolParentLink,
    SchoolStaffAssignment,
    SchoolStudent,
    User,
    UserRoleAssignment,
)

PASSWORD = "Sup3r-Secret-Pass!"


async def login(client, email: str) -> None:
    client.cookies.clear()
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD, "division": "overseas"})
    assert response.status_code == 200, response.text


async def mk_user(db, *, role: str, name: str, school_id=None, assigned_by=None, division: str = "overseas") -> User:
    profile = {"school_id": str(school_id)} if school_id else {}
    user = User(email=f"enh005-{role}-{uuid.uuid4().hex[:8]}@example.local", password_hash=hash_password(PASSWORD), full_name=name, role=role, division=division, active=True, profile=profile)
    db.add(user)
    await db.flush()
    db.add(UserRoleAssignment(user_id=user.id, division=division, role=role, is_active=True, assigned_by_user_id=(assigned_by or user).id, approval_status="approved"))
    return user


async def mk_student(db, school, coordinator, name: str = "Child", teacher=None) -> SchoolStudent:
    student = SchoolStudent(
        school_id=school.id, student_code=await unique_student_code(db, SchoolStudent.student_code), full_name=f"{name} {uuid.uuid4().hex[:4]}",
        grade_or_class="Grade 8-A", grade_level=8, created_by_user_id=coordinator.id, assigned_teacher_user_id=teacher.id if teacher else None,
    )
    db.add(student)
    await db.flush()
    return student


async def mk_school(db, *, admin=None, label: str = "School", students: int = 1, with_teacher: bool = True) -> dict:
    """A school with a coordinator, teacher, principal, `students` students (the first assigned to the teacher) and a parent linked to the first student."""
    admin = admin or await mk_user(db, role="overseas_admin", name="Overseas Admin")
    school = School(name=f"ENH-005 {label} {uuid.uuid4().hex[:6]}", created_by_user_id=admin.id)
    db.add(school)
    await db.flush()
    coordinator = await mk_user(db, role="school_coordinator", name=f"{label} Coordinator", school_id=school.id, assigned_by=admin)
    teacher = await mk_user(db, role="school_teacher", name=f"{label} Teacher", school_id=school.id, assigned_by=coordinator) if with_teacher else None
    principal = await mk_user(db, role="school_principal", name=f"{label} Principal", school_id=school.id, assigned_by=coordinator)
    rows = [await mk_student(db, school, coordinator, f"{label}-kid{i}", teacher if i == 0 else None) for i in range(students)]
    parent = await mk_user(db, role="school_parent", name=f"{label} Parent", school_id=school.id, assigned_by=coordinator)
    if rows:
        db.add(SchoolParentLink(parent_user_id=parent.id, school_student_id=rows[0].id, linked_by_user_id=coordinator.id))
    await db.commit()
    return {"admin": admin, "school": school, "coordinator": coordinator, "teacher": teacher, "principal": principal, "parent": parent, "students": rows}


async def mk_staff(db, school, admin, role: str = "academic_team") -> User:
    member = await mk_user(db, role=role, name=f"{role} member", assigned_by=admin)
    db.add(SchoolStaffAssignment(user_id=member.id, school_id=school.id, role=role, assigned_by_user_id=admin.id))
    await db.commit()
    return member


async def mk_result(db, student, uploader, status: str = "draft", subject: str = "Maths") -> SchoolAcademicResult:
    result = SchoolAcademicResult(
        school_student_id=student.id, academic_year="2026-27", term="Term 1", subject=subject, max_marks=100, marks_obtained=80, status=status,
        uploaded_by_user_id=uploader.id,
    )
    db.add(result)
    await db.commit()
    return result


async def move_student_directly(db, student, school) -> None:
    """Stand-in for the transfer (which does not exist yet in Task 4's tests): a direct update of `school_id`."""
    await db.execute(update(SchoolStudent).where(SchoolStudent.id == student.id).values(school_id=school.id))
    await db.commit()
    await db.refresh(student)
