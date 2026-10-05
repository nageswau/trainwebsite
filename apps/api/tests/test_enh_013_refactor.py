"""ENH-013 -- behavior-preserving refactors (docs/superpowers/specs/2026-09-23-enh-013a-student-360-view-design.md §4, §7)."""
import uuid

import pytest
from fastapi import HTTPException

from tests.enh005_helpers import mk_school, mk_staff, mk_user


async def _denied(loader, db, user, student_id) -> tuple[int, str]:
    with pytest.raises(HTTPException) as exc:
        await loader(db, user, student_id)
    return exc.value.status_code, exc.value.detail


@pytest.mark.asyncio
async def test_reader_loader_allows_the_seven_roles_and_keeps_existing_denials(db_session):
    from app.api.schools import _load_student_for_reader

    a = await mk_school(db_session, label="E13-LoaderA")
    b = await mk_school(db_session, label="E13-LoaderB", admin=a["admin"])
    kid = a["students"][0]
    for who in (a["coordinator"], a["principal"], a["teacher"], a["parent"]):
        assert (await _load_student_for_reader(db_session, who, kid.id)).id == kid.id, who.role
    for role in ("academic_team", "career_counselor", "psychometric_team"):
        member = await mk_staff(db_session, a["school"], a["admin"], role=role)
        assert (await _load_student_for_reader(db_session, member, kid.id)).id == kid.id, role
        outsider = await mk_staff(db_session, b["school"], a["admin"], role=role)
        assert await _denied(_load_student_for_reader, db_session, outsider, kid.id) == (403, "This student is at a school outside your own portfolio")
    assert await _denied(_load_student_for_reader, db_session, b["coordinator"], kid.id) == (403, "This student is at a different institution")
    admin = await mk_user(db_session, role="overseas_admin", name="Admin")
    assert await _denied(_load_student_for_reader, db_session, admin, kid.id) == (403, "School role required")
    assert (await _denied(_load_student_for_reader, db_session, a["coordinator"], uuid.uuid4()))[0] == 404


@pytest.mark.asyncio
async def test_payload_helpers_return_exactly_what_the_existing_routes_return(client, db_session):
    from fastapi.encoders import jsonable_encoder

    from app.api.portfolio import portfolio_payload
    from app.api.schools import _grade_history_rows, _overview_payload
    from tests.enh005_helpers import login

    a = await mk_school(db_session, label="E13-Payload")
    kid = a["students"][0]
    await login(client, a["coordinator"].email)
    base = f"/api/v1/school/students/{kid.id}"
    overview = (await client.get(f"{base}/overview")).json()
    portfolio = (await client.get(f"{base}/portfolio")).json()
    history = (await client.get(f"{base}/grade-history")).json()["history"]
    assert jsonable_encoder(await _overview_payload(db_session, kid)) == overview
    assert jsonable_encoder(await portfolio_payload(db_session, a["coordinator"], kid)) == portfolio
    assert jsonable_encoder(await _grade_history_rows(db_session, kid)) == history


def test_portfolio_module_no_longer_defines_its_own_role_set_or_loader():
    from app.api import portfolio

    assert not hasattr(portfolio, "PORTFOLIO_SCOPED_ROLES")
    assert not hasattr(portfolio, "_load_portfolio_student")
