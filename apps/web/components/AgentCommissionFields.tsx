"use client";
import { AGENT_COMMISSION_CURRENCIES, type AgentCommissionDraft } from "@/lib/agentCommission";

// dtu-001 / ccrm-050: the agent commission inputs (percentage or fixed amount + currency, and a note), used by AgentCommissionCard on the
// university page and by the Add/Edit University form. The parent owns the draft. ccrm-051: the course form passes its own `idPrefix`, so
// an open course form never shares ids or a radio group with the card on the same page.
export default function AgentCommissionFields({ draft, onChange, idPrefix = "agent-commission" }: {
  draft: AgentCommissionDraft; onChange: (draft: AgentCommissionDraft) => void; idPrefix?: string;
}) {
  const set = (change: Partial<AgentCommissionDraft>) => onChange({ ...draft, ...change });
  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="radio" name={`${idPrefix}-kind`} checked={draft.kind === "percent"} onChange={() => set({ kind: "percent" })} /> Percentage
        </label>
        <label style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
          <input type="radio" name={`${idPrefix}-kind`} checked={draft.kind === "fixed"} onChange={() => set({ kind: "fixed" })} /> Fixed amount
        </label>
      </div>
      {draft.kind === "percent" ? (
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${idPrefix}-percent`}>Percent</label>
          <input id={`${idPrefix}-percent`} type="number" inputMode="decimal" min="0.01" max="100" step="0.01" value={draft.percent} onChange={(e) => set({ percent: e.target.value })} />
        </div>
      ) : (
        <>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${idPrefix}-amount`}>Amount</label>
            <input id={`${idPrefix}-amount`} type="number" inputMode="decimal" min="0.01" step="0.01" value={draft.amount} onChange={(e) => set({ amount: e.target.value })} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${idPrefix}-currency`}>Currency</label>
            <select id={`${idPrefix}-currency`} value={draft.currency} onChange={(e) => set({ currency: e.target.value })}>
              <option value="">Choose</option>
              {AGENT_COMMISSION_CURRENCIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </>
      )}
      <div className="field" style={{ margin: 0 }}>
        <label htmlFor={`${idPrefix}-note`}>Note</label>
        <input id={`${idPrefix}-note`} maxLength={300} value={draft.note} onChange={(e) => set({ note: e.target.value })} />
      </div>
    </>
  );
}
