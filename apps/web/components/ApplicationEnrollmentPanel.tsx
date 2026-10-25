"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { EnrollmentPayload, EnrollmentView, enrollmentDocumentsUrl, enrollmentUrl } from "@/lib/applicationEnrollment";
import { documentDownloadUrl, OfferDocument } from "@/lib/applicationOffers";
import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";

type Props = { applicationId: string; onChanged: (message: string) => void };

const NEED_DOCUMENT = "Attach the enrolment confirmation: pick an uploaded one or upload the file.";
const NEED_CHECKLIST = "Confirm the pre-enrolment checklist is complete.";

// ccrm-027 (DEC-SCOPE-259): enrolment is confirmed here, never by a stage change (E3). Confirming needs the confirmation document and the
// pre-enrolment checklist, from an offer onwards, and goes through an explicit step (it may estimate an agency commission). Once enrolled
// the same form corrects the details. The server checks every rule again; the shown stage travels as `expected_status`.
export default function ApplicationEnrollmentPanel({ applicationId, onChanged }: Props) {
  const [data, setData] = useState<EnrollmentPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(enrollmentUrl(applicationId), {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setData(outcome.data as unknown as EnrollmentPayload);
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
  if (data === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading enrolment…</p>;

  const view = data.enrollment;
  const enrolled = view.status === "enrolled";
  return (
    <section aria-label="Enrolment" style={{ marginTop: 8 }}>
      <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>Enrolment</h4>
      {view.confirmed ? (
        <dl className="card-stack" style={{ fontSize: 13 }}>
          <dt>Enrolment date</dt>
          <dd>{view.enrollment_date ?? "Not recorded"}</dd>
          <dt>University student number</dt>
          <dd>{view.university_student_id ?? "Not recorded"}</dd>
          <dt>Course start date</dt>
          <dd>{view.course_start_date ?? "Not recorded"}</dd>
          <dt>Confirmation document</dt>
          <dd>
            {view.document ? (
              <a href={documentDownloadUrl(view.document.id)} target="_blank" rel="noopener">
                {view.document.name}
              </a>
            ) : (
              "Not attached"
            )}
          </dd>
          <dt>Confirmed</dt>
          <dd>{view.confirmed_at ? formatDateTimeIn(view.confirmed_at, viewerTimeZone(), true) : "—"}</dd>
        </dl>
      ) : (
        <p className="muted" style={{ fontSize: 13, margin: 0 }}>
          {enrolled ? "Enrolled before confirmation was required -- add the confirmation details." : "Enrolment not confirmed yet."}
        </p>
      )}
      {editing ? (
        <EnrollmentForm
          applicationId={applicationId}
          view={view}
          documents={data.documents}
          onSaved={(message) => (setEditing(false), onChanged(message), load())}
          onCancel={() => setEditing(false)}
        />
      ) : (
        (enrolled || view.can_confirm) && (
          <button type="button" className="btn secondary small" style={{ marginTop: 8 }} onClick={() => setEditing(true)}>
            {enrolled ? "Edit enrolment details" : "Confirm enrolment"}
          </button>
        )
      )}
    </section>
  );
}

type FormProps = { applicationId: string; view: EnrollmentView; documents: OfferDocument[]; onSaved: (message: string) => void; onCancel: () => void };

function EnrollmentForm({ applicationId: id, view, documents, onSaved, onCancel }: FormProps) {
  const enrolled = view.status === "enrolled";
  const [fields, setFields] = useState({
    enrollment_date: view.enrollment_date ?? "",
    university_student_id: view.university_student_id ?? "",
    course_start_date: view.course_start_date ?? "",
    notes: "",
  });
  const [documentId, setDocumentId] = useState(view.document?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [checklist, setChecklist] = useState(view.pre_enrollment_checklist_complete);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // a same-tick second click sends nothing
  const set = (key: keyof typeof fields) => (event: { target: { value: string } }) => setFields((f) => ({ ...f, [key]: event.target.value }));
  const field = (name: string) => `enrollment-${name}-${id}`;

  function check(event: FormEvent) {
    event.preventDefault();
    if (!documentId && !file) return setError(NEED_DOCUMENT);
    if (!checklist) return setError(NEED_CHECKLIST);
    setError(null);
    if (enrolled) save();
    else setConfirming(true);
  }

  async function save() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      let document = documentId;
      if (file) {
        const form = new FormData();
        form.set("file", file);
        const uploaded = await sendRequest(enrollmentDocumentsUrl(id), { method: "POST", body: form });
        if (!uploaded.ok) return setError(uploaded.message);
        document = String((uploaded.data.document as OfferDocument).id);
        setDocumentId(document);
        setFile(null);
      }
      const outcome = await sendJson(enrollmentUrl(id), "PUT", {
        expected_status: view.status,
        enrollment_date: fields.enrollment_date,
        enrollment_document_id: document,
        pre_enrollment_checklist_complete: checklist,
        university_student_id: fields.university_student_id.trim() || null,
        course_start_date: fields.course_start_date || null,
        notes: enrolled ? null : fields.notes.trim() || null,
      });
      if (!outcome.ok) return setError(outcome.message);
      onSaved(enrolled ? (outcome.data.changed === false ? "Nothing changed." : "Enrolment details saved.") : "Enrolment confirmed.");
    } finally {
      inFlight.current = false;
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <form className="form" onSubmit={check} aria-label={enrolled ? "Enrolment details" : "Confirm enrolment"} style={{ marginTop: 8 }} onKeyDown={(event) => event.key === "Escape" && !busy && onCancel()}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={field("date")}>Enrolment date</label>
          <input id={field("date")} type="date" required min="2000-01-01" max="2100-12-31" value={fields.enrollment_date} onChange={set("enrollment_date")} autoFocus />
        </div>
        <div className="field">
          <label htmlFor={field("start")}>Course start date</label>
          <input id={field("start")} type="date" min="2000-01-01" max="2100-12-31" value={fields.course_start_date} onChange={set("course_start_date")} />
        </div>
      </div>
      <div className="field">
        <label htmlFor={field("student")}>University student number (optional)</label>
        <input id={field("student")} maxLength={60} autoComplete="off" value={fields.university_student_id} onChange={set("university_student_id")} />
      </div>
      <div className="field">
        <label htmlFor={field("document")}>Confirmation document</label>
        <select id={field("document")} value={documentId} onChange={(event) => setDocumentId(event.target.value)} disabled={!!file}>
          <option value="">{documents.length ? "Choose an uploaded confirmation" : "None uploaded yet"}</option>
          {documents.map((d) => (
            <option key={d.id} value={d.id}>
              {d.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor={field("file")}>Or upload the confirmation (PDF or image)</label>
        <input id={field("file")} type="file" accept="application/pdf,image/*" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
      </div>
      <div className="field">
        <label>
          <input type="checkbox" checked={checklist} onChange={(event) => setChecklist(event.target.checked)} /> The pre-enrolment checklist is complete
        </label>
      </div>
      {!enrolled && (
        <div className="field">
          <label htmlFor={field("notes")}>Note (optional)</label>
          <textarea id={field("notes")} maxLength={2000} value={fields.notes} onChange={set("notes")} />
        </div>
      )}
      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
      {confirming ? (
        <div role="group" aria-label="Confirm enrolment" onKeyDown={(event) => event.key === "Escape" && (event.stopPropagation(), setConfirming(false))}>
          <p style={{ fontSize: 13 }}>Confirm enrolment? The application becomes Enrolled; on an agency application a commission is estimated.</p>
          <div className="actions">
            <button type="button" className="btn small" disabled={busy} onClick={save} autoFocus>
              {busy ? "Saving…" : "Yes, confirm enrolment"}
            </button>
            <button type="button" className="btn ghost small" disabled={busy} onClick={() => setConfirming(false)}>
              Go back
            </button>
          </div>
        </div>
      ) : (
        <div className="actions">
          <button className="btn small" disabled={busy || !fields.enrollment_date}>
            {busy ? "Saving…" : enrolled ? "Save enrolment details" : "Continue"}
          </button>
          <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
            Cancel
          </button>
        </div>
      )}
    </form>
  );
}
