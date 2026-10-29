"""nehn-035 (DEC-SCOPE-331 L2-L4): uploaded university logos -- checked against the nehn-003 `university_logo` policy (PNG, JPEG, WebP,
1 MB; never SVG), sized from the header, stripped of metadata, stored under the public prefix, and dropped when replaced."""

import re
import uuid

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import University
from app.services import upload_policy
from app.services.image_metadata import JPEG, PNG, WEBP, InvalidImage, image_size, strip_metadata
from app.services.storage import storage

LOGO_PREFIX = "public/university-logos"
LOGO_URL_PREFIX = "/api/v1/public/university-logos/"
LOGO_NAME = re.compile(r"[0-9a-f]{32}\.(png|jpg|webp)")
LOGO_TYPES = {"png": PNG, "jpg": JPEG, "webp": WEBP}
MIN_SIDE, MAX_SIDE = 32, 2048
logger = get_logger("app.university_logos")


async def read_logo(file: UploadFile) -> tuple[bytes, str]:
    """The logo's bytes (metadata stripped) and type, or the refusal: 413/415 from the policy, 422 for an unreadable or out-of-range size."""
    try:
        upload_policy.check_upload("university_logo", file)
    except upload_policy.PolicyError as refused:
        raise HTTPException(refused.status_code, refused.detail) from None
    content_type = str(file.content_type)
    data = await file.read()
    size = image_size(data, content_type)
    if size is None:
        raise HTTPException(422, "The logo's image size could not be read")
    if not all(MIN_SIDE <= side <= MAX_SIDE for side in size):
        raise HTTPException(422, f"The logo must be {MIN_SIDE}-{MAX_SIDE} pixels wide and high")
    if content_type == WEBP:  # no metadata stripper for WebP; a logo is public artwork, not a personal photo
        return data, content_type
    try:
        return strip_metadata(data, content_type), content_type
    except InvalidImage:
        raise HTTPException(422, "The logo file is damaged") from None


def store(data: bytes, content_type: str) -> str:
    """Writes the logo under a fresh name and returns its public URL."""
    extension = next(ext for ext, kind in LOGO_TYPES.items() if kind == content_type)
    name = f"{uuid.uuid4().hex}.{extension}"
    try:
        storage.write_bytes(f"{LOGO_PREFIX}/{name}", data, content_type)
    except Exception:
        logger.exception("university_logo_store_failed")
        raise HTTPException(500, "Could not store the logo; please try again") from None
    return LOGO_URL_PREFIX + name


def _uploaded_name(logo_url: str | None) -> str | None:
    name = logo_url.removeprefix(LOGO_URL_PREFIX) if logo_url and logo_url.startswith(LOGO_URL_PREFIX) else ""
    return name if LOGO_NAME.fullmatch(name) else None


def delete(logo_url: str | None) -> None:
    """Best effort, and only for a logo `store` wrote -- a bundled `/universities/logos/` or `https://` logo is never touched. On its own
    only for a just-stored logo whose commit failed (nothing points at it); otherwise use `drop_unused`."""
    name = _uploaded_name(logo_url)
    if name is None:
        return
    try:
        storage.delete(f"{LOGO_PREFIX}/{name}")
    except Exception:
        logger.warning("university_logo_delete_failed")


async def drop_unused(db: AsyncSession, logo_url: str | None) -> None:
    """After a commit that let `logo_url` go: deletes it unless a university still uses it (the form accepts a copied uploaded URL)."""
    if _uploaded_name(logo_url) and not await db.scalar(select(University.id).where(University.logo_url == logo_url).limit(1)):
        delete(logo_url)
