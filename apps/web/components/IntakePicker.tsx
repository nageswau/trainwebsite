"use client";

// ccrm-047: the intake is a month and a year ("Sep 2027") wherever it is entered -- the server refuses any other shape for a new value.
// A legacy free-text value is shown as saved and kept until a month or year is chosen (AC6).
const MONTHS = [
  ["Jan", "January"], ["Feb", "February"], ["Mar", "March"], ["Apr", "April"], ["May", "May"], ["Jun", "June"],
  ["Jul", "July"], ["Aug", "August"], ["Sep", "September"], ["Oct", "October"], ["Nov", "November"], ["Dec", "December"],
] as const;
const MONTH_KEYS = MONTHS.map(([key]) => key).join("|");
const INTAKE = new RegExp(`^(?:${MONTH_KEYS}) \\d{4}$`);
const PARTS = new RegExp(`^(${MONTH_KEYS})?\\s?(\\d{4})?$`);
const HALF_CHOSEN = "Choose both the month and the year for the intake.";

export const isIntake = (value: string) => INTAKE.test(value);

/** A client-side refusal for a half-chosen intake; an empty value, a complete one or the untouched saved value is fine. */
export function intakeProblem(value: string, saved?: string | null): string | null {
  const text = value.trim();
  return !text || isIntake(text) || text === (saved ?? "").trim() ? null : HALF_CHOSEN;
}

export default function IntakePicker({ id, label, value, onChange, disabled, required }: {
  id: string; label: string; value: string; onChange: (value: string) => void; disabled?: boolean; required?: boolean;
}) {
  const parts = value.trim() ? PARTS.exec(value.trim()) : null;
  const legacy = !!value.trim() && !parts;
  const month = parts?.[1] ?? "";
  const year = parts?.[2] ?? "";
  const thisYear = new Date().getFullYear();
  const years = [0, 1, 2, 3].map((n) => String(thisYear + n));
  if (year && !years.includes(year)) years.unshift(year); // a saved year outside the range still shows
  const emit = (m: string, y: string) => onChange([m, y].filter(Boolean).join(" "));

  return (
    <fieldset className="field" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }} aria-describedby={legacy ? `${id}-legacy` : undefined}>
      <legend style={{ fontWeight: 800, fontSize: 13, padding: 0 }}>{label}{required && " *"}</legend>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        <select id={id} aria-label={`${label} month`} aria-required={required || undefined} value={month} disabled={disabled}
          onChange={(e) => emit(e.target.value, year)} style={{ flex: "1 1 8rem" }}>
          <option value="">Month</option>
          {MONTHS.map(([key, name]) => <option key={key} value={key}>{name}</option>)}
        </select>
        <select id={`${id}-year`} aria-label={`${label} year`} aria-required={required || undefined} value={year} disabled={disabled}
          onChange={(e) => emit(month, e.target.value)} style={{ flex: "1 1 6rem" }}>
          <option value="">Year</option>
          {years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
      </div>
      {legacy && <p id={`${id}-legacy`} className="muted" style={{ margin: 0, fontSize: 13 }}>Saved as “{value}”. Choose a month and year to replace it.</p>}
    </fieldset>
  );
}
