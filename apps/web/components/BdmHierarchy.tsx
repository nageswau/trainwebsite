import Link from "next/link";

import { type ChainStep, type Hierarchy, organizationPath, type Value, valueText } from "@/lib/bdmPerformance";
import { LINK_STYLE } from "@/lib/bdmOrganizations";

// bdm-024 (DEC-SCOPE-111 P10/P11): the §6 master view -- BDM type -> its BDMs -> their linked organizations, each with the type's value
// chain (V-A / V-S / V-C). A structured hierarchy, not a map: native <details> open and close by keyboard; each organization links to
// its page, whose panels show the same figures. Untracked steps say so; inactive BDMs and empty branches are said in words.
const plural = (n: number, one: string, many = `${one}s`) => `${n.toLocaleString("en-IN")} ${n === 1 ? one : many}`;

function Chain({ chain, values, label }: { chain: ChainStep[]; values: Value[]; label: string }) {
  return (
    <dl className="kpi-grid" aria-label={label}>
      {chain.map((step, i) => (
        <div className="kpi-tile" key={step.key}>
          <dt>{step.label}</dt>
          <dd className="kpi-value">{values[i] === null ? <span className="badge">Not tracked</span> : valueText(values[i] ?? 0)}</dd>
          <dd className="kpi-note muted">{step.definition}</dd>
        </div>
      ))}
    </dl>
  );
}

export default function BdmHierarchy({ data }: { data: Hierarchy }) {
  return (
    <>
      {data.types.map((t) => (
        <section className="card" key={t.type} aria-labelledby={`master-${t.type}`} style={{ marginBottom: 16 }}>
          <h3 id={`master-${t.type}`} style={{ margin: 0, fontSize: 18 }}>{t.label}</h3>
          <p className="muted" style={{ margin: "4px 0 0" }}>
            {[plural(t.bdm_count, "active BDM"), plural(t.organization_count, "linked organization"),
              ...(t.not_linked ? [`${t.not_linked.toLocaleString("en-IN")} not onboarded yet`] : [])].join(" · ")}
          </p>
          {t.chain.length > 0 && (
            <>
              <p style={{ margin: "8px 0 0" }}><strong>{t.chain.map((s) => s.label).join(" → ")}</strong></p>
              <Chain chain={t.chain} values={t.totals} label={`${t.label} value chain`} />
            </>
          )}
          {t.bdms.length === 0 ? (
            <p className="muted">{`No ${t.label}s in this team.`}</p>
          ) : (
            t.bdms.map((b) => (
              <details key={b.id} style={{ borderTop: "1px solid var(--line, #e5e7eb)", padding: "8px 0" }}>
                <summary style={{ cursor: "pointer", minHeight: 44, display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                  <strong>{b.active ? b.full_name : `${b.full_name} (inactive)`}</strong>
                  <span className="muted">
                    {[plural(b.organization_count, "linked organization"), ...(b.not_linked ? [`${b.not_linked} not onboarded yet`] : [])].join(" · ")}
                  </span>
                </summary>
                {b.organizations.length === 0 ? (
                  <p className="muted">No linked organizations yet.</p>
                ) : (
                  <div className="table-scroll">
                    <table className="table">
                      <caption className="sr-only">{`${b.full_name}'s organizations`}</caption>
                      <thead>
                        <tr>
                          <th scope="col">Organization</th>
                          {t.chain.map((s) => <th scope="col" key={s.key}>{s.label}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {b.organizations.map((o) => (
                          <tr key={o.id}>
                            <th scope="row"><Link href={organizationPath(o.id)} style={LINK_STYLE}>{o.name}</Link></th>
                            {o.counts.map((v, i) => <td key={t.chain[i]?.key ?? i}>{v === null ? <span className="badge">Not tracked</span> : valueText(v)}</td>)}
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr>
                          <th scope="row">Total</th>
                          {b.totals.map((v, i) => <td key={t.chain[i]?.key ?? i}><strong>{v === null ? "Not tracked" : valueText(v)}</strong></td>)}
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                )}
              </details>
            ))
          )}
        </section>
      ))}
    </>
  );
}
