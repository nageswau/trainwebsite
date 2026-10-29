from datetime import date
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.core.config import settings
from app.services.storage import storage


def _generate_billing_pdf(*, kind: str, doc_no: str, payer_name: str, amount: float, currency: str, issued_on: date, reference_type: str) -> str:
    """The invoice layout -- same minimal-document pattern as
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
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(56, height - 260, f"{currency} {amount:,.2f}")
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(HexColor("#61728A"))
    pdf.drawString(56, 50, "EduSphere -- amounts shown in the currency charged; exact tax/region mapping is a documented open item.")
    pdf.save()
    return _store(kind, doc_no, buffer.getvalue())


def _store(kind: str, doc_no: str, data: bytes) -> str:
    key = f"{kind.lower()}s/{doc_no}.pdf"
    storage.write_bytes(key, data, "application/pdf")  # nehn-003 PS7: one storage path for every writer
    if settings.aws_s3_bucket:
        return f"s3://{settings.aws_s3_bucket}/{key}"
    return f"/local-files/{key}"


def generate_invoice_pdf(*, invoice_no: str, payer_name: str, amount: float, currency: str, issued_on: date, reference_type: str) -> str:
    return _generate_billing_pdf(kind="Invoice", doc_no=invoice_no, payer_name=payer_name, amount=amount, currency=currency, issued_on=issued_on, reference_type=reference_type)


DASH = "—"


def receipt_lines(
    *,
    receipt_no: str,
    payment_date: date | None,
    payer_name: str,
    currency: str,
    gross: float,
    discount: float,
    paid: float,
    balance: float,
    status: str,
    reference_type: str | None = None,
    student_name: str | None = None,
    student_code: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    course: str | None = None,
    batch: str | None = None,
) -> list[tuple[str, str]]:
    """nehn-019 AC1/AC3: every field the receipt lists, in order, with "—" for a value that is not known (and for no discount)."""

    def money(value: float) -> str:
        return f"{currency} {value:,.2f}"

    return [
        ("Receipt No", receipt_no),
        ("Payment date", payment_date.isoformat() if payment_date else DASH),
        ("Billed to", payer_name),
        ("Student", student_name or DASH),
        ("Student code", student_code or DASH),
        ("Email", email or DASH),
        ("Phone", phone or DASH),
        ("Course", course or DASH),
        ("Batch", batch or DASH),
        ("Reference", reference_type or DASH),
        ("Gross amount", money(gross)),
        ("Discount", money(discount) if discount else DASH),
        ("Amount paid", money(paid)),
        ("Remaining balance", money(balance)),
        ("Payment status", status),
    ]


def generate_receipt_pdf(*, receipt_no: str, issued_on: date, lines: list[tuple[str, str]]) -> str:
    """nehn-019: the receipt is a label/value table of `receipt_lines` (drawString: literal text, no markup). Issued once, at payment,
    and never regenerated (D4) -- it is the snapshot of that moment, so its balance is the balance just after this payment."""
    buffer = BytesIO()
    width, height = A4
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setFillColor(HexColor("#071B38"))
    pdf.setFont("Helvetica-Bold", 26)
    pdf.drawString(56, height - 90, "Receipt")
    pdf.setFillColor(HexColor("#61728A"))
    pdf.setFont("Helvetica", 12)
    pdf.drawString(56, height - 120, f"Issued: {issued_on.isoformat()}")
    y = height - 165
    for label, value in lines:
        bold = label in {"Amount paid", "Payment status"}
        pdf.setFillColor(HexColor("#61728A"))
        pdf.setFont("Helvetica", 11)
        pdf.drawString(56, y, label)
        pdf.setFillColor(HexColor("#071B38"))
        pdf.setFont("Helvetica-Bold" if bold else "Helvetica", 12)
        pdf.drawString(220, y, value[:70])
        y -= 24
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(HexColor("#61728A"))
    pdf.drawString(56, 50, "EduSphere -- amounts shown in the currency charged; exact tax/region mapping is a documented open item.")
    pdf.save()
    return _store("Receipt", receipt_no, buffer.getvalue())
