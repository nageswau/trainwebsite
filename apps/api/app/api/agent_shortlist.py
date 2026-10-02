"""AGN-007 -- an agency's own universities and a student's university shortlist (DEC-SCOPE-049; spec §5).

Reuses AGN-004's gate, lock order and scoped load unchanged (api/agent_students.py is imported, not edited). Every write locks the
agency, loads its rows FOR UPDATE, validates, writes, audits in the same transaction and commits once, so the caps, the duplicate
check and in-use deletes hold under concurrency. Another agency's rows are 404 (or 422 when named inside a body), never 403.
"""

from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.agent_students import _audit, _gate, _locked_row, _log, _require_master_action
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AgentStudent, AgentStudentShortlistEntry, AgentUniversity, AuditLog, User
from app.schemas import AgentUniversityCreate, AgentUniversityUpdate, ShortlistEntryCreate, ShortlistEntryUpdate
from app.services.agent_orgs import lock_active_org
from app.services.agent_shortlist import (
    DUPLICATE_UNIVERSITY,
    apply_changes,
    ensure_entry_capacity,
    ensure_unique_university,
    ensure_university_capacity,
    entry_detail,
    entry_page,
    entry_values,
    in_use_message,
    load_entry,
    load_university,
    university_item,
    university_page,
    university_usage,
    validate_entry,
)
from app.services.agent_students import load_scoped

router = APIRouter(prefix="/workflows/overseas/agent/crm", tags=["agent-shortlist"])


def _university_audit(db: AsyncSession, user: User, action: str, university_id, metadata: dict | None = None) -> None:
    """Same transaction as the write (fail closed, SEC-001); ids and field names only."""
    db.add(AuditLog(user_id=user.id, action=f"agent_university.{action}", entity_type="agent_university", entity_id=str(university_id), metadata_json=metadata or {}))


async def _commit(db: AsyncSession, conflict: str) -> None:
    """The unique index and RESTRICT foreign keys back the locked checks; a violation is the matching 409, never a 500."""
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, conflict) from None


@router.get("/universities")
async def list_universities(
    q: str | None = Query(None, max_length=100),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    membership = _gate(user)
    return await university_page(db, membership.org_id, q=q, limit=limit, offset=offset)


@router.post("/universities", status_code=201)
async def create_university(payload: AgentUniversityCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    _require_master_action(user, "Only an agency Master can add universities")
    await lock_active_org(db, membership.org_id)
    await ensure_university_capacity(db, membership.org_id)
    await ensure_unique_university(db, membership.org_id, payload.name, payload.country)
    data = payload.model_dump()
    # The id is set here (not at flush) so the audit row can name it before the single commit; the unique index can still
    # disagree with the Python duplicate check (Unicode lower()), which _commit answers as a 409, never a 500.
    row = AgentUniversity(id=uuid4(), org_id=membership.org_id, **data, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(row)
    _university_audit(db, user, "create", row.id, {"fields": sorted(k for k, v in data.items() if v is not None)})
    await _commit(db, DUPLICATE_UNIVERSITY)
    _log("agent_university_created", membership, user, "-", university_id=str(row.id))
    return {"university": university_item(row)}


@router.patch("/universities/{university_id}")
async def update_university(university_id: UUID, payload: AgentUniversityUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    row = await load_university(db, membership.org_id, university_id, lock=True)  # 404 before the role check
    _require_master_action(user, "Only an agency Master can edit universities")
    changes = payload.model_dump(exclude_unset=True)
    if {"name", "country"} & changes.keys():
        await ensure_unique_university(db, membership.org_id, changes.get("name", row.name), changes.get("country", row.country), exclude_id=row.id)
    changed = apply_changes(row, changes, user)
    if changed:
        _university_audit(db, user, "update", row.id, {"fields": changed})
    await _commit(db, DUPLICATE_UNIVERSITY)
    if changed:
        _log("agent_university_updated", membership, user, "-", university_id=str(row.id), fields=changed)
    await db.refresh(row)  # updated_at is set by the database on UPDATE; reload it in the async session
    return {"university": university_item(row)}


@router.delete("/universities/{university_id}", status_code=204)
async def delete_university(university_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    await lock_active_org(db, membership.org_id)
    row = await load_university(db, membership.org_id, university_id, lock=True)
    _require_master_action(user, "Only an agency Master can delete universities")
    used = await university_usage(db, row.id)
    if used:
        _log("agent_university_delete_refused", membership, user, "-", university_id=str(row.id), entry_count=used)
        raise HTTPException(409, in_use_message(used))
    _university_audit(db, user, "delete", row.id)
    await db.delete(row)
    await _commit(db, in_use_message(1))
    _log("agent_university_deleted", membership, user, "-", university_id=str(university_id))
    return Response(status_code=204)


SHORTLIST_CHANGED = "The shortlist changed; reload and try again"
SHORTLIST = "/students/{student_id}/shortlist"
ENTRY = SHORTLIST + "/{entry_id}"


def _require_active(student: AgentStudent) -> None:
    if student.status == "archived":
        raise HTTPException(409, "Unarchive this student first")


@router.get(SHORTLIST)
async def list_shortlist(
    student_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _gate(user)
    await load_scoped(db, user, student_id)  # 404 outside the caller's scope (staff: assigned students only)
    return await entry_page(db, student_id, limit=limit, offset=offset)


@router.post(SHORTLIST, status_code=201)
async def add_entry(student_id: UUID, payload: ShortlistEntryCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, student_id)
    _require_active(student)
    values = payload.model_dump()
    await validate_entry(db, membership.org_id, values)
    await ensure_entry_capacity(db, student.id)
    entry = AgentStudentShortlistEntry(id=uuid4(), agent_student_id=student.id, **values, created_by_user_id=user.id, updated_by_user_id=user.id)
    db.add(entry)
    source = "catalogue" if values["university_id"] else "agency"
    _audit(db, user, "shortlist_add", student.id, {"entry_id": str(entry.id), "university_source": source, "fields": sorted(k for k, v in values.items() if v is not None)})
    await _commit(db, SHORTLIST_CHANGED)
    _log("agent_shortlist_added", membership, user, student.id, entry_id=str(entry.id))
    return {"entry": await entry_detail(db, entry.id)}


@router.patch(ENTRY)
async def update_entry(student_id: UUID, entry_id: UUID, payload: ShortlistEntryUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, student_id)
    _require_active(student)
    entry = await load_entry(db, student.id, entry_id, lock=True)
    changes = payload.model_dump(exclude_unset=True)
    await validate_entry(db, membership.org_id, {**entry_values(entry), **changes})
    changed = apply_changes(entry, changes, user)
    if changed:
        _audit(db, user, "shortlist_update", student.id, {"entry_id": str(entry.id), "fields": changed})
    await _commit(db, SHORTLIST_CHANGED)
    if changed:
        _log("agent_shortlist_updated", membership, user, student.id, entry_id=str(entry.id), fields=changed)
    return {"entry": await entry_detail(db, entry.id)}


@router.delete(ENTRY, status_code=204)
async def remove_entry(student_id: UUID, entry_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    membership = _gate(user)
    student = await _locked_row(db, user, membership, student_id)
    _require_active(student)
    entry = await load_entry(db, student.id, entry_id, lock=True)
    _audit(db, user, "shortlist_remove", student.id, {"entry_id": str(entry.id)})
    await db.delete(entry)
    await _commit(db, SHORTLIST_CHANGED)
    _log("agent_shortlist_removed", membership, user, student.id, entry_id=str(entry.id))
    return Response(status_code=204)
