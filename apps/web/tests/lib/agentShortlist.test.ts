import { describe, expect, it } from "vitest";

import { buildEntryPayload, buildUniversityPayload, changedOnly, draftFromEntry, emptyEntryDraft, shortlistUrl, validateEntryDraft, validateUniversityDraft } from "@/lib/agentShortlist";

describe("agentShortlist (AGN-007)", () => {
  it("builds a catalogue payload: course id wins over typed text", () => {
    const d = { ...emptyEntryDraft(), university: "c:u1", courseId: "k1", courseTitle: "ignored", intake: " Sep 2027 ", tuitionFee: "", entryRequirements: "IELTS" };
    expect(buildEntryPayload(d)).toEqual({ university_id: "u1", agent_university_id: null, course_id: "k1", course_title: null, intake: "Sep 2027", tuition_fee: null, entry_requirements: "IELTS" });
  });

  it("builds an agency payload: never a catalogue course", () => {
    const d = { ...emptyEntryDraft(), university: "a:x9", courseId: "k1", courseTitle: " BA Typed " };
    expect(buildEntryPayload(d)).toMatchObject({ university_id: null, agent_university_id: "x9", course_id: null, course_title: "BA Typed" });
  });

  it("sends only changed fields on edit", () => {
    const original = { university_id: "u1", agent_university_id: null, course_id: null, course_title: "A", intake: "Sep", tuition_fee: null, entry_requirements: null };
    expect(changedOnly({ ...original, intake: "Jan" }, original)).toEqual({ intake: "Jan" });
  });

  it("round-trips an entry into a draft", () => {
    const entry = { id: "e1", university: { source: "agency" as const, id: "x9", name: "N", slug: null, country: "Malta" }, course: { id: null, title: "BA" }, intake: "Sep", tuition_fee: null, entry_requirements: null, created_by: null, created_at: "", updated_at: "" };
    expect(draftFromEntry(entry)).toEqual({ university: "a:x9", courseId: "", courseTitle: "BA", intake: "Sep", tuitionFee: "", entryRequirements: "" });
  });

  it("validates the university and lengths", () => {
    expect(validateEntryDraft(emptyEntryDraft())).toBe("Choose a university.");
    expect(validateEntryDraft({ ...emptyEntryDraft(), university: "a:x", intake: "x".repeat(121) })).toBe("Intake must be 120 characters or fewer.");
    expect(validateEntryDraft({ ...emptyEntryDraft(), university: "a:x" })).toBeNull();
    expect(validateUniversityDraft({ name: " ", country: "Ireland", city: "", entryRequirements: "" })).toBe("Name is required.");
    expect(buildUniversityPayload({ name: " Trinity ", country: "Ireland", city: "", entryRequirements: "" })).toEqual({ name: "Trinity", country: "Ireland", city: null, entry_requirements: null });
  });

  it("builds the shortlist URL", () => {
    expect(shortlistUrl("s1")).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/shortlist");
  });
});
