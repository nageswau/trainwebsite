"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { ApplicationChecklistItem, ChecklistDocument, ChecklistMark, ChecklistPayload, checklistUrl, COMPLETE } from "@/lib/applicationChecklist";
import { CHECKLIST_DOCUMENT_TYPES, GATE_LABELS, NEEDS_ACTION, sensitivityBadge } from "@/lib/documentChecklists";
import { staffRequestsUrl, todayInIndia } from "@/lib/documentRequests";
import { formatCalendarDate } from "@/lib/formatDate";

type Props = { applicationId: string; readOnly?: boolean; onChanged?: (message: string) => void };

const documentName = (d: ChecklistDocument) => d.original_filename || d.document_label || d.document_type;

// ccrm-019 (DEC-SCOPE-257): an application's document checklist -- "8 of 10 required complete", each item's status from its linked
// documents or the counselor's mark (AC1), and the counselor's actions: create from the matching template, add / remove own items,
// mark Requested / Not required, link / unlink the student's documents. The agency reads it (AC7). One request at a time.
export default function ApplicationChecklistPanel({ applicationId, readOnly = false, onChanged }: Props) {
  const [data, setData] = useState<ChecklistPayload | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  const inFlight = useRef(false);
  const url = checklistUrl(applicationId);

  async function load() {
    setLoadError(null);
    const outcome = await sendRequest(url, {});
    if (!outcome.ok) return setLoadError(outcome.message);
    setData(outcome.data as unknown as ChecklistPayload);
  }

  useEffect(() => {
    load();
  }, [applicationId]); // eslint-disable-line react-hooks/exhaustive-deps -- reload only when the application changes

  async function act(path: string, method: "POST" | "PATCH" | "PUT" | "DELETE", body: unknown, message: string): Promise<boolean> {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    setActionError(null);
    const outcome = method === "DELETE" ? await sendRequest(url + path, { method }) : await sendJson(url + path, method, body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      setActionError(outcome.message);
      if (outcome.status === 409 || outcome.status === 404) load(); // the server's state changed under us
      return false;
    }
    setData(outcome.data as unknown as ChecklistPayload);
    onChanged?.(message);
    return true;
  }

  // ccrm-020 (DEC-SCOPE-266 R2): ask the student for a missing item; the server marks it Requested, so the checklist is reloaded.
  async function requestFromStudent(itemId: string, body: { due_date: string; note?: string }): Promise<boolean> {
    if (inFlight.current || !data?.student_id) return false;
    inFlight.current = true;
    setBusy(true);
    setActionError(null);
    const outcome = await sendJson(staffRequestsUrl(data.student_id), "POST", { ...body, application_id: applicationId, checklist_item_id: itemId });
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) {
      setActionError(outcome.message);
      return false;
    }
    await load();
    onChanged?.("Requested from the student.");
    return true;
  }

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
  if (data === null) return <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>Loading checklist…</p>;

  const { checklist, template } = data;
  return (
    <section aria-label="Document checklist" style={{ marginTop: 8 }}>
      <h4 style={{ margin: "0 0 4px", fontSize: 14 }}>Document checklist</h4>
      {actionError && (
        <div className="form-error" role="alert" style={{ marginBottom: 6 }}>
          {actionError}
        </div>
      )}
      {!checklist ? (
        <>
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            No checklist yet.{readOnly ? "" : template ? ` The ${template.name} template (v${template.version}) matches this application.` : " No admission template matches this application."}
          </p>
          {!readOnly && (
            <button type="button" className="btn ghost small" style={{ marginTop: 6 }} disabled={busy} onClick={() => act("", "POST", {}, "Checklist created.")}>
              {template ? `Create checklist from ${template.name} (v${template.version})` : "Create an empty checklist"}
            </button>
          )}
        </>
      ) : (
        <>
          <p style={{ fontSize: 13, margin: 0 }}>
            <strong>
              {checklist.summary.required_complete} of {checklist.summary.required_total} required complete
            </strong>
            {checklist.summary.optional_total > 0 && ` · ${checklist.summary.optional_complete} of ${checklist.summary.optional_total} optional`}
          </p>
          <p className="muted" style={{ fontSize: 12, margin: "2px 0 0" }}>
            Ready for Submission: {GATE_LABELS[checklist.gate_mode]}
            {checklist.template_version !== null && ` · template v${checklist.template_version}`}
            {checklist.documents_completed_on && ` · documents completed on ${checklist.documents_completed_on}`}
          </p>
          {checklist.items.length === 0 ? (
            <p className="muted" style={{ fontSize: 13, margin: "6px 0 0" }}>No items yet.</p>
          ) : (
            <ul style={{ listStyle: "none", padding: 0, margin: "6px 0 0", display: "grid", gap: 8 }}>
              {checklist.items.map((item) => (
                <ItemRow
                  key={item.id}
                  item={item}
                  documents={data.documents}
                  readOnly={readOnly}
                  busy={busy}
                  act={act}
                  onRequest={data.student_id ? (body) => requestFromStudent(item.id, body) : undefined}
                />
              ))}
            </ul>
          )}
          {!readOnly &&
            (adding ? (
              <AddItemForm busy={busy} onCancel={() => setAdding(false)} onAdd={async (body) => (await act("/items", "POST", body, "Checklist item added.")) && setAdding(false)} />
            ) : (
              <button type="button" className="btn ghost small" style={{ marginTop: 6 }} onClick={() => setAdding(true)}>
                Add item
              </button>
            ))}
        </>
      )}
    </section>
  );
}

type Act = (path: string, method: "POST" | "PATCH" | "PUT" | "DELETE", body: unknown, message: string) => Promise<boolean>;

type RequestBody = { due_date: string; note?: string };
type RowProps = { item: ApplicationChecklistItem; documents: ChecklistDocument[]; readOnly: boolean; busy: boolean; act: Act; onRequest?: (body: RequestBody) => Promise<boolean> };

function ItemRow({ item, documents, readOnly, busy, act, onRequest }: RowProps) {
  const [picked, setPicked] = useState("");
  const [requesting, setRequesting] = useState(false);
  const path = `/items/${item.id}`;
  const linkable = documents.filter((d) => !item.documents.some((linked) => linked.id === d.id));
  const allows = (mark: ChecklistMark) => item.allowed_statuses.length === 0 || item.allowed_statuses.includes(mark);
  const tone = COMPLETE.has(item.status) ? "status" : NEEDS_ACTION.has(item.status) ? "status error" : "status pending";
  return (
    <li className="card" style={{ padding: 10 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        <strong style={{ fontSize: 13 }}>{item.name}</strong>
        <span className="badge">{item.required ? "Required" : "Optional"}</span>
        {sensitivityBadge(item.sensitivity) && <span className="status closed">{sensitivityBadge(item.sensitivity)}</span>}
        <span className={tone}>{item.status_label}</span>
        {item.mark && <span className="muted" style={{ fontSize: 12 }}>(marked by counselor)</span>}
      </div>
      {item.notes && <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>{item.notes}</p>}
      {item.open_request && (
        <p className="muted" style={{ fontSize: 12, margin: "4px 0 0" }}>
          Requested from the student{item.open_request.due_date && <> · due {formatCalendarDate(item.open_request.due_date)}</>}
        </p>
      )}
      {item.documents.length > 0 && (
        <ul style={{ margin: "4px 0 0", paddingLeft: 18, fontSize: 12 }}>
          {item.documents.map((d) => (
            <li key={d.id}>
              {documentName(d)} — {d.status_label}{" "}
              {!readOnly && (
                <button type="button" className="btn ghost small" disabled={busy} aria-label={`Unlink ${documentName(d)}`} onClick={() => act(`${path}/documents/${d.id}`, "DELETE", null, "Document unlinked.")}>
                  Unlink
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {!readOnly && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6, alignItems: "center" }}>
          {linkable.length > 0 && (
            <>
              <select aria-label={`Link a document to ${item.name}`} value={picked} onChange={(event) => setPicked(event.target.value)} style={{ maxWidth: "100%" }}>
                <option value="">Choose a document…</option>
                {linkable.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.document_type}: {documentName(d)} ({d.status_label})
                  </option>
                ))}
              </select>
              <button type="button" className="btn ghost small" disabled={busy || !picked} onClick={async () => (await act(`${path}/documents/${picked}`, "PUT", {}, "Document linked.")) && setPicked("")}>
                Link
              </button>
            </>
          )}
          {item.mark ? (
            <button type="button" className="btn ghost small" disabled={busy} onClick={() => act(path, "PATCH", { mark: null }, "Mark cleared.")}>
              Clear mark
            </button>
          ) : (
            <>
              {allows("requested") && (
                <button type="button" className="btn ghost small" disabled={busy} onClick={() => act(path, "PATCH", { mark: "requested" }, "Item marked requested.")}>
                  Mark requested
                </button>
              )}
              {allows("not_required") && (
                <button type="button" className="btn ghost small" disabled={busy} onClick={() => act(path, "PATCH", { mark: "not_required" }, "Item marked not required.")}>
                  Mark not required
                </button>
              )}
            </>
          )}
          {item.removable && (
            <button type="button" className="btn ghost small" disabled={busy} onClick={() => act(path, "DELETE", null, "Checklist item removed.")}>
              Remove
            </button>
          )}
          {onRequest && !item.open_request && !COMPLETE.has(item.status) && !requesting && (
            <button type="button" className="btn ghost small" disabled={busy} onClick={() => setRequesting(true)}>
              Request from student
            </button>
          )}
        </div>
      )}
      {!readOnly && onRequest && requesting && !item.open_request && (
        <RequestForm id={item.id} name={item.name} busy={busy} onCancel={() => setRequesting(false)} onSend={async (body) => (await onRequest(body)) && setRequesting(false)} />
      )}
    </li>
  );
}

function RequestForm({ id, name, busy, onSend, onCancel }: { id: string; name: string; busy: boolean; onSend: (body: RequestBody) => void; onCancel: () => void }) {
  const [due, setDue] = useState("");
  const [note, setNote] = useState("");

  function submit(event: FormEvent) {
    event.preventDefault();
    onSend({ due_date: due, ...(note.trim() ? { note: note.trim() } : {}) });
  }

  return (
    <form className="form" onSubmit={submit} aria-label={`Request ${name} from the student`} style={{ marginTop: 6 }}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor={`request-due-${id}`}>Due date for {name}</label>
          <input id={`request-due-${id}`} type="date" required min={todayInIndia()} value={due} onChange={(event) => setDue(event.target.value)} />
        </div>
        <div className="field">
          <label htmlFor={`request-note-${id}`}>Note to the student (optional)</label>
          <input id={`request-note-${id}`} maxLength={1000} value={note} onChange={(event) => setNote(event.target.value)} />
        </div>
      </div>
      <div className="actions">
        <button className="btn small" disabled={busy}>
          Send request
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function AddItemForm({ busy, onAdd, onCancel }: { busy: boolean; onAdd: (body: { document_type: string; label?: string; required: boolean }) => void; onCancel: () => void }) {
  const [documentType, setDocumentType] = useState<string>(CHECKLIST_DOCUMENT_TYPES[0]);
  const [label, setLabel] = useState("");
  const [required, setRequired] = useState(true);
  const needsName = documentType === "Other";

  function submit(event: FormEvent) {
    event.preventDefault();
    onAdd({ document_type: documentType, ...(label.trim() ? { label: label.trim() } : {}), required });
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Add checklist item" style={{ marginTop: 6 }}>
      <div className="field">
        <label htmlFor="checklist-item-type">Document type</label>
        <select id="checklist-item-type" value={documentType} onChange={(event) => setDocumentType(event.target.value)}>
          {CHECKLIST_DOCUMENT_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="checklist-item-label">Name{needsName ? "" : " (optional)"}</label>
        <input id="checklist-item-label" value={label} maxLength={80} required={needsName} onChange={(event) => setLabel(event.target.value)} />
      </div>
      <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
        <input type="checkbox" checked={required} onChange={(event) => setRequired(event.target.checked)} /> Required
      </label>
      <div className="actions">
        <button className="btn small" disabled={busy}>
          Add to checklist
        </button>
        <button type="button" className="btn ghost small" disabled={busy} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
