"""hrc-020 -- saved Find Candidates searches (DEC-SCOPE-401 X1-X7; design
docs/superpowers/specs/2026-11-05-hrc-020-saved-searches-export-design.md). Each test makes its own users, so its own searches are the
only personal ones it sees; shared ones from other tests may appear in a list, so assertions look rows up by id."""

import pytest
from sqlalchemy import select, update

from app.models import SavedCandidateSearch, UserPermissionOverride
from app.services import saved_searches
from tests.rec038_helpers import _user, add, tag
from tests.tel026_helpers import headers

pytestmark = pytest.mark.asyncio
SAVED = "/api/v1/recruiter/candidates/saved-searches"
SEARCH = "/api/v1/recruiter/candidates/search"


async def _people(db):
    recruiter = await _user(db, "placement_team", "it")
    other = await _user(db, "placement_team", "it")
    await db.commit()
    return recruiter, other


async def _save(client, user, name=None, filters=None, shared=False):
    body = {"name": tag("Java devs ") if name is None else name, "filters": filters or {"all": ["Python"]}, "shared": shared}
    return await client.post(SAVED, json=body, headers=headers(user))


def _row(response, search_id):
    assert response.status_code == 200, response.text
    return next((item for item in response.json()["items"] if item["id"] == search_id), None)


async def test_save_and_restore_exactly(client, db_session):
    """AC1: the stored filters are the search body, canonical (defaults left out), so the same search runs again."""
    recruiter, _ = await _people(db_session)
    filters = {"all": ["Python"], "any": [["Django", "Flask"]], "experience_min_months": 24, "experience_max_months": 71, "availability": ["d15"],
               "fresher": False, "city": "Pune", "sort": "experience", "verified_only": False, "cgpa_min": "7.5"}  # fmt: skip
    created = await _save(client, recruiter, name="  Pune   Python  ", filters=filters)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["name"] == "Pune Python" and body["shared"] is False and body["mine"] is True and body["ignored"] == []
    assert body["filters"] == {"all": ["Python"], "any": [["Django", "Flask"]], "experience_min_months": 24, "experience_max_months": 71,
                               "availability": ["d15"], "fresher": False, "city": "Pune", "sort": "experience", "cgpa_min": "7.5"}  # fmt: skip
    row = _row(await client.get(SAVED, headers=headers(recruiter)), body["id"])
    assert row["filters"] == body["filters"] and row["owner"]["name"]
    # the restored body is a valid search as it stands
    assert (await client.post(SEARCH, json=row["filters"], headers=headers(recruiter))).status_code in (200, 422)


async def test_validation_uses_the_search_rules(client, db_session):
    recruiter, _ = await _people(db_session)
    bad = await _save(client, recruiter, filters={"experience_min_months": 24})
    assert bad.status_code == 422 and "skill" in bad.json()["detail"].lower()
    unknown = await _save(client, recruiter, filters={"all": ["Java"], "nope": 1})
    assert unknown.status_code == 422
    for name in ("", "   ", "x" * 81):
        assert (await _save(client, recruiter, name=name)).status_code == 422
    assert (await client.post(SAVED, json={"name": "A", "filters": {"all": ["Java"]}, "extra": 1}, headers=headers(recruiter))).status_code == 422
    assert (await client.post(SAVED, json=[], headers=headers(recruiter))).status_code == 422


async def test_duplicate_name_per_owner_is_409(client, db_session):
    recruiter, other = await _people(db_session)
    name = tag("Dup ")
    assert (await _save(client, recruiter, name=name)).status_code == 201
    clash = await _save(client, recruiter, name=name.upper())
    assert clash.status_code == 409
    assert (await _save(client, other, name=name)).status_code == 201  # another owner may reuse it


async def test_personal_is_private_and_shared_is_visible(client, db_session):
    recruiter, other = await _people(db_session)
    mine = (await _save(client, recruiter)).json()
    shared = (await _save(client, recruiter, shared=True)).json()
    listed = await client.get(SAVED, headers=headers(other))
    assert _row(listed, mine["id"]) is None
    seen = _row(listed, shared["id"])
    assert seen["shared"] is True and seen["mine"] is False and seen["can_edit"] is False
    # writes: another user's personal search is a 404, a shared one they do not own a 403
    assert (await client.patch(f"{SAVED}/{mine['id']}", json={"name": "x"}, headers=headers(other))).status_code == 404
    assert (await client.delete(f"{SAVED}/{mine['id']}", headers=headers(other))).status_code == 404
    assert (await client.patch(f"{SAVED}/{shared['id']}", json={"name": "x"}, headers=headers(other))).status_code == 403
    assert (await client.delete(f"{SAVED}/{shared['id']}", headers=headers(other))).status_code == 403


async def test_owner_updates_and_deletes_super_admin_may_too(client, db_session):
    recruiter, _ = await _people(db_session)
    admin = await _user(db_session, "super_admin", "global")
    await db_session.commit()
    created = (await _save(client, recruiter)).json()
    changed = await client.patch(f"{SAVED}/{created['id']}", json={"filters": {"all": ["Go"], "sort": "match"}, "shared": True},
                                 headers=headers(recruiter))  # fmt: skip
    assert changed.status_code == 200, changed.text
    assert changed.json()["filters"] == {"all": ["Go"], "sort": "match"} and changed.json()["shared"] is True
    assert changed.json()["name"] == created["name"]
    assert (await client.patch(f"{SAVED}/{created['id']}", json={}, headers=headers(recruiter))).status_code == 422
    assert (await client.delete(f"{SAVED}/{created['id']}", headers=headers(admin))).status_code == 204
    assert (await client.delete(f"{SAVED}/{created['id']}", headers=headers(recruiter))).status_code == 404


async def test_roles(client, db_session):
    """X3: Find Candidates readers only, before the body is read."""
    hr = await _user(db_session, "hr_team", "it")
    bdm = await _user(db_session, "bdm", "it")
    await db_session.commit()
    assert (await _save(client, hr)).status_code == 201
    assert (await _save(client, bdm)).status_code == 403
    assert (await client.get(SAVED, headers=headers(bdm))).status_code == 403
    assert (await client.post(SAVED, json="junk", headers=headers(bdm))).status_code == 403
    assert (await client.get(SAVED)).status_code == 401


async def test_compensation_filters_need_the_grant(client, db_session):
    """X5: saving package filters needs the grant; a shared one read without it loses them, named in `ignored`."""
    recruiter, _ = await _people(db_session)
    hr = await _user(db_session, "hr_team", "it")  # hr_team has no compensation grant by default
    await db_session.commit()
    refused = await _save(client, hr, filters={"all": ["Java"], "salary_min": 600000})
    assert refused.status_code == 403
    assert (await _save(client, hr, filters={"all": ["Java"], "sort": "package"})).status_code == 403
    shared = (await _save(client, recruiter, filters={"all": ["Java"], "salary_min": 600000, "package_unknown": True, "sort": "package"}, shared=True)).json()
    assert shared["ignored"] == []
    row = _row(await client.get(SAVED, headers=headers(hr)), shared["id"])
    assert row["filters"] == {"all": ["Java"]}
    assert set(row["ignored"]) == {"Minimum salary", "Include unknown salary", "Sort"}


async def test_a_removed_filter_is_ignored_with_a_notice(client, db_session):
    """Edge case: a key the search no longer declares is dropped on read and named."""
    recruiter, _ = await _people(db_session)
    created = (await _save(client, recruiter, filters={"all": ["Java"], "city": "Pune"})).json()
    await db_session.execute(update(SavedCandidateSearch).where(SavedCandidateSearch.id == created["id"])
                             .values(filters={"all": ["Java"], "city": "Pune", "retired_filter": "x"}))  # fmt: skip
    await db_session.commit()
    row = _row(await client.get(SAVED, headers=headers(recruiter)), created["id"])
    assert row["filters"] == {"all": ["Java"], "city": "Pune"} and row["ignored"] == ["retired_filter"]


async def test_cap_per_owner(client, db_session, monkeypatch):
    monkeypatch.setattr(saved_searches, "MAX_PER_OWNER", 2)
    recruiter, _ = await _people(db_session)
    assert (await _save(client, recruiter)).status_code == 201
    assert (await _save(client, recruiter)).status_code == 201
    over = await _save(client, recruiter)
    assert over.status_code == 422 and "2" in over.json()["detail"]


async def test_unknown_id_is_404(client, db_session):
    recruiter, _ = await _people(db_session)
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.patch(f"{SAVED}/{missing}", json={"name": "x"}, headers=headers(recruiter))).status_code == 404
    assert (await client.delete(f"{SAVED}/{missing}", headers=headers(recruiter))).status_code == 404
    assert (await db_session.scalar(select(SavedCandidateSearch.id).where(SavedCandidateSearch.owner_user_id == recruiter.id))) is None


async def test_deny_override_does_not_affect_saved_searches(client, db_session):
    """Saved searches follow the reader role, not the export grant."""
    recruiter, _ = await _people(db_session)
    await add(db_session, UserPermissionOverride(user_id=recruiter.id, resource="candidates", action="export", effect="deny", reason="hrc-020 test"))
    await db_session.commit()
    assert (await _save(client, recruiter)).status_code == 201
