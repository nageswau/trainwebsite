import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentNetworkRecords from "@/components/AgentNetworkRecords";

const ID = "3f2b8c1e-9d4a-4b7e-8f21-0c6d5e4a3b2f";
const BASE = `/api/v1/overseas-admin/agent-orgs/${ID}`;
const page = (items: unknown[], total = items.length, offset = 0) => new Response(JSON.stringify({ items, total, limit: 20, offset }), { status: 200 });
const student = (id: string, over: Record<string, unknown> = {}) => ({ id, full_name: `Student ${id}`, status: "active", assigned_code: "KAP-S001", has_login: false, applications: 2, created_at: "2026-09-30T00:00:00Z", ...over });
const application = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  student_name: `Student ${id}`,
  university: "Alpha University",
  country: "Aland",
  status: "visa_documentation",
  enrollment_date: null,
  created_at: "2026-09-30T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
  ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentNetworkRecords (AGN-022)", () => {
  it("lists students read-only with assignee and login, and switches to archived (AC7, AC9)", async () => {
    const mock = vi.fn().mockResolvedValueOnce(page([student("s1", { assigned_code: null, has_login: true })])).mockResolvedValueOnce(page([]));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkRecords orgId={ID} kind="students" />);
    expect(screen.getByText("Loading students…")).toBeInTheDocument();
    const row = (await screen.findByText("Student s1")).closest("tr") as HTMLElement;
    expect(within(row).getByText("Unassigned")).toBeInTheDocument();
    expect(within(row).getByText("Yes")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^(edit|delete|archive|assign)\b(?!d)/i })).toBeNull(); // "Archived" is the filter, not an action
    fireEvent.click(screen.getByRole("button", { name: "Archived" }));
    expect(await screen.findByText("No archived students.")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${BASE}/students?status=archived&limit=20&offset=0`);
  });

  it("lists applications with the stage label and pages through them", async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => application(`a${i}`));
    const mock = vi.fn().mockResolvedValueOnce(page(twenty, 25)).mockResolvedValueOnce(page([application("b", { status: "enrolled", enrollment_date: "2026-09-01" })], 25, 20));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkRecords orgId={ID} kind="applications" />);
    expect(await screen.findAllByText("Visa documentation")).toHaveLength(20);
    expect(mock.mock.calls[0][0]).toBe(`${BASE}/applications?limit=20&offset=0`);
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Enrolled")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${BASE}/applications?limit=20&offset=20`);
    expect(screen.getByText("Showing 21–21 of 25")).toBeInTheDocument();
  });

  it("says that withdrawn applications are listed although the Applications figure leaves them out (QA22-04)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([application("w", { status: "withdrawn" })])));
    render(<AgentNetworkRecords orgId={ID} kind="applications" />);
    expect(await screen.findByText("Withdrawn")).toBeInTheDocument();
    expect(screen.getByText("Withdrawn applications are listed here; the Applications figure above leaves them out.")).toBeInTheDocument();
  });

  it("on a page that emptied while browsing, offers the first page instead of claiming there are no records (final review)", async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => student(`s${i}`));
    const mock = vi
      .fn()
      .mockResolvedValueOnce(page(twenty, 21))
      .mockResolvedValueOnce(page([], 18, 20)) // rows were archived meanwhile
      .mockResolvedValueOnce(page([student("x")], 18, 0));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkRecords orgId={ID} kind="students" />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    expect(await screen.findByText("No students on this page.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go to the first page" }));
    expect(await screen.findByText("Student x")).toBeInTheDocument();
    expect(mock.mock.calls[2][0]).toBe(`${BASE}/students?status=active&limit=20&offset=0`);
  });

  it("shows the empty text, and an error with a working Retry", async () => {
    const mock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 500 })).mockResolvedValueOnce(page([]));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkRecords orgId={ID} kind="applications" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load applications.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No applications yet.")).toBeInTheDocument();
  });
});
