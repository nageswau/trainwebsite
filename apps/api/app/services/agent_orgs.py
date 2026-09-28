"""AGN-001 / DEC-SCOPE-034 -- agent organisations (tenants) and their Master members.

Functions only -- no class layer (same shape as `services/provisioning.py`). Spec:
docs/superpowers/specs/2026-09-28-agn-001-multi-tenant-agent-crm-design.md.
"""

import re

MASTER_LIMIT = 3
ORG_STATUSES = ("pending", "active", "rejected", "suspended")

_LATIN = re.compile(r"[A-Za-z]")


def derive_prefix_base(name: str | None) -> str:
    """D5: the first three Latin letters, uppercased, padded with X; no Latin letters -> AGT."""
    letters = _LATIN.findall(name or "")
    if not letters:
        return "AGT"
    return "".join(letters[:3]).upper().ljust(3, "X")


def pick_prefix(base: str, taken: set[str]) -> str:
    """D5 collision rule: the base if free, else the lowest free base+N for N >= 2."""
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def member_code(prefix: str, seq: int) -> str:
    return f"{prefix}-M{seq:03d}"
