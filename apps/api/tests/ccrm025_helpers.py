"""ccrm-025 test helpers: ccrm-023's offer world -- the AGN-023 world with both applications assigned to the counselor at University
selection, and an "Offer letter" uploaded for each."""

from tests.agn001_helpers import client_for
from tests.agn009_helpers import mk_doc
from tests.agn023_helpers import ASSIGN, assign_world


async def offers_world(db) -> dict:
    w = await assign_world(db, status="university_selection")
    async with client_for(w["admin"].email) as c:
        for app in (w["app"], w["direct_app"]):
            assert (await c.put(ASSIGN.format(app.id), json={"counselor_id": str(w["counselor"].id)})).status_code == 200
    w["direct_letter"] = await mk_doc(db, student=w["direct_student"], application=w["direct_app"], document_type="Offer letter")
    w["agency_letter"] = await mk_doc(db, record=w["record"], application=w["app"], document_type="Offer letter")
    return w
