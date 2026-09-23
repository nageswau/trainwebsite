"use client";

import { FormEvent, useState } from "react";
import { detailMessage, interestValue, listText, splitList } from "@/lib/schoolStudents";

type Prefs = { student_id: string; career_interests: string[] | null; global_education_interest: boolean | null; preferred_countries: string[] | null; preferred_courses: string[] | null };
type Student = { id: string; full_name: string; school_name: string };

const LISTS = [
  ["career_interests", "Career interests"],
  ["preferred_countries", "Preferred countries"],
  ["preferred_courses", "Preferred courses"],
] as const;

// ENH-025 (DEC-SCOPE-027 item 2): a Career Counsellor records a portfolio student's career interests and study-abroad
// preferences. Only these four fields are ever sent; the server rejects anything else.
export default function CareerPreferencesCard({ students }: { students: Student[] }) {
  const [studentId, setStudentId] = useState("");
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error" | "saving">("idle");
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  async function load(id: string) {
    setState("loading");
    setPrefs(null);
    setMessage(null);
    const response = await fetch(`/api/v1/school/students/${id}/career-preferences`).catch(() => null);
    if (!response?.ok) {
      setState("error");
      return;
    }
    setPrefs(await response.json());
    setState("idle");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = {
      career_interests: splitList(form.get("career_interests")),
      preferred_countries: splitList(form.get("preferred_countries")),
      preferred_courses: splitList(form.get("preferred_courses")),
      global_education_interest: interestValue(form.get("global_education_interest")),
    };
    setState("saving");
    setMessage(null);
    const response = await fetch(`/api/v1/school/students/${studentId}/career-preferences`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    const data = response ? await response.json().catch(() => ({})) : {};
    setState("idle");
    if (!response?.ok) {
      setMessage({ text: detailMessage(data.detail, "Could not save; please try again."), failed: true });
      return;
    }
    setPrefs(data);
    setMessage({ text: "Career preferences saved.", failed: false });
  }

  return (
    <div className="action-card">
      <h3>Career preferences</h3>
      {students.length === 0 ? (
        <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
      ) : (
        <>
          <div className="field">
            <label htmlFor="prefs-student">Student</label>
            <select
              id="prefs-student"
              value={studentId}
              onChange={(e) => {
                setStudentId(e.target.value);
                if (e.target.value) load(e.target.value);
              }}
            >
              <option value="" disabled>Select student</option>
              {students.map((s) => <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>)}
            </select>
          </div>
          {state === "loading" && <p className="muted" aria-busy="true" aria-live="polite">Loading…</p>}
          {state === "error" && (
            <div className="form-error" role="alert">
              Could not load this student&apos;s preferences.{" "}
              <button type="button" className="btn ghost small" onClick={() => load(studentId)}>Retry</button>
            </div>
          )}
          {prefs && (
            // key: switching student remounts the form so every defaultValue is that student's.
            <form className="form" key={prefs.student_id} aria-busy={state === "saving"} onSubmit={save}>
              <fieldset className="form-busy-wrap" disabled={state === "saving"}>
                <p id="prefs-help" className="muted field-help">Separate multiple values with commas.</p>
                {LISTS.map(([name, label]) => (
                  <div className="field" key={name}>
                    <label htmlFor={`prefs-${name}`}>{label}</label>
                    <input id={`prefs-${name}`} name={name} defaultValue={listText(prefs[name])} aria-describedby="prefs-help" />
                  </div>
                ))}
                <div className="field">
                  <label htmlFor="prefs-global">Interested in studying abroad</label>
                  <select id="prefs-global" name="global_education_interest" defaultValue={prefs.global_education_interest == null ? "" : prefs.global_education_interest ? "yes" : "no"}>
                    <option value="">Not recorded</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                  </select>
                </div>
                <button className="btn">{state === "saving" ? "Saving…" : "Save preferences"}</button>
              </fieldset>
            </form>
          )}
          {message && (message.failed ? <div className="form-error" role="alert">{message.text}</div> : <div className="form-message" role="status" aria-live="polite">{message.text}</div>)}
        </>
      )}
    </div>
  );
}
