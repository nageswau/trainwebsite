"use client";

import { FormEvent, ReactElement, ReactNode, cloneElement, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import BatchRosterPanel from "./BatchRosterPanel";
import LiveClassesPanel from "./LiveClassesPanel";
import SupportTicketQueuePanel from "./SupportTicketQueuePanel";

type Batch = { id: string; name: string; schedule: string; capacity: number };
type Student = { id: string; name: string; batch_id: string };
type Enrollment = { id: string; student_id: string; student: string; batch_id: string; batch: string; enrollment_code: string; progress_percent: number };
type Correction = { id: string; student: string; batch: string; session_date: string; current_status: string; requested_status: string; reason: string };
type Submission = { id: string; assignment: string; student: string; answer: string | null; file_url: string | null; score?: number; max_score: number; status: string };
type TrainerAssignment = {
  id: string;
  batch_id: string;
  batch: string;
  title: string;
  description: string;
  due_date: string;
  max_score: number;
  assignment_type: string;
  submission_type: string;
  published: boolean;
};
type Assessment = {
  id: string;
  title: string;
  batch: string;
  status: string;
  description: string;
  scheduled_at: string;
  duration_minutes: number;
  max_score: number;
  pass_percent: number;
  attempts_allowed: number;
  instructions: string;
  publish_results: boolean;
  attempt_count: number;
};
type Attempt = { id: string; assessment: string; student: string; status: string; max_score: number };
type AttemptAnswer = { id: string; question_id: string; prompt: string; question_type: string; max_score: number; value: string | string[] | null; auto_graded: boolean; score: number | null };
type AttemptDetail = { id: string; assessment: string; student: string; status: string; feedback: string | null; answers: AttemptAnswer[] };
type Session = { id: string; title: string; batch: string; provider: string; recording_status: string };
type QuestionReply = { id: string; author_id: string; body: string; created_at: string };
type Question = { id: string; student: string; batch: string; subject: string; body: string; replies: QuestionReply[] };
type TeacherContext = { batches: Batch[]; students: Student[]; enrollments: Enrollment[] };

const emptyContext: TeacherContext = { batches: [], students: [], enrollments: [] };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map(item => item?.msg || "Invalid input").join("; ");
  return "The operation could not be completed.";
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return <div className="action-card"><h3>{title}</h3>{children}</div>;
}

function Field({ controlId, label, full = false, children }: { controlId: string; label: string; full?: boolean; children: ReactElement<{ id?: string }> }) {
  return <div className={full ? "field full" : "field"}><label htmlFor={controlId}>{label}</label>{cloneElement(children, { id: controlId })}</div>;
}

export default function TeacherWorkspaceActions({ section }: { section: string }) {
  const router = useRouter();
  const [context, setContext] = useState<TeacherContext>(emptyContext);
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [submissions, setSubmissions] = useState<Submission[]>([]);
  const [trainerAssignments, setTrainerAssignments] = useState<TrainerAssignment[]>([]);
  const [editAssignmentId, setEditAssignmentId] = useState("");
  const [gradingSubmissionId, setGradingSubmissionId] = useState("");
  const [editAssessmentId, setEditAssessmentId] = useState("");
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [gradingAttemptId, setGradingAttemptId] = useState("");
  const [attemptDetail, setAttemptDetail] = useState<AttemptDetail | null>(null);
  const [loadingAttemptDetail, setLoadingAttemptDetail] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [certificateOverride, setCertificateOverride] = useState(false);
  const [batch, setBatch] = useState("");
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const feedbackRef = useRef<HTMLDivElement>(null);
  const students = useMemo(() => context.students.filter(student => student.batch_id === batch), [context.students, batch]);

  async function request<T>(path: string): Promise<T> {
    const response = await fetch(path);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(detailMessage(data.detail));
    return data as T;
  }

  async function load() {
    setLoading(true);
    try {
      const [nextContext, nextCorrections, nextSubmissions, nextAssignments, nextAssessments, nextAttempts, nextSessions, nextQuestions] = await Promise.all([
        request<TeacherContext>("/api/v1/workflows/it/trainer/context"),
        request<Correction[]>("/api/v1/workflows/it/trainer/attendance-corrections?status=pending"),
        request<Submission[]>("/api/v1/workflows/it/trainer/submissions"),
        request<TrainerAssignment[]>("/api/v1/workflows/it/trainer/assignments"),
        request<Assessment[]>("/api/v1/workflows/it/trainer/assessments"),
        request<Attempt[]>("/api/v1/workflows/it/trainer/assessment-attempts"),
        request<Session[]>("/api/v1/communications/it/live-sessions"),
        request<Question[]>("/api/v1/workflows/it/trainer/questions"),
      ]);
      setContext(nextContext);
      setCorrections(nextCorrections);
      setSubmissions(nextSubmissions);
      setTrainerAssignments(nextAssignments);
      setAssessments(nextAssessments);
      setAttempts(nextAttempts);
      setSessions(nextSessions);
      setQuestions(nextQuestions);
      setBatch(current => current || nextContext.batches[0]?.id || "");
    } catch (error) {
      setContext(emptyContext);
      setCorrections([]);
      setSubmissions([]);
      setTrainerAssignments([]);
      setAssessments([]);
      setAttempts([]);
      setSessions([]);
      setQuestions([]);
      setBatch("");
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Unable to load teacher actions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);
  useEffect(() => { if (failed && message) feedbackRef.current?.focus(); }, [failed, message]);
  useEffect(() => {
    if (!gradingAttemptId) { setAttemptDetail(null); return; }
    let active = true;
    setLoadingAttemptDetail(true);
    request<AttemptDetail>(`/api/v1/workflows/it/trainer/assessment-attempts/${gradingAttemptId}`)
      .then(data => { if (active) setAttemptDetail(data); })
      .catch(error => { if (active) { setAttemptDetail(null); setFailed(true); setMessage(error instanceof Error ? error.message : "Unable to load attempt"); } })
      .finally(() => { if (active) setLoadingAttemptDetail(false); });
    return () => { active = false; };
  }, [gradingAttemptId]);

  async function submit(event: FormEvent<HTMLFormElement>, path: string, method: "POST" | "PATCH", body: Record<string, unknown>, success: string) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage("");
    setFailed(false);
    try {
      const response = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail));
      setMessage(success);
      formElement.reset();
      await load();
      router.refresh();
    } catch (error) {
      setFailed(true);
      setMessage(error instanceof Error ? error.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  const feedback = message && (
    <div ref={feedbackRef} className={failed ? "form-error" : "form-message"} role={failed ? "alert" : "status"} aria-live={failed ? "assertive" : "polite"} aria-atomic="true" tabIndex={failed ? -1 : undefined}>{message}</div>
  );
  const batchOptions = context.batches.map(item => <option key={item.id} value={item.id}>{item.name} · {item.schedule}</option>);

  if (section === "dashboard") {
    return <div className="portal-content" style={{ paddingTop: 0 }}><div className="workspace"><div className="workspace-head"><div><strong>Teacher functions</strong><p>Everything available for assigned learning batches.</p></div><span className="badge">7 workspaces</span></div><div style={{ padding: "0 24px 24px" }}><BatchRosterPanel/><div style={{ marginTop: 16 }}><LiveClassesPanel title="Upcoming sessions" upcomingOnly/></div></div><div className="action-grid" style={{ padding: 24 }}>{[
      ["Attendance", "Mark a full class register and decide correction requests."],
      ["Assignments", "Create work, review submissions, score, and give feedback."],
      ["Assessments", "Schedule tests, author questions, and grade attempts."],
      ["Materials", "Publish notes, links, documents, videos, and provider recordings."],
      ["Live sessions", "Schedule Google Meet or Zoho Meeting classes and attach provider recordings."],
      ["Student progress", "Update learner progress and issue eligible certificates."],
      ["Support", "Pick up and resolve student support tickets for your division."],
    ].map(([title, description]) => <div className="action-card" key={title}><h3>{title}</h3><p className="muted">{description}</p></div>)}</div></div></div>;
  }

  let content: ReactNode = null;

  if (section === "attendance") content = <>
    <Card title="Mark attendance">
      <form className="form" aria-label="Mark attendance" onSubmit={event => {
        const form = new FormData(event.currentTarget);
        void submit(event, "/api/v1/workflows/it/trainer/attendance", "POST", { batch_id: batch, session_date: form.get("session_date"), records: students.map(student => ({ student_id: student.id, status: form.get(`status_${student.id}`), notes: form.get(`notes_${student.id}`) })) }, "Attendance saved.");
      }}>
        <Field controlId="attendance-batch" label="Batch"><select value={batch} onChange={event => setBatch(event.target.value)} required><option value="">Select batch</option>{batchOptions}</select></Field>
        <Field controlId="attendance-session-date" label="Session date"><input name="session_date" type="date" defaultValue={new Date().toISOString().slice(0, 10)} required /></Field>
        {students.length ? <div className="table-wrap"><table className="table"><thead><tr><th scope="col">Learner</th><th scope="col">Status</th><th scope="col">Notes</th></tr></thead><tbody>{students.map(student => <tr key={student.id}><th scope="row">{student.name}</th><td><select aria-label={`${student.name} status`} name={`status_${student.id}`} defaultValue="present"><option value="present">Present</option><option value="absent">Absent</option><option value="late">Late</option><option value="excused">Excused</option></select></td><td><input aria-label={`${student.name} notes`} name={`notes_${student.id}`} placeholder="Optional note" /></td></tr>)}</tbody></table></div> : <p id="attendance-empty" className="muted">{loading ? "Loading active learners…" : "No active learners in this batch."}</p>}
        <button className="btn" disabled={busy || loading || !batch || !students.length} aria-describedby={!students.length ? "attendance-empty" : undefined}>Save attendance</button>
      </form>
    </Card>
    <Card title="Review correction">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); const reference = String(form.get("correction")); void submit(event, `/api/v1/workflows/it/attendance-corrections/${reference}`, "PATCH", { status: form.get("status"), review_notes: form.get("review_notes") }, "Correction reviewed."); }}>
        <Field controlId="correction-request" label="Pending request"><select name="correction" required><option value="">Select request</option>{corrections.map(item => <option key={item.id} value={item.id}>{item.student} · {item.batch} · {item.current_status} → {item.requested_status}</option>)}</select></Field>
        <Field controlId="correction-decision" label="Decision"><select name="status" required><option value="approved">Approve</option><option value="rejected">Reject</option></select></Field>
        <Field controlId="correction-notes" label="Review notes" full><textarea name="review_notes" /></Field>
        {!corrections.length && <p id="correction-empty" className="muted">{loading ? "Loading pending requests…" : "No pending correction requests."}</p>}
        <button className="btn" disabled={busy || loading || !corrections.length} aria-describedby={!corrections.length ? "correction-empty" : undefined}>Review request</button>
      </form>
    </Card>
  </>;

  if (section === "assignments") content = <>
    <Card title="Create assignment">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); void submit(event, "/api/v1/workflows/it/trainer/assignments", "POST", { batch_id: form.get("batch"), title: form.get("title"), description: form.get("description"), due_date: form.get("due_date"), max_score: Number(form.get("max_score")), assignment_type: form.get("assignment_type") }, "Assignment created."); }}>
        <Field controlId="assignment-batch" label="Batch"><select name="batch" required><option value="">Select batch</option>{batchOptions}</select></Field>
        <Field controlId="assignment-title" label="Title"><input name="title" required /></Field>
        <Field controlId="assignment-type" label="Work type"><select name="assignment_type"><option value="assignment">Assignment</option><option value="project">Project</option></select></Field>
        <Field controlId="assignment-due" label="Due date and time"><input name="due_date" type="datetime-local" required /></Field>
        <Field controlId="assignment-maximum-score" label="Maximum score"><input name="max_score" type="number" min="1" defaultValue="100" required /></Field>
        <Field controlId="assignment-description" label="Description" full><textarea name="description" /></Field>
        <button className="btn" disabled={busy || loading}>Create assignment</button>
      </form>
    </Card>
    <Card title="Edit assignment">
      <Field controlId="assignment-edit-select" label="Assignment">
        <select value={editAssignmentId} onChange={event => setEditAssignmentId(event.target.value)}>
          <option value="">Select assignment</option>
          {trainerAssignments.map(item => <option key={item.id} value={item.id}>{item.title} · {item.batch}</option>)}
        </select>
      </Field>
      {!trainerAssignments.length && <p id="assignment-edit-empty" className="muted">{loading ? "Loading your assignments…" : "No assignments exist yet -- create one above."}</p>}
      {editAssignmentId && (() => {
        const current = trainerAssignments.find(item => item.id === editAssignmentId);
        if (!current) return null;
        return (
          <form key={editAssignmentId} className="form" onSubmit={event => {
            const form = new FormData(event.currentTarget);
            void submit(event, `/api/v1/workflows/it/trainer/assignments/${editAssignmentId}`, "PATCH", {
              title: form.get("title"),
              description: form.get("description"),
              due_date: form.get("due_date"),
              max_score: Number(form.get("max_score")),
              assignment_type: form.get("assignment_type"),
              published: form.get("published") === "on",
            }, "Assignment updated.");
          }}>
            <Field controlId="assignment-edit-title" label="Title"><input name="title" defaultValue={current.title} required /></Field>
            <Field controlId="assignment-edit-type" label="Work type"><select name="assignment_type" defaultValue={current.assignment_type}><option value="assignment">Assignment</option><option value="project">Project</option></select></Field>
            <Field controlId="assignment-edit-due" label="Due date and time"><input name="due_date" type="datetime-local" defaultValue={current.due_date.slice(0, 16)} required /></Field>
            <Field controlId="assignment-edit-maximum-score" label="Maximum score"><input name="max_score" type="number" min="1" defaultValue={current.max_score} required /></Field>
            <Field controlId="assignment-edit-description" label="Description" full><textarea name="description" defaultValue={current.description} /></Field>
            <div className="field"><label htmlFor="assignment-edit-published"><input id="assignment-edit-published" name="published" type="checkbox" defaultChecked={current.published} /> Published (visible to students)</label></div>
            <p className="muted" style={{ fontSize: 13 }}>Editing never changes lateness already recorded on submitted work.</p>
            <button className="btn" disabled={busy}>Save changes</button>
          </form>
        );
      })()}
    </Card>
    <Card title="Grade submission">
      <Field controlId="grade-submission" label="Submitted work">
        <select value={gradingSubmissionId} onChange={event => setGradingSubmissionId(event.target.value)} required>
          <option value="">Select submission</option>
          {submissions.map(item => <option key={item.id} value={item.id}>{item.student} · {item.assignment} · {item.status}</option>)}
        </select>
      </Field>
      {!submissions.length && <p id="submission-empty" className="muted">{loading ? "Loading submitted work…" : "No submitted work is awaiting review."}</p>}
      {gradingSubmissionId && (() => {
        const current = submissions.find(item => item.id === gradingSubmissionId);
        if (!current) return null;
        return (
          <>
            <div className="qa-item">
              <div className="qa-item-head"><strong>What {current.student} submitted</strong></div>
              {current.answer && <blockquote className="answer-text">{current.answer}</blockquote>}
              {current.file_url && <p style={{ margin: current.answer ? "8px 0 0" : 0 }}><a className="btn small secondary" href={current.file_url} target="_blank" rel="noreferrer">Open submitted file</a></p>}
              {!current.answer && !current.file_url && <p className="muted answer-empty">Nothing was submitted.</p>}
            </div>
            <form key={gradingSubmissionId} className="form" onSubmit={event => { const form = new FormData(event.currentTarget); void submit(event, `/api/v1/workflows/it/trainer/submissions/${gradingSubmissionId}`, "PATCH", { score: Number(form.get("score")), status: form.get("status"), feedback: form.get("feedback") }, "Submission graded."); }}>
              <Field controlId="grade-score" label={`Score (of ${current.max_score})`}><input name="score" type="number" min="0" max={current.max_score} required /></Field>
              <Field controlId="grade-outcome" label="Outcome"><select name="status"><option value="graded">Graded</option><option value="revision_required">Revision required</option></select></Field>
              <Field controlId="grade-feedback" label="Feedback" full><textarea name="feedback" /></Field>
              <button className="btn" disabled={busy}>Publish grade</button>
            </form>
          </>
        );
      })()}
    </Card>
  </>;

  if (section === "assessments") content = <>
    <Card title="Create assessment">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); void submit(event, "/api/v1/workflows/it/trainer/assessments", "POST", { batch_id: form.get("batch"), title: form.get("title"), description: form.get("description"), scheduled_at: form.get("scheduled_at"), duration_minutes: Number(form.get("duration")), max_score: Number(form.get("max_score")), status: form.get("status") }, "Assessment created."); }}>
        <Field controlId="assessment-batch" label="Batch"><select name="batch" required><option value="">Select batch</option>{batchOptions}</select></Field>
        <Field controlId="assessment-title" label="Title"><input name="title" required /></Field>
        <Field controlId="assessment-scheduled" label="Scheduled date and time"><input name="scheduled_at" type="datetime-local" required /></Field>
        <Field controlId="assessment-duration" label="Duration in minutes"><input name="duration" type="number" min="1" defaultValue="60" required /></Field>
        <Field controlId="assessment-maximum-score" label="Maximum score"><input name="max_score" type="number" min="1" defaultValue="100" required /></Field>
        <Field controlId="assessment-status" label="Status"><select name="status" defaultValue="draft"><option value="draft">Draft (not visible to students)</option><option value="scheduled">Scheduled (published)</option></select></Field>
        <Field controlId="assessment-description" label="Description" full><textarea name="description" /></Field>
        <button className="btn" disabled={busy || loading}>Create assessment</button>
      </form>
    </Card>
    <Card title="Edit assessment">
      <Field controlId="assessment-edit-select" label="Assessment">
        <select value={editAssessmentId} onChange={event => setEditAssessmentId(event.target.value)}>
          <option value="">Select assessment</option>
          {assessments.map(item => <option key={item.id} value={item.id}>{item.title} · {item.batch} · {item.status}</option>)}
        </select>
      </Field>
      {!assessments.length && <p id="assessment-edit-empty" className="muted">{loading ? "Loading your assessments…" : "No assessments exist yet -- create one above."}</p>}
      {editAssessmentId && (() => {
        const current = assessments.find(item => item.id === editAssessmentId);
        if (!current) return null;
        return (
          <form key={editAssessmentId} className="form" onSubmit={event => {
            const form = new FormData(event.currentTarget);
            void submit(event, `/api/v1/workflows/it/trainer/assessments/${editAssessmentId}`, "PATCH", {
              title: form.get("title"),
              description: form.get("description"),
              scheduled_at: form.get("scheduled_at"),
              duration_minutes: Number(form.get("duration")),
              max_score: Number(form.get("max_score")),
              status: form.get("status"),
            }, "Assessment updated.");
          }}>
            <Field controlId="assessment-edit-title" label="Title"><input name="title" defaultValue={current.title} required /></Field>
            <Field controlId="assessment-edit-scheduled" label="Scheduled date and time"><input name="scheduled_at" type="datetime-local" defaultValue={current.scheduled_at.slice(0, 16)} required /></Field>
            <Field controlId="assessment-edit-duration" label="Duration in minutes"><input name="duration" type="number" min="1" defaultValue={current.duration_minutes} required /></Field>
            <Field controlId="assessment-edit-maximum-score" label="Maximum score"><input name="max_score" type="number" min="1" defaultValue={current.max_score} required /></Field>
            <Field controlId="assessment-edit-status" label="Status"><select name="status" defaultValue={current.status}><option value="draft">Draft (not visible to students)</option><option value="scheduled">Scheduled (published)</option><option value="open">Open</option><option value="closed">Closed</option><option value="published">Published</option></select></Field>
            <Field controlId="assessment-edit-description" label="Description" full><textarea name="description" defaultValue={current.description} /></Field>
            <p className="muted" style={{ fontSize: 13 }}>Moving from Draft to any other status publishes it -- students never see a Draft assessment.</p>
            <button className="btn" disabled={busy}>Save changes</button>
          </form>
        );
      })()}
    </Card>
    <Card title="Add question">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); const reference = String(form.get("assessment")); void submit(event, `/api/v1/workflows/it/trainer/assessments/${reference}/questions`, "POST", { question_type: form.get("question_type"), prompt: form.get("prompt"), options: String(form.get("options") || "").split(",").map(value => value.trim()).filter(Boolean), correct_answers: String(form.get("answers") || "").split(",").map(value => value.trim()).filter(Boolean), max_score: Number(form.get("score")), position: Number(form.get("position")) }, "Question added."); }}>
        <Field controlId="question-assessment" label="Assessment"><select name="assessment" required><option value="">Select assessment</option>{assessments.map(item => <option key={item.id} value={item.id} disabled={item.attempt_count > 0}>{item.title} · {item.batch}{item.attempt_count > 0 ? " · locked, already attempted" : ""}</option>)}</select></Field>
        {assessments.some(item => item.attempt_count > 0) && <p className="muted" style={{ fontSize: 13 }}>Assessments a student has already started can no longer take new questions -- create a new assessment instead.</p>}
        <Field controlId="question-type" label="Question type"><select name="question_type"><option value="mcq_single">Single choice</option><option value="mcq_multiple">Multiple choice</option><option value="text">Written answer</option><option value="file">File response</option></select></Field>
        <Field controlId="question-prompt" label="Question" full><textarea name="prompt" required /></Field>
        <Field controlId="question-options" label="Options, comma separated"><input name="options" /></Field>
        <Field controlId="question-answers" label="Correct answers, comma separated"><input name="answers" /></Field>
        <Field controlId="question-score" label="Score"><input name="score" type="number" min="1" defaultValue="1" /></Field>
        <Field controlId="question-position" label="Position"><input name="position" type="number" min="1" defaultValue="1" /></Field>
        {!assessments.length && <p id="assessment-empty" className="muted">{loading ? "Loading assessments…" : "Create an assessment before adding questions."}</p>}
        <button className="btn" disabled={busy || loading || !assessments.length} aria-describedby={!assessments.length ? "assessment-empty" : undefined}>Add question</button>
      </form>
    </Card>
    <Card title="Grade written attempt">
      <Field controlId="attempt-submission" label="Submitted attempt">
        <select value={gradingAttemptId} onChange={event => setGradingAttemptId(event.target.value)} required>
          <option value="">Select attempt</option>
          {attempts.map(item => <option key={item.id} value={item.id}>{item.student} · {item.assessment} · {item.status}</option>)}
        </select>
      </Field>
      {!attempts.length && <p id="attempt-empty" className="muted">{loading ? "Loading submitted attempts…" : "No written attempts are awaiting review."}</p>}
      {gradingAttemptId && loadingAttemptDetail && <p className="muted">Loading the student&apos;s answers…</p>}
      {gradingAttemptId && !loadingAttemptDetail && attemptDetail && (() => {
        const detail = attemptDetail;
        return (
          <form key={gradingAttemptId} className="form" onSubmit={event => {
            const form = new FormData(event.currentTarget);
            const answer_scores: Record<string, number> = {};
            for (const answer of detail.answers) {
              if (answer.auto_graded) continue;
              const raw = form.get(`answer_score_${answer.id}`);
              if (raw !== null && raw !== "") answer_scores[answer.id] = Number(raw);
            }
            void submit(event, `/api/v1/workflows/it/trainer/assessment-attempts/${gradingAttemptId}`, "PATCH", { answer_scores, feedback: form.get("feedback") }, "Attempt graded.");
            setGradingAttemptId("");
          }}>
            <span className={detail.status === "graded" ? "status" : "status pending"}>{detail.status.replace("_", " ")}</span>
            {detail.answers.length === 0 && <p className="muted">This attempt has no manually gradable questions yet.</p>}
            {detail.answers.map(answer => (
              <div className="qa-item" key={answer.id}>
                <div className="qa-item-head">
                  <strong>{answer.prompt}</strong>
                  <span className="muted" style={{ fontSize: 12 }}>{answer.auto_graded ? `Auto-graded · ${answer.score ?? 0}/${answer.max_score}` : `Max ${answer.max_score}`}</span>
                </div>
                {Array.isArray(answer.value) ? <blockquote className="answer-text">{answer.value.join(", ")}</blockquote>
                  : answer.question_type === "file" && typeof answer.value === "string" && answer.value ? <p style={{ margin: "8px 0 0" }}><a className="btn small secondary" href={answer.value} target="_blank" rel="noreferrer">Open submitted file</a></p>
                  : answer.value ? <blockquote className="answer-text">{String(answer.value)}</blockquote>
                  : <p className="muted answer-empty">Nothing was submitted.</p>}
                {!answer.auto_graded && (
                  <Field controlId={`answer-score-${answer.id}`} label={`Score (of ${answer.max_score})`}>
                    <input name={`answer_score_${answer.id}`} type="number" min="0" max={answer.max_score} defaultValue={answer.score ?? ""} />
                  </Field>
                )}
              </div>
            ))}
            <Field controlId="attempt-feedback" label="Feedback" full><textarea name="feedback" defaultValue={detail.feedback || ""} /></Field>
            <button className="btn" disabled={busy}>Publish grade</button>
          </form>
        );
      })()}
    </Card>
  </>;

  if (section === "materials") content = <Card title="Publish course material">
    <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); void submit(event, "/api/v1/workflows/it/trainer/materials", "POST", { batch_id: form.get("batch"), title: form.get("title"), resource_type: form.get("type"), url: form.get("url") }, "Material published."); }}>
      <Field controlId="material-batch" label="Batch"><select name="batch" required><option value="">Select batch</option>{batchOptions}</select></Field>
      <Field controlId="material-title" label="Title"><input name="title" required /></Field>
      <Field controlId="material-type" label="Material type"><select name="type"><option value="link">Link</option><option value="document">Document</option><option value="video">Video</option><option value="recording">Provider recording</option><option value="notes">Notes</option></select></Field>
      <Field controlId="material-url" label="Resource URL"><input name="url" type="url" required /></Field>
      <button className="btn" disabled={busy || loading}>Publish material</button>
    </form>
  </Card>;

  if (section === "live-sessions") content = <>
    <Card title="Schedule live session">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); void submit(event, "/api/v1/communications/it/live-sessions", "POST", { batch_id: form.get("batch"), title: form.get("title"), starts_at: form.get("starts"), ends_at: form.get("ends"), provider: form.get("provider"), meeting_url: form.get("meeting_url") || undefined, agenda: form.get("agenda"), attendee_emails: [] }, "Live session scheduled."); }}>
        <Field controlId="session-batch" label="Batch"><select name="batch" required><option value="">Select batch</option>{batchOptions}</select></Field>
        <Field controlId="session-title" label="Session title"><input name="title" required /></Field>
        <Field controlId="session-start" label="Starts"><input name="starts" type="datetime-local" required /></Field>
        <Field controlId="session-end" label="Ends"><input name="ends" type="datetime-local" required /></Field>
        <Field controlId="session-provider" label="Meeting provider"><select name="provider" defaultValue="google_meet"><option value="google_meet">Google Meet</option><option value="zoho_meeting">Zoho Meeting</option><option value="manual">Existing provider link</option></select></Field>
        <Field controlId="session-url" label="Existing meeting URL, if applicable"><input name="meeting_url" type="url" /></Field>
        <Field controlId="session-agenda" label="Agenda" full><textarea name="agenda" /></Field>
        <button className="btn" disabled={busy || loading}>Schedule session</button>
      </form>
    </Card>
    <Card title="Attach provider recording">
      <p className="muted">EduSphere stores only the Google Meet or Zoho Meeting recording link.</p>
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); const reference = String(form.get("session")); void submit(event, `/api/v1/communications/it/live-sessions/${reference}/recording`, "PATCH", { recording_url: form.get("recording_url"), recording_external_id: form.get("provider_reference") || undefined, recording_status: form.get("status") }, "Provider recording attached."); }}>
        <Field controlId="recording-session" label="Live session"><select name="session" required><option value="">Select session</option>{sessions.map(item => <option key={item.id} value={item.id}>{item.title} · {item.batch} · {item.provider}</option>)}</select></Field>
        <Field controlId="recording-url" label="Recording URL"><input name="recording_url" type="url" required /></Field>
        <Field controlId="recording-reference" label="Provider recording reference"><input name="provider_reference" /></Field>
        <Field controlId="recording-status" label="Status"><select name="status"><option value="available">Available</option><option value="processing">Processing</option><option value="failed">Failed</option></select></Field>
        {!sessions.length && <p id="session-empty" className="muted">{loading ? "Loading live sessions…" : "No live session is available for a recording link."}</p>}
        <button className="btn" disabled={busy || loading || !sessions.length} aria-describedby={!sessions.length ? "session-empty" : undefined}>Attach recording</button>
      </form>
    </Card>
  </>;

  if (section === "student-progress") content = <>
    <Card title="Update learner progress">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); const reference = String(form.get("enrollment")); void submit(event, `/api/v1/workflows/it/trainer/enrollments/${reference}/progress`, "PATCH", { progress_percent: Number(form.get("progress")) }, "Progress updated."); }}>
        <Field controlId="progress-enrollment" label="Learner and batch"><select name="enrollment" required><option value="">Select learner</option>{context.enrollments.map(item => <option key={item.id} value={item.id}>{item.student} · {item.batch} · {item.progress_percent}%</option>)}</select></Field>
        <Field controlId="progress-percent" label="Progress percent"><input name="progress" type="number" min="0" max="100" required /></Field>
        {!context.enrollments.length && <p id="progress-empty" className="muted">{loading ? "Loading active enrollments…" : "No active enrollment is assigned to this trainer."}</p>}
        <button className="btn" disabled={busy || loading || !context.enrollments.length} aria-describedby={!context.enrollments.length ? "progress-empty" : undefined}>Update progress</button>
      </form>
    </Card>
    <Card title="Issue certificate">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); const reference = String(form.get("enrollment")); void submit(event, `/api/v1/workflows/it/certificates/${reference}/issue`, "POST", { override: form.get("override") === "on", override_reason: form.get("override_reason") || undefined }, "Certificate issued."); }}>
        <Field controlId="certificate-enrollment" label="Eligible learner"><select name="enrollment" required><option value="">Select learner</option>{context.enrollments.map(item => <option key={item.id} value={item.id}>{item.student} · {item.batch} · {item.enrollment_code}</option>)}</select></Field>
        <div className="field"><label htmlFor="certificate-override"><input id="certificate-override" name="override" type="checkbox" checked={certificateOverride} onChange={event => setCertificateOverride(event.target.checked)} /> Override unmet criteria</label></div>
        {certificateOverride && <Field controlId="certificate-override-reason" label="Override reason (required to issue before criteria are met)"><textarea name="override_reason" required /></Field>}
        {!context.enrollments.length && <p id="certificate-empty" className="muted">{loading ? "Loading eligible learners…" : "No active enrollment is available for certificate issuance."}</p>}
        <button className="btn" disabled={busy || loading || !context.enrollments.length} aria-describedby={!context.enrollments.length ? "certificate-empty" : undefined}>Issue certificate</button>
      </form>
    </Card>
  </>;

  if (section === "questions") content = <>
    <Card title="Student questions">
      {questions.length === 0 && <p className="muted">No questions have been raised in your batches yet.</p>}
      {questions.map(item => (
        <div className="card" key={item.id} style={{ marginBottom: 12 }}>
          <span className="badge">{item.batch}</span>
          <h4 style={{ marginTop: 8 }}>{item.subject}</h4>
          <p className="muted" style={{ fontSize: 13 }}>{item.student}: {item.body}</p>
          {item.replies.length > 0 && (
            <ul>
              {item.replies.map(reply => <li key={reply.id} style={{ fontSize: 13 }}>{reply.body}</li>)}
            </ul>
          )}
        </div>
      ))}
    </Card>
    <Card title="Reply to question">
      <form className="form" onSubmit={event => { const form = new FormData(event.currentTarget); const reference = String(form.get("thread")); void submit(event, `/api/v1/workflows/it/trainer/questions/${reference}/replies`, "POST", { body: form.get("body") }, "Reply posted."); }}>
        <Field controlId="question-thread" label="Question"><select name="thread" required><option value="">Select question</option>{questions.map(item => <option key={item.id} value={item.id}>{item.student} · {item.batch} · {item.subject}</option>)}</select></Field>
        <Field controlId="question-reply-body" label="Reply" full><textarea name="body" required /></Field>
        {!questions.length && <p id="question-empty" className="muted">{loading ? "Loading questions…" : "No questions are awaiting a reply."}</p>}
        <button className="btn" disabled={busy || loading || !questions.length} aria-describedby={!questions.length ? "question-empty" : undefined}>Post reply</button>
      </form>
    </Card>
  </>;

  if (section === "support") content = <SupportTicketQueuePanel />;

  if (!content) return null;
  return <div className="portal-content action-center" style={{ paddingTop: 0 }}><div className="workspace-head action-heading"><div><strong>Teacher actions</strong><p>Select records by name; UUID values are not required as manual input.</p></div><span className="badge">Operational</span></div>{feedback}<div className="action-grid">{content}</div></div>;
}
