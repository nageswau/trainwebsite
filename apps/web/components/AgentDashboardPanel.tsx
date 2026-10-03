import Link from "next/link";

import { accessUnavailable } from "./AccessUnavailable";
import { DASHBOARD_URL, formatMoney } from "@/lib/agentDashboard";
import { ApiError, serverApi } from "@/lib/api";
import type { AgentBreakdown, AgentDashboard, AgentStaffRow } from "@/lib/types";

// AGN-018 (DEC-SCOPE-061; spec §6.2): the agency KPI board. A server component that reads its own endpoint, so a failure here
// leaves the page's title, table and nav working. Reuses SchoolKpiBoard's tile markup and the .table-scroll region pattern
// (GlobalEducationStudentTable), so a keyboard user can scroll each table. Staff get their own scope: no commission, no staff table.
const NOTE = "Includes later stages and withdrawn applications";
const n = (value: number) => value.toLocaleString("en-IN");

type Tile = { label: string; value: string; link?: [text: string, href: string]; note?: string };

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

// Browser QA18-06: the visible heading names its scroll region (aria-labelledby), so the title is not repeated in a hidden caption.
// QA18-04: `compact` drops the shared .table min-width, so a two-column table fits a phone instead of hiding its numbers.
const headingId = (title: string) => `agent-dashboard-${title.toLowerCase().replaceAll(" ", "-")}`;

// `stack`: on phones each row becomes a block and every number shows its column label (data-label) -- the staff table has too many
// columns to fit 320 px (QA18-04).
function TableRegion({ title, head, stack = false, children }: { title: string; head: string[]; stack?: boolean; children: React.ReactNode }) {
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-labelledby={headingId(title)}>
      <table className={stack ? "table compact stack" : "table compact"}>
        <thead>
          <tr>
            {head.map((h) => (
              <th scope="col" key={h}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
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
        <TableRegion title={title} stack head={["Member", "Students", "Applications", "Offers", "Enrollments"]}>
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
            </tr>
          ))}
          <tr>
            <th scope="row">Unassigned</th>
            <td data-label="Students">{n(unassigned)}</td>
            <td colSpan={3} className="stack-empty" />
          </tr>
        </TableRegion>
      )}
    </section>
  );
}

export function AgentDashboardBoard({ data }: { data: AgentDashboard }) {
  return (
    <div className="card agent-dashboard">
      <p className="muted">
        {data.scope === "agency" ? "Whole agency" : "Your assigned students"}
        {data.member_code && ` · Your code ${data.member_code}`}
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
          { label: "Offers", value: n(data.offers), note: NOTE },
          { label: "Visa applications", value: n(data.visa_applications), note: NOTE },
          { label: "Visa approvals", value: n(data.visa_approvals), note: NOTE },
          { label: "Enrollments", value: n(data.enrollments), link: ["View enrolled", "/overseas/agent/applications?status=enrolled"] },
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
      {[2, 5, 1].map((count, g) => (
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

export default async function AgentDashboardPanel() {
  let data: AgentDashboard;
  try {
    data = await serverApi<AgentDashboard>(DASHBOARD_URL);
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return accessUnavailable(e, "/overseas/login");
    return (
      <div className="card agent-dashboard">
        <p className="form-error" role="alert">
          Dashboard figures are unavailable right now.
        </p>
        <p>
          <Link href="/overseas/agent/dashboard">Try again</Link>
        </p>
      </div>
    );
  }
  return <AgentDashboardBoard data={data} />;
}
