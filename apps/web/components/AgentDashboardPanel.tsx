import Link from "next/link";

import { accessUnavailable } from "./AccessUnavailable";
import { TableRegion, headingId, n } from "./AgentTableRegion";
import type { DateRange } from "@/lib/agentCommissionReport";
import { DASHBOARD_PAGE, dashboardUrl, formatMoney } from "@/lib/agentDashboard";
import { ApiError, serverApi } from "@/lib/api";
import type { AgentBreakdown, AgentDashboard, AgentStaffRow } from "@/lib/types";

// AGN-018 (DEC-SCOPE-062; spec §6.2): the agency KPI board. A server component that reads its own endpoint, so a failure here
// leaves the page's title, table and nav working. Reuses SchoolKpiBoard's tile markup and the .table-scroll region pattern
// (GlobalEducationStudentTable), so a keyboard user can scroll each table. Staff get their own scope: no commission, no staff table.
// nehn-038 (DEC-SCOPE-306): applications submitted, the visa outcome split, conversion, and a referral-date filter -- a plain GET
// form, so it works without script and the range stays in the address.
const NOTE = "Includes later stages and withdrawn applications";
const FIELD = { from: "Referred from", to: "Referred to" } as const;

type Tile = { label: string; value: string; link?: [text: string, href: string]; note?: string };

const percent = (value: number | null) => (value === null ? "—" : `${value}%`);

function Group({ title, tiles }: { title: string; tiles: Tile[] }) {
  return (
    <section aria-label={title} className="kpi-group">
      <h3>{title}</h3>
      <dl className="kpi-grid">
        {tiles.map((t) => (
          <div className="kpi-tile" key={t.label}>
            <dt>{t.label}</dt>
            <dd className="kpi-value">{t.value}</dd>
            {t.link && (
              <dd>
                <Link className="kpi-link" href={t.link[1]}>
                  {t.link[0]}
                </Link>
              </dd>
            )}
            {t.note && <dd className="kpi-note muted">{t.note}</dd>}
          </div>
        ))}
      </dl>
    </section>
  );
}

// nehn-038: the range filter. The server validates the range (422); a rejected one is shown as `error` with the form kept.
function RangeFilter({ range, error }: { range: DateRange; error?: string }) {
  const filtered = Boolean(range.from || range.to);
  return (
    <>
      {/* Browser QA38-01: no form-state restore on Back, so the inputs always show the range the figures were read for. */}
      <form method="get" action={DASHBOARD_PAGE} aria-label="Dashboard date range" className="actions" autoComplete="off">
        <div className="field">
          <label htmlFor="agent-dashboard-from">{FIELD.from}</label>
          <input id="agent-dashboard-from" name="from" type="date" defaultValue={range.from} aria-invalid={error ? true : undefined} />
        </div>
        <div className="field">
          <label htmlFor="agent-dashboard-to">{FIELD.to}</label>
          <input id="agent-dashboard-to" name="to" type="date" defaultValue={range.to} aria-invalid={error ? true : undefined} />
        </div>
        <button className="btn" type="submit">
          Apply
        </button>
        {filtered && (
          <Link className="btn secondary" href={DASHBOARD_PAGE}>
            Clear dates
          </Link>
        )}
      </form>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}

// The table's scroll region carries the name, so these sections stay unnamed (one landmark per table, not two).
function Breakdown({ title, data }: { title: string; data: AgentBreakdown }) {
  return (
    <section className="kpi-group">
      <h3 id={headingId(title)}>{title}</h3>
      {data.items.length === 0 ? (
        <p className="muted">No applications yet</p>
      ) : (
        <TableRegion title={title} head={["Name", "Applications"]}>
          {data.items.map((i) => (
            <tr key={i.label}>
              <th scope="row">{i.label}</th>
              <td>{n(i.count)}</td>
            </tr>
          ))}
          {data.other > 0 && (
            <tr>
              <th scope="row">Other</th>
              <td>{n(data.other)}</td>
            </tr>
          )}
        </TableRegion>
      )}
    </section>
  );
}

function StaffTable({ rows, unassigned }: { rows: AgentStaffRow[]; unassigned: number }) {
  const title = "Staff performance";
  return (
    <section className="kpi-group">
      <h3 id={headingId(title)}>{title}</h3>
      {rows.length === 0 ? (
        // Browser QA18-05: the note alone, not a header-only table; the unassigned count still shows, in words.
        <>
          <p className="muted">
            No staff yet — <Link href="/overseas/agent/team">add staff from Team</Link>
          </p>
          {unassigned > 0 && (
            <p className="muted">{unassigned === 1 ? "1 student is" : `${n(unassigned)} students are`} not assigned to anyone yet.</p>
          )}
        </>
      ) : (
        <TableRegion title={title} stack head={["Member", "Students", "Applications", "Offers", "Enrollments", "Conversions", "Conversion rate"]}>
          {rows.map((r) => (
            <tr key={r.code}>
              <th scope="row">
                {r.name} <span className="muted">{r.code}</span>
                {!r.active && (
                  <>
                    {" "}
                    <span className="badge">Deactivated</span>
                  </>
                )}
              </th>
              <td data-label="Students">{n(r.students)}</td>
              <td data-label="Applications">{n(r.applications)}</td>
              <td data-label="Offers">{n(r.offers)}</td>
              <td data-label="Enrollments">{n(r.enrollments)}</td>
              <td data-label="Conversions">{n(r.conversions)}</td>
              <td data-label="Conversion rate">{percent(r.conversion_rate)}</td>
            </tr>
          ))}
          <tr>
            <th scope="row">Unassigned</th>
            <td data-label="Students">{n(unassigned)}</td>
            <td colSpan={5} className="stack-empty" />
          </tr>
        </TableRegion>
      )}
      {/* AGN-019 (DEC-SCOPE-066 P7): below the table, so the heading keeps naming the table's region. */}
      <p>
        <Link className="kpi-link" href="/overseas/agent/performance">
          View staff performance
        </Link>
      </p>
    </section>
  );
}

const ANY_TIME: DateRange = { from: "", to: "" };

export function AgentDashboardBoard({ data, range = ANY_TIME }: { data: AgentDashboard; range?: DateRange }) {
  const period = range.from || range.to ? `Students referred ${range.from || "any time"} to ${range.to || "today"}` : "Students referred at any time";
  return (
    <div className="card agent-dashboard">
      <p className="muted">
        {data.scope === "agency" ? "Whole agency" : "Your assigned students"}
        {data.member_code && ` · Your code ${data.member_code}`}
      </p>
      <RangeFilter range={range} />
      <p className="muted">
        {period}. {data.commission ? "Pending documents, pending actions and commission" : "Pending documents and pending actions"} are current,
        whatever the dates.
      </p>
      <Group
        title="Students"
        tiles={[
          { label: "Total students", value: n(data.students), link: ["View students", "/overseas/agent/students"] },
          { label: "Pending actions", value: n(data.pending_actions), link: ["Open tasks", "/overseas/agent/tasks?view=open"] },
        ]}
      />
      <Group
        title="Pipeline"
        tiles={[
          { label: "Applications", value: n(data.applications), link: ["View applications", "/overseas/agent/applications"] },
          { label: "Applications submitted", value: n(data.applications_submitted), note: "Includes withdrawn applications" },
          { label: "Offers", value: n(data.offers), note: NOTE },
          { label: "Enrollments", value: n(data.enrollments), link: ["View enrolled", "/overseas/agent/applications?status=enrolled"] },
        ]}
      />
      <Group
        title="Visa outcomes"
        tiles={[
          { label: "Visa applications", value: n(data.visa_applications), note: NOTE },
          { label: "Visa decisions", value: n(data.visa_decisions), note: "Approved, refused or withdrawn" },
          { label: "Visa approvals", value: n(data.visa_approvals), note: NOTE },
          { label: "Visa refusals", value: n(data.visa_refusals) },
          { label: "Visa withdrawals", value: n(data.visa_withdrawals) },
        ]}
      />
      <Group
        title="Conversion"
        tiles={[
          { label: "Conversions", value: n(data.conversions), note: "Students with an enrolled application" },
          { label: "Conversion rate", value: percent(data.conversion_rate), note: "Conversions out of total students" },
        ]}
      />
      <Group
        title="Documents"
        tiles={[{ label: "Pending documents", value: n(data.pending_documents), link: ["Review pending", "/overseas/agent/documents?view=pending"] }]}
      />
      {data.commission && (
        <Group
          title="Commission"
          tiles={[
            { label: "Claimable commission", value: formatMoney(data.commission.claimable) },
            { label: "Claims", value: n(data.commission.claims) },
            { label: "Revenue", value: formatMoney(data.commission.revenue) },
          ]}
        />
      )}
      <Breakdown title="Applications by country" data={data.by_country} />
      <Breakdown title="Applications by university" data={data.by_university} />
      {data.staff && <StaffTable rows={data.staff} unassigned={data.unassigned_students ?? 0} />}
      {data.reports_available && (
        <p>
          <Link href="/overseas/agent/reports">View reports</Link>
        </p>
      )}
    </div>
  );
}

export function AgentDashboardSkeleton() {
  return (
    <div className="card agent-dashboard" aria-busy="true">
      <span className="visually-hidden">Loading dashboard figures</span>
      {[2, 4, 5, 2, 1].map((count, g) => (
        <div className="kpi-group" key={g} aria-hidden="true">
          <div className="kpi-grid">
            {Array.from({ length: count }, (_, i) => (
              <div className="kpi-tile kpi-skeleton" key={i} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default async function AgentDashboardPanel({ range = ANY_TIME }: { range?: DateRange } = {}) {
  let data: AgentDashboard;
  try {
    data = await serverApi<AgentDashboard>(dashboardUrl(range));
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return accessUnavailable(e, "/overseas/login");
    if (e instanceof ApiError && e.status === 422) {
      // The server's own message, in the form's words (the AGN-019 panel's mapping).
      const text = e.message.replace(/date_from/g, `'${FIELD.from}'`).replace(/date_to/g, `'${FIELD.to}'`);
      return (
        <div className="card agent-dashboard">
          <RangeFilter range={range} error={text} />
        </div>
      );
    }
    return (
      <div className="card agent-dashboard">
        <p className="form-error" role="alert">
          Dashboard figures are unavailable right now.
        </p>
        <p>
          <Link href={DASHBOARD_PAGE}>Try again</Link>
        </p>
      </div>
    );
  }
  return <AgentDashboardBoard data={data} range={range} />;
}
