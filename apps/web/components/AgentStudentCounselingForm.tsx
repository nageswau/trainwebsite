"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import {
  AgentStudentDetail,
  counselingPayload,
  counselingUrl,
  counselingValues,
  CounselingField,
  CounselingValues,
  CURRENCIES,
  fieldErrors,
  Currency,
  NOTES_MAX,
  validateCounseling,
} from "@/lib/agentStudents";

// AGN-006 (DEC-SCOPE-048): record a student's counseling outcome (EVID-015 §5 Step 2). The whole record is sent (PUT); the server
// stamps who completed it and when. Validation mirrors the server's schema; the server remains the authority.
const TEXT_FIELDS: { key: "career_interest" | "course_preference" | "country_preference"; label: string }[] = [
  { key: "career_interest", label: "Career interest" },
  { key: "course_preference", label: "Course preference" },
  { key: "country_preference", label: "Country preference" },
];
const FOCUS_ORDER: CounselingField[] = ["counseling_completed", "career_interest", "course_preference", "country_preference", "budget_amount", "budget_currency", "remarks"];
export const LEAVE_PROMPT = "You have unsaved counseling changes. Leave without saving?";

export default function AgentStudentCounselingForm({
  detail,
  onSaved,
  onCancel,
  onDirtyChange,
}: {
  detail: AgentStudentDetail;
  onSaved: (s: AgentStudentDetail) => void;
  onCancel: () => void;
  // Review #2: the list asks before another student replaces unsaved input (opening a student is leaving the form too).
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const original = useRef<CounselingValues>(counselingValues(detail.counseling));
  const [values, setValues] = useState<CounselingValues>(original.current);
  const [errors, setErrors] = useState<Partial<Record<CounselingField, string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const idPrefix = `counseling-${detail.id}`;
  const dirty = JSON.stringify(counselingPayload(values)) !== JSON.stringify(counselingPayload(original.current));

  useEffect(() => {
    document.getElementById(`${idPrefix}-counseling_completed`)?.focus();
  }, [idPrefix]);

  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false); // unmounted (saved, cancelled or left): nothing unsaved remains
  }, [dirty, onDirtyChange]);

  // Leave prompt while there is unsaved input (C9; AgentStudentForm's pattern, browser QA-03): beforeunload covers reload/close; an
  // in-app link navigates client-side, so ask first -- capture phase runs before Next's Link handler.
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    const guardLinks = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = (event.target as Element | null)?.closest?.("a[href]") as HTMLAnchorElement | null;
      if (!link || link.target === "_blank" || link.hasAttribute("download") || link.origin !== window.location.origin) return;
      if (!window.confirm(LEAVE_PROMPT)) {
        event.preventDefault();
        event.stopPropagation();
      }
    };
    window.addEventListener("beforeunload", warn);
    document.addEventListener("click", guardLinks, true);
    return () => {
      window.removeEventListener("beforeunload", warn);
      document.removeEventListener("click", guardLinks, true);
    };
  }, [dirty]);

  function set<K extends CounselingField>(key: K, value: CounselingValues[K]) {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
  }

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function focusFirst(found: Partial<Record<CounselingField, string>>): boolean {
    const first = FOCUS_ORDER.find((key) => found[key]);
    if (first) document.getElementById(`${idPrefix}-${first}`)?.focus();
    return Boolean(first);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    const found = validateCounseling(values);
    setErrors(found);
    if (focusFirst(found)) return;
    if (!dirty) {
      onCancel();
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    try {
      const response = await fetch(counselingUrl(detail.id), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(counselingPayload(values)),
      });
      const body = await response.json().catch(() => null);
      if (response.ok && body?.student) {
        onSaved(body.student as AgentStudentDetail);
        return;
      }
      const onFields = response.status === 422 ? fieldErrors(body?.detail, FOCUS_ORDER) : null;
      if (onFields) {
        setErrors(onFields);
        requestAnimationFrame(() => focusFirst(onFields));
      } else {
        setFailure(detailMessage(body?.detail, "Unable to save counseling."));
        refocus(`${idPrefix}-save`);
      }
    } catch {
      setFailure(NOT_COMPLETED);
      refocus(`${idPrefix}-save`);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const describedBy = (key: CounselingField, extra?: string) => [errors[key] ? `${idPrefix}-${key}-error` : null, extra].filter(Boolean).join(" ") || undefined;
  const error = (key: CounselingField) =>
    errors[key] ? (
      <p className="form-error" id={`${idPrefix}-${key}-error`}>
        {errors[key]}
      </p>
    ) : null;

  return (
    <form className="form" onSubmit={submit} aria-busy={busy} noValidate aria-labelledby={`${idPrefix}-title`}>
      <h5 id={`${idPrefix}-title`}>
        {detail.counseling ? "Edit counseling" : "Record counseling"} for {detail.full_name}
      </h5>
      <fieldset className="form-busy-wrap" disabled={busy}>
        <label className="pf-check" htmlFor={`${idPrefix}-counseling_completed`}>
          <input
            id={`${idPrefix}-counseling_completed`}
            type="checkbox"
            checked={values.counseling_completed}
            onChange={(e) => set("counseling_completed", e.target.checked)}
          />
          Counseling completed
        </label>
        {TEXT_FIELDS.map((f) => (
          <div className="field" key={f.key}>
            <label htmlFor={`${idPrefix}-${f.key}`}>{f.label}</label>
            <input
              id={`${idPrefix}-${f.key}`}
              type="text"
              value={values[f.key]}
              aria-invalid={errors[f.key] ? true : undefined}
              aria-describedby={describedBy(f.key)}
              onChange={(e) => set(f.key, e.target.value)}
            />
            {error(f.key)}
          </div>
        ))}
        <fieldset>
          <legend>Budget</legend>
          <p className="muted field-help" id={`${idPrefix}-budget-help`}>
            Leave the amount empty if no budget was discussed.
          </p>
          <div className="form-grid">
            <div className="field">
              <label htmlFor={`${idPrefix}-budget_amount`}>Amount</label>
              <input
                id={`${idPrefix}-budget_amount`}
                type="text"
                inputMode="decimal"
                autoComplete="off"
                value={values.budget_amount}
                aria-invalid={errors.budget_amount ? true : undefined}
                aria-describedby={describedBy("budget_amount", `${idPrefix}-budget-help`)}
                onChange={(e) => set("budget_amount", e.target.value)}
              />
              {error("budget_amount")}
            </div>
            <div className="field">
              <label htmlFor={`${idPrefix}-budget_currency`}>Currency</label>
              <select
                id={`${idPrefix}-budget_currency`}
                value={values.budget_currency}
                aria-invalid={errors.budget_currency ? true : undefined}
                aria-describedby={describedBy("budget_currency")}
                onChange={(e) => set("budget_currency", e.target.value as Currency)}
              >
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              {error("budget_currency")}
            </div>
          </div>
        </fieldset>
        <div className="field">
          <label htmlFor={`${idPrefix}-remarks`}>Remarks</label>
          <textarea
            id={`${idPrefix}-remarks`}
            rows={4}
            value={values.remarks}
            aria-invalid={errors.remarks ? true : undefined}
            aria-describedby={describedBy("remarks", `${idPrefix}-remarks-count`)}
            onChange={(e) => set("remarks", e.target.value)}
          />
          <p className="muted field-help" id={`${idPrefix}-remarks-count`}>
            {values.remarks.length} / {NOTES_MAX}
          </p>
          {error("remarks")}
        </div>
        {failure && (
          <p className="form-error" role="alert">
            {failure}
          </p>
        )}
        <div>
          <button id={`${idPrefix}-save`} type="submit" className="btn small">
            {busy ? "Saving…" : "Save counseling"}
          </button>{" "}
          <button type="button" className="btn secondary small" onClick={cancel}>
            Cancel
          </button>
        </div>
      </fieldset>
    </form>
  );
}
