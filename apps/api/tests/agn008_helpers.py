"""AGN-008 test helpers: an agency with staff, a student with no login, a linked student, a university, and applications built
directly (the API under test builds them in the feature tests)."""

from sqlalchemy import func, select

from app.models import AgentStudent, AuditLog, OverseasApplication, SchoolStudent
from tests.agn001_helpers import mk_active_org, mk_user, uniq
from tests.agn003_helpers import mk_university
from tests.agn004_helpers import mk_record, mk_staff
from tests.enh005_helpers import mk_school

APPS = "/api/v1/workflows/overseas/agent/crm/applications"


async def mk_application(db, *, agent, university, record: AgentStudent | None = None, student=None, status: str = "enquiry", course_id=None, school_student=None, **fields) -> OverseasApplication:
    """`record` -> an AGN-008 row (agent_student_id, plus student_id when the record has a login); `student` alone -> a row made
    before AGN-008; `school_student` -> a School-bridged row (DEC-SCOPE-018)."""
    row = OverseasApplication(
        agent_id=agent.id if agent else None,
        agent_student_id=record.id if record else None,
        student_id=(record.student_id if record else None) or (student.id if student else None),
        school_student_id=school_student.id if school_student else None,
        university_id=university.id,
        course_id=course_id,
        status=status,
        intake=fields.pop("intake", "Fall 2027"),
        **fields,
    )
    db.add(row)
    await db.commit()
    return row


async def count_rows(db, model, app_id) -> int:
    """Rows of `model` for one application: audit rows by entity id, the rest (history, commission) by `application_id`."""
    where = AuditLog.entity_id == str(app_id) if model is AuditLog else model.application_id == app_id
    return await db.scalar(select(func.count()).select_from(model).where(where))


async def mk_school_student(db) -> SchoolStudent:
    """A School-affiliated student (no login) for a DEC-SCOPE-018 bridged row -- ENH-005's school builder."""
    return (await mk_school(db, students=1, with_teacher=False))["students"][0]


async def agency_world(db) -> dict:
    ctx = await mk_active_org(db, name=f"Apps {uniq()}")
    other = await mk_active_org(db, name=f"Other {uniq()}")
    staff = await mk_staff(db, ctx["org"], full_name="Apps Staff")
    other_staff = await mk_staff(db, ctx["org"], full_name="Apps Other Staff")
    record = await mk_record(db, agent=ctx["master"], full_name=f"No Login {uniq()}", assigned_member=staff["member"])
    linked_user = await mk_user(db, role="overseas_student", full_name=f"Linked {uniq()}")
    linked_record = AgentStudent(agent_id=ctx["master"].id, student_id=linked_user.id, status="active", assigned_member_id=staff["member"].id)
    db.add(linked_record)
    await db.commit()
    university = await mk_university(db)
    return ctx | {"staff": staff, "other_staff": other_staff, "other": other, "record": record, "linked_record": linked_record, "linked_user": linked_user, "university": university}
