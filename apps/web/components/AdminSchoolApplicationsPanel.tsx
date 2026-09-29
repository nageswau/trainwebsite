"use client";

import { FormEvent, useEffect, useState } from "react";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import SearchableSelect from "@/components/SearchableSelect";
import { sendJson } from "@/lib/apiErrors";
import { lookupSearch, type PickOption } from "@/lib/lookups";

type UniversityOption = { id: string; name: string; city: string };
type BridgedApplication = { id: string; student_name: string; student_code: string; university_name: string; status: string; created_at: string };

// DEC-SCOPE-018 (2026-09-15): Overseas Admin/Counselor links a School-affiliated student
// to a real Overseas application -- never school_coordinator, per direct decision.
// ENH-031 (DEC-SCOPE-037 D4): pick the school first, then search only that school's students by name or Student ID -- no cross-school name browsing.
export default function AdminSchoolApplicationsPanel() {
  const [universities, setUniversities] = useState<UniversityOption[]>([]);
  const [applications, setApplications] = useState<BridgedApplication[] | null>(null);
  const [school, setSchool] = useState<PickOption | null>(null);
  const [student, setStudent] = useState<PickOption | null>(null);
  // Bumped after a successful start so both pickers remount empty.
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<FormMessageState | null>(null);

  function loadApplications() {
    fetch("/api/v1/overseas-admin/school-applications")
      .then((res) => (res.ok ? res.json() : []))
      .then(setApplications)
      .catch(() => setApplications([]));
  }

  useEffect(() => {
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: UniversityOption[]) => setUniversities(data))
      .catch(() => setUniversities([]));
    loadApplications();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!student) {
      setMessage({ text: "Choose a school, then a student, first.", failed: true });
      return;
    }
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setMessage(null);
    const result = await sendJson(`/api/v1/overseas-admin/school-students/${student.id}/applications`, "POST", { university_id: form.get("university_id"), intake: form.get("intake") });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true });
      return;
    }
    setMessage({ text: `Application started for ${student.label}.`, failed: false });
    setSchool(null);
    setStudent(null);
    setVersion((v) => v + 1);
    loadApplications();
  }

  return (
    <div className="action-card">
      <h3>Start an Overseas application for a School student</h3>
      <SearchableSelect
        key={`school-${version}`}
        id="bridge-school"
        label="School"
        noun="school"
        search={lookupSearch("schools")}
        onChange={(option) => {
          setSchool(option);
          setStudent(null);
          setMessage(null);
        }}
      />
      {school && (
        <SearchableSelect
          key={`student-${school.id}-${version}`}
          id="bridge-student"
          label="Student"
          noun="student"
          search={lookupSearch("school-students", { school_id: school.id })}
          onChange={(option) => {
            setStudent(option);
            setMessage(null);
          }}
        />
      )}
      {student && (
        <form className="form" onSubmit={submit}>
          <div className="field">
            <label htmlFor="bridge-university">University</label>
            <select id="bridge-university" name="university_id" required defaultValue="">
              <option value="" disabled>Select university</option>
              {universities.map((u) => (
                <option key={u.id} value={u.id}>{u.name} ({u.city})</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="bridge-intake">Intake</label>
            <input id="bridge-intake" name="intake" required placeholder="e.g. Fall 2027" />
          </div>
          <button className="btn" disabled={busy}>{busy ? "Starting…" : "Start application"}</button>
        </form>
      )}
      {message && <FormMessage message={message} />}
      <div className="table-wrap" style={{ marginTop: 16 }}>
        <h4>Linked applications</h4>
        {!applications || applications.length === 0 ? (
          <p className="muted">No School-linked applications yet.</p>
        ) : (
          <table className="table">
            <thead>
              <tr><th>Student</th><th>Student ID</th><th>University</th><th>Status</th></tr>
            </thead>
            <tbody>
              {applications.map((a) => (
                <tr key={a.id}><td>{a.student_name}</td><td><code>{a.student_code}</code></td><td>{a.university_name}</td><td>{a.status}</td></tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
