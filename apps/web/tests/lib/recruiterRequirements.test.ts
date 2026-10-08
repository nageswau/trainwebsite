import { describe, expect, it } from "vitest";

import {
  experienceText,
  monthsFromYears,
  type Requirement,
  requirementBody,
  salaryText,
  skillList,
  valuesOf,
  yearsFromMonths,
} from "@/lib/recruiterRequirements";

const base = {
  title: "Python Developer", location: "Hyderabad", description: "", department: null, job_category: null, vacancies: 3, qualification: null,
  experience_min_months: 0, experience_max_months: 24, salary_min: "300000.00", salary_max: null, work_mode: "hybrid", shift: null,
  employment_type: null, joining_requirement: null, closes_on: null, requirement_date: "2026-10-08", priority: "high",
  skills: [
    { id: "1", name: "Python", kind: "required", weight: 2, skill_id: "s1", matched: true },
    { id: "2", name: "Docker", kind: "preferred", weight: 1, skill_id: null, matched: false },
  ],
} as unknown as Requirement;

describe("rec-007 requirement helpers", () => {
  it("converts years typed in the form to whole months, and back", () => {
    expect(monthsFromYears("")).toBeNull();
    expect(monthsFromYears("2")).toBe(24);
    expect(monthsFromYears("1.5")).toBe(18);
    expect(Number.isNaN(monthsFromYears("two"))).toBe(true);
    expect(yearsFromMonths(18)).toBe("1.5");
    expect(yearsFromMonths(null)).toBe("");
  });

  it("reads skills one per comma or line, trimmed, without blanks or repeats", () => {
    expect(skillList("Python, SQL\n\n fastapi ,python")).toEqual(["Python", "SQL", "fastapi"]);
  });

  it("describes experience and salary ranges", () => {
    expect(experienceText(0, 24)).toBe("0–2 years");
    expect(experienceText(null, 36)).toBe("Up to 3 years");
    expect(experienceText(12, null)).toBe("1+ years");
    expect(experienceText(null, null)).toBe("—");
    expect(salaryText("300000.00", "600000")).toBe("₹3,00,000 – ₹6,00,000 a year");
    expect(salaryText(null, null)).toBe("—");
  });

  it("sends every filled field on create and only the changed ones on edit", () => {
    const values = valuesOf(base);
    expect(values.experience_max_months).toBe("2");
    expect(values.required_skills).toBe("Python");
    expect(values.preferred_skills).toBe("Docker");
    const created = requirementBody(values);
    expect(created).toMatchObject({ title: "Python Developer", vacancies: 3, experience_min_months: 0, experience_max_months: 24, required_skills: ["Python"], preferred_skills: ["Docker"] });
    expect(created).not.toHaveProperty("department");
    const edited = requirementBody({ ...values, department: "Engineering", required_skills: "Python, SQL" }, values);
    expect(edited).toEqual({ department: "Engineering", required_skills: ["Python", "SQL"] });
    expect(requirementBody({ ...values, salary_min: "" }, values)).toEqual({ salary_min: null });
  });
});
