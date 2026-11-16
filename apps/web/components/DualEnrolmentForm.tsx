"use client";

import { useEffect, useRef, useState } from "react";
import { detailMessage, sendJson } from "@/lib/apiErrors";
import {
  counselorPickerApi, DIVISION_LABEL, dualEnrolmentApi, OTHER_DIVISION, type DualEnrolled, type DualLookup, type StudentDivision,
} from "@/lib/dualEnrolment";

type Option = { id: string; label: string };

// ENH-033 (DEC-SCOPE-441): a counselor or telecaller of `division` adds it to an existing student of the other division (D1, D4) --
// find by email or Student ID, pick a `division` counselor (D2), confirm the student asked (D5). Access only (D6).
export default function DualEnrolmentForm({ division }: { division: StudentDivision }) {
  const label = DIVISION_LABEL[division];
  const from = DIVISION_LABEL[OTHER_DIVISION[division]];
  const [ref, setRef] = useState("");
  const [student, setStudent] = useState<DualLookup | null>(null);
  const [counselors, setCounselors] = useState<Option[] | null>(null);
  const [counselorId, setCounselorId] = useState("");
  const [asked, setAsked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const sending = useRef(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${counselorPickerApi(division)}?limit=50`)
      .then((res) => (res.ok ? res.json() : null))
      .then((page: { items: Option[] } | null) => !cancelled && setCounselors(page?.items ?? []))
      .catch(() => !cancelled && setCounselors([]));
    return () => {
      cancelled = true;
    };
  }, [division]);

  async function find(e: React.FormEvent) {
    e.preventDefault();
    if (!ref.trim() || busy) return;
    setBusy(true);
    setMessage(null);
    setStudent(null);
    const response = await fetch(`${dualEnrolmentApi(division)}/lookup?ref=${encodeURIComponent(ref.trim())}`).catch(() => null);
    setBusy(false);
    if (!response?.ok) {
      const detail = response ? (await response.json().catch(() => null))?.detail : null;
      setMessage({ text: detailMessage(detail, "The search did not complete. Try again."), failed: true });
      return;
    }
    setStudent(await response.json());
    setAsked(false);
  }

  async function enrol(e: React.FormEvent) {
    e.preventDefault();
    if (!student || sending.current) return;
    if (!counselorId) return setMessage({ text: `Pick a ${label} counselor.`, failed: true });
    if (!asked) return setMessage({ text: "Confirm the student asked to enrol.", failed: true });
    sending.current = true;
    setBusy(true);
    setMessage(null);
    const saved = await sendJson(dualEnrolmentApi(division), "POST", { student_id: student.id, counselor_id: counselorId, student_requested: true });
    sending.current = false;
    setBusy(false);
    if (!saved.ok) return setMessage({ text: saved.message, failed: true });
    const done = saved.data as unknown as DualEnrolled;
    setMessage({ text: `${student.full_name} is now enrolled in ${label} with ${done.counselor_name} as counselor. They have been notified.`, failed: false });
    setStudent(null);
    setRef("");
    setCounselorId("");
    setAsked(false);
  }

  const already = student?.divisions.includes(division);
  return (
    <section className="card" style={{ display: "grid", gap: 16, maxWidth: 640 }}>
      <form onSubmit={find} style={{ display: "grid", gap: 8 }} role="search" aria-label={`Find a ${from} student`}>
        <label htmlFor="dual-ref">{from} student&apos;s email or Student ID</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input id="dual-ref" className="input" value={ref} maxLength={320} autoComplete="off" onChange={(e) => setRef(e.target.value)} style={{ flex: "1 1 220px" }} />
          <button className="btn secondary" type="submit" disabled={busy || !ref.trim()}>Find student</button>
        </div>
      </form>

      {student && (
        <form onSubmit={enrol} style={{ display: "grid", gap: 12 }} aria-label={`Enrol in ${label}`}>
          <div>
            <strong>{student.full_name}</strong>
            <div className="muted">Student ID: {student.student_code ?? "—"} · Enrolled in: {student.divisions.map((d) => DIVISION_LABEL[d]).join(", ")}</div>
          </div>
          {already ? (
            <p className="muted">This student is already enrolled in {label}.</p>
          ) : (
            <>
              <label htmlFor="dual-counselor">{label} counselor</label>
              <select id="dual-counselor" className="input" value={counselorId} onChange={(e) => setCounselorId(e.target.value)} required>
                <option value="">{counselors === null ? "Loading counselors…" : counselors.length ? "Choose a counselor" : "No active counselors"}</option>
                {(counselors ?? []).map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
              </select>
              <label style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                <input type="checkbox" checked={asked} onChange={(e) => setAsked(e.target.checked)} />
                <span>The student has asked to enrol in {label}. They keep their {from} enrolment and use the same login.</span>
              </label>
              <div>
                <button className="btn" type="submit" disabled={busy}>Enrol in {label}</button>
              </div>
            </>
          )}
        </form>
      )}

      {message && <p role={message.failed ? "alert" : "status"} className={message.failed ? "error" : "notice"}>{message.text}</p>}
    </section>
  );
}
