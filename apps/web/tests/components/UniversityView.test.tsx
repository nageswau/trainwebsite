import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import UniversityViewPanel from "@/components/UniversityView";
import type { UniversityView } from "@/lib/universityView";

// upc-030: one component for every portal; it renders exactly the sections the API's slice carries.
const profile: UniversityView["university"] = {
  id: "u1", university_code: "UNI-000123", name: "ABC University", institution_type: "university", ownership_type: "public",
  country: { name: "United Kingdom", iso2: "GB", region: "UK" }, state_region: "Greater London", city: "London", website: "https://abc.ac.uk",
  overview: "A research university.", eligibility: "", course_levels: ["UG", "PG"], popular_programs: ["Business"],
  rankings: [{ system: "QS", other_name: null, year: 2026, rank: "145" }],
};
const counselor: UniversityView = {
  slice: "counselor",
  university: profile,
  partnership: { stage: "active_partner", stage_label: "Active Partner", lost: false },
  contacts: [{ id: "c1", name: "Asha Admissions", designation: "Admissions Officer", department: null, role: null, email: "asha@abc.example", phone: null, whatsapp: null, linkedin: null, preferred_channel: "email", is_primary: true }],
  courses: [{
    id: "k1", title: "MSc Data Science", level: "PG", category: "Computing", duration: "1 year", tuition_fee: "GBP 20,000", tuition_amount: "20000.00",
    tuition_currency: "GBP", application_fee: null, application_fee_currency: null, intakes: ["Sep", "Jan"], intake: "Sep", entry_requirements: "A 2:1 degree",
    english_test: "IELTS", english_score: "6.5", scholarships: [], application_process: null, deadline: null,
  }],
  documents: [{ id: "d1", kind: "fee_structure", title: "Fees 2026", current_version: 2, updated_at: "2026-10-01T10:00:00Z" }],
  applications: [{ id: "a1", reference: "APP-1", student_name: "Ravi Kumar", intake: "Sep 2027", status: "offer", next_action: "Pay deposit", updated_at: "2026-10-02T10:00:00Z" }],
};

afterEach(cleanup);

describe("UniversityView", () => {
  it("shows the counselor every section, with IELTS requirements and a document download", () => {
    render(<UniversityViewPanel view={counselor} />);
    expect(screen.getByRole("heading", { level: 2, name: "ABC University" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Partnership" })).toHaveTextContent("Active Partner");
    const courses = screen.getByRole("region", { name: "Courses" });
    expect(within(courses).getByText("IELTS 6.5")).toBeInTheDocument();
    expect(within(courses).getByText("A 2:1 degree")).toBeInTheDocument();
    expect(within(courses).getByText("GBP 20000.00")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Application contacts" })).toHaveTextContent("Asha Admissions");
    const download = screen.getByRole("link", { name: /Download Fees 2026/ });
    expect(download).toHaveAttribute("href", "/api/v1/universities/u1/view/documents/d1/file");
    expect(screen.getByRole("region", { name: "Your students' applications" })).toHaveTextContent("Ravi Kumar");
    expect(screen.getByRole("link", { name: /https:\/\/abc.ac.uk/ })).toHaveAttribute("href", "https://abc.ac.uk");
  });

  it("shows a BDM the profile, stage and manager only", () => {
    render(<UniversityViewPanel view={{ slice: "bdm", university: profile, partnership: counselor.partnership, manager: { full_name: "Priya Manager", email: "priya@x.example" } }} />);
    expect(screen.getByRole("region", { name: "Partnership" })).toHaveTextContent("Priya Manager");
    for (const name of ["Courses", "Application contacts", "Documents", "Your students' applications"]) {
      expect(screen.queryByRole("region", { name })).toBeNull();
    }
  });

  it("says when no manager is assigned yet", () => {
    render(<UniversityViewPanel view={{ slice: "bdm", university: profile, partnership: counselor.partnership, manager: null }} />);
    expect(screen.getByRole("region", { name: "Partnership" })).toHaveTextContent("Not assigned yet");
  });

  it("shows a university rep the profile and courses, and empty states in words", () => {
    render(<UniversityViewPanel view={{ slice: "university_rep", university: profile, courses: [] }} />);
    expect(screen.getByRole("region", { name: "Courses" })).toHaveTextContent("No active courses yet.");
    expect(screen.queryByRole("region", { name: "Partnership" })).toBeNull();
  });

  it("labels overseas_admin's applications as all applications and shows empty sections", () => {
    render(<UniversityViewPanel view={{ ...counselor, slice: "overseas_admin", contacts: [], documents: [], applications: [] }} />);
    expect(screen.getByRole("region", { name: "Applications" })).toHaveTextContent("No applications for this university yet.");
    expect(screen.getByRole("region", { name: "Application contacts" })).toHaveTextContent("No shareable contacts yet.");
    expect(screen.getByRole("region", { name: "Documents" })).toHaveTextContent("No shareable documents yet.");
  });

  it("never links a website that is not http(s)", () => {
    render(<UniversityViewPanel view={{ slice: "university_rep", university: { ...profile, website: "javascript:alert(1)" }, courses: [] }} />);
    expect(screen.queryByRole("link", { name: /javascript/ })).toBeNull();
    expect(screen.getByText("javascript:alert(1)")).toBeInTheDocument();
  });
});
