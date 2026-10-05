"""ENH-025 -- StudentMasterFields / CareerPreferencesUpdate boundary rules (spec §2.1, §3.2)."""

import pytest
from pydantic import ValidationError

from app.schemas import CAREER_PREFERENCE_KEYS, MASTER_FIELD_KEYS, CareerPreferencesUpdate, StudentMasterFields, validation_message


def _msg(model, data):
    with pytest.raises(ValidationError) as exc:
        model.model_validate(data)
    return validation_message(exc.value)


def test_keys_are_the_ten_value_fields():
    assert set(MASTER_FIELD_KEYS) == {"section", "roll_number", "gender", "student_mobile", "city", "subjects", "career_interests", "global_education_interest", "preferred_countries", "preferred_courses"}
    assert set(MASTER_FIELD_KEYS) == set(StudentMasterFields.model_fields)
    assert set(CAREER_PREFERENCE_KEYS) == {"career_interests", "global_education_interest", "preferred_countries", "preferred_courses"}


def test_text_is_trimmed_and_empty_becomes_none():
    f = StudentMasterFields.model_validate({"city": "  Pune ", "section": "", "roll_number": "   "})
    assert (f.city, f.section, f.roll_number) == ("Pune", None, None)
    assert f.model_fields_set == {"city", "section", "roll_number"}


@pytest.mark.parametrize("value", ["female", "Male", " OTHER ", "prefer_not_to_say"])
def test_gender_accepts_the_fixed_list_case_insensitively(value):
    assert StudentMasterFields.model_validate({"gender": value}).gender == value.strip().lower()


def test_gender_rejects_other_values_without_echoing_them():
    assert _msg(StudentMasterFields, {"gender": "robot"}) == "gender must be one of: female, male, other, prefer_not_to_say"


@pytest.mark.parametrize("value", ["+91 98765 43210", "(020) 1234-567", "9876543210"])
def test_mobile_accepts_phone_shapes(value):
    assert StudentMasterFields.model_validate({"student_mobile": value}).student_mobile == value


@pytest.mark.parametrize("value", ["12345", "call me", "+++---()()", "1" * 21])
def test_mobile_rejects_bad_values_without_echoing_them(value):
    msg = _msg(StudentMasterFields, {"student_mobile": value})
    assert msg.startswith("student_mobile ")
    assert value not in msg


def test_lists_trim_dedupe_case_insensitively_and_empty_becomes_none():
    f = StudentMasterFields.model_validate({"subjects": [" Maths", "maths", "Physics", ""], "preferred_courses": []})
    assert f.subjects == ["Maths", "Physics"]
    assert f.preferred_courses is None


def test_list_limits():
    assert _msg(StudentMasterFields, {"subjects": [f"S{i}" for i in range(21)]}) == "subjects must have at most 20 items"
    assert _msg(StudentMasterFields, {"subjects": ["x" * 81]}) == "subjects items must be at most 80 characters"
    assert _msg(StudentMasterFields, {"subjects": "Maths"}) == "subjects must be a list of text values"


def test_length_limits():
    assert _msg(StudentMasterFields, {"section": "x" * 21}) == "section must be at most 20 characters"
    assert _msg(StudentMasterFields, {"city": "x" * 121}) == "city must be at most 120 characters"


@pytest.mark.parametrize("value", ["A\x00", "Pu\nne", "A‮B", "B⁦"])
def test_control_and_bidi_characters_rejected(value):
    assert _msg(StudentMasterFields, {"city": value}) == "city must not contain control or bidirectional-override characters"


def test_zero_width_joiner_is_allowed_for_indic_names():
    assert StudentMasterFields.model_validate({"city": "ತುಮ‍ಕೂರು"}).city == "ತುಮ‍ಕೂರು"


def test_global_interest_is_strict_boolean():
    assert StudentMasterFields.model_validate({"global_education_interest": False}).global_education_interest is False
    assert _msg(StudentMasterFields, {"global_education_interest": "yes"}).startswith("global_education_interest ")


def test_unknown_keys_rejected():
    assert _msg(StudentMasterFields, {"photo_key": "x"}) == "photo_key is not an accepted field"
    assert _msg(CareerPreferencesUpdate, {"roll_number": "7"}) == "roll_number is not an accepted field"


def test_career_update_accepts_only_its_four_fields():
    f = CareerPreferencesUpdate.model_validate({"career_interests": ["Engineering"], "global_education_interest": True})
    assert f.career_interests == ["Engineering"]
    assert f.model_fields_set == {"career_interests", "global_education_interest"}
