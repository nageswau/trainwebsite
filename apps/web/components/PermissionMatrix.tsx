"use client";
import { useCallback, useEffect, useState } from "react";

import { NOT_COMPLETED, sendJson } from "@/lib/apiErrors";
import { roleLabel } from "@/lib/managementDiscussions";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

export type PermissionCatalogue = { roles: string[]; actions: string[]; resources: { key: string; label: string; actions: string[] }[] };
type Loaded = { role: string; saved: string[]; editable: boolean };

const LOAD_FAILED = "This role's permissions could not be loaded.";
const LEAVE_PROMPT = "You have unsaved permission changes. Leave without saving?";
const SUPER_ADMIN_NOTE = "The super admin always holds every permission and cannot be changed.";
const title = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const rolePath = (role: string) => `/api/v1/admin/roles/${encodeURIComponent(role)}/permissions`;

// nehn-006 (DEC-SCOPE-295): rows = catalogue resources, columns = the nine actions, one labelled native checkbox per applicable cell
// (a "—" otherwise). Save replaces the role's set with one PUT (nehn-005 audits every changed key in it); the API stays the authority.
export default function PermissionMatrix({ catalogue }: { catalogue: PermissionCatalogue }) {
  const [role, setRole] = useState(() => catalogue.roles.find((r) => r !== "super_admin") ?? catalogue.roles[0]);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<Set<string>>(new Set());
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string; conflict?: boolean } | null>(null);

  const load = useCallback(async (target: string) => {
    setLoaded(null);
    setLoadError(false);
    try {
      const response = await fetch(rolePath(target), { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      const body = (await response.json()) as { permissions: string[]; editable: boolean };
      setLoaded({ role: target, saved: body.permissions, editable: body.editable });
      setDraft(new Set(body.permissions));
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void load(role);
  }, [load, role]);

  const changes = loaded ? [...draft].filter((k) => !loaded.saved.includes(k)).length + loaded.saved.filter((k) => !draft.has(k)).length : 0;
  useLeaveGuard(changes > 0, LEAVE_PROMPT);

  function pickRole(next: string) {
    if (changes > 0 && !window.confirm(LEAVE_PROMPT)) return;
    setMessage(null);
    setRole(next);
  }

  function toggle(key: string) {
    setMessage(null);
    setDraft((current) => {
      const next = new Set(current);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function save() {
    if (!loaded) return;
    setSaving(true);
    const outcome = await sendJson(rolePath(loaded.role), "PUT", { permissions: [...draft].sort() });
    setSaving(false);
    if (!outcome.ok) {
      setMessage({ ok: false, text: outcome.message || NOT_COMPLETED, conflict: outcome.status === 409 });
      return;
    }
    const saved = (outcome.data.permissions as string[]) ?? [...draft];
    setLoaded({ ...loaded, saved });
    setDraft(new Set(saved));
    setMessage({ ok: true, text: `Saved ${roleLabel(loaded.role)}: ${plural(changes, "change")}.` });
  }

  const editable = loaded?.editable ?? false;
  return (
    <div className="card">
      <div className="field" style={{ maxWidth: 360 }}>
        <label htmlFor="permission-role">Role</label>
        <select id="permission-role" value={role} onChange={(e) => pickRole(e.target.value)}>
          {catalogue.roles.map((r) => <option key={r} value={r}>{roleLabel(r)}</option>)}
        </select>
      </div>
      {loadError ? (
        <div className="form-error" role="alert">
          {LOAD_FAILED} <button type="button" className="btn secondary small" onClick={() => void load(role)}>Try again</button>
        </div>
      ) : !loaded ? (
        <p className="muted" role="status">Loading permissions…</p>
      ) : (
        <>
          {!editable && <p className="muted">{SUPER_ADMIN_NOTE}</p>}
          <div className="table-scroll" role="region" aria-label={`Permissions for ${roleLabel(loaded.role)}`} tabIndex={0}>
            <table className="table">
              <caption className="visually-hidden">{`Permissions for ${roleLabel(loaded.role)}: resources by action`}</caption>
              <thead>
                <tr><th scope="col">Resource</th>{catalogue.actions.map((a) => <th key={a} scope="col">{title(a)}</th>)}</tr>
              </thead>
              <tbody>
                {catalogue.resources.map((resource) => (
                  <tr key={resource.key}>
                    <th scope="row">{resource.label}</th>
                    {catalogue.actions.map((action) => {
                      const key = `${resource.key}.${action}`;
                      return (
                        <td key={action} style={{ textAlign: "center" }}>
                          {resource.actions.includes(action) ? (
                            <input type="checkbox" aria-label={`${resource.label}: ${title(action)}`} checked={draft.has(key)} disabled={!editable || saving} onChange={() => toggle(key)} />
                          ) : (
                            <><span aria-hidden="true">—</span><span className="visually-hidden">Not applicable</span></>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {editable && (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
              <button type="button" className="btn" disabled={changes === 0 || saving} onClick={save}>{saving ? "Saving…" : "Save changes"}</button>
              <button type="button" className="btn secondary" disabled={changes === 0 || saving} onClick={() => { setDraft(new Set(loaded.saved)); setMessage(null); }}>Discard</button>
              {changes > 0 && <span className="muted">{plural(changes, "unsaved change")}</span>}
            </div>
          )}
        </>
      )}
      {message && (message.ok ? (
        <p className="form-message" role="status">{message.text}</p>
      ) : (
        <div className="form-error" role="alert">
          {message.text} {message.conflict && <button type="button" className="btn secondary small" onClick={() => { setMessage(null); void load(role); }}>Reload</button>}
        </div>
      ))}
    </div>
  );
}
