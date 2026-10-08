r"""ENH-014 (spec §6.3, D14): normalise a stored phone number to E.164 for Twilio. Format check only -- no OTP.

ASCII digits only ([0-9], never \d or str.isdigit(), which accept e.g. Devanagari digits). Default country India."""

import re

_SEPARATORS = re.compile(r"[\s\-().]")
_INTERNATIONAL = re.compile(r"\+[0-9]{8,15}")
_INDIAN_MOBILE = re.compile(r"(?:0|91)?([6-9][0-9]{9})")


def normalise_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    compact = _SEPARATORS.sub("", raw)
    if _INTERNATIONAL.fullmatch(compact):
        return compact
    match = _INDIAN_MOBILE.fullmatch(compact)
    return f"+91{match.group(1)}" if match else None


def wa_number(raw: str | None) -> str | None:
    """rec-026 MS6: a wa.me number -- E.164 digits without the `+`; None when the phone is unusable."""
    number = normalise_phone(raw)
    return number.lstrip("+") if number else None
