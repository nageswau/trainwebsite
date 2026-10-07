import { ACTIVITY, progressText, type TelecallerActivity } from "@/lib/telecallerMetrics";
import { KPI_LABEL } from "@/lib/telecallerTargets";

const dayLabel = (day: string) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));

// tel-021 (EVID-019 §14, T27): the 13 computed counts for one IST day beside that day's daily targets. The day is a plain GET form
// (`?date=`), so it needs no client JS and a day can be shared. `activity` null + `error` = the read failed or the API refused the day.
export default function TelecallerActivityPanel({ activity, error, day, today }: {
  activity: TelecallerActivity | null; error?: string; day: string; today: string;
}) {
  return (
    <section className="card tel-targets" aria-labelledby="daily-activity-title" role="region" style={{ marginTop: 16 }}>
      <h3 id="daily-activity-title">Daily activity</h3>
      <form method="get" style={{ display: "flex", flexWrap: "wrap", alignItems: "end", gap: 8, margin: "8px 0 12px" }}>
        <label style={{ display: "grid", gap: 4 }}>
          Day
          <input className="input" type="date" name="date" defaultValue={day} max={today} required />
        </label>
        <button className="btn secondary small" type="submit">Show</button>
      </form>
      {activity === null ? (
        <p className="muted" role="alert">{error}</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="Activity counts" tabIndex={0}>
            <table className="table">
              <caption className="visually-hidden">Activity on {dayLabel(activity.day)}</caption>
              <thead><tr><th scope="col">Activity on {dayLabel(activity.day)}</th><th scope="col">Count</th></tr></thead>
              <tbody>
                {ACTIVITY.map((a) => (
                  <tr key={a.key}><th scope="row">{a.label}</th><td>{activity.counts[a.key]}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap" role="region" aria-label="Targets that day" tabIndex={0} style={{ marginTop: 12 }}>
            <table className="table">
              <thead><tr><th scope="col">KPI</th><th scope="col">Achieved / target</th></tr></thead>
              <tbody>
                {activity.targets.map((t) => (
                  <tr key={t.kpi}><th scope="row">{KPI_LABEL[t.kpi] ?? t.kpi}</th><td>{progressText(t.achieved, t.target)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
