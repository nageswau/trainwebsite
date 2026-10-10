import { type HealthBand, healthText, type PerformanceHealth, periodLabel } from "@/lib/partnershipPerformance";

// upc-028 (§30, DEC-SCOPE-168): the partnership health score, data only (it renders on the server). The badge reuses the existing pills
// and its text always names the band, so colour is never the only signal. The breakdown is shown only when the API sent it (the
// commission roles, U2); its points add up to the score.
const PILL: Record<HealthBand, string> = { excellent: "status", good: "badge", needs_attention: "status error", insufficient_data: "badge health-unknown" };

export function HealthBadge({ health }: { health: PerformanceHealth }) {
  return <span className={PILL[health.band]}>{healthText(health)}</span>;
}

export default function PartnershipHealth({ health }: { health: PerformanceHealth }) {
  const asOf = periodLabel({ from: health.as_of, to: health.as_of });
  return (
    <section className="action-card wide" aria-labelledby="uni-health">
      <h3 id="uni-health">Partnership health</h3>
      <p><HealthBadge health={health} /> <span className="muted">as of {asOf}</span></p>
      {health.score === null && <p className="muted">Not enough activity yet: no students, meetings, messages or agreement in force to score.</p>}
      {health.factors && (
        <div className="table-scroll" role="region" aria-labelledby="uni-health-caption" tabIndex={0}>
          <table className="table">
            <caption id="uni-health-caption" className="visually-hidden">Health score breakdown, as of {asOf}</caption>
            <thead>
              <tr><th scope="col">Factor</th><th scope="col">Measure</th><th scope="col">Weight</th><th scope="col">Points</th></tr>
            </thead>
            <tbody>
              {health.factors.map((f) => (
                <tr key={f.key}>
                  <th scope="row">{f.label}</th>
                  <td>{f.measure}</td>
                  <td>{f.weight}</td>
                  <td>{!f.tracked ? "Not tracked" : f.points ?? "No data"}</td>
                </tr>
              ))}
            </tbody>
            {health.score !== null && (
              <tfoot>
                <tr><th scope="row" colSpan={2}>Score</th><td>100</td><td>{health.score}</td></tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
      <p className="muted" style={{ fontSize: 13 }}>
        Scored from applications, offers, visa success and enrolments over the last 12 months, commission received against expected, how quickly the university
        replies and meetings over the last 90 days, and agreement status. A factor with no data has its weight shared out across the others. Student satisfaction
        is not tracked. Excellent is 80 and above, Good 60–79, Needs attention below 60.
      </p>
    </section>
  );
}
