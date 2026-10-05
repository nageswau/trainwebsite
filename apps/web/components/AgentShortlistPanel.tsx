"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import ShortlistCard, { editId, removeId } from "./AgentShortlistCard";
import AgentShortlistForm from "./AgentShortlistForm";
import { isPage, type Page } from "@/lib/apiErrors";
import { failureText, PAGE_SIZE, type ShortlistEntry, shortlistUrl } from "@/lib/agentShortlist";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// AGN-007 (DEC-SCOPE-049 D2/D3/D5): a student's university shortlist inside the AGN-004 detail view. Masters and staff (in scope) add,
// edit and remove; an archived student's shortlist is read-only. Paging and the inline confirm follow AgentStudentsPanel; the focus
// handling follows AgentUniversitiesPanel (spec §6.4).
type Editing = { mode: "add" } | { mode: "edit"; entry: ShortlistEntry } | null;
const ADD_ID = "shortlist-add";

// `onChanged` (AGN-015 QA15-01): told after this panel saves or removes an entry, so the student's journey can reload.
export default function AgentShortlistPanel({
  studentId,
  archived,
  onStudentGone,
  onStudentChanged,
  onChanged,
}: {
  studentId: string;
  archived: boolean;
  onStudentGone: () => void;
  onStudentChanged: () => void;
  onChanged?: () => void;
}) {
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
  const focusLater = useFocusAfterRender(); // falls back to the next id when the target is gone
  // The parent's callbacks are re-created on each of its renders; a ref keeps onStudentGone out of load's dependencies (no refetch loop).
  const gone = useRef(onStudentGone);
  gone.current = onStudentGone;

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
        if (!response.ok || !isPage<ShortlistEntry>(body)) return setLoadError(failureText(response.status, body?.detail, "Unable to load the shortlist."));
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

  function openForm(next: Editing) {
    setConfirmId(null);
    setEditing(next);
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
      if (response.status === 409) return onStudentChanged();
      const body = response.status === 204 ? null : await response.json().catch(() => null);
      if (response.status === 404 && body?.detail === "Student not found") return onStudentGone();
      if (response.ok || response.status === 404) {
        // an entry 404 after our own delete = done
        setConfirmId(null);
        setNotice(`${e.university.name} removed from the shortlist.`);
        focusLater(ADD_ID);
        onChanged?.();
        return load();
      }
      setActionError(failureText(response.status, body?.detail, "Unable to remove the entry."));
    } catch {
      setActionError("Network error. Check your connection and try again.");
    } finally {
      setRemoving(false);
    }
    closeConfirm(e.id);
  }

  const writable = !archived;
  const formKey = editing?.mode === "edit" ? editing.entry.id : "add"; // a different target never inherits another row's draft
  return (
    <section aria-labelledby={`shortlist-${studentId}`} style={{ marginTop: 16 }}>
      {/* Browser QA-07: the h5 level stays (under the detail's h4); the size reads as a section heading. */}
      <h5 id={`shortlist-${studentId}`} style={{ fontSize: "18px", margin: "0 0 8px" }}>
        University shortlist
      </h5>
      {archived && <p className="muted">This student is archived; the shortlist is read-only.</p>}
      <p aria-live="polite">{notice}</p>
      {actionError && <p className="form-error" role="alert">{actionError}</p>}
      {writable &&
        (editing ? (
          <AgentShortlistForm
            key={formKey}
            studentId={studentId}
            mode={editing.mode}
            entry={editing.mode === "edit" ? editing.entry : undefined}
            onCancel={closeForm}
            onGone={onStudentGone}
            onEntryGone={() => {
              // The entry's Edit button disappears on reload, so focus goes to Add rather than the opener.
              setEditing(null);
              focusLater(ADD_ID);
              setNotice("This entry was removed by someone else.");
              load();
            }}
            onConflict={onStudentChanged}
            onSaved={() => {
              setNotice("Saved to shortlist.");
              closeForm();
              load();
              onChanged?.();
            }}
          />
        ) : (
          <button id={ADD_ID} type="button" className="btn small" onClick={() => openForm({ mode: "add" })}>
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
                  writable={writable && !editing}
                  confirming={confirmId === e.id}
                  removing={removing}
                  onEdit={() => openForm({ mode: "edit", entry: e })}
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
