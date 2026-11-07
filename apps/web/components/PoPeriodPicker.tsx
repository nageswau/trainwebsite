import type { Period } from "@/lib/recruiterPoWork";

/** pob-009: the report period picker -- a plain GET form (daily or the week holding the date, Monday-Sunday IST). */
export default function PoPeriodPicker({ action, period, start, today }: { action: string; period: Period; start: string; today: string }) {
  return (
    <form className="analytics-form" method="get" action={action} aria-label="Choose a report period">
      <div className="field">
        <label htmlFor="report-period">Report</label>
        <select id="report-period" name="period" defaultValue={period}>
          <option value="daily">Daily</option>
          <option value="weekly">Weekly (Mon–Sun)</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="report-start">Date</label>
        <input id="report-start" type="date" name="start" defaultValue={start} max={today} />
      </div>
      <button className="btn secondary" type="submit">Show</button>
    </form>
  );
}
