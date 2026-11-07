"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson, sendRequest } from "@/lib/apiErrors";
import { formatDateTimeIn } from "@/lib/formatDate";
import { type FollowUpRef, type Plan, PLAN_ITEMS_URL, REASON_LABEL } from "@/lib/recruiterPoWork";

const due = (fu: FollowUpRef) => `${REASON_LABEL[fu.reason] ?? fu.reason} · due ${formatDateTimeIn(fu.due_at, "Asia/Kolkata")}`;

// pob-009 T6: the PO's day -- what they planned (tick it done, untick, remove) and, for today, what is left to pick: due follow-ups and this
// month's target companies. Each write re-renders the page from the API.
export default function PoDailyPlan({ plan }: { plan: Plan }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function write(url: string, init: RequestInit | { json: unknown; method: "POST" | "PATCH" }) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    const outcome = "json" in init ? await sendJson(url, init.method, init.json) : await sendRequest(url, init);
    inFlight.current = false;
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    router.refresh();
  }

  const done = plan.items.filter((i) => i.done_at).length;
  return (
    <div>
      {error && <p className="form-error" role="alert">{error}</p>}
      <section aria-labelledby="plan-title">
        <h3 id="plan-title">Planned ({done} of {plan.items.length} done)</h3>
        {plan.items.length === 0 ? (
          <p className="empty">{plan.editable ? "Nothing planned yet — pick from the lists below." : "Nothing was planned for this day."}</p>
        ) : (
          <ul className="plain-list">
            {plan.items.map((item) => (
              <li key={item.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <input type="checkbox" checked={!!item.done_at} disabled={!plan.editable || busy}
                    onChange={(e) => void write(`${PLAN_ITEMS_URL}/${item.id}`, { method: "PATCH", json: { done: e.target.checked } })} />
                  <span style={item.done_at ? { textDecoration: "line-through" } : undefined}>
                    <a href={`/recruiter/companies/${item.company.id}`}>{item.company.name}</a>
                    <span className="muted"> — {item.follow_up ? due(item.follow_up) : "Target company"}</span>
                  </span>
                </label>
                {plan.editable && (
                  <button className="btn secondary small" type="button" disabled={busy} aria-label={`Remove ${item.company.name} from the plan`}
                    onClick={() => void write(`${PLAN_ITEMS_URL}/${item.id}`, { method: "DELETE" })}>Remove</button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      {plan.editable && (
        <>
          <section aria-labelledby="due-title" style={{ marginTop: 24 }}>
            <h3 id="due-title">Follow-ups due by today</h3>
            {plan.suggested_follow_ups.length === 0 ? <p className="muted">No open follow-up is due.</p> : (
              <ul className="plain-list">
                {plan.suggested_follow_ups.map(({ follow_up: fu }) => (
                  <li key={fu.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                    <span>{fu.company.name} <span className="muted">— {due(fu)}</span></span>
                    <button className="btn secondary small" type="button" disabled={busy} aria-label={`Plan follow-up with ${fu.company.name}`}
                      onClick={() => void write(PLAN_ITEMS_URL, { method: "POST", json: { follow_up_id: fu.id } })}>Add to plan</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section aria-labelledby="targets-title" style={{ marginTop: 24 }}>
            <h3 id="targets-title">This month&apos;s target companies</h3>
            {plan.suggested_companies.length === 0 ? <p className="muted">No target company left to plan.</p> : (
              <ul className="plain-list">
                {plan.suggested_companies.map((c) => (
                  <li key={c.id} style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                    <span>{c.name} <span className="muted">{c.code}{c.territory ? ` · ${c.territory}` : ""}</span></span>
                    <button className="btn secondary small" type="button" disabled={busy} aria-label={`Plan ${c.name}`}
                      onClick={() => void write(PLAN_ITEMS_URL, { method: "POST", json: { company_id: c.id } })}>Add to plan</button>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
