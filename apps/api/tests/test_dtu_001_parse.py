"""dtu-001 §4: the parser maps every non-empty cell (0 unmapped) and parses commission / fee / intake texts."""

import pytest

from app.direct_tieups.parse import category_of, months, parse_commission, parse_fee, parse_workbook
from app.models import INSTITUTION_TYPES

HEAD_A = ("Name of the university", "Destination and campus", "Commission", "Ug Courses", "Campus", "Available Intake", "Tution fee", "Scholarship",
          "Pg courses with campus", "Campus", "Tution fee", "Scholarship", None, "Intakes", "Tution Fee", "University Link")


def _sheets(main_rows):
    return {
        "Direct Tie-up's": main_rows,
        "iu": [("Name of the University", "Destination", "Commission"), ("University of East Anglia", "UK", "4000GBP flat"), ("University of Hull", "UK", 0.18)],
        "uc": [("Coventry University",), ("University of Greenwich",)],
    }


def _main():
    rows = [HEAD_A]
    rows.append(("University of Southwales", "UK__ Cardiff Campus,Newport Campus", 0.13, "BA (Hons) Business and Management", "Cardiff Campus", " January 2027",
                 "£15,800 – £16,200 per year", "£1,500-£2,500", "MBA Global", "Newport Campus", "£18,970", "£1,500-£2,500", None, "January / September", None,
                 "https://www.southwales.ac.uk/"))
    rows.append((None, None, None, "BSc (Hons) Computing", "Cardiff Campus", " January 2027", "£15,800 – £16,200 per year", None, None, None, None, None, None,
                 "January / September", None, None))
    rows += [(None,) * 16] * (35 - len(rows))  # pad to the layout-B header row 36
    rows.append(("University Name", "Destination and campus", None, "UG Courses Offered", None, "PG Courses Offered", "Tuition Fee Structure",
                 "Scholarships & Financial Aid", "Available Intakes", "Application Deadlines", "Application Link", None, None, None, None, None))
    rows.append(("BPP University", "UK(London Campus,Birmingham)", None, "• BSc (Hons) Accounting and Finance\n• BSc (Hons) Law", None,
                 "• Master's in Business Administration (MBA)", "• UG: £11,000 – £13,366 / year\n• PG (12 Mo): £14,000 – £16,000",
                 "• International PG Bursary: £1,000 – £1,500", "• January / February\n• September", "• Jan Intake: Mid-November", "https://www.bpp.com/",
                 None, None, None, None, None))
    rows += [(None,) * 16] * (63 - len(rows))
    rows.append(("Walbrook", "UK,London campus", None, "BSc (Hons) Banking and Digital Finance", "£14,500 – £16,500 per year", "MSc Business and Management",
                 "£16,000 – £18,500 per year", "Early Enrolment Discounts:2000,4000 pounds", "Jan,Sep,OCT,NOV", "Mid-November 2026 for Jan",
                 "https://www.walbrook.ac.uk/", None, None, None, None, None))
    return rows


def test_every_cell_is_mapped_and_universities_are_built():
    unis, unmapped = parse_workbook(_sheets(_main()))
    assert unmapped == []
    names = {u["name"] for u in unis}
    assert {"University of Southwales", "BPP University", "Walbrook", "University of East Anglia", "University of Hull", "Coventry University", "University of Greenwich"} <= names
    sw = next(u for u in unis if u["name"] == "University of Southwales")
    assert sw["country_iso2"] == "GB" and sw["campuses"] == ["Cardiff Campus", "Newport Campus"] and sw["city"] == "Cardiff"  # R8: trailing "campus" stripped
    assert sw["agent_commission"] == {"percent": "13.00", "note": "0.13"}
    ug = next(c for c in sw["courses"] if c["title"] == "BA (Hons) Business and Management")
    assert (ug["level"], ug["campus"], ug["tuition_amount"], ug["tuition_currency"], ug["intakes"], ug["intake_text"]) == ("UG", "Cardiff Campus", "15800.00", "GBP", ["Jan"], "January 2027")
    pg = next(c for c in sw["courses"] if c["title"] == "MBA Global")
    assert pg["intakes"] == ["Jan", "Sep"] and pg["fee_text"] == "£18,970"  # column N applies to PG (spec §4.3)
    bpp = next(u for u in unis if u["name"] == "BPP University")
    assert [c["title"] for c in bpp["courses"]] == ["BSc (Hons) Accounting and Finance", "BSc (Hons) Law", "Master's in Business Administration (MBA)"]
    assert bpp["courses"][2]["duration"] == "12 months" and bpp["courses"][0]["tuition_amount"] == "11000.00"
    assert bpp["deadlines"] == ["Jan Intake: Mid-November"] and bpp["scholarships"] == ["International PG Bursary: £1,000 – £1,500"]
    assert next(u for u in unis if u["name"] == "Coventry University")["country_iso2"] == "GB"


def test_contract_keys_logo_placeholder_and_institution_type():
    unis, _ = parse_workbook(_sheets(_main()))
    keys = {"name", "country_iso2", "city", "campuses", "institution_type", "website", "overview", "fee_structure", "deadlines", "scholarships",
            "agent_commission", "courses", "flags", "source", "logo_url"}
    course_keys = {"title", "level", "category", "duration", "campus", "fee_text", "tuition_amount", "tuition_currency", "intakes", "intake_text", "scholarships"}
    for u in unis:
        assert set(u) == keys
        assert u["logo_url"] is None  # ruling R3: Task 6 fills it
        assert u["institution_type"] in INSTITUTION_TYPES and u["overview"]
        assert all(set(c) == course_keys for c in u["courses"])
    walbrook = next(u for u in unis if u["name"] == "Walbrook")
    assert walbrook["institution_type"] == "institute" and walbrook["website"] == "https://www.walbrook.ac.uk/"
    assert [c["intakes"] for c in walbrook["courses"]] == [["Jan", "Sep", "Oct", "Nov"]] * 2  # layout C row intakes apply to every course
    hull = next(u for u in unis if u["name"] == "University of Hull")
    assert hull["courses"] == [] and hull["city"] == "Hull" and "city from owner-approved main-city table (DT15)" in hull["flags"]


def test_an_unknown_cell_is_reported():
    rows = _main()
    rows[1] = rows[1][:12] + ("stray",) + rows[1][13:]  # column M is unmapped
    _, unmapped = parse_workbook(_sheets(rows))
    assert unmapped == [("Direct Tie-up's", 2, 13, "stray")]


def test_double_underscore_is_empty_and_non_url_link_goes_to_overview():
    rows = _main()
    rows.append(("BIGS", "Dubai", "1,50,000 INR flat", "__", None, "Global Management", "AED 85,200", 0.25, "Jan 2027,March 2027,May 2027",
                 "for Jan 2027 , deadline is till dec 3rd week", "Candidats - ICN", None, None, None, None, None))
    unis, unmapped = parse_workbook(_sheets(rows))
    assert unmapped == []
    bigs = next(u for u in unis if u["name"] == "BIGS")
    assert bigs["country_iso2"] == "AE" and bigs["city"] == "Dubai" and bigs["website"] is None
    assert "Application portal: Candidats - ICN" in bigs["overview"]
    assert bigs["agent_commission"] == {"amount": "150000.00", "currency": "INR", "note": "1,50,000 INR flat"}
    assert bigs["scholarships"] == ["25% tuition scholarship"]
    assert [(c["title"], c["fee_text"], c["tuition_amount"]) for c in bigs["courses"]] == [("Global Management", "AED 85,200", None)]


@pytest.mark.parametrize(("value", "expected"), [
    (0.13, {"percent": "13.00", "note": "0.13"}),
    (0.175, {"percent": "17.50", "note": "0.175"}),
    ("4000GBP flat", {"amount": "4000.00", "currency": "GBP", "note": "4000GBP flat"}),
    ("2500GBP flat", {"amount": "2500.00", "currency": "GBP", "note": "2500GBP flat"}),
    ("1,50,000 INR flat", {"amount": "150000.00", "currency": "INR", "note": "1,50,000 INR flat"}),
    ("16 %", {"percent": "16.00", "note": "16 %"}),
    (None, None),
    ("", None),
])
def test_parse_commission(value, expected):
    assert parse_commission(value) == expected


def test_parse_commission_rejects_garbage():
    with pytest.raises(ValueError, match="commission"):
        parse_commission("ask partner")


@pytest.mark.parametrize(("text", "expected"), [
    ("£15,800 – £16,200 per year", ("15800.00", "GBP")), ("A$60,000 total", ("60000.00", "AUD")), ("€6,000 – €7,500 / year", ("6000.00", "EUR")),
    ("~$21,000 – $24,000 / year", ("21000.00", "USD")), ("AED 85,200", (None, None)), ("₹3,500,000 – ₹6,000,000 total", ("3500000.00", "INR")), ("", (None, None)),
])
def test_parse_fee(text, expected):
    assert parse_fee(text) == expected


def test_months_and_category():
    assert months("January / February\nMay / June\nSeptember / October") == ["Jan", "Feb", "May", "Jun", "Sep", "Oct"]
    assert months("Jan,Sep,OCT,NOV") == ["Jan", "Sep", "Oct", "Nov"]
    assert months("Monthly modular entry") == []
    assert category_of("MBA Global (Finance / Financial Services)") == "Business"
    assert category_of("BSc (Hons) Computer Science & AI") == "Computing & IT"
    assert category_of("BSc (Hons) Chiropractic") == "Health"
    assert category_of("International Foundation Year") == "General"


# ---- fix round 1 (owner DT15-DT17, rulings R8-R10)

def _row_b(name, destination, ug, pg, fees):
    return (name, destination, None, ug, None, pg, fees, None, "• January", None, "https://example.org/", None, None, None, None, None)


def _parse_with(row38):
    rows = _main()
    rows[37] = row38  # row 38 is inside layout B (rows 37-62)
    unis, unmapped = parse_workbook(_sheets(rows))
    assert unmapped == []
    return unis


def test_unlabelled_fee_block_with_several_currencies_is_text_only():  # DT16
    fees = "• India/Asia Campuses: ₹3,500,000 – ₹6,000,000 total\n• APAC Regional Programs: $8,000 – $12,000 / year"
    unis = _parse_with(_row_b("APAC Institutions\n", "Australia,Sydney Campus ", "• BSc (Hons) Computer Science & AI", None, fees))
    apac = next(u for u in unis if u["name"] == "APAC Institutions")
    course = apac["courses"][0]
    assert (course["tuition_amount"], course["tuition_currency"]) == (None, None)
    assert "₹3,500,000" in course["fee_text"] and "$8,000" in course["fee_text"]
    assert any("several currencies" in f and "DT16" in f for f in apac["flags"])
    assert apac["city"] == "Sydney"


def test_unlabelled_single_currency_fee_block_still_sets_tuition():
    unis = _parse_with(_row_b("OIEG Pathway Programs (Oxford International)", "UK", "• International Foundation Year", None,
                              "• Pathway Programs: £12,500 – £15,000 total depending on stream and location"))
    oieg = next(u for u in unis if u["name"] == "OIEG Pathway Programs (Oxford International)")
    assert oieg["courses"][0]["tuition_amount"] == "12500.00" and oieg["city"] == "London"
    assert "city from owner-approved main-city table (DT15)" in oieg["flags"]


def test_city_strips_campus_word_and_institution_acronym():  # R8
    unis = _parse_with(_row_b("Ecole de Management Appliqué \n(France)", "France__(EMA Paris campus)", "• Bachelor in Business", None, "• UG: €7,500"))
    ema = next(u for u in unis if u["name"] == "Ecole de Management Appliqué")
    assert ema["city"] == "Paris" and ema["campuses"] == ["EMA Paris campus"] and "partner in Paris, France" in ema["overview"]
    walbrook = next(u for u in unis if u["name"] == "Walbrook")
    assert walbrook["city"] == "London" and walbrook["campuses"] == ["London campus"]


def test_main_city_table_for_universities_without_a_campus():  # DT15
    unis, _ = parse_workbook(_sheets(_main()))
    coventry = next(u for u in unis if u["name"] == "Coventry University")
    assert coventry["city"] == "Coventry" and "city from owner-approved main-city table (DT15)" in coventry["flags"]
    assert not any("capital" in f for f in coventry["flags"])


def test_bpp_pdp_line_goes_to_pdp_titles():  # DT17
    fees = "• UG: £11,000 – £13,366 / year\n• PG (12 Mo): £18,600 – £19,000 total\n• PG (18 Mo PDP): £22,000 – £23,000 total\n• Deposit: 60%"
    pg = "• MSc Management with AI\n• MBA with Professional Development\n• MSc Finance (PDP)"
    unis = _parse_with(_row_b("BPP Test University", "UK(London Campus)", None, pg, fees))
    courses = {c["title"]: c for c in next(u for u in unis if u["name"] == "BPP Test University")["courses"]}
    assert (courses["MSc Management with AI"]["duration"], courses["MSc Management with AI"]["tuition_amount"]) == ("12 months", "18600.00")
    for title in ("MBA with Professional Development", "MSc Finance (PDP)"):
        assert (courses[title]["duration"], courses[title]["tuition_amount"], courses[title]["fee_text"]) == ("18 months", "22000.00", "£22,000 – £23,000 total")


def test_unmatched_pdp_line_is_flagged():
    fees = "• PG (12 Mo): £18,600 – £19,000 total\n• PG (18 Mo PDP): £22,000 – £23,000 total"
    unis = _parse_with(_row_b("BPP Test University", "UK(London Campus)", None, "• MSc Management with AI", fees))
    bpp = next(u for u in unis if u["name"] == "BPP Test University")
    assert bpp["courses"][0]["duration"] == "12 months"
    assert any("PG (18 Mo PDP)" in f and "applies to no course" in f for f in bpp["flags"])


def test_information_technology_category():  # R9
    assert category_of("BSc (Hons) Information Technology") == "Computing & IT"
    assert category_of("MSc Information Technology Management") == "Computing & IT"


def test_duplicate_course_is_emitted_once():  # R10
    rows = _main()
    rows[2] = rows[2][:8] + ("MBA Global", "Cardiff Campus", "£18,970", None, None, "September", None, None)
    unis, unmapped = parse_workbook(_sheets(rows))
    assert unmapped == []
    sw = next(u for u in unis if u["name"] == "University of Southwales")
    assert [c["title"] for c in sw["courses"] if c["level"] == "PG"] == ["MBA Global"]
    assert next(c for c in sw["courses"] if c["title"] == "MBA Global")["intakes"] == ["Jan", "Sep"]  # first row kept
    assert any("duplicate course title" in f and "MBA Global" in f for f in sw["flags"])
