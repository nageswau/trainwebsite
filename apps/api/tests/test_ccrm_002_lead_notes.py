"""ccrm-002 (DEC-SCOPE-242): append-only lead notes -- written and read through the telecaller, counselor and admin lead routes, each in its
own scope (out of scope 404), and shown in the lead timeline (tel-015) with author and time. The shared test database is never truncated:
every assertion is about leads the test made."""

import pytest
from sqlalchemy import select

from app.models import AuditLog, LeadNote
from tests.tel004_helpers import make_user
from tests.tel018_helpers import as_user, c_url, handover, make_counselor, setup

TEL = "/api/v1/telecaller/leads"
ADMIN = "/api/v1/admin/leads"


def t_url(lead_id, tail: str = "/notes") -> str:
    return f"{TEL}/{lead_id}{tail}"


def a_url(lead_id, tail: str = "/notes") -> str:
    return f"{ADMIN}/{lead_id}{tail}"


async def handed(client, db, division: str = "it", **over):
    manager, tel, counselor, row = await setup(db, division, **over)
    assert (await handover(client, tel, row, counselor)).status_code == 200
    return manager, tel, counselor, row


async def add(client, url: str, text: str = "Prefers a weekend batch"):
    return await client.post(url, json={"body": text})


# --- AC: a counselor adds a note -> the timeline shows it with author and time ----------------------------------------------------
@pytest.mark.asyncio
async def test_counselor_adds_a_note_and_the_timeline_shows_it_with_author_and_time(client, db_session):
    _, _, counselor, row = await handed(client, db_session)
    await as_user(client, counselor)
    created = await add(client, c_url(row.id, "/notes"), "  Parents want a call on Sunday  ")
    assert created.status_code == 201, created.text
    note = created.json()
    assert note["body"] == "Parents want a call on Sunday"  # N4: trimmed
    assert note["author"] == {"id": str(counselor.id), "full_name": counselor.full_name} and note["at"]

    listed = await client.get(c_url(row.id, "/notes"))
    assert listed.status_code == 200 and listed.json()["total"] == 1 and listed.json()["items"][0]["id"] == note["id"]

    timeline = (await client.get(c_url(row.id, "/timeline"))).json()["items"]
    entry = next(i for i in timeline if i["kind"] == "note")
    assert entry["id"] == note["id"] and entry["reason"] == "Parents want a call on Sunday"
    assert entry["actor"]["id"] == str(counselor.id) and entry["at"]


@pytest.mark.asyncio
async def test_another_counselors_lead_is_404_for_read_and_write(client, db_session):
    _, _, _, row = await handed(client, db_session)
    other = await make_counselor(db_session)
    await as_user(client, other)
    assert (await client.get(c_url(row.id, "/notes"))).status_code == 404
    assert (await add(client, c_url(row.id, "/notes"))).status_code == 404
    assert (await db_session.scalar(select(LeadNote.id).where(LeadNote.lead_id == row.id))) is None


@pytest.mark.asyncio
async def test_a_counselor_of_another_division_is_404(client, db_session):
    _, _, counselor, row = await handed(client, db_session)
    counselor.division = "overseas"
    await db_session.commit()
    await as_user(client, counselor)
    assert (await add(client, c_url(row.id, "/notes"))).status_code == 404


# --- writers: the telecaller (N1), the manager in scope, super_admin, admins --------------------------------------------------------
@pytest.mark.asyncio
async def test_the_telecaller_writes_even_after_the_handover_and_the_manager_reads_it(client, db_session):
    manager, tel, _, row = await handed(client, db_session)
    await as_user(client, tel)
    assert (await add(client, t_url(row.id), "Spoke to the father")).status_code == 201
    await as_user(client, manager)
    assert (await add(client, t_url(row.id), "Manager check-in")).status_code == 201
    items = (await client.get(t_url(row.id))).json()["items"]
    assert [i["body"] for i in items] == ["Manager check-in", "Spoke to the father"]  # newest first


@pytest.mark.asyncio
async def test_a_telecaller_outside_the_t23_scope_gets_404(client, db_session):
    _, _, _, row = await setup(db_session)
    _, stranger, _, _ = await setup(db_session)
    await as_user(client, stranger)
    assert (await client.get(t_url(row.id))).status_code == 404
    assert (await add(client, t_url(row.id))).status_code == 404


@pytest.mark.asyncio
async def test_admins_write_in_their_division_and_get_403_outside_it(client, db_session):
    _, _, _, row = await setup(db_session, "overseas")
    overseas_admin = await make_user(db_session, "overseas_admin", "overseas")
    await as_user(client, overseas_admin)
    assert (await add(client, a_url(row.id), "Admin note")).status_code == 201
    assert (await client.get(a_url(row.id))).json()["total"] == 1

    it_admin = await make_user(db_session, "it_admin", "it")
    await as_user(client, it_admin)
    assert (await add(client, a_url(row.id))).status_code == 403

    super_admin = await make_user(db_session, "super_admin", "it")
    await as_user(client, super_admin)
    assert (await add(client, a_url(row.id), "Super admin note")).status_code == 201
    assert (await add(client, t_url(row.id), "Through the telecaller routes")).status_code == 201
    assert (await client.get(a_url("00000000-0000-0000-0000-000000000000"))).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["it_student", "trainer", "bdm"])
async def test_other_roles_are_refused(client, db_session, role):
    _, _, _, row = await setup(db_session)
    await as_user(client, await make_user(db_session, role, "it"))
    assert (await add(client, t_url(row.id))).status_code == 403
    assert (await add(client, c_url(row.id, "/notes"))).status_code == 403
    assert (await add(client, a_url(row.id))).status_code == 403


# --- validation, history edge cases, audit ------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["", "   ", "x" * 4001], ids=["empty", "blank", "4001"])
async def test_an_empty_or_too_long_body_is_422(client, db_session, text):
    _, tel, _, row = await setup(db_session)
    await as_user(client, tel)
    assert (await add(client, t_url(row.id), text)).status_code == 422


@pytest.mark.asyncio
async def test_4000_characters_are_kept_whole_and_the_timeline_shows_an_excerpt(client, db_session):
    _, tel, _, row = await setup(db_session)
    await as_user(client, tel)
    assert (await add(client, t_url(row.id), "y" * 4000)).status_code == 201
    assert (await client.get(t_url(row.id))).json()["items"][0]["body"] == "y" * 4000
    entry = next(i for i in (await client.get(t_url(row.id, "/timeline"))).json()["items"] if i["kind"] == "note")
    assert entry["reason"] == "y" * 200


@pytest.mark.asyncio
async def test_a_closed_lead_takes_notes(client, db_session):
    _, tel, _, row = await setup(db_session, status="lost")
    await as_user(client, tel)
    assert (await add(client, t_url(row.id), "Closed: went with another institute")).status_code == 201


@pytest.mark.asyncio
async def test_a_returned_lead_keeps_its_notes(client, db_session):
    _, tel, counselor, row = await handed(client, db_session)
    await as_user(client, counselor)
    assert (await add(client, c_url(row.id, "/notes"), "Not ready this intake")).status_code == 201
    assert (await client.post(c_url(row.id, "/return"), json={"reason": "Not ready"})).status_code == 200
    await as_user(client, tel)
    items = (await client.get(t_url(row.id))).json()["items"]
    assert [i["body"] for i in items] == ["Not ready this intake"] and items[0]["author"]["id"] == str(counselor.id)


@pytest.mark.asyncio
async def test_the_audit_row_never_carries_the_body(client, db_session):
    _, tel, _, row = await setup(db_session)
    await as_user(client, tel)
    note = (await add(client, t_url(row.id), "Private family detail")).json()
    audit = await db_session.scalar(select(AuditLog).where(AuditLog.action == "lead_note.create", AuditLog.entity_id == str(row.id)))
    assert audit is not None and audit.user_id == tel.id and audit.metadata_json == {"note_id": note["id"]}


@pytest.mark.asyncio
async def test_notes_page_newest_first_with_an_exact_total(client, db_session):
    _, tel, _, row = await setup(db_session)
    await as_user(client, tel)
    for n in range(3):
        assert (await add(client, t_url(row.id), f"Note {n}")).status_code == 201
    first = (await client.get(t_url(row.id) + "?limit=2&offset=0")).json()
    second = (await client.get(t_url(row.id) + "?limit=2&offset=2")).json()
    assert first["total"] == 3 and [i["body"] for i in first["items"] + second["items"]] == ["Note 2", "Note 1", "Note 0"]
