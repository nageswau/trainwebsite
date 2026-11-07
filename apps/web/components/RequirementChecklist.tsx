"use client";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import LocalTime from "@/components/LocalTime";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import {
  type Checklist,
  type ChecklistItem,
  checklistUrl,
  companyRuleUrl,
  GLOBAL_RULE_URL,
  isChecklist,
  ITEM_STATUSES,
  type ItemStatus,
  NOT_REVIEWED,
  OVERRIDE_REASON_MAX,
  statusLabel,
} from "@/lib/requirementChecklist";

// pob-016 (DEC-SCOPE-419): the validation checklist on the requirement page. An answer shows at once and saves in order, one request at a time, so going down the list quickly loses
// nothing; radios stay enabled during a save so keyboard focus is not lost. Everything renders from the API's answer and its `can_*` flags; the server enforces every rule. `status` is a dependency because a status move can start sourcing.
type Props = { requirementId: string; status: string; onSaved: () => void };

const RULE_VALUE = (rule: boolean | null) => (rule === null ? "global" : rule ? "block" : "allow");

function FollowUpLine({ item }: { item: ChecklistItem }) {
  if (item.status !== "missing" || !item.follow_up) return null;
  if (item.follow_up.status !== "open") return <p className="muted" style={{ margin: 0 }}>Its follow-up is closed.</p>;
  return (
    <p className="muted" style={{ margin: 0 }}>
      Follow-up with {item.follow_up.contact ?? "the client"} due <LocalTime value={item.follow_up.due_at} time />
    </p>
  );
}

function BlockingLine({ data }: { data: Checklist }) {
  if (data.override) {
    return (
      <p style={{ margin: 0 }}>
        Overridden by {data.override.by?.full_name ?? "a Team Lead"} on <LocalTime value={data.override.at} time />: {data.override.reason}
      </p>
    );
  }
  if (!data.blocking.on) return <p className="muted" style={{ margin: 0 }}>This checklist does not block sourcing.</p>;
  if (data.summary.complete || data.sourcing_started) return null;
  return <p style={{ margin: 0 }}><span className="status error">Sourcing cannot start until this is complete.</span></p>;
}

export default function RequirementChecklist({ requirementId, status, onSaved }: Props) {
  const [data, setData] = useState<Checklist | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [chosen, setChosen] = useState<Record<string, ItemStatus>>({}); // answers still being saved, shown ahead of the server's
  const queue = useRef(Promise.resolve());
  const inFlight = useRef(0);
  const url = checklistUrl(requirementId);
  const id = `requirement-${requirementId}-checklist`;

  const load = useCallback(async () => {
    setLoadError(null);
    const outcome = await sendRequest(url, {});
    if (outcome.ok && isChecklist(outcome.data)) setData(outcome.data);
    else setLoadError(outcome.ok ? "Unable to read the checklist." : outcome.message);
  }, [url]);

  useEffect(() => {
    void load();
  }, [load, status]);

  /** Queued, one at a time, so each reply is newer than the last. `after` runs on success with the answer; `settled` always. A rule's answer is not the checklist, so those re-read it. */
  function send(target: string, method: "PUT" | "POST", body: unknown, after: (answer: Record<string, unknown>) => Promise<void> | void, settled?: (message: string | null) => void) {
    inFlight.current += 1;
    setBusy(true);
    setFailure(null);
    setNotice(null);
    queue.current = queue.current.then(async () => {
      const outcome = await sendJson(target, method, body);
      if (outcome.ok) await after(outcome.data);
      if (settled) settled(outcome.ok ? null : outcome.message);
      else if (!outcome.ok) setFailure(outcome.message);
      inFlight.current -= 1;
      if (!inFlight.current) setBusy(false);
    });
  }

  function accept(answer: Record<string, unknown>, text: string) {
    if (!isChecklist(answer)) return setFailure("Unable to read the checklist.");
    setData(answer);
    setNotice(text);
    onSaved();
  }

  function answer(item: ChecklistItem, next: ItemStatus) {
    const text = `${item.label}: ${statusLabel(next)}.${next === "missing" ? " A follow-up was added." : ""}`;
    setChosen((now) => ({ ...now, [item.key]: next }));
    send(`${url}/items/${encodeURIComponent(item.key)}`, "PUT", { status: next }, (body) => accept(body, text), (message) => {
      if (message) setFailure(`${item.label}: ${message}`);
      setChosen(({ [item.key]: mine, ...others }) => (mine === next ? others : { ...others, [item.key]: mine })); // a later choice for this item stays until its own reply
    });
  }

  function override(event: FormEvent) {
    event.preventDefault();
    const text = reason.trim();
    if (!text) {
      setFailure("Give a reason for the override.");
      document.getElementById(`${id}-reason`)?.focus();
      return;
    }
    send(`${url}/override`, "POST", { reason: text }, (body) => {
      setReason("");
      accept(body, "Checklist overridden.");
    });
  }

  function saveRule(target: string, value: boolean | null, text: string) {
    send(target, "PUT", { block_sourcing: value }, async () => {
      setNotice(text);
      await load();
      onSaved();
    });
  }

  if (!data) {
    return (
      <section className="action-card wide" aria-labelledby={id}>
        <h3 id={id}>Validation checklist</h3>
        {loadError ? (
          <>
            <p className="form-error" role="alert">{loadError}</p>
            <div><button type="button" className="btn secondary small" onClick={() => void load()}>Try again</button></div>
          </>
        ) : (
          <p role="status" className="muted" style={{ margin: 0 }}>Loading the checklist…</p>
        )}
      </section>
    );
  }

  const { summary } = data;
  const settled = summary.confirmed + summary.not_applicable;
  return (
    <section className="action-card wide" aria-labelledby={id} aria-busy={busy}>
      <h3 id={id}>Validation checklist</h3>
      <p style={{ margin: 0 }}>
        <strong>{settled} of {summary.total} settled</strong>
        {summary.missing > 0 && <span className="muted"> · {summary.missing} missing</span>}
        {summary.not_reviewed > 0 && <span className="muted"> · {summary.not_reviewed} not reviewed</span>}
      </p>
      <BlockingLine data={data} />
      {data.warning && <p style={{ margin: 0 }}><span className="status pending">{data.warning}</span></p>}
      <div role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {failure && <p className="form-error" role="alert">{failure}</p>}
      <div className="checklist-items">
        {data.items.map((item) => (
          <fieldset key={item.key} className="checklist-item">
            <legend>{item.label}</legend>
            <p className="muted" style={{ margin: 0 }}>{item.hint}</p>
            {data.can_edit ? (
              <div className="checklist-options">
                {ITEM_STATUSES.map((s) => (
                  <label key={s.key}>
                    <input type="radio" name={`${id}-${item.key}`} checked={(chosen[item.key] ?? item.status) === s.key} onChange={() => answer(item, s.key)} /> {s.label}
                  </label>
                ))}
                {!item.status && !chosen[item.key] && <span className="muted">{NOT_REVIEWED}</span>}
              </div>
            ) : (
              <p style={{ margin: 0 }}><strong>{statusLabel(item.status)}</strong></p>
            )}
            <FollowUpLine item={item} />
          </fieldset>
        ))}
      </div>
      {data.can_override && (
        <form className="form" onSubmit={override} noValidate>
          <div className="field">
            <label htmlFor={`${id}-reason`}>Reason for the override</label>
            <textarea id={`${id}-reason`} rows={2} maxLength={OVERRIDE_REASON_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <div className="actions">
            <button type="submit" className="btn secondary small" disabled={busy}>Override the checklist</button>
          </div>
        </form>
      )}
      {data.can_set_company_rule && (
        <div className="form-grid">
          <div className="field">
            <label htmlFor={`${id}-company-rule`}>Rule for this company</label>
            <select id={`${id}-company-rule`} value={RULE_VALUE(data.blocking.company_rule)} disabled={busy}
              onChange={(e) => saveRule(companyRuleUrl(data.company_id), e.target.value === "global" ? null : e.target.value === "block", "This company's rule is saved.")}>
              <option value="global">Follow the rule for every company ({data.blocking.global_rule ? "blocks" : "does not block"})</option>
              <option value="block">Block sourcing until complete</option>
              <option value="allow">Do not block sourcing</option>
            </select>
          </div>
          {data.can_set_global_rule && (
            <div className="field">
              <label htmlFor={`${id}-global-rule`}>Rule for every other company</label>
              <select id={`${id}-global-rule`} value={data.blocking.global_rule ? "block" : "allow"} disabled={busy}
                onChange={(e) => saveRule(GLOBAL_RULE_URL, e.target.value === "block", "The global rule is saved.")}>
                <option value="allow">Do not block sourcing</option>
                <option value="block">Block sourcing until complete</option>
              </select>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
