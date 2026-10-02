"use client";

import { FormEvent, useRef, useState } from "react";
import { sendJson } from "@/lib/apiErrors";
import { AgentApplicationDetail, APPLICATIONS_URL, todayIso } from "@/lib/agentApplications";
import { useUniversityCourses } from "@/lib/universityCourses";

type Props = {
  detail: AgentApplicationDetail;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
  onCancel: () => void;
};
const FIELDS = [
  ["application_reference", "Application ID", "text", 140],
  ["intake", "Intake (required)", "text", 80],
  ["submitted_on", "Submitted on", "date", 0],
  ["application_deadline", "Application deadline", "date", 0],
  ["offer_deadline", "Offer deadline", "date", 0],
  ["next_action", "Next action", "text", 500],
] as const;
type Key = (typeof FIELDS)[number][0] | "course_id";

// AGN-008 A10: everything but the university is editable; only changed fields are sent (null clears).
export default function AgentApplicationEditForm({ detail, onSaved, onFailed, onCancel }: Props) {
  const initial = Object.fromEntries([...FIELDS.map(([k]) => [k, (detail[k] as string | null) ?? ""]), ["course_id", detail.course_id ?? ""]]) as Record<Key, string>;
  const [values, setValues] = useState(initial);
  const courses = useUniversityCourses(detail.university_slug);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false); // QA8-06: a same-tick second submit sends nothing

  async function submit(event: FormEvent) {
    event.preventDefault();
    const changed = Object.fromEntries(
      (Object.keys(values) as Key[]).filter((k) => values[k].trim() !== initial[k]).map((k) => [k, values[k].trim() || null]),
    );
    if (!Object.keys(changed).length) return onCancel();
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = await sendJson(`${APPLICATIONS_URL}/${detail.id}`, "PATCH", changed);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok) return onFailed(outcome.message, outcome.status);
    const next = (outcome.data as { application?: AgentApplicationDetail }).application;
    if (!next) return onFailed("The change could not be confirmed. Reload to see the application.");
    onSaved(next, "Saved.");
  }

  return (
    <form className="form" onSubmit={submit} aria-label="Edit application">
      <p className="muted">University: {detail.university}. To change university, withdraw and create a new application.</p>
      <div className="field">
        <label htmlFor={`edit-course-${detail.id}`}>Course (optional)</label>
        <select id={`edit-course-${detail.id}`} value={values.course_id} disabled={courses === null} onChange={(e) => setValues({ ...values, course_id: e.target.value })}>
          <option value="">Undecided / any course</option>
          {(courses ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.title} ({c.level})
            </option>
          ))}
        </select>
      </div>
      {FIELDS.map(([key, label, type, max]) => (
        <div className="field" key={key}>
          <label htmlFor={`edit-${key}-${detail.id}`}>{label}</label>
          <input
            id={`edit-${key}-${detail.id}`}
            type={type}
            value={values[key]}
            required={key === "intake"}
            maxLength={max || undefined}
            max={key === "submitted_on" ? todayIso() : undefined}
            onChange={(e) => setValues({ ...values, [key]: e.target.value })}
          />
        </div>
      ))}
      <div className="actions">
        <button className="btn small" disabled={busy}>
          {busy ? "Saving…" : "Save"}
        </button>
        <button type="button" className="btn ghost small" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}
