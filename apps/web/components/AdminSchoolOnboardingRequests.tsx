"use client";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { isPage, type Page, sendJson, sendRequest } from "@/lib/apiErrors";
import { isOnboardingItem, type OnboardingItem, type OnboardingKind, onboardingMessage, QUEUE_PAGE, QUEUE_URL } from "@/lib/bdmOnboarding";
import { formatCalendarDate, formatSchoolDateTime } from "@/lib/formatDate";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Action = { id: string; mode: "link" | "reject" } | null;
const UNABLE = "Unable to load onboarding requests.";

// bdm-018 (spec §6): BDM requests to onboard a signed School, oldest first. "Use for new school" hands one to the create form; a School
// that already exists is linked by its School ID; a rejection needs a reason, which the BDM is told. The server re-checks every rule.
// bdm-019 (DEC-SCOPE-100 A1): `kind="agent"` is the Agents page's queue -- an agency is never created here, only linked by its code.
const TEXT = {
  school: { title: "School onboarding requests", link: "Link existing school", field: "School ID", submit: "Link school", url: "link", body: "school_code" },
  agent: { title: "Agent onboarding requests", link: "Link agent organization", field: "Agent code", submit: "Link agent", url: "link-agent", body: "agent_code" },
} as const;

export default function AdminSchoolOnboardingRequests({ kind = "school", selectedId, version, onUse, onResolved }: {
  kind?: OnboardingKind; selectedId?: string | null; version?: number; onUse?: (item: OnboardingItem) => void; onResolved?: (id: string) => void;
}) {
  const text = TEXT[kind];
  const statusId = kind === "school" ? "onboarding-queue-status" : "agent-onboarding-queue-status";
  const [items, setItems] = useState<OnboardingItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [failure, setFailure] = useState<string | null>(null);
  const [action, setAction] = useState<Action>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const focus = useFocusAfterRender();

  const load = useCallback(async (offset: number) => {
    setLoading(true);
    setFailure(null);
    const outcome = await sendRequest(`${QUEUE_URL}?status=pending&limit=${QUEUE_PAGE}&offset=${offset}${kind === "agent" ? "&kind=agent" : ""}`, { method: "GET" });
    setLoading(false);
    if (!outcome.ok || !isPage<OnboardingItem>(outcome.data)) return setFailure(UNABLE);
    const page = outcome.data as Page<OnboardingItem>;
    setItems((current) => (offset === 0 ? page.items : [...(current ?? []), ...page.items]));
    setTotal(page.total);
  }, [kind]);

  useEffect(() => {
    void load(0); // `version` bumps after a School is created from a request, so it leaves the queue
  }, [load, version]);

  function resolved(item: OnboardingItem, text: string) {
    setItems((current) => (current ?? []).filter((i) => i.id !== item.id));
    setTotal((t) => Math.max(0, t - 1));
    setAction(null);
    setNotice(text);
    onResolved?.(item.id);
    focus(statusId);
  }

  async function submit(event: FormEvent<HTMLFormElement>, item: OnboardingItem, mode: "link" | "reject") {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("value") ?? "").trim();
    setBusy(true);
    setActionError(null);
    const body = mode === "link" ? { [text.body]: value } : { reason: value };
    const outcome = await sendJson(`${QUEUE_URL}/${item.id}/${mode === "link" ? text.url : "reject"}`, "POST", body);
    setBusy(false);
    if (!outcome.ok || !isOnboardingItem(outcome.data)) return setActionError(outcome.ok ? "The outcome could not be confirmed. Reload to check." : onboardingMessage(outcome));
    const target = outcome.data.school ? { name: outcome.data.school.name, code: outcome.data.school.school_code } : outcome.data.agent_org && { name: outcome.data.agent_org.name, code: outcome.data.agent_org.prefix };
    resolved(item, mode === "link" && target
      ? `${item.organization.code} is now linked to ${target.name} (${target.code}).`
      : `Request from ${item.organization.code} rejected. The BDM has been told why.`);
  }

  const open = (id: string, mode: "link" | "reject") => {
    setAction({ id, mode });
    setActionError(null);
    setNotice(null);
  };
  const cancel = (item: OnboardingItem, mode: "link" | "reject") => {
    setAction(null);
    focus(`onboarding-${item.id}-${mode}`);
  };

  let body;
  if (items === null && failure) {
    body = (
      <div role="alert">
        <p className="form-error">{failure}</p>
        <button type="button" className="btn secondary small" onClick={() => void load(0)} disabled={loading}>{loading ? "Loading…" : "Try again"}</button>
      </div>
    );
  } else if (items === null) {
    body = <p className="muted" role="status">Loading onboarding requests…</p>;
  } else if (items.length === 0) {
    body = <p className="muted">No onboarding requests waiting.</p>;
  } else {
    body = (
      // QA18-02: a long queue scrolls in place (keyboard-reachable), so the create form beside it stays in view
      <ul className="list" aria-label="Onboarding requests" tabIndex={0}
        style={{ listStyle: "none", padding: "0 4px 0 0", display: "grid", gap: 12, maxHeight: "min(70vh, 720px)", overflowY: "auto" }}>
        {items.map((item) => {
          const o = item.organization;
          const mode = action?.id === item.id ? action.mode : null;
          return (
            <li key={item.id} style={{ borderTop: "1px solid var(--line, #ddd)", paddingTop: 12 }}>
              <strong>{o.code} · {o.name}</strong>
              <p className="muted" style={{ margin: "4px 0" }}>
                {[o.city, o.state].filter(Boolean).join(", ")} · Requested by {item.requested_by.full_name} on {formatSchoolDateTime(item.created_at, true)}
                {item.mou?.signed_on ? ` · MoU signed ${formatCalendarDate(item.mou.signed_on)}` : ""}
                {item.assigned_bdm.id !== item.requested_by.id ? ` · BDM ${item.assigned_bdm.full_name}` : ""}
              </p>
              {item.note && <p style={{ margin: "4px 0", whiteSpace: "pre-line" }}>{item.note}</p>}
              <div className="actions">
                {kind === "school" && <button type="button" className="btn small" aria-pressed={selectedId === item.id} onClick={() => onUse?.(item)} disabled={busy}>Use for new school</button>}
                <button id={`onboarding-${item.id}-link`} type="button" className="btn secondary small" onClick={() => open(item.id, "link")} disabled={busy}>{text.link}</button>
                <button id={`onboarding-${item.id}-reject`} type="button" className="btn secondary small" onClick={() => open(item.id, "reject")} disabled={busy}>Reject</button>
              </div>
              {mode && (
                <form className="form" aria-label={mode === "link" ? text.link : "Reject request"} onSubmit={(e) => void submit(e, item, mode)} aria-busy={busy}>
                  <div className="field">
                    <label htmlFor={`onboarding-${item.id}-value`}>{mode === "link" ? text.field : "Reason (sent to the BDM)"}</label>
                    {mode === "link"
                      ? <input id={`onboarding-${item.id}-value`} name="value" required maxLength={8} autoComplete="off" disabled={busy} autoFocus />
                      : <textarea id={`onboarding-${item.id}-value`} name="value" required maxLength={500} rows={2} disabled={busy} autoFocus />}
                  </div>
                  {actionError && <p className="form-error" role="alert">{actionError}</p>}
                  <div className="actions">
                    <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : mode === "link" ? text.submit : "Reject request"}</button>
                    <button type="button" className="btn secondary small" onClick={() => cancel(item, mode)} disabled={busy}>Cancel</button>
                  </div>
                </form>
              )}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section className="action-card" aria-label={text.title}>
      <h3>{text.title}</h3>
      <div id={statusId} tabIndex={-1} role="status" aria-live="polite" className={notice ? "form-message" : undefined}>{notice}</div>
      {items !== null && failure && <p className="form-error" role="alert">{failure}</p>}
      {body}
      {items !== null && items.length < total && (
        <button type="button" className="btn secondary small" onClick={() => void load(items.length)} disabled={loading}>{loading ? "Loading…" : "Show more"}</button>
      )}
    </section>
  );
}
