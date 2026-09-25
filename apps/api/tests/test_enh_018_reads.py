import pytest
from enh005_helpers import login, mk_school, mk_user
from enh018_helpers import FEEDBACK, URL, mark, mk_activity

# ENH-018 spec §5.2-5.3 / AC5-AC6: the school's own list (coordinator, principal) and Edusphere management's cross-school list.
SCHOOL = "/api/v1/school/activity-feedback"
ADMIN = "/api/v1/overseas-admin/school-activity-feedback"


async def _submit(client, s, activity, **over):
    await login(client, s["coordinator"].email)
    response = await client.post(URL.format(aid=activity.id), json={**FEEDBACK, **over})
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------------------------------------ school list (Task 4)


@pytest.mark.asyncio
async def test_coordinator_sees_only_own_eligible_activities_with_participation_and_feedback(client, db_session):
    a = await mk_school(db_session, label="A", students=3)
    b = await mk_school(db_session, label="B")
    done = await mk_activity(db_session, a["school"], a["coordinator"], minutes=-120)
    awaiting = await mk_activity(db_session, a["school"], a["coordinator"], minutes=-60)
    await mk_activity(db_session, a["school"], a["coordinator"], minutes=60)  # future: not listed
    await mk_activity(db_session, a["school"], a["coordinator"], activity_type=None)  # untyped: not listed
    await mk_activity(db_session, b["school"], b["coordinator"])  # another school: not listed
    await mark(db_session, done, a["coordinator"], a["students"][:2], a["students"][2:])
    await _submit(client, a, done)
    body = (await client.get(SCHOOL)).json()
    assert body["total"] == 2 and [i["activity_id"] for i in body["items"]] == [str(awaiting.id), str(done.id)]
    by_id = {i["activity_id"]: i for i in body["items"]}
    assert by_id[str(done.id)]["participation"] == {"present": 2, "marked": 3}
    assert by_id[str(done.id)]["feedback"]["rating"] == 4 and by_id[str(done.id)]["activity_type"] == "career_seminar"
    assert by_id[str(awaiting.id)]["participation"] == {"present": 0, "marked": 0} and by_id[str(awaiting.id)]["feedback"] is None


@pytest.mark.asyncio
async def test_status_filter_and_paging(client, db_session):
    s = await mk_school(db_session, label="A")
    acts = [await mk_activity(db_session, s["school"], s["coordinator"], minutes=-10 * (i + 1)) for i in range(3)]
    await _submit(client, s, acts[0])
    awaiting = (await client.get(SCHOOL, params={"status": "awaiting"})).json()
    submitted = (await client.get(SCHOOL, params={"status": "submitted"})).json()
    assert awaiting["total"] == 2 and all(i["feedback"] is None for i in awaiting["items"])
    assert submitted["total"] == 1 and submitted["items"][0]["activity_id"] == str(acts[0].id)
    page = (await client.get(SCHOOL, params={"limit": 1, "offset": 1})).json()
    assert (page["total"], page["limit"], page["offset"], len(page["items"])) == (3, 1, 1, 1)
    assert page["items"][0]["activity_id"] == str(acts[1].id)
    for bad in ({"status": "nope"}, {"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert (await client.get(SCHOOL, params=bad)).status_code == 422


@pytest.mark.asyncio
async def test_principal_reads_own_school_but_cannot_submit(client, db_session):
    s = await mk_school(db_session, label="A")
    activity = await mk_activity(db_session, s["school"], s["coordinator"])
    other = await mk_activity(db_session, s["school"], s["coordinator"])
    await _submit(client, s, activity)
    await login(client, s["principal"].email)
    items = (await client.get(SCHOOL)).json()["items"]
    assert next(i for i in items if i["activity_id"] == str(activity.id))["feedback"]["feedback"] == FEEDBACK["feedback"]
    assert (await client.post(URL.format(aid=other.id), json=FEEDBACK)).status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["school_teacher", "school_parent", "career_counselor", "overseas_admin"])
async def test_other_roles_cannot_read_the_school_list(client, db_session, role):
    s = await mk_school(db_session, label="A")
    other = await mk_user(db_session, role=role, name=f"{role} user", school_id=s["school"].id, assigned_by=s["admin"])
    await db_session.commit()
    await login(client, other.email)
    assert (await client.get(SCHOOL)).status_code == 403


@pytest.mark.asyncio
async def test_unlinked_principal_is_403_not_500(client, db_session):
    s = await mk_school(db_session, label="A")
    orphan = await mk_user(db_session, role="school_principal", name="Unlinked Principal", assigned_by=s["admin"])
    await db_session.commit()
    await login(client, orphan.email)
    assert (await client.get(SCHOOL)).status_code == 403


@pytest.mark.asyncio
async def test_activity_id_narrows_the_list_to_that_one_activity_of_the_callers_school(client, db_session):
    """QA-018-09: the Activities page links to one activity's feedback; the list must be able to return just that row."""
    a = await mk_school(db_session, label="A")
    b = await mk_school(db_session, label="B")
    target = await mk_activity(db_session, a["school"], a["coordinator"], minutes=-30)
    await mk_activity(db_session, a["school"], a["coordinator"], minutes=-60)
    untyped = await mk_activity(db_session, a["school"], a["coordinator"], activity_type=None)
    theirs = await mk_activity(db_session, b["school"], b["coordinator"])
    await login(client, a["coordinator"].email)
    one = (await client.get(SCHOOL, params={"activity_id": str(target.id)})).json()
    assert (one["total"], [i["activity_id"] for i in one["items"]]) == (1, [str(target.id)])
    for other in (untyped.id, theirs.id, "00000000-0000-0000-0000-000000000000"):  # ineligible, another school's, unknown: all simply empty
        assert (await client.get(SCHOOL, params={"activity_id": str(other)})).json()["total"] == 0
    assert (await client.get(SCHOOL, params={"activity_id": "not-a-uuid"})).status_code == 422


@pytest.mark.asyncio
async def test_activities_list_says_which_activities_already_have_feedback(client, db_session):
    """QA-018-10: GET /school/activities gains an additive `feedback_submitted` flag; every existing field is unchanged."""
    s = await mk_school(db_session, label="A")
    done = await mk_activity(db_session, s["school"], s["coordinator"])
    open_ = await mk_activity(db_session, s["school"], s["coordinator"], minutes=-120)
    await _submit(client, s, done)
    rows = {r["id"]: r for r in (await client.get("/api/v1/school/activities")).json()}
    assert set(rows[str(done.id)]) == {"id", "title", "scheduled_at", "activity_type", "feedback_submitted"}
    assert rows[str(done.id)]["feedback_submitted"] is True and rows[str(open_.id)]["feedback_submitted"] is False


# ------------------------------------------------------------------------------------------------- admin list (Task 5)


@pytest.mark.asyncio
async def test_admin_reads_all_schools_newest_first_and_filters_by_school(client, db_session):
    a = await mk_school(db_session, label="A", students=1)
    b = await mk_school(db_session, label="B")
    act_a = await mk_activity(db_session, a["school"], a["coordinator"])
    act_b = await mk_activity(db_session, b["school"], b["coordinator"])
    await mark(db_session, act_a, a["coordinator"], a["students"])
    first = await _submit(client, a, act_a)
    second = await _submit(client, b, act_b, rating=2)
    await login(client, a["admin"].email)
    body = (await client.get(ADMIN, params={"limit": 100})).json()
    ids = [i["id"] for i in body["items"]]
    assert ids.index(second["id"]) < ids.index(first["id"])
    item = next(i for i in body["items"] if i["id"] == first["id"])
    assert item["school_name"] == a["school"].name and item["activity_title"] == act_a.title and item["activity_type"] == "career_seminar"
    assert item["participation"] == {"present": 1, "marked": 1} and item["submitted_by_name"] == a["coordinator"].full_name
    assert a["coordinator"].email not in str(item)
    only_b = (await client.get(ADMIN, params={"school_id": str(b["school"].id)})).json()
    assert only_b["total"] == 1 and only_b["items"][0]["id"] == second["id"]


@pytest.mark.asyncio
async def test_admin_filter_edge_cases(client, db_session):
    s = await mk_school(db_session, label="A")
    await login(client, s["admin"].email)
    empty = (await client.get(ADMIN, params={"school_id": "00000000-0000-0000-0000-000000000000"})).json()
    assert (empty["total"], empty["items"]) == (0, [])
    assert (await client.get(ADMIN, params={"school_id": "not-a-uuid"})).status_code == 422
    assert (await client.get(ADMIN, params={"limit": 101})).status_code == 422


@pytest.mark.asyncio
async def test_super_admin_reads_and_school_roles_are_refused(client, db_session):
    s = await mk_school(db_session, label="A")
    root = await mk_user(db_session, role="super_admin", name="Super Admin", division="global")
    await db_session.commit()
    await login(client, root.email)
    assert (await client.get(ADMIN)).status_code == 200
    for who in ("coordinator", "principal", "teacher", "parent"):
        await login(client, s[who].email)
        assert (await client.get(ADMIN)).status_code == 403
