"""hrc-015 (DEC-SCOPE-379 D1/D3): PDF previews of DOC/DOCX resumes and candidate documents.

A DOC/DOCX upload commits with `preview_status = 'pending'` and queues `convert_candidate_preview_task`; the worker converts the stored file
with headless LibreOffice (its own throw-away directory and profile, a time limit, nothing from the file is ever run by us), stores the PDF
under `candidate-previews/` and marks the row `ready`, or `failed` when the converter is missing or the file cannot be converted (a
password-protected or broken file). Only a pending row is converted, so a repeated task does nothing. Logs carry ids, never file names."""

import asyncio
import logging
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CandidateDocument, CandidateResume
from app.services import candidates

logger = logging.getLogger("app.candidate_previews")

PREFIX = candidates.PREVIEW_PREFIX
CONVERTIBLE = frozenset({candidates.DOC, candidates.DOCX})
TIMEOUT_SECONDS = 60
MODELS = {"resume": CandidateResume, "document": CandidateDocument}


class ConversionError(Exception):
    pass


def initial_status(content_type: str) -> str | None:
    return "pending" if content_type in CONVERTIBLE else None


def enqueue(kind: str, row_id: UUID) -> None:
    """After the upload's commit. A broker failure leaves the row pending (the preview says it is being prepared) and is logged."""
    from app.worker import convert_candidate_preview_task

    try:
        convert_candidate_preview_task.delay(kind, str(row_id))
    except Exception:
        logger.warning("candidate_preview_enqueue_failed", extra={"extra_fields": {"kind": kind, "id": str(row_id)}}, exc_info=True)


def soffice_pdf(data: bytes, extension: str) -> bytes:
    """Convert with `soffice --headless --convert-to pdf` in a temporary directory with its own LibreOffice profile and HOME."""
    binary = shutil.which("soffice") or shutil.which("libreoffice")
    if binary is None:
        raise ConversionError("LibreOffice is not installed")
    with tempfile.TemporaryDirectory(prefix="preview-") as work:
        folder = Path(work)
        source = folder / f"source.{extension}"
        source.write_bytes(data)
        command = [
            binary, f"-env:UserInstallation={(folder / 'profile').as_uri()}", "--headless", "--norestore", "--nolockcheck",
            "--convert-to", "pdf", "--outdir", str(folder), str(source),
        ]  # fmt: skip
        try:
            subprocess.run(command, capture_output=True, timeout=TIMEOUT_SECONDS, check=False, env={"HOME": work, "PATH": "/usr/bin:/bin"})
        except subprocess.TimeoutExpired:
            raise ConversionError("timed out") from None
        output = folder / "source.pdf"
        if not output.exists():
            raise ConversionError("no output")
        pdf = output.read_bytes()
    if not pdf.startswith(b"%PDF-"):
        raise ConversionError("not a PDF")
    return pdf


async def convert(kind: str, row_id: UUID | str, converter: Callable[[bytes, str], bytes] = soffice_pdf) -> str | None:
    """Convert one pending row in its own session; returns the row's status afterwards (None when the row is gone)."""
    from app.core.database import SessionLocal

    model = MODELS[kind]
    row_id = UUID(str(row_id))
    async with SessionLocal() as db:
        row = await db.get(model, row_id)
        if row is None or row.preview_status != "pending":
            return row.preview_status if row else None
        data = candidates.read_key(row.storage_key)
        extension = candidates.EXTENSION[row.content_type]
        await db.rollback()  # no transaction is held open while the converter runs
        try:
            pdf = await asyncio.to_thread(converter, data, extension)
            key = candidates.store(pdf, candidates.PDF, PREFIX)
            status = "ready"
        except Exception as exc:
            logger.warning("candidate_preview_failed", extra={"extra_fields": {"kind": kind, "id": str(row_id), "reason": type(exc).__name__}})
            key, status = None, "failed"
        row = await db.scalar(select(model).where(model.id == row_id).with_for_update())
        if row is None or row.preview_status != "pending":  # converted meanwhile by another run
            await db.rollback()
            if key:
                candidates.discard(key)
            return row.preview_status if row else None
        row.preview_status, row.preview_key = status, key
        await db.commit()
    logger.info("candidate_preview_converted", extra={"extra_fields": {"kind": kind, "id": str(row_id), "status": status}})
    return status


async def target(db: AsyncSession, kind: str, row: CandidateResume | CandidateDocument) -> tuple[str, str]:
    """The (key, content type) a preview link serves: the file itself for a PDF or image, else the ready rendition. A DOC/DOCX from
    before hrc-015 (no status) is queued now; 409 while a rendition is being prepared, 422 when there is none."""
    if row.content_type not in CONVERTIBLE:
        return row.storage_key, row.content_type
    if row.preview_status == "ready" and row.preview_key:
        return row.preview_key, candidates.PDF
    if row.preview_status is None:
        row.preview_status = "pending"
        await db.commit()
        enqueue(kind, row.id)
    if row.preview_status == "pending":
        raise HTTPException(409, "The preview is still being prepared. Try again in a moment.")
    raise HTTPException(422, "A preview isn't available for this file. Download it instead.")
