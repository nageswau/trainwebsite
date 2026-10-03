"use client";

import Link from "next/link";
import { type KeyboardEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import AgentCommissionReportPanel from "@/components/AgentCommissionReportPanel";
import AgentReportFilters, { type FieldError, type ReportField } from "@/components/AgentReportFilters";
import AgentReportTable from "@/components/AgentReportTable";
import ReportDownloadButton from "@/components/ReportDownloadButton";
import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { REPORTS_URL, type ReportKey, type ReportState, csvFilename, csvUrl, isAgentReport, readState, reportQuery, tabsFor, writeState } from "@/lib/agentReports";
import { detailMessage } from "@/lib/apiErrors";
import type { AgentReport } from "@/lib/types";

// AGN-020 (DEC-SCOPE-063; spec §6.2, §6.4): the agency Reports page -- one tab per report (Student360Tabs' keyboard pattern, laid out
// as a strip), the view held in the address, and the AGN-014 commission panel, unchanged, as the Commission tab. The server is the
// authority: hidden tabs are a convenience, a refused report shows the server's reason. A response for an older request is
// dropped, so quick tab or filter changes never show the wrong report. A refetch keeps the current table (dimmed); only a first
// load or a new tab shows the skeleton.

type Failure = { text: string; retry?: boolean; expired?: boolean };
const FAILED = "Couldn't load this report.";
const OFFLINE = "The report could not load. Check your connection and try again.";
const EMPTY: Partial<Record<ReportKey, string>> = { students: "No students yet.", enrollments: "No enrollments yet." };
const FIELDS: Record<string, ReportField> = { date_from: "from", date_to: "to", member: "member", country: "country", university: "university", intake: "intake", status: "status" };
const MOVES: Record<string, (i: number, last: number) => number> = {
  ArrowRight: (i, last) => (i === last ? 0 : i + 1), ArrowLeft: (i, last) => (i === 0 ? last : i - 1), Home: () => 0, End: (_, last) => last,
};

/** The field a 422 names (FastAPI's list shape, `loc: ["query", param]`), if it is one of the form's. */
function fieldOf(detail: unknown): ReportField | null {
  const loc = Array.isArray(detail) ? (detail[0] as { loc?: unknown[] } | undefined)?.loc : undefined;
  return (Array.isArray(loc) && FIELDS[String(loc[1])]) || null;
}

export default function AgentReportsPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined }) {
  const tabs = useMemo(() => tabsFor(memberRole), [memberRole]);
  const [state, setState] = useState<ReportState>({ report: tabs[0].key, from: "", to: "", filters: {}, offset: 0 });
  const [report, setReport] = useState<AgentReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [fieldError, setFieldError] = useState<FieldError | null>(null);
  const [resets, setResets] = useState(0); // remounts the filter form when its values are cleared from outside it
  const latest = useRef(0);
  const requested = useRef<ReportState>(state);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const region = useRef<HTMLDivElement>(null);
  const focusTable = useRef(false);
  const id = useId();
  const active = tabs.find((t) => t.key === state.report) ?? tabs[0];

  useEffect(() => {
    void open(readState(window.location.search, tabs));
    // Mount only: the address is read once; afterwards this panel writes it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (focusTable.current && report) {
      focusTable.current = false;
      region.current?.focus(); // after Previous/Next, keyboard and screen-reader users land on the new rows
    }
  }, [report]);

  async function open(next: ReportState) {
    if (next.report !== requested.current.report) setReport(null); // another report's table never sits under this heading
    setState(next);
    writeState(next);
    setFieldError(null);
    if (next.report === "commission") {
      latest.current += 1; // drop anything still in flight
      requested.current = next;
      setFailure(null);
      setLoading(false);
      return;
    }
    await load(next);
  }

  async function load(next: ReportState) {
    const call = ++latest.current;
    requested.current = next;
    setLoading(true);
    setFailure(null);
    try {
      const response = await fetch(`${REPORTS_URL}/${next.report}${reportQuery(next)}`, { credentials: "same-origin" });
      const body: unknown = await response.json().catch(() => null);
      if (call !== latest.current) return;
      const detail = (body as { detail?: unknown } | null)?.detail;
      const field = response.status === 422 ? fieldOf(detail) : null;
      if (response.ok && isAgentReport(body)) setReport(body);
      else if (field) setFieldError({ field, text: detailMessage(detail, FAILED) }); // the table on screen stays
      else if (response.status === 401) {
        setReport(null);
        setFailure({ text: SESSION_EXPIRED, expired: true });
      } else if (response.ok || response.status >= 500) setFailure({ text: FAILED, retry: true });
      else {
        setReport(null); // e.g. 403: the Reports permission was switched off since the page loaded
        setFailure({ text: detailMessage(detail, FAILED) });
      }
    } catch {
      if (call === latest.current) setFailure({ text: OFFLINE, retry: true });
    } finally {
      if (call === latest.current) setLoading(false);
    }
  }

  function select(index: number, moveFocus: boolean) {
    const tab = tabs[index];
    if (moveFocus) {
      tabRefs.current[index]?.focus();
      tabRefs.current[index]?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    }
    if (tab.key === state.report) return;
    const filters = Object.fromEntries(Object.entries(state.filters).filter(([key]) => tab.filters.includes(key as never)));
    void open({ report: tab.key, from: state.from, to: state.to, filters, offset: 0 }); // the dates carry across tabs
  }

  function onKeyDown(event: KeyboardEvent, index: number) {
    const move = MOVES[event.key];
    if (!move) return;
    event.preventDefault();
    select(move(index, tabs.length - 1), true);
  }

  function clear() {
    setResets((n) => n + 1);
    void open({ ...state, from: "", to: "", filters: {}, offset: 0 });
  }

  const filtered = Boolean(state.from || state.to || Object.values(state.filters).some(Boolean));
  const signIn = () => `${SIGN_IN_PATH}?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  const tabId = (key: string) => `${id}-tab-${key}`;
  const headingId = `${id}-heading`;
  const caption = [state.from && `from ${state.from}`, state.to && `to ${state.to}`, ...Object.values(state.filters)].filter(Boolean).join(", ") || "All dates";

  return (
    <div className="action-card agent-reports">
      <h2>Reports</h2>
      <div role="tablist" aria-label="Reports" className="report-tablist">
        {tabs.map((t, i) => (
          <button
            key={t.key} ref={(el) => { tabRefs.current[i] = el; }} id={tabId(t.key)} type="button" role="tab" className="s360-tab"
            aria-selected={t.key === active.key} aria-controls={`${id}-panel`} tabIndex={t.key === active.key ? 0 : -1}
            onClick={() => select(i, false)} onKeyDown={(e) => onKeyDown(e, i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div id={`${id}-panel`} role="tabpanel" aria-labelledby={tabId(active.key)}>
        {active.key === "commission" ? (
          <AgentCommissionReportPanel />
        ) : (
          <>
            <h3 id={headingId}>{active.heading}</h3>
            <p className="muted">{active.description}</p>
            <AgentReportFilters
              key={`${active.key}-${resets}`} tab={active} value={state} options={report?.options ?? {}} busy={loading} fieldError={fieldError}
              onApply={(draft) => void open({ ...state, ...draft, offset: 0 })} onClear={clear}
            />
            {loading && !report && (
              <div aria-busy="true">
                <p role="status">Loading report…</p>
                {[0, 1, 2, 3, 4].map((n) => <div key={n} className="kpi-skeleton report-skeleton" />)}
              </div>
            )}
            {failure && (
              <>
                <p className="form-error" role="alert">
                  {failure.text}
                  {failure.expired && <> <Link href={signIn()}>Sign in again</Link></>}
                </p>
                {failure.retry && (
                  <div className="actions">
                    <button type="button" className="btn secondary" onClick={() => void load(requested.current)}>Try again</button>
                  </div>
                )}
              </>
            )}
            {report && report.total === 0 && (
              <div role="status">
                {filtered ? (
                  <p>No records match these filters. <button type="button" className="btn small secondary" onClick={clear}>Clear filters</button></p>
                ) : (
                  <p>{EMPTY[active.key] ?? "No applications yet."}</p>
                )}
              </div>
            )}
            {report && report.total > 0 && (
              <>
                <div className="report-toolbar">
                  <p className="muted">{`${report.total} row${report.total === 1 ? "" : "s"} · As of ${new Date(report.as_of).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`}</p>
                  <ReportDownloadButton url={csvUrl(state)} label="Download CSV" filename={csvFilename(state.report, state.from, state.to)} hint="Up to 10,000 rows." contentType="text/csv" busyLabel="Preparing CSV…" />
                </div>
                <AgentReportTable
                  report={report} headingId={headingId} caption={caption} busy={loading} regionRef={region}
                  onPage={(offset) => { focusTable.current = true; void open({ ...state, offset }); }}
                />
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
