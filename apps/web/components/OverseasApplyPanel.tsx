"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { Country, University } from "@/lib/types";
import ApplicationStatusHistory from "@/components/ApplicationStatusHistory";
import IntakePicker, { intakeProblem } from "@/components/IntakePicker";

type Course = { id: string; title: string; level: string; category: string; duration: string; tuition_fee: string; intake: string };
type ApplicationRow = { id: string; university: string; reference: string | null; intake: string; status: string; next_action: string | null };

function detailMessage(status: number, detail: unknown, onBehalf: boolean) {
  if (status === 409 && onBehalf) return "This student already has an open application for this university and course.";
  if (status === 409) return "You already have an application for this university/course.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit the application.";
}

// OVS-002: submitting interest previously meant typing a raw university/course UUID
// into a generic form (same class of gap already fixed for ADM-001/002/003/004/006/007).
// This lists real universities (public catalogue, OVS-001) and their real courses instead.
// nehn-034 (DEC-SCOPE-286 C6): the form starts with a country choice that narrows the universities. "All countries" (the default)
// keeps the full list; ?country=<slug> (a portal country card's Apply) preselects one. A failed country read leaves just "All countries".
// ccrm-046 (DEC-SCOPE-324): with `studentId` the counselor applies for that student from the 360 -- the student's own list is not read
// (the 360 lists the applications) and a refresh shows the new row there; the form stays for the next university or course.
export default function OverseasApplyPanel({ studentId }: { studentId?: string } = {}) {
  const router = useRouter();
  const params = useSearchParams();
  const countrySlug = params.get("country");
  const universitySlug = params.get("university"); // nehn-035 (DEC-SCOPE-331 L9): a university card's Apply preselects it and its country
  const [universities, setUniversities] = useState<University[] | null>(null);
  const [countries, setCountries] = useState<Country[]>([]);
  const [countryId, setCountryId] = useState("");
  const [applications, setApplications] = useState<ApplicationRow[] | null>(studentId ? [] : null);
  const [universityId, setUniversityId] = useState("");
  const [courses, setCourses] = useState<Course[] | null>(null);
  const [courseId, setCourseId] = useState("");
  const [intake, setIntake] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const [openHistoryId, setOpenHistoryId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/public/universities")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: University[]) => {
        if (cancelled) return;
        setUniversities(data);
        const chosen = data.find((u) => u.slug === universitySlug);
        if (chosen) {
          setUniversityId(chosen.id);
          setCountryId(chosen.country_id);
        }
      })
      .catch(() => !cancelled && setUniversities([]));
    if (!studentId) {
      fetch("/api/v1/portal/overseas/student/applications")
        .then((res) => (res.ok ? res.json() : { rows: [] }))
        .then((data) => !cancelled && setApplications(data.rows || []))
        .catch(() => !cancelled && setApplications([]));
    }
    fetch("/api/v1/public/countries")
      .then((res) => (res.ok ? res.json() : []))
      .then((data: Country[]) => {
        if (cancelled) return;
        const offered = data.filter((c) => (c.university_count ?? 0) > 0);
        setCountries(offered);
        setCountryId((current) => offered.find((c) => c.slug === countrySlug)?.id ?? current);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [countrySlug, universitySlug, studentId]);

  function chooseCountry(id: string) {
    setCountryId(id);
    if (id && universities?.find((u) => u.id === universityId)?.country_id !== id) setUniversityId("");
  }

  useEffect(() => {
    setCourseId("");
    if (!universityId) {
      setCourses(null);
      return;
    }
    const university = universities?.find((u) => u.id === universityId);
    if (!university) return;
    let cancelled = false;
    fetch(`/api/v1/public/universities/${university.slug}`)
      .then((res) => (res.ok ? res.json() : { courses: [] }))
      .then((data) => !cancelled && setCourses(data.courses || []))
      .catch(() => !cancelled && setCourses([]));
    return () => {
      cancelled = true;
    };
  }, [universityId, universities]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // ccrm-047: the intake is a month and a year; the server refuses any other shape
    const intakeError = intake ? intakeProblem(intake) : "Choose the intake month and year.";
    if (intakeError) return setMessage({ text: intakeError, failed: true });
    setBusy(true);
    setMessage(null);
    const response = await fetch("/api/v1/workflows/overseas/applications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...(studentId && { student_id: studentId }),
        university_id: universityId,
        course_id: courseId || null,
        intake,
      }),
    }).catch(() => null); // ccrm-046 QA-01: a network failure must not leave the form stuck on "Creating…"
    const data = response ? await response.json().catch(() => ({})) : {};
    setBusy(false);
    if (!response?.ok) {
      setMessage({ text: detailMessage(response?.status ?? 0, data.detail, Boolean(studentId)), failed: true });
      return;
    }
    setMessage({ text: studentId ? "Application created. It is listed below." : "Application submitted -- track its status below.", failed: false });
    setUniversityId("");
    setCourses(null);
    router.refresh();
    if (studentId) return;
    fetch("/api/v1/portal/overseas/student/applications")
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => setApplications(data.rows || []));
  }

  if (universities === null || applications === null) {
    return (
      <div className="action-card">
        <h3>Apply to a University</h3>
        <p className="muted">Loading universities…</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Apply to a University</h3>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="apply-country">Country</label>
          <select id="apply-country" value={countryId} onChange={(event) => chooseCountry(event.target.value)}>
            <option value="">All countries</option>
            {countries.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="apply-university">University</label>
          <select id="apply-university" value={universityId} onChange={(event) => setUniversityId(event.target.value)} required>
            <option value="">Select a university…</option>
            {universities.filter((u) => !countryId || u.country_id === countryId).map((u) => (
              <option key={u.id} value={u.id}>{u.name} -- {u.city}</option>
            ))}
          </select>
        </div>
        {universityId && (
          <div className="field">
            <label htmlFor="apply-course">Course (optional)</label>
            <select id="apply-course" value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={courses === null}>
              <option value="">Undecided / any course</option>
              {(courses || []).map((c) => (
                <option key={c.id} value={c.id}>{c.title} ({c.level})</option>
              ))}
            </select>
          </div>
        )}
        <IntakePicker id="apply-intake" label="Intake" value={intake} onChange={setIntake} disabled={busy} required />
        <button className="btn small" disabled={busy || !universityId}>
          {studentId ? (busy ? "Creating…" : "Create application") : busy ? "Submitting…" : "Submit interest"}
        </button>
      </form>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
      {!studentId && (
        <>
          <h4 style={{ marginTop: 24 }}>Your applications</h4>
          {applications.length === 0 ? (
            <p className="muted">You have not applied to any university yet.</p>
          ) : (
            <div className="grid two">
              {applications.map((a) => (
                <div className="card" key={a.id}>
                  <span className="badge">{a.status}</span>
                  <h4 style={{ marginTop: 10 }}>{a.university}</h4>
                  <p className="muted" style={{ fontSize: 13 }}>{a.intake}</p>
                  {a.next_action && <p className="muted" style={{ fontSize: 13 }}>{a.next_action}</p>}
                  <button className="btn small" aria-expanded={openHistoryId === a.id} onClick={() => setOpenHistoryId(openHistoryId === a.id ? null : a.id)}>
                    {openHistoryId === a.id ? "Hide status history" : "View status history"}
                  </button>
                  {/* ccrm-016: stage, sub-status, outcome and time -- the server leaves out author, notes and reason for a student (H2) */}
                  {openHistoryId === a.id && <ApplicationStatusHistory applicationId={a.id} />}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
