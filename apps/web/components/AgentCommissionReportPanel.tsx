"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";
import DataTable from "@/components/DataTable";
import FormMessage from "@/components/FormMessage";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import { detailMessage } from "@/lib/apiErrors";
import { CSV_URL, REPORT_URL, STATUS_LABELS, type CommissionReport, csvFilename, isReport, reportQuery } from "@/lib/agentCommissionReport";

// AGN-014 (DEC-SCOPE-051): a Master's commission report on the agent Reports page -- breakdowns per currency, a created-date
// filter and a CSV of the applied range. WorkflowPanel mounts it for Masters only; the server refuses staff (403) regardless.
type Range = { from: string; to: string };
type Table = { title: string; columns: { key: string; label: string }[]; rows: Record<string, unknown>[] };

const NONE: Range = { from: "", to: "" };
const EXPIRED = "Your session has expired. Sign in again.";
const FAILED = "Something went wrong on our side. Please try again.";
const GROUP_COLUMNS = [
  { key: "count", label: "Count" },
  { key: "amount", label: "Amount" },
  { key: "currency", label: "Currency" },
];

const money = (amount: number) => amount.toLocaleString("en-IN", { maximumFractionDigits: 2 });

function tablesFor(report: CommissionReport): Table[] {
  const withMoney = <T extends { amount: number }>(rows: T[]) => rows.map((row) => ({ ...row, amount: money(row.amount) }));
  return [
    { title: "By status", columns: [{ key: "status", label: "Status" }, ...GROUP_COLUMNS], rows: withMoney(report.by_status).map((row) => ({ ...row, status: STATUS_LABELS[row.status] ?? row.status })) },
    { title: "By university", columns: [{ key: "university", label: "University" }, { key: "country", label: "Country" }, ...GROUP_COLUMNS], rows: withMoney(report.by_university) },
    { title: "By country", columns: [{ key: "country", label: "Country" }, ...GROUP_COLUMNS], rows: withMoney(report.by_country) },
    { title: "By intake", columns: [{ key: "intake", label: "Intake" }, ...GROUP_COLUMNS], rows: withMoney(report.by_intake) },
  ];
}

export default function AgentCommissionReportPanel() {
  const [draft, setDraft] = useState<Range>(NONE);
  const [applied, setApplied] = useState<Range>(NONE);
  const [report, setReport] = useState<CommissionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const latest = useRef(0);

  async function load(range: Range) {
    const id = ++latest.current; // a response for an older request is dropped
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${REPORT_URL}${reportQuery(range.from, range.to)}`, { credentials: "same-origin" });
      const body: unknown = await response.json().catch(() => null);
      if (id !== latest.current) return;
      if (response.ok && isReport(body)) {
        setReport(body);
        setApplied(range);
      } else {
        setReport(null);
        setError(response.status === 401 ? EXPIRED : response.ok || response.status >= 500 ? FAILED : detailMessage((body as { detail?: unknown } | null)?.detail, FAILED));
      }
    } catch {
      if (id === latest.current) {
        setReport(null);
        setError(FAILED);
      }
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }

  useEffect(() => {
    void load(NONE);
  }, []);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    if (draft.from && draft.to && draft.to < draft.from) {
      setRangeError("'To' must be on or after 'From'.");
      return;
    }
    setRangeError(null);
    void load(draft);
  }

  return (
    <div className="action-card" aria-busy={loading}>
      <h3>Commission report</h3>
      <p className="muted">Your agency&apos;s commissions by the date they were created (UTC). Amounts are totalled per currency.</p>
      <form aria-label="Commission report filters" onSubmit={apply} className="actions" style={{ alignItems: "flex-end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="commission-report-from">From</label>
          <input id="commission-report-from" type="date" value={draft.from} onChange={(e) => setDraft({ ...draft, from: e.target.value })} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="commission-report-to">To</label>
          <input id="commission-report-to" type="date" value={draft.to} onChange={(e) => setDraft({ ...draft, to: e.target.value })} />
        </div>
        <button className="btn" type="submit" aria-disabled={loading}>
          Apply
        </button>
      </form>
      {rangeError && <FormMessage message={{ text: rangeError, failed: true }} />}
      {loading && <p role="status">Loading commission report…</p>}
      {error && <FormMessage message={{ text: error, failed: true }} />}
      {!loading && report && report.totals.length === 0 && <p>No commissions in this period.</p>}
      {!loading && report && report.totals.length > 0 && (
        <>
          <p>
            <strong>Total:</strong> {report.totals.map((t) => `${t.currency} ${money(t.amount)} (${t.count} commission${t.count === 1 ? "" : "s"})`).join(" · ")}
          </p>
          {tablesFor(report).map((table) => (
            <section key={table.title}>
              <h4>{table.title}</h4>
              <DataTable columns={table.columns} rows={table.rows} label={`Commissions ${table.title.toLowerCase()}`} />
            </section>
          ))}
        </>
      )}
      {!loading && report && (
        <ReportDownloadButton url={`${CSV_URL}${reportQuery(applied.from, applied.to)}`} label="Download CSV" filename={csvFilename(applied.from, applied.to)} contentType="text/csv" busyLabel="Preparing CSV…" />
      )}
    </div>
  );
}
