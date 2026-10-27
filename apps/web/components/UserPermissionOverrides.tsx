"use client";
import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { NOT_COMPLETED, sendJson } from "@/lib/apiErrors";
import { roleLabel } from "@/lib/managementDiscussions";
import { useLeaveGuard } from "@/lib/useLeaveGuard";

import type { PermissionCatalogue } from "./PermissionMatrix";

type Effect = "" | "allow" | "deny";
type Override = { permission: string; effect: "allow" | "deny"; reason: string; expires_at: string | null };
type Person = { id: string; full_name: string; email: string; role: string };
// A `GET /admin/users` row, which names the person `name`.
type SearchHit = { id: string; name: string; email: string; role: string };
type Loaded = { user: Person; editable: boolean; role_permissions: string[]; overrides: Override[] };
type ReportRow = Override & { user_id: string; full_name: string; role: string };
type Draft = Record<string, { effect: Effect; reason: string; expires: string }>;

const NO_OVERRIDE: Draft[string] = { effect: "", reason: "", expires: "" };
const LOAD_FAILED = "This user's permissions could not be loaded.";
const LEAVE_PROMPT = "You have unsaved override changes. Leave without saving?";
const SUPER_ADMIN_NOTE = "A super admin always holds every permission and cannot have overrides.";
const REASON_NEEDED = "Give a reason for each override.";
const title = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;
const userHref = (id: string) => `/admin/permissions?tab=user&user=${encodeURIComponent(id)}`;
const userPath = (id: string) => `/api/v1/admin/users/${encodeURIComponent(id)}/permissions`;
// QA-04: links here would otherwise read as plain text (the global `a` style inherits colour, no underline).
const LINK = { color: "var(--blue)", fontWeight: 700 } as const;
const pad = (n: number) => String(n).padStart(2, "0");
// The expiry is picked as a day; it lasts to the end of that local day.
const toDay = (iso: string | null) => (iso ? ((d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`)(new Date(iso)) : "");
const fromDay = (day: string) => (day ? new Date(`${day}T23:59:59`).toISOString() : null);

function toDraft(overrides: Override[]): Draft {
  return Object.fromEntries(overrides.map((o) => [o.permission, { effect: o.effect, reason: o.reason, expires: toDay(o.expires_at) }]));
}

const same = (a: Draft[string] | undefined, b: Draft[string] | undefined) =>
  (a?.effect ?? "") === (b?.effect ?? "") && (!a?.effect || (a.reason === b?.reason && a.expires === b?.expires));

// nehn-007 (DEC-SCOPE-299): the "By user" tab. One row per catalogue key: where the user's access comes from (role or override) and an
// allow/deny override with a reason and an optional expiry. Save replaces the user's whole override set with one PUT (audited by the API).
export default function UserPermissionOverrides({ catalogue, userId }: { catalogue: PermissionCatalogue; userId: string | null }) {
  const keys = catalogue.resources.flatMap((r) => r.actions.map((a) => ({ key: `${r.key}.${a}`, label: `${r.label}: ${title(a)}` })));
  const labelOf = (key: string) => keys.find((k) => k.key === key)?.label ?? key;

  const [report, setReport] = useState<ReportRow[] | null>(null);
  const [reportError, setReportError] = useState(false);
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<SearchHit[] | null>(null);
  const latestSearch = useRef(0);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string; conflict?: boolean } | null>(null);

  const loadReport = useCallback(async () => {
    setReportError(false);
    try {
      const response = await fetch("/api/v1/admin/permissions/overrides", { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      setReport((await response.json()) as ReportRow[]);
    } catch {
      setReportError(true);
    }
  }, []);

  const load = useCallback(async (id: string) => {
    setLoaded(null);
    setLoadError(false);
    try {
      const response = await fetch(userPath(id), { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      const body = (await response.json()) as Loaded;
      setLoaded(body);
      setDraft(toDraft(body.overrides));
    } catch {
      setLoadError(true);
    }
  }, []);

  useEffect(() => {
    void loadReport();
  }, [loadReport]);

  useEffect(() => {
    setMessage(null);
    if (userId) void load(userId);
  }, [load, userId]);

  const saved = loaded ? toDraft(loaded.overrides) : {};
  const changes = loaded ? keys.filter(({ key }) => !same(draft[key], saved[key])).length : 0;
  useLeaveGuard(changes > 0, LEAVE_PROMPT);

  async function search(event: FormEvent) {
    event.preventDefault();
    const q = term.trim();
    if (!q) return;
    // Only the newest search may show its answer; an older one that answers late is dropped (QA-02).
    const ticket = ++latestSearch.current;
    setSearching(true);
    setSearchError(false);
    let hits: SearchHit[] | null = null;
    try {
      const response = await fetch(`/api/v1/admin/users?q=${encodeURIComponent(q)}`, { cache: "no-store" });
      if (!response.ok) throw new Error(String(response.status));
      hits = ((await response.json()) as SearchHit[]).slice(0, 20);
    } catch {
      hits = null;
    }
    if (ticket !== latestSearch.current) return;
    if (hits) setResults(hits);
    setSearchError(!hits);
    setSearching(false);
  }

  function edit(key: string, change: Partial<Draft[string]>) {
    setMessage(null);
    setDraft((current) => ({ ...current, [key]: { ...NO_OVERRIDE, ...current[key], ...change } }));
  }

  async function save() {
    if (!loaded) return;
    const chosen = keys.filter(({ key }) => draft[key]?.effect);
    if (chosen.some(({ key }) => !draft[key].reason.trim())) {
      setMessage({ ok: false, text: REASON_NEEDED });
      return;
    }
    setSaving(true);
    const overrides = chosen.map(({ key }) => ({ permission: key, effect: draft[key].effect, reason: draft[key].reason.trim(), expires_at: fromDay(draft[key].expires) }));
    const outcome = await sendJson(userPath(loaded.user.id), "PUT", { overrides });
    setSaving(false);
    if (!outcome.ok) {
      setMessage({ ok: false, text: outcome.message || NOT_COMPLETED, conflict: outcome.status === 409 });
      return;
    }
    const body = outcome.data as unknown as Loaded;
    setLoaded(body);
    setDraft(toDraft(body.overrides));
    setMessage({ ok: true, text: `Saved overrides for ${body.user.full_name}.` });
    void loadReport();
  }

  function effective(key: string): string {
    const effect = draft[key]?.effect;
    if (effect === "allow") return "Allowed by override";
    if (effect === "deny") return "Denied by override";
    return loaded?.role_permissions.includes(key) ? "Yes, from role" : "No";
  }

  const editable = loaded?.editable ?? false;
  const today = toDay(new Date().toISOString());
  return (
    <>
      <div className="card">
        <h3>Choose a user</h3>
        <form onSubmit={search} style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: 8 }}>
          <div className="field" style={{ flex: "1 1 220px", maxWidth: 360, marginBottom: 0 }}>
            <label htmlFor="override-user-search">Find a user</label>
            <input id="override-user-search" type="search" value={term} maxLength={100} placeholder="Name, email or role" onChange={(e) => setTerm(e.target.value)} />
          </div>
          <button type="submit" className="btn secondary" disabled={searching || !term.trim()}>{searching ? "Searching…" : "Search"}</button>
        </form>
        {searchError && <div className="form-error" role="alert">Users could not be searched. Try again.</div>}
        {results && (results.length === 0 ? (
          <p className="muted" role="status">No user matches.</p>
        ) : (
          <ul aria-label="Matching users" style={{ margin: "12px 0 0", paddingLeft: 18 }}>
            {results.map((person) => (
              <li key={person.id}><Link href={userHref(person.id)} style={LINK}>{person.name}</Link> <span className="muted">· {person.email} · {roleLabel(person.role)}</span></li>
            ))}
          </ul>
        ))}
      </div>

      {userId && (
        <div className="card" style={{ marginTop: 16 }}>
          {loadError ? (
            <div className="form-error" role="alert">
              {LOAD_FAILED} <button type="button" className="btn secondary small" onClick={() => void load(userId)}>Try again</button>
            </div>
          ) : !loaded ? (
            <p className="muted" role="status">Loading permissions…</p>
          ) : (
            <>
              <h3>{loaded.user.full_name}</h3>
              <p className="muted">{loaded.user.email} · {roleLabel(loaded.user.role)}. An override wins over the role; a deny removes access even when the role grants it.</p>
              {!editable && <p className="muted">{SUPER_ADMIN_NOTE}</p>}
              <div className="table-scroll" role="region" aria-label={`Permission overrides for ${loaded.user.full_name}`} tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">{`Permissions for ${loaded.user.full_name}: role grant, override and effective access`}</caption>
                  <thead>
                    <tr><th scope="col">Permission</th><th scope="col">Role grants</th><th scope="col">Override</th><th scope="col">Reason</th><th scope="col">Expires</th><th scope="col">Effective</th></tr>
                  </thead>
                  <tbody>
                    {keys.map(({ key, label }) => {
                      const row = draft[key];
                      const disabled = !editable || saving;
                      return (
                        <tr key={key}>
                          <th scope="row">{label}</th>
                          <td>{loaded.role_permissions.includes(key) ? "Yes" : "No"}</td>
                          <td>
                            <select aria-label={`${label} override`} value={row?.effect ?? ""} disabled={disabled} onChange={(e) => edit(key, { effect: e.target.value as Effect })}>
                              <option value="">None</option>
                              <option value="allow">Allow</option>
                              <option value="deny">Deny</option>
                            </select>
                          </td>
                          <td>
                            {row?.effect ? (
                              <input aria-label={`${label} reason`} value={row.reason} maxLength={500} required disabled={disabled} onChange={(e) => edit(key, { reason: e.target.value })} />
                            ) : <span className="muted">—</span>}
                          </td>
                          <td>
                            {row?.effect ? (
                              <input aria-label={`${label} expires`} type="date" min={today} value={row.expires} disabled={disabled} onChange={(e) => edit(key, { expires: e.target.value })} />
                            ) : <span className="muted">—</span>}
                          </td>
                          <td>{effective(key)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {editable && (
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, marginTop: 12 }}>
                  <button type="button" className="btn" disabled={changes === 0 || saving} onClick={save}>{saving ? "Saving…" : "Save overrides"}</button>
                  <button type="button" className="btn secondary" disabled={changes === 0 || saving} onClick={() => { setDraft(toDraft(loaded.overrides)); setMessage(null); }}>Discard</button>
                  {changes > 0 && <span className="muted">{plural(changes, "unsaved change")}</span>}
                </div>
              )}
            </>
          )}
          {message && (message.ok ? (
            <p className="form-message" role="status">{message.text}</p>
          ) : (
            <div className="form-error" role="alert">
              {message.text} {message.conflict && <button type="button" className="btn secondary small" onClick={() => { setMessage(null); void load(userId); }}>Reload</button>}
            </div>
          ))}
        </div>
      )}

      <div className="card" style={{ marginTop: 16 }}>
        <h3>Active overrides</h3>
        {reportError ? (
          <div className="form-error" role="alert">
            Active overrides could not be loaded. <button type="button" className="btn secondary small" onClick={() => void loadReport()}>Try again</button>
          </div>
        ) : !report ? (
          <p className="muted" role="status">Loading overrides…</p>
        ) : report.length === 0 ? (
          <p className="muted">No user has an override.</p>
        ) : (
          <div className="table-scroll" role="region" aria-label="Active overrides list" tabIndex={0}>
            <table className="table" aria-label="Active overrides">
              <thead>
                <tr><th scope="col">User</th><th scope="col">Role</th><th scope="col">Permission</th><th scope="col">Override</th><th scope="col">Reason</th><th scope="col">Expires</th></tr>
              </thead>
              <tbody>
                {report.map((row) => (
                  <tr key={`${row.user_id}-${row.permission}`}>
                    <td><Link href={userHref(row.user_id)} style={LINK}>{row.full_name}</Link></td>
                    <td>{roleLabel(row.role)}</td>
                    <td>{labelOf(row.permission)}</td>
                    <td>{title(row.effect)}</td>
                    <td>{row.reason}</td>
                    <td>{row.expires_at ? toDay(row.expires_at) : "Never"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
