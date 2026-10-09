import type { Period } from "@/lib/partnershipPerformance";

// upc-018: the period picker shared by Student Opportunities and University Performance -- a plain GET form, so the period lives in the
// URL. `keep` carries other query values (the chosen university) through a new period.
export default function PerformancePeriodForm({ action, period, keep = {} }: { action: string; period: Period; keep?: Record<string, string> }) {
  return (
    <form className="analytics-form" method="get" action={action} aria-label="Choose a period">
      {Object.entries(keep).map(([name, value]) => <input key={name} type="hidden" name={name} value={value} />)}
      <div className="field">
        <label htmlFor="period-from">From</label>
        <input id="period-from" type="date" name="from" defaultValue={period.from} required />
      </div>
      <div className="field">
        <label htmlFor="period-to">To</label>
        <input id="period-to" type="date" name="to" defaultValue={period.to} required />
      </div>
      <button className="btn secondary" type="submit">Show</button>
    </form>
  );
}
