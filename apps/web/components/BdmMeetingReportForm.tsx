"use client";
import { type ChangeEvent, type FormEvent, useEffect, useId, useState } from "react";

import type { BdmType } from "@/lib/bdm";
import { appointmentOutcomes, type MeetingReport, OUTCOME_LABEL, REPORT_FIELD_LABEL, REPORT_LIMITS, type ReportBody, todayIst } from "@/lib/bdmAppointments";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

type Initial = { outcome: string | null; next_follow_up_on: string | null; report: MeetingReport | null };
type Values = { outcome: string; discussion: string; requirements: string; opportunity: string; next_action: string; responsible_person: string; next_follow_up_on: string };
const LONG_FIELDS = ["requirements", "opportunity", "next_action"] as const;
const FIELD_ORDER = ["outcome", "discussion", ...LONG_FIELDS, "responsible_person", "next_follow_up_on"] as const;

// bdm-007 (spec §8): the meeting report -- filed to complete an appointment, or changed on the IST day it was filed. The API is the
// authority (lists, lengths, dates); this form only helps. Blanks are sent as null. Typed text is never cleared by a failed save:
// leaving with unsaved text asks first (QA7-06), and `locked` (the report can no longer change) keeps the text readable to copy.
export default function BdmMeetingReportForm({ bdmType, mode, initial, busy, errors = {}, locked = false, onSubmit, onCancel }: {
  bdmType: BdmType; mode: "complete" | "edit"; initial?: Initial; busy: boolean; errors?: Record<string, string>; locked?: boolean;
  onSubmit: (body: ReportBody) => void; onCancel: () => void;
}) {
  const id = useId();
  const r = initial?.report;
  const [start] = useState<Values>({
    outcome: initial?.outcome ?? "", discussion: r?.discussion ?? "", requirements: r?.requirements ?? "", opportunity: r?.opportunity ?? "",
    next_action: r?.next_action ?? "", responsible_person: r?.responsible_person ?? "", next_follow_up_on: initial?.next_follow_up_on ?? "",
  });
  const [v, setV] = useState<Values>(start);
  useLeaveGuard(!busy && FIELD_ORDER.some((key) => v[key] !== start[key]), "Discard this meeting report?");
  useEffect(() => {
    const first = FIELD_ORDER.find((key) => errors[key]);
    if (first) document.getElementById(`${id}-${first}`)?.focus();
  }, [errors, id]);
  const set = (key: keyof Values) => (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setV({ ...v, [key]: e.target.value });
  const fid = (key: string) => `${id}-${key}`;
  const invalid = (key: string) => ({ "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `${fid(key)}-error` : undefined });
  const error = (key: string) => errors[key] && <p id={`${fid(key)}-error`} className="form-error">{errors[key]}</p>;
  const ready = Boolean(v.outcome && v.discussion.trim());
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    const text = (s: string) => s.trim() || null;
    onSubmit({
      outcome: v.outcome, discussion: v.discussion, requirements: text(v.requirements), opportunity: text(v.opportunity),
      next_action: text(v.next_action), responsible_person: text(v.responsible_person), next_follow_up_on: v.next_follow_up_on || null,
    });
  };
  return (
    <form aria-label={mode === "complete" ? "Meeting report" : "Edit meeting report"} className="action-card" onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={fid("outcome")}>Outcome (required)</label>
        <select id={fid("outcome")} autoFocus required aria-required="true" disabled={locked} value={v.outcome} onChange={set("outcome")} {...invalid("outcome")}>
          <option value="">Choose an outcome</option>
          {appointmentOutcomes(bdmType).map((o) => <option key={o} value={o}>{OUTCOME_LABEL[o]}</option>)}
        </select>
        {error("outcome")}
      </div>
      <div className="field">
        <label htmlFor={fid("discussion")}>Discussion (required)</label>
        <textarea id={fid("discussion")} required aria-required="true" readOnly={locked} rows={4} maxLength={REPORT_LIMITS.discussion} value={v.discussion} onChange={set("discussion")} {...invalid("discussion")} />
        <p className="field-hint">What was discussed. Up to 4,000 characters.</p>
        {error("discussion")}
      </div>
      {LONG_FIELDS.map((key) => (
        <div className="field" key={key}>
          <label htmlFor={fid(key)}>{REPORT_FIELD_LABEL[key]}</label>
          <textarea id={fid(key)} readOnly={locked} rows={2} maxLength={REPORT_LIMITS[key]} value={v[key]} onChange={set(key)} {...invalid(key)} />
          {error(key)}
        </div>
      ))}
      <div className="field">
        <label htmlFor={fid("responsible_person")}>Responsible person</label>
        <input id={fid("responsible_person")} readOnly={locked} maxLength={REPORT_LIMITS.responsible_person} value={v.responsible_person} onChange={set("responsible_person")} {...invalid("responsible_person")} />
        {error("responsible_person")}
      </div>
      <div className="field">
        <label htmlFor={fid("next_follow_up_on")}>Next follow-up (IST date)</label>
        <input id={fid("next_follow_up_on")} type="date" readOnly={locked} min={todayIst()} value={v.next_follow_up_on} onChange={set("next_follow_up_on")} {...invalid("next_follow_up_on")} />
        <p className="field-hint">A date creates one follow-up for you.</p>
        {error("next_follow_up_on")}
      </div>
      <div className="actions">
        {!locked && (
          <button type="submit" className="btn small" disabled={busy || !ready}>
            {busy ? "Saving…" : mode === "complete" ? "Save report and complete" : "Save changes"}
          </button>
        )}
        <button type="button" className="btn secondary small" onClick={onCancel}>{locked ? "Close" : "Cancel"}</button>
      </div>
    </form>
  );
}
