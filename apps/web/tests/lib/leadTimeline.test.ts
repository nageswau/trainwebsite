import { describe, expect, it } from "vitest";

import { actorName, duration, timelineEntry, type TimelineRow } from "@/lib/leadTimeline";

// tel-015 (DEC-SCOPE-114 D3, TM2): how each timeline kind reads.
const row = (over: Partial<TimelineRow>): TimelineRow => ({
  id: "r1", kind: "stage", at: "2026-10-07T05:00:00Z", actor: null, from_value: "", from_label: "", to_value: "", to_label: "", reason: null,
  event: null, subject: null, status: null, duration_seconds: null, scheduled_for: null, ...over,
});
const tara = { id: "t1", full_name: "Tara Caller" };

describe("timelineEntry", () => {
  it("reads the creation, enquiries and actors", () => {
    expect(timelineEntry(row({ kind: "created", from_value: "walk_in", to_value: "Cyber Security" }))).toMatchObject({
      title: "Lead created", meta: ["Source: Walk-in", "Cyber Security"] });
    expect(actorName(row({ kind: "created", from_value: "website" }))).toBe("Website form");
    expect(actorName(row({ kind: "created", from_value: "walk_in" }))).toBe("System");
    expect(actorName(row({ kind: "enquiry", from_value: "google" }))).toBe("Website form");
    expect(actorName(row({ kind: "assignment" }))).toBe("System");
    expect(actorName(row({ kind: "call", actor: tara }))).toBe("Tara Caller");
  });

  it("names assignments, unassignments and reassignments", () => {
    expect(timelineEntry(row({ kind: "assignment", to_value: "t1", to_label: "Tara", event: "round_robin" }))).toMatchObject({
      title: "Assigned to Tara", meta: ["Round robin"] });
    expect(timelineEntry(row({ kind: "assignment", from_value: "t1", from_label: "Tara", to_value: "t2", to_label: "Ravi", event: "manual" })).title)
      .toBe("Reassigned from Tara to Ravi");
    expect(timelineEntry(row({ kind: "assignment", from_value: "t1", from_label: "Tara", event: "team_move" }))).toMatchObject({
      title: "Unassigned from Tara", meta: ["Team move"] });
  });

  it("reads calls with their outcome label and duration", () => {
    const entry = timelineEntry(row({ kind: "call", from_value: "incoming", to_value: "call_back_requested", duration_seconds: 125, reason: "Evening" }));
    expect(entry).toMatchObject({ badge: "Call", meta: ["Duration 2:05"], detail: "Evening" });
    expect(entry.title).toMatch(/^Incoming call: /);
    expect(duration(0)).toBe("0:00");
  });

  it("reads WhatsApp and email, custom or templated, with an ellipsis on a cut excerpt", () => {
    expect(timelineEntry(row({ kind: "message", from_value: "whatsapp", reason: "x".repeat(200) }))).toMatchObject({
      badge: "WhatsApp", title: "WhatsApp sent", meta: ["Custom message"], detail: `${"x".repeat(200)}…` });
    expect(timelineEntry(row({ kind: "message", from_value: "email", to_value: "Fee details", subject: "Fees", status: "failed" }))).toMatchObject({
      badge: "Email", title: "Email failed", meta: ["Fee details", "Subject: Fees"] });
  });

  it("reads follow-ups, appointments, handovers, links and milestones", () => {
    expect(timelineEntry(row({ kind: "follow_up", event: "scheduled", from_value: "fee_details", scheduled_for: "2026-10-09T05:00:00Z" }))).toMatchObject({
      title: "Follow-up scheduled: Need fee details", when: { label: "Due", value: "2026-10-09T05:00:00Z" } });
    expect(timelineEntry(row({ kind: "follow_up", event: "cancelled", from_value: "fee_details", reason: "Handed over to counselor" })).title)
      .toBe("Follow-up cancelled: Need fee details");
    expect(timelineEntry(row({ kind: "appointment", to_value: "scheduled", event: "it_course_counselling", subject: "CAP-000001",
      scheduled_for: "2026-10-09T05:00:00Z" }))).toMatchObject({ title: "Counselling appointment booked", meta: ["IT course counselling", "CAP-000001"] });
    expect(timelineEntry(row({ kind: "appointment", from_value: "scheduled", to_value: "no_show" })).title).toBe("Counselling appointment no show");
    expect(timelineEntry(row({ kind: "handover", to_value: "c1", to_label: "Cara" })).title).toBe("Handed over to Cara");
    expect(timelineEntry(row({ kind: "handover", from_value: "c1", from_label: "Cara", to_value: "c2", to_label: "Dev" })).title)
      .toBe("Counselor changed from Cara to Dev");
    expect(timelineEntry(row({ kind: "student_link", event: "linked", to_label: "Asha Rao" })).title).toBe("Student linked: Asha Rao");
    expect(timelineEntry(row({ kind: "student_link", event: "unlinked", to_label: "Asha Rao" })).title).toBe("Student unlinked: Asha Rao");
    expect(timelineEntry(row({ kind: "milestone", event: "application", to_label: "Univ of Leeds", status: "offer_received", subject: "APP-1" })))
      .toMatchObject({ title: "Overseas application: Univ of Leeds", meta: ["Offer received", "APP-1"] });
  });

  it("keeps the stage wording, the named return and the conversion", () => {
    expect(timelineEntry(row({ kind: "stage", from_label: "New Lead", to_label: "Assigned" })).title).toBe("Stage: New Lead → Assigned");
    expect(timelineEntry(row({ kind: "stage", event: "returned" })).title).toBe("Returned to the telecaller");
    expect(timelineEntry(row({ kind: "stage", event: "converted" })).title).toBe("Converted");
    expect(timelineEntry(row({ kind: "priority", from_label: "Warm", to_label: "Hot" })).title).toBe("Priority: Warm → Hot");
  });
});
