"use client";
import { useRef, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { headSearch } from "@/lib/partnership";
import { USERS_URL, formOptional, formText } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { announceUsersChanged } from "@/lib/usersChanged";
import { toneClass, welcomeLinkFeedback, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "partnership-create-feedback";

// upc-001 (AC1; spec §6): creates a partnership manager through POST /admin/users with the nested profile -- the
// AdminTelecallerCreateForm pattern. No password field: the manager sets their own from the emailed link; the division is always
// Overseas (the API sets it). A failed save keeps everything typed. `headsAvailable`: null while the panel checks, false when none.
export default function AdminPartnershipCreateForm({ headsAvailable, onCreated }: { headsAvailable: boolean | null; onCreated: (employeeId: string) => void }) {
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const focus = useFocusAfterRender();
  const ready = headsAvailable === true;
  // `busy` only disables the button after a re-render, so a second click in the same instant would POST again (tel-001 QA-05).
  const inFlight = useRef(false);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formEl = event.currentTarget;
    const form = new FormData(formEl);
    const employeeId = formText(form, "employee_id");
    setBusy(true);
    const outcome = await sendJson(USERS_URL, "POST", {
      role: "partnership_manager", full_name: formText(form, "full_name"), email: formText(form, "email"), phone: formOptional(form, "phone"),
      partnership_profile: { employee_id: employeeId, reporting_head_user_id: formText(form, "head") },
    });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback(welcomeLinkFeedback("Partnership manager created.", outcome.data));
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
      <h3>Create partnership manager</h3>
      <div className="field"><label htmlFor="pm-name">Full name (required)</label><input id="pm-name" name="full_name" required maxLength={160} disabled={busy} /></div>
      <div className="field"><label htmlFor="pm-email">Email (required)</label><input id="pm-email" name="email" type="email" required maxLength={255} autoComplete="off" disabled={busy} /></div>
      <div className="field"><label htmlFor="pm-phone">Mobile</label><input id="pm-phone" name="phone" type="tel" inputMode="tel" maxLength={40} disabled={busy} /></div>
      <div className="field"><label htmlFor="pm-employee-id">Employee ID (required)</label><input id="pm-employee-id" name="employee_id" required maxLength={40} disabled={busy} /></div>
      <SearchableSelect id="pm-head" name="head" label="Reporting head (required)" noun="head" required search={headSearch} disabled={busy || !ready} />
      {headsAvailable === false && <p className="muted" style={{ fontSize: 13 }}>No active partnership head — a Super Admin must create one first.</p>}
      <button className="btn" disabled={busy || !ready}>{busy ? "Creating…" : "Create partnership manager"}</button>
      <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
        {feedback?.text}
      </div>
    </form>
  );
}
