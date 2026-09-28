import { describe, expect, it } from "vitest";

import { changedFields, hasResults, listError, RESULT_KEYS, toDraft, type PsychometricResult } from "@/lib/psychometric";

const full: PsychometricResult = {
  test_date: "2026-09-10", strengths: ["Logic", "Verbal"], interest_areas: null, personality_indicators: null,
  recommended_careers: ["Engineer"], recommended_stream: null, counsellor_remarks: "Line 1\nLine 2",
  parent_discussion_on: null, parent_discussion_notes: null, follow_up_on: "2026-10-15",
};

describe("lib/psychometric", () => {
  it("lists the ten result keys in API order", () => {
    expect(RESULT_KEYS).toEqual(["test_date", "strengths", "interest_areas", "personality_indicators", "recommended_careers", "recommended_stream", "counsellor_remarks", "parent_discussion_on", "parent_discussion_notes", "follow_up_on"]);
  });

  it("hasResults is false for a legacy record and true once any field is set", () => {
    expect(hasResults({})).toBe(false);
    expect(hasResults(Object.fromEntries(RESULT_KEYS.map((k) => [k, null])))).toBe(false);
    expect(hasResults({ strengths: [] })).toBe(false);
    expect(hasResults({ follow_up_on: "2026-10-15" })).toBe(true);
  });

  it("toDraft joins lists with commas (ENH-025/026 convention) and turns nulls into empty strings", () => {
    const draft = toDraft(full);
    expect(draft.strengths).toBe("Logic, Verbal");
    expect(draft.interest_areas).toBe("");
    expect(draft.counsellor_remarks).toBe("Line 1\nLine 2");
  });

  it("changedFields sends only what changed; emptied fields become null", () => {
    const initial = toDraft(full);
    expect(changedFields(initial, initial)).toEqual({});
    expect(changedFields(initial, { ...initial, strengths: "Logic, Verbal, Spatial", follow_up_on: "" })).toEqual({ strengths: ["Logic", "Verbal", "Spatial"], follow_up_on: null });
    expect(changedFields(initial, { ...initial, interest_areas: "Design" })).toEqual({ interest_areas: ["Design"] });
  });

  it("changedFields ignores spacing and stray commas", () => {
    const initial = toDraft(full);
    expect(changedFields(initial, { ...initial, strengths: " Logic ,, Verbal , " })).toEqual({});
    expect(changedFields(initial, { ...initial, counsellor_remarks: "  Line 1\nLine 2 " })).toEqual({});
  });

  it("listError enforces 20 items of 80 characters", () => {
    expect(listError("a, b")).toBeNull();
    expect(listError(Array.from({ length: 21 }, (_, i) => `s${i}`).join(", "))).toBe("Up to 20 items.");
    expect(listError("x".repeat(81))).toBe("Each item must be 80 characters or fewer.");
  });
});
