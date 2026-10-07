import { progressText, type KpiProgress } from "@/lib/telecallerMetrics";
import { KPIS, targetText, type TargetsInEffect } from "@/lib/telecallerTargets";

type Progress = { daily: KpiProgress[]; monthly: KpiProgress[] };

// tel-022 (G4): the telecaller's own targets on the dashboard -- today's daily and this month's monthly value per KPI. tel-021 (§15):
// with `progress`, each cell reads "achieved / target" (today; the month to date). `null` = the read failed; the rest still renders.
export default function TelecallerTargetsCard({ targets, progress = null }: { targets: TargetsInEffect | null; progress?: Progress | null }) {
  const month = targets ? new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${targets.month}T00:00:00Z`)) : "";
  const value = (period: keyof Progress, kpi: string) => {
    const done = progress?.[period].find((r) => r.kpi === kpi);
    return done ? progressText(done.achieved, done.target) : targetText(targets?.[period].find((r) => r.kpi === kpi)?.value ?? null);
  };
  return (
    <section className="card tel-targets" aria-labelledby="my-targets-title" style={{ marginTop: 16 }}>
      <h3 id="my-targets-title">My targets</h3>
      {targets === null ? (
        <p className="muted" role="status">Targets are unavailable right now.</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="My targets by period" tabIndex={0}>
            <table className="table">
              <thead>
                <tr><th scope="col">KPI</th><th scope="col">Today</th><th scope="col">{month}</th></tr>
              </thead>
              <tbody>
                {KPIS.map((k) => (
                  <tr key={k.key}><th scope="row">{k.label}</th><td>{value("daily", k.key)}</td><td>{value("monthly", k.key)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
            {progress ? "Achieved / target. Targets are set by your manager; the month counts from the 1st to today." : "Set by your manager."}
          </p>
        </>
      )}
    </section>
  );
}
