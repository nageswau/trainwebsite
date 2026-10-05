"""bdm-004 -- the stage history (spec §6.3; AC2): newest first, labels, actor, note; readable in the read scope."""

import pytest

from tests.bdm001_helpers import login, make_manager
from tests.bdm002_helpers import create_org, make_bdm
from tests.bdm004_helpers import move, url


@pytest.mark.asyncio
async def test_history_is_newest_first_with_labels_actor_and_note(client, db_session):
    manager = await make_manager(db_session)
    bdm = await make_bdm(db_session, manager, "school")
    await login(client, bdm)
    org = await create_org(client)
    empty = (await client.get(url(org["id"], "stage-history"))).json()
    assert empty == {"items": [], "total": 0, "limit": 50, "offset": 0}
    org = (await move(client, org, "presentation")).json()["organization"]
    org = (await move(client, org, "contacted", note="Back to basics")).json()["organization"]
    await client.post(url(org["id"], "lost"), json={"reason": "Board changed"})
    page = (await client.get(url(org["id"], "stage-history"), params={"limit": 2})).json()
    assert page["total"] == 3 and page["limit"] == 2 and len(page["items"]) == 2
    lost, back = page["items"]
    assert (lost["kind"], lost["from_label"], lost["to_label"], lost["note"]) == ("lost", "Contacted", "Contacted", "Board changed")
    assert (back["kind"], back["from_label"], back["to_label"], back["note"]) == ("move", "Presentation", "Contacted", "Back to basics")
    assert back["actor"] == {"id": str(bdm.id), "full_name": bdm.full_name}
    first = (await client.get(url(org["id"], "stage-history"), params={"limit": 2, "offset": 2})).json()["items"]
    assert [(e["from_label"], e["to_label"]) for e in first] == [("School Prospect", "Presentation")]
    await login(client, manager)  # S1: the manager reads the team's history
    assert (await client.get(url(org["id"], "stage-history"))).json()["total"] == 3
