import Link from "next/link";

import { alertHref, alertListHref, alertWhen, type ManagerDashboard, TONE } from "@/lib/bdmManagerDashboard";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

// bdm-023 (DEC-SCOPE-104 §6): the management dashboard -- the §13 overview tiles, then the alerts that have records. A plain function
// of its data (no client state). Every alert carries a text word beside its colour (AC4); a resolved alert simply isn't listed (AC2).
const LIST = { listStyle: "none", padding: 0, margin: "8px 0 0" } as const;
const ROW = { display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline", padding: "8px 0", borderTop: "1px solid var(--line, #e5e7eb)" } as const;
const LINK = { ...LINK_STYLE, overflowWrap: "anywhere" } as const;
const HEAD = { margin: 0, fontSize: 18 } as const;
const ALERT_HEAD = { margin: "16px 0 0", fontSize: 16, display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" } as const;

export default function BdmManagerDashboard({ data, superAdmin }: { data: ManagerDashboard; superAdmin: boolean }) {
  const active = data.alerts.filter((a) => a.count > 0);
  return (
    <>
      <section className="card" aria-labelledby="dashboard-overview" style={{ marginBottom: 16 }}>
        <h3 id="dashboard-overview" style={HEAD}>BDM overview</h3>
        <p className="muted" style={{ margin: "4px 0 0" }}>Today and this month, India time (IST).</p>
        <dl className="kpi-grid">
          {data.tiles.map((t) => (
            <div className="kpi-tile" key={t.key}>
              <dt>{t.label}</dt>
              <dd className="kpi-value">{t.value.toLocaleString("en-IN")}</dd>
              <dd className="kpi-note muted">{t.definition}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="card" aria-labelledby="dashboard-alerts">
        <h3 id="dashboard-alerts" style={HEAD}>Alerts</h3>
        {active.length === 0 ? (
          <p className="muted" style={{ margin: "8px 0 0" }}>No alerts right now.</p>
        ) : (
          active.map((alert) => {
            const tone = TONE[alert.tone];
            return (
              <section key={alert.key} aria-labelledby={`alert-${alert.key}`}>
                <h4 id={`alert-${alert.key}`} style={ALERT_HEAD}>
                  <span className={tone.className}>{tone.text}</span>
                  <span>{`${alert.label}: ${alert.count}`}</span>
                </h4>
                <ul style={LIST}>
                  {alert.items.map((item) => (
                    <li key={item.id} style={ROW}>
                      <Link href={alertHref(alert, item)} style={LINK}>{item.title}</Link>
                      <span className="muted">
                        {alert.record === "daily_report" ? alertWhen(alert.key, item.at) : `${item.bdm.full_name} · ${alertWhen(alert.key, item.at)}`}
                      </span>
                    </li>
                  ))}
                </ul>
                {alert.count > alert.items.length && <p className="muted" style={{ margin: "4px 0 0" }}>{`Showing ${alert.items.length} of ${alert.count}.`}</p>}
                <Link href={alertListHref(alert.key, superAdmin)} style={LINK} aria-label={`View all: ${alert.label}`}>View all</Link>
              </section>
            );
          })
        )}
      </section>
    </>
  );
}
