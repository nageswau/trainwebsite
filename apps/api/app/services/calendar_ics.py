"""ccrm-038 (DEC-SCOPE-273 CA2, CA5): RFC 5545 text for the appointment invites and the counselor's feed, standard library only.

Every text value is escaped and its CR/LF become `\\n`, so no value can start a property of its own; lines are folded at 75 octets."""

from datetime import UTC, date, datetime, timedelta

PRODID = "-//EduSphere//Counselor CRM//EN"


def _text(value: str) -> str:
    value = value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return value.replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")


def _fold(line: str) -> list[str]:
    """Split before 75 octets (74 after the first line, which starts with a space), never inside a UTF-8 character."""
    out, current, limit = [], "", 75
    for char in line:
        if len((current + char).encode()) > limit:
            out.append(current)
            current, limit = " ", 75
        current += char
    return [*out, current]


def _stamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _lines(uid: str, sequence: int, dates: list[str], summary: str, location: str | None, description: str | None, status: str | None) -> list[str]:
    lines = ["BEGIN:VEVENT", f"UID:{_text(uid)}", f"DTSTAMP:{_stamp(datetime.now(UTC))}", f"SEQUENCE:{sequence}", *dates, f"SUMMARY:{_text(summary)}"]
    if location:
        lines.append(f"LOCATION:{_text(location)}")
    if description:
        lines.append(f"DESCRIPTION:{_text(description)}")
    if status:
        lines.append(f"STATUS:{status}")
    return [*lines, "END:VEVENT"]


def event(*, uid: str, sequence: int, start: datetime, end: datetime, summary: str, location: str | None = None, description: str | None = None,
          status: str | None = None, organizer: str | None = None) -> list[str]:
    lines = _lines(uid, sequence, [f"DTSTART:{_stamp(start)}", f"DTEND:{_stamp(end)}"], summary, location, description, status)
    if organizer:  # iTIP: an invite (METHOD:REQUEST/CANCEL) names its organizer
        lines.insert(-1, f"ORGANIZER;CN=EduSphere:mailto:{organizer}")
    return lines


def all_day_event(*, uid: str, day: date, summary: str, location: str | None = None, description: str | None = None) -> list[str]:
    dates = [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
    return _lines(uid, 0, dates, summary, location, description, None)


def calendar(events: list[list[str]], method: str | None = None, name: str | None = None) -> str:
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", f"PRODID:{PRODID}", "CALSCALE:GREGORIAN"]
    if method:
        lines.append(f"METHOD:{method}")
    if name:
        lines.append(f"X-WR-CALNAME:{_text(name)}")
    lines += [line for item in events for line in item]
    lines.append("END:VCALENDAR")
    return "".join(part + "\r\n" for line in lines for part in _fold(line))

