import { formatInr, type TripMetrics } from "@/lib/bdmTravel";

// bdm-011 (College §F, DEC-SCOPE-089 L1/L3): the trip's figures as KPI tiles (the SchoolKpiBoard look). A figure with nothing to be
// computed from says why in words -- never a fabricated 0 (DATA_MODEL.md §8). Actual revenue is not tracked yet (D17).
const NO_ESTIMATES = "No estimates entered";
const num = (n: number | null) => (n === null ? null : n.toLocaleString("en-IN"));
const inr = (v: string | null) => (v === null ? null : formatInr(v));

export default function TripProductivity({ metrics: m }: { metrics: TripMetrics }) {
  // [label, value, what to say when there is no value (null = "Not tracked yet")]
  const tiles: [string, string | null, string | null][] = [
    ["Meetings planned", num(m.meetings_planned), null],
    ["Meetings completed", num(m.meetings_completed), null],
    ["Estimated cost", inr(m.estimated_cost), null],
    ["Actual cost", inr(m.actual_cost), null],
    ["Cost per completed meeting", inr(m.cost_per_completed_meeting), "No completed meetings yet"],
    ["Expected leads", num(m.expected_leads), NO_ESTIMATES],
    ["Expected revenue", inr(m.expected_revenue), NO_ESTIMATES],
    ["Actual leads", num(m.actual_leads), null],
    ["Actual revenue", inr(m.actual_revenue), null],
  ];
  return (
    <dl className="kpi-grid">
      {tiles.map(([label, value, empty]) => (
        <div className="kpi-tile" key={label}>
          <dt>{label}</dt>
          {value !== null ? <dd className="kpi-value">{value}</dd>
            : empty ? <dd className="muted">{empty}</dd>
            : <dd><span className="badge">Not tracked yet</span></dd>}
        </div>
      ))}
    </dl>
  );
}
