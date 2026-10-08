"use client";
import { useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { placementManagerSearch } from "@/lib/recruiter";
import { USERS_URL, formOptional, formText } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { announceUsersChanged } from "@/lib/usersChanged";
import { toneClass, welcomeLinkFeedback, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "recruiter-create-feedback";

// rec-001 (AC1; spec §5): creates a recruiter (placement_team, IT) through POST /admin/users with the nested profile. No password
// field: the recruiter sets their own from the emailed link. A failed save keeps everything typed. `managersAvailable`: null while
// the panel checks, false when no active placement manager exists. The AdminTelecallerCreateForm pattern, minus the team.
export default function AdminRecruiterCreateForm({ managersAvailable, onCreated }: { managersAvailable: boolean | null; onCreated: (employeeId: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const focus = useFocusAfterRender();
  const ready = managersAvailable === true;
  const inFlight = useRef(false); // `busy` only disables the button after a re-render, so a double click would POST twice

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const employeeId = formText(form, "employee_id");
    setBusy(true);
    const outcome = await sendJson(USERS_URL, "POST", {
      role: "placement_team", full_name: formText(form, "full_name"), email: formText(form, "email"), phone: formOptional(form, "phone"),
      recruiter_profile: { employee_id: employeeId, reporting_manager_user_id: formText(form, "manager") },
    });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback(welcomeLinkFeedback("Recruiter created.", outcome.data));
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
      <h3>Create recruiter</h3>
      <div className="field"><label htmlFor="rec-name">Full name (required)</label><input id="rec-name" name="full_name" required maxLength={160} disabled={busy} /></div>
      <div className="field"><label htmlFor="rec-email">Email (required)</label><input id="rec-email" name="email" type="email" required maxLength={255} autoComplete="off" disabled={busy} /></div>
      <div className="field"><label htmlFor="rec-phone">Mobile</label><input id="rec-phone" name="phone" type="tel" inputMode="tel" maxLength={40} disabled={busy} /></div>
      <div className="field"><label htmlFor="rec-employee-id">Employee ID (required)</label><input id="rec-employee-id" name="employee_id" required maxLength={40} disabled={busy} /></div>
      <SearchableSelect id="rec-manager" name="manager" label="Reporting manager (required)" noun="manager" required search={placementManagerSearch} disabled={busy || !ready} />
      {managersAvailable === false && <p className="muted" style={{ fontSize: 13 }}>No active placement manager — a Super Admin must create one first (Users → Placement Manager).</p>}
      <button className="btn" disabled={busy || !ready}>{busy ? "Creating…" : "Create recruiter"}</button>
      <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>
    </form>
  );
}
