"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import FormMessage from "@/components/FormMessage";
import {
  AMOUNT_PATTERN, MAX_SPAN_DAYS, MODE_LABEL, PAST_DAYS, TRIPS_URL, addDays, dateRuleField, fieldErrors, isIsoDate, travelDateBounds, tripUrl, type Trip,
  type TripMode,
} from "@/lib/bdmTravel";
import { refocus } from "@/lib/focus";
import { useHydrated } from "@/lib/useHydrated";
import { jsonInit, useTripWrite } from "@/lib/useTripWrite";

type Values = {
  travel_date: string; return_date: string; from_place: string; to_place: string; purpose: string; mode: TripMode;
  accommodation_required: boolean; estimated_cost: string; remarks: string;
};
const TEXT: [keyof Values, string][] = [["from_place", "From"], ["to_place", "To"]];
const REQUIRED: [keyof Values, string][] = [
  ["travel_date", "Travel date"], ["return_date", "Return date"], ["from_place", "From"], ["to_place", "To"], ["purpose", "Purpose"],
  ["estimated_cost", "Estimated cost"],
];

const initial = (t?: Trip): Values => ({
  travel_date: t?.travel_date ?? "", return_date: t?.return_date ?? "", from_place: t?.from_place ?? "", to_place: t?.to_place ?? "",
  purpose: t?.purpose ?? "", mode: t?.mode ?? "train", accommodation_required: t?.accommodation_required ?? false,
  estimated_cost: t ? String(Number(t.estimated_cost)) : "", remarks: "",
});

function payload(v: Values, create: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    travel_date: v.travel_date, return_date: v.return_date, from_place: v.from_place.trim(), to_place: v.to_place.trim(),
    purpose: v.purpose.trim(), mode: v.mode, accommodation_required: v.accommodation_required, estimated_cost: v.estimated_cost.trim(),
  };
  if (create && v.remarks.trim()) body.remarks = v.remarks.trim();
  return body;
}

function validate(v: Values, min: string): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const [key, label] of REQUIRED) if (!String(v[key]).trim()) errors[key] = `${label} is required`;
  if (v.travel_date && !isIsoDate(v.travel_date)) errors.travel_date = "Enter a valid travel date"; // QA10-08
  if (v.return_date && !isIsoDate(v.return_date)) errors.return_date = "Enter a valid return date";
  const datesOk = isIsoDate(v.travel_date) && isIsoDate(v.return_date);
  if (isIsoDate(v.travel_date) && v.travel_date < min) errors.travel_date = `Travel date can be at most ${PAST_DAYS} days in the past`;
  if (datesOk && v.return_date < v.travel_date) errors.return_date = "Return date must be on or after the travel date";
  else if (datesOk && v.return_date > addDays(v.travel_date, MAX_SPAN_DAYS)) errors.return_date = `A trip can last at most ${MAX_SPAN_DAYS + 1} days`; // QA10-07
  if (v.estimated_cost.trim() && !AMOUNT_PATTERN.test(v.estimated_cost.trim())) errors.estimated_cost = "Enter an amount in rupees with up to 2 decimals";
  return errors;
}

// bdm-010 (§12.2 F3): create a draft, or edit a draft/rejected trip (only changed fields are sent). Client checks mirror the API
// for quick feedback; the API stays authoritative and its 422s land next to their field.
export default function TripForm({ trip, today }: { trip?: Trip; today: string }) {
  const router = useRouter();
  const create = !trip;
  const [values, setValues] = useState<Values>(() => initial(trip));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const { busy, message, setMessage, run, resultProps } = useTripWrite();
  const { min } = travelDateBounds(today);
  const ready = useHydrated(); // QA10-17: disabled until React owns the inputs, so nothing typed early is wiped
  const set = <K extends keyof Values>(key: K, value: Values[K]) => setValues((v) => ({ ...v, [key]: value }));

  const fieldProps = (key: keyof Values) => ({
    id: `trip-${key}`, "aria-invalid": errors[key] ? true : undefined, "aria-describedby": errors[key] ? `trip-${key}-error` : undefined,
  });
  const error = (key: keyof Values) => errors[key] && <p className="form-error" id={`trip-${key}-error`}>{errors[key]}</p>;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const found = validate(values, min);
    setErrors(found);
    if (Object.keys(found).length) {
      setMessage({ text: "Check the highlighted fields.", failed: true });
      refocus(`trip-${Object.keys(found)[0]}`);
      return;
    }
    const body = payload(values, create);
    if (create) {
      const outcome = await run(TRIPS_URL, jsonInit("POST", body), "Trip saved as a draft.", (data) => router.push(`/bdm/travel/${data.id}`));
      if (!outcome.ok) setErrors({ ...fieldErrors(outcome.detail), ...dateRuleField(outcome.detail) });
      return;
    }
    const before = payload(initial(trip), false);
    const changes = Object.fromEntries(Object.entries(body).filter(([k, v]) => v !== before[k]));
    if (!Object.keys(changes).length) return setMessage({ text: "Nothing to change.", failed: false });
    const outcome = await run(tripUrl(trip.id), jsonInit("PATCH", changes), "Trip saved.");
    if (!outcome.ok) setErrors({ ...fieldErrors(outcome.detail), ...dateRuleField(outcome.detail) });
  }

  return (
    <form className="form" onSubmit={submit} noValidate aria-label={create ? "New trip" : "Edit trip"}>
      <fieldset disabled={!ready} className="form" style={{ border: 0, padding: 0, margin: 0, minWidth: 0 }}>
      <div className="form-grid">
        <div className="field">
          <label htmlFor="trip-travel_date">Travel date</label>
          <input type="date" min={min} value={values.travel_date} onChange={(e) => set("travel_date", e.target.value)} {...fieldProps("travel_date")} />
          {error("travel_date")}
        </div>
        <div className="field">
          <label htmlFor="trip-return_date">Return date</label>
          <input type="date" min={values.travel_date || min} max={isIsoDate(values.travel_date) ? addDays(values.travel_date, MAX_SPAN_DAYS) : undefined} value={values.return_date} onChange={(e) => set("return_date", e.target.value)} {...fieldProps("return_date")} />
          {error("return_date")}
        </div>
        {TEXT.map(([key, label]) => (
          <div className="field" key={key}>
            <label htmlFor={`trip-${key}`}>{label}</label>
            <input type="text" maxLength={120} autoComplete="off" value={String(values[key])} onChange={(e) => set(key, e.target.value)} {...fieldProps(key)} />
            {error(key)}
          </div>
        ))}
        <div className="field">
          <label htmlFor="trip-mode">Mode of travel</label>
          {/* QA10-11: keep its own height when a neighbour in the row shows an error */}
          <select value={values.mode} onChange={(e) => set("mode", e.target.value as TripMode)} style={{ alignSelf: "start" }} {...fieldProps("mode")}>
            {Object.entries(MODE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </div>
        <div className="field">
          <label htmlFor="trip-estimated_cost">Estimated cost (₹)</label>
          <input type="text" inputMode="decimal" autoComplete="off" value={values.estimated_cost} onChange={(e) => set("estimated_cost", e.target.value)} {...fieldProps("estimated_cost")} />
          {error("estimated_cost")}
        </div>
      </div>
      <div className="field">
        <label htmlFor="trip-purpose">Purpose</label>
        <textarea rows={3} maxLength={1000} value={values.purpose} onChange={(e) => set("purpose", e.target.value)} {...fieldProps("purpose")} />
        {error("purpose")}
      </div>
      <div className="field">
        <label htmlFor="trip-accommodation_required" style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input id="trip-accommodation_required" type="checkbox" checked={values.accommodation_required} onChange={(e) => set("accommodation_required", e.target.checked)} style={{ width: "auto" }} />
          Accommodation required
        </label>
      </div>
      {create && (
        <div className="field">
          <label htmlFor="trip-remarks">Remarks</label>
          <textarea rows={2} maxLength={2000} value={values.remarks} onChange={(e) => set("remarks", e.target.value)} {...fieldProps("remarks")} />
          {error("remarks")}
        </div>
      )}
      <div className="actions">
        <button className="btn" type="submit" disabled={busy}>{busy ? "Saving…" : create ? "Save draft" : "Save changes"}</button>
      </div>
      </fieldset>
      <div {...resultProps}>{message && <FormMessage message={message} />}</div>
    </form>
  );
}
