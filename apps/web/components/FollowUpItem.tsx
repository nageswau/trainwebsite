"use client";
import Link from "next/link";
import { useId, useState } from "react";

import BdmAppointmentReasonForm from "@/components/BdmAppointmentReasonForm";
import FollowUpForm from "@/components/FollowUpForm";
import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { LINK_STYLE } from "@/lib/bdmOrganizations";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { TELECALLER_SIGN_IN } from "@/lib/navigation";
import { followUpUrl, isFollowUp, reasonLabel, type FollowUp } from "@/lib/telecallerFollowUps";
import { PRIORITY_LABEL } from "@/lib/telecallerLeads";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;

/** tel-011 (spec §4): one follow-up with its actions -- Done, Reschedule, Cancel (with a reason) -- offered only when the API says the
 *  caller may change it (`can_change`). `card` is the §7 "Today's follow-ups" card (student, interest, action + time, priority) for the
 *  lists; without it the item sits on its lead's page. A refusal (changed elsewhere: 403/404/409) is handed up so the list reloads. */
export default function FollowUpItem({ followUp: fu, card, leadBasePath, showTelecaller = false, onChanged, onRefused }: {
  followUp: FollowUp; card?: boolean; leadBasePath?: string; showTelecaller?: boolean; onChanged: (fu: FollowUp, notice: string) => void;
  onRefused: (message: string) => void;
}) {
  const [mode, setMode] = useState<"view" | "edit" | "cancel">("view");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [sessionEnded, setSessionEnded] = useState(false);
  const id = useId();
  const when = formatSchoolDateTime(fu.due_at, true);

  async function act(action: "complete" | "cancel", body: unknown, notice: string) {
    setBusy(true);
    setFailure(null);
    setSessionEnded(false);
    const result = await sendJson(followUpUrl(fu.id, action), "POST", body);
    setBusy(false);
    if (result.ok) return isFollowUp(result.data) ? onChanged(result.data, notice) : setFailure(SAVE_FAILED);
    const kind = writeFailure(result.status);
    if (kind === "changed") return onRefused(result.message);
    if (kind === "session") return setSessionEnded(true);
    setFailure(kind === "retry" ? SAVE_FAILED : result.message);
  }

  const action = fu.next_action ?? reasonLabel(fu.reason);
  // QA-01: the action card's 16px grid gap is too loose between these short lines
  return (
    <li className="action-card" style={{ listStyle: "none", gap: 6 }} aria-labelledby={`${id}-title`}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "baseline" }}>
        {card ? (
          <strong id={`${id}-title`}><Link href={`${leadBasePath}/${encodeURIComponent(fu.lead.id)}`} style={LINK_STYLE}>{fu.lead.name}</Link></strong>
        ) : (
          <strong id={`${id}-title`}>{reasonLabel(fu.reason)}</strong>
        )}
        {fu.overdue && <span className="badge status error">Overdue</span>}
        {fu.status === "done" && <span className="badge">Done</span>}
        {fu.status === "cancelled" && <span className="badge">Cancelled</span>}
      </div>
      {card ? (
        <dl style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(10rem, 1fr))", gap: "4px 16px", margin: 0 }}>
          {([
            ["Interest", fu.lead.product?.name ?? "—"], ["Action", `${action} · ${when}`], ["Priority", PRIORITY_LABEL[fu.lead.priority] ?? fu.lead.priority],
            ["Reason", reasonLabel(fu.reason)], ["Lead", `${fu.lead.lead_code} · ${fu.lead.status_label}`],
            ...(showTelecaller ? [["Telecaller", fu.lead.telecaller?.full_name ?? "Unassigned"]] : []),
          ] as [string, string][]).map(([term, value]) => (
            <div key={term}>
              <dt className="muted" style={{ fontSize: 13 }}>{term}</dt>
              <dd style={{ margin: 0, overflowWrap: "anywhere" }}>{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <>
          <p className="muted" style={{ margin: 0 }}>Due {when}</p>
          {fu.next_action && <p style={{ ...TEXT, margin: 0 }}><span className="muted">Next action: </span>{fu.next_action}</p>}
        </>
      )}
      {fu.notes && <p style={{ ...TEXT, margin: 0 }}>{fu.notes}</p>}
      {fu.completed_at && <p className="muted" style={{ margin: 0 }}>Done {formatSchoolDateTime(fu.completed_at)}{fu.completed_by && ` by ${fu.completed_by.full_name}`}</p>}
      {fu.cancelled_at && <p className="muted" style={{ ...TEXT, margin: 0 }}>Cancelled {formatSchoolDateTime(fu.cancelled_at)}{fu.cancel_reason && ` — ${fu.cancel_reason}`}</p>}
      {mode === "edit" && (
        <FollowUpForm leadId={fu.lead.id} leadStage={fu.lead.status} followUp={fu} onCancel={() => setMode("view")}
          onSaved={(next) => { setMode("view"); onChanged(next, "Follow-up rescheduled."); }} />
      )}
      {mode === "cancel" && (
        <BdmAppointmentReasonForm label="Cancel follow-up" submitText="Cancel it" busyText="Cancelling…" busy={busy}
          onSubmit={(reason) => void act("cancel", { reason }, "Follow-up cancelled.")} onCancel={() => setMode("view")} />
      )}
      {mode === "view" && fu.can_change && (
        <div className="actions">
          <button type="button" className="btn small" disabled={busy} onClick={() => void act("complete", {}, "Marked done.")}>{busy ? "Saving…" : "Done"}</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("edit")}>Reschedule</button>
          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setMode("cancel")}>Cancel follow-up</button>
        </div>
      )}
      {failure && <p className="form-error" role="alert">{failure}</p>}
      {sessionEnded && (
        <div role="alert">
          <p className="form-error">{SESSION_ENDED}</p>
          <ReturnToLoginLink loginHref={TELECALLER_SIGN_IN} />
        </div>
      )}
    </li>
  );
}
