"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { KIND_LABEL, LEDGER_API, type LedgerCategory, type LedgerKind } from "@/lib/managementLedger";

const NAME_RULE = "Use 2-80 characters";

// mgmt-004 (ML1-ML3): the managed category list. Partners and the accountant add, rename, deactivate and reactivate; the kind and
// fixed/variable type never change, and a deactivated category keeps its entries (it is only left out of the entry form).
export default function LedgerCategories({ categories }: { categories: LedgerCategory[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const [kind, setKind] = useState<LedgerKind>("expense");
  const [nature, setNature] = useState<"fixed" | "variable">("fixed");
  const [name, setName] = useState("");
  const [renaming, setRenaming] = useState<{ id: string; name: string } | null>(null);

  async function write(url: string, method: "POST" | "PATCH", body: unknown, done: string): Promise<boolean> {
    setBusy(true);
    setResult(null);
    const outcome = await sendJson(url, method, body);
    setBusy(false);
    setResult({ text: outcome.ok ? done : outcome.message, failed: !outcome.ok });
    if (outcome.ok) router.refresh();
    return outcome.ok;
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    const text = name.trim();
    if (text.length < 2 || text.length > 80) return setResult({ text: NAME_RULE, failed: true });
    if (await write(`${LEDGER_API}/categories`, "POST", { kind, ...(kind === "expense" ? { nature } : {}), name: text }, `${text} added.`)) setName("");
  }

  async function rename() {
    if (!renaming) return;
    const text = renaming.name.trim();
    if (text.length < 2 || text.length > 80) return setResult({ text: NAME_RULE, failed: true });
    if (await write(`${LEDGER_API}/categories/${renaming.id}`, "PATCH", { name: text }, "Name saved.")) setRenaming(null);
  }

  const table = (of: LedgerKind) => {
    const rows = categories.filter((c) => c.kind === of);
    return (
      <div className="table-wrap" key={of}>
        <table className="table" aria-label={`${KIND_LABEL[of]} categories`}>
          <thead>
            <tr><th scope="col">Name</th>{of === "expense" && <th scope="col">Type</th>}<th scope="col">Status</th><th scope="col">Actions</th></tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id}>
                <td style={{ overflowWrap: "anywhere" }}>
                  {renaming?.id === c.id ? (
                    <div className="field" style={{ margin: 0 }}>
                      <label htmlFor={`rename-${c.id}`} className="visually-hidden">New name for {c.name}</label>
                      <input id={`rename-${c.id}`} maxLength={80} value={renaming.name} onChange={(e) => setRenaming({ id: c.id, name: e.target.value })} />
                    </div>
                  ) : c.name}
                </td>
                {of === "expense" && <td>{c.nature === "fixed" ? "Fixed" : "Variable"}</td>}
                <td>{c.active ? <span className="status">Active</span> : <span className="badge">Inactive</span>}</td>
                <td>
                  <div className="actions" style={{ gap: 8 }}>
                    {renaming?.id === c.id ? (
                      <>
                        <button className="btn small" type="button" disabled={busy} onClick={() => void rename()}>Save name</button>
                        <button className="btn ghost small" type="button" disabled={busy} onClick={() => setRenaming(null)}>Cancel</button>
                      </>
                    ) : (
                      <button className="btn secondary small" type="button" disabled={busy} aria-label={`Rename ${c.name}`} onClick={() => setRenaming({ id: c.id, name: c.name })}>Rename</button>
                    )}
                    <button className="btn ghost small" type="button" disabled={busy} aria-label={`${c.active ? "Deactivate" : "Reactivate"} ${c.name}`}
                      onClick={() => void write(`${LEDGER_API}/categories/${c.id}`, "PATCH", { active: !c.active }, `${c.name} ${c.active ? "deactivated" : "reactivated"}.`)}>
                      {c.active ? "Deactivate" : "Reactivate"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="action-card" style={{ display: "grid", gap: 16 }}>
      <form className="analytics-form" noValidate aria-label="Add a category" onSubmit={(e) => void add(e)}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="category-kind">Kind</label>
          <select id="category-kind" value={kind} onChange={(e) => setKind(e.target.value as LedgerKind)}>
            {(Object.keys(KIND_LABEL) as LedgerKind[]).map((k) => <option key={k} value={k}>{KIND_LABEL[k]}</option>)}
          </select>
        </div>
        {kind === "expense" && (
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor="category-nature">Type</label>
            <select id="category-nature" value={nature} onChange={(e) => setNature(e.target.value as "fixed" | "variable")}>
              <option value="fixed">Fixed</option>
              <option value="variable">Variable</option>
            </select>
          </div>
        )}
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="category-name">Name</label>
          <input id="category-name" maxLength={80} autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn" type="submit" disabled={busy}>Add category</button>
      </form>
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
      <h3 style={{ margin: 0 }}>Expense categories</h3>
      {table("expense")}
      <h3 style={{ margin: 0 }}>Income categories</h3>
      {table("income")}
    </div>
  );
}
