import Link from "next/link";

import { PLAN_STATUS_CLASS, PLAN_STATUS_LABEL, planHref, type PlanPage } from "@/lib/managementPlans";

// mgmt-026 (PN14): every month's plan, newest first, with the counts of the items the caller may see (revenue items are partners'
// only, PN7). `data` is null when the read failed.
export default function ManagementPlans({ data, error }: { data: PlanPage | null; error: string }) {
  if (error) return <p className="form-error" role="alert">{error}</p>;
  if (!data) return null;
  if (data.items.length === 0) return <p className="muted">No plans yet. Plan a month to get started.</p>;
  return (
    <div className="table-wrap" role="region" aria-labelledby="plans-title" tabIndex={0} style={{ overflowX: "auto" }}>
      <table className="table">
        <caption className="visually-hidden" id="plans-title">Monthly plans</caption>
        <thead>
          <tr><th scope="col">Month</th><th scope="col">Status</th><th scope="col">Items</th><th scope="col">KPI items</th><th scope="col">Other items done</th></tr>
        </thead>
        <tbody>
          {data.items.map((plan) => (
            <tr key={plan.id}>
              <th scope="row"><Link className="kpi-link" href={planHref(plan.month)}>{plan.label}</Link></th>
              <td><span className={PLAN_STATUS_CLASS[plan.status]}>{PLAN_STATUS_LABEL[plan.status]}</span></td>
              <td>{plan.item_count}</td>
              <td>{plan.kpi_count}</td>
              <td>{plan.done_count} of {plan.item_count - plan.kpi_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
