import { formatInr, type TripMetrics } from "@/lib/bdmTravel";

// bdm-011 (College §F, DEC-SCOPE-079 L1/L3): the trip's figures as KPI tiles (the SchoolKpiBoard look). A figure with nothing to be
// computed from says why in words -- never a fabricated 0 (DATA_MODEL.md §8). Actual revenue is not tracked yet (D17).
const NO_ESTIMATES = "No estimates entered";

export default function TripProductivity({ metrics: m }: { metrics: TripMetrics }) {
  const count = (n: number | null, empty: string) => (n === null ? { note: empty } : { value: n.toLocaleString("en-IN") });
  const money = (v: string | null, empty: string) => (v === null ? { note: empty } : { value: formatInr(v) });
  const tiles: [string, { value?: string; note?: string; untracked?: boolean }][] = [
    ["Meetings planned", count(m.meetings_planned, "")],
    ["Meetings completed", count(m.meetings_completed, "")],
    ["Estimated cost", money(m.estimated_cost, "")],
    ["Actual cost", money(m.actual_cost, "")],
    ["Cost per completed meeting", money(m.cost_per_completed_meeting, "No completed meetings yet")],
    ["Expected leads", count(m.expected_leads, NO_ESTIMATES)],
    ["Expected revenue", money(m.expected_revenue, NO_ESTIMATES)],
    ["Actual leads", count(m.actual_leads, "")],
    ["Actual revenue", m.actual_revenue === null ? { untracked: true } : { value: formatInr(m.actual_revenue) }],
  ];
  return (
    <dl className="kpi-grid">
      {tiles.map(([label, t]) => (
        <div className="kpi-tile" key={label}>
          <dt>{label}</dt>
          {t.value !== undefined ? (
            <dd className="kpi-value">{t.value}</dd>
          ) : t.untracked ? (
            <dd><span className="badge">Not tracked yet</span></dd>
          ) : (
            <dd className="muted">{t.note}</dd>
          )}
        </div>
      ))}
    </dl>
  );
}
