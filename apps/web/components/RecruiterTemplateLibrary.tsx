"use client";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, type Page } from "@/lib/apiErrors";
import {
  DEFAULT_CATEGORY, GOVERNED_BODY_LIMIT, GOVERNED_PLACEHOLDER_KEYS, GOVERNED_PLACEHOLDERS, KINDS, STATUS_LABEL, STEPS_MAX, TEMPLATE_CATEGORIES,
  TEMPLATE_CHANNELS, TEMPLATES_URL, categoryLabel, kindLabel, templateChannelLabel, templateUrl, unknownPlaceholders, type GovernedTemplate,
  type TemplateChannel, type TemplateVersion,
} from "@/lib/recruiterMessages";
import { getPage } from "@/lib/telecallerCatalogue";

const PAGE = 25;
const FILTERS = ["channel", "category", "status", "q", "mine"] as const;
const TEXT = { whiteSpace: "pre-wrap", overflowWrap: "anywhere" } as const;
const META = [["purpose", "Purpose", 200], ["department", "Department", 80], ["industry", "Industry", 80], ["role_type", "Role type", 80]] as const;

/** The JSON a create or edit form sends. Optional metadata is sent as null when cleared; only a calling script has steps. */
function formBody(form: FormData, channel: TemplateChannel, creating: boolean): Record<string, unknown> {
  const text = (name: string) => String(form.get(name) ?? "").trim();
  const body: Record<string, unknown> = { name: text("name"), body: String(form.get("body") ?? ""), category: text("category"), language: text("language") || "English" };
  for (const [key] of META) body[key] = text(key) || null;
  if (channel === "whatsapp" || channel === "email") body.kind = text("kind");
  if (channel === "email") body.subject = text("subject");
  if (channel === "call") body.steps = text("steps").split("\n").map((s) => s.trim()).filter(Boolean);
  if (creating) body.visibility = text("visibility") || "shared";
  return body;
}

/** pob-023: the template fields, shared by the create form and a row's edit form. The message is controlled so its length and unknown
 *  placeholders show as you type; the API decides (G8). */
function TemplateFields({ prefix, channel, onChannel, initial, disabled, approver }: {
  prefix: string; channel: TemplateChannel; onChannel?: (c: TemplateChannel) => void; initial?: GovernedTemplate; disabled: boolean; approver: boolean;
}) {
  const [body, setBody] = useState(initial?.body ?? "");
  const [steps, setSteps] = useState((initial?.steps ?? []).join("\n"));
  const id = (name: string) => `${prefix}-${name}`;
  const unknown = unknownPlaceholders(`${body}\n${channel === "call" ? steps : ""}`, GOVERNED_PLACEHOLDER_KEYS);
  const kinds = channel === "whatsapp" || channel === "email" ? KINDS[channel] : null;
  return (
    <div style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))" }}>
      {onChannel ? (
        <div className="field">
          <label htmlFor={id("channel")}>Channel (required)</label>
          <select id={id("channel")} value={channel} onChange={(e) => onChannel(e.target.value as TemplateChannel)} disabled={disabled}>
            {TEMPLATE_CHANNELS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
          </select>
        </div>
      ) : (
        <div className="field"><span className="muted">Channel</span> <strong>{templateChannelLabel(channel)} (cannot be changed)</strong></div>
      )}
      <div className="field">
        <label htmlFor={id("category")}>Category (required)</label>
        <select key={`cat-${channel}`} id={id("category")} name="category" defaultValue={initial?.category ?? DEFAULT_CATEGORY[channel]} disabled={disabled}>
          {TEMPLATE_CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
      </div>
      {kinds && (
        <div className="field">
          <label htmlFor={id("kind")}>Kind (required)</label>
          <select key={`kind-${channel}`} id={id("kind")} name="kind" defaultValue={initial?.kind ?? kinds[0].key} disabled={disabled}>
            {kinds.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </div>
      )}
      <div className="field"><label htmlFor={id("name")}>Template name (required)</label><input id={id("name")} name="name" defaultValue={initial?.name} required maxLength={160} disabled={disabled} /></div>
      {channel === "email" && (
        <div className="field"><label htmlFor={id("subject")}>Subject (required)</label><input id={id("subject")} name="subject" defaultValue={initial?.subject ?? ""} required maxLength={200} disabled={disabled} /></div>
      )}
      <div className="field"><label htmlFor={id("language")}>Language</label><input id={id("language")} name="language" defaultValue={initial?.language ?? "English"} maxLength={40} disabled={disabled} /></div>
      {META.map(([key, label, max]) => (
        <div className="field" key={key}><label htmlFor={id(key)}>{label}</label><input id={id(key)} name={key} defaultValue={initial?.[key] ?? ""} maxLength={max} disabled={disabled} /></div>
      ))}
      {!initial && (
        <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
          <legend>Who can use it</legend>
          <label style={{ display: "block" }}><input type="radio" name="visibility" value="shared" defaultChecked disabled={disabled} /> Shared with the team{approver ? "" : " (after the Team Lead approves it)"}</label>
          <label style={{ display: "block" }}><input type="radio" name="visibility" value="personal" disabled={disabled} /> Personal (only you)</label>
        </fieldset>
      )}
      <div className="field" style={{ gridColumn: "1 / -1" }}>
        <label htmlFor={id("body")}>{channel === "call" ? "Opening (required)" : "Message (required)"}</label>
        <textarea id={id("body")} name="body" value={body} onChange={(e) => setBody(e.target.value)} required rows={channel === "email" ? 8 : 4}
          maxLength={GOVERNED_BODY_LIMIT[channel]} aria-describedby={`${id("hint")} ${id("count")}`} disabled={disabled} />
        <p id={id("count")} className="muted" style={{ fontSize: 13, margin: 0 }}>{body.length} / {GOVERNED_BODY_LIMIT[channel]}</p>
      </div>
      {channel === "call" && (
        <div className="field" style={{ gridColumn: "1 / -1" }}>
          <label htmlFor={id("steps")}>Steps (required, one per line, up to {STEPS_MAX})</label>
          <textarea id={id("steps")} name="steps" value={steps} onChange={(e) => setSteps(e.target.value)} rows={5} required disabled={disabled} />
        </div>
      )}
      <details id={id("hint")} style={{ gridColumn: "1 / -1", fontSize: 13 }}>
        <summary style={{ cursor: "pointer" }}>Placeholders you can use</summary>
        <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
          {GOVERNED_PLACEHOLDERS.map((p) => <li key={p.key}><code>{`{${p.key}}`}</code> — {p.label}</li>)}
        </ul>
      </details>
      {unknown.length > 0 && <p className="form-warning" role="status" style={{ gridColumn: "1 / -1", margin: 0 }}>Unknown placeholder: {unknown.join(", ")}</p>}
    </div>
  );
}

type Panel = { kind: "preview"; data: { subject: string | null; body: string; steps: string[] | null } | "loading" | "failed" }
  | { kind: "versions"; data: TemplateVersion[] | "loading" | "failed" } | null;

function TemplateRow({ row, approver, onChanged }: { row: GovernedTemplate; approver: boolean; onChanged: (notice: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panel, setPanel] = useState<Panel>(null);
  const id = useId();

  async function act(url: string, method: "POST" | "PATCH", body: unknown, notice: string) {
    setBusy(true);
    setError(null);
    const outcome = await sendJson(url, method, body);
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setEditing(false);
    setPanel(null);
    onChanged(notice);
  }

  async function open(kind: "preview" | "versions") {
    if (panel?.kind === kind) return setPanel(null);
    setPanel({ kind, data: "loading" } as Panel);
    try {
      const response = await fetch(templateUrl(row.id, kind));
      if (!response.ok) throw new Error(String(response.status));
      const json = await response.json();
      setPanel(kind === "preview" ? { kind, data: json } : { kind, data: json.items });
    } catch {
      setPanel({ kind, data: "failed" } as Panel);
    }
  }

  if (editing) {
    return (
      <tr>
        <td colSpan={6}>
          <form className="form" aria-describedby={`${id}-error`} onKeyDown={(e) => { if (e.key === "Escape") setEditing(false); }}
            onSubmit={(e) => { e.preventDefault(); void act(templateUrl(row.id), "PATCH", formBody(new FormData(e.currentTarget), row.channel, false), `Saved ${row.name}.`); }}>
            <TemplateFields prefix={`${id}-f`} channel={row.channel} initial={row} disabled={busy} approver={approver} />
            {error && <p id={`${id}-error`} className="form-error" role="alert">{error}</p>}
            <div className="actions">
              <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save (new version)"}</button>
              <button type="button" className="btn secondary small" onClick={() => setEditing(false)} disabled={busy}>Cancel</button>
            </div>
          </form>
        </td>
      </tr>
    );
  }

  const kind = row.kind && (row.channel === "whatsapp" || row.channel === "email") ? ` · ${kindLabel(row.channel, row.kind)}` : "";
  return (
    <>
      <tr>
        <td data-label="Name">
          <strong style={{ overflowWrap: "anywhere" }}>{row.name}</strong>
          {row.purpose && <div className="muted" style={{ fontSize: 13, ...TEXT }}>{row.purpose}</div>}
          <div className="muted" style={{ fontSize: 12 }}>{row.language}{row.industry ? ` · ${row.industry}` : ""}{row.role_type ? ` · ${row.role_type}` : ""}</div>
        </td>
        <td data-label="Channel">{templateChannelLabel(row.channel)}{kind}</td>
        <td data-label="Category">{categoryLabel(row.category)}</td>
        <td data-label="Status">
          <span className="badge">{STATUS_LABEL[row.status]}</span>{row.visibility === "personal" && <> <span className="badge">Personal</span></>}
        </td>
        <td data-label="Version">
          v{row.version}
          <div className="muted" style={{ fontSize: 12 }}>
            {row.updated_by ? `by ${row.updated_by.full_name}` : "seeded"}
            {row.last_used_at ? <> · used <LocalTime value={row.last_used_at} /></> : " · never used"}
          </div>
        </td>
        <td data-label="Actions">
          <div className="actions" style={{ flexWrap: "wrap" }}>
            <button type="button" className="btn secondary small" aria-expanded={panel?.kind === "preview"} onClick={() => void open("preview")} disabled={busy}>
              {panel?.kind === "preview" ? "Hide preview" : "Preview"}<span className="visually-hidden"> {row.name}</span>
            </button>
            <button type="button" className="btn secondary small" aria-expanded={panel?.kind === "versions"} onClick={() => void open("versions")} disabled={busy}>
              Versions<span className="visually-hidden"> of {row.name}</span>
            </button>
            {row.can_edit && <button type="button" className="btn secondary small" onClick={() => { setEditing(true); setError(null); }} disabled={busy}>Edit<span className="visually-hidden"> {row.name}</span></button>}
            {row.can_approve && <button type="button" className="btn small" onClick={() => void act(templateUrl(row.id, "approve"), "POST", {}, `Approved ${row.name}. The team can use it now.`)} disabled={busy}>Approve<span className="visually-hidden"> {row.name}</span></button>}
            {row.can_archive && <button type="button" className="btn secondary small" onClick={() => void act(templateUrl(row.id, "archive"), "POST", {}, `Archived ${row.name}. Messages already sent keep its name.`)} disabled={busy}>Archive<span className="visually-hidden"> {row.name}</span></button>}
            {row.can_restore && <button type="button" className="btn secondary small" onClick={() => void act(templateUrl(row.id, "restore"), "POST", {}, `Restored ${row.name} as a draft.`)} disabled={busy}>Restore<span className="visually-hidden"> {row.name}</span></button>}
          </div>
          {error && <p className="form-error" role="alert" style={{ margin: "4px 0 0" }}>{error}</p>}
        </td>
      </tr>
      {panel && (
        <tr>
          <td colSpan={6}>
            {panel.data === "loading" ? <p className="muted" role="status">Loading…</p>
              : panel.data === "failed" ? <p className="form-error" role="alert">Unable to load the {panel.kind === "preview" ? "preview" : "versions"}.</p>
              : panel.kind === "preview" && !Array.isArray(panel.data) ? (
                <div role="region" aria-label={`Preview of ${row.name}`} style={{ display: "grid", gap: 6 }}>
                  <p className="muted" style={{ fontSize: 13, margin: 0 }}>Sample values: Priya Sharma (HR Manager) at Acme Technologies, a Java Developer role in Pune, and your name.</p>
                  {panel.data.subject !== null && <p style={{ ...TEXT, margin: 0 }}><strong>Subject:</strong> {panel.data.subject}</p>}
                  <p style={{ ...TEXT, margin: 0 }}>{panel.data.body}</p>
                  {panel.data.steps && <ol style={{ margin: 0, paddingLeft: 20 }}>{panel.data.steps.map((s, i) => <li key={i} style={TEXT}>{s}</li>)}</ol>}
                </div>
              ) : Array.isArray(panel.data) && (
                <ol reversed aria-label={`Versions of ${row.name}`} style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 6 }}>
                  {panel.data.map((v) => (
                    <li key={v.version}>
                      <strong>v{v.version}</strong> <span className="muted" style={{ fontSize: 13 }}><LocalTime value={v.created_at} time /> · {v.edited_by?.full_name ?? "migrated"}</span>
                      <div style={{ ...TEXT, fontSize: 13 }}>{v.name}{v.subject ? ` — ${v.subject}` : ""}: {v.body}</div>
                    </li>
                  ))}
                </ol>
              )}
          </td>
        </tr>
      )}
    </>
  );
}

/** pob-023 (DEC-SCOPE-408, §14): the governed template library -- recruiters add and edit (shared drafts wait for the Team Lead), the
 *  placement manager approves; personal templates are the author's only. Filters live in the URL, so refresh and Back keep the view. */
export default function RecruiterTemplateLibrary({ approver }: { approver: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? ""])) as Record<(typeof FILTERS)[number], string>;
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [data, setData] = useState<Page<GovernedTemplate> | null>(null);
  const [failed, setFailed] = useState(false);
  const [version, setVersion] = useState(0);
  const [channel, setChannel] = useState<TemplateChannel>("whatsapp");
  const [formKey, setFormKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<{ text: string; error: boolean } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false);
  const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  for (const k of FILTERS) if (filters[k]) query.set(k, k === "mine" ? "true" : filters[k]);
  const listUrl = `${TEMPLATES_URL}?${query}`;

  useEffect(() => {
    const controller = new AbortController();
    setFailed(false);
    getPage<GovernedTemplate>(listUrl, controller.signal).then(setData).catch(() => controller.signal.aborted || setFailed(true));
    return () => controller.abort();
  }, [listUrl, version]);

  function go(next: Partial<Record<(typeof FILTERS)[number], string>>, nextOffset = 0) {
    const merged = new URLSearchParams();
    for (const k of FILTERS) {
      const value = k in next ? next[k] : filters[k];
      if (value) merged.set(k, value);
    }
    if (nextOffset > 0) merged.set("offset", String(nextOffset));
    router.push(merged.size ? `${pathname}?${merged}` : pathname, { scroll: false });
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const body: Record<string, unknown> = { channel, ...formBody(new FormData(event.currentTarget), channel, true) };
    const name = String(body.name);
    setBusy(true);
    const outcome = await sendJson(TEMPLATES_URL, "POST", body);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setFeedback({ text: outcome.message, error: true });
    const shared = body.visibility !== "personal";
    setFeedback({ text: shared && !approver ? `Created ${name} as a draft. The Team Lead approves it before the team can use it.` : `Created ${name}.`, error: false });
    setFormKey((k) => k + 1);
    setVersion((v) => v + 1);
  }

  const changed = (text: string) => { setNotice(text); setVersion((v) => v + 1); };
  return (
    <>
      <form className="action-card form" onSubmit={create} aria-labelledby="tpl-create-heading">
        <h3 id="tpl-create-heading">Add a template</h3>
        <TemplateFields key={`${formKey}-${channel}`} prefix="tpl-new" channel={channel} onChannel={setChannel} disabled={busy} approver={approver} />
        <div><button className="btn" disabled={busy}>{busy ? "Adding…" : "Add template"}</button></div>
        <div role="status" aria-live="polite" className={feedback ? (feedback.error ? "form-error" : "form-message") : undefined} style={{ overflowWrap: "anywhere" }}>{feedback?.text}</div>
      </form>

      <section className="action-card wide" aria-labelledby="tpl-list-heading" style={{ display: "grid", gap: 8 }}>
        <h3 id="tpl-list-heading" style={{ margin: 0 }}>Templates</h3>
        <form role="search" aria-label="Filter templates" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "end" }}
          onSubmit={(e) => { e.preventDefault(); go({ q: String(new FormData(e.currentTarget).get("q") ?? "").trim() }); }}>
          <div className="field"><label htmlFor="tpl-q">Search name or purpose</label><input id="tpl-q" name="q" type="search" defaultValue={filters.q} key={filters.q} maxLength={100} /></div>
          <div className="field">
            <label htmlFor="tpl-channel">Channel</label>
            <select id="tpl-channel" value={filters.channel} onChange={(e) => go({ channel: e.target.value })}>
              <option value="">All channels</option>{TEMPLATE_CHANNELS.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tpl-category">Category</label>
            <select id="tpl-category" value={filters.category} onChange={(e) => go({ category: e.target.value })}>
              <option value="">All categories</option>{TEMPLATE_CATEGORIES.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
            </select>
          </div>
          <div className="field">
            <label htmlFor="tpl-status">Status</label>
            <select id="tpl-status" value={filters.status} onChange={(e) => go({ status: e.target.value })}>
              <option value="">Any status</option>{Object.entries(STATUS_LABEL).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </select>
          </div>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input type="checkbox" checked={filters.mine === "true"} onChange={(e) => go({ mine: e.target.checked ? "true" : "" })} /> Only mine
          </label>
          <button className="btn secondary small">Search</button>
        </form>
        {notice && <p className="form-message" role="status" style={{ margin: 0 }}>{notice}</p>}
        {failed ? (
          <div><p className="form-error" role="alert">Unable to load the templates.</p><button type="button" className="btn secondary small" onClick={() => setVersion((v) => v + 1)}>Retry</button></div>
        ) : data === null ? (
          <p className="muted" role="status">Loading templates…</p>
        ) : data.items.length === 0 ? (
          <p className="muted">{Object.values(filters).some(Boolean) ? "No templates match these filters." : "No templates yet. Add the first one above."}</p>
        ) : (
          <div className="table-wrap" role="region" aria-label="Templates" tabIndex={0}>
            <table>
              <thead><tr><th>Name</th><th>Channel</th><th>Category</th><th>Status</th><th>Version</th><th>Actions</th></tr></thead>
              <tbody>{data.items.map((t) => <TemplateRow key={`${t.id}-${t.version}-${t.status}`} row={t} approver={approver} onChanged={changed} />)}</tbody>
            </table>
          </div>
        )}
        {data && data.total > PAGE && (
          <nav aria-label="Template pages" className="actions">
            <button type="button" className="btn secondary small" disabled={offset === 0} onClick={() => go({}, Math.max(0, offset - PAGE))}>Previous</button>
            <span className="muted">{offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}</span>
            <button type="button" className="btn secondary small" disabled={offset + PAGE >= data.total} onClick={() => go({}, offset + PAGE)}>Next</button>
          </nav>
        )}
      </section>
    </>
  );
}
