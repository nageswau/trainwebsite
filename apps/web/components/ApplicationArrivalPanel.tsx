"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { ArrivalView, arrivalUrl } from "@/lib/applicationArrival";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";

type Props = { applicationId: string; onChanged: (message: string) => void };

// ccrm-028 (DEC-SCOPE-265): after enrolment the counselor records the arrival date (expected until confirmed), whether arrival is
// confirmed -- the server stamps who and when --, orientation attended and notes. Orientation needs a confirmed arrival. The server
// checks every rule again.
export default function ApplicationArrivalPanel({ applicationId, onChanged }: Props) {
  const [view, setView] = useState<ArrivalView | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(arrivalUrl(applicationId), {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setView(outcome.data.arrival as ArrivalView);
  }

  useEffect(() => {
    load();
  }, [applicationId]); // eslint-disable-line react-hooks/exhaustive-deps -- reload only when the application changes

  if (loadError) {
    return (
      <div className="form-error" role="alert" style={{ marginTop: 8 }}>
        {loadError}{" "}
        <button type="button" className="btn ghost small" onClick={load}>
          Try again
        </button>
      </div>
    );
  }
  if (view === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading arrival…</p>;

  const recorded = view.arrival_date !== null || view.arrival_confirmed || view.notes !== null;
  return (
    <section aria-label="Arrival and orientation" style={{ marginTop: 8 }}>
      <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>Arrival and orientation</h4>
      {recorded ? (
        <dl className="card-stack" style={{ fontSize: 13 }}>
          <dt>{view.arrival_confirmed ? "Arrival date" : "Expected arrival date"}</dt>
          <dd>{view.arrival_date ?? "Not recorded"}</dd>
          <dt>Arrival confirmed</dt>
          <dd>
            {view.arrival_confirmed
              ? `Yes -- by ${view.confirmed_by ?? "a former user"}${view.confirmed_at ? `, ${formatDateTimeIn(view.confirmed_at, viewerTimeZone(), true)}` : ""}`
              : "Not yet"}
          </dd>
          <dt>Orientation attended</dt>
          <dd>{view.orientation_attended ? "Yes" : "No"}</dd>
          {view.notes && (
            <>
              <dt>Notes</dt>
              <dd style={{ whiteSpace: "pre-wrap" }}>{view.notes}</dd>
            </>
          )}
        </dl>
      ) : (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>
          Arrival not recorded yet.
        </p>
      )}
      {editing ? (
        <ArrivalForm
          applicationId={applicationId}
          view={view}
          onSaved={(message) => (setEditing(false), onChanged(message), load())}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <button type="button" className="btn secondary small" style={{ marginTop: 8 }} onClick={() => setEditing(true)}>
          {recorded ? "Edit arrival" : "Record arrival"}
        </button>
      )}
    </section>
  );
}

type FormProps = { applicationId: string; view: ArrivalView; onSaved: (message: string) => void; onCancel: () => void };

function ArrivalForm({ applicationId: id, view, onSaved, onCancel }: FormProps) {
  const [date, setDate] = useState(view.arrival_date ?? "");
  const [confirmed, setConfirmed] = useState(view.arrival_confirmed);
  const [orientation, setOrientation] = useState(view.orientation_attended);
  const [notes, setNotes] = useState(view.notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const field = (name: string) => `arrival-${name}-${id}`;

  async function save(event: FormEvent) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      const outcome = await sendJson(arrivalUrl(id), "PUT", { arrival_date: date || null, arrival_confirmed: confirmed, orientation_attended: orientation, notes: notes.trim() || null });
      if (!outcome.ok) return setError(outcome.message);
      onSaved(outcome.data.changed === false ? "Nothing changed." : "Arrival saved.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <form className="form" onSubmit={save} aria-label="Arrival and orientation" style={{ marginTop: 8 }} onKeyDown={(event) => event.key === "Escape" && !busy && onCancel()}>
      <div className="field">
        <label htmlFor={field("date")}>Arrival date</label>
        <input id={field("date")} type="date" required={confirmed} min="2000-01-01" max="2100-12-31" value={date} onChange={(event) => setDate(event.target.value)} autoFocus />
      </div>
      <div className="field">
        <label>
          <input
            type="checkbox"
            checked={confirmed}
            onChange={(event) => (setConfirmed(event.target.checked), event.target.checked || setOrientation(false))}
          />{" "}
          Arrival confirmed
        </label>
      </div>
      <div className="field">
        <label>
          <input type="checkbox" checked={orientation} disabled={!confirmed} onChange={(event) => setOrientation(event.target.checked)} /> Orientation attended
        </label>
      </div>
      <div className="field">
        <label htmlFor={field("notes")}>Notes (optional)</label>
        <textarea id={field("notes")} maxLength={2000} placeholder="How was arrival confirmed?" value={notes} onChange={(event) => setNotes(event.target.value)} />
      </div>
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save arrival"}
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
