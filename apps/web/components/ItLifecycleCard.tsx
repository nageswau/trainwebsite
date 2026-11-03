"use client";

import { FormEvent, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import {
  CAUSE_LABELS, COMPONENT_LABELS, lifecycleOverrideUrl, OVERRIDE_CHOICES, stageTone, type LifecycleEnrollment, type LifecycleResponse,
} from "@/lib/itLifecycle";

// itc-031 (DEC-SCOPE-359): the 360's lifecycle card -- each enrolment's derived stage, its fee / training / placement components (so
// concurrent states stay visible) and its history. The IT Admin may also set "Not placed" or "Closed" with a reason, or clear it.
export default function ItLifecycleCard({ initial, studentId, canOverride }: { initial: LifecycleResponse; studentId: string; canOverride: boolean }) {
  const [data, setData] = useState(initial);
  return (
    <section className="card" aria-labelledby="student-lifecycle-heading" style={{ marginBottom: 16 }}>
      <h3 id="student-lifecycle-heading" style={{ fontSize: 18 }}>Lifecycle</h3>
      <p className="muted" style={{ marginTop: 0 }}>Worked out from the fee, training, certificate, HR review and placement records, so it updates by itself.</p>
      {data.enrollments.length === 0 ? (
        <p className="muted" style={{ margin: 0 }}>No enrolments yet.</p>
      ) : (
        <div style={{ display: "grid", gap: 16 }}>
          {data.enrollments.map((e) => (
            <LifecycleEnrollmentBlock key={e.enrollment_id} enrollment={e} studentId={studentId} canOverride={canOverride} onSaved={setData} />
          ))}
        </div>
      )}
    </section>
  );
}

function LifecycleEnrollmentBlock({ enrollment: e, studentId, canOverride, onSaved }: {
  enrollment: LifecycleEnrollment; studentId: string; canOverride: boolean; onSaved: (data: LifecycleResponse) => void;
}) {
  const id = `lc-${e.enrollment_id}`;
  return (
    <article aria-labelledby={id} style={{ display: "grid", gap: 8, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
      <h4 id={id} style={{ margin: 0, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
        {e.program} · {e.batch} <span className={stageTone(e.stage)} data-testid="lifecycle-stage">{e.stage_label}</span>
      </h4>
      <dl style={{ margin: 0, display: "grid", gridTemplateColumns: "max-content 1fr", gap: "4px 16px" }}>
        {(Object.keys(COMPONENT_LABELS) as (keyof typeof COMPONENT_LABELS)[]).map((key) => (
          <div key={key} style={{ display: "contents" }}>
            <dt>{COMPONENT_LABELS[key]}</dt>
            <dd style={{ margin: 0 }}>{e.components[key]?.stage_label ?? (key === "fee" ? "Not billed" : "Not started")}</dd>
          </div>
        ))}
      </dl>
      {e.override && (
        <p style={{ margin: 0 }} data-testid="lifecycle-override">
          Set by the IT Admin: <strong>{e.override.stage_label}</strong>{e.override.reason ? ` (${e.override.reason})` : ""}
        </p>
      )}
      {canOverride && <OverrideForm enrollment={e} url={lifecycleOverrideUrl(studentId, e.enrollment_id)} onSaved={onSaved} />}
      <details>
        <summary>History ({e.history.length})</summary>
        {e.history.length === 0 ? (
          <p className="muted" style={{ margin: "8px 0 0" }}>No changes recorded yet. The next fee, training, HR or placement update, or the daily check, records one.</p>
        ) : (
          <ol style={{ margin: "8px 0 0", paddingLeft: 20 }} aria-label={`Lifecycle history for ${e.enrollment_code}`}>
            {e.history.map((h, i) => (
              <li key={`${h.created_at}-${i}`}>
                <LocalTime value={h.created_at} time /> · {h.from_label ? `${h.from_label} → ` : ""}{h.to_label} · {CAUSE_LABELS[h.cause] ?? h.cause} · {h.actor ?? "System"}
              </li>
            ))}
          </ol>
        )}
      </details>
    </article>
  );
}

function OverrideForm({ enrollment: e, url, onSaved }: { enrollment: LifecycleEnrollment; url: string; onSaved: (data: LifecycleResponse) => void }) {
  const [stage, setStage] = useState(e.override?.stage ?? "");
  const [reason, setReason] = useState(e.override?.reason ?? "");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const inFlight = useRef(false);
  const id = `lc-o-${e.enrollment_id}`;

  async function send(body: { stage: string | null; reason?: string }, done: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setSaving(true);
    setMessage(null);
    const outcome = await sendJson(url, "PUT", body);
    inFlight.current = false;
    setSaving(false);
    if (!outcome.ok) return setMessage({ text: Array.isArray(outcome.detail) ? detailMessage(outcome.detail) : outcome.message, failed: true });
    const data = outcome.data as LifecycleResponse;
    const now = data.enrollments.find((row) => row.enrollment_id === e.enrollment_id);
    setStage(now?.override?.stage ?? "");
    setReason(now?.override?.reason ?? "");
    setMessage({ text: done, failed: false });
    onSaved(data);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!stage) return setMessage({ text: "Choose Not placed or Closed.", failed: true });
    if (reason.trim().length < 3) return setMessage({ text: "Give a reason of at least 3 characters.", failed: true });
    void send({ stage, reason: reason.trim() }, "Stage saved.");
  }

  return (
    <form className="form-section" onSubmit={submit} aria-label={`Set the stage by hand for ${e.enrollment_code}`} noValidate>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`${id}-stage`}>Set by hand</label>
          <select id={`${id}-stage`} value={stage} onChange={(ev) => setStage(ev.target.value)}>
            <option value="">Choose…</option>
            {OVERRIDE_CHOICES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor={`${id}-reason`}>Reason</label>
          <input id={`${id}-reason`} value={reason} maxLength={500} onChange={(ev) => setReason(ev.target.value)} />
        </div>
      </div>
      <p className="field-help muted" style={{ margin: 0 }}>Only Not placed and Closed can be set by hand. Every other stage follows the records.</p>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="submit" className="btn small" disabled={saving}>{saving ? "Saving…" : "Save stage"}</button>
        {e.override && (
          <button type="button" className="btn small secondary" disabled={saving} onClick={() => send({ stage: null }, "Hand-set stage cleared.")}>Clear hand-set stage</button>
        )}
      </div>
    </form>
  );
}
