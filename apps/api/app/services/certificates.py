from datetime import date
from io import BytesIO
from pathlib import Path

import boto3
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from app.core.config import settings

# Token system for this template, grounded in an IT training academy's own vernacular
# (a terminal, a CI status bar, an IDE's line-number gutter) rather than the generic
# gold-cornered "diploma" look -- deliberately not corporate blue, not laurel wreaths.
INK = HexColor("#0E1B2B")
PAPER = HexColor("#FBF8F2")
SIGNAL = HexColor("#2FAE73")
SLATE = HexColor("#5B6B7C")

GUTTER_WIDTH = 70


def _fit_font_size(pdf: canvas.Canvas, text: str, font: str, max_width: float, start_size: float, min_size: float = 14) -> float:
    size = start_size
    while size > min_size and pdf.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def generate_certificate_pdf(*, certificate_no: str, student_name: str, program_title: str, issued_on: date, verification_code: str) -> str:
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

    # A thin section rule (the same left-gutter vernacular, not a decorative flourish)
    # gives the eye a resting point between the achievement text and the footer,
    # instead of a stretch of unexplained blank space on a landscape page this wide.
    pdf.setStrokeColor(SLATE)
    pdf.setLineWidth(0.5)
    pdf.line(content_left, 195, content_right, 195)
    pdf.setFillColor(SLATE)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawCentredString(content_center, 175, "Authenticity can be confirmed with the verification code below.")

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
    data = buffer.getvalue()
    key = f"certificates/{certificate_no}.pdf"
    if settings.aws_s3_bucket:
        boto3.client("s3", region_name=settings.aws_region).put_object(Bucket=settings.aws_s3_bucket, Key=key, Body=data, ContentType="application/pdf", ServerSideEncryption="AES256")
        return f"s3://{settings.aws_s3_bucket}/{key}"
    destination = Path(settings.local_upload_dir) / key
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return f"/local-files/{key}"
