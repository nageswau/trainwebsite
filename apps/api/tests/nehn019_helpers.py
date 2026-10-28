"""nehn-019: read a receipt PDF back as its label/value table."""

from pdf_text import pdf_text


def receipt_rows(data: bytes) -> dict[str, str]:
    """After the "Receipt" and "Issued:" lines, labels and values alternate; the footer is last."""
    lines = [line for line in pdf_text(data).split("\n") if line]  # reportlab's colour changes add empty text objects
    return dict(zip(lines[2:-1:2], lines[3:-1:2], strict=True))
