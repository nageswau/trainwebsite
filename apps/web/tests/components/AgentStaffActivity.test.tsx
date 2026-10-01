import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStaffActivity from "@/components/AgentStaffActivity";
import { activityLabel, type StaffMember } from "@/lib/agentStaff";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const member: StaffMember = { id: "m1", code: "ABC-S001", full_name: "Priya", email: "p@example.local", phone: null, status: "active", setup: null, permissions: { can_verify_documents: false, can_view_reports: false } };
const item = (n: number, action = "agent_student.create", extra: Record<string, unknown> = {}) => ({ id: `a${n}`, at: "2026-10-01T09:30:00Z", action, subject: `Student ${n}`, fields: null, ...extra });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 10, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("activityLabel (AGN-021)", () => {
  it("labels every allow-listed action and falls back for others", () => {
    expect(activityLabel("agent_student.create")).toBe("Created a student record");
    expect(activityLabel("document.verify")).toBe("Verified a document");
    expect(activityLabel("something.new")).toBe("Other activity");
  });
});

describe("AgentStaffActivity (AGN-021)", () => {
  it("shows loading, then the member's activity with subject, edited field names and time", async () => {
    const mock = vi.fn().mockResolvedValue(res(page([item(1), item(2, "agent_student.update", { fields: ["phone", "date_of_birth"] })])));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    expect(screen.getByText("Loading activity…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Activity of ABC-S001" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText(/Edited a student record/)).toBeInTheDocument();
    expect(within(list).getByText(/Student 2 — phone, date of birth/)).toBeInTheDocument();
    expect(list.querySelector("time")).toHaveAttribute("dateTime", "2026-10-01T09:30:00Z");
    expect(mock.mock.calls[0][0]).toBe("/api/v1/workflows/overseas/agent/team/staff/m1/activity?limit=10&offset=0");
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    expect(await screen.findByText("No activity yet.")).toBeInTheDocument();
  });

  it("shows the server's message for a refused request and recovers with Try again", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "Staff member not found" }, 404)).mockResolvedValueOnce(res(page([item(1)]))));
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Staff member not found");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/Student 1/)).toBeInTheDocument();
  });

  it("says Unable to load activity for a server error, a dropped connection or a body that is not a page", async () => {
    // Lazy, so the rejected promise only exists once fetch is called (an eager Promise.reject is an unhandled rejection).
    for (const failure of [() => Promise.resolve(res({ detail: "boom" }, 500)), () => Promise.reject(new TypeError("Failed to fetch")), () => Promise.resolve(res("<html>"))]) {
      vi.stubGlobal("fetch", vi.fn().mockImplementation(failure));
      render(<AgentStaffActivity member={member} onClose={() => {}} />);
      expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load activity.");
      cleanup();
    }
  });

  it("pages through activity and refreshes the current page", async () => {
    const ten = Array.from({ length: 10 }, (_, i) => item(i + 1));
    const mock = vi.fn().mockResolvedValueOnce(res(page(ten, 11))).mockResolvedValueOnce(res(page([item(11)], 11, 10))).mockResolvedValueOnce(res(page([item(11)], 11, 10)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    const pager = await screen.findByRole("navigation", { name: "Activity pages" });
    expect(within(pager).getByText("Showing 1–10 of 11")).toBeInTheDocument();
    expect(within(pager).getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Showing 11–11 of 11")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await vi.waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    expect(mock.mock.calls[2][0]).toContain("offset=10");
  });

  it("ignores a response older than the latest request", async () => {  // Review Focus 3
    let slow: (r: Response) => void = () => {};
    const mock = vi.fn()
      .mockResolvedValueOnce(res(page(Array.from({ length: 10 }, (_, i) => item(i + 1)), 11)))
      .mockReturnValueOnce(new Promise<Response>((r) => { slow = r; }))
      .mockResolvedValueOnce(res(page(Array.from({ length: 10 }, (_, i) => item(i + 1)), 11)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStaffActivity member={member} onClose={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" })); // request 2 hangs
    fireEvent.click(screen.getByRole("button", { name: "Refresh" })); // request 3 resolves first
    await vi.waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    slow(res(page([item(99)], 11, 10)));
    await new Promise((r) => setTimeout(r, 0));
    expect(screen.queryByText(/Student 99/)).toBeNull();
  });

  it("closes with the Close button and with Escape", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([item(1)]))));
    const onClose = vi.fn();
    render(<AgentStaffActivity member={member} onClose={onClose} />);
    fireEvent.click(await screen.findByRole("button", { name: "Close activity" }));
    fireEvent.keyDown(screen.getByRole("region", { name: "Activity" }), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
