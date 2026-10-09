"""rec-014 -- resume full-text search on Find Candidates (spec §1, §3-§4; DEC-SCOPE-152 FT1-FT9): the current resume's extracted text,
matched with websearch_to_tsquery('english'), combined with rec-013's skill chips and filters, ranked, with ts_headline snippets. The
shared test database is never truncated, so every test searches for its own unique word (the World tag)."""

import time
import uuid

import pytest
from sqlalchemy import event, insert, select

from app.core.database import engine
from app.models import Candidate, CandidateResume, RecCandidateSource
from app.schemas import CandidateSearch
from app.services import candidate_search
from tests.rec001_helpers import as_role, make_recruiter
from tests.test_rec_013_find_candidates import SEARCH, World, _ids, _search, _world


async def _resume(w: World, candidate, text: str | None, version: int = 1) -> CandidateResume:
    resume = CandidateResume(
        candidate_id=candidate.id, version=version, storage_key=f"candidate-resumes/{uuid.uuid4().hex}", content_type="application/pdf",
        size_bytes=10, uploaded_by_user_id=w.actor.id, extracted_text=text,
    )
    w.db.add(resume)
    await w.db.commit()
    return resume


def _word(w: World) -> str:
    """A word only this test's resumes contain (letters, so the English parser keeps it as one token)."""
    return "zq" + "".join(chr(ord("a") + int(c, 16) % 26) for c in w.tag)


# --- AC1: words in the resume, even when no skill was extracted -------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resume_words_find_a_candidate_without_the_skill(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    hit = await w.candidate()
    await _resume(w, hit, f"{tag} engineer. Java and Spring Boot, building Microservices on Kubernetes.")
    partial = await w.candidate()
    await _resume(w, partial, f"{tag} engineer. Java and Spring Boot monoliths.")
    response = await _search(client, text=f"{tag} Java Spring Boot Microservices")
    assert _ids(response) == {str(hit.id)}
    body = response.json()
    assert body["notice"] is None and body["terms"] == []
    # stemming: the singular finds the plural
    assert _ids(await _search(client, text=f"{tag} microservice")) == {str(hit.id)}


# --- AC2: text and a skill chip narrow each other ---------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_text_with_a_skill_filter_narrows(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    java = await w.skill("Java")
    both = await w.candidate(java)
    await _resume(w, both, f"{tag} AWS Certified Solutions Architect")
    text_only = await w.candidate()
    await _resume(w, text_only, f"{tag} AWS Certified Solutions Architect")
    await w.candidate(java)  # the skill, no resume
    assert _ids(await _search(client, text=f'{tag} "AWS Certified"')) == {str(both.id), str(text_only.id)}  # a certification phrase
    narrowed = await _search(client, text=f'{tag} "AWS Certified"', all=[java.name])
    assert _ids(narrowed) == {str(both.id)}
    for facet in narrowed.json()["facets"].values():
        assert sum(f["count"] for f in facet) == narrowed.json()["total"] == 1


# --- FT3: only stop words -----------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_stop_words_is_an_empty_result_with_a_notice(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    await w.candidate(java)
    response = await _search(client, text="the and of", all=[java.name])
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == [] and body["total"] == 0 and "common words" in body["notice"]
    assert all(f["count"] == 0 for facet in body["facets"].values() for f in facet)


# --- FT1 / FT7: the current resume only; no text, no match -------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_only_the_current_resume_with_text_is_searched(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    moved_on = await w.candidate()
    await _resume(w, moved_on, f"{tag} Cobol mainframe", version=1)
    await _resume(w, moved_on, "Python data engineer", version=2)
    scanned = await w.candidate()
    await _resume(w, scanned, "")
    unextracted = await w.candidate()
    await _resume(w, unextracted, None)
    current = await w.candidate()
    await _resume(w, current, "old", version=1)
    await _resume(w, current, f"{tag} Cobol developer", version=2)
    assert _ids(await _search(client, text=f"{tag} cobol")) == {str(current.id)}


@pytest.mark.asyncio
async def test_pool_and_archive_rules_still_apply(client, db_session):
    from tests.rec001_helpers import make_user

    w = await _world(client, db_session)
    tag = _word(w)
    student = await make_user(db_session, "it_student", "it")
    hidden = await w.candidate(user_id=student.id, opted_in=False)
    await _resume(w, hidden, f"{tag} Rust")
    archived = await w.candidate(archived=True)
    await _resume(w, archived, f"{tag} Rust")
    shown = await w.candidate()
    await _resume(w, shown, f"{tag} Rust")
    assert _ids(await _search(client, text=f"{tag} rust")) == {str(shown.id)}


# --- FT5 / FT6: relevance order and snippets ---------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_more_relevant_resumes_come_first_and_carry_a_highlighted_snippet(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    strong = await w.candidate()  # older, but the hits sit together
    await _resume(w, strong, f"{tag} Kafka Kafka streaming with Kafka Connect")
    weak = await w.candidate()  # newest first would put this one first
    await _resume(w, weak, f"{tag} once used Kafka. " + "Other unrelated work on reports and dashboards. " * 30)
    body = (await _search(client, text=f"{tag} kafka")).json()
    assert [item["id"] for item in body["items"]] == [str(strong.id), str(weak.id)]
    snippet = body["items"][0]["snippet"]
    assert any(s["hit"] and s["text"].lower() == "kafka" for s in snippet)
    assert "".join(s["text"] for s in snippet).lower().startswith(tag)
    long = body["items"][1]["snippet"]
    assert len("".join(s["text"] for s in long)) <= 301  # the cap plus its ellipsis
    assert all(set(s) == {"text", "hit"} for s in long)


@pytest.mark.asyncio
async def test_without_text_the_snippet_is_null_and_order_is_newest_first(client, db_session):
    w = await _world(client, db_session)
    java = await w.skill("Java")
    old = await w.candidate(java)
    await _resume(w, old, "Java Java Java")
    new = await w.candidate(java)
    body = (await _search(client, all=[java.name])).json()
    assert [item["id"] for item in body["items"]] == [str(new.id), str(old.id)]
    assert all(item["snippet"] is None for item in body["items"]) and body["notice"] is None


@pytest.mark.asyncio
async def test_a_snippet_is_plain_text_segments(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    c = await w.candidate()
    await _resume(w, c, f"{tag} <script>alert(1)</script> Golang developer")
    snippet = (await _search(client, text=f"{tag} golang")).json()["items"][0]["snippet"]
    joined = "".join(s["text"] for s in snippet)
    # ts_headline drops tags; the server adds no markup of its own (no <b>), and the stray markers are gone
    assert "<" not in joined and "alert(1)" in joined and "" not in joined and "" not in joined
    assert [s["text"] for s in snippet if s["hit"]] == [tag, "Golang"]


# --- FT4: 422s -----------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("body, needle", [
    ({}, "at least one skill or some resume search text"),
    ({"text": "   "}, "at least one skill or some resume search text"),
    ({"text": "x" * 201}, "200"),
    ({"text": "java\x01"}, "invalid"),
    ({"text": 5}, ""),
])
async def test_bad_text_is_422(client, db_session, body, needle):
    await _world(client, db_session)
    response = await client.post(SEARCH, json=body)
    assert response.status_code == 422, response.text
    assert needle.lower() in str(response.json()["detail"]).lower()


# --- FT9: roles ------------------------------------------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_hr_team_reads_snippets_and_an_employer_is_refused(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    c = await w.candidate()
    await _resume(w, c, f"{tag} Terraform")
    await as_role(client, db_session, "hr_team", "it")
    assert _ids(await _search(client, text=f"{tag} terraform")) == {str(c.id)}
    await as_role(client, db_session, "employer", "it")
    assert (await _search(client, text=f"{tag} terraform")).status_code == 403


# --- performance: a skill-only search runs rec-013's queries; text adds two ---------------------------------------------------------
@pytest.mark.asyncio
async def test_text_adds_exactly_two_queries(client, db_session):
    w = await _world(client, db_session)
    tag = _word(w)
    java = await w.skill("Java")
    for _ in range(3):
        await _resume(w, await w.candidate(java), f"{tag} Java")
    statements: list[str] = []
    listener = lambda *args: statements.append(args[2])  # noqa: E731
    event.listen(engine.sync_engine, "before_cursor_execute", listener)
    try:
        statements.clear()
        assert (await _search(client, all=[java.name])).json()["total"] == 3
        skills_only = len([s for s in statements if s.lstrip().upper().startswith("SELECT")])
        statements.clear()
        assert (await _search(client, all=[java.name], text=f"{tag} java")).json()["total"] == 3
        assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) == skills_only + 2
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", listener)


@pytest.mark.asyncio
async def test_ten_thousand_resumes_search_within_budget(db_session):
    """10k pool candidates, each with a two-version resume history, written in a rolled-back transaction; a text search with snippets
    (the GIN index, the current-version check, the rank and ts_headline on the page) runs in under 2 s."""
    actor = await make_recruiter(db_session)
    source = await db_session.scalar(select(RecCandidateSource.id).where(RecCandidateSource.name == "Referral"))
    tag = "zq" + "".join(chr(ord("a") + int(c, 16) % 26) for c in uuid.uuid4().hex[:8])
    words = ("Kafka", "Spring", "Kubernetes", "Terraform", "React")
    try:
        people = [
            {"id": uuid.uuid4(), "candidate_code": f"R{tag[2:5]}{i:08d}", "name": f"Perf {i}", "email": f"r{tag}{i}@example.com",
             "source_id": source, "created_by_user_id": actor.id, "preferred_locations": []}
            for i in range(10_000)
        ]
        await db_session.execute(insert(Candidate), people)
        filler = "Delivered projects, led teams and wrote documentation for many clients across banking and retail. " * 20
        resumes = [
            {"id": uuid.uuid4(), "candidate_id": p["id"], "version": v, "storage_key": f"candidate-resumes/{n}-{v}",
             "content_type": "application/pdf", "size_bytes": 10, "uploaded_by_user_id": actor.id,
             "extracted_text": f"{tag} {words[(n + v) % 5]} engineer. {filler}"}
            for n, p in enumerate(people) for v in (1, 2)
        ]
        await db_session.execute(insert(CandidateResume), resumes)
        body = CandidateSearch(text=f"{tag} kafka engineer")
        await candidate_search.search(db_session, body, limit=50, offset=0)  # warm: the rows were just written
        started = time.perf_counter()
        result = await candidate_search.search(db_session, body, limit=50, offset=0)
        elapsed = time.perf_counter() - started
        assert result["total"] == 2000 and len(result["items"]) == 50 and all(item["snippet"] for item in result["items"])
        assert elapsed < 2.0, f"search took {elapsed:.2f}s"
    finally:
        await db_session.rollback()
