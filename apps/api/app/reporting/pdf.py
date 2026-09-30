"""ENH-015 -- PDF rendering for the School Summary and the Student Progress Report
(docs/superpowers/specs/2026-09-29-enh-015-reports-downloads-design.md §5). Pure: a dict in, PDF bytes out -- no database,
no I/O, so the caller decides scope and this module only lays out what it is given.

Every piece of text reaches the page through `_p`, the single escape point: Platypus parses `<`, `>` and `&` in a
Paragraph as markup, so unescaped stored text (a counsellor's note) could restyle or break the document (AC08).
Latin text is set in the built-in Helvetica; Devanagari runs in the bundled Noto Sans Devanagari (SIL OFL, `fonts/`), shaped
by `uharfbuzz` so vowel signs and conjuncts are correct (QA15-02). Other non-Latin scripts are not covered yet."""

import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas import CAREER_LIST_KEYS, PSYCHOMETRIC_RESULT_KEYS

INDIA = ZoneInfo("Asia/Kolkata")
DEVANAGARI_FONT = "NotoSansDevanagari"
pdfmetrics.registerFont(TTFont(DEVANAGARI_FONT, str(Path(__file__).parent / "fonts" / "NotoSansDevanagari-Regular.ttf")))
# Devanagari (+ Extended, Vedic Extensions, ZWNJ/ZWJ); spaces between words stay inside a run, so a name is shaped as one.
_DEVANAGARI = "ऀ-ॿ꣠-ꣿ᳐-᳿‌‍"
_DEVANAGARI_RUN = re.compile(rf"[{_DEVANAGARI}]+(?: +[{_DEVANAGARI}]+)*")
_STYLES = getSampleStyleSheet()
# shaping=1 on every style: it only acts on shapable (TrueType) runs, so Helvetica text is unaffected.
TITLE = ParagraphStyle("ReportTitle", parent=_STYLES["Title"], shaping=1)
HEADING = ParagraphStyle("ReportHeading", parent=_STYLES["Heading2"], shaping=1)
BODY = ParagraphStyle("ReportBody", parent=_STYLES["BodyText"], shaping=1)
SMALL = ParagraphStyle("Small", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor("#4B5563"))
CELL = ParagraphStyle("Cell", parent=BODY, fontSize=8.5, leading=10.5)
STATUS = ParagraphStyle("Status", parent=BODY, spaceAfter=4)  # QA15-06: a gap between the status line and the table
GRID = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEF2F7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
)
FIELDS = TableStyle(
    [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F5F7FA")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
NONE = "—"  # em dash, in the built-in fonts' encoding

LABELS = {
    "completed_on": "Completed on",
    "scheduled_for": "Scheduled for",
    "next_follow_up_date": "Next follow-up",
    "counselor_name": "Counsellor",
    "created_at": "Recorded on",
    "scheduled_at": "Date",
    "present": "Attended",
    "university_name": "University",
    "visa_status": "Visa",
    "batch_title": "Programme",
    "test_type": "Test",
    "assessment_type": "Assessment",
    "academic_year": "Academic year",
    "teacher_remarks": "Teacher remarks",
}
CAREER_FIELDS = ("status", "scheduled_for", "completed_on", "next_follow_up_date", "counselor_name", "notes", *CAREER_LIST_KEYS)


def _humanize(key: str) -> str:
    return LABELS.get(key) or key.replace("_", " ").capitalize()


def _text(value) -> str:
    if value is None:
        return NONE
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, datetime):
        return (value.astimezone(INDIA) if value.tzinfo else value).strftime("%d %b %Y")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, dict):
        return ", ".join(f"{_humanize(str(k))}: {_text(v)}" for k, v in value.items()) or NONE
    if isinstance(value, list | tuple):
        return ", ".join(_text(v) for v in value) or NONE
    return str(value)


_DEVANAGARI_STYLES: dict[str, ParagraphStyle] = {}


def _devanagari_style(style: ParagraphStyle) -> ParagraphStyle:
    if style.name not in _DEVANAGARI_STYLES:
        _DEVANAGARI_STYLES[style.name] = ParagraphStyle(f"{style.name}Devanagari", parent=style, fontName=DEVANAGARI_FONT)
    return _DEVANAGARI_STYLES[style.name]


def _p(value, style: ParagraphStyle = BODY) -> Paragraph:
    """The only way text reaches the page: control characters dropped, markup escaped, line breaks kept.

    Text with Devanagari (QA15-02) is based on the Devanagari font, because reportlab shapes a paragraph only when its own
    font is the shapable one; the Latin runs in between go back to the style's font, since the Devanagari font has no Latin
    letters. The split only ever cuts between characters, never inside escaped markup."""
    markup = escape(_CONTROL.sub("", _text(value))).replace("\n", "<br/>")
    if not _DEVANAGARI_RUN.search(markup):
        return Paragraph(markup, style)
    pieces = re.split(f"({_DEVANAGARI_RUN.pattern})", markup)  # even indexes: other text; odd: Devanagari runs
    latin = f'<font name="{style.fontName}">{{}}</font>'
    return Paragraph("".join(latin.format(piece) if i % 2 == 0 and piece else piece for i, piece in enumerate(pieces)), _devanagari_style(style))


def _status(value: str | None) -> str:
    return _humanize(value) if value else NONE


def _empty(value) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _value(key: str, value):
    """A stored value as the screens show it (QA15-06): statuses in words, test types in capitals (Student360Panels)."""
    if key.endswith("status"):
        return _status(value)
    return str(value).upper() if key == "test_type" else value


def _record_table(record: dict, keys: Iterable[str]) -> Table:
    rows = [[_p(_humanize(key), CELL), _p(_value(key, record[key]), CELL)] for key in keys if not _empty(record.get(key))]
    table = Table(rows or [[_p("Details", CELL), _p(NONE, CELL)]], colWidths=[45 * mm, 125 * mm])
    table.setStyle(FIELDS)
    return table


def _section(title: str, status: str | None, records: Sequence[dict], keys: Sequence[str]) -> list[Flowable]:
    """QA15-05: each record is kept on one page, and the heading (with its overall status) stays with what follows it.
    QA15-06: "Overall status", so it is not read as the Status row of the record printed right under it."""
    head: list[Flowable] = [_p(title, HEADING)]
    if status is not None:
        head.append(_p(f"Overall status: {_status(status)}", STATUS))
    if not records:
        return [KeepTogether([*head, _p("No records yet.")])]
    blocks: list[list[Flowable]] = [[_record_table(record, keys), Spacer(1, 3 * mm)] for record in records]
    blocks[0] = head + blocks[0]
    return [KeepTogether(block) for block in blocks]


def _build(story: list[Flowable], title: str, footer: str) -> bytes:
    buffer = BytesIO()

    def _page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#6B7280"))
        canvas.drawString(15 * mm, 10 * mm, footer)
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm, title=title, author="EduSphere")
    doc.build(story, onFirstPage=_page, onLaterPages=_page)
    return buffer.getvalue()


def _cell(cell: dict) -> str:
    pct = cell.get("pct")
    return f"{cell['count']} ({NONE if pct is None else f'{pct:g}%'})"


def render_school_summary(data: dict) -> bytes:
    """Spec §5.1: title block, the §30 management figures, the §29 grade-wise table."""
    story: list[Flowable] = [
        _p("School Summary Report", TITLE),
        _p(data["school_name"], HEADING),
        _p(f"As of {_text(data['as_of'])} (India time)"),
        _p(f"Academic year: {data['academic_year']}" if data.get("academic_year") else "No active academic year"),
    ]
    if not data["total_students"]:
        story.append(_p("No students on the roster yet."))
    story.append(_p("Management summary", HEADING))
    if data["kpis"]:  # reportlab rejects a Table with no rows
        kpis = Table([[_p(label, CELL), _p(value, CELL)] for label, value in data["kpis"]], colWidths=[110 * mm, 30 * mm])
        kpis.setStyle(FIELDS)
        story.append(kpis)
    grades = data["grades"]
    if grades:
        width = (180 - 50) / len(grades) * mm
        rows = [[_p("Metric", CELL), *[_p(g, CELL) for g in grades]], [_p("Students", CELL), *[_p(data["students"].get(g, 0), CELL) for g in grades]]]
        rows += [[_p(m["label"] + (" *" if m["is_proxy"] else ""), CELL), *[_p(_cell(m["cells"][g]), CELL) for g in grades]] for m in data["metrics"]]
        table = Table(rows, colWidths=[50 * mm, *[width] * len(grades)], repeatRows=1)
        table.setStyle(GRID)
        story += [_p("Grade-wise comparison", HEADING), table]
        story += [_p(f"* {m['label']}: {m['definition']}", SMALL) for m in data["metrics"] if m["is_proxy"] and m["definition"]]
    story += [Spacer(1, 4 * mm), _p("Counts are distinct students. Academic results count only when published.", SMALL)]
    return _build(story, "School Summary Report", "EduSphere · School Summary Report")


def render_progress_report(overview: dict, as_of: date) -> bytes:
    """Spec §5.2: the SCH-007 overview the reader already sees, section by section. Reads nothing outside `overview`."""
    student = overview["student"]
    details = {
        "Name": student.get("full_name"),
        "Student code": student.get("student_code"),
        # QA15-09: the free-text class if there is one, else the structured grade (a student may have only `grade_level`).
        "Grade / class": student.get("grade_or_class") or (f"Grade {student['grade_level']}" if student.get("grade_level") else None),
        "Section": student.get("section"),
        "School": student.get("school_name"),
        "Assigned teacher": student.get("assigned_teacher_name"),
    }
    results = [{**r, "marks": f"{_text(r['marks_obtained'])} / {_text(r['max_marks'])}"} for r in overview["results"]]
    skills = overview.get("skills") or {}
    story: list[Flowable] = [_p("Student Progress Report", TITLE), _p(f"As of {_text(as_of)} (India time)"), _record_table(details, details.keys())]
    story += _section("Career guidance", overview["career_guidance"]["status"], overview["career_guidance"]["sessions"], CAREER_FIELDS)
    story += _section("Counselling", overview["counselling"]["status"], overview["counselling"]["notes"], CAREER_FIELDS)
    story += _section("Career recommendations", None, overview["recommended_careers"], CAREER_FIELDS)
    story += _section("Psychometric assessment", overview["psychometric"]["status"], overview["psychometric"]["assessments"], ("assessment_type", "status", "created_at", *PSYCHOMETRIC_RESULT_KEYS))
    story += _section("Academic results (published)", None, results, ("subject", "term", "academic_year", "marks", "percentage", "grade", "teacher_remarks"))
    story += _section("Activities attended", None, overview["activities"]["attended"], ("title", "scheduled_at", "present"))
    story += _section("Test preparation (IELTS/SAT)", overview["test_prep"]["status"], overview["test_prep"]["records"], ("test_type", "status", "target_score", "actual_score", "mock_scores"))
    story += _section(
        "Foreign language", overview["foreign_language"]["status"], overview["foreign_language"]["records"], ("language", "level", "classes_attended", "assessment_score", "certification_status")
    )
    story += _section("Global education", overview["global_education"]["status"], overview["global_education"]["applications"], ("university_name", "status", "visa_status"))
    for key, title in (("soft_skills", "Soft skills"), ("digital_skills", "Digital skills")):
        block = skills.get(key) or {}
        story += _section(title, block.get("status"), block.get("enrollments") or [], ("batch_title", "topic", "status", "start_date", "end_date", "completed_at", "certified_at"))
    return _build(story, "Student Progress Report", "EduSphere · Student Progress Report · Confidential: contains student information")
