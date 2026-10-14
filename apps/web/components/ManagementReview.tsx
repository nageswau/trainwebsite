import type { ReactNode } from "react";

import { formatPercent, inrOrNone, NONE, type MonthlyReview } from "@/lib/managementReviews";

// mgmt-032 (EVID-017 §32, MR5-MR12): sections 1-8 of a review, exactly as frozen in its snapshot (the PDF lays out the same figures).
// Server-rendered: no state. Sections 9 and 10 (the partners' narrative) are ManagementReviewEditor's.

const slug = (title: string) => `review-${title.replace(/\W+/g, "-").toLowerCase()}`;

export function ReviewSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="card" aria-labelledby={slug(title)} style={{ marginBottom: 18 }}>
      <h3 id={slug(title)}>{title}</h3>
      {children}
    </section>
  );
}

export function Figures({ caption, rows }: { caption: string; rows: [string, ReactNode][] }) {
  return (
    <div className="table-wrap">
      <table className="table compact figures">
        <caption className="visually-hidden">{caption}</caption>
        <tbody>
          {rows.map(([label, value], i) => (
            <tr key={`${i}-${label}`}><th scope="row" style={{ fontWeight: label.startsWith("Total") ? 700 : undefined }}>{label}</th><td style={{ textAlign: "right" }}>{value}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ManagementReview({ review }: { review: MonthlyReview }) {
  const { revenue, expenses, profitability: p, sales, partnerships: pa, people, marketing: m, investments: inv } = review.snapshot;
  return (
    <>
      <ReviewSection title="1. Revenue">
        <Figures caption="Revenue by vertical" rows={[...revenue.lines.map((l): [string, ReactNode] => [l.label, inrOrNone(l.amount)]), ["Total revenue", inrOrNone(revenue.total)]]} />
      </ReviewSection>
      <ReviewSection title="2. Expenses">
        <Figures caption="Expenses by head" rows={[...expenses.lines.map((l): [string, ReactNode] => [l.label, inrOrNone(l.amount)]), ["Total expenses", inrOrNone(expenses.total)]]} />
      </ReviewSection>
      <ReviewSection title="3. Profitability">
        <Figures caption="Profitability" rows={[["Gross revenue", inrOrNone(p.revenue)], ["Total expense", inrOrNone(p.expenses)], ["Net profit", inrOrNone(p.net_profit)], ["Profit margin", formatPercent(p.margin)]]} />
      </ReviewSection>
      <ReviewSection title="4. Sales">
        <Figures caption="Sales" rows={[["Leads", sales.leads], ["Students (new IT students)", sales.students], ["Applications", sales.applications], ["Enrollments", sales.enrollments], ["Placements", sales.placements]]} />
      </ReviewSection>
      <ReviewSection title="5. Partnerships">
        <Figures caption="Partnerships" rows={[["New agents", pa.agents], ["New schools (MoUs signed)", pa.schools], ["New universities", pa.universities], ["New companies", pa.companies]]} />
      </ReviewSection>
      <ReviewSection title="6. People">
        <Figures caption="People" rows={[["Employees", people.employees ?? NONE], ["Attendance", people.attendance_note], ["Productivity (revenue per employee)", inrOrNone(people.productivity)]]} />
        <h4 style={{ marginTop: 12 }}>Department performance</h4>
        {people.departments.length === 0 ? (
          <p className="muted">No department salaries entered for the month.</p>
        ) : (
          <div className="table-wrap">
            <table className="table stack">
              <caption className="visually-hidden">Department performance</caption>
              <thead><tr><th scope="col">Department</th><th scope="col">Headcount</th><th scope="col">Total cost</th></tr></thead>
              <tbody>
                {people.departments.map((d) => (
                  <tr key={d.name}><th scope="row" data-label="Department">{d.name}</th><td data-label="Headcount">{d.headcount}</td><td data-label="Total cost">{inrOrNone(d.total_cost)}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </ReviewSection>
      <ReviewSection title="7. Marketing">
        <Figures caption="Marketing" rows={[["Budget", inrOrNone(m.budget)], ["Spend", inrOrNone(m.spend)], ["Leads", m.leads], ["Customers", m.customers], ["Conversion", formatPercent(m.conversion)], ["Revenue", inrOrNone(m.revenue)], ["ROI", formatPercent(m.roi)]]} />
      </ReviewSection>
      <ReviewSection title="8. Investments">
        <Figures caption="Investments" rows={[["New investments", `${inv.new_count} · ${inrOrNone(inv.new_amount)}`], ["Total investment", inrOrNone(inv.total)], ["Return", inrOrNone(inv.return)], ["ROI", formatPercent(inv.roi)]]} />
      </ReviewSection>
    </>
  );
}
