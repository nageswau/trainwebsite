"use client";
import { type FormEvent, useEffect, useId, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson } from "@/lib/apiErrors";
import {
  applicationUrl,
  isApplicationBody,
  isScreeningRead,
  type RecApplication,
  type Screening,
  SCREENING_LIMITS,
  type ScreeningFields,
  type ScreeningRead,
} from "@/lib/recruiterApplications";

// The form's own shape: the checkboxes stay booleans; everything else (numbers, the tri-state relocate) is a string until sent ("" = not given).
type Draft = { [K in keyof ScreeningFields]: ScreeningFields[K] extends boolean ? boolean : string };
const CHECKS = [
  ["qualification_verified", "Qualification verified"], ["experience_verified", "Experience verified"], ["skills_verified", "Skills verified"],
] as const;
const RATINGS = ["1", "2", "3", "4", "5"];
const REMARKS_NEEDED = "Remarks are required when the result is Rejected.";
const money = (v: number) => v.toLocaleString("en-IN", { maximumFractionDigits: 2 });
const yesNo = (v: boolean | null) => (v === null ? "" : v ? "yes" : "no");
const text = (v: string) => v.trim() || null;
const num = (v: string) => (v.trim() === "" ? null : Number(v));

function draftOf(s: Screening | null): Draft {
  return {
    qualification_verified: s?.qualification_verified ?? false, experience_verified: s?.experience_verified ?? false,
    skills_verified: s?.skills_verified ?? false, expected_salary: s?.expected_salary?.toString() ?? "",
    notice_days: s?.notice_days?.toString() ?? "", location_preference: s?.location_preference ?? "",
    communication_rating: s?.communication_rating?.toString() ?? "", technical_rating: s?.technical_rating?.toString() ?? "",
    availability: s?.availability ?? "", willing_to_relocate: yesNo(s?.willing_to_relocate ?? null), remarks: s?.remarks ?? "",
    result: s?.result ?? "",
  };
}

function bodyOf(d: Draft): ScreeningFields {
  return {
    qualification_verified: d.qualification_verified, experience_verified: d.experience_verified, skills_verified: d.skills_verified,
    expected_salary: num(d.expected_salary), notice_days: num(d.notice_days), location_preference: text(d.location_preference),
    communication_rating: num(d.communication_rating), technical_rating: num(d.technical_rating), availability: text(d.availability),
    willing_to_relocate: d.willing_to_relocate === "" ? null : d.willing_to_relocate === "yes", remarks: text(d.remarks), result: d.result,
  };
}

/** A reader's view: the saved answers as a list (salary is internal; this panel is recruiter-module only). */
function Summary({ screening, label }: { screening: Screening; label: string }) {
  const rating = (v: number | null) => (v === null ? "Not rated" : `${v} / 5`);
  const rows: [string, string][] = [
    ["Result", screening.result_label],
    ...CHECKS.map(([key, name]): [string, string] => [name, screening[key] ? "Yes" : "No"]),
    ["Expected salary (per year)", screening.expected_salary === null ? "—" : money(screening.expected_salary)],
    ["Notice period", screening.notice_days === null ? "—" : `${screening.notice_days} days`],
    ["Location preference", screening.location_preference ?? "—"],
    ["Communication skills", rating(screening.communication_rating)],
    ["Technical screening", rating(screening.technical_rating)],
    ["Availability", screening.availability ?? "—"],
    ["Willing to relocate", screening.willing_to_relocate === null ? "Not asked" : screening.willing_to_relocate ? "Yes" : "No"],
    ["Recruiter remarks", screening.remarks ?? "—"],
  ];
  return (
    <ul aria-label={label} style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 2 }}>
      {rows.map(([name, value]) => (
        <li key={name}><span className="muted">{name}:</span> <span style={{ overflowWrap: "anywhere", whiteSpace: "pre-line" }}>{value}</span></li>
      ))}
    </ul>
  );
}

/** rec-018 (spec §4): the §13 screening of one application. Writers on an open application edit the form (the API applies the result's
 *  status move, SC3); everyone else in the requirement's scope reads the summary. */
export default function RecruiterApplicationScreening({ applicationId, candidateName, onSaved, onCancel }: {
  applicationId: string; candidateName: string; onSaved: (a: RecApplication) => void; onCancel: () => void;
}) {
  const [data, setData] = useState<ScreeningRead | null>(null);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState<Draft>(draftOf(null));
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();
  const label = `Screening of ${candidateName}`;

  useEffect(() => {
    const controller = new AbortController();
    fetch(applicationUrl(applicationId, "/screening"), { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((body) => {
        if (!isScreeningRead(body)) return setFailed(true);
        setData(body);
        setDraft(draftOf(body.screening));
      })
      .catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [applicationId]);

  if (failed) return <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>Unable to load the screening.</p>;
  if (data === null) return <p className="muted" role="status" style={{ margin: 0, fontSize: 13 }}>Loading screening…</p>;
  if (!data.can_edit) {
    return data.screening ? <Summary screening={data.screening} label={label} /> : <p className="muted" style={{ margin: 0, fontSize: 13 }}>Not screened yet.</p>;
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => ({ ...d, [key]: value }));
  const rejected = draft.result === "rejected";

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (rejected && !draft.remarks.trim()) {
      setFailure(REMARKS_NEEDED);
      return;
    }
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(applicationUrl(applicationId, "/screening"), "PUT", bodyOf(draft));
    setBusy(false);
    if (outcome.ok && isApplicationBody(outcome.data)) onSaved(outcome.data.application);
    else setFailure(outcome.ok ? "Unable to save the screening." : outcome.message);
  }

  const field = { display: "grid", gap: 4 } as const;
  return (
    <form onSubmit={submit} aria-label={label} style={{ display: "grid", gap: 10 }}>
      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 12 }}>
        <legend className="muted" style={{ fontSize: 13, padding: 0, marginBottom: 4 }}>Verified</legend>
        {CHECKS.map(([key, name]) => (
          <label key={key} htmlFor={`${id}-${key}`} style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input id={`${id}-${key}`} type="checkbox" checked={draft[key]} onChange={(e) => set(key, e.target.checked)} />
            {name}
          </label>
        ))}
      </fieldset>
      <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" }}>
        <label htmlFor={`${id}-salary`} style={field}>
          Expected salary (per year)
          <input id={`${id}-salary`} type="number" inputMode="decimal" min={0} max={SCREENING_LIMITS.salaryMax} step="0.01" value={draft.expected_salary} onChange={(e) => set("expected_salary", e.target.value)} />
        </label>
        <label htmlFor={`${id}-notice`} style={field}>
          Notice period (days)
          <input id={`${id}-notice`} type="number" inputMode="numeric" min={0} max={SCREENING_LIMITS.noticeMax} step="1" value={draft.notice_days} onChange={(e) => set("notice_days", e.target.value)} />
        </label>
        <label htmlFor={`${id}-location`} style={field}>
          Location preference
          <input id={`${id}-location`} maxLength={SCREENING_LIMITS.location} value={draft.location_preference} onChange={(e) => set("location_preference", e.target.value)} />
        </label>
        <label htmlFor={`${id}-availability`} style={field}>
          Availability
          <input id={`${id}-availability`} maxLength={SCREENING_LIMITS.availability} placeholder="e.g. Immediate" value={draft.availability} onChange={(e) => set("availability", e.target.value)} />
        </label>
        {([["communication_rating", "Communication skills"], ["technical_rating", "Technical screening"]] as const).map(([key, name]) => (
          <label key={key} htmlFor={`${id}-${key}`} style={field}>
            {name}
            <select id={`${id}-${key}`} value={draft[key]} onChange={(e) => set(key, e.target.value)}>
              <option value="">Not rated</option>
              {RATINGS.map((r) => <option key={r} value={r}>{r} / 5</option>)}
            </select>
          </label>
        ))}
        <label htmlFor={`${id}-relocate`} style={field}>
          Willing to relocate
          <select id={`${id}-relocate`} value={draft.willing_to_relocate} onChange={(e) => set("willing_to_relocate", e.target.value)}>
            <option value="">Not asked</option>
            <option value="yes">Yes</option>
            <option value="no">No</option>
          </select>
        </label>
        <label htmlFor={`${id}-result`} style={field}>
          Result
          <select id={`${id}-result`} required value={draft.result} onChange={(e) => set("result", e.target.value)}>
            <option value="">Choose a result</option>
            {data.results.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
          </select>
        </label>
      </div>
      <label htmlFor={`${id}-remarks`} style={field}>
        {rejected ? "Recruiter remarks (required for Rejected)" : "Recruiter remarks"}
        <textarea id={`${id}-remarks`} rows={3} maxLength={SCREENING_LIMITS.remarks} aria-required={rejected} value={draft.remarks} onChange={(e) => set("remarks", e.target.value)} />
      </label>
      {data.screening && (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Last saved by {data.screening.screened_by.full_name} on <LocalTime value={data.screening.updated_at} time />
        </p>
      )}
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || !draft.result}>{busy ? "Saving…" : "Save screening"}</button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
