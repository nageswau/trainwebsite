"""bdm-005 QA5-01 -- a field edit from a stale form must not silently overwrite a newer one. The form sends the `updated_at` it was
showing as `expected_updated_at`; a different stored value is 409 `mou_changed`. Without it the PATCH behaves as before."""

import pytest

from tests.bdm005_helpers import change, events, started, world


@pytest.mark.asyncio
async def test_a_stale_field_edit_is_409_and_changes_nothing(client, db_session):
    w = await world(client, db_session)
    shown = await started(client, w["org"], reference="MOU-1")
    first = await change(client, w["org"], reference="FROM-A", expected_updated_at=shown["updated_at"])
    assert first.status_code == 200, first.text
    stale = await change(client, w["org"], reference="FROM-B", expected_updated_at=shown["updated_at"])
    assert stale.status_code == 409
    assert stale.json()["detail"] == {"message": "This MoU was changed meanwhile", "code": "mou_changed"}
    assert first.json()["mou"]["reference"] == "FROM-A"
    assert [e.kind for e in await events(db_session, shown["id"])] == ["created", "updated"]


@pytest.mark.asyncio
async def test_the_current_version_saves_and_the_check_is_optional(client, db_session):
    w = await world(client, db_session)
    shown = await started(client, w["org"])
    saved = await change(client, w["org"], notes="x", expected_updated_at=shown["updated_at"])
    assert saved.status_code == 200, saved.text
    again = await change(client, w["org"], notes="y", expected_updated_at=saved.json()["mou"]["updated_at"])
    assert again.status_code == 200, again.text
    assert (await change(client, w["org"], notes="z")).status_code == 200  # older clients without the field


@pytest.mark.asyncio
async def test_a_stale_status_change_keeps_its_own_message(client, db_session):
    """The status conflict names the status someone else set, so it is checked first."""
    w = await world(client, db_session)
    shown = await started(client, w["org"])
    await change(client, w["org"], status="rejected", from_status="prospect")
    stale = await change(client, w["org"], status="discussion_started", from_status="prospect", expected_updated_at=shown["updated_at"])
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "mou_status_changed"
