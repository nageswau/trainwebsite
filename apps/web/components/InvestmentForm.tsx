"use client";
import { useRouter } from "next/navigation";
import { type FormEvent, useRef, useState } from "react";

import { isRequestBody, sendJson } from "@/lib/apiErrors";
import {
  EMPTY_INVESTMENT_FORM,
  INVESTMENT_STATUS_LABEL,
  INVESTMENT_VERTICAL_LABEL,
  investmentBody,
  investmentFormFrom,
  investmentProblem,
  investmentUrl,
  MANAGEMENT_INVESTMENTS,
  type Investment,
  type InvestmentForm as Form,
  type InvestmentPerson,
} from "@/lib/investments";

// mgmt-014 (§23, MI2-MI6, MI10): add an investment (the register) or edit one (its detail page). Closed until asked for. One request at
// a time, so a double click never records twice; a refusal keeps the entry and shows the API's reason. Adding opens the new investment;
// saving an edit re-reads the page. Partner-only: the API is the gate.
const SAVE_FAILED = "The investment could not be saved. Try again.";

export default function InvestmentForm({ investors, investment }: { investors: InvestmentPerson[]; investment?: Investment }) {
  const router = useRouter();
  const sending = useRef(false);
  const start = () => (investment ? investmentFormFrom(investment) : EMPTY_INVESTMENT_FORM);
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState<Form>(start);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<{ field?: keyof Form; message: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // A partner who has since left stays selectable on the investment that already names them (the API keeps them too).
  const choices = investment?.investor && !investors.some((p) => p.id === investment.investor?.id) ? [...investors, investment.investor] : investors;
  const id = (field: keyof Form) => `investment-${investment?.id ?? "new"}-${field}`;
  const set = (field: keyof Form) => (e: { target: { value: string } }) => setValues((v) => ({ ...v, [field]: e.target.value }));
  const invalid = (field: keyof Form) => (problem?.field === field ? { "aria-invalid": true as const, "aria-describedby": id("error" as keyof Form) } : {});

  const toggle = (next: boolean) => {
    setOpen(next);
    setValues(start());
    setProblem(null);
    if (next) setNotice(null);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (sending.current) return;
    const wrong = investmentProblem(values);
    if (wrong) {
      setProblem(wrong);
      return document.getElementById(id(wrong.field))?.focus(); // browser QA-04: straight to the field to fix
    }
    sending.current = true;
    setBusy(true);
    setProblem(null);
    const outcome = await sendJson(investmentUrl(investment?.id), investment ? "PATCH" : "POST", investmentBody(values));
    sending.current = false;
    setBusy(false);
    if (!outcome.ok) return setProblem({ message: outcome.status !== undefined && outcome.detail === undefined ? SAVE_FAILED : outcome.message });
    if (!isRequestBody(outcome.data)) return setProblem({ message: SAVE_FAILED });
    if (!investment) return router.push(`${MANAGEMENT_INVESTMENTS}/${outcome.data.id}`);
    setOpen(false);
    setNotice("Investment saved.");
    router.refresh();
  }

  const field = (key: keyof Form, label: string, control: React.ReactNode) => (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor={id(key)}>{label}</label>
      {control}
    </div>
  );
  const money = (key: "amount" | "expected_return" | "actual_return", label: string) =>
    field(key, label, <input id={id(key)} className="input" inputMode="decimal" value={values[key]} onChange={set(key)} {...invalid(key)} />);

  if (!open) {
    return (
      <div style={{ display: "grid", gap: 8, justifyItems: "start" }}>
        {notice && <p className="form-message" role="status" style={{ margin: 0 }}>{notice}</p>}
        <button type="button" className="btn" onClick={() => toggle(true)}>{investment ? "Edit investment" : "Add investment"}</button>
      </div>
    );
  }
  return (
    <form className="action-card" onSubmit={submit} noValidate aria-label={investment ? `Edit ${investment.code}` : "Add investment"} style={{ display: "grid", gap: 12 }}>
      <h3 style={{ margin: 0 }}>{investment ? `Edit ${investment.code}` : "Add investment"}</h3>
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))" }}>
        {field("invested_on", "Date", <input id={id("invested_on")} className="input" type="date" value={values.invested_on} onChange={set("invested_on")} {...invalid("invested_on")} />)}
        {field("investor_kind", "Investor", (
          <select id={id("investor_kind")} value={values.investor_kind} onChange={set("investor_kind")}>
            <option value="company">Company</option>
            <option value="partner">A partner</option>
          </select>
        ))}
        {values.investor_kind === "partner" && field("investor_user_id", "Partner", (
          <select id={id("investor_user_id")} value={values.investor_user_id} onChange={set("investor_user_id")} {...invalid("investor_user_id")}>
            <option value="">Choose a partner</option>
            {choices.map((p) => <option key={p.id} value={p.id}>{p.full_name}</option>)}
          </select>
        ))}
        {money("amount", "Amount (₹)")}
        {field("purpose", "Purpose", <input id={id("purpose")} className="input" maxLength={200} value={values.purpose} onChange={set("purpose")} {...invalid("purpose")} />)}
        {field("vertical", "Business vertical", (
          <select id={id("vertical")} value={values.vertical} onChange={set("vertical")} {...invalid("vertical")}>
            <option value="">Choose a vertical</option>
            {Object.entries(INVESTMENT_VERTICAL_LABEL).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        ))}
        {money("expected_return", "Expected return (₹)")}
        {money("actual_return", "Actual return (₹)")}
        {field("status", "Status", (
          <select id={id("status")} value={values.status} onChange={set("status")}>
            {Object.entries(INVESTMENT_STATUS_LABEL).map(([value, text]) => <option key={value} value={value}>{text}</option>)}
          </select>
        ))}
      </div>
      {field("notes", "Notes", <textarea id={id("notes")} className="input" rows={3} maxLength={2000} value={values.notes} onChange={set("notes")} />)}
      <p className="muted" style={{ margin: 0, fontSize: 13 }}>Leave the actual return blank until it is known; ROI then shows “—”.</p>
      {problem && <p id={id("error" as keyof Form)} className="form-error" role="alert" style={{ margin: 0 }}>{problem.message}</p>}
      <div className="actions">
        <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : investment ? "Save changes" : "Save investment"}</button>
        <button type="button" className="btn secondary" onClick={() => toggle(false)} disabled={busy}>Cancel</button>
      </div>
    </form>
  );
}
