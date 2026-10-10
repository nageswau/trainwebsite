import { describe, expect, it } from "vitest";

import { activityActor, activityEntry, type ActivityRow, universityTimelineUrl } from "@/lib/universityActivity";
import { dateText } from "@/lib/visits";

const PM = { id: "u1", full_name: "Asha Menon" };
const row = (over: Partial<ActivityRow>): ActivityRow => ({
  id: "r1", kind: "stage", at: "2026-09-05T05:00:00Z", actor: PM, event: null, from_value: "", from_label: "", to_value: "", to_label: "",
  subject: null, status: null, reason: null, duration_seconds: null, scheduled_for: null, ...over,
});

describe("universityActivity (upc-013)", () => {
  it("builds the timeline URL", () => {
    expect(universityTimelineUrl("u 1")).toBe("/api/v1/partnership/universities/u%201/timeline");
  });

  it("reads the §12 example chain", () => {
    expect(activityEntry(row({ kind: "message", event: "email", status: "sent", subject: "Our proposal", to_label: "Priya" })))
      .toMatchObject({ badge: "Email", title: "Email sent", meta: ["To Priya", "Custom message", "Subject: Our proposal"] });
    expect(activityEntry(row({ kind: "call", event: "outgoing", from_value: "connected", from_label: "Connected", to_label: "Priya", duration_seconds: 125 })))
      .toMatchObject({ badge: "Call", title: "Outgoing call: Connected", meta: ["With Priya", "Duration 2:05"] });
    expect(activityEntry(row({ kind: "meeting", event: "scheduled", from_value: "mou_discussion", subject: "UMT-000001", scheduled_for: "2026-09-10T05:00:00Z" })))
      .toMatchObject({ badge: "Meeting", title: "Meeting scheduled: MoU discussion", meta: ["UMT-000001"], when: { label: "For", value: "2026-09-10T05:00:00Z" } });
    expect(activityEntry(row({ kind: "meeting", event: "completed", from_value: "mou_discussion", subject: "UMT-000001" })).title)
      .toBe("Meeting completed: MoU discussion");
    expect(activityEntry(row({ kind: "stage", event: "move", from_label: "Meeting Completed", to_label: "Proposal Sent" })))
      .toMatchObject({ badge: "Stage", title: "Stage: Meeting Completed → Proposal Sent" });
    expect(activityEntry(row({ kind: "task", event: "scheduled", from_value: "follow_up", subject: "Follow up on the proposal", to_value: "2026-09-18",
      to_label: "Asha Menon", status: "manual" })))
      .toMatchObject({ badge: "Follow-up", title: "Follow-up added: Follow up on the proposal", meta: [`Due ${dateText("2026-09-18")}`, "Assigned to Asha Menon"] });
  });

  it("names the other kinds", () => {
    expect(activityEntry(row({ kind: "stage", event: "lost", reason: "Went with another agency" }))).toMatchObject({ title: "Marked Lost / Closed",
      detail: "Went with another agency" });
    expect(activityEntry(row({ kind: "stage", event: "reopened", to_label: "Interested" })).title).toBe("Reopened at Interested");
    expect(activityEntry(row({ kind: "message", event: "whatsapp", from_value: "Intro", to_label: "Priya" })))
      .toMatchObject({ badge: "WhatsApp", title: "WhatsApp sent", meta: ["To Priya", "Intro"] });
    expect(activityEntry(row({ kind: "message", event: "email", status: "failed" })).title).toBe("Email failed");
    expect(activityEntry(row({ kind: "call", event: "incoming", from_label: "No answer", to_label: "" })).meta).toEqual(["Contact removed"]);
    expect(activityEntry(row({ kind: "visit", event: "approve", from_value: "planned", to_value: "approved", subject: "UV-000002" })))
      .toMatchObject({ badge: "Visit", title: "Visit approved", meta: ["UV-000002", "Status: Approved"] });
    expect(activityEntry(row({ kind: "agreement", event: "status", from_value: "sent", to_value: "signed", subject: "MOU-000123", status: "mou" })))
      .toMatchObject({ badge: "Agreement", title: "MoU MOU-000123: Sent → Signed" });
    expect(activityEntry(row({ kind: "agreement", event: "create", to_value: "draft", subject: "MOU-000123", status: "mou" })).title)
      .toBe("MoU MOU-000123 created");
    expect(activityEntry(row({ kind: "agreement", event: "renew", to_value: "renewed", subject: "MOU-000123", status: "mou" })).title)
      .toBe("MoU MOU-000123 renewed");
    expect(activityEntry(row({ kind: "document", event: "uploaded", from_value: "fee_structure", subject: "Fees 2026", to_value: "1" })))
      .toMatchObject({ badge: "Document", title: "Document added: Fees 2026", meta: ["Fee structure"] });
    expect(activityEntry(row({ kind: "document", event: "new_version", from_value: "brochure", subject: "Brochure", to_value: "3" })).title)
      .toBe("New version (v3): Brochure");
    expect(activityEntry(row({ kind: "task", event: "done", from_value: "task", subject: "Send MoU", status: "stage" })).title).toBe("Task done: Send MoU");
    expect(activityEntry(row({ kind: "task", event: "cancelled", from_value: "task", subject: "Old", reason: "No longer needed" })))
      .toMatchObject({ title: "Task cancelled: Old", detail: "No longer needed" });
  });

  it("marks a cut excerpt and names the system actor", () => {
    expect(activityEntry(row({ kind: "call", reason: "x".repeat(200) })).detail).toBe(`${"x".repeat(200)}…`);
    expect(activityActor(row({}))).toBe("Asha Menon");
    expect(activityActor(row({ actor: null }))).toBe("System");
  });
});
