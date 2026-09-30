"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import AgentStudentDetailPanel, { assignedText } from "./AgentStudentDetailPanel";
import AgentStudentForm from "./AgentStudentForm";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { AgentStudentDetail, AgentStudentItem, RECORDS_URL } from "@/lib/agentStudents";

// AGN-004 (DEC-SCOPE-041): the agency's students -- with or without a login -- on the Students page. Masters see the agency and
// may archive; staff see their assigned students. The server enforces both; the controls here only follow it. Paging follows
// AgentApprovalPanel (20 per page); archive uses the inline confirmation pattern with focus returned to the opener.
const PAGE_SIZE = 20;
type Confirm = { id: string; kind: "archive" | "unarchive" } | null;

export default function AgentStudentsPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined }) {
  const isMaster = memberRole !== "staff";
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [assigned, setAssigned] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Page<AgentStudentItem> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [confirm, setConfirm] = useState<Confirm>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [detail, setDetail] = useState<AgentStudentDetail | null>(null);
  const [detailState, setDetailState] = useState<"idle" | "loading" | "gone" | "error">("idle");
  const returnFocusTo = useRef<string | null>(null);
  const request = useRef<AbortController | null>(null);

  // Search is debounced; a changed search starts again at page 1.
  useEffect(() => {
    const handle = setTimeout(() => {
      const next = draft.trim().slice(0, 100);
      setQuery((current) => {
        if (current !== next) setOffset(0);
        return next;
      });
    }, 300);
    return () => clearTimeout(handle);
  }, [draft]);

  // Each load cancels the previous one, and a response for an older query is discarded, so a slow earlier search can never
  // overwrite a newer one. The current rows stay on screen (dimmed, aria-busy) until the new page arrives.
  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) params.set("q", query);
    if (showArchived) params.set("include_archived", "true");
    if (isMaster && assigned) params.set("assigned", assigned);
    fetch(`${RECORDS_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentStudentItem>(body)) {
          setLoadError(detailMessage(body?.detail, "Unable to load students."));
          return;
        }
        setData(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError("Unable to load students.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [offset, query, showArchived, assigned, isMaster]);

  useEffect(load, [load]);
  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (confirm === null && returnFocusTo.current) {
      document.getElementById(returnFocusTo.current)?.focus();
      returnFocusTo.current = null;
    }
  }, [confirm]);

  function clearFilters() {
    setDraft("");
    setQuery("");
    setShowArchived(false);
    setAssigned("");
    setOffset(0);
  }

  async function openDetail(id: string) {
    setDetail(null);
    setDetailState("loading");
    try {
      const response = await fetch(`${RECORDS_URL}/${id}`);
      const body = await response.json().catch(() => null);
      if (response.status === 404) return setDetailState("gone");
      if (!response.ok || !body?.student) return setDetailState("error");
      setDetail(body.student);
      setDetailState("idle");
    } catch {
      setDetailState("error");
    }
  }

  function closeDetail() {
    const id = detail?.id;
    setDetail(null);
    if (id) requestAnimationFrame(() => document.getElementById(`agent-student-view-${id}`)?.focus());
  }

  // A write answers with the full record: update the row in place; refetch only when the row leaves the current filter.
  function applyUpdate(s: AgentStudentDetail) {
    setDetail((d) => (d && d.id === s.id ? s : d));
    if (s.status === "archived" && !showArchived) return load();
    setData((d) => (d ? { ...d, items: d.items.some((i) => i.id === s.id) ? d.items.map((i) => (i.id === s.id ? s : i)) : [s, ...d.items] } : d));
  }

  async function act(s: AgentStudentItem, kind: "archive" | "unarchive") {
    setBusyId(s.id);
    setRowError(null);
    setNotice(null);
    try {
      const response = await fetch(`${RECORDS_URL}/${s.id}/${kind}`, { method: "POST" });
      const body = await response.json().catch(() => null);
      if (!response.ok || !body?.student) {
        setRowError({ id: s.id, text: detailMessage(body?.detail, "Unable to complete this action.") });
        return;
      }
      setConfirm(null);
      setNotice(`${s.full_name} ${kind === "archive" ? "archived" : "restored"}.`);
      applyUpdate(body.student);
    } catch {
      setRowError({ id: s.id, text: "Network error. Check your connection and try again." });
    } finally {
      setBusyId(null);
    }
  }

  const filtered = Boolean(query || showArchived || assigned);

  return (
    <div className="action-card agent-students">
      <h3>Students</h3>
      {/* Always mounted so screen readers announce the text when it arrives. */}
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite">
        {notice}
      </div>
      <div role="search" style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8, marginTop: 8 }}>
        <div className="field" style={{ flex: "1 1 220px", margin: 0 }}>
          <label htmlFor="agent-students-search">Search students</label>
          <input id="agent-students-search" type="search" value={draft} maxLength={100} placeholder="Name, email or phone" onChange={(e) => setDraft(e.target.value)} />
        </div>
        <label style={{ display: "flex", gap: 6, alignItems: "center", minHeight: 44 }}>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(e) => {
              setShowArchived(e.target.checked);
              setOffset(0);
            }}
          />
          Show archived
        </label>
        {isMaster && (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="agent-students-assigned">Assigned to</label>
            <select
              id="agent-students-assigned"
              value={assigned}
              onChange={(e) => {
                setAssigned(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">Anyone</option>
              <option value="none">Unassigned</option>
            </select>
          </div>
        )}
        <button type="button" className="btn small" onClick={() => setAdding(true)} disabled={adding}>
          Add student
        </button>
      </div>

      {adding && (
        <AgentStudentForm
          mode="create"
          onCancel={() => setAdding(false)}
          onSaved={(s) => {
            setAdding(false);
            setNotice(`${s.full_name} added.`);
            applyUpdate(s);
          }}
        />
      )}

      {/* Above the list: a list refresh (search, paging, archive) never moves the record being read or edited. */}
      {detailState === "loading" && (
        <p className="muted" aria-live="polite">
          Loading student…
        </p>
      )}
      {detailState === "gone" && (
        <p className="form-error" role="alert">
          This student is no longer available.
        </p>
      )}
      {detailState === "error" && (
        <p className="form-error" role="alert">
          Unable to load this student.
        </p>
      )}
      {detail && (
        <AgentStudentDetailPanel
          key={detail.id}
          detail={detail}
          onClose={closeDetail}
          onSaved={(s) => {
            setNotice(`${s.full_name} saved.`);
            applyUpdate(s);
          }}
        />
      )}

      <section aria-label="Student list" aria-busy={loading} style={{ marginTop: 16, opacity: loading && data ? 0.6 : 1 }}>
        {loadError ? (
          <>
            <p className="form-error" role="alert">
              {loadError}
            </p>
            <button type="button" className="btn secondary small" onClick={load}>
              Retry
            </button>
          </>
        ) : data === null ? (
          <p className="muted">Loading students…</p>
        ) : data.items.length === 0 ? (
          filtered ? (
            <p className="muted">
              No students match.{" "}
              <button type="button" className="btn secondary small" onClick={clearFilters}>
                Clear filters
              </button>
            </p>
          ) : (
            <p className="muted">No students yet. Use Add student to record the first one.</p>
          )
        ) : (
          <>
            {/* Cards (the AgentApprovalPanel layout), not a table: the page's roster table above stays the only table, and the
                grid already collapses to one column on phones. */}
            <ul className="grid two" aria-label="Students" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.items.map((s) => {
                const kind = s.status === "archived" ? "unarchive" : "archive";
                const openerId = `agent-student-${kind}-${s.id}`;
                return (
                  <li className="card" key={s.id}>
                    <span className="badge">{s.status === "archived" ? "Archived" : "Active"}</span> <span className="badge">{s.has_login ? "Has login" : "No login"}</span>
                    <h4 style={{ marginTop: 10, fontSize: "1rem", overflowWrap: "anywhere" }}>{s.full_name}</h4>
                    <dl className="record-details" style={{ fontSize: 13 }}>
                      <dt>Contact</dt>
                      <dd>{[s.email, s.phone].filter(Boolean).join(" · ") || "—"}</dd>
                      <dt>Preference</dt>
                      <dd>{[s.preferred_country, s.preferred_intake].filter(Boolean).join(", ") || "—"}</dd>
                      <dt>Assigned to</dt>
                      <dd>{assignedText(s.assigned_to)}</dd>
                    </dl>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                        <button id={`agent-student-view-${s.id}`} type="button" className="btn secondary small" aria-label={`View ${s.full_name}`} onClick={() => openDetail(s.id)}>
                          View
                        </button>{" "}
                        {isMaster &&
                          (confirm?.id === s.id ? (
                            <span role="group" aria-label={`Confirm ${confirm.kind} ${s.full_name}`}>
                              <button type="button" className="btn small" autoFocus disabled={busyId === s.id} onClick={() => act(s, confirm.kind)}>
                                {busyId === s.id ? "Working…" : `Confirm ${confirm.kind}`}
                              </button>{" "}
                              <button
                                type="button"
                                className="btn secondary small"
                                disabled={busyId === s.id}
                                onClick={() => {
                                  returnFocusTo.current = openerId;
                                  setConfirm(null);
                                }}
                              >
                                Cancel
                              </button>
                            </span>
                          ) : (
                            <button
                              id={openerId}
                              type="button"
                              className="btn secondary small"
                              aria-label={`${kind === "archive" ? "Archive" : "Unarchive"} ${s.full_name}`}
                              onClick={() => {
                                setRowError(null);
                                setConfirm({ id: s.id, kind });
                              }}
                            >
                              {kind === "archive" ? "Archive" : "Unarchive"}
                            </button>
                          ))}
                    </div>
                    {rowError?.id === s.id && (
                      <p className="form-error" role="status" aria-live="polite" style={{ fontSize: 13, marginTop: 8 }}>
                        {rowError.text}
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            <nav aria-label="Student pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
              </span>
              <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                Previous
              </button>
              <button
                type="button"
                className="btn secondary small"
                aria-label="Next page"
                disabled={data.offset + data.items.length >= data.total || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Next
              </button>
            </nav>
          </>
        )}
      </section>
    </div>
  );
}
