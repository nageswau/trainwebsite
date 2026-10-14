"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { CAPITAL_API, sharesBody, sharesProblem, type CapitalAccount, type CapitalPerson, type SharesForm } from "@/lib/partnerCapital";

// mgmt-015 (CP5-CP7): set the active partners' share % and committed capital from a month (a later month keeps the history; the same
// month replaces its row). A partner left blank keeps their share. Shares that don't total 100% are warned about, never blocked (AC1).
const SAVE_FAILED = "The shares could not be saved. Try again.";

export default function CapitalSharesForm({ partners, accounts, month }: { partners: CapitalPerson[]; accounts: CapitalAccount[]; month: string }) {
  const router = useRouter();
  const sending = useRef(false);
  const start = (): SharesForm => ({
    effective_from: month,
    rows: Object.fromEntries(partners.map((p) => {
      const account = accounts.find((a) => a.partner.id === p.id);
      return [p.id, { share_pct: account?.share_pct ?? "", commitment: account?.commitment ?? "" }];
    })),
  }); // prettier-ignore
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<SharesForm>(start);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const total = Object.values(values.rows).reduce((sum, r) => sum + (Number(r.share_pct) || 0), 0).toFixed(2);
  const setRow = (partnerId: string, key: "share_pct" | "commitment") => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, rows: { ...v.rows, [partnerId]: { ...v.rows[partnerId], [key]: e.target.value } } }));

  const toggle = (next: boolean) => {
    setOpen(next);
    setValues(start());
    setProblem(null);
    if (next) setNotice(null);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const wrong = sharesProblem(values);
    if (wrong) return setProblem(wrong.message);
    sending.current = true;
    setBusy(true);
    setProblem(null);
    const outcome = await sendJson(`${CAPITAL_API}/shares`, "PUT", sharesBody(values));
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setProblem(outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message);
    setOpen(false);
    setNotice("Shares saved.");
    router.refresh();
  }

  if (!open) {
    return (
      <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
        {notice && <p className="form-message" role="status" style={{ margin: 0 }}>{notice}</p>}
        <button type="button" className="btn secondary" onClick={() => toggle(true)} disabled={partners.length === 0}>Set share %</button>
      </div>
    );
  }
  return (
    <form className="action-card" onSubmit={submit} noValidate aria-label="Set share %" style={{ display: "grid", gap: 12, flexBasis: "100%" }}>
      <h3 style={{ margin: 0 }}>Set share %</h3>
      <div className="field" style={{ margin: 0, maxWidth: 240 }}>
        <label htmlFor="capital-shares-month">From the month</label>
        <input id="capital-shares-month" className="input" type="month" min="2000-01" value={values.effective_from} onChange={(e) => setValues((v) => ({ ...v, effective_from: e.target.value }))} />
      </div>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        {partners.map((p) => (
          <fieldset key={p.id} className="form-section" style={{ display: "grid", gap: 8, margin: 0 }}>
            <legend>{p.full_name}</legend>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor={`share-${p.id}`}>Share %</label>
              <input id={`share-${p.id}`} aria-label={`${p.full_name} share %`} className="input" inputMode="decimal" value={values.rows[p.id]?.share_pct ?? ""} onChange={setRow(p.id, "share_pct")} />
            </div>
            <div className="field" style={{ margin: 0 }}>
              <label htmlFor={`commitment-${p.id}`}>Committed capital (₹, optional)</label>
              <input id={`commitment-${p.id}`} aria-label={`${p.full_name} committed capital (₹)`} className="input" inputMode="decimal" value={values.rows[p.id]?.commitment ?? ""} onChange={setRow(p.id, "commitment")} />
            </div>
          </fieldset>
        ))}
      </div>
      {Number(total) !== 100 && <p className="status pending" style={{ display: "block", margin: 0, fontSize: 14, borderRadius: 10, padding: "10px 14px" }}>These shares total {total}%, not 100%.</p>}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>A partner left blank keeps their current share. Saving the same month again replaces that month&apos;s figures; a later month keeps the history.</p>
      {problem && <p className="form-error" role="alert" style={{ margin: 0 }}>{problem}</p>}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save shares"}</button>
        <button type="button" className="btn secondary" onClick={() => toggle(false)} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
