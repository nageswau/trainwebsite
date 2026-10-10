import Link from "next/link";

import type { DashboardTile } from "@/lib/partnershipDashboard";

// upc-022 (§22, spec §4): one group of dashboard figures as KPI tiles (ExpectedForecastCards' markup). Each figure opens its list. Data
// only, so the server page can render it.
export default function PartnershipDashboardTiles({ id, title, tiles }: { id: string; title: string; tiles: DashboardTile[] }) {
  return (
    <section aria-labelledby={id} className="kpi-group">
      <h3 id={id}>{title}</h3>
      <dl className="kpi-grid dashboard-tiles">
        {tiles.map((t) => (
          <div className="kpi-tile" key={t.key}>
            <dt>{t.icon && <span aria-hidden="true">{t.icon} </span>}{t.label}</dt>
            <dd className="kpi-value">{t.value}</dd>
            {t.note && <dd className="kpi-note muted">{t.note}</dd>}
            <dd>
              <Link className="kpi-link" href={t.href} aria-label={`View ${t.label.toLowerCase()}`}>View list</Link>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
