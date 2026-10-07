"use client";
import { type KeyboardEvent, useCallback, useEffect, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendJson, type Page } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { MANAGERS_URL, PAGE_SIZE, type TelecallerManagerRow, managerDeactivateUrl, managerSearch, plural } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

const telecallers = (n: number) => plural(n, "telecaller");

// tel-025 (DEC-SCOPE-104 D4): the Super Admin's telecaller managers -- the AdminBdmManagersCard pattern. A manager who still has
// telecallers is deactivated only together with a replacement manager, who takes every one of them in one step. The server re-checks it all.
export default function AdminTelecallerManagersCard({ onChanged }: { onChanged: (notice: string) => void }) {
  const [data, setData] = useState<Page<TelecallerManagerRow> | null>(null);
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
        if (!response.ok || !isPage<TelecallerManagerRow>(body)) throw new Error("not a page");
        setData(body);
      })
      .catch(() => setLoadFailed(true));
  }, [offset]);

  useEffect(load, [load]);

  function start(id: string) {
    setOpen(id);
    setPicked(null);
    setError(null);
    focus(`tl-manager-group-${id}`); // the Deactivate button unmounts; the group takes focus so Escape works
  }

  function close(id: string) {
    setOpen(null);
    setError(null);
    focus(`tl-manager-deactivate-${id}`);
  }

  async function deactivate(manager: TelecallerManagerRow) {
    setBusy(true);
    setError(null);
    const outcome = await sendJson(managerDeactivateUrl(manager.id), "POST", picked ? { reassign_to: picked.id } : {});
    setBusy(false);
    if (!outcome.ok) {
      setError((outcome.status ?? 0) >= 500 ? `We couldn't deactivate ${manager.full_name}. Please try again.` : outcome.message);
      focus(`tl-manager-error-${manager.id}`);
      return;
    }
    const moved = Number(outcome.data.moved_telecallers ?? 0);
    setOpen(null);
    load();
    onChanged(`Deactivated ${manager.full_name}.${moved ? ` ${telecallers(moved)} now ${moved === 1 ? "reports" : "report"} to ${picked?.label}.` : ""}`);
  }

  return (
    <div className="action-card wide telecaller-list">
      <h3>Telecaller managers</h3>
      <p className="muted" style={{ marginTop: 0 }}>A manager who still has telecallers is deactivated together with the manager who takes them over.</p>
      {loadFailed ? (
        <>
          <p className="form-error" role="alert">Unable to load the telecaller managers list.</p>
          <button type="button" className="btn secondary small" onClick={load}>Retry</button>
        </>
      ) : data === null ? (
        <p className="muted" role="status">Loading telecaller managers…</p>
      ) : data.total === 0 ? (
        <p className="empty" role="status">No active telecaller managers.</p>
      ) : (
        <>
          <div className="table-wrap" role="region" aria-label="Telecaller managers" tabIndex={0}>
            <table>
              <thead>
                <tr><th scope="col">Manager</th><th scope="col">Telecallers</th><th scope="col"><span className="visually-hidden">Actions</span></th></tr>
              </thead>
              <tbody>
                {data.items.map((m) => (
                  <tr key={m.id}>
                    <td data-label="Name">{m.full_name}<br /><span className="muted" style={{ fontSize: 12, overflowWrap: "anywhere" }}>{m.email}</span></td>
                    <td data-label="Telecallers">{telecallers(m.telecaller_count)}</td>
                    <td data-label="Actions">
                      {open !== m.id ? (
                        <button id={`tl-manager-deactivate-${m.id}`} type="button" className="btn secondary small" aria-label={`Deactivate ${m.full_name}`} onClick={() => start(m.id)} disabled={busy}>Deactivate</button>
                      ) : (
                        <div id={`tl-manager-group-${m.id}`} tabIndex={-1} role="group" aria-label={`Deactivate ${m.full_name}`} className="form" onKeyDown={(e: KeyboardEvent) => { if (e.key === "Escape") close(m.id); }}>
                          {m.telecaller_count > 0 ? (
                            <>
                              <p style={{ margin: 0 }}>Move their {telecallers(m.telecaller_count)} to another manager.</p>
                              <SearchableSelect id={`tl-manager-replacement-${m.id}`} label="Replacement manager" noun="manager" required disabled={busy}
                                search={(q, signal) => managerSearch(q, signal, m.id)} onChange={setPicked} />
                            </>
                          ) : (
                            <p style={{ margin: 0 }}>They have no telecallers; they can no longer sign in.</p>
                          )}
                          <div className="actions">
                            <button type="button" className="btn small" disabled={busy || (m.telecaller_count > 0 && !picked)} onClick={() => void deactivate(m)}>
                              {busy ? "Deactivating…" : "Confirm deactivate"}
                            </button>
                            <button type="button" className="btn secondary small" onClick={() => close(m.id)} disabled={busy}>Keep active</button>
                          </div>
                          {error && <p id={`tl-manager-error-${m.id}`} tabIndex={-1} className="form-error" role="alert">{error}</p>}
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.total > PAGE_SIZE && (
            <nav aria-label="Telecaller manager pages" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
              <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>Previous</button>
              <button type="button" className="btn secondary small" disabled={offset + data.items.length >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>Next</button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
