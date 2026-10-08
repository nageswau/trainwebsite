import { describe, expect, it } from "vitest";

import {
  candidateSkillsUrl, EMPTY_SKILL_FORM, formOf, LEVELS, type SkillForm, SOURCES, STATUS_LABEL, toBody,
} from "@/lib/recruiterCandidateSkills";
import { candidateSkill } from "@/tests/helpers/recruiterCandidateSkills";

// rec-011 (SK1-SK4): the levels, the six S2-§17 sources in source order, the status moves and the form <-> body mapping.
describe("recruiterCandidateSkills (rec-011)", () => {
  it("has the four levels and the six S2-§17 sources in source order", () => {
    expect(LEVELS.map((l) => l.label)).toEqual(["Beginner", "Intermediate", "Advanced", "Expert"]);
    expect(SOURCES.map((s) => s.label)).toEqual([
      "Resume", "Interview verified", "Assessment verified", "Course completed", "Certification", "Employer verified",
    ]);
    expect(STATUS_LABEL).toEqual({ claimed: "Claimed", verified: "Verified", assessed: "Assessed" });
  });

  it("builds the URLs", () => {
    expect(candidateSkillsUrl("C 1")).toBe("/api/v1/recruiter/candidates/C%201/skills");
    expect(candidateSkillsUrl("C1", "S1", "/status")).toBe("/api/v1/recruiter/candidates/C1/skills/S1/status");
  });

  it("maps a form to a body: blanks are null, numbers are numbers, and an edit never sends the skill", () => {
    const form: SkillForm = { ...EMPTY_SKILL_FORM, skill: "Java", level: "advanced", experience_months: " 36 ", last_used_year: "", source: "certification" };
    expect(toBody(form, true)).toEqual({ skill: "Java", level: "advanced", experience_months: 36, last_used_year: null, source: "certification" });
    expect(toBody(form, false)).toEqual({ level: "advanced", experience_months: 36, last_used_year: null, source: "certification" });
    expect(EMPTY_SKILL_FORM.source).toBe("resume");
    expect(formOf(candidateSkill({ experience_months: null, last_used_year: 2025 }))).toEqual({
      skill: "Java", level: "advanced", experience_months: "", last_used_year: "2025", source: "resume",
    });
  });
});
