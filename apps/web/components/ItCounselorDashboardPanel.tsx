import Link from "next/link";

import { accessUnavailable } from "./AccessUnavailable";
import { Section } from "./CounselorDashboardPanel";
import ItCounselorDashboardFilters from "./ItCounselorDashboardFilters";
import { ApiError, serverApi } from "@/lib/api";
import type { ItCounselorDashboard, ItCounselorWidgetKey } from "@/lib/types";

// itc-030 (DEC-SCOPE-367): the IT counselor's dashboard and workspace -- and the IT Admin's over every counselor (the Owner filter).
// A server component reading its own endpoint, so a failure leaves the page's tiles and recent leads working (the ccrm-032 precedent).
// Figure tiles first (each jumps to its list), then the workspace lists, then the rest, in the ccrm-032 grid: side by side on wide
// screens, stacked on a phone. Every figure is the count of the list under it (AC1).
const URL = "/api/v1/counselor/it/dashboard";
const GRID = { display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 300px), 1fr))", margin: "16px 0" } as const;

export const WIDGETS: { key: ItCounselorWidgetKey; title: string; empty: string; tile: string }[] = [
  { key: "follow_ups", title: "Follow-ups due today and overdue", empty: "No follow-ups due today.", tile: "Follow-ups due" },
  { key: "ready_to_convert", title: "Ready to convert", empty: "No lead is ready to convert.", tile: "Ready to convert" },
  { key: "at_risk", title: "Students at risk", empty: "None of your students is at risk right now.", tile: "At-risk students" },
  { key: "pending_hr", title: "Pending HR actions", empty: "No HR review is waiting on a change.", tile: "Pending HR actions" },
  { key: "assigned_leads", title: "Assigned leads", empty: "No open leads.", tile: "Assigned leads" },
  { key: "conversions", title: "Conversions", empty: "No conversions yet.", tile: "Conversions" },
  { key: "enrolled_students", title: "Enrolled students", empty: "No student in an active enrolment.", tile: "Enrolled students" },
  { key: "outstanding_fees", title: "Outstanding fees", empty: "No fee is outstanding.", tile: "Outstanding fees" },
];

const inr = (value: number) => `INR ${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function note(key: ItCounselorWidgetKey, data: ItCounselorDashboard): string | undefined {
  const w = data.widgets[key];
  if (key === "follow_ups") return `${w.overdue ?? 0} overdue · soonest first.`;
  if (key === "ready_to_convert") return "Qualified up to Counselling Completed. Open the lead to convert it.";
  if (key === "outstanding_fees") return `${inr(w.total ?? 0)} due on active enrolments, largest first.`;
  if (key === "pending_hr") return "HR asked the student for an updated resume.";
  return undefined;
}

export function ItCounselorDashboardBoard({ data }: { data: ItCounselorDashboard }) {
  const pipeline = data.widgets.pipeline;
  return (
    <>
      {data.filters.stage && (
        <p className="muted" style={{ margin: "0 0 8px" }}>Status filters the lead widgets only: students have no lead status.</p>
      )}
      <div className="metric-grid">
        {WIDGETS.map((w) => (
          <a className="metric" key={w.key} href={`#counselor-dashboard-${w.key}`} style={{ color: "inherit", textDecoration: "none" }}>
            <span>{w.tile}</span>
            <strong>{w.key === "outstanding_fees" ? inr(data.widgets[w.key].total ?? 0) : data.widgets[w.key].count.toLocaleString("en-IN")}</strong>
          </a>
        ))}
      </div>
      <div style={GRID}>
        <section className="panel" aria-labelledby="counselor-dashboard-pipeline">
          <h3 id="counselor-dashboard-pipeline" style={{ margin: 0, fontSize: 17, display: "flex", gap: 8, alignItems: "center" }}>
            Counseling pipeline <span className="badge">{pipeline.count.toLocaleString("en-IN")}</span>
          </h3>
          {pipeline.count === 0 ? (
            <p className="muted" style={{ margin: "8px 0 0" }}>No open leads.</p>
          ) : (
            <table className="table" style={{ marginTop: 8, width: "100%" }}>
              <caption className="visually-hidden">Open leads by stage</caption>
              <tbody>
                {pipeline.stages.map((s) => (
                  <tr key={s.stage}><th scope="row" style={{ textAlign: "left", fontWeight: 400 }}>{s.label}</th><td style={{ textAlign: "right" }}>{s.count.toLocaleString("en-IN")}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
        {WIDGETS.map((w) => (
          <Section key={w.key} id={w.key} title={w.title} note={note(w.key, data)} empty={w.empty} data={data.widgets[w.key]} />
        ))}
      </div>
    </>
  );
}

export function ItCounselorDashboardSkeleton() {
  return (
    <div style={GRID} aria-busy="true">
      <span className="visually-hidden">Loading the dashboard</span>
      {WIDGETS.map((w) => <div className="panel kpi-skeleton" key={w.key} aria-hidden="true" />)}
    </div>
  );
}

/** `query` is the page's filter query string; a refused filter (422) falls back to the unfiltered board with the message. */
export default async function ItCounselorDashboardPanel({ query, path = "/it/counselor/dashboard" }: { query: string; path?: string }) {
  let data: ItCounselorDashboard;
  let error: string | null = null;
  try {
    data = await serverApi<ItCounselorDashboard>(query ? `${URL}?${query}` : URL).catch((e) => {
      if (query && e instanceof ApiError && e.status === 422) {
        error = e.message;
        return serverApi<ItCounselorDashboard>(URL);
      }
      throw e;
    });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return accessUnavailable(e, "/it/login");
    return (
      <div className="card" style={{ margin: "16px 0" }}>
        <p className="form-error" role="alert">The dashboard is unavailable right now.</p>
        <p style={{ margin: 0 }}><Link href={path}>Try again</Link></p>
      </div>
    );
  }
  return (
    <>
      <ItCounselorDashboardFilters filters={data.filters} options={data.options} error={error} />
      <ItCounselorDashboardBoard data={data} />
    </>
  );
}

