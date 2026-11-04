// hrc-003 (DEC-SCOPE-370 S3, S7): "this record changed since you opened it". An edit form keeps the values and the token (the record's
// `updated_at` string exactly as the API sent it -- never through Date, which drops microseconds -- or a JD's version number) it was
// opened with and sends the token with every save. A 409 `record_changed` carries who/what/when and the current record; the user then
// reloads (drops their edits) or reviews (their edited fields re-applied over the latest values). Nothing is merged automatically.
import { useState } from "react";

import { formatDateTimeIn, SCHOOL_TIME_ZONE } from "@/lib/formatDate";

export type StaleToken = string | number;
export type StaleConflict<T> = { changedBy: string | null; changedAt: string | null; changedFields: string[]; current: T };
export type ReviewItem = { key: string; yours: string; now: string; alsoChanged: boolean };
type Values = Record<string, string>;

/** A 409 `record_changed` body -> the conflict; any other failure -> null (the caller shows its usual error). */
export function staleConflict<T>(outcome: { ok: boolean; status?: number; detail?: unknown }): StaleConflict<T> | null {
  const d = outcome.ok ? null : (outcome.detail as { code?: unknown; changed_by?: { full_name?: unknown } | null; changed_at?: unknown; changed_fields?: unknown; current?: unknown } | null);
  if (outcome.ok || outcome.status !== 409 || !d || d.code !== "record_changed" || typeof d.current !== "object" || d.current === null) return null;
  return {
    changedBy: typeof d.changed_by?.full_name === "string" ? d.changed_by.full_name : null,
    changedAt: typeof d.changed_at === "string" ? d.changed_at : null,
    changedFields: Array.isArray(d.changed_fields) ? d.changed_fields.filter((f): f is string => typeof f === "string") : [],
    current: d.current as T,
  };
}

/** "This record changed since you opened it (by Priya at 04 Nov 2026, 10:15 IST)." -- the parts the API knew. */
export function staleSummary(conflict: StaleConflict<unknown>): string {
  const by = [conflict.changedBy && `by ${conflict.changedBy}`, conflict.changedAt && `at ${formatDateTimeIn(conflict.changedAt, SCHOOL_TIME_ZONE, true)}`].filter(Boolean).join(" ");
  return `This record changed since you opened it${by ? ` (${by})` : ""}.`;
}

/** S7 Review: the latest values with the user's own edits (the fields that differ from what they opened) put back on top. */
export function reapply<F extends Values>(latest: F, opened: F, mine: F): { values: F; review: ReviewItem[] } {
  const edited = Object.keys(mine).filter((key) => mine[key] !== opened[key]);
  const values = { ...latest };
  for (const key of edited) (values as Values)[key] = mine[key];
  return { values, review: edited.filter((key) => mine[key] !== latest[key]).map((key) => ({ key, yours: mine[key], now: latest[key], alsoChanged: latest[key] !== opened[key] })) };
}

/** The form's values plus the version they were opened from. `toValues`/`tokenOf` read a record (the prop, or a 409's `current`);
 *  `onLatest` hands the latest record to the page behind the form when the user reloads or reviews (so Cancel shows it too). */
export function useStaleGuard<T, F extends Values>(
  record: T | undefined, toValues: (r: T | undefined) => F, tokenOf: (r: T | undefined) => StaleToken | null, onLatest?: (r: T) => void,
) {
  const [opened, setOpened] = useState(() => ({ values: toValues(record), token: tokenOf(record) }));
  const [values, setValues] = useState(opened.values);
  const [conflict, setConflict] = useState<StaleConflict<T> | null>(null);
  const [review, setReview] = useState<ReviewItem[] | null>(null);

  function rebase(current: T, next: F, items: ReviewItem[] | null) {
    setOpened({ values: toValues(current), token: tokenOf(current) });
    setValues(next);
    setConflict(null);
    setReview(items);
    onLatest?.(current);
  }

  return {
    values,
    setValues,
    opened: opened.values,
    token: opened.token,
    conflict,
    review,
    /** True (and the notice shows) when the outcome is a 409 `record_changed`. */
    caught(outcome: { ok: boolean; status?: number; detail?: unknown }): boolean {
      const found = staleConflict<T>(outcome);
      if (found) {
        setConflict(found);
        setReview(null);
      }
      return !!found;
    },
    /** Reload: the latest record, the user's edits dropped. */
    reload: () => rebase(conflict!.current, toValues(conflict!.current), null),
    /** Review my changes: the latest record with the user's edits re-applied, listed for checking. */
    reviewMine: () => {
      const { values: next, review: items } = reapply(toValues(conflict!.current), opened.values, values);
      rebase(conflict!.current, next, items);
    },
  };
}

