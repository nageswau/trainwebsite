import { rupees } from "@/lib/investments";
import { budgetText, percentText, type MarketingFigures, type MarketingMonth } from "@/lib/marketing";
import { monthLabel } from "@/lib/salaries";

// mgmt-012 (EVID-017 §10, §15, spec MK1-MK11, MK14): the month's marketing figures, the Budget → Spend → Leads → Conversions → Revenue →
// ROI table per channel and the campaigns. Read-only; the budget form sits below it. Without the finance tier (super_admin) the API
// sends no money, and no money column or tile is drawn.
const count = (n: number) => n.toLocaleString("en-IN");

function Cells({ f, money }: { f: MarketingFigures; money: boolean }) {
  return (
    <>
      {money && <td>{budgetText(f.budget)}</td>}
      {money && <td>{rupees(f.spend)}</td>}
      <td>{count(f.leads)}</td>
      <td>{count(f.qualified)}</td>
      <td>{count(f.customers)}</td>
      <td>{percentText(f.conversion)}</td>
      {money && <td>{rupees(f.revenue)}</td>}
      {money && <td>{percentText(f.roi)}</td>}
    </>
  );
}

export default function MarketingDashboard({ data }: { data: MarketingMonth }) {
  const label = monthLabel(data.month);
  const money = data.money_visible;
  const t = data.totals;
  const g = data.groups;
  const tiles: [string, string][] = [
    ...(money ? ([["Marketing budget", budgetText(t.budget)], ["Marketing spend", rupees(t.spend)]] as [string, string][]) : []),
    ["Leads", count(t.leads)], ["Qualified leads", count(t.qualified)], ["Campaigns", count(data.campaigns.length)],
    ["Social media leads", count(g.social)], ["Website leads", count(g.website)], ["School leads", count(g.school)], ["College leads", count(g.college)],
    ["Agent leads", count(g.agent)], ["Influencer leads", g.influencer === null ? "Not tracked" : count(g.influencer)], ["Events leads", count(g.events)],
    ["Conversion", percentText(t.conversion)],
    ...(money ? ([["Revenue", rupees(t.revenue)], ["ROI", percentText(t.roi)]] as [string, string][]) : []),
  ];
  const headers = ["Channel", ...(money ? ["Budget", "Spent"] : []), "Leads", "Qualified", "Customers", "Conversion", ...(money ? ["Revenue", "ROI"] : [])];
  const tableTitle = money ? "Marketing ROI by channel" : "Leads by channel";
  return (
    <>
      <section className="action-card" aria-labelledby="marketing-figures" style={{ display: "grid", gap: 12 }}>
        <h3 id="marketing-figures" style={{ margin: 0 }}>Marketing · {label}</h3>
        <ul className="metric-grid snapshot-tiles money-tiles accounts-tiles" aria-label={`Marketing figures, ${label}`}>
          {tiles.map(([name, value]) => (
            <li className="metric" key={name}><span>{name}</span><strong>{value}</strong></li>
          ))}
        </ul>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Leads are enquiries created in {label} by lead source; qualified leads reached Qualified or later; customers are leads converted in{" "}
          {label}. Social media is Instagram, Facebook and WhatsApp. Influencer leads have no lead source yet, so they are not tracked.
          {money ? (
            <> Spend is approved ledger expenses tagged with the channel. Revenue is fees paid in {label} by students whose lead from that channel converted, from the day it was linked. ROI is (revenue − spend) ÷ spend.</>
          ) : (
            <> Budget, spend, revenue and ROI are shown to partners and the accountant only.</>
          )}
        </p>
      </section>

      <section className="action-card" id="marketing-leads" aria-labelledby="marketing-roi" style={{ display: "grid", gap: 12, scrollMarginTop: 84 }}>
        <h3 id="marketing-roi" style={{ margin: 0 }}>{money ? "Budget → Spend → Leads → Conversions → Revenue → ROI" : "Leads by channel"}</h3>
        <div className="table-wrap">
          <table className="table" aria-label={`${tableTitle}, ${label}`}>
            <thead>
              <tr>{headers.map((h) => <th scope="col" key={h}>{h}</th>)}</tr>
            </thead>
            <tbody>
              {data.channels.map((c) => (
                <tr key={c.channel}>
                  <th scope="row">{c.label}</th>
                  <Cells f={c} money={money} />
                </tr>
              ))}
              <tr>
                <th scope="row">Total</th>
                <Cells f={t} money={money} />
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section className="action-card" aria-labelledby="marketing-campaigns" style={{ display: "grid", gap: 12 }}>
        <h3 id="marketing-campaigns" style={{ margin: 0 }}>Campaigns · {label}</h3>
        {data.campaigns.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>No campaign ran or brought leads in {label}.</p>
        ) : (
          <div className="table-wrap">
            <table className="table" aria-label={`Campaigns, ${label}`}>
              <thead>
                <tr>{["Campaign", "Channel", "Leads", "Qualified", "Customers"].map((h) => <th scope="col" key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {data.campaigns.map((c) => (
                  <tr key={c.id}>
                    <th scope="row" style={{ overflowWrap: "anywhere" }}>{c.name}{!c.active && <span className="muted"> (inactive)</span>}</th>
                    <td>{c.label}</td>
                    <td>{count(c.leads)}</td>
                    <td>{count(c.qualified)}</td>
                    <td>{count(c.customers)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Spend is tagged per channel, not per campaign, so a campaign has no ROI of its own.</p>
      </section>
    </>
  );
}
