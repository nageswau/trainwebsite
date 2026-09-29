import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApprovalPanel from "@/components/AgentApprovalPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const master = { id: "m1", code: "ABC-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active" };
const org = (id: string, status: string, name = `Agency ${id}`) => ({ id, name, prefix: "ABC", status, created_at: "2026-09-28T00:00:00Z", masters: [master] });
const page = (items: unknown[], total = items.length, offset = 0) => new Response(JSON.stringify({ items, total, limit: 20, offset }), { status: 200 });
const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const LIST = "/api/v1/overseas-admin/agent-orgs";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApprovalPanel (AGN-001)", () => {
  it("opens on the Pending tab with a loading state, then shows each card's Masters and actions", async () => {
    const mock = vi.fn().mockResolvedValue(page([org("p", "pending", "Kappa Overseas")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    expect(screen.getByText("Loading agent organisations…")).toBeInTheDocument();
    expect(await screen.findByText("ABC-M001 · Asha Rao")).toBeInTheDocument();
    expect(mock.mock.calls[0][0]).toBe(`${LIST}?status=pending&limit=20&offset=0`);
    expect(screen.getByRole("button", { name: "Pending" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: /^Approve / })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Reject / })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 4, name: "Pending" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 5, name: /Kappa Overseas/ })).toBeInTheDocument();
  });

  it.each([
    ["Approved", "active", "Suspend"],
    ["Suspended", "suspended", "Reinstate"],
    ["Rejected", "rejected", "Approve"],
  ])("the %s tab loads %s organisations with the right action", async (tab, status, action) => {
    const mock = vi.fn().mockResolvedValueOnce(page([])).mockResolvedValueOnce(page([org("x", status)]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    await screen.findByText("No organisations awaiting approval.");
    fireEvent.click(screen.getByRole("button", { name: tab }));
    expect(await screen.findByRole("button", { name: new RegExp(`^${action} `) })).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${LIST}?status=${status}&limit=20&offset=0`);
    expect(screen.getByRole("button", { name: tab })).toHaveAttribute("aria-pressed", "true");
  });

  it("pages through a long list with Previous/Next and a range label", async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => org(`a${i}`, "pending"));
    const mock = vi.fn().mockResolvedValueOnce(page(twenty, 45, 0)).mockResolvedValueOnce(page([org("b", "pending")], 45, 20));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    expect(await screen.findByText("Showing 1–20 of 45")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous page" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Showing 21–21 of 45")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${LIST}?status=pending&limit=20&offset=20`);
    expect(screen.getByRole("button", { name: "Previous page" })).toBeEnabled();
  });

  it("shows an error with a working Retry instead of an empty list", async () => {
    const mock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 500 })).mockResolvedValueOnce(page([org("p", "pending")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("button", { name: /^Approve / })).toBeInTheDocument();
  });

  it("shows the empty text when nothing awaits approval", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([])));
    render(<AgentApprovalPanel />);
    expect(await screen.findByText("No organisations awaiting approval.")).toBeInTheDocument();
    expect(screen.queryByText(/^Showing/)).toBeNull();
  });

  it("confirms before suspending, ignores repeat clicks, then follows the organisation to the Suspended tab", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn()
      .mockResolvedValueOnce(page([]))
      .mockResolvedValueOnce(page([org("a", "active")]))
      .mockReturnValueOnce(new Promise<Response>((r) => { release = r; }))
      .mockResolvedValue(page([org("a", "suspended")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    await screen.findByText("No organisations awaiting approval.");
    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Suspend / }));
    const confirm = screen.getByRole("button", { name: "Confirm suspend" });
    act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
    expect(mock).toHaveBeenCalledTimes(3);
    expect(mock.mock.calls[2][0]).toBe(`${LIST}/a/suspend`);
    release(ok({ id: "a", status: "suspended" }));
    expect(await screen.findByRole("button", { name: /^Reinstate / })).toBeInTheDocument();
    expect(mock.mock.calls[3][0]).toBe(`${LIST}?status=suspended&limit=20&offset=0`);
    expect(screen.getByRole("button", { name: "Suspended" })).toHaveAttribute("aria-pressed", "true");
  });

  it("moves focus into the suspend confirmation and back on Cancel (keyboard support)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(page([])).mockResolvedValue(page([org("a", "active")])));
    render(<AgentApprovalPanel />);
    await screen.findByText("No organisations awaiting approval.");
    fireEvent.click(screen.getByRole("button", { name: "Approved" }));
    fireEvent.click(await screen.findByRole("button", { name: /^Suspend / }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Confirm suspend" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /^Suspend / }));
  });

  it("announces a network failure on an action (final review #1)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(page([org("p", "pending", "Kappa Overseas")])).mockRejectedValueOnce(new TypeError("Failed to fetch")));
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve Kappa Overseas" }));
    expect(await screen.findByText("Network error. Check your connection and try again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve Kappa Overseas" })).toBeEnabled();
  });

  it("names the organisation in every action button for screen readers (final review #9)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([org("p", "pending", "Kappa Overseas"), org("q", "pending", "Lambda Travel")])));
    render(<AgentApprovalPanel />);
    expect(await screen.findByRole("button", { name: "Approve Kappa Overseas" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reject Lambda Travel" })).toBeInTheDocument();
  });

  it("announces what an action did (browser QA-09)", async () => {
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(page([org("p", "pending", "Kappa Overseas")]))
      .mockResolvedValueOnce(ok({ id: "p", status: "active" }))
      .mockResolvedValue(page([org("p", "active", "Kappa Overseas")])));
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve Kappa Overseas" }));
    const note = await screen.findByText("Kappa Overseas approved.");
    expect(note.closest("[role=status]")).not.toBeNull();
  });

  it("shows a server error on the card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(page([org("p", "pending")])).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Cannot approve an organisation that is active" }), { status: 409 })));
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /^Approve / }));
    expect(await screen.findByText("Cannot approve an organisation that is active")).toBeInTheDocument();
  });
});
