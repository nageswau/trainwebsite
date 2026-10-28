import Link from "next/link";

import { accessUnavailable } from "./AccessUnavailable";
import { ApiError, serverApi } from "@/lib/api";
import type { CounselorDashboard, CounselorDashboardKey, CounselorDashboardSection } from "@/lib/types";

// ccrm-032 (DEC-SCOPE-277): the overseas counselor's action dashboard. A server component that reads its own endpoint, so a failure
// here leaves the quick search, the tiles and the application table working (the AGN-018 precedent). Sections sit in the BdmMyDay grid:
// side by side on wide screens, stacked on a phone. Each shows its full count and the first ten items, soonest first.
const URL = "/api/v1/counselor/dashboard";
const BASE = "/overseas/counselor";
const GRID = { display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", margin: "16px 0" } as const;
const LIST = { listStyle: "none", padding: 0, margin: "8px 0 0" } as const;
const ROW = { display: "flex", flexWrap: "wrap", gap: "4px 8px", alignItems: "baseline", padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)" } as const;
const HEAD = { margin: 0, fontSize: 17, display: "flex", gap: 8, alignItems: "center" } as const;
const WEEK = new Set<CounselorDashboardKey>(["follow_ups", "overdue_tasks"]); // ccrm-042: overdue + the next `follow_up_days` days

export const SECTIONS: { key: CounselorDashboardKey; title: string; empty: string; href: string }[] = [
  { key: "new_leads", title: "New and not-contacted leads", empty: "No new leads waiting.", href: `${BASE}/leads` },
  { key: "appointments_today", title: "Today's appointments", empty: "No appointments today.", href: `${BASE}/appointments` },
  { key: "calls_today", title: "Calls logged today", empty: "No calls logged today.", href: `${BASE}/leads` },
  { key: "follow_ups", title: "Follow-ups due", empty: "No follow-ups in the next 7 days.", href: `${BASE}/leads` },
  { key: "overdue_tasks", title: "Tasks due", empty: "No tasks due in the next 7 days.", href: `${BASE}/tasks` },
  { key: "no_next_action", title: "Leads without a next action", empty: "Every lead has a next action.", href: `${BASE}/leads` },
  { key: "pending_documents", title: "Students with pending documents", empty: "No documents pending.", href: `${BASE}/documents` },
  { key: "not_ready", title: "Applications not ready", empty: "No applications waiting on documents.", href: `${BASE}/applications` },
  { key: "awaiting_decision", title: "Submitted, awaiting decision", empty: "No applications awaiting a decision.", href: `${BASE}/applications` },
  { key: "offers_due", title: "Offer deadlines and conditions", empty: "Nothing due on offers.", href: `${BASE}/applications` },
  { key: "visa", title: "Visa appointments and decisions", empty: "No visa appointments or pending decisions.", href: `${BASE}/visa` },
  { key: "enrolment", title: "Enrolment and arrival", empty: "No enrolment or arrival to confirm.", href: `${BASE}/applications` },
];

/** A timestamp in India time (day, month, time); a calendar date as written (day, month, year). */
function when(value: string): string {
  return value.includes("T")
    ? new Date(value).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", hour: "numeric", minute: "2-digit" })
    : new Date(`${value}T00:00:00Z`).toLocaleDateString("en-IN", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" });
}

function Section({ id, title, note, empty, href, data }: { id: string; title: string; note?: string; empty: string; href: string; data: CounselorDashboardSection }) {
  const headingId = `counselor-dashboard-${id}`;
  return (
    <section className="panel" aria-labelledby={headingId}>
      <h3 id={headingId} style={HEAD}>
        {title} <span className="badge">{data.count.toLocaleString("en-IN")}</span>
      </h3>
      {note && <p className="muted" style={{ margin: "4px 0 0", fontSize: 13 }}>{note}</p>}
      {data.items.length === 0 ? (
        <p className="muted" style={{ margin: "8px 0 0" }}>{empty}</p>
      ) : (
        <ul style={LIST}>
          {data.items.map((i) => (
            <li key={i.id} style={ROW}>
              <Link href={i.href} style={{ fontWeight: 700, color: "var(--blue)", overflowWrap: "anywhere" }}>{i.label}</Link>
              {i.detail && <span className="muted" style={{ overflowWrap: "anywhere" }}>{i.detail}</span>}
              {i.date && <time dateTime={i.date} style={{ fontSize: 13 }}>{when(i.date)}</time>}
              {i.overdue && <span className="status error">Overdue</span>}
            </li>
          ))}
        </ul>
      )}
      {data.more && (
        <p style={{ margin: "8px 0 0" }}>
          <Link href={href} style={{ color: "var(--blue)" }}>View all {data.count.toLocaleString("en-IN")}</Link>
        </p>
      )}
    </section>
  );
}

export function CounselorDashboardBoard({ data }: { data: CounselorDashboard }) {
  return (
    <div style={GRID}>
      {SECTIONS.map((s) => (
        <Section
          key={s.key}
          id={s.key}
          title={s.title}
          note={
            s.key === "offers_due"
              ? `Offers, conditions and deposits due in the next ${data.window_days} days, or overdue.`
              : WEEK.has(s.key) ? `Overdue or due in the next ${data.follow_up_days} days, soonest first.` : undefined
          }
          empty={s.empty}
          href={s.href}
          data={data.sections[s.key]}
        />
      ))}
    </div>
  );
}

export function CounselorDashboardSkeleton() {
  return (
    <div style={GRID} aria-busy="true">
      <span className="visually-hidden">Loading dashboard sections</span>
      {SECTIONS.map((s) => (
        <div className="panel kpi-skeleton" key={s.key} aria-hidden="true" />
      ))}
    </div>
  );
}

export default async function CounselorDashboardPanel() {
  let data: CounselorDashboard;
  try {
    data = await serverApi<CounselorDashboard>(URL);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return accessUnavailable(e, "/overseas/login");
    return (
      <div className="card" style={{ margin: "16px 0" }}>
        <p className="form-error" role="alert">Dashboard sections are unavailable right now.</p>
        <p style={{ margin: 0 }}>
          <Link href={`${BASE}/dashboard`}>Try again</Link>
        </p>
      </div>
    );
  }
  return <CounselorDashboardBoard data={data} />;
}
