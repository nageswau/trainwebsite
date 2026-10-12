"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { DEPARTMENTS_API, type Department } from "@/lib/salaries";

const NAME_RULE = "Use 2-80 characters";

// mgmt-011 (SM1/SM2, Q-13 interim): the managed department list salaries are recorded against. Partners and the accountant add, rename,
// deactivate and reactivate (the LedgerCategories idiom); a deactivated department keeps its saved months and leaves new ones.
export default function Departments({ departments }: { departments: Department[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
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
    if (await write(DEPARTMENTS_API, "POST", { name: text }, `${text} added.`)) setName("");
  }

  async function rename() {
    if (!renaming) return;
    const text = renaming.name.trim();
    if (text.length < 2 || text.length > 80) return setResult({ text: NAME_RULE, failed: true });
    if (await write(`${DEPARTMENTS_API}/${renaming.id}`, "PATCH", { name: text }, "Name saved.")) setRenaming(null);
  }

  return (
    <section className="action-card" aria-labelledby="departments-title" style={{ display: "grid", gap: 16 }}>
      <h3 id="departments-title" style={{ margin: 0 }}>Departments</h3>
      <form className="analytics-form" noValidate aria-label="Add a department" onSubmit={(e) => void add(e)}>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="department-name">New department</label>
          <input id="department-name" maxLength={80} autoComplete="off" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn" type="submit" disabled={busy}>Add department</button>
      </form>
      {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
      <div className="table-wrap">
        <table className="table" aria-label="Departments">
          <thead>
            <tr><th scope="col">Name</th><th scope="col">Status</th><th scope="col">Actions</th></tr>
          </thead>
          <tbody>
            {departments.map((d) => (
              <tr key={d.id}>
                <td style={{ overflowWrap: "anywhere" }}>
                  {renaming?.id === d.id ? (
                    <div className="field" style={{ margin: 0 }}>
                      <label htmlFor={`rename-${d.id}`} className="visually-hidden">New name for {d.name}</label>
                      <input id={`rename-${d.id}`} maxLength={80} value={renaming.name} onChange={(e) => setRenaming({ id: d.id, name: e.target.value })} />
                    </div>
                  ) : d.name}
                </td>
                <td>{d.active ? <span className="status">Active</span> : <span className="badge">Inactive</span>}</td>
                <td>
                  <div className="actions" style={{ gap: 8 }}>
                    {renaming?.id === d.id ? (
                      <>
                        <button className="btn small" type="button" disabled={busy} onClick={() => void rename()}>Save name</button>
                        <button className="btn ghost small" type="button" disabled={busy} onClick={() => setRenaming(null)}>Cancel</button>
                      </>
                    ) : (
                      <button className="btn secondary small" type="button" disabled={busy} aria-label={`Rename ${d.name}`} onClick={() => setRenaming({ id: d.id, name: d.name })}>Rename</button>
                    )}
                    <button className="btn ghost small" type="button" disabled={busy} aria-label={`${d.active ? "Deactivate" : "Reactivate"} ${d.name}`}
                      onClick={() => void write(`${DEPARTMENTS_API}/${d.id}`, "PATCH", { active: !d.active }, `${d.name} ${d.active ? "deactivated" : "reactivated"}.`)}>
                      {d.active ? "Deactivate" : "Reactivate"}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
