import { formatCalendarDate } from "@/lib/formatDate";
import type { ManagementSnapshot as Snapshot } from "@/lib/management";

// mgmt-003 (EVID-017 §3, Appendix B S1-S15): the fifteen counts on the existing metric tiles, in source order, Indian digit grouping.
export default function ManagementSnapshot({ snapshot }: { snapshot: Snapshot }) {
  return (
    <>
      <p className="muted">As of {formatCalendarDate(snapshot.as_of)} (India time). Counts are live from the EduSphere records.</p>
      <ul className="metric-grid snapshot-tiles" aria-label="Business snapshot figures">
        {snapshot.kpis.map((kpi) => (
          <li key={kpi.key} className="metric">
            <span>{kpi.label}</span>
            <strong>{kpi.value.toLocaleString("en-IN")}</strong>
          </li>
        ))}
      </ul>
    </>
  );
}
