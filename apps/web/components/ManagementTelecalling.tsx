import Link from "next/link";

import { formatCalendarDate } from "@/lib/formatDate";
import {
  TELECALLING_FIGURES,
  TELECALLING_HOME,
  conversionText,
  stepShareText,
  type Telecalling,
  type TelecallingFigures,
  type TelecallingFilters,
} from "@/lib/managementTelecalling";

const count = (value: number) => value.toLocaleString("en-IN");

function FigureCells({ row }: { row: TelecallingFigures }) {
  return (
    <>
      {TELECALLING_FIGURES.map((figure) => (
        <td key={figure.key}>{count(row[figure.key] as number)}</td>
      ))}
      <td>{conversionText(row.conversion)}</td>
    </>
  );
}

function FigureHeaders({ first }: { first: string[] }) {
  return (
    <thead>
      <tr>
        {first.map((label) => (
          <th scope="col" key={label}>{label}</th>
        ))}
        {TELECALLING_FIGURES.map((figure) => (
          <th scope="col" key={figure.key}>{figure.label}</th>
        ))}
        <th scope="col">Conversion</th>
      </tr>
    </thead>
  );
}

// mgmt-019 (EVID-017 §14, spec TC1-TC16): the company-wide Telecalling dashboard for the operational tier. Server-rendered; the period is
// a GET form. The figures are the Telecaller CRM's own (tel-021 / tel-023), so every total is the sum of its rows.
export default function ManagementTelecalling({ data, error, filters }: { data: Telecalling | null; error: string; filters: TelecallingFilters }) {
  return (
    <>
      {error && <p className="form-error" role="alert">{error}</p>}
      <form method="get" action={TELECALLING_HOME} aria-label="Telecalling period" className="funnel-filters" autoComplete="off">
        <div className="field">
          <label htmlFor="telecalling-from">From</label>
          <input id="telecalling-from" name="date_from" type="date" defaultValue={filters.date_from} />
        </div>
        <div className="field">
          <label htmlFor="telecalling-to">To</label>
          <input id="telecalling-to" name="date_to" type="date" defaultValue={filters.date_to} />
        </div>
        <div className="funnel-filter-actions">
          <button className="btn" type="submit">Apply</button>
          {(filters.date_from || filters.date_to) && <Link href={TELECALLING_HOME}>This month</Link>}
        </div>
      </form>
      {data && (
        <>
          <p className="muted">
            Activity from {formatCalendarDate(data.date_from)} to {formatCalendarDate(data.date_to)} (India time), as the Telecaller CRM counts it.
            Telecaller conversion is leads converted out of leads assigned in the period.
          </p>
          <ul className="metric-grid snapshot-tiles" aria-label="Company telecalling figures">
            {TELECALLING_FIGURES.map((figure) => (
              <li key={figure.key} className="metric">
                <span>{figure.label}</span>
                <strong>{count(data.totals[figure.key] as number)}</strong>
              </li>
            ))}
            <li className="metric">
              <span>Telecaller conversion</span>
              <strong>{conversionText(data.totals.conversion)}</strong>
            </li>
          </ul>
          <section className="card" aria-labelledby="telecalling-chain">
            <h3 id="telecalling-chain">Calls → Interested → Counseling → Registration</h3>
            <p className="muted">
              Counseling is counselling appointments booked by telecallers; Registration is leads converted. Each step shows its share of the step
              before it.
            </p>
            <ol className="funnel" aria-label="Calls to registration">
              {data.chain.map((step, index) => {
                const share = index > 0 ? stepShareText(step.share, data.chain[index - 1].label) : null;
                return (
                  <li className="funnel-row" key={step.key}>
                    <span className="funnel-label">{step.label}</span>
                    <span className="funnel-count">{count(step.value)}</span>
                    {share && <span className="funnel-percent muted">{share}</span>}
                  </li>
                );
              })}
            </ol>
          </section>
          <h3 id="telecalling-teams">By team</h3>
          <div className="table-wrap" role="region" aria-labelledby="telecalling-teams" tabIndex={0} style={{ overflowX: "auto" }}>
            <table className="table" style={{ minWidth: 820 }}>
              <caption className="visually-hidden">Telecalling by team</caption>
              <FigureHeaders first={["Team", "Telecallers"]} />
              <tbody>
                {data.teams.map((team) => (
                  <tr key={team.team}>
                    <th scope="row">{team.label}</th>
                    <td>{team.telecallers}</td>
                    <FigureCells row={team} />
                  </tr>
                ))}
                <tr>
                  <th scope="row">Company</th>
                  <td>{data.telecallers.length}</td>
                  <FigureCells row={data.totals} />
                </tr>
              </tbody>
            </table>
          </div>
          <section id="telecallers" className="telecalling-people" aria-labelledby="telecallers-title">
            <h3 id="telecallers-title">By telecaller</h3>
            {data.telecallers.length === 0 ? (
              <p className="empty" role="status">There are no telecallers yet.</p>
            ) : (
              <div className="table-wrap" role="region" aria-labelledby="telecallers-title" tabIndex={0} style={{ overflowX: "auto" }}>
                <table className="table" style={{ minWidth: 880 }}>
                  <caption className="visually-hidden">Telecalling by telecaller</caption>
                  <FigureHeaders first={["Telecaller", "Team"]} />
                  <tbody>
                    {data.telecallers.map((row) => (
                      <tr key={row.user_id}>
                        <th scope="row">{row.active ? row.full_name : `${row.full_name} (inactive)`}</th>
                        <td>{row.team}</td>
                        <FigureCells row={row} />
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
