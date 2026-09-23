"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import FormMessage, { type FormMessageState } from "@/components/FormMessage";
import { sendJson } from "@/lib/apiErrors";

type Student = { id: string; full_name: string; school_name: string };
type TestPrepRecord = { id: string; school_student_id: string; test_type: string; mock_scores: string[]; target_score: string | null; actual_score: string | null; status: string };
type LanguageRecord = { id: string; school_student_id: string; language: string; level: string | null; classes_attended: number; assessment_score: string | null; certification_status: string };
// ENH-022: the card whose control produced the message, so it renders beside that control.
type MessageCard = "scores" | "testprep" | "certify" | "language";

// SCH-009 (DEC-SCOPE-018): Test Preparation (IELTS/SAT) and Foreign Language Classes,
// delivered by the same Academic Team role that already owns Academic Results -- the user
// explicitly chose to reuse this role rather than create a new one.
export default function SchoolTestPrepLanguagePanel({ testPrepRecords, languageRecords, students }: { testPrepRecords: TestPrepRecord[]; languageRecords: LanguageRecord[]; students: Student[] }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<(FormMessageState & { card: MessageCard }) | null>(null);
  const [scoreDrafts, setScoreDrafts] = useState<Record<string, string>>({});

  function studentName(id: string) {
    return students.find((s) => s.id === id)?.full_name || "Unknown student";
  }

  async function createTestPrep(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const result = await sendJson("/api/v1/school/academic-team/test-prep-records", "POST", { school_student_id: form.get("school_student_id"), test_type: form.get("test_type"), target_score: form.get("target_score") || undefined });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, card: "testprep" });
      return;
    }
    setMessage({ text: `${String(form.get("test_type")).toUpperCase()} preparation started.`, failed: false, card: "testprep" });
    formElement.reset();
    router.refresh();
  }

  async function recordActualScore(recordId: string) {
    const actualScore = scoreDrafts[recordId]?.trim();
    if (!actualScore) return;
    setBusy(true);
    setMessage(null);
    const result = await sendJson(`/api/v1/school/academic-team/test-prep-records/${recordId}`, "PATCH", { actual_score: actualScore });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, card: "scores" });
      return;
    }
    setMessage({ text: "Result recorded.", failed: false, card: "scores" });
    router.refresh();
  }

  async function createLanguageRecord(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const result = await sendJson("/api/v1/school/academic-team/language-records", "POST", { school_student_id: form.get("school_student_id"), language: form.get("language"), level: form.get("level") || undefined });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, card: "language" });
      return;
    }
    setMessage({ text: `${result.data.language} classes started.`, failed: false, card: "language" });
    formElement.reset();
    router.refresh();
  }

  async function markCertified(recordId: string) {
    setBusy(true);
    setMessage(null);
    const result = await sendJson(`/api/v1/school/academic-team/language-records/${recordId}`, "PATCH", { certification_status: "certified" });
    setBusy(false);
    if (!result.ok) {
      setMessage({ text: result.message, failed: true, card: "certify" });
      return;
    }
    setMessage({ text: "Marked certified.", failed: false, card: "certify" });
    router.refresh();
  }

  return (
    <div className="portal-content">
      <div className="card">
        <h2>Test preparation</h2>
        {testPrepRecords.length === 0 ? (
          <p className="muted">No test preparation started yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Test</th><th>Target</th><th>Actual</th><th>Status</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {testPrepRecords.map((r) => (
                  <tr key={r.id}>
                    <td>{studentName(r.school_student_id)}</td>
                    <td>{r.test_type.toUpperCase()}</td>
                    <td>{r.target_score || "-"}</td>
                    <td>{r.actual_score || "-"}</td>
                    <td>{r.status}</td>
                    <td>
                      {r.status === "completed" ? (
                        <span className="muted" style={{ fontSize: 13 }}>-</span>
                      ) : (
                        <div style={{ display: "flex", gap: 6 }}>
                          <input
                            aria-label={`Actual score for ${studentName(r.school_student_id)}`}
                            style={{ width: 90 }}
                            value={scoreDrafts[r.id] || ""}
                            onChange={(e) => setScoreDrafts((current) => ({ ...current, [r.id]: e.target.value }))}
                          />
                          <button className="btn ghost small" disabled={busy} onClick={() => recordActualScore(r.id)}>Record score</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {message?.card === "scores" && <FormMessage message={message} style={{ marginTop: 12 }} />}
      </div>

      <div className="action-card">
        <h3>Start test preparation</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <form className="form" onSubmit={createTestPrep}>
            <div className="field">
              <label htmlFor="testprep-student">Student</label>
              <select id="testprep-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="testprep-type">Test</label>
              <select id="testprep-type" name="test_type" required defaultValue="">
                <option value="" disabled>Select test</option>
                <option value="ielts">IELTS</option>
                <option value="sat">SAT</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="testprep-target">Target score</label>
              <input id="testprep-target" name="target_score" placeholder="Optional" />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Starting…" : "Start preparation"}</button>
          </form>
        )}
        {message?.card === "testprep" && <FormMessage message={message} />}
      </div>

      <div className="card">
        <h2>Foreign language classes</h2>
        {languageRecords.length === 0 ? (
          <p className="muted">No language classes started yet.</p>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Student</th><th>Language</th><th>Level</th><th>Classes attended</th><th>Certification</th><th>Actions</th></tr>
              </thead>
              <tbody>
                {languageRecords.map((r) => (
                  <tr key={r.id}>
                    <td>{studentName(r.school_student_id)}</td>
                    <td>{r.language}</td>
                    <td>{r.level || "-"}</td>
                    <td>{r.classes_attended}</td>
                    <td>{r.certification_status}</td>
                    <td>
                      {r.certification_status === "certified" ? (
                        <span className="muted" style={{ fontSize: 13 }}>-</span>
                      ) : (
                        <button className="btn ghost small" disabled={busy} onClick={() => markCertified(r.id)}>Mark certified</button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {message?.card === "certify" && <FormMessage message={message} style={{ marginTop: 12 }} />}
      </div>

      <div className="action-card">
        <h3>Start language classes</h3>
        {students.length === 0 ? (
          <p className="muted">No students in your portfolio yet. Contact your Overseas Admin.</p>
        ) : (
          <form className="form" onSubmit={createLanguageRecord}>
            <div className="field">
              <label htmlFor="language-student">Student</label>
              <select id="language-student" name="school_student_id" required defaultValue="">
                <option value="" disabled>Select student</option>
                {students.map((s) => (
                  <option key={s.id} value={s.id}>{s.full_name} — {s.school_name}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="language-name">Language</label>
              <input id="language-name" name="language" required />
            </div>
            <div className="field">
              <label htmlFor="language-level">Level</label>
              <input id="language-level" name="level" placeholder="Optional" />
            </div>
            <button className="btn" disabled={busy}>{busy ? "Starting…" : "Start classes"}</button>
          </form>
        )}
        {message?.card === "language" && <FormMessage message={message} />}
      </div>
    </div>
  );
}
