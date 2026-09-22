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
    // 10 self-entry sections' own Add buttons -- excludes the personal statement's "Add statement"
    // affordance (Task 1), which also matches /add/i but isn't a section entry-add button.
    const addButtons = screen.getAllByRole("button", { name: /add/i }).filter((btn) => !/statement/i.test(btn.textContent ?? ""));
    expect(addButtons.length).toBe(10);
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

  it("a fast double-click on Confirm delete only sends one DELETE request", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    const fetchMock = vi.fn().mockImplementation(() => new Promise((resolve) => { resolveFetch = resolve; }));
    global.fetch = fetchMock as unknown as typeof fetch;
    const data: PortfolioData = { ...BASE, can_edit: true, entries: { ...BASE.entries, project: [{ id: "e1", section: "project", title: "Robotics", description: null, organization: null, date_from: null, date_to: null, created_at: "2026-01-01", updated_at: "2026-01-01" }] } };
    render(<PortfolioPanel data={data} />);
    fireEvent.click(screen.getByRole("button", { name: /delete robotics/i }));
    const confirmBtn = screen.getByRole("button", { name: /confirm delete/i });
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);
    fireEvent.click(confirmBtn);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolveFetch({ ok: true, status: 204, json: async () => null });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("renders a Profile section reflecting profile_complete", () => {
    render(<PortfolioPanel data={{ ...BASE, profile_complete: true }} />);
    expect(screen.getByText(/profile complete/i)).toBeInTheDocument();
  });

  it("shows an Add statement affordance for a writer with no statement yet", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true, personal_statement: null }} />);
    expect(screen.getByRole("button", { name: /add statement/i })).toBeInTheDocument();
  });

  it("shows an Edit statement affordance for a writer with an existing statement", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: true, personal_statement: "I want to study engineering." }} />);
    expect(screen.getByRole("button", { name: /edit statement/i })).toBeInTheDocument();
  });

  it("does not show any personal-statement edit affordance for a read-only viewer", () => {
    render(<PortfolioPanel data={{ ...BASE, can_edit: false, personal_statement: "I want to study engineering." }} />);
    expect(screen.queryByRole("button", { name: /edit statement/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /add statement/i })).not.toBeInTheDocument();
  });

  it("clicking Edit statement reveals a textarea, and Save PATCHes the personal-statement endpoint", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ personal_statement: "Updated.", updated_at: "2026-01-01" }) });
    global.fetch = fetchMock as unknown as typeof fetch;
    render(<PortfolioPanel data={{ ...BASE, can_edit: true, personal_statement: "Original." }} />);
    fireEvent.click(screen.getByRole("button", { name: /edit statement/i }));
    const textarea = screen.getByLabelText(/personal statement/i);
    expect(textarea).toBeInTheDocument();
    fireEvent.change(textarea, { target: { value: "Updated." } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/school/students/s1/portfolio/personal-statement",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ personal_statement: "Updated." }) }),
    ));
  });
});
