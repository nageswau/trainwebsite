"""tel-012 test builders. Every value is unique per call: the test database is shared and never truncated."""

import uuid

from app.models import TelProduct
from tests.bdm001_helpers import login, make_user

READERS = [("telecaller", "it"), ("telecaller_manager", "global"), ("super_admin", "global")]
WRITERS = [("telecaller_manager", "global"), ("super_admin", "global")]
NON_READERS = [("it_admin", "it"), ("overseas_admin", "overseas"), ("counselor", "overseas"), ("bdm_manager", "global"), ("it_student", "it")]
PDF_BYTES = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def uname(prefix: str = "T") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def as_role(client, db, role="telecaller_manager", division="global"):
    user = await make_user(db, role, division)
    await login(client, user)
    return user


async def product(db, *, group="it", active=True) -> TelProduct:
    row = TelProduct(product_group=group, name=uname("Prod"), team=None if group == "other" else group, active=active)
    db.add(row)
    await db.commit()
    return row
