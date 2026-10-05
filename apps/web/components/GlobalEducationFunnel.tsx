import { plural } from "@/lib/plural";
import type { GlobalEducationPipeline } from "@/lib/types";

// ENH-017 (School CRM.md §17/§19, DEC-SCOPE-036): the school's bridged students by the furthest high-level stage they reached.
// The count is the text; the bar is decoration sized against the pathway count, so nothing is conveyed by length alone. Stages
// with no data source say so -- never a fabricated 0 (DATA_MODEL.md §8).
const pct = (count: number, total: number) => (total > 0 ? Math.round((count / total) * 100) : 0);

export default function GlobalEducationFunnel({ data }: { data: GlobalEducationPipeline }) {
  const scope = `${plural(data.students_in_scope, "student")}${data.grade === null ? "" : ` in Grade ${data.grade}`}`;
  return (
    <div className="card">
      <h2>Pipeline</h2>
      <p>{scope} · {plural(data.bridged_students, "student")} on the global education pathway</p>
      <p className="muted">High-level stage only. Application details are handled by EduSphere&apos;s application team.</p>
      <ol className="pipeline-funnel" aria-label="Global education funnel">
        {data.funnel.map((stage) => (
          <li key={stage.key} className="pipeline-stage">
            <span className="pipeline-label">{stage.label}</span>
            <span className="pipeline-count">{stage.count.toLocaleString("en-IN")}</span>
            <span className="pipeline-track" aria-hidden="true"><span className="pipeline-fill" style={{ width: `${pct(stage.count, data.bridged_students)}%` }} /></span>
          </li>
        ))}
      </ol>
      {data.not_tracked.length > 0 && (
        <section aria-label="Not tracked yet" className="kpi-group">
          <h3>Not tracked yet</h3>
          <dl className="kpi-grid">
            {data.not_tracked.map((s) => (
              <div className="kpi-tile" key={s.key}>
                <dt>{s.label}</dt>
                <dd><span className="badge">Not tracked yet</span><span className="kpi-note muted">{s.note}</span></dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
