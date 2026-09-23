import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

import CareerGoalForm from "@/components/CareerGoalForm";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  refresh.mockReset();
});

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function openAndType(value: string) {
  fireEvent.click(screen.getByRole("button", { name: /(set|edit) career goal/i }));
  fireEvent.change(screen.getByLabelText(/^career goal$/i), { target: { value } });
}

describe("CareerGoalForm", () => {
  it("shows the goal with an Edit button, then a labelled input with a live counter", () => {
    render(<CareerGoalForm studentId="s1" goal="Technology" />);
    expect(screen.getByText("Technology")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /edit career goal/i }));
    const input = screen.getByLabelText(/^career goal$/i);
    expect(input).toHaveValue("Technology");
    expect(input).toHaveAttribute("maxLength", "120");
    expect(input).toHaveAccessibleDescription(/10 of 120 characters/i);
  });

  it("offers 'Set career goal' when there is none", () => {
    render(<CareerGoalForm studentId="s1" goal={null} />);
    expect(screen.getByText(/no career goal set yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /set career goal/i })).toBeInTheDocument();
  });

  it("PATCHes the trimmed value, announces success and refreshes the page data", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ school_student_id: "s1", career_goal: "Medicine", updated_at: "2026-09-23T00:00:00Z" }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("  Medicine ");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/career goal saved/i));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/school/students/s1/career-goal", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ career_goal: "Medicine" }) }));
    expect(refresh).toHaveBeenCalled();
    expect(screen.queryByLabelText(/^career goal$/i)).not.toBeInTheDocument();
  });

  it("sends null to clear the goal", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ school_student_id: "s1", career_goal: null, updated_at: "x" }));
    render(<CareerGoalForm studentId="s1" goal="Technology" />);
    openAndType("   ");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][1]?.body).toBe(JSON.stringify({ career_goal: null }));
  });

  it("keeps the typed value and shows the server's message on a refusal", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: "This student is at a school outside your own portfolio" }, 403));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("Law");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("This student is at a school outside your own portfolio"));
    expect(screen.getByLabelText(/^career goal$/i)).toHaveValue("Law");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("shows a readable validation message from a 422 list", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({ detail: [{ msg: "Value error, must be 120 characters or fewer" }] }, 422));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("x");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Must be 120 characters or fewer"));
  });

  it("on a server error says what failed, keeps the entry, and puts focus back in the input (browser QA-04)", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("Internal Server Error", { status: 500, headers: { "Content-Type": "text/plain" } }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("Law");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("The career goal could not be saved. Please try again."));
    const input = screen.getByLabelText(/^career goal$/i);
    expect(input).toHaveValue("Law");
    await waitFor(() => expect(document.activeElement).toBe(input));
  });

  it("keeps the entry and says so when the network drops", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("Arts");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/did not complete/i));
    expect(screen.getByLabelText(/^career goal$/i)).toHaveValue("Arts");
  });

  it("does not report success for a 200 that is not the saved record", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>login</html>", { status: 200 }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("Arts");
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(refresh).not.toHaveBeenCalled();
  });

  it("blocks a double submit while saving", async () => {
    let resolve!: (r: Response) => void;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(() => new Promise<Response>((r) => { resolve = r; }));
    render(<CareerGoalForm studentId="s1" goal={null} />);
    openAndType("Arts");
    const save = screen.getByRole("button", { name: /^save$/i });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: /saving/i })).toBeDisabled();
    // Read-only, not disabled, while saving: refocus() runs on the next animation frame, and a disabled input silently refuses
    // focus -- so whether focus came back after an error depended on whether React had re-enabled it by then (browser QA-04).
    const input = screen.getByLabelText(/^career goal$/i);
    expect(input).not.toBeDisabled();
    expect(input).toHaveAttribute("readonly");
    // ...and Escape still cannot close the editor mid-save (the disabled input used to swallow it; Cancel is disabled too).
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.getByLabelText(/^career goal$/i)).toBeInTheDocument();
    resolve(json({ school_student_id: "s1", career_goal: "Arts", updated_at: "x" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
  });

  it("Escape cancels without saving", () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    render(<CareerGoalForm studentId="s1" goal="Technology" />);
    fireEvent.click(screen.getByRole("button", { name: /edit career goal/i }));
    fireEvent.keyDown(screen.getByLabelText(/^career goal$/i), { key: "Escape" });
    expect(screen.queryByLabelText(/^career goal$/i)).not.toBeInTheDocument();
    expect(screen.getByText("Technology")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
