import { describe, expect, it } from "vitest";

import { SCHOOL_NAV } from "@/lib/navigation";
import { ENROLMENT_CLASS, ENROLMENT_LABEL, ENROLMENT_STATUSES, MODULE_LABEL, TRANSITIONS, attendanceText, canMark, type SkillEnrollment } from "@/lib/skills";

// ENH-011 (docs/superpowers/specs/2026-09-22-enh-011-skills-tracker-design.md §5.1, §7): the shared labels and rules the
// counselor screens use. TRANSITIONS must equal the API's table exactly, so the UI never offers a change the API refuses.

function enrolment(over: Partial<SkillEnrollment> = {}): SkillEnrollment {
  return {
    id: "e1", batch_id: "b1", school_student_id: "s1", student_name: "Asha R", status: "enrolled", frozen: false,
    completed_at: null, certified_at: null, created_at: "2026-10-01T10:00:00Z", attendance: { present: 0, marked: 0 }, scores: [], ...over,
  };
}

describe("lib/skills", () => {
  it("labels every module and enrolment status in words, with a class", () => {
    expect(MODULE_LABEL).toEqual({ soft_skills: "Soft Skills", digital_skills: "Digital Skills" });
    for (const status of ENROLMENT_STATUSES) {
      expect(ENROLMENT_LABEL[status]).toMatch(/\w/);
      expect(typeof ENROLMENT_CLASS[status]).toBe("string");
    }
  });

  it("mirrors the API's transition table, with certified terminal", () => {
    expect(TRANSITIONS).toEqual({
      enrolled: ["completed", "certified", "withdrawn"],
      completed: ["certified", "enrolled"],
      withdrawn: ["enrolled"],
      certified: [],
    });
  });

  it("describes attendance in words", () => {
    expect(attendanceText({ present: 0, marked: 0 })).toBe("No attendance yet");
    expect(attendanceText({ present: 4, marked: 5 })).toBe("Attended 4 of 5 sessions");
    expect(attendanceText({ present: 1, marked: 1 })).toBe("Attended 1 of 1 session");
  });

  it("only enrolled or completed, not-frozen enrolments take attendance and scores", () => {
    expect(canMark(enrolment())).toBe(true);
    expect(canMark(enrolment({ status: "completed" }))).toBe(true);
    expect(canMark(enrolment({ status: "certified" }))).toBe(false);
    expect(canMark(enrolment({ status: "withdrawn" }))).toBe(false);
    expect(canMark(enrolment({ frozen: true }))).toBe(false);
  });

  it("gives the career counselor a Skills entry after the dashboard", () => {
    expect(SCHOOL_NAV["career-counselor"].map((item) => [item.label, item.href])).toEqual([
      ["Dashboard", "/school/career-counselor/dashboard"],
      ["Skills", "/school/career-counselor/skills"],
    ]);
  });
});
