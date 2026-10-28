"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";

import AgentCommissionFields from "@/components/AgentCommissionFields";
import { sendJson, sendRequest, type SendOutcome } from "@/lib/apiErrors";
import { type AgentCommission, agentCommissionBody, agentCommissionDraft, agentCommissionUrl, formatAgentCommission } from "@/lib/agentCommission";

// dtu-001 (DEC-SCOPE-209): the "Agent commission" card on the partnership university page -- what EduSphere pays an agent Master.
// Editors save with PUT ({percent} or {amount, currency}, plus a note) and clear with DELETE (ruling R5). The API's detail is shown as is.
export default function AgentCommissionCard({ universityId, value, canEdit }: { universityId: string; value: AgentCommission | null; canEdit: boolean }) {
  const router = useRouter();
  const [draft, setDraft] = useState(() => agentCommissionDraft(value));
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
    const entry = agentCommissionBody(draft);
    if ("error" in entry) return setError(entry.error);
    if (!entry.body) return setError(draft.kind === "percent" ? "Enter the percentage." : "Enter the amount.");
    setError(null);
    setBusy(true);
    await finish(await sendJson(agentCommissionUrl(universityId), "PUT", entry.body));
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
            <AgentCommissionFields draft={draft} onChange={setDraft} />
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
