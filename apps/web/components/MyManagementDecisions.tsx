"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { decisionLine, isOverdue, MY_DECISIONS_API, MY_STATUSES, STATUS_LABEL, type DiscussionStatus, type MyDecision } from "@/lib/managementDiscussions";

// mgmt-027 (MD8/MD14): the decisions a staff member is responsible for -- the decision line only (decision, deadline, status) and the
// files management shared with them. They can move the status between Open, In Progress and Completed.
export default function MyManagementDecisions({ items, today }: { items: MyDecision[]; today: string }) {
  if (items.length === 0) return <p className="empty" role="status">No management decisions are assigned to you.</p>;
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 12 }}>
      {items.map((item) => <DecisionRow key={item.id} item={item} today={today} />)}
    </ul>
  );
}

function DecisionRow({ item, today }: { item: MyDecision; today: string }) {
  const router = useRouter();
  const [status, setStatus] = useState<DiscussionStatus>(item.status);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const id = `decision-${item.id}-status`;

  async function update() {
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(`${MY_DECISIONS_API}/${item.id}`, "PATCH", { status });
    setBusy(false);
    setResult(outcome.ok ? { text: "Status updated.", failed: false } : { text: outcome.message, failed: true });
    if (outcome.ok) router.refresh();
  }

  return (
    <li className="action-card" style={{ display: "grid", gap: 10, overflowWrap: "anywhere" }}>
      <p style={{ margin: 0, fontWeight: 700 }}>{decisionLine(item)}</p>
      {isOverdue(item, today) && <p style={{ margin: 0 }}><span className="status error">Overdue</span></p>}
      {item.attachments.length > 0 && (
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          {item.attachments.map((a) => (
            <li key={a.id}><a className="kpi-link" href={`${MY_DECISIONS_API}/${item.id}/attachments/${a.id}`}>{a.name ?? "Attachment"}</a></li>
          ))}
        </ul>
      )}
      <div className="form-grid" style={{ alignItems: "end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={id}>Status of “{item.decision}”</label>
          <select id={id} value={status} disabled={busy} onChange={(e) => setStatus(e.target.value as DiscussionStatus)}>
            {MY_STATUSES.map((value) => <option key={value} value={value}>{STATUS_LABEL[value]}</option>)}
          </select>
        </div>
        <div className="actions">
          <button className="btn" type="button" disabled={busy || status === item.status} onClick={() => void update()}>{busy ? "Saving…" : "Update status"}</button>
        </div>
      </div>
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
    </li>
  );
}
