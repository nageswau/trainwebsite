"use client";

import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import SearchableSelect from "@/components/SearchableSelect";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import type { PickOption } from "@/lib/lookups";
import { assigneeSearch, personLabel } from "@/lib/recruiterCandidates";
import {
  CATEGORIES_URL, KIND_LABEL, KINDS, ROUTING_URL, SOURCES_URL, STRATEGIES, UNASSIGNED_QUEUE_PATH,
  type Routing, type RoutingKind, type RoutingRule, type RoutingStrategy,
} from "@/lib/recruiterRouting";

type Message = { text: string; failed: boolean } | null;
type Choice = { id: string; name: string };

const failure = (status: number | undefined, message: string) => ((status ?? 0) >= 500 ? "We couldn't save. Please try again." : message);

async function choices(url: string, signal: AbortSignal): Promise<Choice[]> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`List failed (${response.status})`);
  return ((await response.json()) as { items: Choice[] }).items;
}

// hrc-024 (DEC-SCOPE-393): the placement manager's candidate routing -- the default recruiter and strategy (R4/R6), the rules in routing
// order (R1/R2) and the way to the unassigned queue (R10). The API enforces who may read and write (R11).
export default function RecruiterRoutingPanel() {
  const [routing, setRouting] = useState<Routing | null>(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback((signal?: AbortSignal) => {
    setLoadError(false);
    fetch(ROUTING_URL, { signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: Routing) => setRouting(data))
      .catch((e: Error) => { if (e.name !== "AbortError") setLoadError(true); });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    return () => controller.abort();
  }, [load]);

  if (loadError) {
    return (
      <div className="action-card" role="alert">
        <p className="form-error" style={{ margin: 0 }}>We couldn&apos;t load candidate routing.</p>
        <button type="button" className="btn secondary small" style={{ marginTop: 8 }} onClick={() => load()}>Try again</button>
      </div>
    );
  }
  if (!routing) return <p className="muted" role="status">Loading candidate routing…</p>;

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <p className="muted" style={{ margin: 0 }}>
        Candidates who apply or register on the website get a primary recruiter from these settings. Anyone no rule matches waits in
        the <Link href={UNASSIGNED_QUEUE_PATH}>unassigned queue</Link>, and placement managers are alerted.
      </p>
      <SettingsCard routing={routing} onSaved={setRouting} />
      <RulesCard rules={routing.rules} onChanged={() => load()} />
    </div>
  );
}

function SettingsCard({ routing, onSaved }: { routing: Routing; onSaved: (r: Routing) => void }) {
  const [recruiter, setRecruiter] = useState<PickOption | null>(routing.default_recruiter && { id: routing.default_recruiter.id, label: routing.default_recruiter.full_name });
  const [strategy, setStrategy] = useState<RoutingStrategy>(routing.strategy);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message>(null);
  const [pickerKey, setPickerKey] = useState(0);

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    const outcome = await sendJson(ROUTING_URL, "PUT", { default_recruiter_user_id: recruiter?.id ?? null, strategy });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: failure(outcome.status, outcome.message), failed: true });
    onSaved(outcome.data as Routing);
    setMessage({ text: "Routing settings saved.", failed: false });
  }

  const inactive = routing.default_recruiter && !routing.default_recruiter.active;
  return (
    <form className="action-card form" onSubmit={save} aria-labelledby="routing-settings-title">
      <h3 id="routing-settings-title" style={{ marginTop: 0 }}>Settings</h3>
      <div className="field">
        <SearchableSelect key={pickerKey} id="routing-default" label="Default recruiter (optional)" noun="recruiter" search={assigneeSearch("recruiter")}
          initial={recruiter} disabled={busy} onChange={setRecruiter} />
        <span className="muted" style={{ fontSize: 13 }}>When set, every website candidate goes to this recruiter and the rules below are skipped.</span>
        {recruiter && (
          <button type="button" className="btn secondary small" style={{ justifySelf: "start", marginTop: 4 }} disabled={busy}
            onClick={() => { setRecruiter(null); setPickerKey((k) => k + 1); }}>Clear default recruiter</button>
        )}
        {inactive && <p className="form-error" style={{ margin: "4px 0 0" }}>{personLabel(routing.default_recruiter)} is inactive, so the rules apply.</p>}
      </div>
      <fieldset className="field" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontWeight: 600 }}>When several recruiters share a rule</legend>
        {STRATEGIES.map((s) => (
          <label key={s.key} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
            <input type="radio" name="strategy" value={s.key} checked={strategy === s.key} disabled={busy} onChange={() => setStrategy(s.key)} style={{ marginTop: 4 }} />
            <span>{s.label}<span className="muted" style={{ display: "block", fontSize: 13 }}>{s.help}</span></span>
          </label>
        ))}
      </fieldset>
      <div>
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save settings"}</button>
      </div>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
    </form>
  );
}

function RulesCard({ rules, onChanged }: { rules: RoutingRule[]; onChanged: () => void }) {
  const [message, setMessage] = useState<Message>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  async function remove(rule: RoutingRule) {
    if (!window.confirm(`Delete the ${KIND_LABEL[rule.kind].toLowerCase()} rule “${rule.value_label}” → ${rule.recruiter.full_name}?`)) return;
    setDeleting(rule.id);
    setMessage(null);
    const outcome = await sendRequest(`${ROUTING_URL}/rules/${rule.id}`, { method: "DELETE" });
    setDeleting(null);
    if (!outcome.ok && outcome.status !== 404) return setMessage({ text: failure(outcome.status, outcome.message), failed: true });
    setMessage({ text: "Rule deleted.", failed: false });
    onChanged();
  }

  return (
    <section className="action-card" aria-labelledby="routing-rules-title">
      <h3 id="routing-rules-title" style={{ marginTop: 0 }}>Rules</h3>
      <p className="muted" style={{ marginTop: 0, fontSize: 13 }}>
        Checked in this order: candidate source, then skill category, then location. The first type that matches decides; inactive
        recruiters are skipped.
      </p>
      {rules.length === 0 ? (
        <p className="muted">No rules yet. Website candidates go to the unassigned queue until you add one.</p>
      ) : (
        <table className="table stack" aria-label="Routing rules">
          <thead><tr><th scope="col">Type</th><th scope="col">Matches</th><th scope="col">Recruiter</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.id}>
                <td data-label="Type">{KIND_LABEL[rule.kind]}</td>
                <td data-label="Matches" style={{ overflowWrap: "anywhere" }}>{rule.value_label}</td>
                <td data-label="Recruiter">{personLabel(rule.recruiter)}</td>
                <td>
                  <button type="button" className="btn secondary small" disabled={deleting !== null} onClick={() => void remove(rule)}
                    aria-label={`Delete rule ${KIND_LABEL[rule.kind]} ${rule.value_label} for ${rule.recruiter.full_name}`}>
                    {deleting === rule.id ? "Deleting…" : "Delete"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: "8px 0 0" }}>{message.text}</p>}
      <AddRule onAdded={() => { setMessage(null); onChanged(); }} />
    </section>
  );
}

function AddRule({ onAdded }: { onAdded: () => void }) {
  const [kind, setKind] = useState<RoutingKind>("source");
  const [lists, setLists] = useState<{ source: Choice[]; skill_category: Choice[] } | null>(null);
  const [listError, setListError] = useState(false);
  const [value, setValue] = useState("");
  const [recruiter, setRecruiter] = useState<PickOption | null>(null);
  const [pickerKey, setPickerKey] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<Message>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([choices(SOURCES_URL, controller.signal), choices(CATEGORIES_URL, controller.signal)])
      .then(([source, skill_category]) => setLists({ source, skill_category }))
      .catch((e: Error) => { if (e.name !== "AbortError") setListError(true); });
    return () => controller.abort();
  }, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (!recruiter) return setMessage({ text: "Choose a recruiter.", failed: true });
    setBusy(true);
    setMessage(null);
    const field = kind === "source" ? "source_id" : kind === "skill_category" ? "skill_category_id" : "location";
    const outcome = await sendJson(`${ROUTING_URL}/rules`, "POST", { kind, [field]: value || null, recruiter_user_id: recruiter.id });
    setBusy(false);
    if (!outcome.ok) return setMessage({ text: failure(outcome.status, outcome.message), failed: true });
    setValue("");
    setRecruiter(null);
    setPickerKey((k) => k + 1);
    setMessage({ text: "Rule added.", failed: false });
    onAdded();
  }

  const help = KINDS.find((k) => k.key === kind)?.help;
  return (
    <form className="form" onSubmit={add} aria-labelledby="routing-add-title" style={{ marginTop: 16, borderTop: "1px solid var(--line, #e5e7eb)", paddingTop: 12 }}>
      <h4 id="routing-add-title" style={{ margin: 0 }}>Add a rule</h4>
      <div className="field">
        <label htmlFor="routing-kind">Rule type</label>
        <select id="routing-kind" value={kind} disabled={busy} onChange={(e) => { setKind(e.target.value as RoutingKind); setValue(""); }}>
          {KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
        </select>
        <span className="muted" style={{ fontSize: 13 }}>{help}</span>
      </div>
      <div className="field">
        {kind === "location" ? (
          <>
            <label htmlFor="routing-value">Location</label>
            <input id="routing-value" value={value} maxLength={80} required disabled={busy} onChange={(e) => setValue(e.target.value)} placeholder="e.g. Pune" />
          </>
        ) : (
          <>
            <label htmlFor="routing-value">{KIND_LABEL[kind]}</label>
            <select id="routing-value" value={value} required disabled={busy || !lists} onChange={(e) => setValue(e.target.value)}>
              <option value="">{lists ? `Choose a ${KIND_LABEL[kind].toLowerCase()}` : listError ? "Couldn't load the list" : "Loading…"}</option>
              {(lists?.[kind] ?? []).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </>
        )}
      </div>
      <SearchableSelect key={pickerKey} id="routing-recruiter" label="Recruiter" noun="recruiter" required search={assigneeSearch("recruiter")} disabled={busy} onChange={setRecruiter} />
      <div>
        <button type="submit" className="btn" disabled={busy}>{busy ? "Adding…" : "Add rule"}</button>
      </div>
      {message && <p className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} style={{ margin: 0 }}>{message.text}</p>}
    </form>
  );
}
