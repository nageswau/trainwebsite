import { describe, expect, it } from "vitest";

import { isJd, jdBody, jdValues, type JdVersion, requirementChangesFromJd } from "@/lib/recruiterJd";
import type { Requirement } from "@/lib/recruiterRequirements";

const requirement = {
  id: "r1", title: "Python Developer", location: "Hyderabad", qualification: "B.Tech", vacancies: 3, closes_on: "2026-11-01",
  description: "Build APIs", experience_min_months: 0, experience_max_months: 24, salary_min: "300000", salary_max: "600000",
  skills: [
    { id: "s1", name: "Python", kind: "required", weight: 2, skill_id: null, matched: false },
    { id: "s2", name: "Docker", kind: "preferred", weight: 1, skill_id: null, matched: false },
  ],
} as unknown as Requirement;

const version: JdVersion = {
  version: 2, is_current: true, role: "Senior Python Developer", experience: "2–4 years", qualification: "B.Tech", skills: "Python",
  salary: null, location: "Pune", description: "Build APIs", responsibilities: "Own it", requirements: null, openings: 5,
  contact: { id: "c1", name: "Asha", active: true }, closing_date: "2026-11-01", closing_date_differs: false,
  file: null, created_by: null, created_at: "2026-10-08T10:00:00Z",
};

describe("jdValues", () => {
  it("prefills a first JD from the requirement (experience, salary and skills as text)", () => {
    const v = jdValues(undefined, requirement);
    expect(v.role).toBe("Python Developer");
    expect(v.experience).toBe("0–2 years");
    expect(v.salary).toBe("₹3,00,000 – ₹6,00,000 a year");
    expect(v.skills).toBe("Python, Docker");
    expect(v.openings).toBe("3");
    expect(v.closing_date).toBe("2026-11-01");
    expect(v.contact_id).toBe("");
  });

  it("edits start from the current version", () => {
    const v = jdValues(version, requirement);
    expect(v.role).toBe("Senior Python Developer");
    expect(v.contact_id).toBe("c1");
    expect(v.salary).toBe("");
  });
});

describe("jdBody", () => {
  it("sends trimmed text, blanks as null and openings as a number", () => {
    const body = jdBody({ ...jdValues(version, requirement), role: "  Dev ", salary: " ", openings: "7" });
    expect(body.role).toBe("Dev");
    expect(body.salary).toBeNull();
    expect(body.openings).toBe(7);
    expect(body.contact_id).toBe("c1");
  });

  it("leaves an unreadable number for the server to name", () => {
    expect(jdBody({ ...jdValues(version, requirement), openings: "lots" }).openings).toBe("lots");
  });
});

describe("requirementChangesFromJd", () => {
  it("lists only the mappable fields that differ, with the PATCH body", () => {
    const { changes, patch } = requirementChangesFromJd(version, requirement);
    expect(changes.map((c) => c.label)).toEqual(["Job title", "Job location", "Number of vacancies"]);
    expect(patch).toEqual({ title: "Senior Python Developer", location: "Pune", vacancies: 5 });
  });

  it("never clears a requirement field from an empty JD field", () => {
    const { patch } = requirementChangesFromJd({ ...version, role: "Python Developer", location: null, openings: null, closing_date: null, description: null }, requirement);
    expect(patch).toEqual({});
  });
});

describe("isJd", () => {
  it("accepts the API shape only", () => {
    expect(isJd({ jd_number: null, versions: [], can_edit: true })).toBe(true);
    expect(isJd({ detail: "x" })).toBe(false);
  });
});
