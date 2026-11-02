"use client";

export const CREATED_FILTERS = ["created_from", "created_to"] as const;
export type CreatedFilter = (typeof CREATED_FILTERS)[number];
export const RANGE_REVERSED = "Choose a start date on or before the end date.";

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/** A hand-edited URL date the API would refuse (422) is ignored, not sent -- the lead lists' QA-02 rule. */
export const validDay = (value: string) => (ISO_DAY.test(value) ? value : "");

/** nehn-012 (DEC-SCOPE-298): the lead lists' "Created from" / "Created to" -- India-time days, inclusive; the panel owns the URL. Each
 *  picker is bounded by the other, and the panel says so (without asking the API) when a typed or linked range is reversed.
 *  itc-008: any other from/to pair of day filters (last contact, next follow-up) passes its own `keys` and `labels`. */
export default function LeadCreatedRange({ idPrefix, values, onChange, keys = CREATED_FILTERS, labels = ["Created from", "Created to"] }: {
  idPrefix: string;
  values: Record<string, string>;
  onChange(key: string, value: string): void; // method syntax: a caller may type `key` as its own filter union
  keys?: readonly [string, string];
  labels?: readonly [string, string];
}) {
  const [from, to] = keys;
  const field = (key: string, label: string, bound: { min?: string; max?: string }) => (
    <div className="field" style={{ flex: "1 1 10rem" }}>
      <label htmlFor={`${idPrefix}-${key}`}>{label}</label>
      <input id={`${idPrefix}-${key}`} type="date" value={values[key]} {...bound} onChange={(event) => onChange(key, event.target.value)} />
    </div>
  );
  return (
    <>
      {field(from, labels[0], { max: values[to] || undefined })}
      {field(to, labels[1], { min: values[from] || undefined })}
    </>
  );
}

export const reversed = (values: Record<string, string>, [from, to]: readonly [string, string] = CREATED_FILTERS) =>
  !!values[from] && !!values[to] && values[from] > values[to];
