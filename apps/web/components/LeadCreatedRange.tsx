"use client";

export const CREATED_FILTERS = ["created_from", "created_to"] as const;
export type CreatedFilter = (typeof CREATED_FILTERS)[number];
export const RANGE_REVERSED = "Choose a start date on or before the end date.";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** A hand-edited URL date the API would refuse (422) is ignored, not sent -- the lead lists' QA-02 rule. */
export const validDay = (value: string) => (ISO_DAY.test(value) ? value : "");

/** nehn-012 (DEC-SCOPE-296): the lead lists' "Created from" / "Created to" -- India-time days, inclusive; the panel owns the URL. Each
 *  picker is bounded by the other, and the panel says so (without asking the API) when a typed or linked range is reversed. */
export default function LeadCreatedRange({ idPrefix, values, onChange }: {
  idPrefix: string;
  values: Record<CreatedFilter, string>;
  onChange: (key: CreatedFilter, value: string) => void;
}) {
  const field = (key: CreatedFilter, label: string, bound: { min?: string; max?: string }) => (
    <div className="field" style={{ flex: "1 1 10rem" }}>
      <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
      <input id={`${idPrefix}-${key}`} type="date" value={values[key]} {...bound} onChange={(event) => onChange(key, event.target.value)} />
    </div>
  );
  return (
    <>
      {field("created_from", "Created from", { max: values.created_to || undefined })}
      {field("created_to", "Created to", { min: values.created_from || undefined })}
    </>
  );
}

export const reversed = (values: Record<CreatedFilter, string>) => !!values.created_from && !!values.created_to && values.created_from > values.created_to;
