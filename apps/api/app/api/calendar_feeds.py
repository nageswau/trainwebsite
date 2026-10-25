"""ccrm-038 (DEC-SCOPE-271 CA4-CA7; API §12FX): the overseas counselor's iCal feed.

- /counselor/calendar-feed: the session user's own feed -- status, create/regenerate (the URL is in this answer only), revoke.
- /calendar/feeds/{token}.ics: the feed itself, without a session (the token is the credential)."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import User
from app.services import calendar_feeds as svc

manage_router = APIRouter(prefix="/counselor/calendar-feed", tags=["calendar-feeds"])
feed_router = APIRouter(prefix="/calendar/feeds", tags=["calendar-feeds"])

REFUSED = "Only an overseas counselor has a calendar feed"
NOT_FOUND = "Calendar feed not found"


def _counselor(user: User) -> User:
    if not svc.is_overseas_counselor(user):
        raise HTTPException(403, REFUSED)
    return user


@manage_router.get("")
async def status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return svc.out(await svc.current(db, _counselor(user)))


@manage_router.post("", status_code=201)
async def issue(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await svc.issue(db, _counselor(user))


@manage_router.delete("", status_code=204)
async def revoke(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.revoke(db, _counselor(user))
    return Response(status_code=204)


@feed_router.get("/{token}.ics")
async def feed(token: str, db: AsyncSession = Depends(get_db)):
    counselor = await svc.owner(db, token)
    if counselor is None:
        raise HTTPException(404, NOT_FOUND)
    return Response(await svc.body(db, counselor), media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, no-store", "Content-Disposition": 'inline; filename="edusphere.ics"'})
