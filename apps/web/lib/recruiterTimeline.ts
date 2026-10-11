// rec-027 (spec §2): a company's and a candidate's timeline -- the row the API sends (`services/recruiter_timeline.py`) and how each kind
// reads. Status-like kinds arrive with server labels; meeting types, follow-up reasons, share channels / responses and interview rounds are
// keys labelled here with the labels their own sections use. Display only: the API decides who reads it and what it holds.
import { EMAIL_TITLE, EXCERPT, duration, type TimelineEntry } from "@/lib/leadTimeline";
import { candidateUrl } from "@/lib/recruiterCandidates";
import { COMPANIES_URL } from "@/lib/recruiterCompanies";
import { reasonLabel } from "@/lib/recruiterFollowUps";
import { ROUNDS } from "@/lib/recruiterInterviews";
import { meetingTypeLabel } from "@/lib/recruiterMeetings";
import { CHANNELS, RESPONSES } from "@/lib/recruiterShares";

type Kind = "stage" | "call" | "message" | "meeting" | "follow_up" | "requirement" | "share" | "share_response" | "contract" | "application" | "interview" | "offer";
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

function stageTitle(row: RecTimelineRow): string {
  if (row.event === "lost") return "Marked Lost";
  if (row.event === "reopen") return `Reopened at ${row.to_label}`;
  return `Stage: ${move(row)}`;
}

function interviewTitle(row: RecTimelineRow): string {
  if (row.event === "status") return `Interview: ${move(row)}`;
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
      const email = row.event === "email";
      return { ...base, badge: email ? "Email" : "WhatsApp", tone: row.status === "failed" ? TONE.stop : TONE.contact,
        title: email ? EMAIL_TITLE[row.status ?? "queued"] ?? "Email" : "WhatsApp sent",
        meta: compact([row.to_label && `To ${row.to_label}`, row.from_value || "Custom message", email && row.subject && `Subject: ${row.subject}`]) };
    }
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
    default:
      return { ...base, badge: "Activity", tone: TONE.stage, title: String((row as { kind: string }).kind) };
  }
}
