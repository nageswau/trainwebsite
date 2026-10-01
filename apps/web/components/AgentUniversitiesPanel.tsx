"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import AgentUniversityForm from "./AgentUniversityForm";
import { detailMessage, isPage, type Page } from "@/lib/apiErrors";
import { type AgentUniversity, PAGE_SIZE, UNIVERSITIES_URL } from "@/lib/agentShortlist";

// AGN-007 (DEC-SCOPE-049): the agency's own universities. §6 "University Database": Masters full, Staff view; "Add University" is
// Master only. The server enforces both; the controls here only follow it. Paging and the inline confirm follow AgentStudentsPanel.
type Editing = { mode: "add" } | { mode: "edit"; university: AgentUniversity } | null;

export default function AgentUniversitiesPanel({ memberRole }: { memberRole: "master" | "staff" | null | undefined }) {
  const isMaster = memberRole !== "staff";
  const [data, setData] = useState<Page<AgentUniversity> | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [draftQuery, setDraftQuery] = useState("");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Editing>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; text: string } | null>(null);
  const [notice, setNotice] = useState("");
  const request = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setLoadError(null);
    const params = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
    if (query) params.set("q", query);
    fetch(`${UNIVERSITIES_URL}?${params}`, { signal: controller.signal })
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (controller.signal.aborted) return;
        if (!response.ok || !isPage<AgentUniversity>(body)) return setLoadError(detailMessage(body?.detail, "Unable to load universities."));
        if (body.items.length === 0 && body.offset > 0) return setOffset(Math.max(0, body.offset - PAGE_SIZE));
        setData(body);
      })
      .catch(() => {
        if (!controller.signal.aborted) setLoadError("Unable to load universities.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  }, [offset, query]);

  useEffect(load, [load]);
  useEffect(() => () => request.current?.abort(), []);

  function search(e: FormEvent) {
    e.preventDefault();
    setQuery(draftQuery.trim());
    setOffset(0);
  }

  async function remove(u: AgentUniversity) {
    setRowError(null);
    try {
      const response = await fetch(`${UNIVERSITIES_URL}/${u.id}`, { method: "DELETE" });
      if (response.status === 204 || response.status === 404) {
        setConfirmId(null);
        setNotice(`${u.name} deleted.`);
        return load();
      }
      const body = await response.json().catch(() => null);
      setRowError({ id: u.id, text: detailMessage(body?.detail, "Unable to delete the university.") });
    } catch {
      setRowError({ id: u.id, text: "Network error. Check your connection and try again." });
    }
    setConfirmId(null);
  }

  return (
    <div className="portal-content">
      <h2>Universities</h2>
      <p className="muted">
        Your agency&apos;s own universities. Masters add and edit them; everyone in your agency can use them on a student&apos;s shortlist.{" "}
        <Link href="/overseas/universities">Browse the university catalogue</Link>
      </p>
      <form role="search" onSubmit={search} className="field">
        <label htmlFor="agent-universities-q">Search universities</label>
        <input id="agent-universities-q" type="search" maxLength={100} value={draftQuery} onChange={(e) => setDraftQuery(e.target.value)} />
      </form>
      <p aria-live="polite">{notice}</p>
      {isMaster &&
        (editing ? (
          <AgentUniversityForm
            mode={editing.mode}
            university={editing.mode === "edit" ? editing.university : undefined}
            onCancel={() => setEditing(null)}
            onSaved={(u) => {
              setNotice(`${u.name} ${editing.mode === "add" ? "added" : "saved"}.`);
              setEditing(null);
              load();
            }}
          />
        ) : (
          <button type="button" className="btn small" onClick={() => setEditing({ mode: "add" })}>
            Add university
          </button>
        ))}
      <section aria-busy={loading} style={{ marginTop: 16, opacity: loading && data ? 0.6 : 1 }}>
        {loadError ? (
          <>
            <p className="form-error" role="alert">
              {loadError}
            </p>
            <button type="button" className="btn secondary small" aria-label="Retry loading universities" onClick={load}>
              Retry
            </button>
          </>
        ) : data === null ? (
          <p className="muted">Loading universities…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">Your agency hasn&apos;t added any universities yet.</p>
        ) : (
          <>
            <ul aria-label="Agency universities" className="grid two" style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {data.items.map((u) => (
                <li key={u.id} className="card">
                  <h3>{u.name}</h3>
                  <p className="muted">{[u.country, u.city].filter(Boolean).join(" · ")}</p>
                  {u.entry_requirements && (
                    <details>
                      <summary>Entry requirements</summary>
                      <p style={{ whiteSpace: "pre-line" }}>{u.entry_requirements}</p>
                    </details>
                  )}
                  {isMaster &&
                    (confirmId === u.id ? (
                      <span role="group" aria-label={`Confirm delete ${u.name}`}>
                        <button type="button" className="btn small" autoFocus onClick={() => void remove(u)}>
                          Confirm delete
                        </button>{" "}
                        <button type="button" className="btn secondary small" onClick={() => setConfirmId(null)}>
                          Cancel
                        </button>
                      </span>
                    ) : (
                      <>
                        <button type="button" className="btn secondary small" aria-label={`Edit ${u.name}`} onClick={() => setEditing({ mode: "edit", university: u })}>
                          Edit
                        </button>{" "}
                        <button type="button" className="btn secondary small" aria-label={`Delete ${u.name}`} onClick={() => setConfirmId(u.id)}>
                          Delete
                        </button>
                      </>
                    ))}
                  {rowError?.id === u.id && (
                    <p className="form-error" role="status" aria-live="polite">
                      {rowError.text}
                    </p>
                  )}
                </li>
              ))}
            </ul>
            <p className="muted">
              Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}
            </p>
            <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0 || loading} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </button>{" "}
            <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total || loading} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </button>
          </>
        )}
      </section>
    </div>
  );
}
