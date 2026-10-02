"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import FormMessage from "@/components/FormMessage";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { detailMessage } from "@/lib/apiErrors";
import { CSV_URL, REPORT_URL, STATUS_LABELS, type CommissionReport, csvFilename, isReport, readRange, reportQuery, writeRange } from "@/lib/agentCommissionReport";

// AGN-014 (DEC-SCOPE-051): a Master's commission report on the agent Reports page -- breakdowns per currency, a created-date
// filter and a CSV of the applied range. WorkflowPanel mounts it for Masters only; the server refuses staff (403) regardless.
type Range = { from: string; to: string };
type Field = "from" | "to";
type Failure = { text: string; retry?: boolean; expired?: boolean };
type Table = { title: string; columns: { key: string; label: string }[]; rows: Record<string, string | number>[] };

const NONE: Range = { from: "", to: "" };
const FAILED = "Something went wrong on our side. Please try again.";
const OFFLINE = "The report could not load. Check your connection and try again."; // QA14-07: not "on our side"
const FIELD_LABEL: Record<Field, string> = { from: "'From'", to: "'To'" };

// Lakh/crore grouping is right for rupees only; other currencies use the international 1,000s grouping.
const money = (amount: number, currency: string) => `${currency} ${amount.toLocaleString(currency === "INR" ? "en-IN" : "en-US", { maximumFractionDigits: 2 })}`;

// QA14-02/09: small fixed tables, the amount (with its currency) right after the label so it stays on screen on a phone.
function tablesFor(report: CommissionReport): Table[] {
  const tail = [{ key: "amount", label: "Amount" }, { key: "count", label: "Commissions" }];
  const cells = <T extends { amount: number; currency: string; count: number }>(row: T) => ({ amount: money(row.amount, row.currency), count: row.count });
  return [
    { title: "By status", columns: [{ key: "status", label: "Status" }, ...tail], rows: report.by_status.map((r) => ({ status: STATUS_LABELS[r.status] ?? r.status, ...cells(r) })) },
    { title: "By university", columns: [{ key: "university", label: "University" }, { key: "country", label: "Country" }, ...tail], rows: report.by_university.map((r) => ({ university: r.university, country: r.country, ...cells(r) })) },
    { title: "By country", columns: [{ key: "country", label: "Country" }, ...tail], rows: report.by_country.map((r) => ({ country: r.country, ...cells(r) })) },
    { title: "By intake", columns: [{ key: "intake", label: "Intake" }, ...tail], rows: report.by_intake.map((r) => ({ intake: r.intake, ...cells(r) })) },
  ];
}

function Breakdown({ table }: { table: Table }) {
  const headingId = useId();
  return (
    <section>
      <h4 id={headingId}>{table.title}</h4>
      {/* QA14-03: the heading names the table for assistive tech. */}
      <div className="table-wrap">
        <table className="table" aria-labelledby={headingId}>
          <thead>
            <tr>{table.columns.map((c) => <th key={c.key} scope="col">{c.label}</th>)}</tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>{table.columns.map((c) => <td key={c.key}>{row[c.key]}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AgentCommissionReportPanel() {
  const [draft, setDraft] = useState<Range>(NONE);
  const [applied, setApplied] = useState<Range>(NONE);
  const [report, setReport] = useState<CommissionReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [fieldError, setFieldError] = useState<{ field: Field; text: string } | null>(null);
  const latest = useRef(0);
  const requested = useRef<Range>(NONE); // what "Try again" reloads
  const inputs = { from: useRef<HTMLInputElement>(null), to: useRef<HTMLInputElement>(null) };
  const fieldErrorId = useId();

  async function load(range: Range) {
    const id = ++latest.current; // a response for an older request is dropped
    requested.current = range;
    setLoading(true);
    setFailure(null);
    try {
      const response = await fetch(`${REPORT_URL}${reportQuery(range.from, range.to)}`, { credentials: "same-origin" });
      const body: unknown = await response.json().catch(() => null);
      if (id !== latest.current) return;
      const detail = (body as { detail?: unknown } | null)?.detail;
      if (response.ok && isReport(body)) {
        setReport(body);
        setApplied(range);
        writeRange(range); // QA14-06: refresh, Back and a shared link keep the range
      } else if (response.status === 422) {
        // QA14-05: an input the server rejects is a field error; the figures on screen stay and there is nothing to retry.
        const text = detailMessage(detail, FAILED);
        const field: Field = text.includes("date_from") ? "from" : "to";
        setFieldError({ field, text: text.replace(/date_from/g, FIELD_LABEL.from).replace(/date_to/g, FIELD_LABEL.to) });
        inputs[field].current?.focus();
      } else if (response.status === 401) {
        setReport(null);
        setFailure({ text: SESSION_EXPIRED, expired: true }); // QA14-08: sign in, not retry
      } else if (response.ok || response.status >= 500) {
        setFailure({ text: FAILED, retry: true });
      } else {
        setReport(null); // e.g. 403: this account may no longer see the report
        setFailure({ text: detailMessage(detail, FAILED) });
      }
    } catch {
      if (id === latest.current) setFailure({ text: OFFLINE, retry: true });
    } finally {
      if (id === latest.current) setLoading(false);
    }
  }

  useEffect(() => {
    const initial = readRange(window.location.search);
    setDraft(initial);
    void load(initial);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- load once on mount; Apply and Try again reload

  function apply(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    if (draft.from && draft.to && draft.to < draft.from) {
      setFieldError({ field: "to", text: "'To' must be on or after 'From'." });
      inputs.to.current?.focus(); // the field to correct, described by the error below
      return;
    }
    setFieldError(null);
    void load(draft);
  }

  function edit(change: Partial<Range>) {
    setDraft({ ...draft, ...change });
    setFieldError(null); // the error described the old values
  }

  const filtered = Boolean(applied.from || applied.to);
  const signIn = () => `${SIGN_IN_PATH}?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  const described = (field: Field) =>
    fieldError?.field === field ? { "aria-invalid": true as const, "aria-describedby": fieldErrorId } : {};

  return (
    <div className="action-card commission-report" aria-busy={loading}>
      <h3>Commission report</h3>
      <p className="muted">Your agency&apos;s commissions by the date they were created (UTC). Amounts are totalled per currency.</p>
      <form aria-label="Commission report filters" onSubmit={apply} className="actions" style={{ alignItems: "flex-end" }}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="commission-report-from">From</label>
          <input id="commission-report-from" ref={inputs.from} type="date" value={draft.from} onChange={(e) => edit({ from: e.target.value })} {...described("from")} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="commission-report-to">To</label>
          <input id="commission-report-to" ref={inputs.to} type="date" value={draft.to} onChange={(e) => edit({ to: e.target.value })} {...described("to")} />
        </div>
        <button className="btn" type="submit" aria-disabled={loading}>
          Apply
        </button>
      </form>
      {fieldError && (
        <div id={fieldErrorId}>
          <FormMessage message={{ text: fieldError.text, failed: true }} />
        </div>
      )}
      {/* The current figures stay on screen while a new range loads; only the first load has nothing to show. */}
      {loading && <p role="status">{report ? "Updating commission report…" : "Loading commission report…"}</p>}
      {failure && (
        <>
          <p className="form-error" role="alert">
            {failure.text}
            {failure.expired && (
              <>
                {" "}
                <Link href={signIn()}>Sign in again</Link>
              </>
            )}
          </p>
          {failure.retry && (
            <div className="actions">
              <button type="button" className="btn secondary" onClick={() => void load(requested.current)}>
                Try again
              </button>
            </div>
          )}
        </>
      )}
      {report && report.totals.length === 0 && <p>{filtered ? "No commissions in this period." : "Your agency has no commissions yet."}</p>}
      {report && report.totals.length > 0 && (
        <>
          <p>
            <strong>Total:</strong> {report.totals.map((t) => `${money(t.amount, t.currency)} (${t.count} commission${t.count === 1 ? "" : "s"})`).join(" · ")}
          </p>
          {/* QA14-02/10: the export sits with the totals, before the tables, and only when there is something to export. */}
          <ReportDownloadButton url={`${CSV_URL}${reportQuery(applied.from, applied.to)}`} label="Download CSV" filename={csvFilename(applied.from, applied.to)} contentType="text/csv" busyLabel="Preparing CSV…" />
          {tablesFor(report).map((table) => (
            <Breakdown key={table.title} table={table} />
          ))}
        </>
      )}
    </div>
  );
}
