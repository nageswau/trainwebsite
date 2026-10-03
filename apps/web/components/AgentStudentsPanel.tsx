"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import AgentStudentAssign from "./AgentStudentAssign";
import { LEAVE_PROMPT as COUNSELING_LEAVE_PROMPT } from "./AgentStudentCounselingForm";
import AgentStudentDetailPanel, { assignedText } from "./AgentStudentDetailPanel";
import AgentStudentForm from "./AgentStudentForm";
import { detailMessage, isPage, Page } from "@/lib/apiErrors";
import { AgentStudentDetail, AgentStudentItem, RECORDS_URL } from "@/lib/agentStudents";

// AGN-004 (DEC-SCOPE-042): the agency's students -- with or without a login -- on the Students page. Masters see the agency and
// may archive and assign; staff see their assigned students. The server enforces both; the controls here only follow it. Paging follows
// AgentApprovalPanel (20 per page); archive uses the inline confirmation pattern with focus returned to the opener.
const PAGE_SIZE = 20;
const LIST_ID = "agent-students-list";
const ADD_ID = "agent-student-add";
type Confirm = { id: string; kind: "archive" | "unarchive" } | null;

// Browser QA-10: an email has no spaces, so on a narrow card it broke mid-word ("…edusphere.loca / l"). Offer line-break
// points after "@" and each "." instead; the text itself (and what a screen reader reads) is unchanged.
function breakable(text: string) {
  return text.split(/(?<=[@.])/).map((part, i) => (
    <span key={i}>
      {i > 0 && <wbr />}
      {part}
    </span>
  ));
}

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
  const detailRequest = useRef(0); // only the latest View may fill the detail panel
  const lastDetailId = useRef<string | null>(null);
  // AGN-006 review #2: an open counseling form with unsaved input -- opening another student asks first.
  const unsavedCounseling = useRef(false);
  const trackCounseling = useCallback((dirty: boolean) => {
    unsavedCounseling.current = dirty;
  }, []);
  // Browser QA-06: search, Show archived and page live in the URL (the AgentApprovalPanel pattern), so refresh and Back keep
  // them. Read once on mount (the server has no URL state to match) and hold the first fetch until then.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const searched = (params.get("q") ?? "").trim().slice(0, 100);
    setDraft(searched);
    setQuery(searched);
    setShowArchived(params.get("archived") === "1");
    const pageNumber = Number.parseInt(params.get("page") ?? "1", 10);
    if (Number.isFinite(pageNumber) && pageNumber > 1) setOffset((pageNumber - 1) * PAGE_SIZE);
    setReady(true);
  }, []);

  // AGN-018 (DEC-SCOPE-061 G4): the staff sidebar's "Add" link (?new=1) opens the add form -- on first load and when the link is
  // clicked while this panel is already on screen (a client navigation changes only the query). Its Full name field takes focus;
  // `new` is dropped through the router (browser QA18-01: a raw history.replaceState left the router's search params at new=1, so the
  // next Add changed nothing), so Back and refresh do not reopen it and every later Add is a real change.
  const router = useRouter();
  const wantsNew = useSearchParams().get("new") === "1";
  useEffect(() => {
    if (!wantsNew) return;
    setAdding(true);
    const params = new URLSearchParams(window.location.search);
    params.delete("new");
    const rest = params.toString();
    router.replace(`${window.location.pathname}${rest ? `?${rest}` : ""}`, { scroll: false });
  }, [wantsNew, router]);

  useEffect(() => {
    if (!ready) return;
    const params = new URLSearchParams(window.location.search);
    ["q", "archived", "page"].forEach((key) => params.delete(key));
    if (query) params.set("q", query);
    if (showArchived) params.set("archived", "1");
    if (offset > 0) params.set("page", String(offset / PAGE_SIZE + 1));
    const search = params.toString();
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${search ? `?${search}` : ""}${window.location.hash}`);
  }, [ready, query, showArchived, offset]);

  // Search is debounced; a changed search starts again at page 1.
  useEffect(() => {
    const next = draft.trim().slice(0, 100);
    if (next === query) return;
    const handle = setTimeout(() => {
      setQuery(next);
      setOffset(0);
    }, 300);
    return () => clearTimeout(handle);
  }, [draft, query]);

  // Each load cancels the previous one, and a response for an older query is discarded, so a slow earlier search can never
  // overwrite a newer one. The current rows stay on screen (dimmed, aria-busy) until the new page arrives.
  const load = useCallback(() => {
    if (!ready) return;
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
        // The last card of a later page was archived (or removed elsewhere): step back instead of a false empty state.
        if (body.items.length === 0 && body.offset > 0) {
          setOffset(Math.max(0, body.offset - PAGE_SIZE));
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
  }, [ready, offset, query, showArchived, assigned, isMaster]);

  useEffect(load, [load]);
  useEffect(() => () => request.current?.abort(), []);

  useEffect(() => {
    if (confirm === null && returnFocusTo.current) {
      document.getElementById(returnFocusTo.current)?.focus();
      returnFocusTo.current = null;
    }
  }, [confirm]);

  // AGN-005 QA5-02: Add student is disabled while its form is open, so keyboard focus would fall to the page; give it back to the
  // opener once the form closes (Cancel or saved). An effect runs after the commit that re-enables the button -- a frame-timed
  // focus missed it after a save, which re-renders outside the click (browser re-check).
  const focusAddOnClose = useRef(false);
  function closeAdd() {
    focusAddOnClose.current = true;
    setAdding(false);
  }
  useEffect(() => {
    if (!adding && focusAddOnClose.current) {
      focusAddOnClose.current = false;
      document.getElementById(ADD_ID)?.focus();
    }
  }, [adding]);

  function clearFilters() {
    setDraft("");
    setQuery("");
    setShowArchived(false);
    setAssigned("");
    setOffset(0);
  }

  async function openDetail(id: string) {
    if (unsavedCounseling.current && !window.confirm(COUNSELING_LEAVE_PROMPT)) return;
    const ticket = ++detailRequest.current;
    const current = () => ticket === detailRequest.current; // a slower, earlier View must not replace a later one
    lastDetailId.current = id;
    setDetail(null);
    setDetailState("loading");
    try {
      const response = await fetch(`${RECORDS_URL}/${id}`);
      const body = await response.json().catch(() => null);
      if (!current()) return;
      if (response.status === 404) return setDetailState("gone");
      if (!response.ok || !body?.student) return setDetailState("error");
      setDetail(body.student);
      setDetailState("idle");
    } catch {
      if (current()) setDetailState("error");
    }
  }

  function closeDetail() {
    const id = detail?.id;
    setDetail(null);
    if (id) requestAnimationFrame(() => document.getElementById(`agent-student-view-${id}`)?.focus());
  }

  // An edit or archive answers with the full record: update its card in place; refetch only when it leaves the current filter.
  // (Adding a student reloads the list instead -- the new one may not belong to this page or filter.)
  function applyUpdate(s: AgentStudentDetail) {
    setDetail((d) => (d && d.id === s.id ? s : d));
    if (s.status === "archived" && !showArchived) return load();
    setData((d) => (d ? { ...d, items: d.items.map((i) => (i.id === s.id ? s : i)) } : d));
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
      // Keyboard focus survives the confirmation unmounting: onto the row's new opposite action, or onto the list when the
      // row leaves the current view.
      const leaves = body.student.status === "archived" && !showArchived;
      returnFocusTo.current = leaves ? LIST_ID : `agent-student-${kind === "archive" ? "unarchive" : "archive"}-${s.id}`;
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
      <h3>All students</h3>
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
        <button id={ADD_ID} type="button" className="btn small" onClick={() => setAdding(true)} disabled={adding}>
          Add student
        </button>
      </div>

      {adding && (
        <AgentStudentForm
          mode="create"
          onCancel={closeAdd}
          onSaved={(s) => {
            closeAdd();
            setNotice(`${s.full_name} added.`);
            load(); // the new student may not belong to this page or filter, and the total changes
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
          Unable to load this student.{" "}
          {/* Browser QA-09: the failed View can be retried in place. */}
          <button type="button" className="btn secondary small" aria-label="Retry loading the student" onClick={() => lastDetailId.current && openDetail(lastDetailId.current)}>
            Retry
          </button>
        </p>
      )}
      {detail && (
        <AgentStudentDetailPanel
          key={detail.id}
          detail={detail}
          onClose={closeDetail}
          onDirtyChange={trackCounseling}
          onSaved={(s, notice) => {
            setNotice(notice ?? `${s.full_name} saved.`);
            applyUpdate(s);
          }}
        />
      )}

      <section id={LIST_ID} tabIndex={-1} aria-label="Student list" aria-busy={loading} style={{ marginTop: 16, opacity: loading && data ? 0.6 : 1 }}>
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
                      <dd>
                        {s.email || s.phone ? (
                          <>
                            {s.email && breakable(s.email)}
                            {s.email && s.phone && " · "}
                            {s.phone}
                          </>
                        ) : (
                          "—"
                        )}
                      </dd>
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
                        {isMaster && s.status === "active" && confirm?.id !== s.id && (
                          <AgentStudentAssign
                            student={s}
                            onAssigned={(updated) => {
                              setNotice(updated.assigned_to ? `${s.full_name} assigned to ${assignedText(updated.assigned_to)}.` : `${s.full_name} unassigned.`);
                              applyUpdate(updated);
                            }}
                          />
                        )}
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
