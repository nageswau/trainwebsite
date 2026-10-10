import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import { expectedHref, type ForecastWindow, weightedText } from "@/lib/partnershipExpected";

// upc-023 (§23-§24, spec §5): E1-E3 as KPI tiles (AgentDashboardPanel's markup) -- the raw count of universities expected to sign in the
// window and the weighted forecast (E4: Σ probability). Each tile opens the list for its window. Data only, so a server page can render it.
export default function ExpectedForecastCards({ windows, undatedCount }: { windows: ForecastWindow[]; undatedCount: number }) {
  return (
    <section aria-labelledby="forecast-heading" className="kpi-group">
      <h3 id="forecast-heading">Partnership forecast</h3>
      <dl className="kpi-grid">
        {windows.map((w) => (
          <div className="kpi-tile" key={w.key}>
            <dt>{w.label}</dt>
            <dd className="kpi-value">{w.count}</dd>
            <dd className="kpi-note">Weighted forecast: <strong>{weightedText(w.weighted)}</strong></dd>
            <dd className="kpi-note muted">{formatCalendarDate(w.first)} – {formatCalendarDate(w.last)}</dd>
            <dd>
              <Link className="kpi-link" href={expectedHref(w.key)} aria-label={`View ${w.label.toLowerCase()}`}>View list</Link>
            </dd>
          </div>
        ))}
      </dl>
      <p className="muted" style={{ fontSize: 13 }}>
        Universities not yet signed, by expected agreement date. The weighted forecast adds up each university&apos;s probability (10 at 80% = 8).
        {undatedCount > 0 && <> {undatedCount} without an expected date {undatedCount === 1 ? "is" : "are"} not counted — <Link className="kpi-link" href={expectedHref("undated")}>see them</Link>.</>}
      </p>
    </section>
  );
}
