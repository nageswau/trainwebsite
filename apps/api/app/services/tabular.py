"""The shared spreadsheet helper: `to_xlsx`, a one-sheet writer over the same `{columns, items, totals}` payload as `agent_reports.to_csv`
(ccrm-035, DEC-SCOPE-268 E1/E8), and `read_tabular`, the one hardened `.xlsx`/`.csv` reader for imports (nehn-004, DEC-SCOPE-280).

The writer is standard library only. Numbers and dates are typed cells (nehn-004 X1: `date`/`datetime` values and ISO `YYYY-MM-DD`
strings, the form every report payload uses for days); everything else is an inline string through `_safe_cell`, so a cell never runs
as a formula -- the CSV export's rule -- and a leading-zero phone number stays text. The header row is bold, frozen and filtered.

The reader (X2) uses openpyxl in read-only mode, after the archive itself is checked: entry count, unpacked size (a zip bomb is refused
before anything is inflated), macros and any DTD. No formula is evaluated."""

import csv
import io
import math
import re
import zipfile
from datetime import date, datetime, time
from decimal import Decimal
from xml.sax.saxutils import escape, quoteattr
from zoneinfo import ZoneInfo

import openpyxl

from app.api.school_bulk import _safe_cell

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_RELS = "http://schemas.openxmlformats.org/package/2006/relationships"
INDIA = ZoneInfo("Asia/Kolkata")  # a timestamp is shown as the India time the screens use
EPOCH = date(1899, 12, 30)  # spreadsheet day 0
ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
# XML 1.0 forbids these control characters; a pasted one would make the file unreadable.
CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
SHEET_NAME_UNSAFE = re.compile(r"[\\/:*?\[\]]")
HEADER, DAY, MINUTE = 1, 2, 3  # cellXfs indexes in STYLES

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
    "</Types>"
)
ROOT_RELS = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}"><Relationship Id="rId1" Type="{RELS}/officeDocument" Target="xl/workbook.xml"/></Relationships>'
)
WORKBOOK_RELS = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{PACKAGE_RELS}">'
    f'<Relationship Id="rId1" Type="{RELS}/worksheet" Target="worksheets/sheet1.xml"/>'
    f'<Relationship Id="rId2" Type="{RELS}/styles" Target="styles.xml"/></Relationships>'
)
# The smallest stylesheet Excel opens without a repair prompt (two fills and one border are mandatory), plus a bold font and the
# day / day-and-time number formats.
STYLES = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{MAIN}">'
    '<numFmts count="2"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/><numFmt numFmtId="165" formatCode="yyyy-mm-dd hh:mm"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="4"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
    '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
)


def _column(index: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _day(value) -> date | None:
    """A calendar day for a `date` or an exact ISO `YYYY-MM-DD` string; None for anything else."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and ISO_DAY.fullmatch(value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _typed(value) -> tuple[str, int, str] | None:
    """(cell value, style, display text) for a number or a date; None for text."""
    if isinstance(value, int | float | Decimal) and not isinstance(value, bool) and math.isfinite(value):
        return str(value), 0, str(value)
    if isinstance(value, datetime):
        local = value.astimezone(INDIA).replace(tzinfo=None) if value.tzinfo else value
        serial = (local.date() - EPOCH).days + (local - datetime.combine(local.date(), time())).total_seconds() / 86400
        return repr(serial), MINUTE, "yyyy-mm-dd hh:mm"
    day = _day(value)
    if day is not None:
        return str((day - EPOCH).days), DAY, "yyyy-mm-dd"
    return None


def _cell(ref: str, value, style: int = 0) -> tuple[str, str]:
    """The cell's XML and its display text (for the column width)."""
    typed = _typed(value)
    if typed is not None:
        number, number_style, shown = typed
        return f'<c r="{ref}"{_s(style or number_style)} t="n"><v>{number}</v></c>', shown
    text = CONTROL.sub("", _safe_cell("" if value is None else str(value)))
    return f'<c r="{ref}"{_s(style)} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>', text


def _s(style: int) -> str:
    return f' s="{style}"' if style else ""


def to_xlsx(payload: dict, sheet_name: str) -> bytes:
    """The header (the on-screen labels), the items, then a summary's Total row -- `to_csv`'s order. The auto-filter covers the header
    and the items, so sorting never moves the Total row."""
    columns = payload["columns"]
    items = payload["items"]
    lines = [[c["label"] for c in columns]]
    lines += [[item[c["key"]] for c in columns] for item in [*items, *([payload["totals"]] if payload["totals"] else [])]]
    widths = [0] * len(columns)
    rows = []
    for number, values in enumerate(lines, start=1):
        cells = []
        for index, value in enumerate(values):
            xml, shown = _cell(f"{_column(index)}{number}", value, HEADER if number == 1 else 0)
            cells.append(xml)
            widths[index] = max(widths[index], len(shown))
        rows.append(f'<row r="{number}">' + "".join(cells) + "</row>")
    last = _column(max(len(columns), 1) - 1)
    filter_ref = f"A1:{last}{len(items) + 1}"
    cols = "".join(f'<col min="{i}" max="{i}" width="{min(max(w + 2, 8), 60)}" customWidth="1"/>' for i, w in enumerate(widths, start=1))
    sheet = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="{MAIN}">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        + (f"<cols>{cols}</cols>" if cols else "")
        + "<sheetData>" + "".join(rows) + "</sheetData>"
        + (f'<autoFilter ref="{filter_ref}"/>' if columns else "")
        + "</worksheet>"
    )
    name = SHEET_NAME_UNSAFE.sub(" ", sheet_name).strip()[:31] or "Sheet1"
    # Excel keeps a filter's range in this hidden name; without it some versions drop the filter buttons.
    defined = escape("'" + name.replace("'", "''") + f"'!$A$1:${last}${len(items) + 1}")
    names = f'<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">{defined}</definedName></definedNames>' if columns else ""
    workbook = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{MAIN}" xmlns:r="{RELS}">'
        f'<sheets><sheet name={quoteattr(name)} sheetId="1" r:id="rId1"/></sheets>{names}</workbook>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", ROOT_RELS)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        archive.writestr("xl/styles.xml", STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return buffer.getvalue()


# --- reading (X2) ---------------------------------------------------------------------------------------------------------------------
MB = 1024 * 1024
MAX_BYTES = MB  # the bulk imports' limit (school_bulk.MAX_FILE_BYTES)
MAX_ROWS = 5000
MAX_ENTRIES = 200  # a one-sheet workbook has about a dozen parts
MAX_UNPACKED = 20 * MB
NOT_XLSX = "The file is not a valid Excel (.xlsx) file"
NOT_CSV = "The file is not a valid UTF-8 CSV file"


class TabularError(Exception):
    """A refused upload: the HTTP status the caller should answer with, and one message per problem."""

    def __init__(self, status_code: int, messages: list[str]):
        super().__init__("; ".join(messages))
        self.status_code = status_code
        self.messages = messages


def read_tabular(
    filename: str, raw: bytes, *, required: tuple[str, ...], known: tuple[str, ...] | None = None, max_rows: int = MAX_ROWS, max_bytes: int = MAX_BYTES
) -> list[tuple[int, dict[str, str]]]:
    """(sheet row / file line, {column: trimmed text}) for every row with a cell filled -- `school_bulk._read_csv`'s contract, for
    `.xlsx` and `.csv`. Header names are trimmed and lower-cased. Every missing required column is reported (one message each); with
    `known`, repeated and unknown columns are too."""
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension not in ("xlsx", "csv"):
        raise TabularError(415, ["Upload a .xlsx or .csv file"])
    if len(raw) > max_bytes:
        size = f"{max_bytes // MB} MB" if max_bytes >= MB else f"{max_bytes:,} bytes"
        raise TabularError(413, [f"The file is larger than {size}"])
    lines = _xlsx_lines(raw) if extension == "xlsx" else _csv_lines(raw)
    header = [name.strip().lower() for name in next(lines, [])]
    _check_header(header, required, known)
    rows = []
    for number, cells in lines:
        values = {name: cells[i].strip() if i < len(cells) else "" for i, name in enumerate(header) if name}
        if any(values.values()):
            if len(rows) == max_rows:
                raise TabularError(422, [f"The file has more than {max_rows:,} rows"])
            rows.append((number, values))
    return rows


def _check_header(header: list[str], required: tuple[str, ...], known: tuple[str, ...] | None) -> None:
    problems = []
    if known is not None:
        named = [name for name in header if name]
        problems += [f"Duplicate column: {name[:40]}" for name in dict.fromkeys(n for n in named if named.count(n) > 1)]
        problems += [f"Unknown column: {name[:40]}" for name in dict.fromkeys(n for n in named if n not in known)]
    problems += [f"Missing required column: {name}" for name in required if name not in header]
    if problems:
        raise TabularError(422, problems)


def _csv_lines(raw: bytes):
    """The header row, then (file line, cells)."""
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise TabularError(422, [NOT_CSV]) from None
    if "\x00" in content:
        raise TabularError(422, [NOT_CSV])
    try:
        rows = list(csv.reader(io.StringIO(content, newline=""), strict=True))
    except csv.Error:
        raise TabularError(422, [NOT_CSV]) from None
    yield rows[0] if rows else []
    yield from enumerate(rows[1:], start=2)


def _check_archive(raw: bytes) -> None:
    """Refuse a zip bomb, a macro workbook or a DTD before openpyxl parses anything. `zipfile` never inflates an entry past its declared
    size, so the declared total bounds the work; every part is UTF-8 XML in a real workbook, so a NUL byte (UTF-16) is refused too."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise TabularError(422, [NOT_XLSX]) from None
    with archive:
        entries = archive.infolist()
        if len(entries) > MAX_ENTRIES or sum(e.file_size for e in entries) > MAX_UNPACKED:
            raise TabularError(422, [NOT_XLSX])
        if any(e.filename.lower().endswith("vbaproject.bin") for e in entries):
            raise TabularError(415, ["Macro-enabled workbooks are not accepted"])
        try:
            for entry in entries:
                if entry.filename.endswith((".xml", ".rels")):
                    part = archive.read(entry)
                    if b"<!DOCTYPE" in part or b"<!ENTITY" in part or b"\x00" in part:
                        raise TabularError(422, [NOT_XLSX])
                    if entry.filename == "[Content_Types].xml" and b"macroEnabled" in part:
                        raise TabularError(415, ["Macro-enabled workbooks are not accepted"])
        except (zipfile.BadZipFile, OSError, EOFError, RuntimeError):  # a damaged or encrypted entry
            raise TabularError(422, [NOT_XLSX]) from None


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        if value.time() == time():
            return value.date().isoformat()
        return value.isoformat(" ", "minutes" if not value.second and not value.microsecond else "seconds")
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _xlsx_lines(raw: bytes):
    """The first sheet's header row, then (sheet row, cells). data_only: a formula cell gives Excel's saved value, never a re-run."""
    _check_archive(raw)
    try:
        book = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True, keep_links=False)
    except Exception:  # noqa: BLE001 -- any parse failure of an untrusted file is "not a valid workbook"
        raise TabularError(422, [NOT_XLSX]) from None
    try:
        rows = [[_text(v) for v in row] for row in book.worksheets[0].iter_rows(values_only=True)]
    except Exception:  # noqa: BLE001 -- as above, for a sheet that fails while it is read
        raise TabularError(422, [NOT_XLSX]) from None
    finally:
        book.close()
    yield rows[0] if rows else []
    yield from enumerate(rows[1:], start=2)
