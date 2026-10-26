"""nehn-003 (DEC-SCOPE-279 PS4): per-purpose upload limits and allowed types, checked against the client's content-type AND the file's
magic bytes, so a renamed `.exe` is refused whatever it claims to be."""

from dataclasses import dataclass

from app.core.config import settings

MB = 1024 * 1024
SNIFF_BYTES = 2048

PDF = "application/pdf"
JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"
HEIC = "image/heic"
DOC = "application/msword"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# What a declared type's bytes must sniff as: OOXML files are zip containers, legacy Office files OLE2, text has no magic at all.
FAMILY = {PDF: PDF, JPEG: JPEG, PNG: PNG, WEBP: WEBP, HEIC: HEIC, DOC: "ole2", DOCX: "zip", XLSX: "zip", PPTX: "zip", "text/plain": "text", "text/csv": "text"}


class PolicyError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class Policy:
    max_bytes: int
    types: frozenset[str]


def _default() -> Policy:
    """Today's global limit and type list (`MAX_UPLOAD_BYTES`, `ALLOWED_UPLOAD_TYPES`), read at call time so config overrides apply."""
    return Policy(settings.max_upload_bytes, frozenset(t.strip() for t in settings.allowed_upload_types.split(",") if t.strip()))


POLICIES: dict[str, Policy] = {
    "assignment_submission": Policy(5 * MB, frozenset({PDF, DOC, DOCX, JPEG, PNG, HEIC})),
    "learning_material": Policy(20 * MB, frozenset({PDF, DOC, DOCX, XLSX, PPTX, JPEG, PNG})),
    "signature": Policy(1 * MB, frozenset({PNG})),
    "university_logo": Policy(1 * MB, frozenset({PNG, WEBP, JPEG})),
    "career_resume": Policy(5 * MB, frozenset({PDF, DOC, DOCX})),
}


def policy_for(purpose: str) -> Policy:
    if purpose == "default":
        return _default()
    if purpose not in POLICIES:
        raise PolicyError(422, "Unknown upload purpose")
    return POLICIES[purpose]


def sniff(head: bytes) -> str | None:
    """The family the first bytes belong to, or None when they match nothing allowed anywhere (executables, archives of other kinds…)."""
    if b"%PDF-" in head[:1024]:
        return PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return WEBP
    if head[4:8] == b"ftyp" and head[8:12] in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
        return HEIC
    if head.startswith(b"PK\x03\x04"):
        return "zip"
    if head.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return "ole2"
    if head and b"\x00" not in head and not head.startswith(b"MZ"):
        return "text"
    return None


def check_upload(purpose: str, file) -> int:
    """Check a received `UploadFile` (already spooled by Starlette) without reading it into memory; returns its size."""
    stream = file.file
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    head = stream.read(SNIFF_BYTES)
    stream.seek(0)
    check(purpose, file.content_type or "application/octet-stream", size, head)
    return size


def check(purpose: str, content_type: str, size: int, head: bytes) -> None:
    policy = policy_for(purpose)
    if size < 1 or size > policy.max_bytes:
        raise PolicyError(413, f"File size must be between 1 and {policy.max_bytes} bytes")
    if content_type not in policy.types:
        raise PolicyError(415, "This file type is not allowed")
    if sniff(head) != FAMILY.get(content_type):
        raise PolicyError(415, "The file's contents do not match its type")
