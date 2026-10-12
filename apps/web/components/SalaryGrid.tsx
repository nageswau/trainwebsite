"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { rupees } from "@/lib/investments";
import {
  draftFrom,
  FIELD_LABEL,
  monthLabel,
  ratioText,
  rowErrors,
  SALARY_FIELDS,
  salariesUrl,
  salaryBody,
  type SalaryDraft,
  type SalaryMonth,
  type SalaryRow,
} from "@/lib/salaries";

const MONEY_FIELDS = SALARY_FIELDS.filter((f) => f !== "headcount");

// mgmt-011 (EVID-017 §9, spec SM3-SM7, SM13): the month's figures, the Employee Cost Ratio, and the grid the accountant (or a partner)
// fills per department. Saving replaces the month (a row left blank is removed); the API decides every rule and its 422s land on their
// department rows. The tiles show what is saved; the grid holds what is being typed.
export default function SalaryGrid({ data }: { data: SalaryMonth }) {
  const router = useRouter();
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, SalaryDraft>>({}); // only the rows being edited; the others show what is saved
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [result, setResult] = useState<{ text: string; failed: boolean } | null>(null);
  const label = monthLabel(data.month);
  const t = data.totals;

  function change(row: SalaryRow, field: keyof SalaryDraft, value: string) {
    const id = row.department.id;
    setDrafts((current) => ({ ...current, [id]: { ...(current[id] ?? draftFrom(row)), [field]: value } }));
    setResult(null);
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (saving.current) return; // one save per double click
    saving.current = true;
    setBusy(true);
    setResult(null);
    const body = salaryBody(data.rows.map((r) => ({ department_id: r.department.id, draft: drafts[r.department.id] ?? draftFrom(r) })));
    const outcome = await sendJson(salariesUrl(data.month), "PUT", body);
    saving.current = false;
    setBusy(false);
    if (outcome.ok) {
      setErrors({});
      setResult({ text: `Salaries for ${label} saved.`, failed: false });
      router.refresh();
      return;
    }
    const placed = rowErrors(outcome.detail, body.rows.map((r) => r.department_id));
    setErrors(placed);
    setResult({ text: Object.keys(placed).length ? "Check the highlighted departments and save again." : outcome.message, failed: true });
  }

  const paidAbovePayable = (d: SalaryDraft) => d.paid.trim() !== "" && d.payable.trim() !== "" && Number(d.paid) > Number(d.payable);

  return (
    <>
      <ul className="metric-grid snapshot-tiles money-tiles" aria-label={`Salary figures for ${label}`}>
        <li className="metric"><span>Total employees</span><strong>{(t.headcount ?? 0).toLocaleString("en-IN")}</strong></li>
        {MONEY_FIELDS.map((f) => (
          <li className="metric" key={f}><span>{FIELD_LABEL[f]}</span><strong>{rupees(t[f])}</strong></li>
        ))}
      </ul>

      <section className="action-card" id="employee-cost" aria-labelledby="employee-cost-title" style={{ display: "grid", gap: 12 }}>
        <h3 id="employee-cost-title" style={{ margin: 0 }}>Employee cost ratio</h3>
        <ul className="metric-grid snapshot-tiles money-tiles" aria-label="Employee cost against revenue">
          <li className="metric"><span>Total monthly employee cost</span><strong>{rupees(t.total_cost)}</strong></li>
          <li className="metric"><span>Revenue</span><strong>{rupees(data.revenue)}</strong></li>
          <li className="metric"><span>Employee Cost Ratio</span><strong>{ratioText(data.ratio)}</strong></li>
        </ul>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Employee cost = salary paid + incentives + commissions + employer cost. Ratio = employee cost ÷ revenue × 100, where revenue is the
          month&apos;s counted ledger income (approved entries and automatic lines in rupees). No revenue shows “—”.
        </p>
      </section>

      <form className="action-card" style={{ display: "grid", gap: 12 }} noValidate aria-label={`Salaries for ${label}`} onSubmit={(e) => void save(e)}>
        <h3 style={{ margin: 0 }}>Department totals · {label}</h3>
        {data.rows.length === 0 ? (
          <p className="muted" role="status" style={{ margin: 0 }}>No departments yet. Add one under Departments to start recording salaries.</p>
        ) : (
          <div className="table-wrap">
            <table className="table" aria-label="Salaries by department">
              <thead>
                <tr>
                  <th scope="col">Department</th>
                  {SALARY_FIELDS.map((f) => <th scope="col" key={f}>{FIELD_LABEL[f]}{f !== "headcount" && " (₹)"}</th>)}
                  <th scope="col">Employee cost</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r) => {
                  const id = r.department.id;
                  const draft = drafts[id] ?? draftFrom(r);
                  const error = errors[id];
                  const name = r.department.name;
                  return (
                    <tr key={id}>
                      <th scope="row" style={{ overflowWrap: "anywhere", minWidth: 140 }}>
                        {name}
                        {!r.department.active && <> <span className="badge">Inactive</span></>}
                        {paidAbovePayable(draft) && <div className="muted" style={{ fontSize: 12, fontWeight: 400 }}>Paid is more than payable</div>}
                        {error && <div className="form-error" style={{ fontSize: 12, fontWeight: 400 }} id={`salary-error-${id}`}>{error}</div>}
                      </th>
                      {SALARY_FIELDS.map((f) => (
                        <td key={f}>
                          <label htmlFor={`salary-${id}-${f}`} className="visually-hidden">{FIELD_LABEL[f]} for {name}</label>
                          <input
                            id={`salary-${id}-${f}`} className="input" inputMode={f === "headcount" ? "numeric" : "decimal"} autoComplete="off"
                            style={{ minWidth: f === "headcount" ? 72 : 110 }} value={draft[f]} onChange={(e) => change(r, f, e.target.value)}
                            aria-invalid={error ? true : undefined} aria-describedby={error ? `salary-error-${id}` : undefined}
                          />
                        </td>
                      ))}
                      <td>{rupees(r.total_cost)}</td>
                    </tr>
                  );
                })}
                <tr>
                  <th scope="row">Total (saved)</th>
                  <td>{(t.headcount ?? 0).toLocaleString("en-IN")}</td>
                  {MONEY_FIELDS.map((f) => <td key={f}>{rupees(t[f])}</td>)}
                  <td><strong>{rupees(t.total_cost)}</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        )}
        {result && <p className={result.failed ? "form-error" : "form-message"} role={result.failed ? "alert" : "status"}>{result.text}</p>}
        {data.rows.length > 0 && (
          <div className="actions" style={{ justifyContent: "space-between", flexWrap: "wrap", gap: 8 }}>
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>
              A department left blank is not recorded for the month. Saved salary cost is posted to the ledger as an automatic “Salaries” expense.
              {data.updated_by && data.updated_at && <> Last saved by {data.updated_by.full_name}.</>}
            </p>
            <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : `Save ${label}`}</button>
          </div>
        )}
      </form>
    </>
  );
}
