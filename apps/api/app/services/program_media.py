"""PUB-025 (DEC-SCOPE-334): an IT course's card image and its syllabus.

S1 one source per course: "manual" (modules with topics), "link" (a Google Drive or other https link) or "pdf" (an uploaded PDF).
Setting a source clears the other two, and an uploaded PDF the course no longer uses is deleted.
S2 the syllabus is public with no enquiry gate.
S3 the card image is optional (PNG/JPEG/WebP, 2 MB, metadata stripped). A course without one keeps its generated tile.
Files live under one public prefix with server-made names, and the public route serves a file only while an active course uses it.
"""

import re
import uuid
from urllib.parse import urlsplit

from fastapi import HTTPException, UploadFile
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Program
from app.services import upload_policy
from app.services.image_metadata import JPEG, PNG, WEBP, InvalidImage, image_size, strip_metadata
from app.services.storage import storage

PREFIX = "public/programs"
URL_PREFIX = "/api/v1/public/program-files/"
FILE_NAME = re.compile(r"[0-9a-f]{32}\.(png|jpg|webp|pdf)")
TYPES = {"png": PNG, "jpg": JPEG, "webp": WEBP, "pdf": upload_policy.PDF}
MIN_SIDE, MAX_SIDE = 120, 4096
SOURCES = ("manual", "link", "pdf")
MAX_MODULES, MAX_TOPICS, MAX_TITLE, MAX_TOPIC, MAX_URL = 40, 40, 160, 300, 500
logger = get_logger("app.program_media")


def _policy(purpose: str, file: UploadFile) -> None:
    try:
        upload_policy.check_upload(purpose, file)
    except upload_policy.PolicyError as refused:
        raise HTTPException(refused.status_code, refused.detail) from None


async def read_image(file: UploadFile, purpose: str = "program_image") -> tuple[bytes, str]:
    """The image's bytes (metadata stripped where we can) and type, or 413/415 from the policy, 422 for an unreadable or out-of-range size.
    itc-019 reuses it for the trainer photo (`purpose="trainer_photo"`)."""
    _policy(purpose, file)
    content_type = str(file.content_type)
    data = await file.read()
    size = image_size(data, content_type)
    if size is None:
        raise HTTPException(422, "The image size could not be read")
    if not all(MIN_SIDE <= side <= MAX_SIDE for side in size):
        raise HTTPException(422, f"The image must be {MIN_SIDE}-{MAX_SIDE} pixels wide and high")
    if content_type == WEBP:
        return data, content_type
    try:
        return strip_metadata(data, content_type), content_type
    except InvalidImage:
        raise HTTPException(422, "The image file is damaged") from None


def check_pdf(file: UploadFile) -> None:
    _policy("program_syllabus", file)


def _new_name(content_type: str) -> str:
    return f"{uuid.uuid4().hex}.{next(ext for ext, kind in TYPES.items() if kind == content_type)}"


def store_bytes(data: bytes, content_type: str) -> str:
    name = _new_name(content_type)
    try:
        storage.write_bytes(f"{PREFIX}/{name}", data, content_type)
    except Exception:
        logger.exception("program_media_store_failed")
        raise HTTPException(500, "Could not store the file; please try again") from None
    return URL_PREFIX + name


def store_pdf(file: UploadFile) -> str:
    name = _new_name(upload_policy.PDF)
    try:
        storage.write_stream(f"{PREFIX}/{name}", file.file, upload_policy.PDF)
    except Exception:
        logger.exception("program_media_store_failed")
        raise HTTPException(500, "Could not store the file; please try again") from None
    return URL_PREFIX + name


def file_name(url: str | None) -> str | None:
    name = url.removeprefix(URL_PREFIX) if url and url.startswith(URL_PREFIX) else ""
    return name if FILE_NAME.fullmatch(name) else None


def delete(url: str | None) -> None:
    """Best effort; only for a file `store_*` wrote."""
    name = file_name(url)
    if name is None:
        return
    try:
        storage.delete(f"{PREFIX}/{name}")
    except Exception:
        logger.warning("program_media_delete_failed")


def clean_modules(raw: object) -> list[dict]:
    """S1 manual: a list of {title, topics[]}; blank topics dropped, at least one module with a title. 422 otherwise."""
    if not isinstance(raw, list) or not raw:
        raise HTTPException(422, "Add at least one syllabus module")
    if len(raw) > MAX_MODULES:
        raise HTTPException(422, f"A syllabus can have at most {MAX_MODULES} modules")
    modules = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise HTTPException(422, f"Module {index} is not valid")
        title = item.get("title")
        topics = item.get("topics", [])
        if not isinstance(title, str) or not title.strip():
            raise HTTPException(422, f"Module {index} needs a title")
        if len(title.strip()) > MAX_TITLE:
            raise HTTPException(422, f"Module {index}'s title is longer than {MAX_TITLE} characters")
        if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
            raise HTTPException(422, f"Module {index}'s topics must be text lines")
        kept = [t.strip() for t in topics if t.strip()]
        if len(kept) > MAX_TOPICS:
            raise HTTPException(422, f"Module {index} can have at most {MAX_TOPICS} topics")
        if any(len(t) > MAX_TOPIC for t in kept):
            raise HTTPException(422, f"A topic in module {index} is longer than {MAX_TOPIC} characters")
        modules.append({"title": title.strip(), "topics": kept})
    return modules


def clean_link(raw: object) -> str:
    """S1 link: an absolute https URL (Google Drive or any other host), at most 500 characters."""
    if not isinstance(raw, str) or not raw.strip():
        raise HTTPException(422, "Enter the syllabus link")
    url = raw.strip()
    parts = urlsplit(url)
    if len(url) > MAX_URL or parts.scheme != "https" or not parts.hostname or any(c.isspace() for c in url):
        raise HTTPException(422, f"The syllabus link must be a full https:// address of at most {MAX_URL} characters")
    return url


def media_out(p: Program) -> dict:
    return {"id": p.id, "slug": p.slug, "title": p.title, "image_url": p.image_url, "syllabus": p.syllabus}


async def owner_of(db: AsyncSession, url: str) -> Program | None:
    """The active course that currently shows this file (as its image or its PDF syllabus), if any."""
    return await db.scalar(
        select(Program).where(
            Program.active.is_(True),
            or_(Program.image_url == url, (Program.syllabus_source == "pdf") & (Program.syllabus_pdf_url == url)),
        ).limit(1)
    )
