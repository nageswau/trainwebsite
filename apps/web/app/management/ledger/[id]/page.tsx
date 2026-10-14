import Link from "next/link";

import { accessUnavailable } from "@/components/AccessUnavailable";
import LedgerEntryActions from "@/components/LedgerEntryActions";
import LedgerShell from "@/components/LedgerShell";
import { ApiError, serverApi } from "@/lib/api";
import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";
import type { ManagementMe } from "@/lib/management";
import {
  EVENT_LABEL, formatInr, KIND_LABEL, LEDGER_API, LEDGER_HOME, STATUS_LABEL, statusClass, VERTICAL_LABEL, type LedgerEntryDetail,
} from "@/lib/managementLedger";
import { SOURCE_LABEL } from "@/lib/telecallerCatalogue";

const NOTICES: Record<string, string> = {
  receipt: "The entry was saved, but the receipt could not be uploaded. Edit the entry to attach it again.",
  submit: "The entry was saved as a draft, but it could not be submitted. Submit it below.",
};

// mgmt-004 (ML7-ML14): one entry -- its fields, receipt, reversal links, history, and the actions the API allows the caller.
export default async function LedgerEntryPage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const { id } = await params;
  const notice = NOTICES[String((await searchParams).notice ?? "")];
  let me: ManagementMe;
  let entry: LedgerEntryDetail | null = null;
  try {
    me = await serverApi<ManagementMe>("/api/v1/management/me");
  } catch (e) {
    return accessUnavailable(e, "/admin/login");
  }
  try {
    entry = await serverApi<LedgerEntryDetail>(`${LEDGER_API}/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403)) return accessUnavailable(e, "/admin/login");
    if (!(e instanceof ApiError && (e.status === 404 || e.status === 422))) throw e;
  }
  if (!entry) {
    return (
      <LedgerShell me={me} title="Ledger entry not found">
        <p className="empty" role="status">This entry does not exist. <Link className="kpi-link" href={LEDGER_HOME}>Back to the ledger</Link></p>
      </LedgerShell>
    );
  }
  const at = (value: string | null) => (value ? formatDateTimeIn(value, SCHOOL_TIME_ZONE, true) : "—");
  const rows: [string, React.ReactNode][] = [
    ["Status", <span key="s" className={statusClass(entry.status)}>{STATUS_LABEL[entry.status]}</span>],
    ["Kind", KIND_LABEL[entry.kind]],
    ["Date", entry.entry_date],
    ["Amount", `${entry.reversal_of_id ? "−" : ""}${formatInr(entry.amount)}`],
    ["Category", entry.category.active ? entry.category.name : `${entry.category.name} (inactive)`],
    ["Vertical", VERTICAL_LABEL[entry.vertical] ?? entry.vertical],
    ["Marketing channel", entry.channel ? (SOURCE_LABEL[entry.channel] ?? entry.channel) : "—"],
    ["Course", entry.program?.name ?? "—"],
    ...(entry.school ? [["School", entry.school.name] as [string, string]] : []),
    ["Batch", entry.batch?.name ?? "—"],
    ["Created by", `${entry.created_by?.full_name ?? "—"} · ${at(entry.created_at)}`],
    ["Last changed by", `${entry.updated_by?.full_name ?? "—"} · ${at(entry.updated_at)}`],
    ...(entry.decided_by ? [[entry.status === "rejected" ? "Rejected by" : "Approved by", `${entry.decided_by.full_name} · ${at(entry.decided_at)}`] as [string, string]] : []),
    ...(entry.rejection_reason ? [["Reason for rejection", entry.rejection_reason] as [string, string]] : []),
  ];
  return (
    <LedgerShell me={me} title={entry.description} actions={<Link className="btn secondary" href={LEDGER_HOME}>Back to the ledger</Link>}>
      {notice && <p className="form-error" role="alert">{notice}</p>}
      {entry.reversal_of_id && <p className="muted">This entry reverses <Link className="kpi-link" href={`${LEDGER_HOME}/${entry.reversal_of_id}`}>an approved entry</Link>; once approved it counts as minus its amount.</p>}
      {entry.reversed_by_id && <p className="muted">A reversal of this entry exists: <Link className="kpi-link" href={`${LEDGER_HOME}/${entry.reversed_by_id}`}>open the reversal</Link>.</p>}
      <div className="action-card">
        <dl className="form-grid" style={{ margin: 0 }}>
          {rows.map(([label, value]) => (
            <div key={label} style={{ minWidth: 0, overflowWrap: "anywhere" }}>
              <dt className="muted" style={{ fontSize: 13 }}>{label}</dt>
              <dd style={{ margin: 0, fontWeight: 600 }}>{value}</dd>
            </div>
          ))}
        </dl>
        <p style={{ marginTop: 16, marginBottom: 0 }}>
          {entry.receipt ? (
            <a className="kpi-link" href={`${LEDGER_API}/${entry.id}/receipt`}>Download receipt{entry.receipt.name ? ` (${entry.receipt.name})` : ""}</a>
          ) : (
            <span className="muted">No receipt attached.</span>
          )}
        </p>
      </div>
      <LedgerEntryActions entry={entry} />
      <section aria-labelledby="ledger-history" className="action-card">
        <h3 id="ledger-history">History</h3>
        <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>
          {entry.events.map((event) => (
            <li key={event.id} style={{ overflowWrap: "anywhere" }}>
              <strong>{EVENT_LABEL[event.event] ?? event.event}</strong>
              {event.fields.length > 0 && <span> · {event.fields.map((f) => f.replace(/_id$/, "").replaceAll("_", " ")).join(", ")}</span>}
              {event.reason && <span> · “{event.reason}”</span>}
              <div className="muted" style={{ fontSize: 13 }}>by {event.actor?.full_name ?? "—"} · <time dateTime={event.at}>{at(event.at)}</time></div>
            </li>
          ))}
        </ol>
      </section>
    </LedgerShell>
  );
}
