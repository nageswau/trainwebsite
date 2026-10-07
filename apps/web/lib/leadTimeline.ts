// tel-015 (DEC-SCOPE-114): the merged lead timeline -- the row the API sends (`services/lead_timeline.py`) and how each kind reads. Keys
// arrive for calls, messages, follow-ups and appointments; the labels are the ones their own sections already use. Display only.
import { STATUS_LABEL as APPOINTMENT_STATUS, type AppointmentStatus } from "@/lib/leadAppointments";
import { milestoneKind, statusText, type MilestoneKind } from "@/lib/leadHandover";
import { outcomeLabel } from "@/lib/telecallerCalls";
import { SOURCE_LABEL } from "@/lib/telecallerCatalogue";
import { reasonLabel } from "@/lib/telecallerFollowUps";
import type { PersonRef } from "@/lib/telecallerLeads";

export type TimelineKind =
  | "created" | "enquiry" | "stage" | "priority" | "assignment" | "handover" | "student_link" | "call" | "message" | "follow_up" | "appointment"
  | "milestone";
export type TimelineRow = {
  id: string; kind: TimelineKind; at: string; actor: PersonRef | null; from_value: string; from_label: string; to_value: string; to_label: string;
  reason: string | null; event?: string | null; subject?: string | null; status?: string | null; duration_seconds?: number | null;
  scheduled_for?: string | null;
};
export type TimelineEntry = {
  badge: string; tone: string; title: string; meta: string[]; when: { label: string; value: string } | null; detail: string | null;
};

export const TIMELINE_LIMIT = 50;
export const EXCERPT = 200; // TM2: the API cuts free text here; the full text stays in the Calls / Messages / Follow-ups sections

const TONE = { stage: "var(--blue)", contact: "var(--green)", plan: "var(--amber)", owner: "var(--navy)", stop: "var(--red)" };
const METHOD: Record<string, string> = { manual: "Manual", round_robin: "Round robin", product_rule: "Product rule", location_rule: "Location rule" };
const APPOINTMENT_TYPE: Record<string, string> = {
  career_counselling: "Career counselling", it_course_counselling: "IT course counselling", overseas_counselling: "Overseas counselling",
  university_counselling: "University counselling",
};
const EMAIL_TITLE: Record<string, string> = { queued: "Email sending", sending: "Email sending", retrying: "Email delayed", sent: "Email sent", failed: "Email failed" };

const source = (key: string) => SOURCE_LABEL[key] ?? key;
const humanise = (key: string) => (key ? statusText(key) : key);
const compact = (parts: (string | null | undefined | false)[]) => parts.filter((p): p is string => !!p);

/** "2:05" -- a call's length in minutes and seconds (tel-010 keeps seconds). */
export function duration(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Who did it. No actor: the website for its own enquiries, otherwise the system (round robin, auto stages, milestones). */
export function actorName(row: TimelineRow): string {
  if (row.actor) return row.actor.full_name;
  if (row.kind === "enquiry" || (row.kind === "created" && row.from_value === "website")) return "Website form";
  return "System";
}

function stageTitle(row: TimelineRow): string {
  if (row.event === "returned") return "Returned to the telecaller"; // tel-018 QA-03
  if (row.event === "converted") return "Converted";
  return `Stage: ${row.from_label} → ${row.to_label}`;
}

function assignmentTitle(row: TimelineRow): string {
  if (!row.to_value) return row.from_value ? `Unassigned from ${row.from_label}` : "Unassigned";
  return row.from_value ? `Reassigned from ${row.from_label} to ${row.to_label}` : `Assigned to ${row.to_label}`;
}

function appointmentTitle(row: TimelineRow): string {
  if (!row.from_value) return "Counselling appointment booked";
  const status = APPOINTMENT_STATUS[row.to_value as AppointmentStatus] ?? humanise(row.to_value);
  return `Counselling appointment ${status.toLowerCase()}`;
}

export function timelineEntry(row: TimelineRow): TimelineEntry {
  const base = { meta: [] as string[], when: null, detail: row.reason ? (row.reason.length >= EXCERPT ? `${row.reason}…` : row.reason) : null };
  switch (row.kind) {
    case "created":
      return { ...base, badge: "Lead", tone: TONE.owner, title: "Lead created", meta: compact([`Source: ${source(row.from_value)}`, row.to_value]) };
    case "enquiry":
      return { ...base, badge: "Enquiry", tone: TONE.owner, title: `New enquiry: ${row.to_label}`, meta: [`Source: ${source(row.from_value)}`] };
    case "stage":
      return { ...base, badge: "Stage", tone: row.event === "converted" ? TONE.contact : TONE.stage, title: stageTitle(row) };
    case "priority":
      return { ...base, badge: "Priority", tone: TONE.stage, title: `Priority: ${row.from_label} → ${row.to_label}` };
    case "assignment":
      return { ...base, badge: "Telecaller", tone: TONE.owner, title: assignmentTitle(row), meta: compact([row.event && (METHOD[row.event] ?? humanise(row.event))]) };
    case "handover":
      return { ...base, badge: "Counselor", tone: TONE.owner,
        title: row.from_value ? `Counselor changed from ${row.from_label} to ${row.to_label}` : `Handed over to ${row.to_label}` };
    case "student_link":
      return { ...base, badge: "Student", tone: row.event === "unlinked" ? TONE.stop : TONE.contact,
        title: `${row.event === "unlinked" ? "Student unlinked" : "Student linked"}: ${row.to_label}` };
    case "call":
      return { ...base, badge: "Call", tone: TONE.contact, title: `${row.from_value === "incoming" ? "Incoming" : "Outgoing"} call: ${outcomeLabel(row.to_value)}`,
        meta: compact([row.duration_seconds != null && `Duration ${duration(row.duration_seconds)}`]) };
    case "message": {
      const email = row.from_value === "email";
      return { ...base, badge: email ? "Email" : "WhatsApp", tone: row.status === "failed" ? TONE.stop : TONE.contact,
        title: email ? EMAIL_TITLE[row.status ?? "queued"] ?? "Email" : "WhatsApp sent",
        meta: compact([row.to_value || "Custom message", email && row.subject && `Subject: ${row.subject}`]) };
    }
    case "follow_up": {
      const verb = row.event === "done" ? "done" : row.event === "cancelled" ? "cancelled" : "scheduled";
      return { ...base, badge: "Follow-up", tone: verb === "cancelled" ? TONE.stop : TONE.plan, title: `Follow-up ${verb}: ${reasonLabel(row.from_value)}`,
        when: verb === "scheduled" && row.scheduled_for ? { label: "Due", value: row.scheduled_for } : null };
    }
    case "appointment":
      return { ...base, badge: "Appointment", tone: ["cancelled", "no_show"].includes(row.to_value) ? TONE.stop : TONE.plan, title: appointmentTitle(row),
        meta: compact([row.event && (APPOINTMENT_TYPE[row.event] ?? humanise(row.event)), row.subject]),
        when: row.scheduled_for ? { label: "For", value: row.scheduled_for } : null };
    case "milestone":
      return { ...base, badge: "Milestone", tone: TONE.contact, title: `${milestoneKind(row.event as MilestoneKind)}: ${row.to_label}`,
        meta: compact([row.status && statusText(row.status), row.subject]) };
    default:
      return { ...base, badge: "Activity", tone: TONE.stage, title: humanise(String((row as { kind: string }).kind)) };
  }
}
