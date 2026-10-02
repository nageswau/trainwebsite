"use client";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { BDM_TYPE_LABEL, USERS_URL, creatableTypes, formOptional, formText, type BdmManagerOption } from "@/lib/bdm";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { announceUsersChanged } from "@/lib/usersChanged";
import { toneClass, welcomeLinkFeedback, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "bdm-create-feedback";

// bdm-001 (AC01, spec §6.3): creates a BDM through POST /admin/users with the nested profile. There is no password field: the BDM
// sets their own from the emailed link. A failed save keeps everything typed.
export default function AdminBdmCreateForm({ role, managers, onCreated }: { role: string; managers: BdmManagerOption[] | null; onCreated: () => void }) {
  const types = creatableTypes(role);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const focus = useFocusAfterRender();
  const noManagers = managers !== null && managers.length === 0;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    setBusy(true);
    const outcome = await sendJson(USERS_URL, "POST", {
      role: "bdm", full_name: formText(form, "full_name"), email: formText(form, "email"), phone: formOptional(form, "phone"),
      bdm_profile: {
        bdm_type: formText(form, "bdm_type"), employee_id: formText(form, "employee_id"), designation: formOptional(form, "designation"),
        department: formOptional(form, "department"), territory: formOptional(form, "territory"), reporting_manager_user_id: formText(form, "manager"),
      },
    });
    setBusy(false);
    if (outcome.ok) {
      setFeedback(welcomeLinkFeedback("BDM created.", outcome.data));
      formEl.reset();
      announceUsersChanged();
      onCreated();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <form className="action-card form" onSubmit={submit} aria-describedby={FEEDBACK_ID}>
      <h3>Create BDM</h3>
      <div className="field"><label htmlFor="bdm-name">Full name (required)</label><input id="bdm-name" name="full_name" required maxLength={160} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-email">Email (required)</label><input id="bdm-email" name="email" type="email" required maxLength={255} autoComplete="off" disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-phone">Mobile</label><input id="bdm-phone" name="phone" type="tel" inputMode="tel" maxLength={40} disabled={busy} /></div>
      {types.length === 1 ? (
        <div className="field">
          <span className="muted">Module</span> <strong>{BDM_TYPE_LABEL[types[0]]}</strong>
          <input type="hidden" name="bdm_type" value={types[0]} />
        </div>
      ) : (
        <div className="field">
          <label htmlFor="bdm-type">Module (required)</label>
          <select id="bdm-type" name="bdm_type" required disabled={busy}>
            {types.map((t) => <option key={t} value={t}>{BDM_TYPE_LABEL[t]}</option>)}
          </select>
        </div>
      )}
      <div className="field"><label htmlFor="bdm-employee-id">Employee ID (required)</label><input id="bdm-employee-id" name="employee_id" required maxLength={40} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-designation">Designation</label><input id="bdm-designation" name="designation" maxLength={120} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-department">Department</label><input id="bdm-department" name="department" maxLength={120} disabled={busy} /></div>
      <div className="field"><label htmlFor="bdm-territory">Territory</label><input id="bdm-territory" name="territory" maxLength={120} disabled={busy} /></div>
      <div className="field">
        <label htmlFor="bdm-manager">Reporting manager (required)</label>
        <select id="bdm-manager" name="manager" required disabled={busy || managers === null || noManagers} defaultValue="">
          <option value="" disabled>{managers === null ? "Loading managers…" : "Select a manager"}</option>
          {(managers ?? []).map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
        </select>
        {noManagers && <p className="muted" style={{ fontSize: 13 }}>No active BDM manager — a Super Admin must create one first.</p>}
      </div>
      <button className="btn" disabled={busy || managers === null || noManagers}>{busy ? "Creating…" : "Create BDM"}</button>
      <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>
    </form>
  );
}
