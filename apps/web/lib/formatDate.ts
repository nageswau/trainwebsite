// Date display shared by server and client components. It lives here, not in SchoolChildOverview.tsx, because that file imports `serverApi`
// (`next/headers`), so a "use client" component importing from it fails `next build`. Import it from here.

// The School calendar (DEC-SCOPE-027 D10). Pass it when a server-rendered time must read the same on the server (UTC) and in the
// browser -- without a zone each side formats in its own and React reports hydration error #418 (QA-022-06).
export const SCHOOL_TIME_ZONE = "Asia/Kolkata";

export function formatDate(value: string | null | undefined, withTime = false, timeZone?: string): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}), ...(timeZone ? { timeZone } : {}) });
}

// A timestamp with its time of day in `timeZone`. `label` appends the zone's name for a time people act on (a session start, an
// event); a missing or unparseable value is never labelled.
export function formatDateTimeIn(value: string | null | undefined, timeZone: string, label = false): string {
  const text = formatDate(value, true, timeZone);
  return label && value && text !== value ? `${text} ${zoneLabel(value, timeZone)}` : text;
}

// A school portal timestamp in India time (D10); `label` adds "IST". Record timestamps (created, decided) stay unlabelled.
export function formatSchoolDateTime(value: string | null | undefined, label = false): string {
  return formatDateTimeIn(value, SCHOOL_TIME_ZONE, label);
}

// A calendar date (YYYY-MM-DD: birth dates, due dates, deadlines, session days) has no time of day. It parses as UTC midnight, so it is
// formatted in UTC: the same day for every viewer and on the server (a zone west of UTC would otherwise show the day before).
export function formatCalendarDate(value: string | null | undefined): string {
  return formatDate(value, false, "UTC");
}

// Short zone label for a scheduled time. India reads "IST" (the en-US name would be "GMT+5:30"); other zones use the en-US short name,
// which tracks daylight saving ("EDT"/"EST").
export function zoneLabel(value: string, timeZone: string): string {
  if (timeZone === "Asia/Kolkata" || timeZone === "Asia/Calcutta") return "IST";
  const parts = new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "short" }).formatToParts(new Date(value));
  return parts.find((p) => p.type === "timeZoneName")?.value ?? timeZone;
}
