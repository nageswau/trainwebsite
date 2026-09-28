import type { Scorecard, ScorecardState } from "@/lib/types";

// ENH-016 (School CRM.md §28). Every state is an icon AND words -- never colour or emoji alone (spec §8).
const STATES: Record<ScorecardState, { icon: string; label: string }> = {
  completed: { icon: "✅", label: "Completed" },
  in_progress: { icon: "🔄", label: "In progress" },
  not_started: { icon: "⏳", label: "Not started" },
  not_in_plan: { icon: "—", label: "Not in plan" },
  not_tracked: { icon: "—", label: "Not tracked yet" },
};

export function ScorecardStateBadge({ state }: { state: ScorecardState }) {
  const { icon, label } = STATES[state];
  return (
    <span className="state-badge">
      <span aria-hidden="true">{icon}</span>
      {label}
    </span>
  );
}

export default function StudentScorecard({ card }: { card: Scorecard }) {
  return (
    <div className="card">
      <h2>Progress scorecard</h2>
      <p className="muted">Portfolio {card.portfolio_completion_pct}% complete</p>
      <div className="table-scroll">
      <table className="table">
        <caption className="sr-only">Progress by area for {card.full_name}</caption>
        <thead>
          <tr><th scope="col">Area</th><th scope="col">Status</th></tr>
        </thead>
        <tbody>
          {card.areas.map((a) => (
            <tr key={a.key}>
              <th scope="row">{a.label}</th>
              <td><ScorecardStateBadge state={a.state} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}
