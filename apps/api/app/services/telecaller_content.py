"""tel-012 (DEC-SCOPE-076, spec §4-§6): the script, message-template and brochure library -- placeholder rules and rendering, the
signed brochure links, and the stored PDF objects.

Functions only; nothing here commits -- the route owns the transaction. Audit rows carry ids and changed field names only (tel-002's
`audit`). Never log a link token or a storage key."""

import re

from fastapi import HTTPException

PLACEHOLDERS = ("name", "product", "brochure_link", "appointment_time")
_TOKEN = re.compile(r"\{([^{}\n]*)\}")
_UNKNOWN = "Unknown placeholder {%s}. Use {name}, {product}, {brochure_link} or {appointment_time}"


def check_placeholders(*texts: str | None) -> set[str]:
    """AC3: every `{...}` in the texts must be one of the four placeholders, spelled exactly; returns the ones used. A lone brace is
    plain text."""
    used: set[str] = set()
    for text in texts:
        for token in _TOKEN.findall(text or ""):
            if token not in PLACEHOLDERS:
                raise HTTPException(422, _UNKNOWN % token)
            used.add(token)
    return used


def render(text: str, values: dict[str, str]) -> str:
    """AC2: one pass, so a value that looks like a placeholder is never expanded again; a missing value renders empty. Plain text out --
    the sink escapes (wa.me URL-encoding in tel-013, HTML in tel-014)."""
    return _TOKEN.sub(lambda m: values.get(m.group(1), "") if m.group(1) in PLACEHOLDERS else m.group(0), text)
