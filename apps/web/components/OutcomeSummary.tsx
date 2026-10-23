import { formatCalendarDate } from "@/lib/formatDate";
import { outcomeLabel, type OutcomeDetail } from "@/lib/applicationOutcome";

// ccrm-015 (DEC-SCOPE-244): the current outcome of one application and the details recorded with it (staff fields when present).
export default function OutcomeSummary({ outcome }: { outcome: OutcomeDetail }) {
  const rows: [string, string | null | undefined][] = [
    ["Date", outcome.outcome_date && formatCalendarDate(outcome.outcome_date)],
    ["Reason", outcome.reason],
    ["Requested by", outcome.requested_by && outcomeLabel(outcome.requested_by)],
    ["Review date", outcome.review_date && formatCalendarDate(outcome.review_date)],
    ["Hold owner", outcome.hold_owner],
    ["New intake", outcome.new_intake],
    ["Suggested next steps", outcome.next_steps],
    ["Prefers another offer", outcome.another_offer_preferred == null ? null : outcome.another_offer_preferred ? "Yes" : "No"],
  ];
  return (
    <section className="card" style={{ marginTop: 8, padding: 14 }} aria-label="Application outcome">
      <span className={outcome.terminal ? "status error" : "status pending"}>{outcome.label}</span>
      <dl className="card-stack" style={{ marginTop: 8 }}>
        {rows
          .filter(([, value]) => value)
          .map(([term, value]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{value}</dd>
            </div>
          ))}
      </dl>
    </section>
  );
}
