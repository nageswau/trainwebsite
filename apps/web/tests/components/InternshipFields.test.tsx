import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import PortfolioEntryForm from "@/components/PortfolioEntryForm";
import PortfolioPanel, { type PortfolioData } from "@/components/PortfolioPanel";
import { internshipChanges } from "@/lib/internship";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("internship entry form (ENH-021)", () => {
  it("names the fields Role and Company, and requires a company", async () => {
    render(<PortfolioEntryForm studentId="s1" section="internship" onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Design intern" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Enter the company.")).toBeInTheDocument();
  });

  it("creates with the tracking fields that were filled in", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "e1" }) });
    vi.stubGlobal("fetch", fetchMock);
    render(<PortfolioEntryForm studentId="s1" section="internship" onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Design intern" } });
    fireEvent.change(screen.getByLabelText("Company"), { target: { value: "Acme" } });
    fireEvent.change(screen.getByLabelText("Mentor name (optional)"), { target: { value: "R. Rao" } });
    fireEvent.change(screen.getByLabelText("Attendance % (optional)"), { target: { value: "92" } });
    fireEvent.change(screen.getByLabelText("Skills acquired (optional)"), { target: { value: "Figma, Research" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body).toMatchObject({ section: "internship", title: "Design intern", organization: "Acme", mentor_name: "R. Rao", attendance_percent: 92, skills_acquired: ["Figma", "Research"] });
    expect(body).not.toHaveProperty("feedback");
  });

  it("sends only the internship fields that changed on edit", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ id: "e1" }) });
    vi.stubGlobal("fetch", fetchMock);
    const initial = { title: "Intern", description: null, organization: "Acme", date_from: null, date_to: null, mentor_name: "R", mentor_designation: null, attendance_percent: 90, completion_status: null, feedback: null, skills_acquired: null };
    render(<PortfolioEntryForm studentId="s1" section="internship" entryId="e1" initial={initial} onDone={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Senior intern" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.title).toBe("Senior intern");
    expect(body).not.toHaveProperty("mentor_name"); // unchanged tracking fields are not sent (keeps the Gold gate)
    expect(body).not.toHaveProperty("attendance_percent");
  });

  it("computes changed internship fields", () => {
    expect(internshipChanges({ mentor_name: "A", skills_acquired: ["x"] }, { mentor_name: "A", skills_acquired: ["x", "y"] })).toEqual({ skills_acquired: ["x", "y"] });
  });
});

describe("internship entry in the portfolio (ENH-021)", () => {
  const data: PortfolioData = {
    student: { id: "s1", full_name: "Test Student" }, completion_percentage: 0, can_edit: false, profile_complete: false,
    academic_achievements: [], psychometric_report: [], career_guidance: [], languages: [], personal_statement: null,
    entries: {
      project: [], competition: [], sport: [], leadership: [], volunteering: [], extracurricular: [], award: [], certification: [], skill: [],
      internship: [{ id: "e1", section: "internship", title: "Design intern", description: null, organization: "Acme", date_from: "2026-05-01", date_to: "2026-06-30",
        created_at: "2026-06-30T00:00:00Z", updated_at: "2026-06-30T00:00:00Z", mentor_name: "R. Rao", mentor_designation: "Lead designer",
        attendance_percent: 92, completion_status: "completed", feedback: null, skills_acquired: ["Figma"], has_certificate: true, certificate_content_type: "application/pdf" }],
    },
  };

  it("shows status in words, mentor, attendance, skills and a download link for a reader", () => {
    render(<PortfolioPanel data={data} />);
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("R. Rao, Lead designer")).toBeInTheDocument();
    expect(screen.getByText("92%")).toBeInTheDocument();
    expect(screen.getByText("Figma")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download certificate (PDF)" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Upload certificate|Replace certificate/)).toBeNull();
  });

  it("labels an internship recorded before tracking", () => {
    const legacy = { ...data.entries.internship[0], completion_status: null, mentor_name: null, mentor_designation: null, attendance_percent: null, skills_acquired: null, has_certificate: false, certificate_content_type: null };
    render(<PortfolioPanel data={{ ...data, entries: { ...data.entries, internship: [legacy] } }} />);
    expect(screen.getByText("No status")).toBeInTheDocument();
  });
});
