import type { ReactNode } from "react";

import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { BAND_LABEL, type Band, PRIORITY_LABEL, type UniversityFollowUpData } from "@/lib/partnershipTasks";

// upc-020 (§20, the XYZ example): Last Action, Next Action, its date, owner and priority. Next Action is the earliest open follow-up
// (TK14); Last Action the latest completed task or stage move (TK15). Server-rendered on the university page.
export default function UniversityFollowUp({ followUp }: { followUp: UniversityFollowUpData }) {
  const next = followUp.next_action;
  const last = followUp.last_action;
  const rows: [string, ReactNode][] = [
    ["Last action", last ? <><span>{last.title}</span> <span className="muted">({formatSchoolDateTime(last.at)})</span></> : <span className="muted">Nothing recorded yet</span>],
    ["Next action", next ? next.title : <span className="muted">No follow-up planned</span>],
  ];
  if (next) {
    rows.push(
      ["Date", <><span>{formatCalendarDate(next.due_on)}</span> <span className={`badge${next.band === "overdue" ? " status error" : ""}`}>{BAND_LABEL[next.band as Band] ?? next.band}</span></>],
      ["Owner", `${next.assignee.full_name}${next.assignee.active ? "" : " (inactive)"}`],
      ["Priority", PRIORITY_LABEL[next.priority] ?? next.priority],
    );
  }
  return (
    <dl style={{ display: "grid", gridTemplateColumns: "minmax(110px, max-content) 1fr", gap: "6px 16px", margin: "0 0 12px" }}>
      {rows.map(([term, value]) => [
        <dt key={`${term}-t`} className="muted">{term}</dt>,
        <dd key={`${term}-d`} style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>,
      ])}
    </dl>
  );
}
