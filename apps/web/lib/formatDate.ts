// Date display shared by server and client components. It lives here, not in SchoolChildOverview.tsx, because that file imports `serverApi`
// (`next/headers`), so a "use client" component importing from it fails `next build`. SchoolChildOverview re-exports it, so existing imports work.

// The School calendar (DEC-SCOPE-027 D10). Pass it when a server-rendered time must read the same on the server (UTC) and in the
// browser -- without a zone each side formats in its own and React reports hydration error #418 (QA-022-06).
export const SCHOOL_TIME_ZONE = "Asia/Kolkata";

export function formatDate(value: string | null | undefined, withTime = false, timeZone?: string): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}), ...(timeZone ? { timeZone } : {}) });
}
