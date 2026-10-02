import { describe, expect, it } from "vitest";

import { type AgentTask, buildCreatePayload, buildUpdatePayload, draftFromTask, emptyDraft, isPastLocal, localToIso, parseView, toLocalInput, validateDraft } from "@/lib/agentTasks";

const task = (over: Partial<AgentTask> = {}): AgentTask => ({
  id: "t1", title: "Call", notes: null, due_at: "2026-10-05T04:00:00Z", status: "open", overdue: false,
  student: { id: "s1", full_name: "Asha", status: "active" }, application: null, assigned_to: null,
  created_by: "M", closed_by: null, closed_at: null, created_at: "", updated_at: "", ...over,
});

describe("agentTasks (AGN-016)", () => {
  it("parses the view, defaulting to open", () => {
    expect(parseView("overdue")).toBe("overdue");
    expect(parseView("archived")).toBe("open");
    expect(parseView(null)).toBe("open");
  });

  it("converts a datetime-local value to an instant with an offset, and back", () => {
    expect(localToIso("2026-10-05T09:30")).toBe(new Date(2026, 9, 5, 9, 30).toISOString());
    expect(localToIso("")).toBeNull();
    expect(localToIso("not a date")).toBeNull();
    const iso = new Date(2026, 9, 5, 9, 30).toISOString();
    expect(localToIso(toLocalInput(iso))).toBe(iso);
  });

  it("tells a past due time", () => {
    const now = new Date(2026, 9, 5, 10, 0);
    expect(isPastLocal("2026-10-05T09:59", now)).toBe(true);
    expect(isPastLocal("2026-10-05T10:01", now)).toBe(false);
    expect(isPastLocal("", now)).toBe(false);
  });

  it("validates the draft", () => {
    expect(validateDraft(emptyDraft())).toEqual({ studentId: "Choose a student.", title: "Title is required.", dueLocal: "Choose a due date and time." });
    const ok = { ...emptyDraft("s1"), title: " Call ", dueLocal: "2026-10-05T09:30" };
    expect(validateDraft(ok)).toEqual({});
    expect(validateDraft({ ...ok, title: "x".repeat(201) })).toEqual({ title: "Title must be 200 characters or fewer." });
    expect(validateDraft({ ...ok, notes: "x".repeat(2001) })).toEqual({ notes: "Notes must be 2000 characters or fewer." });
  });

  it("builds the create payload: trimmed, blank optional fields null", () => {
    const d = { ...emptyDraft("s1"), title: " Call ", dueLocal: "2026-10-05T09:30", notes: "  " };
    expect(buildCreatePayload(d)).toEqual({ agent_student_id: "s1", title: "Call", due_at: new Date(2026, 9, 5, 9, 30).toISOString(), notes: null, application_id: null });
  });

  it("sends only changed fields on edit", () => {
    const original = task({ notes: "Old", application: { id: "a1", university: "U" } });
    const draft = draftFromTask(original);
    expect(buildUpdatePayload(draft, original)).toEqual({});
    expect(buildUpdatePayload({ ...draft, notes: "", applicationId: "" }, original)).toEqual({ notes: null, application_id: null });
    expect(buildUpdatePayload({ ...draft, title: "New" }, original)).toEqual({ title: "New" });
  });
});
