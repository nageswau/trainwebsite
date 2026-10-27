"use client";

import { FormEvent, useEffect, useState } from "react";
import type { StudentAccessRules } from "@/lib/studentAccess";

const RULES = "/api/v1/workflows/it/student-access/rules";

function detailMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return fallback;
}

// nehn-018 (DEC-SCOPE-304 AC4): the IT admin sets, per student feature, the lowest payment state that unlocks it (`student_access.configure`).
// The change applies to every student's next page or request; course information, fees and payment are never locked.
export default function AdminStudentAccessPanel() {
  const [policy, setPolicy] = useState<StudentAccessRules | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(RULES)
      .then(async (response) => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !Array.isArray(data.rules)) throw new Error(detailMessage(data.detail, "The student access rules could not be loaded."));
        setPolicy(data);
      })
      .catch((error: Error) => {
        setFailed(true);
        setMessage(error.message || "The student access rules could not be loaded.");
      });
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!policy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage("");
    setFailed(false);
    const rules = Object.fromEntries(policy.rules.map((rule) => [rule.feature, String(form.get(rule.feature))]));
    const response = await fetch(RULES, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rules }) }).catch(() => null);
    const data = await response?.json().catch(() => ({}));
    setBusy(false);
    if (!response?.ok) {
      setFailed(true);
      setMessage(detailMessage(data?.detail, "The student access rules could not be saved."));
      return;
    }
    setPolicy(data);
    setMessage("Access rules saved. Students see the change on their next page.");
  }

  return (
    <div className="action-card">
      <h3>Student access by payment</h3>
      <p className="muted">Choose when each feature opens for an IT student. Course information, fees and payment are always available.</p>
      {!policy && !failed && <p className="muted">Loading the student access rules…</p>}
      {policy && (
        <form className="form" onSubmit={save} key={policy.rules.map((rule) => rule.min_state).join()}>
          {policy.rules.map((rule) => (
            <div className="field" key={rule.feature}>
              <label htmlFor={`access-${rule.feature}`}>{rule.label}</label>
              <select id={`access-${rule.feature}`} name={rule.feature} defaultValue={rule.min_state}>
                {policy.states.map((state) => <option key={state.key} value={state.key}>{state.label}</option>)}
              </select>
            </div>
          ))}
          <button className="btn small" disabled={busy}>{busy ? "Saving…" : "Save access rules"}</button>
        </form>
      )}
      {message && <div className={failed ? "form-error" : "form-message"} role={failed ? "alert" : "status"} aria-live="polite">{message}</div>}
    </div>
  );
}
