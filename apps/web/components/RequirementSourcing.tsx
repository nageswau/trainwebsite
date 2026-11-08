"use client";
import Link from "next/link";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { formatCalendarDate } from "@/lib/formatDate";
import { activeValues, type CatalogueValue } from "@/lib/recruiterCatalogue";
import { isSavedSearch, SAVED_SEARCHES_URL, type SavedSearch } from "@/lib/recruiterCandidateSearch";
import {
  bodyOf,
  type Draft,
  draftOf,
  isSourcing,
  LABEL_MAX,
  percent,
  PROFILE_MAX,
  PROGRESS_LABELS,
  QUERY_MAX,
  searchHref,
  type Sourcing,
  sourcingUrl,
  STAGES,
  STRINGS_MAX,
  TARGET_MAX,
  TARGETS,
} from "@/lib/requirementSourcing";

// pob-017 (DEC-SCOPE-429): the requirement's sourcing plan and its source funnel. Renders from the API's answer and its `can_*` flags; the
// server enforces every rule. `version` re-reads the funnel when the requirement changes; `team` is who may own sourcing (S8).
type TeamMember = { id: string; full_name: string };
type Props = { requirementId: string; version: string; team: TeamMember[]; skills: { name: string; kind: string }[] };

const STATE_CLASS = { no_targets: "muted", met: "status", on_track: "status pending", breached: "status error" } as const;

function CopyButton({ text, label, onCopied }: { text: string; label: string; onCopied: (message: string) => void }) {
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      onCopied(`Copied “${label}”.`);
    } catch {
      onCopied("Copy failed. Select the text and copy it.");
    }
  }
  return <button type="button" className="btn secondary small" onClick={() => void copy()} aria-label={`Copy ${label}`}>Copy</button>;
}

function Progress({ data }: { data: Sourcing }) {
  const p = data.progress;
  const shortLabels = TARGETS.filter((t) => p.short.includes(t.key)).map((t) => t.label.toLowerCase());
  return (
    <div className="sourcing-progress">
      <p style={{ margin: 0 }}>
        <span className={STATE_CLASS[p.state]}>{PROGRESS_LABELS[p.state]}</span>
        {p.deadline && (
          <span className="muted"> · Deadline {formatCalendarDate(p.deadline)}{p.days_left !== null && p.days_left >= 0 && ` (${p.days_left === 0 ? "today" : `${p.days_left} days left`})`}</span>
        )}
      </p>
      {p.state === "breached" && <p style={{ margin: 0 }} role="note">The deadline has passed and these are short: {shortLabels.join(", ")}.</p>}
      <ul className="sourcing-targets">
        {TARGETS.map((t) => (
          <li key={t.key}>
            <span className="muted">{t.label}</span> <strong>{p[t.key].actual}{p[t.key].target !== null ? ` of ${p[t.key].target}` : ""}</strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** QA-01: each row header's text sits in one span, so a stacked (phone) row keeps "LinkedIn · planned" together. */
function Funnel({ data, id }: { data: Sourcing; id: string }) {
  const { rows, total } = data.funnel;
  if (rows.length === 0) return <p className="empty" role="status">No candidates on this requirement yet, and no channels planned.</p>;
  return (
    <div className="table-wrap">
      <table className="table compact stack sourcing-funnel" aria-describedby={`${id}-funnel-note`}>
        <caption className="visually-hidden">Candidates by source</caption>
        <thead>
          <tr>
            <th scope="col">Source</th>
            {STAGES.map((s) => <th key={s.key} scope="col">{s.label}</th>)}
            <th scope="col">Conversion</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source.id}>
              <th scope="row"><span>{r.source.name}{r.planned && <span className="muted"> · planned</span>}</span></th>
              {STAGES.map((s) => <td key={s.key} data-label={s.label}>{r[s.key]}</td>)}
              <td data-label="Conversion">{percent(r.conversion)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            {STAGES.map((s) => <td key={s.key} data-label={s.label}><strong>{total[s.key]}</strong></td>)}
            <td data-label="Conversion"><strong>{percent(total.conversion)}</strong></td>
          </tr>
        </tfoot>
      </table>
      <p id={`${id}-funnel-note`} className="muted" style={{ margin: 0 }}>Conversion is submitted ÷ found. A candidate stays under the source they had when first submitted.</p>
    </div>
  );
}

export default function RequirementSourcing({ requirementId, version, team, skills }: Props) {
  const [data, setData] = useState<Sourcing | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [sources, setSources] = useState<CatalogueValue[] | null>(null);
  const [searches, setSearches] = useState<SavedSearch[] | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const url = sourcingUrl(requirementId);
  const id = `requirement-${requirementId}-sourcing`;

  const load = useCallback(async () => {
    setLoadError(null);
    const outcome = await sendRequest(url, {});
    if (outcome.ok && isSourcing(outcome.data)) setData(outcome.data);
    else setLoadError(outcome.ok ? "Unable to read the sourcing plan." : outcome.message);
  }, [url]);

  useEffect(() => {
    void load();
  }, [load, version]);

  function edit() {
    if (!data) return;
    setDraft(draftOf(data));
    setFailure(null);
    setNotice(null);
    if (sources === null) activeValues("candidate-sources").then(setSources).catch(() => setSources([]));
    if (data.can_link_searches && searches === null) {
      sendRequest(SAVED_SEARCHES_URL, {}).then((o) => setSearches(o.ok && Array.isArray(o.data.items) ? (o.data.items as unknown[]).filter(isSavedSearch) : []));
    }
    requestAnimationFrame(() => document.getElementById(`${id}-profile`)?.focus());
  }

  function close(message: string | null) {
    setDraft(null);
    setNotice(message);
    requestAnimationFrame(() => document.getElementById(`${id}-edit`)?.focus());
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft || saving) return;
    const built = bodyOf(draft);
    if ("error" in built) return setFailure(built.error);
    setSaving(true);
    setFailure(null);
    const outcome = await sendJson(url, "PUT", built.body);
    setSaving(false);
    if (!outcome.ok) return setFailure(outcome.message);
    if (!isSourcing(outcome.data)) return setFailure("Unable to read the sourcing plan.");
    setData(outcome.data);
    close("Sourcing plan saved.");
  }

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((d) => (d ? { ...d, [key]: value } : d));
  const toggle = (key: "channel_ids" | "saved_search_ids", value: string, on: boolean) =>
    setDraft((d) => (d ? { ...d, [key]: on ? [...d[key], value] : d[key].filter((v) => v !== value) } : d));

  if (!data) {
    return (
      <section className="action-card wide" aria-labelledby={id}>
        <h3 id={id}>Sourcing plan</h3>
        {loadError ? (
          <>
            <p className="form-error" role="alert">{loadError}</p>
            <div><button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button></div>
          </>
        ) : (
          <p role="status" className="muted" style={{ margin: 0 }}>Loading the sourcing plan…</p>
        )}
      </section>
    );
  }

  const { plan } = data;
  const required = skills.filter((s) => s.kind === "required").map((s) => s.name);
  const preferred = skills.filter((s) => s.kind === "preferred").map((s) => s.name);
  const ownerChoices = plan.source_owner && !team.some((m) => m.id === plan.source_owner?.id) ? [...team, plan.source_owner] : team;
  const channelChoices = [...(sources ?? []).filter((s) => s.active), ...data.channels.filter((c) => !(sources ?? []).some((s) => s.id === c.id && s.active))];
  const searchChoices = [...(searches ?? []), ...data.searches.filter((s) => !(searches ?? []).some((x) => x.id === s.id))];
  const empty = !plan.updated_at;

  return (
    <section className="action-card wide sourcing-plan" aria-labelledby={id} aria-busy={saving}>
      <div className="sourcing-head">
        <h3 id={id}>Sourcing plan</h3>
        {data.can_edit && !draft && <button id={`${id}-edit`} type="button" className="btn secondary small" onClick={edit}>{empty ? "Create plan" : "Edit plan"}</button>}
      </div>
      <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <Progress data={data} />
      {draft ? (
        <form className="form" onSubmit={save} noValidate>
          <div className="field">
            <label htmlFor={`${id}-profile`}>Target profile</label>
            <textarea id={`${id}-profile`} rows={3} maxLength={PROFILE_MAX} value={draft.target_profile} onChange={(e) => set("target_profile", e.target.value)} />
          </div>
          <fieldset className="field">
            <legend>Search strings for job sites</legend>
            {draft.boolean_strings.map((s, i) => (
              <div key={i} className="sourcing-string-row">
                <div className="field">
                  <label htmlFor={`${id}-label-${i}`}>Name</label>
                  <input id={`${id}-label-${i}`} maxLength={LABEL_MAX} value={s.label}
                    onChange={(e) => set("boolean_strings", draft.boolean_strings.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                </div>
                <div className="field">
                  <label htmlFor={`${id}-query-${i}`}>Search string</label>
                  <textarea id={`${id}-query-${i}`} rows={2} maxLength={QUERY_MAX} value={s.query}
                    onChange={(e) => set("boolean_strings", draft.boolean_strings.map((x, j) => (j === i ? { ...x, query: e.target.value } : x)))} />
                </div>
                <div><button type="button" className="btn secondary small" onClick={() => set("boolean_strings", draft.boolean_strings.filter((_, j) => j !== i))}>Remove</button></div>
              </div>
            ))}
            {draft.boolean_strings.length < STRINGS_MAX && (
              <div><button type="button" className="btn secondary small" onClick={() => set("boolean_strings", [...draft.boolean_strings, { label: "", query: "" }])}>Add a search string</button></div>
            )}
          </fieldset>
          <fieldset className="field">
            <legend>Planned channels</legend>
            {sources === null ? <p className="muted" role="status" style={{ margin: 0 }}>Loading the sources…</p> : (
              <div className="checklist-options">
                {channelChoices.map((c) => (
                  <label key={c.id}><input type="checkbox" checked={draft.channel_ids.includes(c.id)} onChange={(e) => toggle("channel_ids", c.id, e.target.checked)} /> {c.name}</label>
                ))}
              </div>
            )}
          </fieldset>
          {data.can_link_searches && (
            <fieldset className="field">
              <legend>Saved searches</legend>
              {searches === null ? <p className="muted" role="status" style={{ margin: 0 }}>Loading your saved searches…</p> : searchChoices.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>No saved searches yet. Save one on <Link href="/recruiter/find-candidates">Find candidates</Link>.</p>
              ) : (
                <div className="checklist-options">
                  {searchChoices.map((s) => (
                    <label key={s.id}><input type="checkbox" checked={draft.saved_search_ids.includes(s.id)} onChange={(e) => toggle("saved_search_ids", s.id, e.target.checked)} /> {s.name}</label>
                  ))}
                </div>
              )}
            </fieldset>
          )}
          <div className="form-grid">
            {TARGETS.map((t) => (
              <div key={t.field} className="field">
                <label htmlFor={`${id}-${t.field}`}>{t.label}</label>
                <input id={`${id}-${t.field}`} type="number" inputMode="numeric" min={0} max={TARGET_MAX} step={1} value={draft[t.field]} onChange={(e) => set(t.field, e.target.value)} />
              </div>
            ))}
            <div className="field">
              <label htmlFor={`${id}-deadline`}>Deadline</label>
              <input id={`${id}-deadline`} type="date" value={draft.deadline} onChange={(e) => set("deadline", e.target.value)} />
            </div>
            <div className="field">
              <label htmlFor={`${id}-owner`}>Source owner</label>
              <select id={`${id}-owner`} value={draft.source_owner_user_id} onChange={(e) => set("source_owner_user_id", e.target.value)}>
                <option value="">No one yet</option>
                {ownerChoices.map((m) => <option key={m.id} value={m.id}>{m.full_name}</option>)}
              </select>
            </div>
          </div>
          <div className="actions">
            <button type="submit" className="btn small" disabled={saving}>{saving ? "Saving…" : "Save plan"}</button>
            <button type="button" className="btn secondary small" onClick={() => close(null)} disabled={saving}>Cancel</button>
          </div>
        </form>
      ) : (
        <>
          {empty && <p className="muted" style={{ margin: 0 }}>No plan yet.{data.can_edit ? " Create one to set targets, channels and search strings." : ""}</p>}
          <dl className="sourcing-details">
            <dt>Target profile</dt>
            <dd style={{ whiteSpace: "pre-line" }}>{plan.target_profile ?? <span className="muted">Not set</span>}</dd>
            <dt>Must-have skills</dt>
            <dd>{required.length ? required.join(", ") : <span className="muted">None on the requirement</span>}</dd>
            <dt>Alternative skills</dt>
            <dd>{preferred.length ? preferred.join(", ") : <span className="muted">None on the requirement</span>}</dd>
            <dt>Planned channels</dt>
            <dd>{data.channels.length ? data.channels.map((c) => c.name).join(", ") : <span className="muted">None</span>}</dd>
            <dt>Source owner</dt>
            <dd>{plan.source_owner?.full_name ?? <span className="muted">No one yet</span>}</dd>
          </dl>
          {(data.searches.length > 0 || data.hidden_searches > 0) && (
            <div>
              <h4 className="sourcing-subhead">Saved searches</h4>
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {data.searches.map((s) => <li key={s.id}><Link href={searchHref(s)}>{s.name}</Link> <span className="muted">by {s.owner.name}</span></li>)}
                {data.hidden_searches > 0 && <li className="muted">{data.hidden_searches} more you cannot see (private to their owner)</li>}
              </ul>
            </div>
          )}
          {plan.boolean_strings.length > 0 && (
            <div>
              <h4 className="sourcing-subhead">Search strings for job sites</h4>
              <ul className="sourcing-strings">
                {plan.boolean_strings.map((s, i) => (
                  <li key={i}>
                    <div className="sourcing-string-head"><strong>{s.label}</strong><CopyButton text={s.query} label={s.label} onCopied={setNotice} /></div>
                    <code>{s.query}</code>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {plan.updated_at && (
            <p className="muted" style={{ margin: 0 }}>Last changed by {plan.updated_by?.full_name ?? "someone"} on <LocalTime value={plan.updated_at} time /></p>
          )}
        </>
      )}
      <h4 className="sourcing-subhead">Results by source</h4>
      <Funnel data={data} id={id} />
    </section>
  );
}
