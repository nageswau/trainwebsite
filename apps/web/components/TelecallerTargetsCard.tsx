import { KPIS, targetText, type TargetsInEffect } from "@/lib/telecallerTargets";

// tel-022 (G4): the telecaller's own targets on the dashboard -- today's daily and this month's monthly value per KPI. tel-021 adds the
// achieved figures beside them. `null` = the read failed; the rest of the dashboard still renders.
export default function TelecallerTargetsCard({ targets }: { targets: TargetsInEffect | null }) {
  const month = targets ? new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${targets.month}T00:00:00Z`)) : "";
  const value = (rows: TargetsInEffect["daily"], kpi: string) => targetText(rows.find((r) => r.kpi === kpi)?.value ?? null);
  return (
    <section className="card" aria-labelledby="my-targets-title" style={{ marginTop: 16 }}>
      <h3 id="my-targets-title">My targets</h3>
      {targets === null ? (
        <p className="muted" role="status">Targets are unavailable right now.</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="My targets by period" tabIndex={0}>
            <table>
              <thead>
                <tr><th scope="col">KPI</th><th scope="col">Today</th><th scope="col">{month}</th></tr>
              </thead>
              <tbody>
                {KPIS.map((k) => (
                  <tr key={k.key}><th scope="row">{k.label}</th><td>{value(targets.daily, k.key)}</td><td>{value(targets.monthly, k.key)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Set by your manager. Achieved figures will appear here once call logging is live.</p>
        </>
      )}
    </section>
  );
}
