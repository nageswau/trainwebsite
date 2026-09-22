import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

import PortfolioPanel, { type PortfolioData } from "@/components/PortfolioPanel";

afterEach(() => {
  cleanup();
});

const BASE: PortfolioData = {
  student: { id: "s1", full_name: "Test Student" },
  completion_percentage: 0,
  can_edit: false,
  profile_complete: false,
  academic_achievements: [], psychometric_report: [], career_guidance: [], languages: [],
  entries: { project: [], internship: [], competition: [], sport: [], leadership: [], volunteering: [], extracurricular: [], award: [], certification: [], skill: [] },
  personal_statement: null,
};

describe("PortfolioPanel", () => {
  it("shows the completion percentage as visible text", () => {
    render(<PortfolioPanel data={{ ...BASE, completion_percentage: 25 }} />);
    expect(screen.getByText(/25% complete/i)).toBeInTheDocument();
  });

  it("renders an empty-state message per empty section", () => {
    render(<PortfolioPanel data={BASE} />);
    expect(screen.getAllByText("No entries yet.").length).toBeGreaterThan(0);
  });

  it("does not render any Add button for a read-only viewer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: false }} />);
    expect(screen.queryByRole("button", { name: /add/i })).not.toBeInTheDocument();
  });

  it("renders an Add button per self-entry section for a writer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true }} />);
    expect(screen.getAllByRole("button", { name: /add/i }).length).toBe(10);
  });

  it("clicking Add opens the entry form for that section", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true }} />);
    fireEvent.click(screen.getAllByRole("button", { name: /add project/i })[0]);
    expect(screen.getByLabelText(/title/i)).toBeInTheDocument();
  });

  it("shows Edit and Delete for each existing entry when can_edit is true", () => {
    const data: PortfolioData = { ...BASE, can_edit: true, entries: { ...BASE.entries, project: [{ id: "e1", section: "project", title: "Robotics", description: null, organization: null, date_from: null, date_to: null, created_at: "2026-01-01", updated_at: "2026-01-01" }] } };
    render(<PortfolioPanel data={data} />);
    expect(screen.getByRole("button", { name: /edit robotics/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /delete robotics/i })).toBeInTheDocument();
  });

  it("delete requires a second confirming click", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => null });
    global.fetch = fetchMock as unknown as typeof fetch;
    const data: PortfolioData = { ...BASE, can_edit: true, entries: { ...BASE.entries, project: [{ id: "e1", section: "project", title: "Robotics", description: null, organization: null, date_from: null, date_to: null, created_at: "2026-01-01", updated_at: "2026-01-01" }] } };
    render(<PortfolioPanel data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /delete robotics/i }));
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /confirm delete/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/portfolio/entries/e1", expect.objectContaining({ method: "DELETE" })));
  });
});
