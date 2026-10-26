from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.services.storage import storage


def _generate_billing_pdf(*, kind: str, doc_no: str, payer_name: str, amount: float, currency: str, issued_on: date, reference_type: str, student_name: str | None = None) -> str:
    """Shared layout for Invoice/Receipt PDFs -- same minimal-document pattern as
    `services/certificates.py`'s `generate_certificate_pdf`. Exact invoice/receipt format is an
    explicitly open item (`PRD_OPEN_ITEMS.md` item 12, currency/tax mapping); this renders the
    confirmed fields only (amount, currency, payer, reference) rather than inventing a tax/GST
    breakdown that has no confirmed rate anywhere.
    """
    buffer = BytesIO()
    width, height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFillColor(HexColor("#071B38"))
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(56, height - 90, kind)
    pdf.setFillColor(HexColor("#61728A"))
    pdf.setFont("Helvetica", 12)
    pdf.drawString(56, height - 120, f"{kind} No: {doc_no}")
    pdf.drawString(56, height - 140, f"Issued: {issued_on.isoformat()}")
    pdf.setFillColor(HexColor("#071B38"))
    pdf.setFont("Helvetica", 13)
    pdf.drawString(56, height - 190, f"Billed to: {payer_name}")
    pdf.drawString(56, height - 214, f"Reference: {reference_type}")
    if student_name:  # AGN-011 AC5: an agent deposit names the student it was paid for (drawString: literal text, no markup)
        pdf.drawString(56, height - 238, f"Student: {student_name}")
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(56, height - 260, f"{currency} {amount:,.2f}")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(HexColor("#61728A"))
    pdf.drawString(56, 50, "EduSphere -- amounts shown in the currency charged; exact tax/region mapping is a documented open item.")
    pdf.save()
    data = buffer.getvalue()
    key = f"{kind.lower()}s/{doc_no}.pdf"
    storage.write_bytes(key, data, "application/pdf")  # nehn-003 PS7: one storage path for every writer
    if settings.aws_s3_bucket:
        return f"s3://{settings.aws_s3_bucket}/{key}"
    return f"/local-files/{key}"


def generate_invoice_pdf(*, invoice_no: str, payer_name: str, amount: float, currency: str, issued_on: date, reference_type: str) -> str:
    return _generate_billing_pdf(kind="Invoice", doc_no=invoice_no, payer_name=payer_name, amount=amount, currency=currency, issued_on=issued_on, reference_type=reference_type)


def generate_receipt_pdf(*, receipt_no: str, payer_name: str, amount: float, currency: str, issued_on: date, reference_type: str, student_name: str | None = None) -> str:
    return _generate_billing_pdf(
        kind="Receipt", doc_no=receipt_no, payer_name=payer_name, amount=amount, currency=currency, issued_on=issued_on, reference_type=reference_type, student_name=student_name
    )
