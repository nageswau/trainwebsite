"use client";

import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import FormMessage from "@/components/FormMessage";
import { FILTER_LABEL, type FilterKey, OPTION_LIST, type ReportState, type ReportTab } from "@/lib/agentReports";
import type { AgentReportOptions } from "@/lib/types";

// AGN-020 (DEC-SCOPE-063; spec §6.2): the filters of one report -- dates, then a select per filter the report offers, each option
// from the server's `options` (the caller's own scope). A field error (client or server 422) sits under the form, is tied to its
// control (`aria-describedby`, `aria-invalid`) and takes focus. Apply stays focusable while a report loads (`aria-disabled`).

export type ReportField = "from" | "to" | FilterKey;
export type FieldError = { field: ReportField; text: string };
type Draft = Pick<ReportState, "from" | "to" | "filters">;

const ALL: Record<FilterKey, string> = { member: "All staff", country: "All countries", university: "All universities", intake: "All intakes", status: "Any status" };
const RANGE_ORDER = "'To' must be on or after 'From'";

export default function AgentReportFilters({ tab, value, options, busy, fieldError, onApply, onClear }: {
  tab: ReportTab;
  value: ReportState;
  options: AgentReportOptions;
  busy: boolean;
  fieldError: FieldError | null;
  onApply: (draft: Draft) => void;
  onClear: () => void;
}) {
  const [draft, setDraft] = useState<Draft>({ from: value.from, to: value.to, filters: value.filters });
  const [localError, setLocalError] = useState<FieldError | null>(null);
  const id = useId();
  const controls = useRef<Partial<Record<ReportField, HTMLInputElement | HTMLSelectElement | null>>>({});
  const error = localError ?? fieldError;

  useEffect(() => {
    if (fieldError) controls.current[fieldError.field]?.focus();
  }, [fieldError]);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (draft.from && draft.to && draft.to < draft.from) {
      setLocalError({ field: "to", text: RANGE_ORDER });
      controls.current.to?.focus();
      return;
    }
    setLocalError(null);
    const filters = Object.fromEntries(Object.entries(draft.filters).filter(([, v]) => v)) as Draft["filters"];
    onApply({ from: draft.from, to: draft.to, filters });
  }

  function edit(change: Partial<Draft>) {
    setDraft({ ...draft, ...change });
    setLocalError(null); // the error described the old values
  }

  const errorId = `${id}-error`;
  const described = (field: ReportField) => (error?.field === field ? { "aria-invalid": true as const, "aria-describedby": errorId } : {});
  const fieldId = (field: ReportField) => `${id}-${field}`;
  const hasFilters = Boolean(value.from || value.to || Object.values(value.filters).some(Boolean));

  return (
    <>
      <form aria-label="Report filters" onSubmit={apply} className="analytics-form">
        {(["from", "to"] as const).map((field) => (
          <div className="field" style={{ margin: 0 }} key={field}>
            <label htmlFor={fieldId(field)}>{field === "from" ? "From" : "To"}</label>
            <input
              id={fieldId(field)} type="date" value={draft[field]} ref={(el) => { controls.current[field] = el; }}
              onChange={(e) => edit({ [field]: e.target.value })} {...described(field)}
            />
          </div>
        ))}
        {tab.filters.map((key) => (
          <div className="field" style={{ margin: 0 }} key={key}>
            <label htmlFor={fieldId(key)}>{FILTER_LABEL[key]}</label>
            <select
              id={fieldId(key)} value={draft.filters[key] ?? ""} ref={(el) => { controls.current[key] = el; }}
              onChange={(e) => edit({ filters: { ...draft.filters, [key]: e.target.value } })} {...described(key)}
            >
              <option value="">{ALL[key]}</option>
              {(options[OPTION_LIST[key]] ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        ))}
        <button className="btn" type="submit" aria-disabled={busy}>Apply</button>
        {hasFilters && <button className="btn secondary" type="button" onClick={onClear}>Clear filters</button>}
      </form>
      {error && (
        <div id={errorId}>
          <FormMessage message={{ text: error.text, failed: true }} />
        </div>
      )}
    </>
  );
}
