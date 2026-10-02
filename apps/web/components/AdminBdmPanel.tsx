"use client";
import { useCallback, useEffect, useState } from "react";

import AdminBdmCreateForm from "@/components/AdminBdmCreateForm";
import AdminBdmRow from "@/components/AdminBdmRow";
import { isPage, type Page } from "@/lib/apiErrors";
import { BDMS_URL, MANAGERS_URL, PAGE_SIZE, type BdmAdminRow, type BdmManagerOption } from "@/lib/bdm";

// bdm-001 (spec §6.3): the admin's BDM list -- loading / error+Retry / empty / pager (AgentStaffPanel's pattern). The API scopes rows
// to the types this admin manages (D10); nothing here filters for security. The current page stays on screen while the next loads.
export default function AdminBdmPanel({ role }: { role: string }) {
  const [data, setData] = useState<Page<BdmAdminRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [managers, setManagers] = useState<BdmManagerOption[] | null>(null);
  const [managersFailed, setManagersFailed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback((at: number) => {
    setLoadFailed(false);
    fetch(`${BDMS_URL}?limit=${PAGE_SIZE}&offset=${at}`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<BdmAdminRow>(body)) throw new Error("not a page");
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, []);

  useEffect(() => {
    load(offset);
  }, [load, offset]);

  // A failed picker load is NOT "no managers" (review Important #1): it stays null (create disabled) with its own alert and Retry.
  const loadManagers = useCallback(() => {
    setManagersFailed(false);
    setManagers(null);
    fetch(`${MANAGERS_URL}?limit=100`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<BdmManagerOption>(body)) throw new Error("not a page");
        setManagers(body.items);
      })
      .catch(() => setManagersFailed(true));
  }, []);

  useEffect(() => {
    loadManagers();
  }, [loadManagers]);

  const reload = () => load(offset);

  return (
    <>
      {managersFailed && (
        <div className="action-card">
          <p className="form-error" role="alert">Unable to load BDM managers.</p>
          <button type="button" className="btn secondary small" onClick={loadManagers}>Retry loading managers</button>
        </div>
      )}
      <AdminBdmCreateForm role={role} managers={managers} onCreated={reload} />
      <div className="action-card" aria-busy={data === null && !loadFailed}>
        <h3>BDMs</h3>
        <div className={notice ? "form-message" : undefined} role="status" aria-live="polite" style={notice ? { marginBottom: 8 } : undefined}>{notice}</div>
        {loadFailed ? (
          <>
            <p className="form-error" role="alert">Unable to load BDMs.</p>
            <button type="button" className="btn secondary small" onClick={reload}>Retry</button>
          </>
        ) : data === null ? (
          <p className="muted" role="status">Loading BDMs…</p>
        ) : data.total === 0 ? (
          <p className="empty" role="status">No BDMs yet. Use Create BDM above to add the first one.</p>
        ) : (
          <>
            <div className="table-wrap" role="region" aria-label="BDMs" tabIndex={0}>
              <table>
                <thead>
                  <tr>
                    <th scope="col">Name</th><th scope="col">Employee ID</th><th scope="col">Module</th><th scope="col">Territory</th>
                    <th scope="col">Manager</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r) => (
                    <AdminBdmRow key={r.id} row={r} managers={managers} onChanged={(text) => { setNotice(text); reload(); }} />
                  ))}
                </tbody>
              </table>
            </div>
            {data.total > PAGE_SIZE && (
              <nav aria-label="BDM pages" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                <span className="muted" style={{ fontSize: 13 }}>Showing {data.offset + 1}–{data.offset + data.items.length} of {data.total}</span>
                <button type="button" className="btn secondary small" aria-label="Previous page" disabled={data.offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
                <button type="button" className="btn secondary small" aria-label="Next page" disabled={data.offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
              </nav>
            )}
          </>
        )}
      </div>
    </>
  );
}
