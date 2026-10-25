"""ccrm-035 (DEC-SCOPE-268 E1, E8): a one-sheet xlsx writer over the same `{columns, items, totals}` payload as `agent_reports.to_csv`.

Standard library only (openpyxl is not a runtime dependency; nehn-004 may replace this behind the same call). Numbers are number cells,
everything else an inline string through `_safe_cell`, so a cell never runs as a formula -- the CSV export's rule. The header row is frozen."""

import io
import re
import zipfile
from xml.sax.saxutils import escape, quoteattr

from app.api.school_bulk import _safe_cell

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
# XML 1.0 forbids these control characters; a pasted one would make the file unreadable.
CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
SHEET_NAME_UNSAFE = re.compile(r"[\\/:*?\[\]]")

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}"><Relationship Id="rId1" Type="{RELS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
)
WORKBOOK_RELS = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}"><Relationship Id="rId1" Type="{RELS}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
)


def _column(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _cell(ref: str, value) -> str:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return f'<c r="{ref}" t="n"><v>{value}</v></c>'
    text = CONTROL.sub("", _safe_cell("" if value is None else str(value)))
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _row(number: int, values: list) -> str:
    return f'<row r="{number}">' + "".join(_cell(f"{_column(i)}{number}", v) for i, v in enumerate(values)) + "</row>"


def to_xlsx(payload: dict, sheet_name: str) -> bytes:
    """The header (the on-screen labels), the items, then a summary's Total row -- `to_csv`'s order."""
    columns = payload["columns"]
    lines = [[c["label"] for c in columns]]
    lines += [[item[c["key"]] for c in columns] for item in [*payload["items"], *([payload["totals"]] if payload["totals"] else [])]]
    sheet = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{MAIN}">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        "<sheetData>" + "".join(_row(n, values) for n, values in enumerate(lines, start=1)) + "</sheetData></worksheet>"
    )
    name = SHEET_NAME_UNSAFE.sub(" ", sheet_name).strip()[:31] or "Sheet1"
    workbook = f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{MAIN}" xmlns:r="{RELS}"><sheets><sheet name={quoteattr(name)} sheetId="1" r:id="rId1"/></sheets></workbook>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()
