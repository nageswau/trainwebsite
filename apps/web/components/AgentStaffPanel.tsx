"use client";

import { useCallback, useEffect, useState } from "react";

import { STAFF_URL, type StaffMember } from "@/lib/agentStaff";
import { isPage, type Page } from "@/lib/apiErrors";

import AgentStaffCreateForm from "./AgentStaffCreateForm";
import AgentStaffRow from "./AgentStaffRow";

const PAGE_SIZE = 20;

// AGN-002 (DEC-SCOPE-040): the agency's staff logins, 20 per page, below the Masters on the Team screen. Results of row actions
// are announced here; the add form announces its own.
export default function AgentStaffPanel() {
  const [data, setData] = useState<Page<StaffMember> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback((at: number) => {
    setLoadFailed(false);
    fetch(`${STAFF_URL}?limit=${PAGE_SIZE}&offset=${at}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(res)))
      .then((body: unknown) => {
        if (!isPage<StaffMember>(body)) throw new Error("not a page");
        // A page emptied by a change (here or by another Master) steps back one page.
        if (body.items.length === 0 && at > 0) {
          setOffset(Math.max(0, at - PAGE_SIZE));
          return;
        }
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(() => {
    load(offset);
  }, [load, offset]);

  const reload = () => load(offset);

  if (loadFailed) {
    return (
      <div className="action-card">
        <h3>Staff</h3>
        <p className="form-error" role="alert">Unable to load your staff.</p>
        <button className="btn secondary small" onClick={reload}>Retry</button>
      </div>
    );
  }
  if (data === null) {
    return (
      <div className="action-card" aria-busy="true">
        <h3>Staff</h3>
        <p className="muted">Loading staff…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Staff</h3>
      <p className="muted" style={{ fontSize: 13 }}>Staff work on your agency&apos;s students and applications. Only Masters see the team and commissions.</p>
      {/* Always mounted so screen readers announce the text when it arrives; styled only while it has something to say. */}
      <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8, overflowWrap: "anywhere" } : undefined}>{notice}</div>
      {data.items.length === 0 ? (
        <p className="muted">No staff yet. Add your first staff member below.</p>
      ) : (
        <ul style={{ paddingLeft: 0, listStyle: "none" }}>
          {data.items.map((m) => (
            <AgentStaffRow
              key={m.id}
              member={m}
              onChanged={(message) => {
                setNotice(message);
                reload();
              }}
            />
          ))}
        </ul>
      )}
      {data.total > PAGE_SIZE && (
        <nav aria-label="Staff pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginBottom: 12 }}>
          <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
          <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
          <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
        </nav>
      )}
      <AgentStaffCreateForm onCreated={reload} />
    </div>
  );
}
