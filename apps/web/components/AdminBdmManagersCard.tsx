"use client";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendJson, type Page } from "@/lib/apiErrors";
import { type BdmManagerRow, bdmCountText, MANAGERS_URL, managerDeactivateUrl, managerSearch, PAGE_SIZE } from "@/lib/bdm";
import type { PickOption } from "@/lib/lookups";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-025 (DEC-SCOPE-082 L4, AC4): the Super Admin's BDM managers. A manager who still has BDMs is deactivated only together with a
// replacement manager, who takes every one of them (and so their pending travel approvals) in one step. The server re-checks it all.
export default function AdminBdmManagersCard({ onChanged }: { onChanged: (notice: string) => void }) {
  const [data, setData] = useState<Page<BdmManagerRow> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);
  const [offset, setOffset] = useState(0);
  const [open, setOpen] = useState<string | null>(null);
  const [picked, setPicked] = useState<PickOption | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const focus = useFocusAfterRender();

  const load = useCallback(() => {
    setLoadFailed(false);
    fetch(`${MANAGERS_URL}?limit=${PAGE_SIZE}&offset=${offset}`)
      .then(async (response) => {
        const body = await response.json().catch(() => null);
        if (!response.ok || !isPage<BdmManagerRow>(body)) throw new Error("not a page");
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, [offset]);

  useEffect(load, [load]);

  function start(id: string) {
    setOpen(id);
    setPicked(null);
    setError(null);
    focus(`manager-group-${id}`); // QA25-02: the Deactivate button unmounts; the group takes focus so Escape works
  }

  function close(id: string) {
    setOpen(null);
    setError(null);
    focus(`manager-deactivate-${id}`);
  }

  async function deactivate(manager: BdmManagerRow) {
    setBusy(true);
    setError(null);
    const outcome = await sendJson(managerDeactivateUrl(manager.id), "POST", picked ? { reassign_to: picked.id } : {});
    setBusy(false);
    if (!outcome.ok) {
      // QA25-03: a 5xx in plain words; a 4xx keeps the server's own sentence.
      setError((outcome.status ?? 0) >= 500 ? `We couldn't deactivate ${manager.full_name}. Please try again.` : outcome.message);
      focus(`manager-error-${manager.id}`);
      return;
    }
    const moved = Number(outcome.data.moved_bdms ?? 0);
    setOpen(null);
    load();
    onChanged(`Deactivated ${manager.full_name}.${moved ? ` ${bdmCountText(moved)} now ${moved === 1 ? "reports" : "report"} to ${picked?.label}.` : ""}`);
  }

  return (
    <div className="action-card wide bdm-managers">
      <h3>BDM managers</h3>
      <p className="muted" style={{ marginTop: 0 }}>A manager who still has BDMs is deactivated together with the manager who takes them over.</p>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load the BDM managers list.</p>
          <button type="button" className="btn secondary small" onClick={load}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading BDM managers…</p>
      ) : data.total === 0 ? (
        <p className="empty" role="status">No active BDM managers.</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="BDM managers" tabIndex={0}>
            <table>
              <thead>
                <tr><th scope="col">Manager</th><th scope="col">BDMs</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {data.items.map((m) => (
                  <tr key={m.id}>
                    <td data-label="Name">{m.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{m.email}</span></td>
                    <td data-label="BDMs">{bdmCountText(m.bdm_count ?? 0)}</td>
                    <td data-label="Actions">
                      {open !== m.id ? (
                        <button id={`manager-deactivate-${m.id}`} type="button" className="btn secondary small" aria-label={`Deactivate ${m.full_name}`} onClick={() => start(m.id)} disabled={busy}>Deactivate</button>
                      ) : (
                        <div id={`manager-group-${m.id}`} tabIndex={-1} role="group" aria-label={`Deactivate ${m.full_name}`} className="form" onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") close(m.id); }}>
                          {m.bdm_count > 0 ? (
                            <>
                              <p style={{ margin: 0 }}>Move their {bdmCountText(m.bdm_count)} to another manager first. Pending travel approvals move with them.</p>
                              <SearchableSelect id={`manager-replacement-${m.id}`} label="Replacement manager" noun="manager" required disabled={busy}
                                search={(q, signal) => managerSearch(q, signal, m.id)} onChange={setPicked} />
                            </>
                          ) : (
                            <p style={{ margin: 0 }}>They have no BDMs; they can no longer sign in.</p>
                          )}
                          <div className="actions">
                            <button type="button" className="btn small" disabled={busy || (m.bdm_count > 0 && !picked)} onClick={() => void deactivate(m)}>
                              {busy ? "Deactivating…" : "Confirm deactivate"}
                            </button>
                            <button type="button" className="btn secondary small" onClick={() => close(m.id)} disabled={busy}>Keep active</button>
                          </div>
                          {error && <p id={`manager-error-${m.id}`} tabIndex={-1} className="form-error" role="alert">{error}</p>}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="BDM manager pages" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
              <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
