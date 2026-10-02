"""AGN-010 AC06 -- the offer route's authorization and IDOR guards (spec §7): scope 404s, the offer document must be this
application's offer letter, other roles and super_admin refused, mass assignment refused. Nothing is written on any refusal."""

import uuid

import pytest
import pytest_asyncio

from tests.agn001_helpers import client_for, mk_user
from tests.agn008_helpers import mk_application
from tests.agn009_helpers import mk_doc
from tests.agn010_helpers import OFFER_LETTER, offer_body, offer_url, offer_world, writes_for


@pytest_asyncio.fixture
async def world(db_session):
    return await offer_world(db_session)


@pytest.mark.asyncio
@pytest.mark.parametrize("who", ["other_org_master", "other_staff"])
async def test_application_outside_scope_is_404(db_session, world, who):
    email = world["other"]["master"].email if who == "other_org_master" else world["other_staff"]["user"].email
    async with client_for(email) as c:
        r = await c.put(offer_url(world["app"].id), json=offer_body())
    assert r.status_code == 404 and r.json()["detail"] == "Application not found"
    assert await writes_for(db_session, world["app"].id) == (0, 0)


@pytest.mark.asyncio
async def test_document_of_another_application_is_422(db_session, world):
    second = await mk_application(db_session, agent=world["master"], university=world["university"], record=world["linked_record"])
    letter = await mk_doc(db_session, record=world["linked_record"], application=second, document_type=OFFER_LETTER)
    async with client_for(world["master"].email) as c:
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=letter.id))
    assert r.status_code == 422 and r.json()["detail"] == "Choose an offer letter uploaded for this application"
    assert await writes_for(db_session, world["app"].id) == (0, 0)


@pytest.mark.asyncio
async def test_document_of_the_wrong_type_is_422(db_session, world):
    passport = await mk_doc(db_session, record=world["record"], application=world["app"], document_type="Passport")
    async with client_for(world["master"].email) as c:
        r = await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=passport.id))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_document_outside_scope_or_unknown_is_404(db_session, world):
    outsider = await mk_application(db_session, agent=world["other"]["master"], university=world["university"], student=await mk_user(db_session, role="overseas_student"))
    foreign = await mk_doc(db_session, student=await mk_user(db_session, role="overseas_student"), application=outsider, document_type=OFFER_LETTER)
    async with client_for(world["master"].email) as c:
        for doc_id in (foreign.id, uuid.uuid4()):
            r = await c.put(offer_url(world["app"].id), json=offer_body(offer_document_id=doc_id))
            assert r.status_code == 404 and r.json()["detail"] == "Document not found"
    assert await writes_for(db_session, world["app"].id) == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["super_admin", "counselor", "university_rep", "overseas_admin"])
async def test_other_roles_are_refused(db_session, world, role):
    user = await mk_user(db_session, role=role)
    async with client_for(user.email) as c:
        assert (await c.put(offer_url(world["app"].id), json=offer_body())).status_code == 403
    assert await writes_for(db_session, world["app"].id) == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"status": "enrolled"}, {"offer_letter_url": "https://evil.example/x.pdf"}, {"agent_id": str(uuid.uuid4())}])
async def test_unknown_fields_are_422(db_session, world, extra):
    async with client_for(world["master"].email) as c:
        assert (await c.put(offer_url(world["app"].id), json=offer_body() | extra)).status_code == 422
    assert await writes_for(db_session, world["app"].id) == (0, 0)
