import Link from "next/link";

import SchoolValuesEditor from "@/components/SchoolValuesEditor";
import { formatCalendarDate } from "@/lib/formatDate";
import { formatCount } from "@/lib/managementCounseling";
import { formatInr } from "@/lib/managementLedger";
import { SCHOOLS_HOME, type SchoolCountKey, type SchoolMoneyKey, type SchoolRow, type SchoolsDashboard, type SchoolsQuery } from "@/lib/managementSchools";

const COUNTS: SchoolCountKey[] = ["students", "teachers", "parents", "career_guidance", "psychometric_tests", "academic_results"];
const MONEY: SchoolMoneyKey[] = ["revenue", "contract_value", "renewal_value"];
const COLUMN: Record<string, string> = {
  students: "Students", teachers: "Teachers", parents: "Parents", career_guidance: "Career guidance", psychometric_tests: "Psychometric tests",
  academic_results: "Academic results", profile_completion: "Profile completion", revenue: "Revenue", contract_value: "Contract value", renewal_value: "Renewal value",
}; // prettier-ignore
const percent = (value: number | null) => (value === null ? "No students" : `${value}%`);
const rupees = (value: string | null) => (value === null ? "Not entered" : formatInr(value));

function figure(key: string, value: number | string | null): string {
  if (key === "profile_completion") return percent(value as number | null);
  if (key === "revenue") return formatInr(value as string);
  return formatCount(value as number);
}

function schoolMeta(s: SchoolRow): string {
  const tier = s.tier ? `${s.tier[0].toUpperCase()}${s.tier.slice(1)}` : "No tier";
  const until = s.tier_valid_until ? `valid until ${formatCalendarDate(s.tier_valid_until)}` : "";
  return [tier, s.active ? "Active" : "Not active", until, s.renewal_due && "Renewal due"].filter(Boolean).join(" · ");
}

// mgmt-022 (EVID-017 §18, spec SD1-SD16): the period form, the §18 figures and the school-wise table with an all-school total. Server-
// rendered; a GET form, so refresh, back and shared links keep it. Only the finance tier gets money from the API: for everyone else the
// revenue tile says whose figure it is and the money columns are left out. Partners and the accountant edit a school's values in its row.
export default function ManagementSchools({ data, error, query }: { data: SchoolsDashboard | null; error: string; query: SchoolsQuery }) {
  const period = { from: data?.from ?? query.from, to: data?.to ?? query.to };
  const money = Boolean(data?.money_visible);
  const columns = [...COUNTS, "profile_completion", ...(money ? MONEY : [])];
  const cell = (key: string, s: { [k: string]: unknown }) =>
    key === "profile_completion" ? percent(s[key] as number | null) : (MONEY as string[]).includes(key) ? rupees(s[key] as string | null) : formatCount(s[key] as number);
  return (
    <div className="action-card">
      {error && <p className="form-error" role="alert">{error}</p>}
      <form key={`${period.from}-${period.to}`} method="get" action={SCHOOLS_HOME} aria-label="Choose a period" className="analytics-form" autoComplete="off">
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="schools-from">From</label>
          <input id="schools-from" className="input" type="date" name="from" defaultValue={period.from} required />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor="schools-to">To</label>
          <input id="schools-to" className="input" type="date" name="to" defaultValue={period.to} required />
        </div>
        <button className="btn" type="submit">Show</button>
        <Link className="btn secondary" href={SCHOOLS_HOME}>This month</Link>
      </form>
      {data && (
        <>
          <p className="muted">
            {formatCalendarDate(data.from)} to {formatCalendarDate(data.to)}, India time (IST). {data.schools.length} {data.schools.length === 1 ? "school" : "schools"}.
            Meetings, proposals, MoUs, schools contacted and revenue are for the period; the other figures are as of today.
          </p>
          <section>
            <h3>Schools</h3>
            <ul className="metric-grid snapshot-tiles" aria-label="School figures">
              {data.figures.map((f) => (
                <li key={f.key} className="metric">
                  <span>{f.label}</span>
                  {data.totals[f.key] === null && f.key === "revenue" ? <strong className="metric-untracked">Finance only</strong> : <strong>{figure(f.key, data.totals[f.key])}</strong>}
                  <p className="metric-note">{f.definition}</p>
                </li>
              ))}
            </ul>
          </section>
          <section id="school-money" className="schools-table">
            <h3 id="schools-heading">{money ? "School-wise revenue, contract value and renewal value" : "School-wise figures"}</h3>
            {data.schools.length === 0 ? (
              <p className="empty" role="status">No partner schools yet.</p>
            ) : (
              <div className="table-scroll" role="region" aria-labelledby="schools-heading" tabIndex={0}>
                <table className="table">
                  <caption className="visually-hidden">School-wise figures</caption>
                  <thead>
                    <tr>
                      <th scope="col">School</th>
                      {columns.map((key) => <th key={key} scope="col">{COLUMN[key]}</th>)}
                      {money && <th scope="col">Values</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {data.schools.map((s) => (
                      <tr key={s.id}>
                        <th scope="row" className="schools-name">
                          {s.name}
                          <span className="muted schools-meta">{schoolMeta(s)}</span>
                        </th>
                        {columns.map((key) => <td key={key}>{cell(key, s)}</td>)}
                        {money && <td><SchoolValuesEditor school={s} /></td>}
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    {money && (
                      <tr>
                        <th scope="row">Not tagged to a school</th>
                        {columns.map((key) => <td key={key}>{key === "revenue" ? formatInr(data.untagged_revenue ?? "0") : ""}</td>)}
                        <td />
                      </tr>
                    )}
                    <tr>
                      <th scope="row">All schools</th>
                      {columns.map((key) => <td key={key}><strong>{cell(key, data.totals)}</strong></td>)}
                      {money && <td />}
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
            <p className="muted">
              Parents with children at two schools are in both rows and counted once in the total.{" "}
              {money &&
                `Revenue is School projects income tagged with the school in the ledger; untagged income is shown on its own line. ${
                  data.totals.contracts_not_entered ? `${data.totals.contracts_not_entered} of ${data.schools.length} schools have no contract value entered.` : ""
                }`}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
