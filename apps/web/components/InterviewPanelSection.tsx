"use client";
import { type FormEvent, useEffect, useId, useRef, useState } from "react";

import ReturnToLoginLink from "@/components/ReturnToLoginLink";
import { sendJson } from "@/lib/apiErrors";
import { SAVE_FAILED, SESSION_ENDED, writeFailure } from "@/lib/bdmTasks";
import { formatSchoolDateTime } from "@/lib/formatDate";
import { RECRUITER_SIGN_IN } from "@/lib/recruiterCompanies";
import { type InterviewerOption, interviewOf, PANEL_MAX, type PanelMember, panelUrl, type RecInterview } from "@/lib/recruiterInterviews";

const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
type Failure = { message: string; session: boolean };

function failureOf(status: number | undefined, message: string): Failure {
  const kind = writeFailure(status);
  return { message: kind === "session" ? SESSION_ENDED : kind === "retry" ? SAVE_FAILED : message, session: kind === "session" };
}

/** hrc-029 (DEC-SCOPE-405 V2/V3): choose the panel from the internal interviewers and the company's employer users; one may lead. */
function PanelForm({ interview, onSaved, onCancel }: { interview: RecInterview; onSaved: (next: RecInterview) => void; onCancel: () => void }) {
  const id = useId();
  const current = interview.interviewers ?? [];
  const [options, setOptions] = useState<InterviewerOption[] | null>(null);
  const [chosen, setChosen] = useState<string[]>(current.map((m) => m.id));
  const [lead, setLead] = useState(current.find((m) => m.is_lead)?.id ?? "");
  const [failure, setFailure] = useState<Failure | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  useEffect(() => {
    let live = true;
    fetch(panelUrl(interview.id, "interviewer-options"), { cache: "no-store" })
      .then(async (r) => {
        if (!live) return;
        if (!r.ok) return setFailure(failureOf(r.status, "The interviewers could not be loaded. Try again."));
        setOptions(((await r.json()) as { items: InterviewerOption[] }).items);
      })
      .catch(() => live && setFailure({ message: "The interviewers could not be loaded. Try again.", session: false }));
    return () => { live = false; };
  }, [interview.id]);

  function toggle(userId: string, on: boolean) {
    setChosen((prev) => (on ? [...prev, userId] : prev.filter((x) => x !== userId)));
    if (!on && lead === userId) setLead("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (chosen.length > PANEL_MAX) return setFailure({ message: `Choose at most ${PANEL_MAX} interviewers`, session: false });
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    const result = await sendJson(panelUrl(interview.id, "interviewers"), "PUT", { interviewers: chosen.map((user_id) => ({ user_id, is_lead: user_id === lead })) });
    inFlight.current = false;
    setBusy(false);
    if (result.ok) {
      const next = interviewOf(result.data);
      return next ? onSaved(next) : setFailure({ message: SAVE_FAILED, session: false });
    }
    setFailure(failureOf(result.status, result.message));
  }

  return (
    <form aria-label={`Interview panel for ${interview.code}`} className="action-card" noValidate onSubmit={submit} onKeyDown={(e) => e.key === "Escape" && onCancel()}>
      {options === null && !failure && <p className="muted" aria-busy="true" style={{ margin: 0 }}>Loading interviewers…</p>}
      {options !== null && options.length === 0 && (
        <p className="muted" style={{ margin: 0 }}>No interviewers are available. An IT admin can add Interviewer users; the company&apos;s employer users also appear here.</p>
      )}
      {options !== null && options.length > 0 && (
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 6 }}>
          <legend style={{ fontWeight: 600, marginBottom: 4 }}>Interviewers</legend>
          {options.map((o) => {
            const on = chosen.includes(o.id);
            return (
              <div key={o.id} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                  <input type="checkbox" checked={on} onChange={(e) => toggle(o.id, e.target.checked)} />
                  <span>{o.full_name} <span className="muted" style={{ fontSize: 13 }}>· {o.kind_label} · {o.email}</span></span>
                </label>
                {on && (
                  <label style={{ display: "inline-flex", gap: 6, alignItems: "center", fontSize: 13 }}>
                    <input type="radio" name={`${id}-lead`} checked={lead === o.id} onChange={() => setLead(o.id)} />
                    Lead<span className="visually-hidden"> interviewer: {o.full_name}</span>
                  </label>
                )}
              </div>
            );
          })}
        </fieldset>
      )}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Newly added interviewers are notified and can open the candidate&apos;s current resume.</p>
      {failure && (
        <div role="alert">
          <p className="form-error">{failure.message}</p>
          {failure.session && <ReturnToLoginLink loginHref={RECRUITER_SIGN_IN} />}
        </div>
      )}
      <div className="actions">
        <button type="submit" className="btn small" disabled={busy || options === null}>{busy ? "Saving…" : "Save panel"}</button>
        <button type="button" className="btn secondary small" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}

function MemberItem({ member: m }: { member: PanelMember }) {
  const f = m.feedback;
  return (
    <li style={TEXT}>
      <strong>{m.full_name}</strong> <span className="muted">({m.kind_label}{m.is_lead ? ", lead" : ""})</span>
      {f ? (
        <>
          {" — "}{f.attendance_label}
          {f.score !== null && `, ${f.score} / 5`}
          {f.recommendation_label && `, ${f.recommendation_label}`}
          {f.notes && <><br /><span>{f.notes}</span></>}
          <br /><span className="muted">Submitted {formatSchoolDateTime(f.updated_at, true)}</span>
        </>
      ) : (
        <span className="muted"> — no feedback yet</span>
      )}
    </li>
  );
}

/** hrc-029 (V9): the panel on a recruiter's interview -- every member's own feedback (internal; the candidate never sees it). */
export default function InterviewPanelSection({ interview, editing, onEdit, onDone, showActions }: {
  interview: RecInterview; editing: boolean; onEdit: () => void; onDone: (next?: RecInterview) => void; showActions: boolean;
}) {
  const members = interview.interviewers ?? [];
  if (!members.length && !interview.can_assign) return null;
  return (
    <div style={{ display: "grid", gap: 4 }}>
      <strong style={{ fontSize: 13 }}>Interview panel</strong>
      {members.length > 0 ? (
        <ul aria-label={`Interview panel of ${interview.code}`} style={{ margin: 0, paddingLeft: 18, fontSize: 13, display: "grid", gap: 4 }}>
          {members.map((m) => <MemberItem key={m.id} member={m} />)}
        </ul>
      ) : (
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>No interviewers assigned.</p>
      )}
      {editing && <PanelForm interview={interview} onCancel={() => onDone()} onSaved={(next) => onDone(next)} />}
      {!editing && showActions && interview.can_assign && (
        <div className="actions">
          <button type="button" className="btn secondary small" onClick={onEdit}>
            {members.length ? "Edit panel" : "Assign interviewers"}<span className="visually-hidden"> for {interview.code}</span>
          </button>
        </div>
      )}
    </div>
  );
}
