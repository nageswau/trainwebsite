"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AgentShortlistForm from "./AgentShortlistForm";
import { detailMessage, isPage, type Page } from "@/lib/apiErrors";
import { PAGE_SIZE, type ShortlistEntry, shortlistUrl } from "@/lib/agentShortlist";

// AGN-007 (DEC-SCOPE-049 D2/D3/D5): a student's university shortlist inside the AGN-004 detail view. Masters and staff (in scope) add,
// edit and remove; an archived student's shortlist is read-only. Paging and the inline confirm follow AgentStudentsPanel; the focus
// handling follows AgentUniversitiesPanel (spec §6.4).
type Editing = { mode: "add" } | { mode: "edit"; entry: ShortlistEntry } | null;
const ADD_ID = "shortlist-add";
const editId = (id: string) => `shortlist-edit-${id}`;
const removeId = (id: string) => `shortlist-remove-${id}`;
// Focus moves after the control has been re-rendered; fall back to the next id when the target is gone.
const focusLater = (...ids: string[]) =>
  requestAnimationFrame(() => {
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) return el.focus();
    }
  });

function ShortlistCard({ e, writable, confirming, removing, onEdit, onAskRemove, onCancelRemove, onRemove }: {
  e: ShortlistEntry; writable: boolean; confirming: boolean; removing: boolean; onEdit: () => void; onAskRemove: () => void; onCancelRemove: () => void; onRemove: () => void;
}) {
  const name = e.university.name;
  return (
    <li className="card">
      <strong>{name}</strong> {e.university.source === "agency" && <span className="badge">Agency</span>}
      <p className="muted">
        <span>{e.university.country ?? "—"}</span>
        {e.course && <> · <span>{e.course.title}</span></>}
      </p>
      {e.intake && <p>Intake: {e.intake}</p>}
      {e.tuition_fee && <p>Tuition fee: {e.tuition_fee}</p>}
      {e.entry_requirements && (
        <details>
          <summary>Entry requirements</summary>
          <p style={{ whiteSpace: "pre-line" }}>{e.entry_requirements}</p>
        </details>
      )}
      {writable &&
        (confirming ? (
          <span
            role="group"
            aria-label={`Confirm remove ${name}`}
            onKeyDown={(k) => {
              if (k.key === "Escape") {
                k.stopPropagation(); // the detail panel closes on Escape too; only the confirm closes here
                onCancelRemove();
              }
            }}
          >
            <button type="button" className="btn small" disabled={removing} onClick={onRemove}>Confirm remove</button>{" "}
            <button type="button" className="btn secondary small" autoFocus onClick={onCancelRemove}>Cancel</button>
          </span>
        ) : (
          <>
            <button id={editId(e.id)} type="button" className="btn secondary small" aria-label={`Edit ${name}`} onClick={onEdit}>Edit</button>{" "}
            <button id={removeId(e.id)} type="button" className="btn secondary small" aria-label={`Remove ${name}`} onClick={onAskRemove}>Remove</button>
          </>
        ))}
    </li>
  );
}

export default function AgentShortlistPanel({ studentId, archived, onStudentGone, onStudentChanged }: { studentId: string; archived: boolean; onStudentGone: () => void; onStudentChanged: () => void }) {
  const [data, setData] = useState<Page<ShortlistEntry> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [removing, setRemoving] = useState(false);
  const [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);
  // The parent's callbacks are re-created on each of its renders; refs keep them out of any dependency list (no refetch loop).
  const gone = useRef(onStudentGone);
  gone.current = onStudentGone;
  const changed = useRef(onStudentChanged);
  changed.current = onStudentChanged;

  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    fetch(`${shortlistUrl(studentId)}?limit=${PAGE_SIZE}&offset=${offset}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (response.status === 404) return gone.current();
        if (!response.ok || !isPage<ShortlistEntry>(body)) return setLoadError(detailMessage(body?.detail, "Unable to load the shortlist."));
        if (body.items.length === 0 && body.offset > 0) return setOffset(Math.max(0, body.offset - PAGE_SIZE));
        setData(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError("Unable to load the shortlist.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [studentId, offset]);

  useEffect(load, [load]);
  useEffect(() => () => request.current?.abort(), []);

  function closeForm() {
    const opener = editing?.mode === "edit" ? editId(editing.entry.id) : ADD_ID;
    setEditing(null);
    focusLater(opener, ADD_ID);
  }

  function closeConfirm(id: string) {
    setConfirmId(null);
    focusLater(removeId(id), ADD_ID);
  }

  async function remove(e: ShortlistEntry) {
    if (removing) return;
    setRemoving(true);
    setActionError(null);
    try {
      const response = await fetch(`${shortlistUrl(studentId)}/${e.id}`, { method: "DELETE" });
      if (response.status === 409) return changed.current();
      if (response.ok || response.status === 404) {
        // 404 after our own delete = done
        setConfirmId(null);
        setNotice(`${e.university.name} removed from the shortlist.`);
        focusLater(ADD_ID);
        return load();
      }
      setActionError(detailMessage((await response.json().catch(() => null))?.detail, "Unable to remove the entry."));
    } catch {
      setActionError("Network error. Check your connection and try again.");
    } finally {
      setRemoving(false);
    }
    closeConfirm(e.id);
  }

  const writable = !archived;
  return (
    <section aria-labelledby={`shortlist-${studentId}`} style={{ marginTop: 16 }}>
      <h5 id={`shortlist-${studentId}`}>University shortlist</h5>
      {archived && <p className="muted">This student is archived; the shortlist is read-only.</p>}
      <p aria-live="polite">{notice}</p>
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      {writable &&
        (editing ? (
          <AgentShortlistForm
            studentId={studentId}
            mode={editing.mode}
            entry={editing.mode === "edit" ? editing.entry : undefined}
            onCancel={closeForm}
            onGone={onStudentGone}
            onConflict={onStudentChanged}
            onSaved={() => {
              setNotice("Saved to shortlist.");
              closeForm();
              load();
            }}
          />
        ) : (
          <button id={ADD_ID} type="button" className="btn small" onClick={() => setEditing({ mode: "add" })}>
            Add university to shortlist
          </button>
        ))}
      <div aria-busy={loading} style={{ marginTop: 12, opacity: loading && data ? 0.6 : 1 }}>
        {loadError ? (
          <>
            <p className="form-error" role="alert">{loadError}</p>
            <button type="button" className="btn secondary small" aria-label="Retry loading the shortlist" onClick={load}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted">Loading the shortlist…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">No universities shortlisted yet.</p>
        ) : (
          <>
            <ul aria-label="Shortlist" className="grid two" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.items.map((e) => (
                <ShortlistCard
                  key={e.id}
                  e={e}
                  writable={writable}
                  confirming={confirmId === e.id}
                  removing={removing}
                  onEdit={() => setEditing({ mode: "edit", entry: e })}
                  onAskRemove={() => setConfirmId(e.id)}
                  onCancelRemove={() => closeConfirm(e.id)}
                  onRemove={() => void remove(e)}
                />
              ))}
            </ul>
            <p className="muted">Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</p>
            <button type="button" className="btn secondary small" aria-label="Previous page of the shortlist" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>{" "}
            <button type="button" className="btn secondary small" aria-label="Next page of the shortlist" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
          </>
        )}
      </div>
    </section>
  );
}
