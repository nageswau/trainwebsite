"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { User } from "@/lib/types";
import BatchSlotPicker from "./BatchSlotPicker";
import LiveClassesPanel from "./LiveClassesPanel";
import AssignmentSubmissionPanel from "./AssignmentSubmissionPanel";
import AgreementConsentPanel from "./AgreementConsentPanel";
import AdminUserManagementPanel from "./AdminUserManagementPanel";
import AdminExpiredLinksPanel from "./AdminExpiredLinksPanel";
import AdminProgramManagementPanel from "./AdminProgramManagementPanel";
import AdminLeadManagementPanel from "./AdminLeadManagementPanel";
import AdminBatchCreatePanel from "./AdminBatchCreatePanel";
import AdminEnrollmentReviewPanel from "./AdminEnrollmentReviewPanel";
import SupportTicketQueuePanel from "./SupportTicketQueuePanel";
import CertificateDownloadPanel from "./CertificateDownloadPanel";
import FeedbackSubmissionPanel from "./FeedbackSubmissionPanel";
import QuestionAskPanel from "./QuestionAskPanel";
import OverseasApplyPanel from "./OverseasApplyPanel";
import ScholarshipApplyPanel from "./ScholarshipApplyPanel";
import FeePaymentPanel from "./FeePaymentPanel";
import CounselorEvaluationPanel from "./CounselorEvaluationPanel";
import DocumentDownloadPanel from "./DocumentDownloadPanel";
import CounselorDocumentReviewPanel from "./CounselorDocumentReviewPanel";
import VisaChecklistPanel from "./VisaChecklistPanel";
import CounselorVisaPanel from "./CounselorVisaPanel";
import AgentApprovalPanel from "./AgentApprovalPanel";
import AdminCertificatePanel from "./AdminCertificatePanel";
import PlacementCandidatePanel from "./PlacementCandidatePanel";
import HrShortlistPanel from "./HrShortlistPanel";
import AuditExportPanel from "./AuditExportPanel";
import ProfileDocumentUpload from "./ProfileDocumentUpload";
import CounselorChatPanel from "./CounselorChatPanel";
import AdminUniversityCreatePanel from "./AdminUniversityCreatePanel";
import AgentApplicationCreatePanel from "./AgentApplicationCreatePanel";
import AdminSchoolApplicationsPanel from "./AdminSchoolApplicationsPanel";
import AdminSchoolCreatePanel from "./AdminSchoolCreatePanel";
import AdminSchoolStaffPanel from "./AdminSchoolStaffPanel";

type Field = {
  name: string;
  label: string;
  type?: "text" | "number" | "date" | "datetime-local" | "textarea" | "select" | "checkbox" | "password";
  options?: { label: string; value: string }[];
  required?: boolean;
  placeholder?: string;
  defaultValue?: string | number | boolean;
  parse?: "number" | "list" | "boolean";
};

type ActionSpec = {
  title: string;
  description?: string;
  endpoint: string;
  method?: "POST" | "PATCH" | "PUT";
  success: string;
  fields: Field[];
  pathFields?: string[];
  buildBody?: (values: Record<string, unknown>) => Record<string, unknown>;
};

const options = (values: string[]) => values.map(value => ({ value, label: value.replaceAll("_", " ") }));
// DATA_MODEL.md #6.2's contract-fixed enum (OVS-002/003) -- exception-path values
// (rejected/waitlisted/deferred) are a deliberate open item, not offered here.
const applicationStatuses = options(["enquiry", "eligibility_evaluation", "university_selection", "offer", "visa_documentation", "status_tracking", "enrolled"]);

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) return String((detail as { message: unknown }).message);
  if (Array.isArray(detail)) return detail.map(item => item?.msg || "Invalid input").join("; ");
  return "The operation could not be completed.";
}

// Shared local-upload/presign flow (mirrors DocumentUpload's own inline copy) -- used by
// AssessmentForm to give a `file`-response question a real upload instead of the plain
// textarea every other non-MCQ question type falls back to.
async function uploadFile(file: File): Promise<string> {
  const local = new FormData(); local.set("file", file);
  const localResponse = await fetch("/api/v1/files/local-upload", { method: "POST", body: local });
  if (localResponse.ok) return String((await localResponse.json()).url);
  const presignResponse = await fetch("/api/v1/files/presign", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: file.name, content_type: file.type, size: file.size }) });
  const signed = await presignResponse.json();
  if (!presignResponse.ok) throw new Error(detailMessage(signed.detail));
  const upload = await fetch(signed.upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
  if (!upload.ok) throw new Error("Object storage upload failed");
  return String(signed.key);
}

function parseValues(form: FormData, fields: Field[]) {
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    const raw = field.type === "checkbox" ? form.get(field.name) === "on" : form.get(field.name);
    if (raw === "" || raw === null) continue;
    if (field.parse === "number" || field.type === "number") values[field.name] = Number(raw);
    else if (field.parse === "list") values[field.name] = String(raw).split(",").map(item => item.trim()).filter(Boolean);
    else if (field.parse === "boolean" || field.type === "checkbox") values[field.name] = Boolean(raw);
    else values[field.name] = String(raw);
  }
  return values;
}

function ActionForm({ spec }: { spec: ActionSpec }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // The DOM nulls event.currentTarget once dispatch finishes, which happens as soon
    // as this handler yields at the first `await` below -- capture the element now, not
    // after the fetch, or `.reset()` intermittently throws "Cannot read properties of
    // null" (found while testing STU-005's ticket form, which uses this same component).
    const formElement = event.currentTarget;
    setBusy(true); setMessage(""); setFailed(false);
    const values = parseValues(new FormData(formElement), spec.fields);
    let endpoint = spec.endpoint;
    for (const name of spec.pathFields || []) endpoint = endpoint.replace(`:${name}`, encodeURIComponent(String(values[name] ?? "")));
    let body = { ...values };
    for (const name of spec.pathFields || []) delete body[name];
    if (spec.buildBody) body = spec.buildBody(values);
    try {
      const response = await fetch(endpoint, { method: spec.method || "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(detailMessage(data.detail));
      setMessage(spec.success); formElement.reset(); router.refresh();
    } catch (error) {
      setFailed(true); setMessage(error instanceof Error ? error.message : "Request failed");
    } finally { setBusy(false); }
  }

  return <div className="action-card"><div><h3>{spec.title}</h3>{spec.description && <p className="muted">{spec.description}</p>}</div><form className="form" onSubmit={submit}>
    <div className="form-grid">{spec.fields.map(field => <div className={`field${field.type === "textarea" ? " full" : ""}`} key={field.name}>
      <label htmlFor={`${spec.title}-${field.name}`}>{field.label}</label>
      {field.type === "textarea" ? <textarea id={`${spec.title}-${field.name}`} name={field.name} required={field.required} placeholder={field.placeholder} defaultValue={String(field.defaultValue ?? "")}/> : field.type === "select" ? <select id={`${spec.title}-${field.name}`} name={field.name} required={field.required} defaultValue={String(field.defaultValue ?? "")}><option value="">Select</option>{field.options?.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select> : field.type === "checkbox" ? <input id={`${spec.title}-${field.name}`} name={field.name} type="checkbox" defaultChecked={Boolean(field.defaultValue)}/> : <input id={`${spec.title}-${field.name}`} name={field.name} type={field.type || "text"} required={field.required} placeholder={field.placeholder} defaultValue={String(field.defaultValue ?? "")}/>} 
    </div>)}</div>
    {message && <div className={failed ? "form-error" : "form-message"}>{message}</div>}
    <button className="btn" disabled={busy}>{busy ? "Saving…" : spec.title}</button>
  </form></div>;
}

type Attempt = { id: string; title: string; questions: { id: string; prompt: string; question_type: string; options: string[]; required: boolean }[] };

type ExaminationRow = { id: string; title: string; scheduled: string; status: string };

function AssessmentForm() {
  const router = useRouter();
  const [assessmentId, setAssessmentId] = useState("");
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  // The "Take assessment" reference used to be a raw UUID the student had to type by
  // hand -- every assessment's real id was already visible in the "Examinations" table
  // above this form, but nowhere pickable, the same "raw ID typed by hand" gap already
  // fixed for nearly every other action in this app. `start_assessment` (workflows.py)
  // only ever accepts scheduled/open/published, so this list is filtered the same way
  // -- a helpful narrowing, not the authoritative check (the backend still enforces it).
  const [available, setAvailable] = useState<ExaminationRow[] | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/portal/it/student/examinations")
      .then(res => (res.ok ? res.json() : { rows: [] }))
      .then(data => {
        if (cancelled) return;
        const rows = (data.rows || []) as ExaminationRow[];
        setAvailable(rows.filter(row => ["scheduled", "open", "published"].includes(row.status)));
      })
      .catch(() => !cancelled && setAvailable([]));
    return () => { cancelled = true; };
  }, []);
  async function start(event: FormEvent) {
    event.preventDefault(); setBusy(true); setMessage("");
    const response = await fetch(`/api/v1/workflows/it/assessments/${assessmentId}/attempts`, { method: "POST" });
    const data = await response.json().catch(() => ({})); setBusy(false);
    if (!response.ok) return setMessage(detailMessage(data.detail));
    setAttempt(data as Attempt);
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!attempt) return; setBusy(true); setMessage("");
    const form = new FormData(event.currentTarget);
    try {
      const answers = await Promise.all(attempt.questions.map(async question => {
        if (question.question_type === "mcq_multiple") return { question_id: question.id, value: form.getAll(`q_${question.id}`) };
        if (question.question_type === "file") {
          const file = form.get(`q_${question.id}`);
          const url = file instanceof File && file.size ? await uploadFile(file) : "";
          return { question_id: question.id, value: url };
        }
        return { question_id: question.id, value: String(form.get(`q_${question.id}`) || "") };
      }));
      const response = await fetch(`/api/v1/workflows/it/assessment-attempts/${attempt.id}/submit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ answers }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) { setMessage(detailMessage(data.detail)); return; }
      setMessage(`Submitted. Status: ${data.status}${data.percentage !== undefined ? `, score ${data.percentage}%` : ""}.`); setAttempt(null); router.refresh();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "File upload failed");
    } finally {
      setBusy(false);
    }
  }
  return <div className="action-card"><h3>Take assessment</h3>{!attempt ? <form className="form" onSubmit={start}><div className="field"><label htmlFor="assessment-picker">Assessment</label><select id="assessment-picker" required value={assessmentId} onChange={event => setAssessmentId(event.target.value)} disabled={available === null || !available.length}><option value="">{available === null ? "Loading assessments…" : "Select assessment"}</option>{(available || []).map(row => <option key={row.id} value={row.id}>{row.title} · {new Date(row.scheduled).toLocaleDateString("en-GB")}</option>)}</select></div>{available !== null && !available.length && <p className="muted">No assessment is currently open to attempt.</p>}<button className="btn" disabled={busy || available === null || !available.length}>{busy ? "Opening…" : "Start assessment"}</button></form> : <form className="form" onSubmit={submit}><h3>{attempt.title}</h3>{attempt.questions.map(question => <fieldset className="question" key={question.id}><legend>{question.prompt}</legend>{question.options.length ? question.options.map(option => <label key={option}><input type={question.question_type === "mcq_multiple" ? "checkbox" : "radio"} name={`q_${question.id}`} value={option} required={question.required && question.question_type !== "mcq_multiple"}/> {option}</label>) : question.question_type === "file" ? <input type="file" name={`q_${question.id}`} required={question.required}/> : <textarea name={`q_${question.id}`} required={question.required}/>}</fieldset>)}<button className="btn" disabled={busy}>{busy ? "Submitting…" : "Submit assessment"}</button></form>}{message && <div className={message.startsWith("Submitted") ? "form-message" : "form-error"}>{message}</div>}</div>;
}

function DocumentUpload({ user }: { user: User }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setMessage(""); setFailed(false);
    const formElement = event.currentTarget;
    const form = new FormData(formElement); const file = form.get("file");
    if (!(file instanceof File) || !file.size) { setBusy(false); return; }
    try {
      let fileUrl = "";
      const local = new FormData(); local.set("file", file);
      const localResponse = await fetch("/api/v1/files/local-upload", { method: "POST", body: local });
      if (localResponse.ok) fileUrl = String((await localResponse.json()).url);
      else {
        const presignResponse = await fetch("/api/v1/files/presign", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ filename: file.name, content_type: file.type, size: file.size }) });
        const signed = await presignResponse.json(); if (!presignResponse.ok) throw new Error(detailMessage(signed.detail));
        const upload = await fetch(signed.upload_url, { method: "PUT", headers: { "Content-Type": file.type }, body: file });
        if (!upload.ok) throw new Error("Object storage upload failed"); fileUrl = signed.key;
      }
      const studentId = String(form.get("student_id") || ""); const applicationId = String(form.get("application_id") || "");
      const response = await fetch("/api/v1/workflows/overseas/documents", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ student_id: studentId || undefined, application_id: applicationId || undefined, document_type: form.get("document_type"), file_url: fileUrl, original_filename: file.name, content_type: file.type, file_size: file.size }) });
      const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(detailMessage(data.detail));
      setMessage("Document uploaded and queued for verification."); formElement.reset(); router.refresh();
    } catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : "Upload failed"); } finally { setBusy(false); }
  }
  const ownsDocument = user.role === "overseas_student";
  return <div className="action-card"><h3>Upload document</h3><p className="muted">PDF, Word, and configured image formats are accepted. Recording files are intentionally not stored here.</p><form className="form" onSubmit={submit}><div className="form-grid">{!ownsDocument && <div className="field"><label>Student reference</label><input name="student_id" required/></div>}<div className="field"><label>Application reference (optional)</label><input name="application_id"/></div><div className="field"><label>Document type</label><input name="document_type" required placeholder="Passport, transcript, SOP…"/></div><div className="field"><label>File</label><input name="file" type="file" required/></div></div>{message && <div className={failed ? "form-error" : "form-message"}>{message}</div>}<button className="btn" disabled={busy}>{busy ? "Uploading…" : "Upload document"}</button></form></div>;
}

const supportSpec = (): ActionSpec[] => [{ title: "Open support ticket", endpoint: "/api/v1/workflows/support", success: "Support ticket opened.", fields: [{ name: "subject", label: "Subject", required: true }, { name: "description", label: "Description", type: "textarea", required: true }, { name: "priority", label: "Priority", type: "select", defaultValue: "normal", options: options(["low", "normal", "high", "urgent"]) }] }];

const appointmentSpec = (staff: boolean): ActionSpec => ({ title: "Schedule appointment", endpoint: "/api/v1/workflows/overseas/appointments", success: "Appointment scheduled.", fields: [...(staff ? [{ name: "student_id", label: "Student reference", type: "text" as const, required: true }] : []), { name: "scheduled_at", label: "Date and time", type: "datetime-local", required: true }, { name: "appointment_type", label: "Type", defaultValue: "Career Counseling", required: true }, { name: "mode", label: "Mode", type: "select", defaultValue: "Online", options: options(["Online", "Phone", "In person"]) }] });

function liveSessionSpecs(): ActionSpec[] { return [
  { title: "Schedule live session", description: "Google Meet or Zoho Meeting creates the meeting through its API. Manual mode accepts an existing link.", endpoint: "/api/v1/communications/it/live-sessions", success: "Live session scheduled.", fields: [{ name: "batch_id", label: "Batch reference", type: "text", required: true }, { name: "title", label: "Session title", required: true }, { name: "starts_at", label: "Starts", type: "datetime-local", required: true }, { name: "ends_at", label: "Ends", type: "datetime-local", required: true }, { name: "provider", label: "Meeting provider", type: "select", required: true, defaultValue: "manual", options: [{ value: "google_meet", label: "Google Meet" }, { value: "zoho_meeting", label: "Zoho Meeting" }, { value: "manual", label: "Manual link" }] }, { name: "meeting_url", label: "Manual meeting URL" }, { name: "agenda", label: "Agenda", type: "textarea" }] },
  { title: "Attach provider recording", description: "Store only the provider recording link; EduSphere does not capture media.", endpoint: "/api/v1/communications/it/live-sessions/:session_id/recording", method: "PATCH", success: "Recording link attached.", pathFields: ["session_id"], fields: [{ name: "session_id", label: "Live session reference", type: "text", required: true }, { name: "recording_url", label: "Google/Zoho recording URL", required: true }, { name: "recording_external_id", label: "Provider recording reference" }, { name: "recording_status", label: "Status", type: "select", defaultValue: "available", options: options(["processing", "available", "failed"]) }] }
]; }

function studentSpecs(user: User, section: string): ActionSpec[] {
  if (section === "profile") {
    const profile = user.profile || {};
    return [{ title: "Update profile", endpoint: "/api/v1/auth/me", method: "PATCH", success: "Profile updated.", fields: [{ name: "full_name", label: "Full name", required: true, defaultValue: user.full_name }, { name: "phone", label: "Phone", defaultValue: user.phone || "" }, { name: "education", label: "Education", defaultValue: String(profile.education || "") }, { name: "skills", label: "Skills (comma separated)", parse: "list", defaultValue: Array.isArray(profile.skills) ? profile.skills.join(", ") : "" }, { name: "preferred_countries", label: "Preferred countries", parse: "list", defaultValue: Array.isArray(profile.preferred_countries) ? profile.preferred_countries.join(", ") : "" }, { name: "preferred_intake", label: "Preferred intake", defaultValue: String(profile.preferred_intake || "") }, { name: "resume_url", label: "Resume URL", defaultValue: String(profile.resume_url || "") }], buildBody: values => ({ full_name: values.full_name, phone: values.phone, profile: { ...profile, education: values.education, skills: values.skills || [], preferred_countries: values.preferred_countries || [], preferred_intake: values.preferred_intake, resume_url: values.resume_url } }) }];
  }
  if (user.role === "it_student") {
    // "course" is handled by BatchSlotPicker + LiveClassesPanel (STU-001/STU-003), and
    // "assignments"/"projects" by AssignmentSubmissionPanel (STU-004), instead of a
    // generic spec -- see WorkflowPanel's render below.
    if (section === "attendance") return [{ title: "Request correction", endpoint: "/api/v1/workflows/it/student/attendance-corrections", success: "Correction request submitted.", fields: [{ name: "attendance_id", label: "Attendance record reference", type: "text", required: true }, { name: "requested_status", label: "Correct status", type: "select", required: true, options: options(["present", "absent", "late", "excused"]) }, { name: "reason", label: "Reason", type: "textarea", required: true }] }];
    // "fees" is handled by FeePaymentPanel (STU-010/PAY-001) instead of a generic spec --
    // see WorkflowPanel's render below.
    if (section === "job-applications") return [{ title: "Apply for job", endpoint: "/api/v1/workflows/it/jobs/:job_id/apply", success: "Job application submitted.", pathFields: ["job_id"], fields: [{ name: "job_id", label: "Open job reference", type: "text", required: true }, { name: "resume_url", label: "Resume URL" }] }];
    if (section === "support") return supportSpec();
  }
  if (user.role === "overseas_student") {
    // "applications" is handled by OverseasApplyPanel (OVS-002), and "payments" by
    // FeePaymentPanel (STU-010/PAY-001), instead of a generic spec -- see WorkflowPanel's
    // render below.
    if (section === "appointments") return [appointmentSpec(false)];
    // RAID.md I-19: `ROLE_ACTION_MATRIX.md`'s own confirmed base action for this role is
    // "counselor-chat (direct messaging with their assigned counselor)" -- only a
    // read-only history view existed, never a way to send. The counselor is resolved
    // server-side from the student's own application, so this needs nothing but the
    // message body, no picker.
    if (section === "counselor-chat") return [{ title: "Send message to counselor", endpoint: "/api/v1/workflows/overseas/student/counselor-chat", success: "Message sent to your counselor.", fields: [{ name: "body", label: "Message", type: "textarea", required: true }] }];
  }
  return [];
}

function trainerSpecs(section: string): ActionSpec[] {
  if (section === "attendance") return [{ title: "Review correction", endpoint: "/api/v1/workflows/it/attendance-corrections/:correction_id", method: "PATCH", success: "Correction reviewed.", pathFields: ["correction_id"], fields: [{ name: "correction_id", label: "Correction reference", type: "text", required: true }, { name: "status", label: "Decision", type: "select", required: true, options: options(["approved", "rejected"]) }, { name: "review_notes", label: "Review notes", type: "textarea" }] }];
  if (section === "assignments") return [{ title: "Grade submission", endpoint: "/api/v1/workflows/it/trainer/submissions/:submission_id", method: "PATCH", success: "Submission graded.", pathFields: ["submission_id"], fields: [{ name: "submission_id", label: "Submission reference", type: "text", required: true }, { name: "score", label: "Score", type: "number", required: true }, { name: "status", label: "Status", type: "select", defaultValue: "graded", options: options(["graded", "revision_required"]) }, { name: "feedback", label: "Feedback", type: "textarea" }] }];
  if (section === "assessments") return [{ title: "Add assessment question", endpoint: "/api/v1/workflows/it/trainer/assessments/:assessment_id/questions", success: "Question added.", pathFields: ["assessment_id"], fields: [{ name: "assessment_id", label: "Assessment reference", type: "text", required: true }, { name: "question_type", label: "Type", type: "select", defaultValue: "mcq_single", options: options(["mcq_single", "mcq_multiple", "text", "file"]) }, { name: "prompt", label: "Question", type: "textarea", required: true }, { name: "options", label: "Options (comma separated)", parse: "list" }, { name: "correct_answers", label: "Correct answer(s), comma separated", parse: "list" }, { name: "max_score", label: "Maximum score", type: "number", defaultValue: 1, required: true }, { name: "position", label: "Position", type: "number", defaultValue: 1, required: true }] }];
  if (section === "materials") return [{ title: "Publish material", endpoint: "/api/v1/workflows/it/trainer/materials", success: "Material published.", fields: [{ name: "batch_id", label: "Batch reference", type: "text", required: true }, { name: "title", label: "Title", required: true }, { name: "resource_type", label: "Type", type: "select", defaultValue: "link", options: options(["link", "document", "video", "recording", "notes"]) }, { name: "url", label: "Resource URL", required: true }] }];
  if (section === "live-sessions") return liveSessionSpecs();
  if (section === "student-progress") return [{ title: "Update progress", endpoint: "/api/v1/workflows/it/trainer/enrollments/:enrollment_id/progress", method: "PATCH", success: "Progress updated.", pathFields: ["enrollment_id"], fields: [{ name: "enrollment_id", label: "Enrollment database reference", type: "text", required: true }, { name: "progress_percent", label: "Progress percent", type: "number", required: true }] }, { title: "Issue certificate", endpoint: "/api/v1/workflows/it/certificates/:enrollment_id/issue", success: "Certificate issued.", pathFields: ["enrollment_id"], fields: [{ name: "enrollment_id", label: "Enrollment database reference", type: "text", required: true }, { name: "override", label: "Override unmet criteria", type: "checkbox", parse: "boolean" }] }];
  return [];
}

function placementSpecs(section: string): ActionSpec[] {
  if (["company-requirements", "job-requirements"].includes(section)) return [
    { title: "Create job requirement", endpoint: "/api/v1/workflows/it/jobs", success: "Job requirement published.", fields: [{ name: "company_name", label: "Company name", required: true }, { name: "company_website", label: "Company website" }, { name: "title", label: "Role", required: true }, { name: "location", label: "Location", defaultValue: "Remote" }, { name: "description", label: "Description", type: "textarea" }, { name: "skills", label: "Skills (comma separated)", parse: "list" }, { name: "closes_on", label: "Closes on", type: "date" }] },
    // ADM-008, tester feedback 2026-09-04 (RAID.md I-13): only a "Create" action existed
    // for this section -- no way to set or change a close date (or anything else) on a
    // requirement after creation, even though the backend (`PATCH /it/jobs/{id}`) has
    // always accepted `closes_on` for this role.
    { title: "Update job requirement", endpoint: "/api/v1/workflows/it/jobs/:job_id", method: "PATCH", success: "Job requirement updated.", pathFields: ["job_id"], fields: [{ name: "job_id", label: "Job requirement reference", type: "text", required: true }, { name: "status", label: "Status", type: "select", options: options(["open", "closed"]) }, { name: "closes_on", label: "Closes on", type: "date" }, { name: "location", label: "Location" }] },
  ];
  if (section === "interviews") return [
    { title: "Schedule interview", endpoint: "/api/v1/workflows/it/interviews", success: "Interview scheduled.", fields: [{ name: "application_id", label: "Job application reference", type: "text", required: true }, { name: "scheduled_at", label: "Date and time", type: "datetime-local", required: true }, { name: "mode", label: "Mode", defaultValue: "Online" }, { name: "meeting_url", label: "Meeting URL" }] },
    { title: "Record interview result", endpoint: "/api/v1/workflows/it/interviews/:interview_id", method: "PATCH", success: "Interview result updated.", pathFields: ["interview_id"], fields: [{ name: "interview_id", label: "Interview reference", type: "text", required: true }, { name: "result", label: "Result", type: "select", required: true, options: options(["selected", "rejected", "on_hold"]) }] }
  ];
  if (section === "offers") return [{ title: "Create offer", endpoint: "/api/v1/workflows/it/offers", success: "Offer recorded.", fields: [{ name: "application_id", label: "Job application reference", type: "text", required: true }, { name: "compensation", label: "Compensation", type: "number" }, { name: "currency", label: "Currency", defaultValue: "INR" }, { name: "joining_date", label: "Joining date", type: "date" }, { name: "letter_url", label: "Offer letter URL" }] }];
  return [];
}

function agentSpecs(section: string): ActionSpec[] {
  if (section === "students") return [{ title: "Link student", endpoint: "/api/v1/workflows/overseas/agent/students", success: "Student linked.", fields: [{ name: "student_id", label: "Overseas student reference", type: "text", required: true }] }];
  // RAID.md I-32: "applications" is now handled by AgentApplicationCreatePanel (real
  // linked-student/university/course pickers) instead of this generic form -- see
  // WorkflowPanel's render below.
  if (section === "commissions") return [{ title: "Claim commission", endpoint: "/api/v1/workflows/overseas/agent/commissions/:commission_id/claim", success: "Commission claimed.", pathFields: ["commission_id"], fields: [{ name: "commission_id", label: "Eligible commission reference", type: "text", required: true }] }];
  return [];
}

function overseasOperationsSpecs(role: string, section: string): ActionSpec[] {
  // OVS-003: a Counselor now gets a dedicated real picker (CounselorEvaluationPanel,
  // forward-only + enum-validated) instead of this generic form -- see WorkflowPanel's
  // render below. University Rep/Admin keep this broader correction tool.
  if (role !== "counselor" && ["applications", "admission-updates", "offer-letters"].includes(section)) return [{ title: "Update application", endpoint: "/api/v1/workflows/overseas/applications/:application_id", method: "PATCH", success: "Application updated and student notified.", pathFields: ["application_id"], fields: [{ name: "application_id", label: "Application reference", type: "text", required: true }, { name: "status", label: "Status", type: "select", required: true, options: applicationStatuses }, { name: "application_reference", label: "University reference" }, { name: "offer_letter_url", label: "Offer letter URL" }, { name: "next_action", label: "Next action", type: "textarea" }, { name: "notes", label: "Internal update note", type: "textarea" }] }];
  // OVS-005: a Counselor now gets a real review queue (CounselorDocumentReviewPanel,
  // with an actual "View document" action this generic form never had) instead of this
  // raw-typed form -- see WorkflowPanel's render below. Admin keeps this broader tool.
  if (section === "documents" && !["university_rep", "counselor"].includes(role)) return [{ title: "Verify document", endpoint: "/api/v1/workflows/overseas/documents/:document_id/verify", method: "PATCH", success: "Document reviewed.", pathFields: ["document_id"], fields: [{ name: "document_id", label: "Document reference", type: "text", required: true }, { name: "verification_status", label: "Decision", type: "select", required: true, options: options(["verified", "rejected", "changes_required"]) }, { name: "notes", label: "Reviewer notes", type: "textarea" }] }];
  // VISA-001: a Counselor now gets a real per-application view (CounselorVisaPanel, with
  // an actual checklist + document verification status this generic form never showed)
  // instead of typing raw application/visa-case UUIDs -- see WorkflowPanel's render
  // below. Admin keeps this broader tool.
  if (section === "visa" && role !== "counselor") return [
    { title: "Create visa case", endpoint: "/api/v1/workflows/overseas/visa", success: "Visa case created.", fields: [{ name: "application_id", label: "Application reference", type: "text", required: true }, { name: "status", label: "Status", defaultValue: "checklist" }, { name: "appointment_date", label: "Appointment date", type: "date" }, { name: "checklist", label: "Checklist (comma separated)", parse: "list" }, { name: "tracking_reference", label: "Tracking reference" }] },
    { title: "Update visa case", endpoint: "/api/v1/workflows/overseas/visa/:visa_id", method: "PATCH", success: "Visa case updated.", pathFields: ["visa_id"], fields: [{ name: "visa_id", label: "Visa case reference", type: "text", required: true }, { name: "status", label: "Status", required: true }, { name: "appointment_date", label: "Appointment date", type: "date" }, { name: "tracking_reference", label: "Tracking reference" }, { name: "checklist", label: "Checklist (comma separated)", parse: "list" }] }
  ];
  if (section === "appointments") return [appointmentSpec(true), { title: "Update appointment", endpoint: "/api/v1/workflows/overseas/appointments/:appointment_id", method: "PATCH", success: "Appointment updated.", pathFields: ["appointment_id"], fields: [{ name: "appointment_id", label: "Appointment reference", type: "text", required: true }, { name: "status", label: "Status", type: "select", required: true, options: options(["scheduled", "completed", "cancelled", "no_show"]) }] }];
  // UNI-001: net-new -- no communication action existed for the university rep's own
  // "Student Communication" section at all before this feature, only a read-only view of
  // inbound university emails.
  if (section === "student-communication" && role === "university_rep") return [{ title: "Post admission update", endpoint: "/api/v1/workflows/overseas/university-rep/applications/:application_id/updates", success: "Update posted to the student and counselor.", pathFields: ["application_id"], fields: [{ name: "application_id", label: "Application reference", type: "text", required: true }, { name: "message", label: "Update message", type: "textarea", required: true }] }];
  // AGT-003-AC02: set/adjust the amount on a commission (typically a system-triggered
  // "estimated" row with amount=0, since no fixed commission rate is confirmed).
  // AGT-004-AC01: approve payout on a commission the Agent has already claimed -- the
  // Admin who created an admin-manual commission cannot also approve its own payout
  // (enforced server-side, AGT-004-AC02).
  if (role === "overseas_admin" && section === "commissions") return [
    { title: "Set/adjust commission amount", endpoint: "/api/v1/workflows/overseas/agent/commissions/:commission_id", method: "PATCH", success: "Commission amount updated.", pathFields: ["commission_id"], fields: [{ name: "commission_id", label: "Commission reference", type: "text", required: true }, { name: "amount", label: "Amount", type: "number", required: true }, { name: "currency", label: "Currency (leave blank to keep current)" }] },
    { title: "Approve commission payout", endpoint: "/api/v1/overseas-admin/commissions/:commission_id/approve-payout", success: "Payout approved -- commission marked paid.", pathFields: ["commission_id"], fields: [{ name: "commission_id", label: "Commission reference (must be claimed)", type: "text", required: true }] },
  ];
  return [];
}

// Mirrors the `allowed_by_division` allow-list `POST /admin/users` enforces server-side
// (apps/api/app/api/admin.py) -- keeps the dropdown from ever offering a role the backend
// would 422 on.
const ROLES_BY_DIVISION: Record<string, string[]> = {
  it: ["it_student", "trainer", "placement_team", "hr_team", "it_admin"],
  overseas: ["overseas_student", "counselor", "university_rep", "agent", "overseas_admin"],
  global: ["super_admin"],
};

// RAID.md I-31 (ADM-001 follow-up): `it_admin`/`overseas_admin` can never create outside
// their own division (`admin.py`'s division-lock gate 403s first) -- offering the other
// division here was a dead-end option, not a real choice. `super_admin` is exempt from
// that gate server-side, so it alone gets all three divisions, "global" included, closing
// the pre-existing gap where creating another super_admin had no reachable UI path at all.
function createUserDivisionOptions(user: User) {
  return user.role === "super_admin" ? options(["it", "overseas", "global"]) : options([user.division]);
}

function createUserRoleOptions(user: User) {
  const roles = user.role === "super_admin" ? [...ROLES_BY_DIVISION.it, ...ROLES_BY_DIVISION.overseas, ...ROLES_BY_DIVISION.global] : ROLES_BY_DIVISION[user.division] || [];
  return options(roles);
}

function adminSpecs(user: User, section: string): ActionSpec[] {
  if (["users", "students", "trainers", "counselors", "staff"].includes(section)) return [{ title: "Create user", endpoint: "/api/v1/admin/users", success: "User created.", fields: [{ name: "full_name", label: "Full name", required: true }, { name: "email", label: "Email", required: true }, { name: "phone", label: "Phone" }, { name: "division", label: "Division", type: "select", required: true, defaultValue: user.division === "global" ? "it" : user.division, options: createUserDivisionOptions(user) }, { name: "role", label: "Role", type: "select", required: true, options: createUserRoleOptions(user) }] }];
  if (section === "programs") return [{ title: "Create program", endpoint: "/api/v1/admin/programs", success: "Program created.", fields: [{ name: "slug", label: "Slug", required: true }, { name: "category", label: "Category", required: true }, { name: "title", label: "Title", required: true }, { name: "summary", label: "Summary", type: "textarea" }, { name: "duration", label: "Duration", required: true }, { name: "fees", label: "Fees", type: "number", required: true }, { name: "eligibility", label: "Eligibility", type: "textarea" }, { name: "curriculum", label: "Curriculum (comma separated)", parse: "list" }] }];
  // "batches" is handled by AdminBatchCreatePanel (ADM-003) -- see showBatchCreate below.
  if (section === "payments") return [
    { title: "Create payment due", endpoint: "/api/v1/admin/payments", success: "Payment due created.", fields: [{ name: "user_id", label: "User reference", type: "text", required: true }, { name: "reference_type", label: "Fee type", defaultValue: "service_fee" }, { name: "amount", label: "Amount", type: "number", required: true }, { name: "currency", label: "Currency", defaultValue: "INR" }, { name: "provider", label: "Provider", type: "select", defaultValue: "razorpay", options: options(["razorpay", "manual"]) }, { name: "status", label: "Status", type: "select", defaultValue: "pending", options: options(["pending", "paid"]) }, { name: "due_date", label: "Due date", type: "date" }] },
    { title: "Apply discount", description: "Lowers a still-unpaid fee -- never a paid one. Requires a written reason.", endpoint: "/api/v1/admin/payments/:payment_id/discount", success: "Discount applied.", pathFields: ["payment_id"], fields: [{ name: "payment_id", label: "Payment reference", type: "text", required: true }, { name: "amount", label: "New (discounted) amount", type: "number", required: true }, { name: "reason", label: "Reason", type: "textarea", required: true }] },
  ];
  // "leads" is handled by AdminLeadManagementPanel (ADM-002) -- see showLeadManagement below.
  // RAID.md I-32: "universities" is now handled by AdminUniversityCreatePanel (a real
  // country picker) instead of this generic form -- see WorkflowPanel's render below.
  if (section === "recruiters") return [{ title: "Create recruiter requirement", endpoint: "/api/v1/workflows/it/jobs", success: "Recruiter and job requirement recorded.", fields: [{ name: "company_name", label: "Company name", required: true }, { name: "company_website", label: "Company website" }, { name: "title", label: "Role", required: true }, { name: "location", label: "Location", defaultValue: "Remote" }, { name: "description", label: "Description", type: "textarea" }, { name: "skills", label: "Skills (comma separated)", parse: "list" }, { name: "closes_on", label: "Closes on", type: "date" }] }];
  if (section === "content") return [{ title: "Publish content page", endpoint: "/api/v1/cms/pages/:division/:slug", method: "PUT", success: "Content page saved.", pathFields: ["division", "slug"], fields: [{ name: "division", label: "Division", type: "select", required: true, options: options(["it", "overseas"]) }, { name: "slug", label: "Page slug", required: true }, { name: "title", label: "Page title", required: true }, { name: "body", label: "Page body", type: "textarea", required: true }, { name: "published", label: "Published", type: "checkbox", parse: "boolean", defaultValue: true }] }];
  if (section === "blogs") return [{ title: "Create blog post", endpoint: "/api/v1/cms/posts", success: "Blog post saved.", fields: [{ name: "division", label: "Division", type: "select", required: true, options: options(["it", "overseas"]) }, { name: "slug", label: "Slug", required: true }, { name: "title", label: "Title", required: true }, { name: "category", label: "Category", defaultValue: "News" }, { name: "summary", label: "Summary", type: "textarea" }, { name: "body", label: "Article body", type: "textarea", required: true }, { name: "published", label: "Published", type: "checkbox", parse: "boolean", defaultValue: true }] }, { title: "Update blog status", endpoint: "/api/v1/cms/posts/:post_id", method: "PATCH", success: "Blog post updated.", pathFields: ["post_id"], fields: [{ name: "post_id", label: "Post reference", type: "text", required: true }, { name: "published", label: "Published", type: "checkbox", parse: "boolean" }] }];
  // PUB-005: GalleryItem had no admin publish path at all before this feature -- only a
  // public read and seed-time direct DB inserts existed.
  if (section === "gallery") return [{ title: "Publish gallery item", endpoint: "/api/v1/cms/gallery", success: "Gallery item saved.", fields: [{ name: "division", label: "Division", type: "select", required: true, options: options(["it", "overseas"]) }, { name: "title", label: "Title", required: true }, { name: "image_url", label: "Image URL", required: true }, { name: "alt_text", label: "Alt text" }, { name: "category", label: "Category", defaultValue: "General" }, { name: "published", label: "Published", type: "checkbox", parse: "boolean", defaultValue: true }] }, { title: "Update gallery item", endpoint: "/api/v1/cms/gallery/:item_id", method: "PATCH", success: "Gallery item updated.", pathFields: ["item_id"], fields: [{ name: "item_id", label: "Gallery item reference", type: "text", required: true }, { name: "title", label: "Title" }, { name: "image_url", label: "Image URL" }, { name: "category", label: "Category" }, { name: "published", label: "Published", type: "checkbox", parse: "boolean" }] }];
  if (section === "events") return [{ title: "Create event", endpoint: "/api/v1/cms/events", success: "Event created.", fields: [{ name: "division", label: "Division", type: "select", required: true, options: options(["it", "overseas"]) }, { name: "title", label: "Title", required: true }, { name: "event_type", label: "Type", defaultValue: "Seminar" }, { name: "starts_at", label: "Starts", type: "datetime-local", required: true }, { name: "location", label: "Location", defaultValue: "Online" }, { name: "description", label: "Description", type: "textarea" }, { name: "registration_url", label: "Registration URL" }] }, { title: "Update event", endpoint: "/api/v1/cms/events/:event_id", method: "PATCH", success: "Event updated.", pathFields: ["event_id"], fields: [{ name: "event_id", label: "Event reference", type: "text", required: true }, { name: "title", label: "Title" }, { name: "starts_at", label: "Starts", type: "datetime-local" }, { name: "location", label: "Location" }, { name: "registration_url", label: "Registration URL" }] }];
  if (section === "applications") return [{ title: "Update overseas application", endpoint: "/api/v1/workflows/overseas/applications/:application_id", method: "PATCH", success: "Application updated.", pathFields: ["application_id"], fields: [{ name: "application_id", label: "Overseas application reference", type: "text", required: true }, { name: "status", label: "Status", type: "select", required: true, options: applicationStatuses }, { name: "application_reference", label: "Reference" }, { name: "offer_letter_url", label: "Offer letter URL" }, { name: "next_action", label: "Next action", type: "textarea" }] }];
  if (section === "notifications") return [{ title: "Send notification", endpoint: "/api/v1/communications/notify", success: "Notification queued.", fields: [{ name: "user_id", label: "Recipient user reference", type: "text", required: true }, { name: "title", label: "Title", required: true }, { name: "body", label: "Message", type: "textarea", required: true }, { name: "channels", label: "Channels (comma separated)", parse: "list", defaultValue: "email" }, { name: "action_url", label: "Portal action URL" }] }];
  return [];
}

function specsFor(user: User, section: string): ActionSpec[] {
  if (["it_student", "overseas_student"].includes(user.role)) return studentSpecs(user, section);
  if (user.role === "trainer") return trainerSpecs(section);
  if (["placement_team", "hr_team"].includes(user.role)) return placementSpecs(section);
  if (user.role === "agent") return agentSpecs(section);
  if (["counselor", "university_rep"].includes(user.role)) return overseasOperationsSpecs(user.role, section);
  if (["it_admin", "overseas_admin", "super_admin"].includes(user.role)) {
    const operational = user.role === "overseas_admin" ? overseasOperationsSpecs(user.role, section) : [];
    return operational.length ? operational : adminSpecs(user, section);
  }
  return [];
}

export default function WorkflowPanel({ user, section }: { user: User; section: string }) {
  const specs = specsFor(user, section);
  const showAssessment = user.role === "it_student" && section === "examinations";
  const showDocuments = section === "documents" && ["overseas_student", "agent"].includes(user.role);
  const showDocumentDownload = user.role === "overseas_student" && section === "documents";
  const showCounselorDocumentReview = user.role === "counselor" && section === "documents";
  const showVisaChecklist = user.role === "overseas_student" && section === "visa-status";
  const showCounselorVisa = user.role === "counselor" && section === "visa";
  const showAgentApproval = user.role === "overseas_admin" && section === "agents";
  const showBatchPicker = user.role === "it_student" && section === "course";
  const showLiveClasses = user.role === "it_student" && section === "course";
  const showAgreementConsent = user.role === "it_student" && section === "course";
  const showAssignmentSubmission = user.role === "it_student" && ["assignments", "projects"].includes(section);
  const showCertificateDownload = user.role === "it_student" && section === "certificates";
  const showFeedback = user.role === "it_student" && section === "feedback";
  const showQuestions = user.role === "it_student" && section === "questions";
  const showProfileDocuments = user.role === "it_student" && section === "profile";
  const showOverseasApply = user.role === "overseas_student" && section === "applications";
  const showScholarshipApply = user.role === "overseas_student" && section === "scholarships";
  const showFeePayment = (user.role === "it_student" && section === "fees") || (user.role === "overseas_student" && section === "payments");
  const showCounselorEvaluation = user.role === "counselor" && ["applications", "students"].includes(section);
  const showCounselorChat = user.role === "counselor" && section === "counselor-chat";
  const isAdmin = ["it_admin", "super_admin"].includes(user.role);
  // QA-009: the Overseas Admin provisions school staff, so they get the Manage users panel (setup status + Re-send)
  // on the `users` page too. The API already scopes every route to their division; the role/section-specific
  // directories stay IT/Super Admin only.
  const showUserManagement = (isAdmin && ["users", "students", "trainers", "employers", "counselors", "staff"].includes(section)) || (user.role === "overseas_admin" && section === "users");
  const showProgramManagement = isAdmin && section === "programs";
  const showLeadManagement = isAdmin && section === "leads";
  const showBatchCreate = isAdmin && section === "batches";
  const showEnrollmentReview = isAdmin && section === "enrollments";
  const showSupportQueue = isAdmin && section === "support";
  const showCertificateIssue = isAdmin && section === "certificates";
  const showPlacementCandidates = user.role === "placement_team" && section === "candidates";
  const showHrShortlists = user.role === "hr_team" && section === "shortlists";
  const showAuditExport = user.role === "super_admin" && section === "security-logs";
  // ENH-003: expired set-password links on the IT and Overseas admin dashboards (`PortalPage` always
  // renders this panel under the dashboard content). Independent of `isAdmin`, which excludes
  // overseas_admin. The Super Admin's own `/admin` page shows a tile and links to /admin/users.
  const showExpiredLinks = ["it_admin", "overseas_admin", "super_admin"].includes(user.role) && section === "dashboard";
  // RAID.md I-32: gated by the same role set `admin.py`'s `create_university` itself
  // enforces (`super_admin`/`overseas_admin`, not `it_admin` -- IT Admin's own nav has no
  // "universities" entry at all), not the narrower `isAdmin` constant above.
  const showUniversityCreate = ["overseas_admin", "super_admin"].includes(user.role) && section === "universities";
  const showAgentApplicationCreate = user.role === "agent" && section === "applications";
  const showSchoolCreate = ["overseas_admin", "super_admin"].includes(user.role) && section === "schools";
  const showSchoolStaffCreate = ["overseas_admin", "super_admin"].includes(user.role) && section === "school-staff";
  // DEC-SCOPE-018 -- Overseas Admin/Counselor (never school_coordinator) links a School
  // student to a real Overseas application, same section name as the School side's own
  // "school-applications" nav entry but a distinct role gate.
  const showSchoolApplications = ["overseas_admin", "counselor", "super_admin"].includes(user.role) && section === "school-applications";
  if (!specs.length && !showAssessment && !showDocuments && !showDocumentDownload && !showCounselorDocumentReview && !showVisaChecklist && !showCounselorVisa && !showAgentApproval && !showBatchPicker && !showLiveClasses && !showAgreementConsent && !showAssignmentSubmission && !showCertificateDownload && !showFeedback && !showQuestions && !showProfileDocuments && !showOverseasApply && !showScholarshipApply && !showFeePayment && !showCounselorEvaluation && !showCounselorChat && !showUserManagement && !showProgramManagement && !showLeadManagement && !showBatchCreate && !showEnrollmentReview && !showSupportQueue && !showCertificateIssue && !showPlacementCandidates && !showHrShortlists && !showAuditExport && !showUniversityCreate && !showAgentApplicationCreate && !showSchoolCreate && !showSchoolStaffCreate && !showSchoolApplications && !showExpiredLinks) return null;
  return <div className="portal-content action-center"><div className="workspace-head action-heading"><div><strong>Actions</strong><p>Changes are validated, permission checked, and written to the live workflow.</p></div><span className="badge">Operational</span></div><div className="action-grid">{showAgreementConsent && <AgreementConsentPanel/>}{showLiveClasses && <LiveClassesPanel userName={user.full_name} userEmail={user.email}/>}{showBatchPicker && <BatchSlotPicker/>}{showAssignmentSubmission && <AssignmentSubmissionPanel section={section as "assignments" | "projects"}/>}{showCertificateDownload && <CertificateDownloadPanel/>}{showFeedback && <FeedbackSubmissionPanel/>}{showQuestions && <QuestionAskPanel/>}{showProfileDocuments && <ProfileDocumentUpload/>}{showOverseasApply && <OverseasApplyPanel/>}{showScholarshipApply && <ScholarshipApplyPanel/>}{showFeePayment && <FeePaymentPanel/>}{showCounselorEvaluation && <CounselorEvaluationPanel/>}{showCounselorChat && <CounselorChatPanel userId={user.id}/>}{showCounselorDocumentReview && <CounselorDocumentReviewPanel/>}{showVisaChecklist && <VisaChecklistPanel/>}{showCounselorVisa && <CounselorVisaPanel/>}{showAgentApproval && <AgentApprovalPanel/>}{showUserManagement && <AdminUserManagementPanel section={section}/>}{showProgramManagement && <AdminProgramManagementPanel/>}{showLeadManagement && <AdminLeadManagementPanel/>}{showBatchCreate && <AdminBatchCreatePanel/>}{showEnrollmentReview && <AdminEnrollmentReviewPanel/>}{showSupportQueue && <SupportTicketQueuePanel/>}{showCertificateIssue && <AdminCertificatePanel/>}{showPlacementCandidates && <PlacementCandidatePanel/>}{showHrShortlists && <HrShortlistPanel/>}{showAuditExport && <AuditExportPanel/>}{showExpiredLinks && <AdminExpiredLinksPanel/>}{showUniversityCreate && <AdminUniversityCreatePanel/>}{showAgentApplicationCreate && <AgentApplicationCreatePanel/>}{showSchoolCreate && <AdminSchoolCreatePanel/>}{showSchoolStaffCreate && <AdminSchoolStaffPanel/>}{showSchoolApplications && <AdminSchoolApplicationsPanel/>}{specs.map(spec => <ActionForm key={spec.title} spec={spec}/>)}{showAssessment && <AssessmentForm/>}{showDocuments && <DocumentUpload user={user}/>}{showDocumentDownload && <DocumentDownloadPanel/>}</div></div>;
}
