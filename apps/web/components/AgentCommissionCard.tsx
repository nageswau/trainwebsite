"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { AGENT_COMMISSION_CURRENCIES, type AgentCommission, agentCommissionUrl, formatAgentCommission } from "@/lib/agentCommission";

// dtu-001 (DEC-SCOPE-209): the "Agent commission" card on the partnership university page -- what EduSphere pays an agent Master.
// Editors save with PUT ({percent} or {amount, currency}, plus a note) and clear with DELETE (ruling R5). The API's detail is shown as is.
export default function AgentCommissionCard({ universityId, value, canEdit }: { universityId: string; value: AgentCommission | null; canEdit: boolean }) {
  const router = useRouter();
  const [kind, setKind] = useState<"percent" | "fixed">(value && !value.percent && value.amount ? "fixed" : "percent");
  const [percent, setPercent] = useState(value?.percent ?? "");
  const [amount, setAmount] = useState(value?.amount ?? "");
  const [currency, setCurrency] = useState(value?.currency ?? "");
  const [note, setNote] = useState(value?.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function finish(outcome: SendOutcome) {
    setBusy(false);
    if (outcome.ok) return router.refresh();
    setError(outcome.message);
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const rate = kind === "percent" ? percent.trim() : amount.trim();
    if (!rate) return setError(kind === "percent" ? "Enter the percentage." : "Enter the amount.");
    if (kind === "fixed" && !currency) return setError("Choose the currency.");
    const body: Record<string, string> = kind === "percent" ? { percent: rate } : { amount: rate, currency };
    if (note.trim()) body.note = note.trim();
    setError(null);
    setBusy(true);
    await finish(await sendJson(agentCommissionUrl(universityId), "PUT", body));
  }

  async function clear() {
    if (busy) return;
    if (!window.confirm("Clear the agent commission for this university?")) return;
    setError(null);
    setBusy(true);
    await finish(await sendRequest(agentCommissionUrl(universityId), { method: "DELETE" }));
  }

  return (
    <section className="action-card" aria-labelledby="uni-agent-commission">
      <h3 id="uni-agent-commission">Agent commission</h3>
      <p style={{ margin: 0, fontWeight: 700 }}>{formatAgentCommission(value)}</p>
      {value?.note && <p className="muted" style={{ marginBottom: 0 }}>{value.note}</p>}
      {canEdit && (
        <form onSubmit={save} noValidate aria-label="Agent commission" aria-busy={busy} style={{ display: "grid", gap: 10, marginTop: 12 }}>
          <fieldset disabled={busy} style={{ border: 0, padding: 0, margin: 0, display: "grid", gap: 10 }}>
            <div style={{ display: "flex", gap: 16 }}>
              <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                <input type="radio" name="agent-commission-kind" checked={kind === "percent"} onChange={() => setKind("percent")} /> Percentage
              </label>
              <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                <input type="radio" name="agent-commission-kind" checked={kind === "fixed"} onChange={() => setKind("fixed")} /> Fixed amount
              </label>
            </div>
            {kind === "percent" ? (
              <div className="field" style={{ margin: 0 }}>
                <label htmlFor="agent-commission-percent">Percent</label>
                <input id="agent-commission-percent" type="number" inputMode="decimal" min="0.01" max="100" step="0.01" value={percent} onChange={(e) => setPercent(e.target.value)} />
              </div>
            ) : (
              <>
                <div className="field" style={{ margin: 0 }}>
                  <label htmlFor="agent-commission-amount">Amount</label>
                  <input id="agent-commission-amount" type="number" inputMode="decimal" min="0.01" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
                </div>
                <div className="field" style={{ margin: 0 }}>
                  <label htmlFor="agent-commission-currency">Currency</label>
                  <select id="agent-commission-currency" value={currency} onChange={(e) => setCurrency(e.target.value)}>
                    <option value="">Choose</option>
                    {AGENT_COMMISSION_CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </div>
              </>
            )}
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor="agent-commission-note">Note</label>
              <input id="agent-commission-note" value={note} onChange={(e) => setNote(e.target.value)} />
            </div>
            {error && <p role="alert" style={{ margin: 0, color: "var(--danger, #b42318)" }}>{error}</p>}
            <div className="actions">
              <button className="btn small" type="submit">Save agent commission</button>
              {value && <button className="btn ghost small" type="button" onClick={clear}>Clear</button>}
            </div>
          </fieldset>
        </form>
      )}
    </section>
  );
}
