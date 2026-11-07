// rec-027 (spec §2): a company's and a candidate's timeline -- the row the API sends (`services/recruiter_timeline.py`) and how each kind
// reads. Status-like kinds arrive with server labels; meeting types, follow-up reasons, share channels / responses and interview rounds are
// keys labelled here with the labels their own sections use. Display only: the API decides who reads it and what it holds.
import { EMAIL_TITLE, EXCERPT, duration, type TimelineEntry } from "@/lib/leadTimeline";
import { candidateUrl } from "@/lib/recruiterCandidates";
import { taskTypeLabel } from "@/lib/recruiterCandidateTasks";
import { COMPANIES_URL } from "@/lib/recruiterCompanies";
import { reasonLabel } from "@/lib/recruiterFollowUps";
import { ROUNDS } from "@/lib/recruiterInterviews";
import { meetingTypeLabel } from "@/lib/recruiterMeetings";
import { linkedinTitle } from "@/lib/recruiterMessages";
import { CHANNELS, RESPONSES } from "@/lib/recruiterShares";

type Kind = "stage" | "call" | "message" | "meeting" | "follow_up" | "requirement" | "share" | "share_response" | "contract" | "application" | "interview" | "offer"
  | "note" | "task" | "assignment" | "profile" | "screening" // hrc-016 (T9): the candidate timeline's new kinds
  | "message_reply" | "contact_status"; // pob-005 (D10): a logged reply; a contact's status change (the per-contact view only)
export type RecTimelineRow = {
  id: string; kind: Kind; at: string; actor: { id: string; full_name: string } | null; event: string | null; from_value: string; from_label: string;
  to_value: string; to_label: string; subject: string | null; status: string | null; reason: string | null; context: string | null;
  duration_seconds: number | null; scheduled_for: string | null;
};

export const companyTimelineUrl = (companyId: string) => `${COMPANIES_URL}/${encodeURIComponent(companyId)}/timeline`;
export const candidateTimelineUrl = (candidateId: string) => candidateUrl(candidateId, "/timeline");

const TONE = { stage: "var(--blue)", contact: "var(--green)", plan: "var(--amber)", owner: "var(--navy)", stop: "var(--red)" };
const labelOf = (list: readonly { key: string; label: string }[], key: string | null) => list.find((o) => o.key === key)?.label ?? key ?? "";
const compact = (parts: (string | null | undefined | false)[]) => parts.filter((p): p is string => !!p);
const move = (row: RecTimelineRow) => `${row.from_label} → ${row.to_label}`;
const FOLLOW_UP_VERB: Record<string, string> = { scheduled: "added", done: "done", cancelled: "cancelled" };
const CONTRACT_TITLE: Record<string, (row: RecTimelineRow) => string> = {
  created: (r) => `Contract created (${r.to_label})`, renewed: (r) => `Contract renewed (${r.to_label})`, updated: () => "Contract edited",
  document: () => "Contract document uploaded", status: (r) => `Contract: ${move(r)}`,
};
const OFFER_TITLE: Record<string, (row: RecTimelineRow) => string> = {
  created: (r) => `Offer recorded (${r.to_label})`, status: (r) => `Offer: ${move(r)}`, revised: () => "Offer revised", letter: () => "Offer letter uploaded",
  joining: () => "Joining details updated", joined: () => "Joined", did_not_join: () => "Did not join", proof: () => "Joining proof uploaded",
};

const TASK_VERB: Record<string, string> = { scheduled: "assigned", done: "done", cancelled: "cancelled" };
// pob-005 (D4/D5): what moved a contact's status
const STATUS_CAUSE: Record<string, string> = {
  call: "After a call", message: "After a message", share: "After a profile share", interview: "After an interview invite", reply: "After a reply",
  meeting: "After a meeting was scheduled", manual: "Changed by hand",
};
const ASSIGNMENT_REASON: Record<string, string> = { create: "When the candidate was added", reassign: "Team reassignment", route: "Automatic routing" }; // hrc-024

/** hrc-016: an ownership change (hrc-012's history) -- who held it before and who holds it now. */
function assignmentTitle(row: RecTimelineRow): string {
  if (row.event === "collaborator_added") return `Collaborator added: ${row.to_label}`;
  if (row.event === "collaborator_removed") return `Collaborator removed: ${row.from_label}`;
  const role = row.event === "placement_officer" ? "Placement officer" : "Primary recruiter";
  return `${role}: ${row.from_label || "None"} → ${row.to_label || "None"}`;
}

/** hrc-016: the candidate's own record changes -- an edit says how many fields changed (the Change history card has the values). */
function profileTitle(row: RecTimelineRow): string {
  const n = Number(row.to_value);
  switch (row.event) {
    case "create": return "Candidate added";
    case "update": return n > 0 ? `Profile edited (${n} field${n === 1 ? "" : "s"})` : "Profile edited";
    case "archive": return "Candidate archived";
    case "restore": return "Candidate restored";
    case "merge": return `${row.subject ?? "A duplicate"} merged into this candidate`;
    case "merged_into": return `Merged into ${row.subject ?? "another candidate"}`;
    default: return "Profile changed";
  }
}

function stageTitle(row: RecTimelineRow): string {
  if (row.event === "lost") return "Marked Lost";
  if (row.event === "inactive") return "Marked Inactive";
  if (row.event === "active_client") return "Became an Active Client";
  if (row.event === "repeat_business") return "Became Repeat Business";
  if (row.event === "reopen") return `Reopened at ${row.to_label}`;
  return `Stage: ${move(row)}`;
}

function interviewTitle(row: RecTimelineRow): string {
  if (row.event === "status") return `Interview: ${move(row)}`;
  if (row.event === "details") return `Interview details changed: ${labelOf(ROUNDS, row.status)}`; // hrc-028 (I4): a link or location replaced
  return `Interview ${row.event === "rescheduled" ? "rescheduled" : "scheduled"}: ${labelOf(ROUNDS, row.status)}`;
}

function shareTitle(row: RecTimelineRow): string {
  const channel = labelOf(CHANNELS, row.event);
  if (!row.to_value) return `Profile shared by ${channel}`; // a candidate's entry: this one profile
  const count = Number(row.to_value);
  return `${count} profile${count === 1 ? "" : "s"} shared by ${channel}`;
}

/** Who did it. No actor: the system (an engine stage move, a legacy row). */
export function timelineActor(row: RecTimelineRow): string {
  return row.actor ? row.actor.full_name : "System";
}

export function timelineEntry(row: RecTimelineRow): TimelineEntry {
  const base = { meta: [] as string[], when: null, detail: row.reason ? (row.reason.length >= EXCERPT ? `${row.reason}…` : row.reason) : null };
  const where = compact([row.subject, row.context]); // a candidate entry's requirement and company
  switch (row.kind) {
    case "stage":
      return { ...base, badge: "Stage", tone: row.event === "lost" ? TONE.stop : TONE.stage, title: stageTitle(row) };
    case "call":
      return { ...base, badge: "Call", tone: TONE.contact, title: `${row.event === "incoming" ? "Incoming" : "Outgoing"} call: ${row.from_label}`,
        meta: compact([row.to_label && `With ${row.to_label}`, row.duration_seconds != null && `Duration ${duration(row.duration_seconds)}`]) };
    case "message": {
      if (row.event === "linkedin") // pob-007 A2: the action travels in `status`
        return { ...base, badge: "LinkedIn", tone: TONE.contact, title: linkedinTitle(row.status),
          meta: compact([row.to_label && `To ${row.to_label}`, row.from_value || (row.status === "message" ? "Custom message" : null)]) };
      const email = row.event === "email";
      return { ...base, badge: email ? "Email" : "WhatsApp", tone: row.status === "failed" ? TONE.stop : TONE.contact,
        title: email ? EMAIL_TITLE[row.status ?? "queued"] ?? "Email" : "WhatsApp sent",
        meta: compact([row.to_label && `To ${row.to_label}`, row.from_value || "Custom message", email && row.subject && `Subject: ${row.subject}`]) };
    }
    case "message_reply":
      return { ...base, badge: "Reply", tone: TONE.contact, title: `${row.event === "email" ? "Email" : "WhatsApp"} reply received`,
        meta: compact([row.to_label && `From ${row.to_label}`, row.subject && `Subject: ${row.subject}`]) };
    case "contact_status":
      return { ...base, badge: "Status", tone: row.to_value === "do_not_contact" || row.to_value === "not_interested" ? TONE.stop : TONE.stage,
        title: `Status: ${move(row)}`, meta: compact([STATUS_CAUSE[row.event ?? ""]]) };
    case "meeting": {
      const open = row.event === "scheduled" || row.event === "rescheduled";
      return { ...base, badge: "Meeting", tone: row.event === "cancelled" ? TONE.stop : TONE.plan,
        title: `Meeting ${row.event ?? ""}: ${meetingTypeLabel(row.from_value)}`, meta: compact([row.subject]),
        when: open && row.scheduled_for ? { label: "For", value: row.scheduled_for } : null };
    }
    case "follow_up":
      return { ...base, badge: "Follow-up", tone: row.event === "cancelled" ? TONE.stop : TONE.plan,
        title: `Follow-up ${FOLLOW_UP_VERB[row.event ?? ""] ?? row.event}: ${reasonLabel(row.from_value)}`,
        when: row.event === "scheduled" && row.scheduled_for ? { label: "Due", value: row.scheduled_for } : null };
    case "requirement":
      return { ...base, badge: "Requirement", tone: TONE.owner, meta: compact([row.subject]),
        title: row.from_value ? `Requirement: ${move(row)}` : `Requirement added (${row.to_label})` };
    case "share":
      return { ...base, badge: "Profiles shared", tone: TONE.contact, title: shareTitle(row), meta: compact([row.subject, row.to_label && `To ${row.to_label}`, row.context]) };
    case "share_response":
      return { ...base, badge: "Response", tone: row.event === "not_interested" ? TONE.stop : TONE.contact,
        title: `Company response: ${labelOf(RESPONSES, row.event)}`, meta: compact([row.to_label, row.subject, row.context]) };
    case "contract":
      return { ...base, badge: "Contract", tone: TONE.owner, title: (CONTRACT_TITLE[row.event ?? ""] ?? (() => "Contract"))(row), meta: compact([row.subject]) };
    case "application":
      return { ...base, badge: "Application", tone: TONE.stage, meta: where,
        title: row.from_value ? `Application: ${move(row)}` : `Added to requirement (${row.to_label})` };
    case "interview":
      return { ...base, badge: "Interview", tone: TONE.plan, title: interviewTitle(row), meta: where,
        when: row.scheduled_for ? { label: "For", value: row.scheduled_for } : null };
    case "offer":
      return { ...base, badge: "Offer", tone: row.event === "did_not_join" ? TONE.stop : TONE.owner, title: (OFFER_TITLE[row.event ?? ""] ?? (() => "Offer"))(row), meta: where };
    case "note":
      return { ...base, badge: "Note", tone: TONE.owner, title: "Note added" };
    case "task":
      return { ...base, badge: "Task", tone: row.event === "cancelled" ? TONE.stop : TONE.plan,
        title: `Task ${TASK_VERB[row.event ?? ""] ?? row.event}: ${taskTypeLabel(row.from_value)}`,
        meta: compact([row.subject, row.to_label && `Assigned to ${row.to_label}`]),
        when: row.event === "scheduled" && row.scheduled_for ? { label: "Due", value: row.scheduled_for } : null };
    case "assignment":
      return { ...base, badge: "Ownership", tone: TONE.owner, title: assignmentTitle(row), meta: compact([ASSIGNMENT_REASON[row.status ?? ""]]) };
    case "profile":
      return { ...base, badge: "Profile", tone: row.event === "archive" ? TONE.stop : TONE.stage, title: profileTitle(row) };
    case "screening":
      return { ...base, badge: "Screening", tone: row.to_value === "rejected" ? TONE.stop : TONE.stage, title: `Screening: ${row.to_label}`, meta: where };
    default:
      return { ...base, badge: "Activity", tone: TONE.stage, title: String((row as { kind: string }).kind) };
  }
}
