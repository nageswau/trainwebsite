import { describe, expect, it } from "vitest";

import { PORTAL_NAV, RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { EMPTY_FORM, candidateBody, experienceLabel, FIELDS, formFromDetail, missingRequired, packageText, STATUS_LABEL, type CandidateDetail } from "@/lib/recruiterCandidates";

const filled = {
  ...EMPTY_FORM, name: " Rahul ", mobile: "98765 43210", email: "", source_id: "s1", experience_months: "30",
  current_salary: "450000", preferred_locations: "Hyderabad, Bengaluru ,, ", linkedin: " https://linkedin.com/in/r ",
};

describe("rec-009 candidate form mapping", () => {
  it("sends only the filled fields on create, numbers as numbers and the places as a list", () => {
    expect(candidateBody(filled, "create")).toEqual({
      name: "Rahul", mobile: "98765 43210", source_id: "s1", experience_months: 30, current_salary: "450000",
      current_salary_currency: "INR", current_salary_period: "year", // hrc-011: the currency and period go with their amount
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

  it("hrc-001: without the compensation grant no salary key is sent and there is no salary input", () => {
    for (const mode of ["create", "edit"] as const) {
      const body = candidateBody({ ...filled, expected_salary: "1" }, mode, false);
      expect(body).not.toHaveProperty("current_salary");
      expect(body).not.toHaveProperty("expected_salary");
    }
    expect(FIELDS.map((f) => f.key).filter((k) => k.includes("salary"))).toEqual([]); // hrc-011: the compensation group has its own inputs
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
    expect(form).toMatchObject({ name: "R", mobile: "", email: "r@x.com", source_id: "s", status: "placed",
      experience_months: "14", current_salary: "450000.00", preferred_locations: "Pune, Goa", location: "" });
  });

  it("hrc-011: sends each amount with its currency and period, Negotiable as true/false/null, and nothing for an empty amount", () => {
    const form = { ...filled, current_salary: "50000", current_salary_period: "month", expected_salary: "4000", expected_salary_currency: "USD",
      expected_salary_period: "month", minimum_salary: "", minimum_salary_currency: "USD", salary_negotiable: "yes" };
    const created = candidateBody(form, "create");
    expect(created).toMatchObject({ current_salary: "50000", current_salary_currency: "INR", current_salary_period: "month", expected_salary: "4000",
      expected_salary_currency: "USD", expected_salary_period: "month", salary_negotiable: true });
    expect(created).not.toHaveProperty("minimum_salary_currency");
    const edited = candidateBody({ ...form, salary_negotiable: "" }, "edit");
    expect(edited).toMatchObject({ minimum_salary: null, minimum_salary_currency: null, minimum_salary_period: null, salary_negotiable: null });
    expect(candidateBody({ ...form, salary_negotiable: "no" }, "edit").salary_negotiable).toBe(false);
  });

  it("hrc-011: round-trips the package and shows the amount as entered, with its annual INR when it differs", () => {
    const detail = { source: { id: "s" }, preferred_locations: [], current_salary: "50000.00", current_salary_currency: "INR", current_salary_period: "month",
      current_annual_inr: "600000.00", expected_salary: "4000.00", expected_salary_currency: "USD", expected_salary_period: "month",
      expected_annual_inr: "3996000.00", minimum_salary: "700000.00", minimum_salary_currency: "INR", minimum_salary_period: "year",
      minimum_annual_inr: "700000.00", salary_negotiable: false } as unknown as CandidateDetail;
    expect(formFromDetail(detail)).toMatchObject({ current_salary: "50000.00", current_salary_period: "month", expected_salary_currency: "USD", salary_negotiable: "no" });
    expect(packageText(detail, "current")).toBe("₹50,000 per month (≈ ₹6,00,000 a year)");
    expect(packageText(detail, "expected")).toBe("USD 4,000 per month (≈ ₹39,96,000 a year)");
    expect(packageText(detail, "minimum")).toBe("₹7,00,000 per year");
    expect(packageText({ ...detail, minimum_salary: null }, "minimum")).toBeNull();
    expect(formFromDetail({ ...detail, minimum_salary: null, minimum_salary_currency: null, salary_negotiable: null })).toMatchObject({ minimum_salary: "", minimum_salary_currency: "INR", salary_negotiable: "" });
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
