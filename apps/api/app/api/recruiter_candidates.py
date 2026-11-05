"""rec-009 (DEC-SCOPE-122, spec §5): the candidate master. Recruiters, placement managers and super_admin read and write the whole pool
(R11); hr_team reads. The role check runs before anything is read; a candidate outside the pool (services/candidates.pool_filter) is a 404.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-002 idiom). Each write
is one transaction: role, row lock, rules, change, audit row, one commit here, then the log line. `duplicate-check` is declared before
`/{candidate_id}` so it never reaches the id routes."""

import re
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import crm_exports
from app.api.agent_reports import NO_STORE
from app.api.bdm import LIMIT, OFFSET, SEARCH
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.portfolio_certificates import HEADERS
from app.api.telecaller_catalogue import NOT_AN_OBJECT
from app.core.database import get_db
from app.models import Candidate, CandidateResume, RecCandidateSource, SavedCandidateSearch, User
from app.notifications.phone import normalise_phone
from app.schemas import (
    CANDIDATE_FIELD_LABELS,
    CANDIDATE_MERGE_LABELS,
    CANDIDATE_OWNERSHIP_LABELS,
    CANDIDATE_SEARCH_LABELS,
    RESUME_APPLY_LABELS,
    SAVED_SEARCH_LABELS,
    CandidateAssignee,
    CandidateCreate,
    CandidateDetail,
    CandidateEngagementKey,
    CandidateMergeBody,
    CandidateOwnershipIn,
    CandidateOwnershipSettings,
    CandidateOwnershipSettingsOut,
    CandidatePage,
    CandidateSearch,
    CandidateStatus,
    CandidateUpdate,
    ResumeApply,
    SavedSearchIn,
    SavedSearchUpdate,
    WebsiteRegistrationPage,
    WebsiteRegistrationView,
)
from app.services import candidate_documents as documents
from app.services import candidate_duplicates as duplicates
from app.services import candidate_engagement, candidate_merge, candidate_search, candidate_skills, compensation, course_skills, recruitment_history, saved_searches
from app.services import candidate_ownership as ownership
from app.services import candidate_previews as previews
from app.services import candidate_privacy as privacy
from app.services import candidate_profile as profile
from app.services import candidates as svc
from app.services import resume_extraction as extraction
from app.services import website_registrations as registrations
from app.services.permissions import user_has_grant
from app.services.reports import placement as placement_reports
from app.services.stale_guard import require_fresh
from app.services.telecaller import _parse

router = APIRouter(prefix="/recruiter/candidates", tags=["recruiter-candidates"])
settings_router = APIRouter(prefix="/recruiter/candidate-ownership-settings", tags=["recruiter-candidates"])  # hrc-012 (O4)
PHONE_DIGITS = re.compile(r"[0-9]+")  # ASCII only, like notifications.phone
NO_EXPORT = "Your role cannot export candidates"  # hrc-020 X8


@settings_router.get("", response_model=CandidateOwnershipSettingsOut)
async def ownership_settings(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-012 (O4): whether collaborators may be added -- every candidate reader sees it; managers and super_admin may change it."""
    svc.require_reader(user)
    return {"shared_ownership": await ownership.shared_ownership(db), "can_edit": user.role in ownership.SETTING_EDITORS}


@settings_router.put("", response_model=CandidateOwnershipSettingsOut)
async def save_ownership_settings(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if user.role not in ownership.SETTING_EDITORS:
        raise HTTPException(403, "Only a placement manager can change candidate ownership settings")
    body = _parse(CandidateOwnershipSettings, payload, NOT_AN_OBJECT, CANDIDATE_OWNERSHIP_LABELS)
    await ownership.save_setting(db, user, body.shared_ownership)
    await db.commit()
    return {"shared_ownership": body.shared_ownership, "can_edit": True}


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, CANDIDATE_FIELD_LABELS)


@router.get("", response_model=CandidatePage)
async def list_candidates(
    q: str | None = SEARCH,
    source_id: UUID | None = None,
    status: CandidateStatus | None = None,
    engagement: CandidateEngagementKey | None = None,
    archived: bool = False,
    owner: Literal["me", "unassigned"] | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Newest first. `q` matches the name, code or email; a phone-shaped `q` (digits with + - ( ) . or spaces) also matches the mobile's
    digits, so a name or code that holds digits never matches phone numbers (S2-§13: the source is on every row). hrc-012 (O1): `owner`
    narrows to My candidates (primary recruiter, officer or collaborator) or the unassigned ones; each row names its primary recruiter."""
    svc.require_reader(user)
    filters = [*svc.pool_filter(), Candidate.archived_at.is_not(None) if archived else Candidate.archived_at.is_(None)]
    if owner == "me":
        filters.append(ownership.mine(user.id))
    elif owner == "unassigned":
        filters.append(Candidate.owner_user_id.is_(None))
    pattern = like_pattern(q)
    if pattern:
        digits = re.sub(r"[\s+().-]", "", q)
        columns = [Candidate.name.ilike(pattern, escape="\\"), Candidate.candidate_code.ilike(pattern, escape="\\"), Candidate.email.ilike(pattern, escape="\\")]
        if len(digits) >= 4 and PHONE_DIGITS.fullmatch(digits):
            columns.append(Candidate.mobile_normalized.contains(digits, autoescape=True))
        filters.append(or_(*columns))
    if source_id:
        filters.append(Candidate.source_id == source_id)
    if status:
        filters.append(Candidate.status == status)
    if engagement:  # hrc-021 (DEC-SCOPE-397 E7): the derived status, one WHERE term
        filters.append(candidate_engagement.expression() == engagement)
    stmt = select(Candidate, RecCandidateSource).join(RecCandidateSource, RecCandidateSource.id == Candidate.source_id).where(*filters)
    total = await db.scalar(select(func.count()).select_from(stmt.subquery()))
    page = stmt.add_columns(candidate_engagement.expression()).order_by(Candidate.created_at.desc(), Candidate.id.desc()).limit(limit).offset(offset)
    rows = (await db.execute(page)).all()
    people = await ownership.owners(db, [c for c, _, _ in rows])
    items = [{**svc.item_out(c, s), "owner": ownership.owner_out(people, c), "engagement": candidate_engagement.out(e)} for c, s, e in rows]
    return {"items": items, "total": total or 0, "limit": limit, "offset": offset}


@router.get("/duplicate-check")
async def duplicate_check(
    mobile: Annotated[str | None, Query(max_length=40)] = None,
    email: Annotated[str | None, Query(max_length=255)] = None,
    exclude_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The form's live panel (on blur); the create and the edit re-check. An unparseable mobile matches nothing."""
    svc.require_writer(user)
    return {"matches": await svc.find_matches(db, *svc.keys(mobile, email), exclude_id=exclude_id)}


@router.get("/website-registrations", response_model=WebsiteRegistrationPage)
async def website_registration_list(view: WebsiteRegistrationView | None = None, limit: int = LIMIT, offset: int = OFFSET,
                                    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):  # fmt: skip
    """hrc-025 (DEC-SCOPE-402): the candidates the website created, newest first, with first contact, next follow-up, conversion and
    the contact SLA. A recruiter reads their own and the unassigned queue; managers, super_admin, hr_team and the HR Manager read all."""
    registrations.require_reader(user)
    return await registrations.page(db, user, view, limit=limit, offset=offset)


@router.get("/assignees", response_model=list[CandidateAssignee])
async def assignees(kind: Literal["recruiter", "officer", "collaborator"], q: str | None = SEARCH, user: User = Depends(get_current_user),
                    db: AsyncSession = Depends(get_db)):  # fmt: skip
    """hrc-012 (O5): the ownership pickers -- active people who may be chosen (names and roles only), for the roles that can assign."""
    svc.require_writer(user)
    return await ownership.lookup(db, kind, like_pattern(q))


@router.post("/search")
async def search_candidates(
    payload: dict = Body(...), limit: int = LIMIT, offset: int = OFFSET, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    """rec-013 (DEC-SCOPE-151): Find Candidates over the whole pool (R11) -- skill AND / OR groups expanded through aliases and related
    skills, the S2-§18 filters, the F1-F3 facets. Read only; the role check runs before the body is read."""
    svc.require_reader(user)
    body = _search_body(payload)
    sees = await _compensation_allowed(db, user, body)
    result = await candidate_search.search(db, body, limit=limit, offset=offset, user_id=user.id)
    if not sees:
        svc.without_compensation(result["items"])
    candidate_search.log(user, body, result["total"])
    return result


def _search_body(raw) -> CandidateSearch:
    return _parse(CandidateSearch, raw, NOT_AN_OBJECT, CANDIDATE_SEARCH_LABELS)


async def _compensation_allowed(db: AsyncSession, user: User, body: CandidateSearch) -> bool:
    """hrc-001 H2 / hrc-019 S9: a package filter or sort without the grant is a 403; returns whether the caller sees compensation."""
    sees = await svc.sees_compensation(db, user)
    if not sees and body.package():
        raise HTTPException(403, svc.NO_COMPENSATION)
    return sees


@router.post("/search/export")
async def export_candidates(payload: Any = Body(...), format: Literal["csv", "xlsx"] = "csv", user: User = Depends(get_current_user),  # noqa: A002
                            db: AsyncSession = Depends(get_db)):  # fmt: skip
    """hrc-020 (DEC-SCOPE-401 X8-X11, AC2/AC3): the Find Candidates result as CSV / XLSX -- the reader role, then `candidates.export`,
    then the body; ccrm-035's one export step (lock, throttle, cap, audit row with the filters and row count, commit, file)."""
    svc.require_reader(user)
    if not await user_has_grant(db, user, "candidates", "export"):
        raise HTTPException(403, NO_EXPORT)
    body = _search_body(payload)
    sees = await _compensation_allowed(db, user, body)

    async def build() -> dict:
        return await candidate_search.export_table(db, body, user_id=user.id, cap=crm_exports.ROW_CAP, salary=sees)

    return await crm_exports.export(db, user, entity_type="candidate_search", key="find_candidates", fmt=format, filters=saved_searches.stored(body),
                                    filename="candidates", sheet_name="Candidates", build=build)  # fmt: skip


# hrc-020 (DEC-SCOPE-401 X1-X7): saved searches -- declared before `/{candidate_id}` so they never reach the id routes.
@router.get("/saved-searches")
async def saved_search_list(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    sees = await svc.sees_compensation(db, user)
    return {"items": [saved_searches.out(row, owner, user, sees) for row, owner in await saved_searches.listed(db, user)]}


async def _commit_saved(db: AsyncSession, row: SavedCandidateSearch) -> None:
    try:
        await db.commit()
    except IntegrityError:  # the unique name index under a race
        await db.rollback()
        raise HTTPException(409, saved_searches.DUPLICATE) from None
    await db.refresh(row)


@router.post("/saved-searches", status_code=201)
async def create_saved_search(payload: Any = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    data = _parse(SavedSearchIn, payload, NOT_AN_OBJECT, SAVED_SEARCH_LABELS)
    body = _search_body(data.filters)
    sees = await _compensation_allowed(db, user, body)
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())  # one owner's saves queue: the cap and the name hold
    await saved_searches.require_room(db, user)
    if await saved_searches.name_taken(db, user.id, data.name):
        raise HTTPException(409, saved_searches.DUPLICATE)
    row = SavedCandidateSearch(owner_user_id=user.id, name=data.name, filters=saved_searches.stored(body), shared=data.shared)
    db.add(row)
    await _commit_saved(db, row)
    saved_searches.log("saved_search.create", user, row)
    return saved_searches.out(row, user.full_name, user, sees)


@router.patch("/saved-searches/{search_id}")
async def update_saved_search(search_id: UUID, payload: Any = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    data = _parse(SavedSearchUpdate, payload, NOT_AN_OBJECT, SAVED_SEARCH_LABELS)
    body = _search_body(data.filters) if data.filters is not None else None
    sees = await _compensation_allowed(db, user, body) if body is not None else await svc.sees_compensation(db, user)
    row = await saved_searches.load_for_write(db, user, search_id)
    if data.name is not None:
        if await saved_searches.name_taken(db, row.owner_user_id, data.name, exclude=row.id):
            raise HTTPException(409, saved_searches.DUPLICATE)
        row.name = data.name
    if body is not None:
        row.filters = saved_searches.stored(body)
    if data.shared is not None:
        row.shared = data.shared
    await _commit_saved(db, row)
    saved_searches.log("saved_search.update", user, row)
    owner = user.full_name if row.owner_user_id == user.id else await db.scalar(select(User.full_name).where(User.id == row.owner_user_id))
    return saved_searches.out(row, owner, user, sees)


@router.delete("/saved-searches/{search_id}", status_code=204)
async def delete_saved_search(search_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    row = await saved_searches.load_for_write(db, user, search_id)
    await db.delete(row)
    await db.commit()
    saved_searches.log("saved_search.delete", user, row)
    return Response(status_code=204)


@router.post("", response_model=CandidateDetail, response_model_exclude_unset=True, status_code=201)
async def create_candidate(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Q-07: a known mobile or email is the 409 panel, before and (by the unique indexes) under a race."""
    svc.require_writer(user)
    lawful_basis = privacy.basis(payload.pop("lawful_basis", None)) if isinstance(payload, dict) else None  # hrc-035 K1
    data = _body(CandidateCreate, payload).model_dump()
    stored = {kind: data.pop(kind) for kind in profile.ROWS}  # hrc-010 P1
    await svc.require_compensation(db, user, payload)
    await svc.active_source(db, data["source_id"])
    candidate = Candidate(**data, mobile_normalized=normalise_phone(data["mobile"]), created_by_user_id=user.id)  # email: lower-cased by the schema
    profile.sync(candidate, stored, set(payload))  # hrc-010 P4/P5
    await compensation.normalise(db, candidate)  # hrc-011
    await svc.block_duplicates(db, candidate)
    candidate.candidate_code = await svc.next_code(db)
    db.add(candidate)
    await svc.flush_candidate(db, candidate)
    for kind, values in stored.items():
        if values:
            await profile.replace(db, candidate.id, kind, values)
    ownership.on_create(db, user, candidate)  # hrc-012 O7
    privacy.record_staff_basis(db, user, [candidate.id], "manual", lawful_basis)  # hrc-035 K1
    filled = {**data, **stored}
    svc.audit(db, user, "create", candidate, {"fields": sorted(k for k, v in filled.items() if v not in (None, []))})
    await duplicates.detect(db, candidate.id)  # hrc-014 D2: probable duplicates are queued, never blocked
    await db.commit()
    svc.log("candidate_created", user, candidate)
    return await svc.detail_out(db, user, candidate)


@router.get("/{candidate_id}", response_model=CandidateDetail, response_model_exclude_unset=True)
async def get_candidate(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    return await svc.detail_out(db, user, await svc.load(db, candidate_id))


@router.get("/{candidate_id}/journey")
async def get_journey(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """rec-036 (CI7): lead → IT student → trained → recruiter candidate → placed, read only. Outside the pool is a 404 (R4)."""
    svc.require_reader(user)
    return await course_skills.journey(db, await svc.load(db, candidate_id))


@router.get("/{candidate_id}/training")
async def get_training(candidate_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """nehn-016 (DEC-SCOPE-312): the student's training progress, read only -- recruiters, placement managers and super_admin (HR's
    access is nehn-017's). Outside the pool is a 404 (R4); an external candidate has no training."""
    if user.role not in svc.WRITERS:
        raise HTTPException(403, "Your role cannot view training progress")
    response.headers.update(NO_STORE)
    return await placement_reports.candidate_training(db, await svc.load(db, candidate_id))


@router.get("/{candidate_id}/history")
async def candidate_history(candidate_id: UUID, response: Response, limit: int = Query(20, ge=1, le=100), offset: int = OFFSET,
                            user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-004 (DEC-SCOPE-376 B1/B6): the candidate's changes with before/after values (contact and salary redacted), for its readers."""
    svc.require_reader(user)
    candidate = await svc.load(db, candidate_id)
    response.headers.update(NO_STORE)
    return await recruitment_history.history(db, "candidates", candidate.id, ("candidate.",), limit=limit, offset=offset)


@router.patch("/{candidate_id}", response_model=CandidateDetail, response_model_exclude_unset=True)
async def update_candidate(candidate_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Partial. Moving to another source needs an active one; keeping a since-deactivated source is allowed (the rec-002 rule)."""
    svc.require_writer(user)
    changes = _body(CandidateUpdate, payload).model_dump(exclude_unset=True)
    expected = changes.pop("expected_updated_at", None)
    sent_rows = {kind: changes.pop(kind) for kind in profile.ROWS if kind in changes}  # hrc-010 P1: each sent list replaces its set
    await svc.require_compensation(db, user, changes)
    candidate = await svc.load(db, candidate_id, lock=True)

    async def current() -> dict:  # the 200 response's shape and fields (response_model), never more -- salary absent without the grant
        return CandidateDetail.model_validate(await svc.detail_out(db, user, candidate)).model_dump(exclude_unset=True)

    await require_fresh(db, stored=candidate.updated_at, expected=expected, entity=("candidates", candidate.id), action_prefix="candidate.",
                        since=expected, current=current)
    if candidate.archived_at is not None:
        raise HTTPException(409, svc.ARCHIVED)
    if changes.get("source_id", candidate.source_id) != candidate.source_id:
        await svc.active_source(db, changes["source_id"])
    # hrc-004: the stored values, for the audit diff -- hrc-010: plus the rows sent and the mirrors they may move (P5)
    audited = {*changes, *profile.DERIVED}
    stored_before = await profile.rows(db, candidate.id)
    stored = {**stored_before, **sent_rows}
    before = await svc.audited_values(db, candidate, audited) | profile.audited(stored_before, sent_rows)
    old_email = candidate.email
    applied = svc.apply_fields(candidate, changes)
    if candidate.email != old_email:
        candidate.email_verified_at = None  # hrc-010 P9: a new address is unverified
    profile.sync(candidate, stored, {*changes, *sent_rows}, stored_before)
    if set(svc.COMPENSATION) & set(applied):  # hrc-011: the currency, period and annual INR follow the amounts
        await compensation.normalise(db, candidate)
    if {"mobile", "email"} & set(applied):
        await svc.block_duplicates(db, candidate)
    with db.no_autoflush:  # the candidate's own change reaches the unique indexes in flush_candidate (the friendly 409), not here
        for kind, values in sent_rows.items():
            if values != stored_before[kind]:
                await profile.replace(db, candidate.id, kind, values)
    changed = recruitment_history.diff(before, await svc.audited_values(db, candidate, audited) | profile.audited(stored, sent_rows))
    fields = sorted((set(applied) - set(profile.DERIVED)) | set(changed))  # a mirror is listed only when it really moved
    if fields:
        candidate.updated_by_user_id = user.id
        candidate.updated_at = datetime.now(UTC)  # hrc-003: a rows-only save is a new version too
        await svc.flush_candidate(db, candidate)
        svc.audit(db, user, "update", candidate, {"fields": fields, "changes": changed})
        if duplicates.WATCHED & set(fields):  # hrc-014 D2
            await duplicates.detect(db, candidate.id)
    await db.commit()
    if fields:
        svc.log("candidate_updated", user, candidate, fields=fields)
    return await svc.detail_out(db, user, candidate)


@router.put("/{candidate_id}/ownership", response_model=CandidateDetail, response_model_exclude_unset=True)
async def change_ownership(candidate_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """hrc-012 (DEC-SCOPE-382 O2-O6): the primary recruiter, placement officer and collaborators. Partial; a no-op writes nothing. The
    primary recruiter changes their own candidate; a placement manager or super_admin any (403 before the body is read otherwise)."""
    svc.require_writer(user)
    candidate = await svc.load(db, candidate_id, lock=True)
    if not ownership.may_assign(user, candidate):
        raise HTTPException(403, ownership.CANNOT_ASSIGN)
    sent = _parse(CandidateOwnershipIn, payload, NOT_AN_OBJECT, CANDIDATE_OWNERSHIP_LABELS).model_dump(exclude_unset=True)
    if candidate.archived_at is not None:
        raise HTTPException(409, svc.ARCHIVED)
    await ownership.change(db, user, candidate, sent)
    await db.commit()
    return await svc.detail_out(db, user, candidate)


async def _set_archived(db: AsyncSession, user: User, candidate_id: UUID, archive: bool) -> dict:
    svc.require_writer(user)
    candidate = await svc.load(db, candidate_id, lock=True)
    if (candidate.archived_at is not None) == archive:
        raise HTTPException(409, "This candidate is already archived" if archive else "This candidate is not archived")
    if candidate.merged_into_id is not None:  # hrc-014 D8: a merge is final
        raise HTTPException(409, f"This candidate was merged into {(await svc.merged_into(db, candidate))['candidate_code']}")
    candidate.archived_at = datetime.now(UTC) if archive else None
    candidate.archived_by_user_id = user.id if archive else None
    candidate.updated_by_user_id = user.id
    action = "archive" if archive else "restore"
    svc.audit(db, user, action, candidate, {})
    await db.commit()
    svc.log(f"candidate_{action}d", user, candidate)
    return await svc.detail_out(db, user, candidate)


@router.post("/{candidate_id}/archive", response_model=CandidateDetail, response_model_exclude_unset=True)
async def archive_candidate(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_archived(db, user, candidate_id, True)


@router.post("/{candidate_id}/restore", response_model=CandidateDetail, response_model_exclude_unset=True)
async def restore_candidate(candidate_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _set_archived(db, user, candidate_id, False)


# --- resumes (AC4) ---------------------------------------------------------------------------------------------------------------
@router.put("/{candidate_id}/resume", status_code=201)
async def upload_resume(candidate_id: UUID, file: UploadFile = File(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """A new version, current from now on. Not idempotent: each upload is a version (the form sends one per click). The file is stored
    before the row lock and discarded when the transaction fails."""
    svc.require_writer(user)
    await svc.load(db, candidate_id)  # 404 before reading a byte of an unknown candidate's upload
    data, content_type, file_name = await svc.read_resume(file)
    key = svc.store(data, content_type)
    try:
        candidate = await svc.load(db, candidate_id, lock=True)
        if candidate.archived_at is not None:
            raise HTTPException(409, svc.ARCHIVED)
        last = await db.scalar(select(func.max(CandidateResume.version)).where(CandidateResume.candidate_id == candidate.id))
        resume = CandidateResume(
            candidate_id=candidate.id,
            version=(last or 0) + 1,
            storage_key=key,
            content_type=content_type,
            file_name=file_name,
            size_bytes=len(data),
            uploaded_by_user_id=user.id,
            preview_status=previews.initial_status(content_type),  # hrc-015 (DEC-SCOPE-379 D3)
        )
        db.add(resume)
        candidate.updated_by_user_id = user.id
        svc.audit(db, user, "resume_upload", candidate, {"version": resume.version, "content_type": content_type, "size_bytes": len(data)})
        await db.commit()
    except Exception:  # the 409, a lost race on the version pair, or a failed commit: nothing references the stored file
        await db.rollback()
        svc.discard(key)
        raise
    if resume.preview_status:
        previews.enqueue("resume", resume.id)
    svc.log("candidate_resume_uploaded", user, candidate, version=resume.version)
    return {"version": resume.version, "file_name": file_name, "content_type": content_type, "size_bytes": len(data)}


@router.get("/{candidate_id}/resume/{version}")
async def download_resume(candidate_id: UUID, version: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Readers only. The audit row is committed before any byte leaves; the file name is built from the candidate code."""
    svc.require_reader(user)
    candidate = await svc.load(db, candidate_id)
    resume = await db.scalar(select(CandidateResume).where(CandidateResume.candidate_id == candidate.id, CandidateResume.version == version))
    if resume is None:
        raise HTTPException(404, "Resume version not found")
    data = svc.read_file(resume)
    svc.audit(db, user, "resume_download", candidate, {"version": version, "role": user.role})
    await db.commit()
    svc.log("candidate_resume_downloaded", user, candidate, version=version, role=user.role)
    filename = f"resume-{candidate.candidate_code}-v{version}.{svc.EXTENSION.get(resume.content_type, 'bin')}"
    return Response(content=data, media_type=resume.content_type, headers={**HEADERS, "Content-Disposition": f'attachment; filename="{filename}"'})


# --- hrc-015 (DEC-SCOPE-379, API §12JX): signed links, documents and document requests ------------------------------------------------
LinkMode = Annotated[Literal["download", "preview"], Query()]


@router.get("/{candidate_id}/resume/{version}/link")
async def resume_link(candidate_id: UUID, version: int, response: Response, mode: LinkMode = "download", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """D4: a 300 s signed link to download the version or preview it (a DOC/DOCX through its PDF rendition). Audited before it leaves."""
    svc.require_reader(user)
    candidate = await svc.load(db, candidate_id)
    resume = await db.scalar(select(CandidateResume).where(CandidateResume.candidate_id == candidate.id, CandidateResume.version == version))
    if resume is None:
        raise HTTPException(404, "Resume version not found")
    out = await documents.link(db, "resume", resume, mode, f"resume-{candidate.candidate_code}-v{version}")
    svc.audit(db, user, "resume_link", candidate, {"version": version, "mode": mode, "role": user.role})
    await db.commit()
    svc.log("candidate_resume_link", user, candidate, version=version, mode=mode, role=user.role)
    response.headers.update(NO_STORE)
    return out


@router.get("/{candidate_id}/documents")
async def list_documents(candidate_id: UUID, response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_reader(user)
    candidate = await svc.load(db, candidate_id)
    response.headers.update(NO_STORE)
    return await documents.listing(db, candidate)


@router.post("/{candidate_id}/documents", status_code=201)
async def upload_document(
    candidate_id: UUID,
    file: UploadFile = File(...),
    document_type: str | None = Form(None),
    title: str | None = Form(None),
    request_id: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """D6/D7: a certificate or other document, optionally fulfilling one of this candidate's pending requests. Not idempotent."""
    svc.require_writer(user)
    await svc.load(db, candidate_id)  # 404 before reading a byte of an unknown candidate's upload

    async def lock() -> Candidate:
        candidate = await svc.load(db, candidate_id, lock=True)
        if candidate.archived_at is not None:
            raise HTTPException(409, svc.ARCHIVED)
        return candidate

    _, row = await documents.upload(db, user, file, (document_type, title, request_id), lock)
    return documents.document_out(row, {user.id: user})


@router.get("/{candidate_id}/documents/{document_id}/link")
async def document_link(
    candidate_id: UUID, document_id: UUID, response: Response, mode: LinkMode = "download", user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
):
    svc.require_reader(user)
    candidate = await svc.load(db, candidate_id)
    row = await documents.load_document(db, candidate, document_id)
    out = await documents.link(db, "document", row, mode, f"{row.document_type}-{candidate.candidate_code}-{str(row.id)[:8]}")
    svc.audit(db, user, "document_link", candidate, {"document_id": str(row.id), "mode": mode, "role": user.role})
    await db.commit()
    svc.log("candidate_document_link", user, candidate, document_id=str(row.id), mode=mode, role=user.role)
    response.headers.update(NO_STORE)
    return out


@router.post("/{candidate_id}/document-requests", status_code=201)
async def request_document(candidate_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """D7: ask the candidate for one document type. One pending request per type (409)."""
    svc.require_writer(user)
    body = documents.parse_request(payload)
    candidate = await svc.load(db, candidate_id, lock=True)
    if candidate.archived_at is not None:
        raise HTTPException(409, svc.ARCHIVED)
    row = await documents.add_request(db, user, candidate, body)
    await db.commit()
    svc.log("candidate_document_requested", user, candidate, request_id=str(row.id), document_type=row.document_type)
    return documents.request_out(row, None, {user.id: user})


@router.post("/{candidate_id}/document-requests/{request_id}/cancel")
async def cancel_document_request(candidate_id: UUID, request_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    svc.require_writer(user)
    candidate = await svc.load(db, candidate_id, lock=True)
    row = await documents.cancel_request(db, user, candidate, request_id)
    await db.commit()
    svc.log("candidate_document_request_cancelled", user, candidate, request_id=str(row.id))
    people = {u.id: u for u in (await db.scalars(select(User).where(User.id == row.requested_by_user_id))).all()}
    return documents.request_out(row, None, people)


# --- rec-012: extraction (DEC-SCOPE-151) ------------------------------------------------------------------------------------------
@router.post("/{candidate_id}/resume/{version}/extract")
async def extract_resume(candidate_id: UUID, version: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """EX1/EX2: suggestions from this version's text, stored on the resume row only -- the candidate and their skills are unchanged
    until Apply (AC2). A scanned PDF answers `no_text` (AC3); an unreadable or password-protected file is a 422 sentence."""
    svc.require_writer(user)
    candidate = await extraction.extractable(db, candidate_id)
    resume = await extraction.load_resume(db, candidate, version)
    await extraction.extract(db, resume)
    stored = resume.extraction_json
    svc.audit(db, user, "resume_extract", candidate, {"version": version, "skills": len(stored["skills"]), "text_chars": len(resume.extracted_text), "truncated": stored["truncated"]})
    await db.commit()
    svc.log("candidate_resume_extracted", user, candidate, version=version, skills=len(stored["skills"]), text_chars=len(resume.extracted_text))
    return await extraction.extraction_out(db, candidate, resume)


@router.post("/{candidate_id}/resume/{version}/apply")
async def apply_resume(candidate_id: UUID, version: int, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """EX6/EX7: the ticked skills and profile fields, all or nothing."""
    svc.require_writer(user)
    body = _parse(ResumeApply, payload, NOT_AN_OBJECT, RESUME_APPLY_LABELS)
    candidate = await candidate_skills.writable(db, candidate_id)
    resume = await extraction.load_resume(db, candidate, version)
    result = await extraction.apply(db, user, candidate, resume, body)
    await db.commit()
    svc.log("candidate_resume_applied", user, candidate, version=version, skills_added=result["skills_added"], fields=result["fields"])
    return result


# --- hrc-014: merge (DEC-SCOPE-377) -----------------------------------------------------------------------------------------------
@router.get("/{candidate_id}/merge")
async def merge_preview(candidate_id: UUID, response: Response, victim: Annotated[str, Query(min_length=1, max_length=20)],
                        user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Both candidates side by side, what would move and the same-requirement conflicts. Read only."""
    await duplicates.require_merger(db, user)
    response.headers.update(NO_STORE)
    return await candidate_merge.preview(db, user, candidate_id, victim)


@router.post("/{candidate_id}/merge")
async def merge_candidate(candidate_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """The victim (by code) merges into this candidate, all or nothing; a lost race on a unique pair is a 409 to retry."""
    await duplicates.require_merger(db, user)
    body = _parse(CandidateMergeBody, payload, NOT_AN_OBJECT, CANDIDATE_MERGE_LABELS)
    try:
        result = await candidate_merge.merge(db, user, candidate_id, body.victim_code, body.use_victim, body.reason)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, candidate_merge.RACE) from None
    return result
