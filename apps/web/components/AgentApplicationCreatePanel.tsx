"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import SearchableSelect from "@/components/SearchableSelect";
import { isPage, sendJson } from "@/lib/apiErrors";
import { APPLICATIONS_URL, todayIso } from "@/lib/agentApplications";
import { AgentStudentItem, RECORDS_URL } from "@/lib/agentStudents";
import type { LookupPage } from "@/lib/lookups";
import type { University } from "@/lib/types";
import { useUniversityCourses } from "@/lib/universityCourses";

// AGN-008 (DEC-SCOPE-050): create an application for any of the agency's students -- with or without a login -- searched on the
// server (AGN-004's records list), so a large agency is never truncated. University/course reuse OVS-002's cascading picker. Ids,
// the "Linked student" name and the success text are kept for ENH-031's specs.
async function searchStudents(q: string, signal: AbortSignal): Promise<LookupPage> {
  const params = new URLSearchParams({ limit: "20" });
  if (q) params.set("q", q);
  const response = await fetch(`${RECORDS_URL}?${params}`, { signal });
  const data = await response.json().catch(() => null);
  if (!response.ok || !isPage<AgentStudentItem>(data)) throw new Error(`Student search failed (${response.status})`);
  return {
    items: data.items.map((s) => ({ id: s.id, label: s.full_name, detail: s.has_login ? s.email : "no login" })),
    truncated: data.total > data.items.length,
  };
}

const OPTIONAL = [
  ["application_reference", "Application ID", "text"],
  ["submitted_on", "Submitted on", "date"],
  ["application_deadline", "Application deadline", "date"],
  ["offer_deadline", "Offer deadline", "date"],
] as const;

export default function AgentApplicationCreatePanel({ onCreated }: { onCreated?: () => void }) {
  const [universities, setUniversities] = useState<University[] | null>(null);
  const [studentId, setStudentId] = useState("");
  const [universityId, setUniversityId] = useState("");
  const courses = useUniversityCourses(universities?.find((u) => u.id === universityId)?.slug ?? null);
  const [courseId, setCourseId] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [formVersion, setFormVersion] = useState(0); // ENH-031: bumped after a create so the picker remounts empty
  const messageRef = useRef<HTMLDivElement>(null);
  const inFlight = useRef(false); // QA8-06: a same-tick second submit sends nothing

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: University[]) => !cancelled && setUniversities(data))
      .catch(() => !cancelled && setUniversities([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => setCourseId(""), [universityId, universities]);

  useEffect(() => {
    if (message) messageRef.current?.focus();
  }, [message]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const optional = Object.fromEntries(OPTIONAL.map(([key]) => [key, String(form.get(key) ?? "").trim() || null]));
    setBusy(true);
    setMessage(null);
    let outcome: Awaited<ReturnType<typeof sendJson>>;
    try {
      outcome = await sendJson(APPLICATIONS_URL, "POST", {
        agent_student_id: studentId,
        university_id: universityId,
        course_id: courseId || null,
        intake: String(form.get("intake") ?? "").trim(),
        ...optional,
      });
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
    if (!outcome.ok) return setMessage({ text: outcome.message, failed: true });
    setMessage({ text: "Application created.", failed: false });
    formElement.reset();
    setStudentId("");
    setFormVersion((v) => v + 1);
    setUniversityId("");
    onCreated?.();
  }

  if (universities === null) {
    return (
      <div className="action-card">
        <h3>Create application</h3>
        <p className="muted">Loading universities…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Create application</h3>
      {/* QA8-12: a blocked submit or an edit after an error drops the stale server message. */}
      <form className="form" onSubmit={submit} aria-label="Create application" onInvalidCapture={() => setMessage(null)} onChange={() => message?.failed && setMessage(null)}>
        <SearchableSelect key={formVersion} id="agent-app-student" label="Linked student" required noun="student" search={searchStudents} onChange={(option) => setStudentId(option?.id ?? "")} />
        <div className="field">
          <label htmlFor="agent-app-university">University (required)</label>
          <select id="agent-app-university" value={universityId} onChange={(event) => setUniversityId(event.target.value)} required>
            <option value="">Select university</option>
            {universities.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} -- {u.city}
              </option>
            ))}
          </select>
        </div>
        {universityId && (
          <div className="field">
            <label htmlFor="agent-app-course">Course (optional)</label>
            <select id="agent-app-course" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={courses === null}>
              <option value="">Undecided / any course</option>
              {(courses || []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title} ({c.level})
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="field">
          <label htmlFor="agent-app-intake">Intake (required)</label>
          <input id="agent-app-intake" name="intake" defaultValue="Next intake" maxLength={80} required />
        </div>
        {OPTIONAL.map(([key, label, type]) => (
          <div className="field" key={key}>
            <label htmlFor={`agent-app-${key}`}>{label}</label>
            <input
              id={`agent-app-${key}`}
              name={key}
              type={type}
              maxLength={type === "text" ? 140 : undefined}
              max={key === "submitted_on" ? todayIso() : undefined}
              aria-describedby={key === "submitted_on" ? "agent-app-submitted-hint" : undefined}
            />
            {key === "submitted_on" && (
              <small id="agent-app-submitted-hint" className="muted">
                Leave empty until submitted.
              </small>
            )}
          </div>
        ))}
        <button className="btn" disabled={busy || !studentId || !universityId}>
          {busy ? "Creating…" : "Create application"}
        </button>
      </form>
      {message && (
        <div ref={messageRef} tabIndex={-1} className={message.failed ? "form-error" : "form-message"} role={message.failed ? "alert" : "status"} aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
