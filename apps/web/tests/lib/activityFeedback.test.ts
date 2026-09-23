import { describe, expect, it } from "vitest";

import { activityTypeLabel, isFeedbackEligible, participationText, scoreText } from "@/lib/activityFeedback";

// ENH-018 -- wording helpers shared by the feedback screens (spec §7).
describe("activityFeedback helpers", () => {
  it("words participation, including attendance never marked", () => {
    expect(participationText({ present: 42, marked: 50 })).toBe("42 of 50 present");
    expect(participationText({ present: 0, marked: 0 })).toBe("Not marked");
  });

  it("labels a score with words, not a number alone", () => {
    expect(scoreText(1)).toBe("1 – Poor");
    expect(scoreText(5)).toBe("5 – Excellent");
  });

  it("labels activity types and falls back to the raw value", () => {
    expect(activityTypeLabel("campus_visit")).toBe("Monthly campus visit");
    expect(activityTypeLabel("something_new")).toBe("something_new");
  });

  it("is eligible only when typed and already held", () => {
    const now = Date.parse("2026-09-23T10:00:00Z");
    expect(isFeedbackEligible({ activity_type: "career_seminar", scheduled_at: "2026-09-23T09:59:00Z" }, now)).toBe(true);
    expect(isFeedbackEligible({ activity_type: "career_seminar", scheduled_at: "2026-09-23T10:01:00Z" }, now)).toBe(false);
    expect(isFeedbackEligible({ activity_type: null, scheduled_at: "2026-09-01T10:00:00Z" }, now)).toBe(false);
    expect(isFeedbackEligible({ scheduled_at: "2026-09-01T10:00:00Z" }, now)).toBe(false);
  });
});
