"use client";
import Link from "next/link";
import { type FormEvent, useId, useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import RecruiterFollowUpForm, { type ContactOption } from "@/components/RecruiterFollowUpForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { COMPANIES_PATH, RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { followUpUrl, isRecFollowUp, OUTCOME_MAX, reasonLabel, type RecFollowUp } from "@/lib/recruiterFollowUps";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

/** FU7: "Mark done" asks what came of it (optional). Escape keeps it open. */
function DoneForm({ busy, onSubmit, onCancel }: { busy: boolean; onSubmit: (outcome: string | null) => void; onCancel: () => void }) {
  const [outcome, setOutcome] = useState("");
  const id = useId();
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit(outcome.trim() || null);
  };
  return (
    <form aria-label="Mark follow-up done" className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      <div className="field">
        <label htmlFor={id}>Outcome (optional)</label>
        <textarea id={id} autoFocus rows={2} maxLength={OUTCOME_MAX} value={outcome} aria-describedby={`${id}-count`} onChange={(e) => setOutcome(e.target.value)} />
        <p id={`${id}-count`} className="muted" style={{ margin: 0 }}>{outcome.length}/{OUTCOME_MAX}</p>
      </div>
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : "Mark done"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Keep it open</button>
      </div>
    </form>
  );
}

/** rec-024 (spec §4): one follow-up with its actions -- Done (with an optional outcome), Reschedule and Cancel (with a reason) -- offered
 *  only when the API says the caller may change it (`can_change`). `card` is the daily-list form (the company first, linked); without it
 *  the item sits on its company's page. A refusal (changed elsewhere: 403/404/409) is handed up so the list reloads. */
export default function RecruiterFollowUpItem({ followUp: fu, card = false, contacts, onChanged, onRefused }: {
  followUp: RecFollowUp; card?: boolean; contacts?: ContactOption[]; onChanged: (fu: RecFollowUp, notice: string) => void;
  onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "done" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const id = useId();

  async function act(action: "complete" | "cancel", body: unknown, notice: string) {
    setBusy(true);
    setFailure(null);
    setSessionEnded(false);
    const result = await sendJson(followUpUrl(fu.id, action), "POST", body);
    setBusy(false);
    if (result.ok) return isRecFollowUp(result.data) ? onChanged(result.data, notice) : setFailure(SAVE_FAILED);
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message);
  }

  const facts = [
    card && ["Reason", reasonLabel(fu.reason)],
    ["Due", formatSchoolDateTime(fu.due_at, true)],
    fu.contact && ["Contact", fu.contact.name],
    fu.requirement && ["Requirement", fu.requirement.title],
    card && ["Recruiter", fu.company.assigned_recruiter?.full_name ?? "Unassigned"],
  ].filter(Boolean) as [string, string][];
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        {card ? (
          <strong id={`${id}-title`}>
            <Link href={`${COMPANIES_PATH}/${encodeURIComponent(fu.company.id)}`} style={LINK_STYLE}>{fu.company.name}</Link>{" "}
            <span className="muted" style={{ fontWeight: 400 }}>{fu.company.code}</span>
          </strong>
        ) : (
          <strong id={`${id}-title`}>{reasonLabel(fu.reason)}</strong>
        )}
        {fu.overdue && <span className="badge status error">Overdue</span>}
        {fu.status === "done" && <span className="badge">Done</span>}
        {fu.status === "cancelled" && <span className="badge">Cancelled</span>}
      </div>
      <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: 0 }}>
        {facts.map(([term, value]) => (
          <div key={term}>
            <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
            <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
          </div>
        ))}
      </dl>
      {fu.notes && <p style={{ ...TEXT, margin: 0 }}>{fu.notes}</p>}
      {fu.completed_at && (
        <p className="muted" style={{ ...TEXT, margin: 0 }}>
          Done {formatSchoolDateTime(fu.completed_at)}{fu.completed_by && ` by ${fu.completed_by.full_name}`}{fu.outcome && ` — ${fu.outcome}`}
        </p>
      )}
      {fu.cancelled_at && <p className="muted" style={{ ...TEXT, margin: 0 }}>Cancelled {formatSchoolDateTime(fu.cancelled_at)}{fu.cancel_reason && ` — ${fu.cancel_reason}`}</p>}
      {mode === "edit" && (
        <RecruiterFollowUpForm companyId={fu.company.id} contacts={contacts} followUp={fu} onCancel={() => setMode("view")}
          onSaved={(next) => { setMode("view"); onChanged(next, "Follow-up updated."); }} />
      )}
      {mode === "done" && (
        <DoneForm busy={busy} onCancel={() => setMode("view")} onSubmit={(outcome) => void act("complete", { outcome }, "Marked done.")} />
      )}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel follow-up" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void act("cancel", { reason }, "Follow-up cancelled.")} onCancel={() => setMode("view")} />
      )}
      {mode === "view" && fu.can_change && (
        <div className="actions">
          <button type="button" className="btn small" onClick={() => setMode("done")}>Done</button>
          <button type="button" className="btn secondary small" onClick={() => setMode("edit")}>Reschedule</button>
          <button type="button" className="btn secondary small" onClick={() => setMode("cancel")}>Cancel follow-up</button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />
        </div>
      )}
    </li>
  );
}
