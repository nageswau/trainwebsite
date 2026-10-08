import { describe, expect, it } from "vitest";

import { PORTAL_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { EMPTY_FORM, candidateBody, experienceLabel, formFromDetail, missingRequired, STATUS_LABEL, type CandidateDetail } from "@/lib/recruiterCandidates";

const filled = {
  ...EMPTY_FORM, name: " Rahul ", mobile: "98765 43210", email: "", source_id: "s1", passing_year: "2022", experience_months: "30",
  current_salary: "450000", preferred_locations: "Hyderabad, Bengaluru ,, ", linkedin: " https://linkedin.com/in/r ",
};

describe("rec-009 candidate form mapping", () => {
  it("sends only the filled fields on create, numbers as numbers and the places as a list", () => {
    expect(candidateBody(filled, "create")).toEqual({
      name: "Rahul", mobile: "98765 43210", source_id: "s1", passing_year: 2022, experience_months: 30, current_salary: "450000",
      preferred_locations: ["Hyderabad", "Bengaluru"], linkedin: "https://linkedin.com/in/r", status: "available",
    });
  });

  it("sends every field on edit, a cleared one as null, so a value can be removed", () => {
    const body = candidateBody({ ...filled, location: "", current_salary: "" }, "edit");
    expect(body.location).toBeNull();
    expect(body.current_salary).toBeNull();
    expect(body.email).toBeNull();
    expect(body.preferred_locations).toEqual(["Hyderabad", "Bengaluru"]);
    expect(Object.keys(body)).toHaveLength(Object.keys(EMPTY_FORM).length);
  });

  it("names the missing required fields: name, source and a mobile or an email", () => {
    expect(missingRequired(EMPTY_FORM)).toBe("Enter the name, source and a mobile number or an email.");
    expect(missingRequired({ ...EMPTY_FORM, name: "R", source_id: "s", email: "r@x.com" })).toBeNull();
    expect(missingRequired({ ...EMPTY_FORM, name: "R", mobile: "9" })).toBe("Enter the source.");
    // QA-01: never "the a mobile number" when only the contact is missing
    expect(missingRequired({ ...EMPTY_FORM, name: "R", source_id: "s" })).toBe("Enter a mobile number or an email.");
    expect(missingRequired({ ...EMPTY_FORM, source_id: "s" })).toBe("Enter the name and a mobile number or an email.");
    expect(missingRequired({ ...EMPTY_FORM, email: "r@x.com" })).toBe("Enter the name and source.");
  });

  it("round-trips a detail into the edit form", () => {
    const detail = { name: "R", mobile: null, email: "r@x.com", source: { id: "s", name: "LinkedIn", active: true }, status: "placed",
      passing_year: 2020, experience_months: 14, current_salary: "450000.00", preferred_locations: ["Pune", "Goa"] } as unknown as CandidateDetail;
    const form = formFromDetail(detail);
    expect(form).toMatchObject({ name: "R", mobile: "", email: "r@x.com", source_id: "s", status: "placed", passing_year: "2020",
      experience_months: "14", current_salary: "450000.00", preferred_locations: "Pune, Goa", location: "" });
  });

  it("reads experience in years and months", () => {
    expect(experienceLabel(null)).toBe("—");
    expect(experienceLabel(0)).toBe("Fresher");
    expect(experienceLabel(5)).toBe("5 mo");
    expect(experienceLabel(24)).toBe("2 yr");
    expect(experienceLabel(30)).toBe("2 yr 6 mo");
  });

  it("labels the five Q-08 statuses", () => {
    expect(Object.values(STATUS_LABEL)).toEqual(["Available", "Interviewing", "Placed", "Not looking", "Do not contact"]);
  });
});

describe("rec-009 navigation", () => {
  it("adds Candidates for recruiters, managers, super admin and (read only) HR", () => {
    expect(RECRUITER_NAV).toContainEqual({ label: "Candidate Master", href: "/recruiter/candidates" });
    expect(RECRUITER_MANAGER_NAV).toContainEqual({ label: "Candidate Master", href: "/recruiter/candidates" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Candidate Master", href: "/recruiter/candidates" });
    expect(PORTAL_NAV["it/hr"]).toContainEqual({ label: "Candidate Master", href: "/recruiter/candidates" });
  });
});
