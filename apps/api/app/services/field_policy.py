"""nehn-008 (DEC-SCOPE-300): the field (column) policy -- a user may not download what they cannot see.

A report tags its sensitive columns with a field class (`{"commission_expected": "financial"}`); the caller gets a tagged column only
with the catalogue permission `field.<class>.view` (role grant ± their nehn-007 override; super_admin always). An untagged column is the
report's own business: its route gate and row scope already apply (F2). The report applies this to the one payload its JSON and its
CSV/xlsx are rendered from, so the screen and the file can never differ. A class outside the catalogue reaches nobody (deny by default)."""

from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.permissions import user_has_grant


async def strip(db: AsyncSession, user: User, payload: dict, classes: Mapping[str, str]) -> dict:
    """The payload without the columns the user may not view: gone from `columns`, from every item and from `totals`. Not mutated."""
    present = {classes[c["key"]] for c in payload["columns"] if c["key"] in classes}
    denied_classes = {cls for cls in present if not await user_has_grant(db, user, f"field.{cls}", "view")}
    denied = {key for key, cls in classes.items() if cls in denied_classes}
    if not denied:
        return payload
    totals = payload.get("totals")
    return {
        **payload,
        "columns": [c for c in payload["columns"] if c["key"] not in denied],
        "items": [{k: v for k, v in item.items() if k not in denied} for item in payload["items"]],
        "totals": {k: v for k, v in totals.items() if k not in denied} if totals else totals,
    }
