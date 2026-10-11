import { describe, expect, it } from "vitest";

import { candidateTimelineUrl, companyTimelineUrl, timelineActor, timelineEntry, type RecTimelineRow } from "@/lib/recruiterTimeline";

const ME = { id: "u1", full_name: "Asha Menon" };
const row = (over: Partial<RecTimelineRow>): RecTimelineRow => ({
  id: "r1", kind: "stage", at: "2026-10-05T05:00:00Z", actor: ME, event: null, from_value: "", from_label: "", to_value: "", to_label: "",
  subject: null, status: null, reason: null, context: null, duration_seconds: null, scheduled_for: null, ...over,
});

describe("recruiterTimeline (rec-027)", () => {
  it("builds the timeline URLs", () => {
    expect(companyTimelineUrl("c 1")).toBe("/api/v1/recruiter/companies/c%201/timeline");
    expect(candidateTimelineUrl("k 1")).toBe("/api/v1/recruiter/candidates/k%201/timeline");
  });

  it("reads a call then an email", () => {
    expect(timelineEntry(row({ kind: "call", event: "outgoing", from_value: "connected", from_label: "Connected", to_label: "Priya", duration_seconds: 125 })))
      .toMatchObject({ badge: "Call", title: "Outgoing call: Connected", meta: ["With Priya", "Duration 2:05"] });
    expect(timelineEntry(row({ kind: "call", event: "incoming", from_value: "busy", from_label: "Busy" })))
      .toMatchObject({ title: "Incoming call: Busy", meta: [] });
    expect(timelineEntry(row({ kind: "message", event: "email", status: "sent", subject: "Profiles", to_label: "Priya", from_value: "Intro" })))
      .toMatchObject({ badge: "Email", title: "Email sent", meta: ["To Priya", "Intro", "Subject: Profiles"] });
    expect(timelineEntry(row({ kind: "message", event: "whatsapp" }))).toMatchObject({ badge: "WhatsApp", title: "WhatsApp sent", meta: ["Custom message"] });
  });

  it("reads stage, meeting and follow-up entries with their labels", () => {
    expect(timelineEntry(row({ kind: "stage", event: "manual", from_label: "New Lead", to_label: "Contacted" })).title).toBe("Stage: New Lead → Contacted");
    expect(timelineEntry(row({ kind: "stage", event: "lost" })).title).toBe("Marked Lost");
    expect(timelineEntry(row({ kind: "stage", event: "reopen", to_label: "Contacted" })).title).toBe("Reopened at Contacted");
    expect(timelineEntry(row({ kind: "meeting", event: "scheduled", from_value: "hr_meeting", subject: "RMT-000001", scheduled_for: "2026-10-10T05:00:00Z" })))
      .toMatchObject({ badge: "Meeting", title: "Meeting scheduled: HR meeting", meta: ["RMT-000001"], when: { label: "For", value: "2026-10-10T05:00:00Z" } });
    expect(timelineEntry(row({ kind: "meeting", event: "completed", from_value: "hr_meeting", scheduled_for: "2026-10-10T05:00:00Z" })))
      .toMatchObject({ title: "Meeting completed: HR meeting", when: null });
    expect(timelineEntry(row({ kind: "follow_up", event: "scheduled", from_value: "jd", scheduled_for: "2026-10-12T05:00:00Z" })))
      .toMatchObject({ badge: "Follow-up", title: "Follow-up added: Follow-up for JD", when: { label: "Due", value: "2026-10-12T05:00:00Z" } });
    expect(timelineEntry(row({ kind: "follow_up", event: "cancelled", from_value: "jd", reason: "Sent already" })))
      .toMatchObject({ title: "Follow-up cancelled: Follow-up for JD", detail: "Sent already" });
  });

  it("reads requirement, share, response and contract entries", () => {
    expect(timelineEntry(row({ kind: "requirement", to_value: "requirement_received", to_label: "Requirement Received", subject: "REQ-000001 — Java Dev" })))
      .toMatchObject({ badge: "Requirement", title: "Requirement added (Requirement Received)", meta: ["REQ-000001 — Java Dev"] });
    expect(timelineEntry(row({ kind: "requirement", from_value: "sourcing", from_label: "Sourcing", to_value: "on_hold", to_label: "On Hold" })).title)
      .toBe("Requirement: Sourcing → On Hold");
    expect(timelineEntry(row({ kind: "share", event: "email", to_value: "3", to_label: "Priya", subject: "REQ-000001 — Java Dev" })))
      .toMatchObject({ badge: "Profiles shared", title: "3 profiles shared by Email", meta: ["REQ-000001 — Java Dev", "To Priya"] });
    expect(timelineEntry(row({ kind: "share", event: "portal", to_value: "1" })).title).toBe("1 profile shared by Portal");
    expect(timelineEntry(row({ kind: "share", event: "other", context: "Acme", subject: "REQ-1 — Dev" })))
      .toMatchObject({ title: "Profile shared by Other", meta: ["REQ-1 — Dev", "Acme"] });
    expect(timelineEntry(row({ kind: "share_response", event: "interview_requested", to_label: "Rahul", subject: "REQ-1 — Dev", reason: "Strong" })))
      .toMatchObject({ badge: "Response", title: "Company response: Interview requested", meta: ["Rahul", "REQ-1 — Dev"], detail: "Strong" });
    expect(timelineEntry(row({ kind: "contract", event: "created", to_label: "Discussion" })).title).toBe("Contract created (Discussion)");
    expect(timelineEntry(row({ kind: "contract", event: "status", from_label: "Discussion", to_label: "Signed" })).title).toBe("Contract: Discussion → Signed");
    expect(timelineEntry(row({ kind: "contract", event: "document" })).title).toBe("Contract document uploaded");
  });

  it("reads the candidate's application, interview and offer entries", () => {
    expect(timelineEntry(row({ kind: "application", to_value: "sourced", to_label: "Sourced", subject: "REQ-1 — Dev", context: "Acme" })))
      .toMatchObject({ badge: "Application", title: "Added to requirement (Sourced)", meta: ["REQ-1 — Dev", "Acme"] });
    expect(timelineEntry(row({ kind: "application", from_value: "sourced", from_label: "Sourced", to_value: "selected", to_label: "Selected" })).title)
      .toBe("Application: Sourced → Selected");
    expect(timelineEntry(row({ kind: "interview", event: "scheduled", status: "hr_round", subject: "INT-000001", context: "Acme", scheduled_for: "2026-10-12T05:00:00Z" })))
      .toMatchObject({ badge: "Interview", title: "Interview scheduled: HR Round", meta: ["INT-000001", "Acme"], when: { label: "For", value: "2026-10-12T05:00:00Z" } });
    expect(timelineEntry(row({ kind: "interview", event: "status", status: "hr_round", from_label: "Scheduled", to_label: "Completed" })).title)
      .toBe("Interview: Scheduled → Completed");
    expect(timelineEntry(row({ kind: "offer", event: "created", to_label: "Offer Received" })).title).toBe("Offer recorded (Offer Received)");
    expect(timelineEntry(row({ kind: "offer", event: "status", from_label: "Offer Received", to_label: "Accepted" })).title).toBe("Offer: Offer Received → Accepted");
    expect(timelineEntry(row({ kind: "offer", event: "did_not_join", reason: "Relocated" }))).toMatchObject({ title: "Did not join", detail: "Relocated" });
  });

  it("names the actor, or the system", () => {
    expect(timelineActor(row({}))).toBe("Asha Menon");
    expect(timelineActor(row({ actor: null }))).toBe("System");
  });

  it("marks a cut excerpt", () => {
    expect(timelineEntry(row({ kind: "call", event: "outgoing", reason: "x".repeat(200) })).detail).toBe(`${"x".repeat(200)}…`);
  });
});
