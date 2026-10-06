import Link from "next/link";

import TripDetails from "@/components/TripDetails";
import TripItinerary from "@/components/TripItinerary";
import TripProductivity from "@/components/TripProductivity";
import { CATEGORY_LABEL, type ExpenseCategory, formatInr, type Trip } from "@/lib/bdmTravel";

// bdm-011 (§4 Common: travel report): the read-only summary of a completed trip, for the BDM and their manager -- details, the
// appointments, the productivity figures, expenses by category and the remarks added after the trip (they stay editable, §7).
const paise = (amount: string) => Math.round(Number(amount) * 100); // sum in whole paise: no floating-point drift
const rupees = (p: number) => (p / 100).toFixed(2);

function byCategory(trip: Trip): [string, string][] {
  const totals = new Map<ExpenseCategory, number>();
  for (const e of trip.expenses) totals.set(e.category, (totals.get(e.category) ?? 0) + paise(e.amount));
  return (Object.keys(CATEGORY_LABEL) as ExpenseCategory[]).filter((c) => totals.has(c)).map((c) => [CATEGORY_LABEL[c], rupees(totals.get(c)!)]);
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  const id = `report-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section className="card" aria-labelledby={id} style={{ marginTop: 20 }}>
      <h3 id={id}>{title}</h3>
      {children}
    </section>
  );
}

/** The report page's title, with the way back to the trip (also when the report isn't available yet). */
export function ReportTitle({ trip, tripHref }: { trip: Trip | null; tripHref: string }) {
  return (
    <div className="portal-title">
      <div>
        <div className="eyebrow">Travel report{trip ? ` · ${trip.code} · ${trip.bdm.full_name}` : ""}</div>
        <h2 style={{ overflowWrap: "anywhere" }}>{trip ? `${trip.from_place} → ${trip.to_place}` : "Travel report"}</h2>
      </div>
      <Link className="btn secondary" href={tripHref}>Back to the trip</Link>
    </div>
  );
}

export default function TripReport({ trip, view }: { trip: Trip; view: "owner" | "manager" }) {
  const lines = byCategory(trip);
  return (
    <>
      <Section title="Trip details"><TripDetails trip={trip} /></Section>
      <Section title="Appointments"><TripItinerary trip={trip} view={view} /></Section>
      <Section title="Productivity"><TripProductivity metrics={trip.metrics} /></Section>
      <Section title="Expenses by category">
        {lines.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>No expenses were recorded.</p>
        ) : (
          <div className="table-wrap">
            <table style={{ minWidth: 0 }}>
              <caption className="visually-hidden">Expenses by category</caption>
              <thead><tr><th scope="col">Category</th><th scope="col">Amount</th></tr></thead>
              <tbody>
                {lines.map(([label, amount]) => <tr key={label}><td>{label}</td><td>{formatInr(amount)}</td></tr>)}
                <tr><th scope="row">Total</th><td><strong>{formatInr(trip.actual_cost)}</strong></td></tr>
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section title="Remarks">
        {trip.remarks ? <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>{trip.remarks}</p> : <p className="muted" style={{ margin: 0 }}>No remarks were added.</p>}
      </Section>
    </>
  );
}
