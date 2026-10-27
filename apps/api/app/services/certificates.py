from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import CertificateSignatory
from app.services.storage import storage

# Token system for this template, grounded in an IT training academy's own vernacular
# (a terminal, a CI status bar, an IDE's line-number gutter) rather than the generic
# gold-cornered "diploma" look -- deliberately not corporate blue, not laurel wreaths.
INK = HexColor("#0E1B2B")
PAPER = HexColor("#FBF8F2")
SIGNAL = HexColor("#2FAE73")
SLATE = HexColor("#5B6B7C")

GUTTER_WIDTH = 70

# nehn-032 (DEC-SCOPE-300): the two signature slots, left to right; the upload's pixel bounds (S4) and the drawn box in points (S8).
SIGNATORY_ROLES = ("founder", "coordinator")
SIGNATURE_MIN_PX, SIGNATURE_MAX_PX = (50, 20), (2000, 1000)
SIGNATURE_BOX = (170, 50)
SIGNATURE_LINE_Y = 228


def _fit_font_size(pdf: canvas.Canvas, text: str, font: str, max_width: float, start_size: float, min_size: float = 14) -> float:
    size = start_size
    while size > min_size and pdf.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


async def active_signatories(db: AsyncSession) -> list[CertificateSignatory]:
    """The active version of each slot, in slot order (a slot without one is simply absent)."""
    rows = (await db.scalars(select(CertificateSignatory).where(CertificateSignatory.active_to.is_(None)))).all()
    return sorted(rows, key=lambda row: SIGNATORY_ROLES.index(row.role))


def missing_signatories(rows: Sequence[CertificateSignatory]) -> list[str]:
    present = {row.role for row in rows}
    return [role for role in SIGNATORY_ROLES if role not in present]


def require_signatories(rows: Sequence[CertificateSignatory]) -> None:
    """S7: no certificate (or preview) without both signatures."""
    if missing := missing_signatories(rows):
        raise HTTPException(409, f"Certificate signatures are not configured: {', '.join(missing)}")


def signatory_snapshot(rows: Sequence[CertificateSignatory]) -> list[dict]:
    return [{"id": str(row.id), "role": row.role, "display_name": row.display_name, "designation": row.designation} for row in rows]


def check_signature_image(data: bytes) -> None:
    """S4, after the nehn-003 `signature` policy (PNG type, size, magic bytes): it must decode, fit the pixel bounds and have an alpha
    channel. The size comes from the header, so an oversized image is refused before any pixel is decoded."""
    try:
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            if not (SIGNATURE_MIN_PX[0] <= width <= SIGNATURE_MAX_PX[0] and SIGNATURE_MIN_PX[1] <= height <= SIGNATURE_MAX_PX[1]):
                raise HTTPException(422, f"The signature must be {SIGNATURE_MIN_PX[0]}-{SIGNATURE_MAX_PX[0]} px wide and {SIGNATURE_MIN_PX[1]}-{SIGNATURE_MAX_PX[1]} px high")
            transparent = image.mode in ("RGBA", "LA", "PA") or (image.mode == "P" and "transparency" in image.info)
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "The signature is not a readable PNG image") from error
    if not transparent:
        raise HTTPException(422, "The signature must have a transparent background")


@lru_cache(maxsize=16)
def _signature_image(key: str) -> ImageReader:
    """Decoded once per worker: keys are never reused (a new image is a new key), so a cached entry cannot go stale."""
    return ImageReader(BytesIO(storage.read_bytes(key)))


def _draw_signatories(pdf: canvas.Canvas, signatories: Sequence[CertificateSignatory], content_left: float, content_width: float) -> None:
    """S8: each signatory centred in its share of the content width -- the image on the signature line, scaled to fit the box with its
    aspect ratio, then the name and designation, each shrunk to fit the slot."""
    slot_width = content_width / max(len(signatories), 1)
    box_width, box_height = SIGNATURE_BOX
    for index, signatory in enumerate(signatories):
        center = content_left + slot_width * (index + 0.5)
        image = _signature_image(signatory.image_key)
        pixel_width, pixel_height = image.getSize()
        scale = min(box_width / pixel_width, box_height / pixel_height)
        width, height = pixel_width * scale, pixel_height * scale
        pdf.drawImage(image, center - width / 2, SIGNATURE_LINE_Y + 3, width, height, mask="auto")
        pdf.setStrokeColor(SLATE)
        pdf.setLineWidth(0.6)
        pdf.line(center - box_width / 2 - 10, SIGNATURE_LINE_Y, center + box_width / 2 + 10, SIGNATURE_LINE_Y)
        text_width = slot_width - 30
        name_size = _fit_font_size(pdf, signatory.display_name, "Helvetica-Bold", text_width, 10.5, min_size=7)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica-Bold", name_size)
        pdf.drawCentredString(center, SIGNATURE_LINE_Y - 14, signatory.display_name)
        designation_size = _fit_font_size(pdf, signatory.designation, "Helvetica", text_width, 9, min_size=6)
        pdf.setFillColor(SLATE)
        pdf.setFont("Helvetica", designation_size)
        pdf.drawCentredString(center, SIGNATURE_LINE_Y - 26, signatory.designation)


def generate_certificate_pdf(*, certificate_no: str, student_name: str, program_title: str, issued_on: date, verification_code: str, signatories: Sequence[CertificateSignatory]) -> str:
    data = render_certificate_pdf(
        certificate_no=certificate_no, student_name=student_name, program_title=program_title, issued_on=issued_on, verification_code=verification_code, signatories=signatories
    )
    key = f"certificates/{certificate_no}.pdf"
    storage.write_bytes(key, data, "application/pdf")  # nehn-003 PS7: one storage path for every writer
    if settings.aws_s3_bucket:
        return f"s3://{settings.aws_s3_bucket}/{key}"
    return f"/local-files/{key}"


def render_certificate_pdf(*, certificate_no: str, student_name: str, program_title: str, issued_on: date, verification_code: str, signatories: Sequence[CertificateSignatory]) -> bytes:
    """The certificate as PDF bytes, stored by `generate_certificate_pdf` or streamed as the admin preview (nehn-032 S9)."""
    buffer = BytesIO()
    width, height = landscape(A4)
    pdf = canvas.Canvas(buffer, pagesize=(width, height))

    pdf.setFillColor(PAPER)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(1.2)
    pdf.rect(18, 18, width - 36, height - 36, fill=0, stroke=1)

    # Signature element (1 of 2): a solid ink gutter down the left edge with the
    # wordmark set vertically, evoking an editor's line-number gutter rather than a
    # decorative border or seal.
    pdf.setFillColor(INK)
    pdf.rect(18, 18, GUTTER_WIDTH, height - 36, fill=1, stroke=0)
    pdf.saveState()
    pdf.translate(18 + GUTTER_WIDTH / 2 + 6, height / 2)
    pdf.rotate(90)
    pdf.setFillColor(PAPER)
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(0, 0, "E D U S P H E R E   ·   I T   A C A D E M Y")
    pdf.restoreState()

    content_left = 18 + GUTTER_WIDTH + 34
    content_right = width - 56
    content_center = (content_left + content_right) / 2
    content_width = content_right - content_left

    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 10.5)
    pdf.drawCentredString(content_center, height - 78, "E D U S P H E R E   I T   A C A D E M Y   P R E S E N T S")

    pdf.setFillColor(INK)
    pdf.setFont("Times-Bold", 34)
    pdf.drawCentredString(content_center, height - 128, "Certificate of Completion")

    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica-Oblique", 13)
    pdf.drawCentredString(content_center, height - 168, "This certifies that")

    name_size = _fit_font_size(pdf, student_name, "Times-Bold", content_width - 40, 32)
    pdf.setFillColor(INK)
    pdf.setFont("Times-Bold", name_size)
    name_y = height - 212
    pdf.drawCentredString(content_center, name_y, student_name)
    name_width = pdf.stringWidth(student_name, "Times-Bold", name_size)
    pdf.setStrokeColor(SIGNAL)
    pdf.setLineWidth(2)
    pdf.line(content_center - name_width / 2, name_y - 10, content_center + name_width / 2, name_y - 10)

    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 13)
    pdf.drawCentredString(content_center, height - 252, "has successfully completed the program")

    program_size = _fit_font_size(pdf, program_title, "Helvetica-Bold", content_width - 40, 21)
    pdf.setFillColor(INK)
    pdf.setFont("Helvetica-Bold", program_size)
    pdf.drawCentredString(content_center, height - 290, program_title)

    # nehn-032 (DEC-SCOPE-300 S8): the Founder and Coordinator signatures, between the program and the authenticity rule.
    _draw_signatories(pdf, signatories, content_left, content_width)

    # A thin section rule (the same left-gutter vernacular, not a decorative flourish)
    # gives the eye a resting point between the achievement text and the footer,
    # instead of a stretch of unexplained blank space on a landscape page this wide.
    pdf.setStrokeColor(SLATE)
    pdf.setLineWidth(0.5)
    pdf.line(content_left, 185, content_right, 185)
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawCentredString(content_center, 167, "Authenticity can be confirmed with the verification code below.")

    # Footer: issued date (left) and a terminal-styled verification block (right) --
    # signature element (2 of 2). `verification_code` has always had a real public
    # lookup (GET /public/certificates/{verification_code}) but was never printed
    # anywhere on the certificate itself before this -- without it there was nothing
    # for a verifier to actually type in.
    footer_y = 80
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(content_left, footer_y + 14, "ISSUED")
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 12)
    pdf.drawString(content_left, footer_y, issued_on.isoformat())

    box_width = 260
    box_height = 40
    box_x = content_right - box_width
    box_y = footer_y - 6
    pdf.setStrokeColor(INK)
    pdf.setLineWidth(0.75)
    pdf.roundRect(box_x, box_y, box_width, box_height, 4, fill=0, stroke=1)
    pdf.setFillColor(SIGNAL)
    pdf.circle(box_x + 14, box_y + box_height - 13, 3, fill=1, stroke=0)
    pdf.setFillColor(INK)
    pdf.setFont("Courier-Bold", 9)
    pdf.drawString(box_x + 22, box_y + box_height - 16, f"verify {certificate_no}")
    pdf.setFillColor(SLATE)
    pdf.setFont("Courier", 8.5)
    pdf.drawString(box_x + 14, box_y + 8, f"code: {verification_code}")

    pdf.save()
    return buffer.getvalue()
