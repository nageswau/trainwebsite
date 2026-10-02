"""AGN-010 AC08 (documents) -- "Offer letter" is an upload type that must name its application; document requests keep the AGN-009
list (an offer letter is never asked of a student). Spec §4.4."""

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import StudentDocument
from tests.agn001_helpers import client_for
from tests.agn009_helpers import DOCS, REQUESTS, upload_files
from tests.agn010_helpers import OFFER_LETTER, offer_body, offer_url, offer_world


@pytest_asyncio.fixture
async def world(db_session):
    return await offer_world(db_session)


async def _letters(db, world) -> int:
    return await db.scalar(select(func.count()).select_from(StudentDocument).where(StudentDocument.agent_student_id == world["record"].id, StudentDocument.document_type == OFFER_LETTER))


@pytest.mark.asyncio
async def test_an_offer_letter_uploaded_for_the_application_can_be_attached(db_session, world):
    form = {"agent_student_id": str(world["record"].id), "document_type": OFFER_LETTER, "application_id": str(world["app"].id)}
    async with client_for(world["staff"]["user"].email) as c:
        r = await c.post(DOCS, data=form, files=upload_files(name="offer.pdf"))
        assert r.status_code == 201, r.text
        doc_id = r.json()["document"]["id"]
        offer = (await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=doc_id))).json()["application"]["offer"]
    assert offer["document"]["id"] == doc_id and offer["document"]["name"] == "offer.pdf"


@pytest.mark.asyncio
async def test_an_offer_letter_without_an_application_is_422(db_session, world):
    before = await _letters(db_session, world)
    async with client_for(world["master"].email) as c:
        r = await c.post(DOCS, data={"agent_student_id": str(world["record"].id), "document_type": OFFER_LETTER}, files=upload_files())
    assert r.status_code == 422 and r.json()["detail"] == "Choose the application this offer letter belongs to"
    assert await _letters(db_session, world) == before


@pytest.mark.asyncio
async def test_an_offer_letter_cannot_be_requested_from_a_student(world):
    async with client_for(world["master"].email) as c:
        r = await c.post(REQUESTS, json={"agent_student_id": str(world["record"].id), "document_type": OFFER_LETTER})
    assert r.status_code == 422
