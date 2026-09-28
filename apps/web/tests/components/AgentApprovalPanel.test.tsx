import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApprovalPanel from "@/components/AgentApprovalPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const master = { id: "m1", code: "ABC-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active" };
const org = (id: string, status: string, name = `Agency ${id}`) => ({ id, name, prefix: "ABC", status, created_at: "2026-09-28T00:00:00Z", masters: [master] });
const ok = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApprovalPanel (AGN-001)", () => {
  it("shows a loading state, then groups organisations by status with the right actions", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([org("p", "pending"), org("a", "active"), org("s", "suspended"), org("r", "rejected")])));
    render(<AgentApprovalPanel />);
    expect(screen.getByText("Loading agent organisations…")).toBeInTheDocument();
    const pending = await screen.findByRole("region", { name: "Pending" });
    expect(within(pending).getByRole("button", { name: "Approve" })).toBeInTheDocument();
    expect(within(pending).getByRole("button", { name: "Reject" })).toBeInTheDocument();
    expect(within(pending).getByText("ABC-M001 · Asha Rao")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Approved" })).getByRole("button", { name: "Suspend" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Suspended" })).getByRole("button", { name: "Reinstate" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Rejected" })).getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("shows an error with a working Retry instead of an empty list", async () => {
    const mock = vi.fn().mockResolvedValueOnce(new Response("{}", { status: 500 })).mockResolvedValueOnce(ok([org("p", "pending")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: "Pending" })).toBeInTheDocument();
  });

  it("shows the empty text when nothing awaits approval", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([])));
    render(<AgentApprovalPanel />);
    expect(await screen.findByText("No organisations awaiting approval.")).toBeInTheDocument();
  });

  it("asks for confirmation before suspending and ignores repeat clicks", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn().mockResolvedValueOnce(ok([org("a", "active")])).mockReturnValueOnce(new Promise<Response>((r) => { release = r; })).mockResolvedValue(ok([org("a", "suspended")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    const confirm = screen.getByRole("button", { name: "Confirm suspend" });
    act(() => { fireEvent.click(confirm); fireEvent.click(confirm); });
    expect(mock).toHaveBeenCalledTimes(2);
    expect(mock.mock.calls[1][0]).toBe("/api/v1/overseas-admin/agent-orgs/a/suspend");
    release(ok({ id: "a", status: "suspended" }));
    expect(await screen.findByRole("button", { name: "Reinstate" })).toBeInTheDocument();
  });

  it("moves focus into the suspend confirmation and back on Cancel (keyboard support)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([org("a", "active")])));
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Suspend" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Confirm suspend" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Suspend" }));
  });

  it("titles each organisation card one level below its group heading", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(ok([org("p", "pending", "Kappa Overseas")])));
    render(<AgentApprovalPanel />);
    expect(await screen.findByRole("heading", { level: 4, name: "Pending" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 5, name: /Kappa Overseas/ })).toBeInTheDocument();
  });

  it("shows a server error on the card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(ok([org("p", "pending")])).mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Cannot approve an organisation that is active" }), { status: 409 })));
    render(<AgentApprovalPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText("Cannot approve an organisation that is active")).toBeInTheDocument();
  });
});
