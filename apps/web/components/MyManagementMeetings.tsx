import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import { KIND_LABEL, safeLink, STATUS_LABEL, statusClass, type MyMeeting } from "@/lib/managementMeetings";

// mgmt-029 (MM12): the management meetings a staff member is invited to -- time, kind, place, link and agenda only (never the minutes,
// the chain or the other participants). Shown in their Management tasks page; the API lists only their own meetings.
export default function MyManagementMeetings({ items }: { items: MyMeeting[] }) {
  if (items.length === 0) return <p className="empty" role="status">No management meetings for you this week or later.</p>;
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 10 }}>
      {items.map((m) => {
        const link = safeLink(m.meeting_url);
        return (
          <li key={m.id} className="action-card" style={{ display: "grid", gap: 6, overflowWrap: "anywhere" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <strong>{m.title}</strong>
              <span className="badge">{KIND_LABEL[m.kind]}</span>
              {m.status !== "scheduled" && <span className={statusClass(m.status)}>{STATUS_LABEL[m.status]}</span>}
            </div>
            <div className="muted" style={{ fontSize: 14 }}>
              {formatDateTimeIn(m.starts_at, SCHOOL_TIME_ZONE, true)} · {m.mode}{m.location ? ` · ${m.location}` : ""}
            </div>
            {link && m.status === "scheduled" && (
              <a className="kpi-link" href={link} target="_blank" rel="noopener noreferrer" aria-label={`Join ${m.title}`}>Join the meeting</a>
            )}
            {m.agenda && <p style={{ margin: 0, whiteSpace: "pre-wrap" }}><span className="muted">Agenda: </span>{m.agenda}</p>}
          </li>
        );
      })}
    </ul>
  );
}
