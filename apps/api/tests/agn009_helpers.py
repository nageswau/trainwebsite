"""AGN-009 test helpers: an agency with a Master, two staff (one with Verify), a student with no login and one with a login (both
assigned to the Verify staff member), an unassigned student, another agency, and documents built directly (the API under test builds
them in the feature tests)."""

import io

from sqlalchemy import select

from app.models import AgentStudent, AuditLog, DocumentEvent, StudentDocument
from tests.agn001_helpers import mk_active_org, mk_user, uniq
from tests.agn002_helpers import mk_staff
from tests.agn003_helpers import mk_university
from tests.agn004_helpers import mk_record

DOCS = "/api/v1/workflows/overseas/agent/crm/documents"
REQUESTS = "/api/v1/workflows/overseas/agent/crm/document-requests"
DOWNLOAD = "/api/v1/workflows/overseas/documents/{}/download"
VERIFY = "/api/v1/workflows/overseas/documents/{}/verify"
OLD_UPLOAD = "/api/v1/workflows/overseas/documents"

PDF = b"%PDF-1.4\n1 0 obj << >> endobj\ntrailer << >>\n%%EOF\n"
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa75\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def world(db) -> dict:
    ctx = await mk_active_org(db, name=f"Docs {uniq()}")
    other = await mk_active_org(db, name=f"Other {uniq()}")
    staff = await mk_staff(db, ctx["org"], full_name="Docs Staff", can_verify_documents=True)
    plain = await mk_staff(db, ctx["org"], full_name="Docs Plain Staff")
    record = await mk_record(db, agent=ctx["master"], full_name=f"No Login {uniq()}", assigned_member=staff["member"])
    unassigned = await mk_record(db, agent=ctx["master"], full_name=f"Unassigned {uniq()}")
    linked_user = await mk_user(db, role="overseas_student", full_name=f"Linked {uniq()}")
    linked_record = AgentStudent(agent_id=ctx["master"].id, student_id=linked_user.id, status="active", assigned_member_id=staff["member"].id)
    db.add(linked_record)
    await db.commit()
    university = await mk_university(db)
    return ctx | {
        "staff": staff, "plain": plain, "other": other, "record": record, "unassigned": unassigned,
        "linked_user": linked_user, "linked_record": linked_record, "university": university,
    }


async def mk_doc(db, *, record: AgentStudent | None = None, student=None, status: str = "pending", application=None, verified_by=None, document_type: str = "Passport", key: str | None = None) -> StudentDocument:
    """`record` -> an AGN-009 row (agent_student_id, plus student_id when the record has a login); `student` alone -> a row made
    before AGN-009."""
    row = StudentDocument(
        agent_student_id=record.id if record else None,
        student_id=(record.student_id if record else None) or (student.id if student else None),
        application_id=application.id if application else None,
        document_type=document_type,
        file_url=key or f"agent-documents/{uniq('doc')}",
        verification_status=status,
        verified_by_id=verified_by.id if verified_by else None,
    )
    db.add(row)
    await db.commit()
    return row


async def events_of(db, document_id=None, request_id=None) -> list[DocumentEvent]:
    clause = DocumentEvent.document_id == document_id if document_id else DocumentEvent.request_id == request_id
    return list((await db.scalars(select(DocumentEvent).where(clause).order_by(DocumentEvent.seq).execution_options(populate_existing=True))).all())


async def audit_actions(db, entity_id) -> list[str]:
    return list((await db.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(entity_id)).order_by(AuditLog.created_at))).all())


def upload_files(data: bytes = PDF, name: str = "passport.pdf", content_type: str = "application/pdf") -> dict:
    return {"file": (name, io.BytesIO(data), content_type)}
