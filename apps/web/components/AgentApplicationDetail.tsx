"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import AgentApplicationEditForm from "./AgentApplicationEditForm";
import AgentApplicationEnrollment from "./AgentApplicationEnrollment";
import AgentApplicationOffer from "./AgentApplicationOffer";
import AgentApplicationStatusForm from "./AgentApplicationStatusForm";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { AgentApplicationDetail as Detail, APPLICATIONS_URL, deadlineText, READ_ONLY_TEXT, stageLabel, todayIso } from "@/lib/agentApplications";

type Props = { id: string; isMaster?: boolean; onChanged: (d: Detail) => void; onClose: () => void };

// AGN-008: one application -- fields, status history, edit and status change. A 409 (or a status 422) shows the server's words and
// reloads, so the screen always ends on the real state (stale, withdrawn, archived); the reload also updates the list card (QA8-03).
// A 422 from Save keeps the edit form open with the user's input (QA8-01). AGN-013: the Enrollment section (Masters act, Staff read).
// AGN-010: the offer block sits between the fields and the enrollment/status forms, and its form follows the edit form's rules (a 422
// keeps the input; 409 reloads). One form of the detail is open at a time.
export default function AgentApplicationDetail({ id, isMaster = false, onChanged, onClose }: Props) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "gone" | "error">("loading");
  const [editing, setEditing] = useState(false);
  const [enrolling, setEnrolling] = useState(false); // AGN-013 QA13-06: the enrollment form is open, so no competing status action
  const [offering, setOffering] = useState(false); // AGN-010: the offer form is open
  const [notice, setNotice] = useState<{ text: string; failed: boolean } | null>(null);
  const focusAfter = useFocusAfterRender();
  const firstLoad = useRef(true); // the heading takes focus on the first successful load only
  const headingId = `detail-${id}`;
  const editId = `detail-edit-${id}`;
  const noticeId = `detail-notice-${id}`;
  const readOnlyId = `detail-read-only-${id}`;

  const load = useCallback(async (): Promise<Detail | null> => {
    try {
      const response = await fetch(`${APPLICATIONS_URL}/${id}`);
      const body = await response.json().catch(() => null);
      if (response.status === 404) return (setState("gone"), null);
      if (!response.ok || !body?.application) return (setState("error"), null);
      setDetail(body.application);
      setState("ready");
      if (firstLoad.current) {
        firstLoad.current = false;
        focusAfter(`detail-${id}`);
      }
      return body.application;
    } catch {
      setState("error");
      return null;
    }
  }, [id, focusAfter]);

  useEffect(() => {
    load();
  }, [load]);

  function saved(next: Detail, message: string) {
    if (next.read_only_reason === "withdrawn" && detail?.read_only_reason !== "withdrawn") focusAfter(readOnlyId);
    setDetail(next);
    setEditing(false);
    setEnrolling(false);
    setOffering(false);
    setNotice({ text: message, failed: false });
    onChanged(next);
  }
  function failed(message: string, status?: number) {
    setNotice({ text: message, failed: true });
    if (status === 404) return setState("gone");
    if (status === 409 || status === 422) {
      setEditing(false); // the reload shows the real state; stale input must not stay on screen
      setEnrolling(false);
      setOffering(false);
      load().then((reloaded) => reloaded && onChanged(reloaded));
    }
  }
  function enrollmentSaved(next: Detail, message: string) {
    saved(next, message);
    focusAfter(noticeId); // the form and its opener are gone: the announced notice takes focus
  }
  function editFailed(message: string, status?: number) {
    if (status !== 404) focusAfter(noticeId); // a 404 shows "no longer available" instead of the notice
    if (status === 422) return setNotice({ text: message, failed: true }); // the input stays for the user to correct
    failed(message, status);
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
    <section aria-labelledby={headingId} style={{ marginTop: 12 }}>
      <h4 id={headingId} tabIndex={-1}>
        {title}
      </h4>
      <p>
        <span className={detail.status === "withdrawn" ? "status error" : "badge"}>{stageLabel(detail.status)}</span>
        {deadline && <span className="muted"> · {deadline}</span>}
      </p>
      {notice && (
        <p id={noticeId} tabIndex={-1} className={notice.failed ? "form-error" : "form-message"} role={notice.failed ? "alert" : "status"} aria-live="polite">
          {notice.text}
        </p>
      )}
      {detail.read_only_reason && (
        <p id={readOnlyId} tabIndex={-1} className="muted">
          {READ_ONLY_TEXT[detail.read_only_reason]}
        </p>
      )}
      {editing ? (
        <AgentApplicationEditForm detail={detail} onSaved={saved} onFailed={editFailed} onCancel={() => {
            focusAfter(editId);
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
          {!detail.read_only_reason && !offering && (
            <button id={editId} type="button" className="btn secondary small" onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
        </>
      )}
      <AgentApplicationOffer
        detail={detail}
        open={offering}
        canOpen={!detail.read_only_reason && !editing && !enrolling}
        onOpen={() => setOffering(true)}
        onCancel={() => setOffering(false)}
        onSaved={saved}
        onFailed={editFailed}
      />
      {!editing && !offering && (
        // A status change starts both action forms afresh.
        <Fragment key={detail.status}>
          <AgentApplicationEnrollment detail={detail} isMaster={isMaster} onSaved={enrollmentSaved} onFailed={editFailed} onOpenChange={setEnrolling} />
          {!detail.read_only_reason && !enrolling && <AgentApplicationStatusForm detail={detail} onSaved={saved} onFailed={failed} />}
        </Fragment>
      )}
      <h5>Status history</h5>
      <ol aria-label="Status history">
        {detail.history.map((h, i) => (
          <li key={i}>
            {h.from_status ? `${stageLabel(h.from_status)} → ` : ""}
            {stageLabel(h.to_status)}
            {h.changed_by && ` · ${h.changed_by}`} · {formatDateTimeIn(h.created_at, viewerTimeZone(), true)}
            {h.notes && <div className="muted history-note">{h.notes}</div>}
          </li>
        ))}
      </ol>
      <button type="button" className="btn ghost small" onClick={onClose}>
        Close
      </button>
    </section>
  );
}
