"""bdm-017 -- lead and conversion bodies (spec §4, §5). Pure schema tests; no database."""

import pytest
from pydantic import ValidationError

from app.schemas import AdminLeadConversionIn, BdmLeadCreate


def body(**over) -> dict:
    data = {"name": "Asha Nair", "email": "asha@example.com", "interest": "B.Tech admissions"}
    data.update(over)
    return data


def messages(raw: dict, model=BdmLeadCreate) -> list[str]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(raw)
    return [e["msg"] for e in caught.value.errors()]


def test_minimal_lead_is_valid_and_server_owned_fields_have_defaults():
    lead = BdmLeadCreate.model_validate(body())
    assert (lead.name, lead.email, lead.phone, lead.interest, lead.note, lead.acknowledge_duplicate) == (
        "Asha Nair", "asha@example.com", None, "B.Tech admissions", None, False)


@pytest.mark.parametrize("field", ["source", "division", "status", "bdm_organization_id", "bdm_user_id", "converted_user_id", "owner_id"])
def test_server_owned_fields_are_refused(field):
    assert any("Extra inputs" in m for m in messages(body(**{field: "x"})))


def test_email_is_trimmed_and_lowered():
    assert BdmLeadCreate.model_validate(body(email="  Asha@Example.COM ")).email == "asha@example.com"


@pytest.mark.parametrize("bad", ["asha", "asha@", "a b@c.com", "asha@example"])
def test_invalid_email_is_refused_in_plain_words(bad):
    assert "Value error, Enter a valid email address" in messages(body(email=bad))


@pytest.mark.parametrize(("field", "label"), [("name", "Student name"), ("interest", "Interest"), ("email", "Email")])
def test_required_text_cannot_be_blank(field, label):
    assert f"Value error, {label} is required" in messages(body(**{field: "   "}))


@pytest.mark.parametrize(("field", "limit"), [("name", 160), ("email", 255), ("phone", 40), ("interest", 180), ("note", 5000)])
def test_lengths_match_the_enquiries_columns(field, limit):
    value = ("a" * (limit - len("@example.com")) + "@example.com") if field == "email" else ("1" * limit if field == "phone" else "a" * limit)
    BdmLeadCreate.model_validate(body(**{field: value}))
    too_long = value + ("1" if field == "phone" else "a")
    if field == "email":
        too_long = "a" + value
    assert any("at most" in m for m in messages(body(**{field: too_long})))


def test_phone_allows_only_dialable_characters():
    assert BdmLeadCreate.model_validate(body(phone="+91 (484) 000-1111")).phone == "+91 (484) 000-1111"
    assert "Value error, Phone may contain only digits, spaces and + - ( )" in messages(body(phone="call me"))


def test_blank_optional_fields_become_none():
    lead = BdmLeadCreate.model_validate(body(phone="  ", note=" "))
    assert (lead.phone, lead.note) == (None, None)


def test_note_keeps_line_breaks_but_single_line_fields_refuse_them():
    assert BdmLeadCreate.model_validate(body(note="Line one\nLine two")).note == "Line one\nLine two"
    assert "Value error, Student name contains invalid characters" in messages(body(name="Asha\nNair"))


def test_acknowledge_duplicate_is_a_strict_bool():
    assert BdmLeadCreate.model_validate(body(acknowledge_duplicate=True)).acknowledge_duplicate is True
    assert messages(body(acknowledge_duplicate="yes"))


def test_conversion_body_takes_one_trimmed_lowered_email_and_nothing_else():
    assert AdminLeadConversionIn.model_validate({"student_email": " Stu@Example.com "}).student_email == "stu@example.com"
    assert "Value error, Enter a valid email address" in messages({"student_email": "nope"}, AdminLeadConversionIn)
    assert any("Extra inputs" in m for m in messages({"student_email": "s@example.com", "user_id": "x"}, AdminLeadConversionIn))
