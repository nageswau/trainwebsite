"use client";

import { type FormEvent, useId, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import {
  collegeSearch, companyRequirementSearch, type Drive, driveBody, type DriveForm, DRIVES_URL, driveUrl, formProblem, isDrive, STATUS_OPTIONS,
} from "@/lib/recruiterDrives";
import { companySearch } from "@/lib/recruiterRequirements";

const MAX_REQUIREMENTS = 10;

/** rec-029: create or edit a campus drive -- its company (fixed once created), 1-10 of the company's live requirements, a BDM college or a
 *  typed name (DR2), the §21 fields and, on edit, its status (DR3). The API re-checks every rule; its message is shown as it comes. */
export default function RecruiterDriveForm({ initial, driveId, onSaved, onCancel }: {
  initial: DriveForm; driveId?: string; onSaved: (drive: Drive) => void; onCancel: () => void;
}) {
  const [form, setForm] = useState<DriveForm>(initial);
  const [picker, setPicker] = useState(0); // remounts the requirement picker after each pick
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const id = useId();
  const set = <K extends keyof DriveForm>(field: K, value: DriveForm[K]) => setForm((f) => ({ ...f, [field]: value }));

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const problem = formProblem(form);
    if (problem) return setFailure(problem);
    const body = driveBody(form, driveId ? initial : undefined);
    if (driveId && !Object.keys(body).length) return onCancel();
    setBusy(true);
    setFailure(null);
    const outcome = await sendJson(driveId ? driveUrl(driveId) : DRIVES_URL, driveId ? "PATCH" : "POST", body);
    setBusy(false);
    if (outcome.ok && isDrive(outcome.data)) return onSaved(outcome.data);
    setFailure(outcome.ok ? "The drive could not be saved. Try again." : outcome.message);
  }

  const addRequirement = (option: { id: string; label: string; detail?: string | null } | null) => {
    if (!option) return;
    if (!form.requirements.some((r) => r.id === option.id)) set("requirements", [...form.requirements, option]);
    setPicker((n) => n + 1);
  };

  return (
    <form onSubmit={submit} className="action-card" style={{ gap: 14 }} aria-label={driveId ? "Edit drive" : "New campus drive"} noValidate>
      <h3 style={{ margin: 0 }}>{driveId ? "Edit drive" : "New campus drive"}</h3>
      {driveId ? (
        <p style={{ margin: 0 }}><span className="muted">Company:</span> {form.company?.label}</p>
      ) : (
        <SearchableSelect label="Company" noun="company" required search={companySearch}
          onChange={(company) => setForm((f) => ({ ...f, company, requirements: [] }))} />
      )}

      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>Job requirements</legend>
        {form.requirements.length > 0 && (
          <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexWrap: "wrap", gap: 6 }}>
            {form.requirements.map((r) => (
              <li key={r.id} className="badge" style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                {r.label}{r.detail ? ` (${r.detail})` : ""}
                <button type="button" className="btn ghost small" aria-label={`Remove ${r.label}`}
                  onClick={() => set("requirements", form.requirements.filter((x) => x.id !== r.id))}>×</button>
              </li>
            ))}
          </ul>
        )}
        {form.company && form.requirements.length < MAX_REQUIREMENTS ? (
          <SearchableSelect key={`${form.company.id}-${picker}`} label="Add a job requirement" noun="requirement"
            search={companyRequirementSearch(form.company.id)} onChange={addRequirement} />
        ) : (
          <p className="muted" style={{ margin: 0, fontSize: 14 }}>
            {form.company ? `A drive can recruit for up to ${MAX_REQUIREMENTS} requirements.` : "Choose the company first."}
          </p>
        )}
      </fieldset>

      <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 8 }}>
        <legend style={{ fontWeight: 600, marginBottom: 4 }}>College</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="radio" name={`${id}-college-kind`} checked={!form.typed} onChange={() => set("typed", false)} /> From BDM colleges
          </label>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="radio" name={`${id}-college-kind`} checked={form.typed} onChange={() => set("typed", true)} /> Not in the list — type the name
          </label>
        </div>
        {form.typed ? (
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor={`${id}-college-name`}>College name</label>
            <input id={`${id}-college-name`} maxLength={200} value={form.collegeName} onChange={(e) => set("collegeName", e.target.value)} />
          </div>
        ) : (
          <SearchableSelect label="BDM college" noun="college" search={collegeSearch} initial={form.college} onChange={(c) => set("college", c)} />
        )}
      </fieldset>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(11rem, 1fr))", gap: 12 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${id}-date`}>Drive date</label>
          <input id={`${id}-date`} type="date" required value={form.drive_date} onChange={(e) => set("drive_date", e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${id}-role`}>Job role</label>
          <input id={`${id}-role`} maxLength={150} required value={form.job_role} onChange={(e) => set("job_role", e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${id}-vacancies`}>Vacancies</label>
          <input id={`${id}-vacancies`} type="number" inputMode="numeric" min={1} required value={form.vacancies} onChange={(e) => set("vacancies", e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${id}-registered`}>Students registered</label>
          <input id={`${id}-registered`} type="number" inputMode="numeric" min={0} value={form.registered} onChange={(e) => set("registered", e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label htmlFor={`${id}-attended`}>Students attended</label>
          <input id={`${id}-attended`} type="number" inputMode="numeric" min={0} aria-describedby={`${id}-attended-hint`} value={form.attended}
            onChange={(e) => set("attended", e.target.value)} />
          <span id={`${id}-attended-hint`} className="muted" style={{ fontSize: 13 }}>No more than registered.</span>
        </div>
        {driveId && (
          <div className="field" style={{ marginBottom: 0 }}>
            <label htmlFor={`${id}-status`}>Status</label>
            <select id={`${id}-status`} value={form.status} onChange={(e) => set("status", e.target.value as DriveForm["status"])}>
              {STATUS_OPTIONS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </div>
        )}
      </div>
      <div className="field" style={{ marginBottom: 0 }}>
        <label htmlFor={`${id}-eligibility`}>Eligibility (optional)</label>
        <textarea id={`${id}-eligibility`} rows={2} maxLength={1000} value={form.eligibility} onChange={(e) => set("eligibility", e.target.value)}
          placeholder="e.g. B.Tech 2026 batch, 60% and above, no active backlogs" />
      </div>
      {driveId && form.status === "cancelled" && initial.status !== "cancelled" && (
        <p className="muted" role="note" style={{ margin: 0 }}>A cancelled drive cannot be changed again or take new candidates.</p>
      )}
      {failure && <p className="form-error" role="alert" style={{ margin: 0 }}>{failure}</p>}
      <div className="actions" style={{ gap: 8 }}>
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : driveId ? "Save changes" : "Create drive"}</button>
        <button type="button" className="btn secondary" onClick={onCancel} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
