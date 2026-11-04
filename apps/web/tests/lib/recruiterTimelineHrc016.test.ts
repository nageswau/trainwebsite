import { describe, expect, it } from "vitest";

import { timelineEntry, type RecTimelineRow } from "@/lib/recruiterTimeline";

const row = (over: Partial<RecTimelineRow>): RecTimelineRow => ({
  id: "r1", kind: "note", at: "2026-11-04T05:00:00Z", actor: { id: "u1", full_name: "Asha Menon" }, event: null, from_value: "", from_label: "",
  to_value: "", to_label: "", subject: null, status: null, reason: null, context: null, duration_seconds: null, scheduled_for: null, ...over,
});

describe("recruiterTimeline (hrc-016 T9)", () => {
  it("reads a note with its excerpt", () => {
    expect(timelineEntry(row({ kind: "note", reason: "Prefers Pune" }))).toMatchObject({ badge: "Note", title: "Note added", detail: "Prefers Pune" });
  });

  it("reads a task's assignment, completion and cancellation", () => {
    expect(timelineEntry(row({ kind: "task", event: "scheduled", from_value: "resume_screening", subject: "Screen the CV", to_label: "Ravi", scheduled_for: "2026-11-05T05:00:00Z" })))
      .toMatchObject({ badge: "Task", title: "Task assigned: Resume screening", meta: ["Screen the CV", "Assigned to Ravi"], when: { label: "Due", value: "2026-11-05T05:00:00Z" } });
    expect(timelineEntry(row({ kind: "task", event: "done", from_value: "employer_feedback", subject: "Chase", to_label: "Ravi" })))
      .toMatchObject({ title: "Task done: Employer feedback", when: null });
    expect(timelineEntry(row({ kind: "task", event: "cancelled", from_value: "follow_up", subject: "Call" })).title).toBe("Task cancelled: Follow-up");
  });

  it("reads ownership changes", () => {
    expect(timelineEntry(row({ kind: "assignment", event: "owner", from_label: "", to_label: "Asha", status: "create" })))
      .toMatchObject({ badge: "Ownership", title: "Primary recruiter: None → Asha", meta: ["When the candidate was added"] });
    expect(timelineEntry(row({ kind: "assignment", event: "placement_officer", from_label: "Ravi", to_label: "", status: "assign" })))
      .toMatchObject({ title: "Placement officer: Ravi → None", meta: [] });
    expect(timelineEntry(row({ kind: "assignment", event: "collaborator_added", to_label: "Meera" })).title).toBe("Collaborator added: Meera");
    expect(timelineEntry(row({ kind: "assignment", event: "collaborator_removed", from_label: "Meera" })).title).toBe("Collaborator removed: Meera");
    // hrc-024 (R8): a routed website candidate -- no actor (the system)
    expect(timelineEntry(row({ kind: "assignment", event: "owner", from_label: "", to_label: "Asha", status: "route", actor: null })))
      .toMatchObject({ title: "Primary recruiter: None → Asha", meta: ["Automatic routing"] });
  });

  it("reads profile changes", () => {
    expect(timelineEntry(row({ kind: "profile", event: "create", to_value: "5" })).title).toBe("Candidate added");
    expect(timelineEntry(row({ kind: "profile", event: "update", to_value: "1" })).title).toBe("Profile edited (1 field)");
    expect(timelineEntry(row({ kind: "profile", event: "update", to_value: "3" })).title).toBe("Profile edited (3 fields)");
    expect(timelineEntry(row({ kind: "profile", event: "archive" })).title).toBe("Candidate archived");
    expect(timelineEntry(row({ kind: "profile", event: "restore" })).title).toBe("Candidate restored");
    expect(timelineEntry(row({ kind: "profile", event: "merge", subject: "CAN-000002" })).title).toBe("CAN-000002 merged into this candidate");
    expect(timelineEntry(row({ kind: "profile", event: "merged_into", subject: "CAN-000001" })).title).toBe("Merged into CAN-000001");
  });

  it("reads a screening with its requirement and company", () => {
    expect(timelineEntry(row({ kind: "screening", to_value: "hold", to_label: "Hold", subject: "REQ-1 — Java", context: "Acme" })))
      .toMatchObject({ badge: "Screening", title: "Screening: Hold", meta: ["REQ-1 — Java", "Acme"] });
  });
});
