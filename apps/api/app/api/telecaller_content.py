"""tel-012 (DEC-SCOPE-082, spec §6): the script, message-template and brochure library. Managers and super_admin write; telecallers
read active rows. The library is global (T9), so there is no row scope -- only the role checks below. Rendering against a real lead
arrives with tel-008/tel-013 (C2); here a template previews with sample values.

Bodies are untyped dicts parsed by services/telecaller._parse, so a 422 is one sentence naming the field (the tel-001 idiom)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bdm import LIMIT, OFFSET, SEARCH, _matching
from app.api.deps import get_current_user
from app.api.lookups import _pattern as like_pattern
from app.api.telecaller_catalogue import _locked, _page
from app.core.database import get_db
from app.models import TelAsset, TelMessageTemplate, TelProduct, TelScript, User
from app.schemas import (
    TEL_CONTENT_FIELD_LABELS,
    TelAssetCreate,
    TelAssetLink,
    TelAssetOut,
    TelAssetPage,
    TelAssetUpdate,
    TelScriptCreate,
    TelScriptOut,
    TelScriptPage,
    TelScriptUpdate,
    TelTemplateCreate,
    TelTemplateOut,
    TelTemplatePage,
    TelTemplatePreview,
    TelTemplateUpdate,
)
from app.services import telecaller_content as svc
from app.services.telecaller import _parse, require_manager
from app.services.telecaller_catalogue import active_filters, apply_changes, audit, flush_unique, locked_active_product, sees_inactive
from app.tel_content_kinds import KINDS_BY_CHANNEL

router = APIRouter(prefix="/telecaller", tags=["telecaller-content"])
public_router = APIRouter(prefix="/public", tags=["telecaller-content"])
NOT_AN_OBJECT = "The request body must be an object"
# WhatsApp before email, then the source's kind order (§11, §12), then name.
KIND_ORDER = case(
    *((and_(TelMessageTemplate.channel == channel, TelMessageTemplate.kind == kind), index) for channel, kinds in KINDS_BY_CHANNEL.items() for index, kind in enumerate(kinds)),
    else_=99,
)


def _body(model, payload):
    return _parse(model, payload, NOT_AN_OBJECT, TEL_CONTENT_FIELD_LABELS)


async def _visible(db: AsyncSession, user: User, model, row_id: UUID, noun: str):
    """A row the caller may read: 404 when missing, and for a telecaller also when inactive."""
    row = await db.get(model, row_id)
    if not row or not (row.active or sees_inactive(user)):
        raise HTTPException(404, f"{noun} not found")
    return row


# --- scripts --------------------------------------------------------------------------------------------------------------------
def _script_taken(product: TelProduct) -> str:
    return f"{product.name} already has an active script. Deactivate it first."


@router.get("/scripts", response_model=TelScriptPage)
async def scripts(
    product_id: UUID | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Product, then name -- whatever the status, so deactivating never moves a row (QA-04)."""
    svc.require_content_reader(user)
    filters = active_filters(user, TelScript.active, active) + _matching(like_pattern(q), TelScript.name)
    if product_id:
        filters.append(TelScript.product_id == product_id)
    stmt = select(TelScript, TelProduct).join(TelProduct, TelProduct.id == TelScript.product_id).where(*filters)
    order = (func.lower(TelProduct.name), func.lower(TelScript.name), TelScript.id)
    return await _page(db, stmt, order, limit, offset, svc.script_out)


@router.post("/scripts", response_model=TelScriptOut, status_code=201)
async def create_script(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    data = _body(TelScriptCreate, payload)
    product = await locked_active_product(db, data.product_id)
    script = TelScript(product_id=product.id, name=data.name, steps=[s.model_dump() for s in data.steps], active=True)
    db.add(script)
    await flush_unique(db, svc.SCRIPT_INDEX, _script_taken(product))
    audit(db, user, "telecaller.script_create", "tel_script", script.id, ["name", "product_id", "steps"])
    out = svc.script_out(script, product)
    await db.commit()
    return out


@router.patch("/scripts/{script_id}", response_model=TelScriptOut)
async def update_script(script_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C3: reactivating, or moving to a product that already has an active script, is a 409 (the partial unique index decides)."""
    require_manager(user)
    script = await _locked(db, TelScript, script_id, "Script")
    changes = _body(TelScriptUpdate, payload).model_dump(exclude_unset=True)
    if changes.get("product_id", script.product_id) != script.product_id:
        product = await locked_active_product(db, changes["product_id"])
    else:
        product = await db.get(TelProduct, script.product_id)
    fields = apply_changes(script, changes)
    await flush_unique(db, svc.SCRIPT_INDEX, _script_taken(product))
    if fields:
        audit(db, user, "telecaller.script_update", "tel_script", script.id, fields)
    out = svc.script_out(script, product)
    await db.commit()
    return out


# --- message templates ----------------------------------------------------------------------------------------------------------
def _template_taken(channel: str, name: str) -> str:
    return f"A {svc.CHANNEL_LABEL[channel]} template named “{name}” already exists"


async def _template_refs(db: AsyncSession, template: TelMessageTemplate) -> tuple[TelProduct | None, TelAsset | None]:
    product = await db.get(TelProduct, template.product_id) if template.product_id else None
    asset = await db.get(TelAsset, template.asset_id) if template.asset_id else None
    return product, asset


@router.get("/templates", response_model=TelTemplatePage)
async def templates(
    channel: Literal["whatsapp", "email"] | None = None,
    kind: str | None = Query(None, max_length=40),
    product_id: UUID | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    svc.require_content_reader(user)
    filters = active_filters(user, TelMessageTemplate.active, active) + _matching(like_pattern(q), TelMessageTemplate.name)
    for column, value in ((TelMessageTemplate.channel, channel), (TelMessageTemplate.kind, kind), (TelMessageTemplate.product_id, product_id)):
        if value:
            filters.append(column == value)
    stmt = (
        select(TelMessageTemplate, TelProduct, TelAsset)
        .outerjoin(TelProduct, TelProduct.id == TelMessageTemplate.product_id)
        .outerjoin(TelAsset, TelAsset.id == TelMessageTemplate.asset_id)
        .where(*filters)
    )
    order = (TelMessageTemplate.channel.desc(), KIND_ORDER, func.lower(TelMessageTemplate.name), TelMessageTemplate.id)
    return await _page(db, stmt, order, limit, offset, svc.template_out)


@router.post("/templates", response_model=TelTemplateOut, status_code=201)
async def create_template(payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    require_manager(user)
    data = _body(TelTemplateCreate, payload)
    svc.check_template(data.channel, data.kind, data.subject, data.body, data.asset_id)
    product = await locked_active_product(db, data.product_id) if data.product_id else None
    asset = await svc.locked_active_asset(db, data.asset_id) if data.asset_id else None
    template = TelMessageTemplate(**data.model_dump(), active=True)
    db.add(template)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _template_taken(data.channel, data.name))
    audit(db, user, "telecaller.template_create", "tel_message_template", template.id, sorted(data.model_dump()))
    out = svc.template_out(template, product, asset)
    await db.commit()
    return out


@router.patch("/templates/{template_id}", response_model=TelTemplateOut)
async def update_template(template_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Every rule is re-checked on the merged row; a product or brochure must be active only when it is being set."""
    require_manager(user)
    template = await _locked(db, TelMessageTemplate, template_id, "Template")
    changes = _body(TelTemplateUpdate, payload).model_dump(exclude_unset=True)
    if changes.pop("channel", template.channel) != template.channel:
        raise HTTPException(422, "Channel cannot be changed")
    merged = {key: changes.get(key, getattr(template, key)) for key in ("kind", "subject", "body", "asset_id")}
    svc.check_template(template.channel, merged["kind"], merged["subject"], merged["body"], merged["asset_id"])
    if changes.get("product_id") not in (None, template.product_id):
        await locked_active_product(db, changes["product_id"])
    if changes.get("asset_id") not in (None, template.asset_id):
        await svc.locked_active_asset(db, changes["asset_id"])
    fields = apply_changes(template, changes)
    await flush_unique(db, svc.TEMPLATE_NAME_INDEX, _template_taken(template.channel, template.name))
    if fields:
        audit(db, user, "telecaller.template_update", "tel_message_template", template.id, fields)
    out = svc.template_out(template, *(await _template_refs(db, template)))
    await db.commit()
    return out


@router.get("/templates/{template_id}/preview", response_model=TelTemplatePreview)
async def preview_template(template_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """AC2 with sample values (C2). The brochure link is real (7 days) while the brochure is active; otherwise it is omitted."""
    svc.require_content_reader(user)
    template = await _visible(db, user, TelMessageTemplate, template_id, "Template")
    product, asset = await _template_refs(db, template)
    link = svc.asset_link(asset) if asset and asset.active else None
    values = {**svc.SAMPLE_VALUES, "brochure_link": link["url"] if link else ""}
    if product:
        values["product"] = product.name
    subject = svc.render(template.subject, values) if template.subject is not None else None
    return {"subject": subject, "body": svc.render(template.body, values), "brochure_link": link}


# --- brochure assets ------------------------------------------------------------------------------------------------------------
@router.get("/assets", response_model=TelAssetPage)
async def assets(
    kind: Literal["brochure", "fee"] | None = None,
    product_id: UUID | None = None,
    active: bool | None = None,
    q: str | None = SEARCH,
    limit: int = LIMIT,
    offset: int = OFFSET,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Newest upload first -- whatever the status, so deactivating never moves a row (QA-04)."""
    svc.require_content_reader(user)
    filters = active_filters(user, TelAsset.active, active) + _matching(like_pattern(q), TelAsset.name)
    for column, value in ((TelAsset.kind, kind), (TelAsset.product_id, product_id)):
        if value:
            filters.append(column == value)
    stmt = select(TelAsset, TelProduct).outerjoin(TelProduct, TelProduct.id == TelAsset.product_id).where(*filters)
    return await _page(db, stmt, (TelAsset.created_at.desc(), TelAsset.id), limit, offset, svc.asset_out)


@router.post("/assets", response_model=TelAssetOut, status_code=201)
async def upload_asset(
    name: str = Form(""),
    kind: str = Form(""),
    product_id: str = Form(""),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AC5: a PDF by its bytes, within the upload limit. The object is written before the row and deleted if the row fails."""
    require_manager(user)
    data = _body(TelAssetCreate, {"name": name, "kind": kind, "product_id": product_id or None})
    content, file_name = await svc.read_pdf(file)
    product = await locked_active_product(db, data.product_id) if data.product_id else None
    key = svc.store(content)
    try:
        asset = TelAsset(**data.model_dump(), storage_key=key, file_name=file_name, size_bytes=len(content), active=True, uploaded_by_user_id=user.id)
        db.add(asset)
        await db.flush()
        audit(db, user, "telecaller.asset_create", "tel_asset", asset.id, ["file", "kind", "name", "product_id"])
        await db.commit()
    except BaseException:
        await db.rollback()
        svc.discard(key)
        raise
    await db.refresh(asset)
    return svc.asset_out(asset, product)


@router.patch("/assets/{asset_id}", response_model=TelAssetOut)
async def update_asset(asset_id: UUID, payload: dict = Body(...), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Metadata only. Deactivating ends every link at once (AC4); templates that use it keep it but stop previewing a link."""
    require_manager(user)
    asset = await _locked(db, TelAsset, asset_id, "Brochure")
    changes = _body(TelAssetUpdate, payload).model_dump(exclude_unset=True)
    if changes.get("product_id") not in (None, asset.product_id):
        await locked_active_product(db, changes["product_id"])
    fields = apply_changes(asset, changes)
    if fields:
        audit(db, user, "telecaller.asset_update", "tel_asset", asset.id, fields)
    out = svc.asset_out(asset, await db.get(TelProduct, asset.product_id) if asset.product_id else None)
    await db.commit()
    return out


@router.post("/assets/{asset_id}/link", response_model=TelAssetLink)
async def asset_link(asset_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """C1: a 7-day signed link for one active brochure. Nothing is stored; the token is never logged."""
    svc.require_content_reader(user)
    asset = await db.get(TelAsset, asset_id)
    if not asset or not asset.active:
        raise HTTPException(404, "Brochure not found")
    return svc.asset_link(asset)


@public_router.get("/telecaller-assets/{token}")
async def public_asset(token: str, db: AsyncSession = Depends(get_db)):
    """AC4: no session. Every failure -- bad, expired or foreign token, missing or deactivated brochure, unreadable object -- is the same
    404, so nothing is learned about which."""
    asset = await svc.asset_from_token(db, token)
    content = svc.read_object(asset) if asset else None
    if content is None:
        raise HTTPException(404, "This link has expired or is no longer available")
    return Response(content=content, media_type=svc.PDF, headers=svc.download_headers(asset.file_name))
