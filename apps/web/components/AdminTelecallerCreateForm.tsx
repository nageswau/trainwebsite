"use client";
import { useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { TEAM_LABEL, USERS_URL, creatableTeams, formOptional, formText, managerSearch } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { announceUsersChanged } from "@/lib/usersChanged";
import { toneClass, welcomeLinkFeedback, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "telecaller-create-feedback";

// tel-001 (AC1, AC2; spec §6.3): creates a telecaller through POST /admin/users with the nested profile. No password field: the
// telecaller sets their own from the emailed link. A failed save keeps everything typed. The team list is display-only; the API
// decides (services/telecaller.CREATOR_TEAMS). `managersAvailable`: null while the panel checks, false when none exists.
export default function AdminTelecallerCreateForm({ role, managersAvailable, onCreated }: { role: string; managersAvailable: boolean | null; onCreated: (employeeId: string) => void }) {
  const teams = creatableTeams(role);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const focus = useFocusAfterRender();
  const ready = managersAvailable === true;

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const employeeId = formText(form, "employee_id");
    setBusy(true);
    const outcome = await sendJson(USERS_URL, "POST", {
      role: "telecaller", full_name: formText(form, "full_name"), email: formText(form, "email"), phone: formOptional(form, "phone"),
      telecaller_profile: { team: formText(form, "team"), employee_id: employeeId, reporting_manager_user_id: formText(form, "manager") },
    });
    setBusy(false);
    if (outcome.ok) {
      setFeedback(welcomeLinkFeedback("Telecaller created.", outcome.data));
      formEl.reset();
      announceUsersChanged();
      onCreated(employeeId);
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <form className="action-card form" onSubmit={submit} aria-describedby={FEEDBACK_ID}>
      <h3>Create telecaller</h3>
      <div className="field"><label htmlFor="tel-name">Full name (required)</label><input id="tel-name" name="full_name" required maxLength={160} disabled={busy} /></div>
      <div className="field"><label htmlFor="tel-email">Email (required)</label><input id="tel-email" name="email" type="email" required maxLength={255} autoComplete="off" disabled={busy} /></div>
      <div className="field"><label htmlFor="tel-phone">Mobile</label><input id="tel-phone" name="phone" type="tel" inputMode="tel" maxLength={40} disabled={busy} /></div>
      {teams.length === 1 ? (
        <div className="field">
          <span className="muted">Team</span> <strong>{TEAM_LABEL[teams[0]]}</strong>
          <input type="hidden" name="team" value={teams[0]} />
        </div>
      ) : (
        <div className="field">
          <label htmlFor="tel-team">Team (required)</label>
          <select id="tel-team" name="team" required disabled={busy}>
            {teams.map((t) => <option key={t} value={t}>{TEAM_LABEL[t]}</option>)}
          </select>
        </div>
      )}
      <div className="field"><label htmlFor="tel-employee-id">Employee ID (required)</label><input id="tel-employee-id" name="employee_id" required maxLength={40} disabled={busy} /></div>
      <SearchableSelect id="tel-manager" name="manager" label="Reporting manager (required)" noun="manager" required search={managerSearch} disabled={busy || !ready} />
      {managersAvailable === false && <p className="muted" style={{ fontSize: 13 }}>No active telecaller manager — a Super Admin must create one first.</p>}
      <button className="btn" disabled={busy || !ready}>{busy ? "Creating…" : "Create telecaller"}</button>
      <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>
    </form>
  );
}
