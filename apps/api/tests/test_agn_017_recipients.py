"""AGN-017 N2/N5/§8 -- who hears about an agency student, and what may appear in a notice. Service-level: the event tests exercise the
routes."""

import pytest
import pytest_asyncio

from app.services import agent_notifications as notices_svc
from tests.agn004_helpers import mk_record
from tests.agn008_helpers import agency_world
from tests.agn017_helpers import channels_of, deactivate, notices, set_org_status
from tests.enh014_helpers import set_prefs


@pytest_asyncio.fixture
async def world(db_session):
    return await agency_world(db_session)


def _ids(users) -> list:
    return sorted(u.id for u in users)


@pytest.mark.asyncio
async def test_the_active_assignee_is_the_recipient(db_session, world):
    users = await notices_svc.recipients(db_session, world["record"], world["master"])
    assert _ids(users) == [world["staff"]["user"].id]


@pytest.mark.asyncio
async def test_the_actor_is_never_a_recipient(db_session, world):
    assert await notices_svc.recipients(db_session, world["record"], world["staff"]["user"]) == []


@pytest.mark.asyncio
async def test_a_deactivated_assignee_falls_back_to_the_active_masters(db_session, world):
    await deactivate(db_session, world["staff"]["member"])
    users = await notices_svc.recipients(db_session, world["record"], world["staff"]["user"])
    assert _ids(users) == [world["master"].id]


@pytest.mark.asyncio
async def test_an_unassigned_student_goes_to_the_masters_but_not_the_acting_master(db_session, world):
    record = await mk_record(db_session, agent=world["master"], full_name="Unassigned")
    assert _ids(await notices_svc.recipients(db_session, record, None)) == [world["master"].id]
    assert await notices_svc.recipients(db_session, record, world["master"]) == []


@pytest.mark.asyncio
async def test_an_inactive_organisation_notifies_nobody(db_session, world):
    await set_org_status(db_session, world["org"], "suspended")
    assert await notices_svc.recipients(db_session, world["record"], None) == []


@pytest.mark.asyncio
async def test_another_agency_is_never_a_recipient(db_session, world):
    other_ids = {world["other"]["master"].id}
    users = await notices_svc.recipients(db_session, world["record"], None)
    assert not other_ids & set(_ids(users))


def test_only_known_document_types_are_named():
    assert notices_svc.document_label("Passport") == "Passport"
    assert notices_svc.document_label("rahul's passport scan") == "A document"
    assert notices_svc.document_label(None) == "A document"
    assert notices_svc.document_label("Other") == "A document"  # "Other" names nothing; its label is user-typed and never shown


def test_stored_text_loses_control_characters_and_is_capped():
    cleaned = notices_svc.clean_text("Uni\r\nBcc: x@example.com\t" + "y" * 300)
    assert "\r" not in cleaned and "\n" not in cleaned and "\t" not in cleaned
    assert len(cleaned) <= 120
    assert notices_svc.clean_text(None) == ""


@pytest.mark.asyncio
async def test_notify_queues_email_only_even_for_a_whatsapp_opt_in(db_session, world):
    staff = world["staff"]["user"]
    await set_prefs(db_session, staff, whatsapp=True, sms=True)
    count = await notices_svc.notify(db_session, [staff], "Title", "Body", notices_svc.TASKS_URL)
    await db_session.commit()
    assert count == 1
    [item] = await notices(db_session, staff)
    assert (item.title, item.body, item.action_url, item.read, item.dedupe_key) == ("Title", "Body", "/overseas/agent/tasks", False, None)
    assert await channels_of(db_session, item) == ["email"]
