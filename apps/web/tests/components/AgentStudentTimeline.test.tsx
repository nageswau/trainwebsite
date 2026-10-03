import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentTimeline from "@/components/AgentStudentTimeline";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `s2:${n}`,
  at: "2026-10-01T09:30:00Z",
  kind: "counseling_saved",
  actor: "Priya",
  application: null,
  document: null,
  from_status: null,
  to_status: null,
  fields: ["budget_amount"],
  notes: null,
  ...extra,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const URL = "/api/v1/workflows/overseas/agent/crm/students/s1/timeline";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentStudentTimeline (AGN-015)", () => {
  it("loads nothing until Show history, then lists events with actor, subject, stages and notes", async () => {
    const mock = vi.fn().mockResolvedValue(
      res(
        page([
          item(1),
          item(2, {
            kind: "application_stage_changed",
            actor: "EduSphere counsellor",
            application: { id: "a1", university: "Leeds" },
            from_status: "enquiry",
            to_status: "offer",
            fields: null,
            notes: "Offer recorded: Conditional",
          }),
          item(3, { kind: "document_verified", document: { id: "d1", type: "Passport" }, from_status: "pending", to_status: "verified", fields: null }),
        ]),
      ),
    );
    vi.stubGlobal("fetch", mock);
    render(<AgentStudentTimeline studentId="s1" />);
    expect(mock).not.toHaveBeenCalled();
    const toggle = screen.getByRole("button", { name: "Show history" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Hide history" })).toHaveAttribute("aria-expanded", "true");
    const list = await screen.findByRole("list", { name: "Student history" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Counseling saved");
    expect(rows[0]).toHaveTextContent("budget amount");
    expect(rows[0]).toHaveTextContent("Priya");
    expect(rows[1]).toHaveTextContent("Application stage changed · Leeds · Enquiry → Offer");
    expect(rows[1]).toHaveTextContent("EduSphere counsellor");
    expect(rows[1]).toHaveTextContent("Offer recorded: Conditional");
    expect(rows[2]).toHaveTextContent("Document verified · Passport · Pending → Verified");
    expect(within(rows[0]).getByText(/2026|Oct/, { selector: "time" })).toHaveAttribute("dateTime", "2026-10-01T09:30:00Z");
    expect(mock).toHaveBeenCalledWith(`${URL}?limit=20&offset=0`);
  });

  it("shows the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("No history yet.")).toBeInTheDocument();
  });

  it("pages with Next and Previous", async () => {
    const mock = vi
      .fn()
      .mockResolvedValueOnce(res(page(Array.from({ length: 20 }, (_, i) => item(i)), 25)))
      .mockResolvedValueOnce(res(page([item(99)], 25, 20)));
    vi.stubGlobal("fetch", mock);
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Showing 1–20 of 25")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Showing 21–21 of 25")).toBeInTheDocument();
    expect(mock).toHaveBeenLastCalledWith(`${URL}?limit=20&offset=20`);
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
  });

  it("shows a retryable error, then a sign-in link on 401", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({}, 500)).mockResolvedValueOnce(res({}, 401)));
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Unable to load history.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Sign in again" })).toBeInTheDocument();
  });

  it("treats an unexpected body as an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ student: {} })));
    render(<AgentStudentTimeline studentId="s1" />);
    fireEvent.click(screen.getByRole("button", { name: "Show history" }));
    expect(await screen.findByText("Unable to load history.")).toBeInTheDocument();
  });
});
