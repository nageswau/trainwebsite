// Date display shared by server and client components. It lives here, not in SchoolChildOverview.tsx, because that file imports `serverApi`
// (`next/headers`), so a "use client" component importing from it fails `next build`. SchoolChildOverview re-exports it, so existing imports work.
export function formatDate(value: string | null | undefined, withTime = false): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}) });
}
