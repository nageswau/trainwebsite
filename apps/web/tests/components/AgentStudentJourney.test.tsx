import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentJourney from "@/components/AgentStudentJourney";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const journey = {
  student: { id: "s1", full_name: "Asha", status: "active" },
  steps: [
    { key: "create", state: "done" },
    { key: "counseling", state: "in_progress" },
    { key: "shortlist", state: "not_started" },
    { key: "documents", state: "not_started" },
  ],
  applications: [
    {
      id: "a1",
      university: "Leeds",
      intake: "Fall 2027",
      status: "offer",
      steps: [
        { key: "application", state: "done" },
        { key: "offer", state: "done" },
        { key: "deposit", state: "not_required" },
        { key: "visa", state: "in_progress" },
        { key: "enrollment", state: "not_started" },
      ],
    },
  ],
};
// The glyph is aria-hidden decoration; what a reader gets is the step name and its state as text.
const spoken = (li: HTMLElement) => `${li.querySelector(".jny-name")?.textContent} ${li.querySelector(".jny-state")?.textContent}`;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStudentJourney (AGN-015)", () => {
  it("shows loading, then each step with its state as text and the current step marked", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(journey)));
    render(<AgentStudentJourney studentId="s1" />);
    expect(screen.getByText("Loading journey…")).toBeInTheDocument();
    const steps = await screen.findByRole("list", { name: "Student steps" });
    expect(within(steps).getAllByRole("listitem").map(spoken)).toEqual(["Create Done", "Counseling In progress", "Shortlist Not started", "Documents Not started"]);
    expect(within(steps).getByText("Counseling").closest("li")).toHaveAttribute("aria-current", "step");
    const app = screen.getByRole("list", { name: "Steps for Leeds" });
    expect(within(app).getByText("Deposit").closest("li")).toHaveTextContent("Not required");
    expect(within(app).getByText("Visa").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("Leeds · Fall 2027 · Offer")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Journey" })).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/v1/workflows/overseas/agent/crm/students/s1/journey");
  });

  it("says when there are no applications", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ ...journey, applications: [] })));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByText("No applications yet.")).toBeInTheDocument();
  });

  it("shows an error with Try again, and recovers", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(journey)));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByText("Unable to load the journey.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("list", { name: "Student steps" })).toBeInTheDocument();
  });

  it("announces a failure through a live region that exists before it (QA15-07), and never as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({}, 500)).mockResolvedValueOnce(res(journey)));
    const { container } = render(<AgentStudentJourney studentId="s1" />);
    const live = container.querySelector(".jny [aria-live='polite']");
    expect(live).not.toBeNull();
    expect(live).toHaveTextContent("");
    await screen.findByText("Try again");
    expect(live).toHaveTextContent("Unable to load the journey.");
    expect(screen.queryByRole("alert")).toBeNull(); // the detail panel's own alerts stay unique
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByRole("list", { name: "Student steps" });
    expect(live).toHaveTextContent("");
  });

  it("offers sign-in on an expired session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({}, 401)));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByRole("link", { name: "Sign in again" })).toBeInTheDocument();
  });

  it("treats an unexpected body or a dropped connection as an error, not a crash", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ items: [], total: 0 })).mockRejectedValueOnce(new TypeError("offline")));
    render(<AgentStudentJourney studentId="s1" />);
    expect(await screen.findByText("Unable to load the journey.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Unable to load the journey.")).toBeInTheDocument();
  });

  it("reloads when the student changes", async () => {
    const mock = vi.fn().mockResolvedValue(res(journey));
    vi.stubGlobal("fetch", mock);
    const { rerender } = render(<AgentStudentJourney studentId="s1" refreshKey="t1" />);
    await screen.findByRole("list", { name: "Student steps" });
    rerender(<AgentStudentJourney studentId="s1" refreshKey="t2" />);
    await vi.waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
  });
});
