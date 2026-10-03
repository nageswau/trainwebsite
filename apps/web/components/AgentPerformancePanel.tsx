"use client";

import Link from "next/link";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import FormMessage from "@/components/FormMessage";
import { TableRegion, headingId, n } from "@/components/AgentTableRegion";
import { SESSION_EXPIRED, SIGN_IN_PATH } from "@/lib/activityFeedback";
import { detailMessage } from "@/lib/apiErrors";
import { type DateRange, readRange, reportQuery, writeRange } from "@/lib/agentCommissionReport";
import { type AgentPerformance, type AgentPerformanceCounts, PERFORMANCE_URL, funnelStages, isPerformance } from "@/lib/agentPerformance";

// AGN-019 (DEC-SCOPE-065; spec §6.4): a Master's per-staff counts and student funnel for a cohort of students. The data flow is
// AgentCommissionReportPanel's (range in the address, older responses dropped, field errors, sign-in on 401); the server refuses
// staff (403) regardless of what renders here.
type Field = "from" | "to";
type Failure = { text: string; retry?: boolean; expired?: boolean };

const NONE: DateRange = { from: "", to: "" };
const AGENCY = "agency";
const TOTAL_LABEL = "All staff and unassigned";
const FAILED = "Couldn't load staff performance.";
const OFFLINE = "Staff performance could not load. Check your connection and try again.";
const FIELD_LABEL: Record<Field, string> = { from: "'From'", to: "'To'" };
const TABLE_TITLE = "By staff member";
// Each count column once: its field and its header (also the phone layout's per-cell label).
const COLUMNS = [
  ["students", "Students"],
  ["applications", "Applications"],
  ["offers", "Offers"],
  ["visa_applications", "Visa applications"],
  ["visa_approvals", "Visa approvals"],
  ["enrollments", "Enrollments"],
] as const;
const HEAD = ["Staff", ...COLUMNS.map(([, label]) => label)];

type Choice = { value: string; label: string; counts: AgentPerformanceCounts };

function choices(data: AgentPerformance): Choice[] {
  return [
    { value: AGENCY, label: TOTAL_LABEL, counts: data.total },
    ...data.rows.map((r) => ({ value: r.code, label: `${r.name} (${r.code})${r.active ? "" : " — deactivated"}`, counts: r })),
    ...(data.unassigned ? [{ value: "unassigned", label: "Unassigned", counts: data.unassigned }] : []),
  ];
}

function Funnel({ data, selected, onSelect }: { data: AgentPerformance; selected: string; onSelect: (value: string) => void }) {
  const selectId = useId();
  const options = choices(data);
  const current = options.find((o) => o.value === selected) ?? options[0];
  return (
    <section className="kpi-group">
      <h3>Funnel</h3>
      <div className="field">
        <label htmlFor={selectId}>Show funnel for</label>
        <select id={selectId} value={current.value} onChange={(e) => onSelect(e.target.value)}>
          {options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <ol className="funnel" aria-label={`Student funnel: ${current.label}`}>
        {funnelStages(current.counts.funnel).map((s) => (
          <li className="funnel-row" key={s.key}>
            <span className="funnel-label">{s.label}</span>
            <span className="funnel-count">{n(s.count)}</span>
            <span className="funnel-percent muted">{s.percent === null ? "—" : `${s.percent}% of students`}</span>
            <span className="funnel-track" aria-hidden="true">
              {s.count > 0 && <span className="funnel-fill" style={{ width: `${Math.min(100, Math.max(2, s.percent ?? 0))}%` }} />}
            </span>
          </li>
        ))}
      </ol>
      <p className="kpi-note muted">Includes archived students and withdrawn applications. A student counts at every stage up to the furthest one reached.</p>
    </section>
  );
}

function CountCells({ counts }: { counts: AgentPerformanceCounts }) {
  return COLUMNS.map(([key, label]) => (
    <td key={key} data-label={label}>
      {n(counts[key])}
    </td>
  ));
}

function StaffTable({ data }: { data: AgentPerformance }) {
  return (
    <section className="kpi-group">
      <h3 id={headingId(TABLE_TITLE)}>{TABLE_TITLE}</h3>
      <TableRegion title={TABLE_TITLE} head={HEAD} stack>
        {data.rows.map((r) => (
          <tr key={r.code}>
            <th scope="row">
              {r.name} <span className="muted">{r.code}</span>
              {!r.active && (
                <>
                  {" "}
                  <span className="badge">Deactivated</span>
                </>
              )}
            </th>
            <CountCells counts={r} />
          </tr>
        ))}
        {data.unassigned && (
          <tr>
            <th scope="row">Unassigned</th>
            <CountCells counts={data.unassigned} />
          </tr>
        )}
        <tr>
          <th scope="row">{TOTAL_LABEL}</th>
          <CountCells counts={data.total} />
        </tr>
      </TableRegion>
    </section>
  );
}

export default function AgentPerformancePanel() {
  const [draft, setDraft] = useState<DateRange>(NONE);
  const [applied, setApplied] = useState<DateRange>(NONE);
  const [data, setData] = useState<AgentPerformance | null>(null);
  const [selected, setSelected] = useState(AGENCY);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [fieldError, setFieldError] = useState<{ field: Field; text: string } | null>(null);
  const latest = useRef(0);
  const requested = useRef<DateRange>(NONE); // what "Try again" reloads
  const inputs = { from: useRef<HTMLInputElement>(null), to: useRef<HTMLInputElement>(null) };
  const fieldErrorId = useId();

  async function load(range: DateRange) {
    const id = ++latest.current; // a response for an older request is dropped
    requested.current = range;
    setLoading(true);
    setFailure(null);
    try {
      const response = await fetch(`${PERFORMANCE_URL}${reportQuery(range.from, range.to)}`, { credentials: "same-origin" });
      const body: unknown = await response.json().catch(() => null);
      if (id !== latest.current) return;
      const detail = (body as { detail?: unknown } | null)?.detail;
      if (response.ok && isPerformance(body)) {
        setData(body);
        setSelected(AGENCY); // a new range is a new cohort: start from the agency
        setApplied(range);
        writeRange(range);
      } else if (response.status === 422) {
        // A rejected input is a field error; the figures on screen stay and there is nothing to retry.
        const text = detailMessage(detail, FAILED);
        const field: Field = text.includes("date_from") ? "from" : "to";
        setFieldError({ field, text: text.replace(/date_from/g, FIELD_LABEL.from).replace(/date_to/g, FIELD_LABEL.to) });
        inputs[field].current?.focus();
      } else if (response.status === 401) {
        setData(null);
        setFailure({ text: SESSION_EXPIRED, expired: true });
      } else if (response.ok || response.status >= 500) {
        setFailure({ text: FAILED, retry: true });
      } else {
        setData(null); // e.g. 403: this account may no longer see the page
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
      inputs.to.current?.focus();
      return;
    }
    setFieldError(null);
    void load(draft);
  }

  function edit(change: Partial<DateRange>) {
    setDraft({ ...draft, ...change });
    setFieldError(null);
  }

  const filtered = Boolean(applied.from || applied.to);
  const signIn = () => `${SIGN_IN_PATH}?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  const described = (field: Field) => (fieldError?.field === field ? { "aria-invalid": true as const, "aria-describedby": fieldErrorId } : {});

  return (
    <div className="action-card staff-performance" aria-busy={loading}>
      <form aria-label="Staff performance filters" onSubmit={apply} className="actions">
        <div className="field">
          <label htmlFor="staff-performance-from">From</label>
          <input id="staff-performance-from" ref={inputs.from} type="date" value={draft.from} onChange={(e) => edit({ from: e.target.value })} {...described("from")} />
        </div>
        <div className="field">
          <label htmlFor="staff-performance-to">To</label>
          <input id="staff-performance-to" ref={inputs.to} type="date" value={draft.to} onChange={(e) => edit({ to: e.target.value })} {...described("to")} />
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
      {loading && <p role="status">{data ? "Updating staff performance…" : "Loading staff performance…"}</p>}
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
      {data && (
        <>
          <p className="muted">
            Students added {filtered ? "in this period" : "at any time"}. Figures as of{" "}
            {new Date(data.as_of).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}.
          </p>
          {data.total.funnel.students === 0 ? (
            <p>{filtered ? "No students were added in this period." : "Your agency has no students yet."}</p>
          ) : (
            <Funnel data={data} selected={selected} onSelect={setSelected} />
          )}
          {/* Review #2: an agency with no staff rows still has Unassigned and total figures to show. */}
          {(data.rows.length > 0 || data.unassigned) && <StaffTable data={data} />}
        </>
      )}
    </div>
  );
}
