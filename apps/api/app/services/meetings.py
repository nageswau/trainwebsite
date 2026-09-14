import asyncio
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

import httpx

from app.core.config import settings


class MeetingProviderError(RuntimeError):
    pass


@dataclass
class MeetingResult:
    provider: str
    meeting_url: str | None
    host_url: str | None = None
    provider_event_id: str | None = None
    provider_meeting_id: str | None = None
    sync_status: str = "created"


async def _google_access_token() -> str:
    if not all((settings.google_client_id, settings.google_client_secret, settings.google_refresh_token)):
        raise MeetingProviderError("Google Meet is not configured. Add Google OAuth credentials and a refresh token.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "refresh_token": settings.google_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()["access_token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise MeetingProviderError("Google OAuth token refresh failed.") from exc


async def _zoho_access_token() -> str:
    if not all((settings.zoho_client_id, settings.zoho_client_secret, settings.zoho_refresh_token)):
        raise MeetingProviderError("Zoho Meeting is not configured. Add Zoho OAuth credentials and a refresh token.")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{settings.zoho_accounts_url.rstrip('/')}/oauth/v2/token",
                data={
                    "client_id": settings.zoho_client_id,
                    "client_secret": settings.zoho_client_secret,
                    "refresh_token": settings.zoho_refresh_token,
                    "grant_type": "refresh_token",
                },
            )
            response.raise_for_status()
            return response.json()["access_token"]
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise MeetingProviderError("Zoho OAuth token refresh failed.") from exc


def _google_join_url(payload: dict) -> str | None:
    if payload.get("hangoutLink"):
        return payload["hangoutLink"]
    for point in payload.get("conferenceData", {}).get("entryPoints", []):
        if point.get("entryPointType") == "video":
            return point.get("uri")
    return None


async def create_google_meet(*, title: str, agenda: str, starts_at: datetime, ends_at: datetime, attendee_emails: list[str]) -> MeetingResult:
    token = await _google_access_token()
    body = {
        "summary": title,
        "description": agenda,
        "start": {"dateTime": starts_at.isoformat()},
        "end": {"dateTime": ends_at.isoformat()},
        "attendees": [{"email": email} for email in attendee_emails],
        "conferenceData": {
            "createRequest": {
                "requestId": uuid4().hex,
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
    }
    calendar_id = settings.google_calendar_id or "primary"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
            params={"conferenceDataVersion": 1, "sendUpdates": "all"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
        if response.status_code >= 400:
            raise MeetingProviderError(f"Google Meet creation failed ({response.status_code}).")
        data = response.json()
        event_id = data.get("id")
        for _ in range(4):
            if _google_join_url(data) or not event_id:
                break
            await asyncio.sleep(0.5)
            poll = await client.get(
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if poll.status_code >= 400:
                break
            data = poll.json()
    return MeetingResult(
        provider="google_meet",
        meeting_url=_google_join_url(data),
        host_url=data.get("htmlLink"),
        provider_event_id=data.get("id"),
        provider_meeting_id=data.get("conferenceData", {}).get("conferenceId"),
        sync_status="created" if _google_join_url(data) else "pending",
    )


async def create_zoho_meeting(*, title: str, agenda: str, starts_at: datetime, ends_at: datetime, attendee_emails: list[str]) -> MeetingResult:
    if not settings.zoho_organization_id or not settings.zoho_presenter_id:
        raise MeetingProviderError("Zoho Meeting organization and presenter IDs are not configured.")
    token = await _zoho_access_token()
    duration_ms = max(60_000, int((ends_at - starts_at).total_seconds() * 1000))
    body = {
        "session": {
            "topic": title,
            "agenda": agenda,
            "presenter": settings.zoho_presenter_id,
            "startTime": starts_at.strftime("%b %d, %Y %I:%M %p"),
            "duration": duration_ms,
            "timezone": "Asia/Calcutta",
            "participants": [{"email": email} for email in attendee_emails],
        }
    }
    url = f"{settings.zoho_meeting_base_url.rstrip('/')}/api/v2/{settings.zoho_organization_id}/sessions.json"
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Zoho-oauthtoken {token}", "Content-Type": "application/json;charset=UTF-8"},
            json=body,
        )
        if response.status_code >= 400:
            raise MeetingProviderError(f"Zoho Meeting creation failed ({response.status_code}).")
        data = response.json().get("session", response.json())
    meeting_id = data.get("meetingKey") or data.get("sessionKey")
    return MeetingResult(
        provider="zoho_meeting",
        meeting_url=data.get("joinLink"),
        host_url=data.get("startLink") or data.get("meetingEmbedUrl"),
        provider_event_id=str(data.get("sysId")) if data.get("sysId") is not None else None,
        provider_meeting_id=str(meeting_id) if meeting_id is not None else None,
    )


async def create_provider_meeting(
    provider: str,
    *,
    title: str,
    agenda: str,
    starts_at: datetime,
    ends_at: datetime,
    attendee_emails: list[str],
    meeting_url: str | None = None,
) -> MeetingResult:
    if provider == "google_meet":
        return await create_google_meet(title=title, agenda=agenda, starts_at=starts_at, ends_at=ends_at, attendee_emails=attendee_emails)
    if provider == "zoho_meeting":
        return await create_zoho_meeting(title=title, agenda=agenda, starts_at=starts_at, ends_at=ends_at, attendee_emails=attendee_emails)
    if not meeting_url:
        raise MeetingProviderError("A meeting URL is required for the manual provider.")
    return MeetingResult(provider="manual", meeting_url=meeting_url, sync_status="manual")
