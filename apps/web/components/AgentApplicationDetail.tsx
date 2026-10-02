"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import AgentApplicationEditForm from "./AgentApplicationEditForm";
import AgentApplicationStatusForm from "./AgentApplicationStatusForm";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { AgentApplicationDetail as Detail, APPLICATIONS_URL, deadlineText, READ_ONLY_TEXT, stageLabel, todayIso } from "@/lib/agentApplications";

type Props = { id: string; onChanged: (d: Detail) => void; onClose: () => void };

// AGN-008: one application -- fields, status history, edit and status change. A 409/422 from a write shows the server's words and
// reloads, so the screen always ends on the real state (stale, withdrawn, archived).
export default function AgentApplicationDetail({ id, onChanged, onClose }: Props) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "gone" | "error">("loading");
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const focusHeading = useRef(true);
  const returnToEdit = useRef(false);

  const load = useCallback(async () => {
    try {
      const response = await fetch(`${APPLICATIONS_URL}/${id}`);
      const body = await response.json().catch(() => null);
      if (response.status === 404) return setState("gone");
      if (!response.ok || !body?.application) return setState("error");
      setDetail(body.application);
      setState("ready");
    } catch {
      setState("error");
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);
  useEffect(() => {
    if (state === "ready" && focusHeading.current) {
      focusHeading.current = false;
      headingRef.current?.focus();
    }
  }, [state]);
  useEffect(() => {
    if (!editing && returnToEdit.current) {
      returnToEdit.current = false;
      editRef.current?.focus();
    }
  }, [editing]);

  function saved(next: Detail, message: string) {
    setDetail(next);
    setEditing(false);
    setNotice({ text: message, failed: false });
    onChanged(next);
  }
  function failed(message: string, status?: number) {
    setNotice({ text: message, failed: true });
    if (status === 404) return setState("gone");
    if (status === 409 || status === 422) {
      setEditing(false); // the reload shows the real state; stale input must not stay on screen
      load();
    }
  }

  if (state === "loading") return <p className="muted" aria-busy="true">Loading application…</p>;
  if (state === "gone") return <p className="form-error" role="alert">This application is no longer available.</p>;
  if (state === "error" || !detail)
    return (
      <p className="form-error" role="alert">
        The application could not be loaded.{" "}
        <button type="button" className="btn secondary small" onClick={() => (setState("loading"), load())}>
          Retry
        </button>
      </p>
    );

  const title = `${detail.student} — ${detail.university}`;
  const deadline = deadlineText(detail.nearest_deadline, todayIso());
  return (
    <section aria-labelledby={`detail-${id}`} style={{ marginTop: 12 }}>
      <h4 id={`detail-${id}`} ref={headingRef} tabIndex={-1}>
        {title}
      </h4>
      <p>
        <span className={detail.status === "withdrawn" ? "status error" : "badge"}>{stageLabel(detail.status)}</span>
        {deadline && <span className="muted"> · {deadline}</span>}
      </p>
      {notice && (
        <p className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} aria-live="polite">
          {notice.text}
        </p>
      )}
      {detail.read_only_reason && <p className="muted">{READ_ONLY_TEXT[detail.read_only_reason]}</p>}
      {editing ? (
        <AgentApplicationEditForm detail={detail} onSaved={saved} onFailed={failed} onCancel={() => {
            returnToEdit.current = true;
            setEditing(false);
          }} />
      ) : (
        <>
          <dl className="card-stack">
            <dt>Application ID</dt>
            <dd>{detail.application_reference ?? "—"}</dd>
            <dt>Course</dt>
            <dd>{detail.course ?? "Undecided"}</dd>
            <dt>Intake</dt>
            <dd>{detail.intake}</dd>
            <dt>Submitted on</dt>
            <dd>{detail.submitted_on ?? "Not submitted"}</dd>
            <dt>Application deadline</dt>
            <dd>{detail.application_deadline ?? "—"}</dd>
            <dt>Offer deadline</dt>
            <dd>{detail.offer_deadline ?? "—"}</dd>
            <dt>Next action</dt>
            <dd>{detail.next_action ?? "—"}</dd>
          </dl>
          {!detail.read_only_reason && (
            <button ref={editRef} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </>
      )}
      {!detail.read_only_reason && !editing && <AgentApplicationStatusForm key={detail.status} detail={detail} onSaved={saved} onFailed={failed} />}
      <h5>Status history</h5>
      <ol aria-label="Status history">
        {detail.history.map((h, i) => (
          <li key={i}>
            {h.from_status ? `${stageLabel(h.from_status)} → ` : ""}
            {stageLabel(h.to_status)}
            {h.changed_by && ` · ${h.changed_by}`} · {formatDateTimeIn(h.created_at, viewerTimeZone(), true)}
            {h.notes && <div className="muted">{h.notes}</div>}
          </li>
        ))}
      </ol>
      <button type="button" className="btn ghost small" onClick={onClose}>
        Close
      </button>
    </section>
  );
}
