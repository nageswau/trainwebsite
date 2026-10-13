"""dtu-001 §4.1-§4.3: turn the owner's "Direct Tie-ups.xlsx" into the load JSON + a review CSV.

Pure functions over ``{sheet name: [row tuples]}`` so the tests need no openpyxl (not a project dependency); the CLI
``python -m app.direct_tieups.parse <xlsx> <out_dir>`` imports openpyxl lazily and is run on a dev machine that has it.

Coverage check (spec §1 "Success"): every non-empty cell must land in a named destination. A cell whose column has no
destination in its layout is returned in ``unmapped`` as ``(sheet, row, column, str(value))`` and the CLI exits non-zero.
Every default or inference (spec §4.3, DT8) is recorded in the university's ``flags`` and shown in the review CSV.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from app.models import AGENT_COMMISSION_CURRENCIES, COUNSELING_CURRENCIES, COURSE_MONTHS, INSTITUTION_TYPES

MAIN_SHEET = "Direct Tie-up's"
IU_SHEET = "iu"
UC_SHEET = "uc"
HEADER_ROWS = frozenset({1, 36, 44, 50})  # main-sheet section headers (spec §4.2)

# 1-based column -> destination key, per main-sheet layout (spec §4.2).
LAYOUT_A = {  # rows 2-34: one course grid row per line
    1: "name", 2: "destination", 3: "commission",
    4: "ug.title", 5: "ug.campus", 6: "ug.intake", 7: "ug.fee", 8: "ug.scholarship",
    9: "pg.title", 10: "pg.campus", 11: "pg.fee", 12: "pg.scholarship",
    14: "pg.intake",  # "Intakes", placed after the PG columns -> PG courses (spec §4.3)
    15: "uni.tuition_fee",  # empty today; any value is flagged on the university
    16: "link",
}
LAYOUT_B = {  # rows 37-62: one row per university, bullet cells
    1: "name", 2: "destination", 3: "commission", 4: "ug.titles", 6: "pg.titles", 7: "fee_block",
    8: "scholarships", 9: "intakes", 10: "deadlines", 11: "link",
}
LAYOUT_C = {  # rows >= 63: per-row grid
    1: "name", 2: "destination", 3: "commission", 4: "ug.title", 5: "ug.fee", 6: "pg.title", 7: "pg.fee",
    8: "scholarships", 9: "intakes", 10: "deadlines", 11: "link",
}
IU_COLUMNS = {1: "name", 2: "destination", 3: "commission"}  # row 1 is a header
UC_COLUMNS = {1: "name"}  # no header row

COUNTRY_WORDS = {"uk": "GB", "usa": "US", "us": "US", "australia": "AU", "france": "FR", "germany": "DE", "malta": "MT",
                 "dubai": "AE", "uae": "AE", "paris": "FR"}
CITY_WORDS = frozenset({"dubai", "paris"})  # country words that are also a campus city
NAME_COUNTRY = (("Schiller", "US"), ("Berlin School of Business", "DE"), ("GBS Dubai", "AE"), ("GBS Malta", "MT"), ("ICN", "FR"))
CAPITALS = {"GB": "London", "US": "Washington", "AU": "Canberra", "FR": "Paris", "DE": "Berlin", "MT": "Valletta", "AE": "Dubai"}
COUNTRY_NAMES = {"GB": "United Kingdom", "US": "United States", "AU": "Australia", "FR": "France", "DE": "Germany", "MT": "Malta",
                 "AE": "United Arab Emirates"}

CATEGORY_RULES = (  # spec §4.3, first match wins
    ("Business", re.compile(r"\b(business|management|mba)\b", re.I)),
    ("Computing & IT", re.compile(r"\b(?:computing|computers?|data)\b", re.I)),
    ("Computing & IT", re.compile(r"\b(?:IT|AI)\b")),
    ("Finance", re.compile(r"\b(finance|accounting|banking)\b", re.I)),
    ("Engineering", re.compile(r"\b(engineering|maritime|marine)\b", re.I)),
    ("Health", re.compile(r"\b(health|healthcare|nursing|physio\w*|chiropractic)\b", re.I)),
    ("Creative Arts", re.compile(r"\b(design|media|film|animation|arts?)\b", re.I)),
    ("Law", re.compile(r"\blaw\b", re.I)),
    ("Hospitality", re.compile(r"\b(hospitality|tourism)\b", re.I)),
)
DEFAULT_CATEGORY = "General"
DEFAULT_DURATION = "Not specified"
INSTITUTE_WORDS = ("Institute", "Institutions", "School", "College", "Ecole", "Pathway", "BIGS", "Walbrook", "GBS")

_CURRENCY_TOKENS = (("A$", "AUD"), ("AU$", "AUD"), ("US$", "USD"), ("£", "GBP"), ("€", "EUR"), ("₹", "INR"), ("$", "USD"))
_CURRENCY_CODES = ("AED", "GBP", "USD", "EUR", "INR", "AUD", "CAD", "NZD")
_CURRENCY_RE = re.compile("|".join([re.escape(t) for t, _ in _CURRENCY_TOKENS] + [rf"\b{c}\b" for c in _CURRENCY_CODES]))
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_MONTH_RE = re.compile(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                       r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b", re.I)
_MONTH_CODES = {m.lower(): m for m in COURSE_MONTHS}
_FEE_LABEL_RE = re.compile(r"^(UG|PG)\b([^:]*):\s*(.*)$")
_DURATION_RE = re.compile(r"(\d+)\s*(?:mo|months?)\b", re.I)
_CENT = Decimal("0.01")


# ---------------------------------------------------------------- small text helpers

def is_empty(value) -> bool:
    """None, blank, or the sheet's ``"__"`` placeholder."""
    return value is None or (isinstance(value, str) and value.strip() in ("", "__"))


def clean(value) -> str:
    """Collapse whitespace (including newlines and NBSP) to single spaces."""
    return " ".join(str(value).split())


def bullets(text) -> list[str]:
    """One item per line, leading bullet marks (•, -, *) and whitespace stripped, empties dropped."""
    out = []
    for line in str(text).splitlines():
        item = clean(re.sub(r"^[\s•\-*]+", "", line))
        if item:
            out.append(item)
    return out


def _money(amount: Decimal) -> str:
    return str(amount.quantize(_CENT, rounding=ROUND_HALF_UP))


def _dedupe(items) -> list:
    out = []
    for item in items:
        if item not in out:
            out.append(item)
    return out


# ---------------------------------------------------------------- field parsers

def parse_commission(value) -> dict | None:
    """Fraction (< 1) -> percent; "N %" -> percent; "<amount> <CUR> flat" -> amount + currency. ``note`` keeps the raw text."""
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        fraction = Decimal(str(value))
        if 0 < fraction < 1:
            return {"percent": _money(fraction * 100), "note": str(value)}
        raise ValueError(f"commission: {value!r} is not a fraction between 0 and 1")
    text = str(value)
    if is_empty(text):
        return None
    if m := re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%\s*", text):
        percent = Decimal(m[1])
        if not 0 < percent <= 100:
            raise ValueError(f"commission: {text!r} is outside 0-100 %")
        return {"percent": _money(percent), "note": text}
    if m := re.fullmatch(r"\s*(\d[\d,]*(?:\.\d+)?)\s*([A-Za-z]{3})\s+flat\s*", text, re.I):
        amount, currency = Decimal(m[1].replace(",", "")), m[2].upper()
        if currency not in AGENT_COMMISSION_CURRENCIES or amount <= 0:
            raise ValueError(f"commission: {text!r} has an unsupported currency or amount")
        return {"amount": _money(amount), "currency": currency, "note": text}
    raise ValueError(f"commission: cannot read {text!r}")


def parse_fee(text) -> tuple[str | None, str | None]:
    """(low-end amount, currency) from a fee text; (None, None) when no number or the currency is not a course-master currency."""
    if is_empty(text):
        return None, None
    text = str(text)
    found = _CURRENCY_RE.search(text)
    if not found:
        return None, None
    currency = dict(_CURRENCY_TOKENS).get(found[0], found[0])
    number = _NUMBER_RE.search(text, found.end())
    if currency not in COUNSELING_CURRENCIES or not number:
        return None, None
    amount = Decimal(number[0].replace(",", ""))
    return (_money(amount), currency) if amount > 0 else (None, None)


def months(text) -> list[str]:
    """Month names / abbreviations in order of appearance, deduped, as COURSE_MONTHS codes."""
    if is_empty(text):
        return []
    return _dedupe(_MONTH_CODES[m[:3].lower()] for m in _MONTH_RE.findall(str(text)))


def category_of(title) -> str:
    for category, pattern in CATEGORY_RULES:
        if pattern.search(str(title)):
            return category
    return DEFAULT_CATEGORY


def institution_type_of(name: str) -> tuple[str, str | None]:
    """(type, flag) per spec §4.3."""
    if "university" in name.lower():
        return "university", None
    if any(word.lower() in name.lower() for word in INSTITUTE_WORDS):
        return "institute", "institution_type 'institute' inferred from the name"
    return "university", "institution_type 'university' by default (no keyword in the name)"


def scholarship_texts(value) -> list[str]:
    """A fraction (BIGS ``0.25``) reads as "25% tuition scholarship"; text is split into bullets."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        percent = (Decimal(str(value)) * 100).normalize()
        return [f"{percent:f}% tuition scholarship"]
    return bullets(value)


def parse_destination(text) -> tuple[str | None, list[str]]:
    """``"UK__ Cardiff Campus,Newport Campus"`` / ``"UK(London Campus,Birmingham)"`` / ``"Dubai"`` / ... -> (iso2, campuses)."""
    if is_empty(text):
        return None, []
    s = clean(text)
    if "__" in s:
        head, rest = s.split("__", 1)
    elif "(" in s:
        head, rest = s[: s.index("(")], s[s.index("("):]
    elif "," in s:
        head, rest = s.split(",", 1)
    else:
        head, rest = s, ""
    head = head.strip(" ,")
    if head.lower() not in COUNTRY_WORDS:
        raise ValueError(f"destination: unknown country {head!r} in {s!r}")
    rest = rest.strip(" ,")
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1]
    campuses = [head] if head.lower() in CITY_WORDS else []
    for part in _split_top_level(rest):
        part = re.sub(r"^and\s+", "", part.strip(), flags=re.I)
        if part and (part.lower() not in COUNTRY_WORDS or part.lower() in CITY_WORDS):
            campuses.append(part)
    return COUNTRY_WORDS[head.lower()], _dedupe(campuses)


def _split_top_level(text: str) -> list[str]:
    """Split on commas outside parentheses ("East London (SE10)" stays one item)."""
    parts, depth, current = [], 0, ""
    for ch in text:
        depth += (ch == "(") - (ch == ")")
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p for p in (p.strip() for p in parts) if p]


def parse_link(value) -> tuple[str | None, str | None]:
    """(website, portal label): a URL (also inside parentheses) is the website, anything else is a portal label."""
    s = clean(value)
    inner = s[1:-1].strip() if s.startswith("(") and s.endswith(")") else s
    if re.match(r"https?://", inner, re.I):
        return inner, None
    return None, s


def clean_name(raw) -> tuple[str, str | None]:
    """Strip/collapse the name; a parenthetical on its own line ("GBS Dubai\\n(UAE)") is split off."""
    text = str(raw).strip()
    if m := re.fullmatch(r"(.*?)\s*\n\s*\((.*)\)", text, re.S):
        return clean(m[1]), clean(m[2])
    return clean(text), None


# ---------------------------------------------------------------- university builder

class _Uni:
    def __init__(self, raw_name, source: str, layout: str):
        self.name, paren = clean_name(raw_name)
        self.source, self.layout = source, layout
        self.country: str | None = None
        self.campuses: list[str] = []
        self.commission: dict | None = None
        self.website: str | None = None
        self.overview_extra: list[str] = []
        self.flags: list[str] = []
        self.fee_structure: str | None = None
        self.deadlines: list[str] = []
        self.scholarships: list[str] = []
        self.intake_text: str | None = None  # layouts B/C: one intake text for every course
        self.courses: list[dict] = []
        if paren:
            if "," in paren:
                self.overview_extra.append(f"Also in: {paren}")
            else:
                self.overview_extra.append(f"Name in the sheet: {self.name} ({paren})")
            self.flags.append(f"name: '({paren})' on a second line moved to the overview")

    # single-valued university fields: first value wins, a second one is flagged (never silently dropped)
    def set_destination(self, value, where):
        iso2, campuses = parse_destination(value)
        if self.country or self.campuses:
            self.flags.append(f"{where}: second destination {clean(value)!r} ignored")
            return
        self.country, self.campuses = iso2, campuses

    def set_commission(self, value, where):
        commission = parse_commission(value)
        if self.commission is not None:
            self.flags.append(f"{where}: second commission {value!r} ignored")
            return
        self.commission = commission
        if commission and "amount" in commission and "," in commission["note"]:
            self.flags.append(f"commission {commission['note']!r} read as {commission['amount']} {commission['currency']}")

    def set_link(self, value, where):
        website, portal = parse_link(value)
        if website:
            if self.website and self.website != website:
                self.flags.append(f"{where}: second website {website!r} ignored")
            else:
                self.website = website
        else:
            self.overview_extra.append(f"Application portal: {portal}")
            self.flags.append(f"link {portal!r} is not a URL; kept in the overview as 'Application portal'")

    def add_scholarships(self, value):
        texts = scholarship_texts(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            self.flags.append(f"scholarship {value!r} read as {texts[0]!r}")
        self.scholarships = _dedupe(self.scholarships + texts)
        return texts

    def add_course(self, title, level, *, campus=None, fee=None, intake=None, scholarships=(), duration=None):
        fee_text = clean(fee) if not is_empty(fee) else None
        amount, currency = parse_fee(fee_text)
        self.courses.append({
            "title": clean(title), "level": level, "category": category_of(title), "duration": duration or DEFAULT_DURATION,
            "campus": clean(campus) if not is_empty(campus) else None, "fee_text": fee_text,
            "tuition_amount": amount, "tuition_currency": currency,
            "intakes": months(intake), "intake_text": clean(intake) if not is_empty(intake) else None,
            "scholarships": list(scholarships),
        })

    def finish(self) -> dict:
        override = next((iso for key, iso in NAME_COUNTRY if re.search(r"\b" + re.escape(key) + r"\b", self.name, re.I)), None)
        if self.country is None:
            if override is None:
                raise ValueError(f"{self.source}: no country for {self.name!r}")
            self.country = override
            self.flags.append(f"country {override} inferred from the name (destination empty)")
        elif override and override != self.country:
            self.flags.append(f"country {override} from the name overrides destination {self.country}")
            self.country = override
        if self.campuses:
            city = self.campuses[0]
        else:
            city = CAPITALS[self.country]
            self.flags.append(f"city defaulted to the capital {city} (no campus named)")
        institution_type, type_flag = institution_type_of(self.name)
        assert institution_type in INSTITUTION_TYPES
        if type_flag:
            self.flags.append(type_flag)
        if self.layout in ("B", "C") and self.intake_text is not None:
            for course in self.courses:
                course["intakes"], course["intake_text"] = months(self.intake_text), self.intake_text
        if self.layout == "B" and self.fee_structure:
            self._apply_fee_block()
        self._course_flags()
        if not self.website and not any(x.startswith("Application portal") for x in self.overview_extra):
            self.flags.append("no website in the sheet")
        overview = "\n".join([f"{self.name} — direct tie-up partner in {city}, {COUNTRY_NAMES[self.country]}.", *self.overview_extra])
        self.flags.append("overview: generated default sentence")
        return {
            "name": self.name, "country_iso2": self.country, "city": city, "campuses": self.campuses,
            "institution_type": institution_type, "website": self.website, "overview": overview,
            "fee_structure": self.fee_structure, "deadlines": self.deadlines, "scholarships": self.scholarships,
            "agent_commission": self.commission, "courses": self.courses, "flags": self.flags, "source": self.source,
            "logo_url": None,  # ruling R3: Task 6 (logos) fills it
        }

    def _apply_fee_block(self):
        lines = bullets(self.fee_structure)
        labelled = [(m[1], m[2], m[3]) for m in map(_FEE_LABEL_RE.match, lines) if m]
        if not labelled:
            fee_text = "; ".join(lines)
            amount, currency = parse_fee(fee_text)
            for course in self.courses:
                course.update(fee_text=fee_text, tuition_amount=amount, tuition_currency=currency)
            if self.courses:
                self.flags.append("fee block has no UG/PG labels; applied to every course")
            return
        for level in ("UG", "PG"):
            matches = [x for x in labelled if x[0] == level]
            courses = [c for c in self.courses if c["level"] == level]
            if not matches:
                if courses:
                    self.flags.append(f"fee block has no {level} line; {level} courses have no fee")
                continue
            _, label, fee_text = matches[0]
            if len(matches) > 1:
                self.flags.append(f"fee block has {len(matches)} {level} lines; the first ({level}{label}: …) applies to {level} courses")
            amount, currency = parse_fee(fee_text)
            found = _DURATION_RE.search(label)
            duration = f"{found[1]} months" if found else None
            for course in courses:
                course.update(fee_text=fee_text, tuition_amount=amount, tuition_currency=currency)
                if duration:
                    course["duration"] = duration
            if duration and courses:
                self.flags.append(f"duration '{duration}' for {level} courses from the fee label '{level}{label}'")

    def _course_flags(self):
        if not self.courses:
            return
        n = len(self.courses)
        self.flags.append(f"category inferred from title keywords for {n} courses")
        general = [c["title"] for c in self.courses if c["category"] == DEFAULT_CATEGORY]
        if general:
            self.flags.append(f"category '{DEFAULT_CATEGORY}' (no keyword) for: " + "; ".join(general))
        unspecified = sum(c["duration"] == DEFAULT_DURATION for c in self.courses)
        if unspecified:
            self.flags.append(f"duration '{DEFAULT_DURATION}' for {unspecified} of {n} courses")
        unparsed = _dedupe(c["fee_text"] for c in self.courses if c["fee_text"] and c["tuition_amount"] is None)
        if unparsed:
            self.flags.append("tuition amount not set (currency not in the course master list): " + "; ".join(unparsed))
        no_fee = sum(c["fee_text"] is None for c in self.courses)
        if no_fee:
            self.flags.append(f"no fee in the sheet for {no_fee} of {n} courses")
        seen, dupes = set(), []
        for c in self.courses:
            key = (c["level"], c["title"].lower())
            if key in seen:
                dupes.append(f"{c['level']} {c['title']}")
            seen.add(key)
        if dupes:
            self.flags.append("duplicate course title in the sheet: " + "; ".join(_dedupe(dupes)))


# ---------------------------------------------------------------- row handlers

def _row_a(uni: _Uni, m: dict, where: str):
    for level, key in (("UG", "ug"), ("PG", "pg")):
        scholarship = m.get(f"{key}.scholarship")
        texts = uni.add_scholarships(scholarship) if scholarship is not None else []
        if f"{key}.title" in m:
            uni.add_course(m[f"{key}.title"], level, campus=m.get(f"{key}.campus"), fee=m.get(f"{key}.fee"),
                           intake=m.get(f"{key}.intake"), scholarships=texts)
        else:
            orphans = {k: v for k, v in m.items() if k.startswith(f"{key}.") and k != f"{key}.scholarship"}
            if orphans:
                uni.flags.append(f"{where}: {level} cells without a course title: {orphans}")
    if "uni.tuition_fee" in m:
        uni.flags.append(f"column O had a value: {clean(m['uni.tuition_fee'])}")


def _row_b(uni: _Uni, m: dict, where: str):
    for level, key in (("UG", "ug.titles"), ("PG", "pg.titles")):
        for title in bullets(m.get(key, "")):
            uni.add_course(title, level)
    if "fee_block" in m:
        block = str(m["fee_block"]).strip()
        uni.fee_structure = f"{uni.fee_structure}\n{block}" if uni.fee_structure else block
    _uni_level_b_c(uni, m, where, intake_join="; ")


def _row_c(uni: _Uni, m: dict, where: str):
    for level, key in (("UG", "ug"), ("PG", "pg")):
        if f"{key}.title" in m:
            uni.add_course(m[f"{key}.title"], level, fee=m.get(f"{key}.fee"))
        elif f"{key}.fee" in m:
            uni.flags.append(f"{where}: {level} fee without a course title: {clean(m[f'{key}.fee'])}")
    _uni_level_b_c(uni, m, where, intake_join=" ")


def _uni_level_b_c(uni: _Uni, m: dict, where: str, intake_join: str):
    if "scholarships" in m:
        uni.add_scholarships(m["scholarships"])
    if "deadlines" in m:
        uni.deadlines = _dedupe(uni.deadlines + bullets(m["deadlines"]))
    if "intakes" in m:
        text = intake_join.join(bullets(m["intakes"]))
        if uni.intake_text and uni.intake_text != text:
            uni.flags.append(f"{where}: second intake text {text!r} ignored")
        else:
            uni.intake_text = text


_LAYOUTS = {"A": (LAYOUT_A, _row_a), "B": (LAYOUT_B, _row_b), "C": (LAYOUT_C, _row_c)}


def layout_of(row: int) -> str | None:
    if 2 <= row <= 34:
        return "A"
    if 37 <= row <= 62:
        return "B"
    if row >= 63:
        return "C"
    return None


def _col_letter(col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _cells(row) -> dict[int, object]:
    return {c: v for c, v in enumerate(row, 1) if not is_empty(v)}


def _uni_fields(uni: _Uni, m: dict, where: str):
    if "destination" in m:
        uni.set_destination(m["destination"], where)
    if "commission" in m:
        uni.set_commission(m["commission"], where)
    if "link" in m:
        uni.set_link(m["link"], where)


def _with_context(sheet, row, fn, *args):
    try:
        fn(*args)
    except ValueError as exc:
        raise ValueError(f"{sheet} row {row}: {exc}") from exc


def parse_workbook(sheets: dict[str, list[tuple]]) -> tuple[list[dict], list[tuple]]:
    """(universities in sheet order, unmapped cells). Raises ValueError on an unreadable commission / destination."""
    unis: list[_Uni] = []
    unmapped: list[tuple] = []

    current: _Uni | None = None
    for r, row in enumerate(sheets.get(MAIN_SHEET, []), 1):
        cells = _cells(row)
        if r in HEADER_ROWS:
            current = None
            continue
        if not cells:
            continue
        layout = layout_of(r)
        if layout is None:
            unmapped += [(MAIN_SHEET, r, c, str(v)) for c, v in cells.items()]
            continue
        column_map, handler = _LAYOUTS[layout]
        unmapped += [(MAIN_SHEET, r, c, str(v)) for c, v in cells.items() if c not in column_map]
        m = {column_map[c]: v for c, v in cells.items() if c in column_map}
        if "name" in m:
            current = _Uni(m["name"], f"{MAIN_SHEET}!A{r}", layout)
            unis.append(current)
        elif current is None or current.layout != layout:
            unmapped += [(MAIN_SHEET, r, c, str(v)) for c, v in cells.items() if c in column_map]
            continue
        where = f"{MAIN_SHEET}!{r}"
        _with_context(MAIN_SHEET, r, _uni_fields, current, m, where)
        _with_context(MAIN_SHEET, r, handler, current, m, where)

    for sheet, columns, first_row in ((IU_SHEET, IU_COLUMNS, 2), (UC_SHEET, UC_COLUMNS, 1)):
        for r, row in enumerate(sheets.get(sheet, []), 1):
            cells = _cells(row)
            if r < first_row or not cells:
                continue  # iu row 1 is its header
            unmapped += [(sheet, r, c, str(v)) for c, v in cells.items() if c not in columns]
            m = {columns[c]: v for c, v in cells.items() if c in columns}
            if "name" not in m:
                unmapped += [(sheet, r, c, str(v)) for c, v in cells.items() if c in columns]
                continue
            uni = _Uni(m["name"], f"{sheet}!A{r}", sheet)
            unis.append(uni)
            _with_context(sheet, r, _uni_fields, uni, m, f"{sheet}!{r}")
            if sheet == UC_SHEET:
                uni.country = "GB"
                uni.flags.append("country GB from the uc sheet (it has no destination column)")

    for sheet, rows in sheets.items():
        if sheet not in (MAIN_SHEET, IU_SHEET, UC_SHEET):
            unmapped += [(sheet, r, c, str(v)) for r, row in enumerate(rows, 1) for c, v in _cells(row).items()]

    result = [u.finish() for u in unis]
    names = [u["name"].lower() for u in result]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise ValueError(f"duplicate university names: {duplicates}")
    return result, unmapped


# ---------------------------------------------------------------- CLI

REVIEW_COLUMNS = ("university", "country", "city", "campuses", "agent commission", "course", "level", "category", "duration", "campus",
                  "fee_text", "tuition", "intakes", "intake_text", "flags")


def _commission_text(commission: dict | None) -> str:
    if not commission:
        return ""
    if "percent" in commission:
        return f"{commission['percent']}% ({commission['note']})"
    return f"{commission['amount']} {commission['currency']} ({commission['note']})"


def review_rows(unis: list[dict]) -> list[dict]:
    rows = []
    for u in unis:
        base = {"university": u["name"], "country": u["country_iso2"], "city": u["city"], "campuses": "; ".join(u["campuses"]),
                "agent commission": _commission_text(u["agent_commission"]), "flags": " | ".join(u["flags"])}
        for c in u["courses"] or [None]:
            row = dict.fromkeys(REVIEW_COLUMNS, "") | base
            if c:
                row |= {"course": c["title"], "level": c["level"], "category": c["category"], "duration": c["duration"],
                        "campus": c["campus"] or "", "fee_text": c["fee_text"] or "",
                        "tuition": f"{c['tuition_amount']} {c['tuition_currency']}" if c["tuition_amount"] else "",
                        "intakes": ", ".join(c["intakes"]), "intake_text": c["intake_text"] or ""}
            rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        print("usage: python -m app.direct_tieups.parse <xlsx> <out_dir>", file=sys.stderr)
        return 2
    import openpyxl  # dev-machine only; not a project dependency (spec §4.1)

    workbook = openpyxl.load_workbook(argv[0], read_only=True, data_only=True)
    try:
        sheets = {ws.title: [tuple(r) for r in ws.iter_rows(values_only=True)] for ws in workbook.worksheets}
    finally:
        workbook.close()
    unis, unmapped = parse_workbook(sheets)
    if unmapped:
        print(f"{len(unmapped)} unmapped non-empty cell(s):", file=sys.stderr)
        for sheet, row, col, value in unmapped:
            print(f"  {sheet}!{_col_letter(col)}{row}: {value!r}", file=sys.stderr)
        return 1
    unis.sort(key=lambda u: u["name"].lower())
    out_dir = Path(argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path, csv_path = out_dir / "direct_tieups.json", out_dir / "direct_tieups_review.csv"
    json_path.write_text(json.dumps(unis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:  # BOM so Excel shows £ / € / ₹
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(review_rows(unis))
    courses = sum(len(u["courses"]) for u in unis)
    print(f"0 unmapped cells; {len(unis)} universities, {courses} courses -> {json_path}, {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
