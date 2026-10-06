"""tel-012 -- placeholder validation and rendering (spec §4; AC2, AC3). Pure functions: no database."""

import pytest
from fastapi import HTTPException

from app.services.telecaller_content import PLACEHOLDERS, check_placeholders, render

UNKNOWN = "Unknown placeholder {x}. Use {name}, {product}, {brochure_link} or {appointment_time}"


def test_the_four_placeholders():
    assert PLACEHOLDERS == ("name", "product", "brochure_link", "appointment_time")


def test_check_returns_the_placeholders_used_across_texts():
    assert check_placeholders("Dear {name}", "About {product} at {appointment_time}", None) == {"name", "product", "appointment_time"}
    assert check_placeholders("No placeholders here") == set()


@pytest.mark.parametrize("token", ["{discount}", "{NAME}", "{ name }", "{}", "{brochure-link}"])
def test_an_unknown_placeholder_is_a_422_naming_it(token):
    with pytest.raises(HTTPException) as exc:
        check_placeholders("Hi {name}", f"Offer {token} today")
    assert exc.value.status_code == 422
    assert exc.value.detail == UNKNOWN.replace("{x}", token)


def test_lone_braces_are_plain_text():
    assert check_placeholders("Smile :} or {: and a brace { across\n lines }") == set()


def test_render_fills_every_placeholder():
    values = {"name": "Priya", "product": "Cyber Security", "brochure_link": "https://x/b", "appointment_time": "Mon 10:30"}
    text = "Hi {name}, {product} brochure: {brochure_link}. See you {appointment_time}."
    assert render(text, values) == "Hi Priya, Cyber Security brochure: https://x/b. See you Mon 10:30."


def test_render_is_a_single_pass():
    """A value that itself looks like a placeholder is never expanded again."""
    assert render("Hi {name} -- {product}", {"name": "{product}", "product": "SAP"}) == "Hi {product} -- SAP"


def test_a_missing_value_renders_empty_and_text_is_not_escaped():
    """Escaping belongs to the sink (wa.me URL-encoding, email HTML escaping) -- see spec §4."""
    assert render("Hi {name}<b>{product}</b>", {"name": "A & B"}) == "Hi A & B<b></b>"
