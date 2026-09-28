"use client";

import { useState } from "react";
import { COMPLETION_LABEL, type InternshipValues } from "@/lib/internship";
import { listText, splitList } from "@/lib/schoolStudents";

// ENH-021 (§22): the tracking fields of an internship entry, grouped per spec §11.2 F1. Controlled by PortfolioEntryForm; the skills
// text is kept raw while typing (so a trailing comma is not swallowed) and split on every change.
export default function InternshipFields({ values, onChange, disabled, attendanceError }: {
  values: InternshipValues; onChange: (next: InternshipValues) => void; disabled: boolean; attendanceError?: string | null;
}) {
  const [skillsText, setSkillsText] = useState(listText(values.skills_acquired));
  const set = (patch: InternshipValues) => onChange({ ...values, ...patch });
  return (
    <>
      <fieldset className="form-section">
        <legend>Mentor</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="pf-mentor">Mentor name (optional)</label>
            <input id="pf-mentor" className="search" maxLength={200} disabled={disabled} value={values.mentor_name ?? ""} onChange={(e) => set({ mentor_name: e.target.value || null })} />
          </div>
          <div className="field">
            <label htmlFor="pf-mentor-role">Mentor designation (optional)</label>
            <input id="pf-mentor-role" className="search" maxLength={200} disabled={disabled} value={values.mentor_designation ?? ""} onChange={(e) => set({ mentor_designation: e.target.value || null })} />
          </div>
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Progress</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="pf-completion">Completion</label>
            <select id="pf-completion" className="search" disabled={disabled} value={values.completion_status ?? ""} onChange={(e) => set({ completion_status: e.target.value || null })} aria-describedby="pf-completion-help">
              <option value="">No status</option>
              {Object.entries(COMPLETION_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <p id="pf-completion-help" className="field-help muted">A completed internship needs an end date.</p>
          </div>
          <div className="field">
            <label htmlFor="pf-attendance">Attendance % (optional)</label>
            <input id="pf-attendance" className="search" type="number" inputMode="numeric" min={0} max={100} step={1} disabled={disabled} value={values.attendance_percent ?? ""}
              aria-invalid={attendanceError ? true : undefined} aria-describedby={attendanceError ? "pf-attendance-error" : undefined}
              onChange={(e) => set({ attendance_percent: e.target.value === "" ? null : Number(e.target.value) })} />
            {attendanceError && <span id="pf-attendance-error" className="form-error">{attendanceError}</span>}
          </div>
        </div>
      </fieldset>
      <fieldset className="form-section">
        <legend>Outcome</legend>
        <div className="field">
          <label htmlFor="pf-skills">Skills acquired (optional)</label>
          <input id="pf-skills" className="search" disabled={disabled} value={skillsText} aria-describedby="pf-skills-help" onChange={(e) => { setSkillsText(e.target.value); const items = splitList(e.target.value); set({ skills_acquired: items.length ? items : null }); }} />
          <p id="pf-skills-help" className="field-help muted">Separate items with commas.</p>
        </div>
        <div className="field">
          <label htmlFor="pf-feedback">Feedback (optional)</label>
          <textarea id="pf-feedback" className="search" rows={3} maxLength={2000} disabled={disabled} value={values.feedback ?? ""} onChange={(e) => set({ feedback: e.target.value || null })} />
        </div>
      </fieldset>
    </>
  );
}
