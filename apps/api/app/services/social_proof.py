"""PUB-022 -- homepage social proof (DEC-SCOPE-210; docs/superpowers/specs/2026-10-14-pub-022-social-proof-design.md).

One place for the rules the CMS and public routes share:
- SP6: consent is recorded by the server, never by the client.
- SP9: unticking consent unpublishes.
- SP8: the strip shows at most 6 featured, published testimonials.
- Photos are validated by their bytes and have their metadata stripped (ruling R1: JPEG/PNG only).
"""

import hashlib
import logging
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SiteRatingBadge, Testimonial, User
from app.services.image_metadata import InvalidImage, detect_image_type, strip_metadata
from app.services.storage import storage

logger = logging.getLogger(__name__)

DIVISIONS = ("it", "overseas")
STRIP_LIMIT = 6
MAX_PHOTO_BYTES = 2 * 1024 * 1024
STORAGE_PREFIX = "testimonials"
PUBLISH_NEEDS_CONSENT = "Record consent before publishing"
WRONG_PHOTO = "The photo must be a JPEG or PNG image"
BAD_PHOTO = "The photo could not be read; try another image"
EMPTY_PHOTO = "The photo file is empty"


def photo_url(t: Testimonial) -> str | None:
    """Versioned by a digest of the storage key (never the key itself), so a replaced photo is a new URL for every cache."""
    if not t.photo_key:
        return None
    return f"/api/v1/public/testimonials/{t.id}/photo?v={hashlib.sha256(t.photo_key.encode()).hexdigest()[:12]}"


def public_out(t: Testimonial) -> dict:
    return {
        "id": t.id,
        "division": t.division,
        "person_name": t.person_name,
        "headline": t.headline,
        "quote": t.quote,
        "rating": t.rating,
        "context": t.context,
        "photo_url": photo_url(t),
    }


def manage_out(t: Testimonial) -> dict:
    return {
        **public_out(t),
        "published": t.published,
        "featured": t.featured,
        "display_order": t.display_order,
        "consent_confirmed": t.consent_confirmed,
        "consent_at": t.consent_at,
        "has_photo": t.photo_key is not None,
        "updated_at": t.updated_at,
    }


def badge_out(b: SiteRatingBadge) -> dict:
    return {"source_name": b.source_name, "rating": float(b.rating), "review_count": b.review_count, "review_url": b.review_url, "as_of": b.as_of}


def apply_consent(t: Testimonial, consent: bool, user: User) -> None:
    """Only a real change moves the record: re-sending true keeps the original who/when."""
    if consent and not t.consent_confirmed:
        t.consent_confirmed, t.consent_by_user_id, t.consent_at = True, user.id, datetime.now(UTC)
    elif not consent and t.consent_confirmed:
        t.consent_confirmed, t.consent_by_user_id, t.consent_at, t.published = False, None, None, False


def apply_publish(t: Testimonial, published: bool) -> None:
    if published and not t.consent_confirmed:
        raise HTTPException(422, PUBLISH_NEEDS_CONSENT)
    t.published = published


def public_testimonials():
    return select(Testimonial).where(Testimonial.published.is_(True))


async def featured(db: AsyncSession, division: str) -> list[Testimonial]:
    stmt = public_testimonials().where(Testimonial.featured.is_(True))
    if division != "all":
        stmt = stmt.where(Testimonial.division == division)
    stmt = stmt.order_by(Testimonial.display_order, Testimonial.created_at, Testimonial.id).limit(STRIP_LIMIT)
    return list((await db.scalars(stmt)).all())


async def published_badge(db: AsyncSession) -> SiteRatingBadge | None:
    badge = await db.get(SiteRatingBadge, 1)
    return badge if badge is not None and badge.published else None


async def read_photo(file: UploadFile) -> tuple[bytes, str]:
    """The type comes from the bytes, never from the file name or the client's Content-Type. Metadata such as EXIF GPS is stripped."""
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if not data:
        raise HTTPException(422, EMPTY_PHOTO)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, "The photo must be at most 2 MB")
    content_type = detect_image_type(data)
    if content_type is None:
        raise HTTPException(415, WRONG_PHOTO)
    try:
        return strip_metadata(data, content_type), content_type
    except InvalidImage:
        raise HTTPException(422, BAD_PHOTO) from None


def store_photo(data: bytes, content_type: str) -> str:
    key = f"{STORAGE_PREFIX}/{uuid4().hex}"
    try:
        storage.write_bytes(key, data, content_type)
    except Exception:
        logger.exception("testimonial_photo_store_failed")
        raise HTTPException(500, "Could not store the photo; please try again") from None
    return key


def drop_photo(key: str | None) -> None:
    """Best effort: a file that is already gone must not block a delete (SP9)."""
    if not key:
        return
    try:
        storage.delete(key)
    except Exception:
        logger.warning("testimonial_photo_delete_failed")


def read_photo_bytes(key: str) -> bytes | None:
    try:
        return storage.read_bytes(key)
    except Exception:
        logger.warning("testimonial_photo_read_failed")
        return None
