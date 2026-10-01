"use client";

import { FormEvent, useEffect, useRef, useState } from "react";

import { detailMessage, NOT_COMPLETED } from "@/lib/apiErrors";
import { refocus } from "@/lib/focus";
import {
  AgentStudentDetail,
  buildPayload,
  DuplicateDetail,
  duplicateDetail,
  emptyValues,
  FieldKey,
  FormValues,
  NOTES_MAX,
  RECORDS_URL,
  validate,
  valuesFrom,
} from "@/lib/agentStudents";

// AGN-004 (DEC-SCOPE-042): add or edit an agency student who never logs in (EVID-015 §5 Step 1). Only Full name is required.
// A possible duplicate is the server's 409; the user decides, and "Save anyway" resends the same entry with confirm_duplicate.
type Field = { key: FieldKey; label: string; type?: string; inputMode?: "numeric"; autoComplete?: string };
const GROUPS: { legend: string; fields: Field[] }[] = [
  { legend: "Personal", fields: [{ key: "full_name", label: "Full name (required)", autoComplete: "name" }, { key: "date_of_birth", label: "Date of birth", type: "date" }] },
  { legend: "Contact", fields: [{ key: "email", label: "Email", type: "email", autoComplete: "email" }, { key: "phone", label: "Phone", type: "tel", autoComplete: "tel" }] },
  {
    legend: "Academic",
    fields: [{ key: "highest_qualification", label: "Highest qualification" }, { key: "institution", label: "Institution" }, { key: "graduation_year", label: "Graduation year", inputMode: "numeric" }],
  },
  {
    legend: "Preferences",
    fields: [{ key: "preferred_country", label: "Preferred country" }, { key: "preferred_course", label: "Preferred course" }, { key: "preferred_intake", label: "Preferred intake (e.g. Sep 2027)" }],
  },
];
const FOCUS_ORDER: FieldKey[] = [...GROUPS.flatMap((g) => g.fields.map((f) => f.key)), "notes"];
const LEAVE_PROMPT = "You have unsaved changes to this student. Leave without saving?";

// FastAPI's 422 list -> {field: message} for the fields this form shows, or null when any error is not one of them (then the
// whole detail is shown as one message instead, so nothing is hidden).
function fieldErrors(detail: unknown): Partial<Record<FieldKey, string>> | null {
  if (!Array.isArray(detail) || detail.length === 0) return null;
  const out: Partial<Record<FieldKey, string>> = {};
  for (const item of detail as { loc?: unknown[] }[]) {
    const field = item?.loc?.[item.loc.length - 1];
    if (typeof field !== "string" || !FOCUS_ORDER.includes(field as FieldKey)) return null;
    out[field as FieldKey] = detailMessage([item]);
  }
  return out;
}

export default function AgentStudentForm({
  mode,
  student,
  onSaved,
  onCancel,
}: {
  mode: "create" | "edit";
  student?: AgentStudentDetail;
  onSaved: (s: AgentStudentDetail) => void;
  onCancel: () => void;
}) {
  const original = useRef<FormValues>(student ? valuesFrom(student) : emptyValues());
  const [values, setValues] = useState<FormValues>(original.current);
  const [errors, setErrors] = useState<Partial<Record<FieldKey, string>>>({});
  const [failure, setFailure] = useState<string | null>(null);
  const [duplicate, setDuplicate] = useState<DuplicateDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const idPrefix = mode === "create" ? "agent-student-new" : `agent-student-${student?.id}`;
  const today = new Date().toISOString().slice(0, 10);
  const dirty = Object.keys(buildPayload(values, original.current)).length > 0;

  // Leave prompt while there is unsaved input (the PsychometricResultsForm pattern): beforeunload covers reload/close; an in-app
  // link (sidebar) navigates client-side, so ask first -- capture phase runs before Next's Link handler (browser QA-03).
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

  function cancel() {
    if (dirty && !window.confirm(LEAVE_PROMPT)) return;
    onCancel();
  }

  function set(key: FieldKey, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
    setErrors((e) => ({ ...e, [key]: undefined }));
    setDuplicate(null);
  }

  async function save(confirmDuplicate: boolean) {
    if (inFlight.current) return;
    const found = validate(values, mode === "edit" ? original.current : undefined);
    setErrors(found);
    const firstInvalid = FOCUS_ORDER.find((key) => found[key]);
    if (firstInvalid) {
      document.getElementById(`${idPrefix}-${firstInvalid}`)?.focus();
      return;
    }
    const payload = mode === "create" ? buildPayload(values) : buildPayload(values, original.current);
    if (mode === "edit" && Object.keys(payload).length === 0) {
      onCancel();
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setFailure(null);
    let focusAfter = `${idPrefix}-save`;
    try {
      const response = await fetch(mode === "create" ? RECORDS_URL : `${RECORDS_URL}/${student!.id}`, {
        method: mode === "create" ? "POST" : "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(confirmDuplicate ? { ...payload, confirm_duplicate: true } : payload),
      });
      const body = await response.json().catch(() => ({}));
      if (response.ok && body?.student?.id) {
        original.current = values;
        setDuplicate(null);
        onSaved(body.student);
        return;
      }
      const dup = response.status === 409 ? duplicateDetail(body?.detail) : null;
      const onFields = response.status === 422 ? fieldErrors(body?.detail) : null;
      if (dup) setDuplicate(dup);
      else if (onFields) {
        // Browser QA-05: a server validation error belongs on its field, like the client-side ones.
        setErrors(onFields);
        const first = FOCUS_ORDER.find((key) => onFields[key]);
        if (first) focusAfter = `${idPrefix}-${first}`;
      } else setFailure(detailMessage(body?.detail, "Unable to save this student."));
    } catch {
      setFailure(NOT_COMPLETED);
    } finally {
      inFlight.current = false;
      setBusy(false);
      refocus(focusAfter);
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void save(false);
  }

  const describedBy = (key: FieldKey, extra?: string) => [errors[key] ? `${idPrefix}-${key}-error` : null, extra].filter(Boolean).join(" ") || undefined;

  return (
    <form className="form" onSubmit={submit} aria-busy={busy} noValidate aria-labelledby={`${idPrefix}-title`}>
      <h4 id={`${idPrefix}-title`}>{mode === "create" ? "Add student" : `Edit ${student?.full_name}`}</h4>
      {GROUPS.map((group) => (
        <fieldset key={group.legend}>
          <legend>{group.legend}</legend>
          {group.fields.map((f) => {
            const id = `${idPrefix}-${f.key}`;
            return (
              <div className="field" key={f.key}>
                <label htmlFor={id}>{f.label}</label>
                <input
                  id={id}
                  type={f.type ?? "text"}
                  inputMode={f.inputMode}
                  autoComplete={f.autoComplete}
                  value={values[f.key]}
                  max={f.type === "date" ? today : undefined}
                  // AGN-005 QA5-02: a new-student form opens on its first field, so keyboard users start typing where they expect.
                  autoFocus={mode === "create" && f.key === "full_name"}
                  aria-required={f.key === "full_name" ? true : undefined}
                  aria-invalid={errors[f.key] ? true : undefined}
                  aria-describedby={describedBy(f.key)}
                  onChange={(e) => set(f.key, e.target.value)}
                />
                {errors[f.key] && (
                  <p className="form-error" id={`${id}-error`}>
                    {errors[f.key]}
                  </p>
                )}
              </div>
            );
          })}
        </fieldset>
      ))}
      <div className="field">
        <label htmlFor={`${idPrefix}-notes`}>Notes</label>
        <textarea
          id={`${idPrefix}-notes`}
          rows={4}
          value={values.notes}
          aria-invalid={errors.notes ? true : undefined}
          aria-describedby={describedBy("notes", `${idPrefix}-notes-count`)}
          onChange={(e) => set("notes", e.target.value)}
        />
        <p className="muted" id={`${idPrefix}-notes-count`} style={{ fontSize: 12 }}>
          {values.notes.length} / {NOTES_MAX}
        </p>
        {errors.notes && (
          <p className="form-error" id={`${idPrefix}-notes-error`}>
            {errors.notes}
          </p>
        )}
      </div>
      {duplicate && (
        <div role="alert" className="form-error">
          <p>{duplicate.message}</p>
          {duplicate.matches.length > 0 && (
            <ul>
              {duplicate.matches.map((m) => (
                <li key={m.id}>
                  {m.full_name} — {m.has_login ? "has a login" : "no login"}, {m.status}, same {m.matched_on.join(" and ")}
                </li>
              ))}
            </ul>
          )}
          {duplicate.hidden_matches > 0 && <p>{duplicate.hidden_matches} more you can&apos;t view.</p>}
          <button type="button" className="btn small" onClick={() => void save(true)} disabled={busy}>
            Save anyway
          </button>{" "}
          <button type="button" className="btn secondary small" onClick={() => setDuplicate(null)}>
            Go back
          </button>
        </div>
      )}
      {failure && (
        <p className="form-error" role="alert">
          {failure}
        </p>
      )}
      {/* While the duplicate warning is open its own buttons are the next step (browser QA-08). */}
      <button id={`${idPrefix}-save`} type="submit" className="btn small" disabled={busy || duplicate !== null}>
        {busy ? "Saving…" : mode === "create" ? "Save student" : "Save changes"}
      </button>{" "}
      <button type="button" className="btn secondary small" onClick={cancel} disabled={busy}>
        Cancel
      </button>
    </form>
  );
}
