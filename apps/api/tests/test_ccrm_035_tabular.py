"""ccrm-035 (DEC-SCOPE-268 E1, E8): the standard-library xlsx writer -- one sheet, the same `{columns, items, totals}` payload as
`agent_reports.to_csv`, numbers typed as numbers, text escaped for XML and for formula injection."""

import io
import zipfile
from xml.etree import ElementTree

from app.services.tabular import XLSX_TYPE, to_xlsx

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
PAYLOAD = {
    "columns": [{"key": "name", "label": "Name"}, {"key": "count", "label": "Count"}, {"key": "rate", "label": "Rate"}],
    "items": [{"name": "A & <B>", "count": 3, "rate": 12.5}, {"name": '=HYPERLINK("x")', "count": 0, "rate": None}, {"name": "bell\x07", "count": 1, "rate": 1}],
    "totals": {"name": "Total", "count": 4, "rate": 10.0},
}


def _sheet(body: bytes) -> list[list[tuple[str | None, str]]]:
    """Each row as [(cell type, text)] in column order."""
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        assert {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet1.xml"} <= set(archive.namelist())
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows = []
    for row in root.iterfind(".//m:sheetData/m:row", NS):
        cells = []
        for cell in row.iterfind("m:c", NS):
            text = cell.find("m:is/m:t", NS) if cell.get("t") == "inlineStr" else cell.find("m:v", NS)
            cells.append((cell.get("t"), "" if text is None or text.text is None else text.text))
        rows.append(cells)
    return rows


def test_header_rows_and_total_in_order_with_typed_numbers():
    rows = _sheet(to_xlsx(PAYLOAD, "Report"))
    assert [text for _, text in rows[0]] == ["Name", "Count", "Rate"]
    assert rows[1] == [("inlineStr", "A & <B>"), ("n", "3"), ("n", "12.5")]
    assert rows[-1] == [("inlineStr", "Total"), ("n", "4"), ("n", "10.0")]
    assert len(rows) == 5


def test_text_is_neutralised_and_control_characters_dropped():
    rows = _sheet(to_xlsx(PAYLOAD, "Report"))
    assert rows[2][0] == ("inlineStr", '\'=HYPERLINK("x")')  # E8: the same escape as the CSV
    assert rows[2][2] == ("inlineStr", "")  # None is an empty cell, never "None"
    assert rows[3][0] == ("inlineStr", "bell")  # a control character would make the XML invalid


def test_cells_carry_references_and_the_header_is_frozen():
    body = to_xlsx(PAYLOAD, "Report")
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    assert [c.get("r") for c in sheet.find(".//m:sheetData/m:row", NS)] == ["A1", "B1", "C1"]
    assert sheet.find(".//m:pane", NS).get("topLeftCell") == "A2"
    assert workbook.find(".//m:sheet", NS).get("name") == "Report"


def test_a_long_or_unsafe_sheet_name_is_made_valid():
    with zipfile.ZipFile(io.BytesIO(to_xlsx(PAYLOAD, "a/b:c*d?[e] " + "x" * 40))) as archive:
        name = ElementTree.fromstring(archive.read("xl/workbook.xml")).find(".//m:sheet", NS).get("name")
    assert len(name) <= 31 and not set(name) & set("/\\:*?[]")


def test_an_empty_report_is_a_header_only_sheet():
    rows = _sheet(to_xlsx({"columns": PAYLOAD["columns"], "items": [], "totals": None}, "Empty"))
    assert len(rows) == 1


def test_content_type():
    assert XLSX_TYPE == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
