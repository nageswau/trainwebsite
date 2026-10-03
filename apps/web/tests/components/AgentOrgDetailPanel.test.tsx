import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentOrgDetailPanel from "@/components/AgentOrgDetailPanel";

const ID = "3f2b8c1e-9d4a-4b7e-8f21-0c6d5e4a3b2f";
const DETAIL = `/api/v1/overseas-admin/agent-orgs/${ID}`;
const detail = (over: Record<string, unknown> = {}) => ({
  id: ID,
  name: "Kappa Overseas",
  prefix: "KAP",
  status: "active",
  created_at: "2026-09-28T00:00:00Z",
  status_changed_at: "2026-09-29T00:00:00Z",
  masters: [{ id: "m1", code: "KAP-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active" }],
  staff_count: 3,
  counts: { students: 4, applications: 7, enrollments: 0 },
  commission: { claimable: [{ currency: "INR", count: 1, amount: 1000 }, { currency: "USD", count: 1, amount: 200 }], claims: 1, revenue: [{ currency: "INR", count: 1, amount: 12000 }] },
  deposits: { currency: "INR", count: 2, collected: 50000, remitted: 30000, refunded: 5000 },
  as_of: "2026-10-03T00:00:00Z",
  ...over,
});
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentOrgDetailPanel (AGN-022)", () => {
  it("shows the agency's counts, money per currency and Masters, and fetches no student data until asked (AC1, AC2, AC9)", async () => {
    const mock = vi.fn().mockResolvedValue(json(detail()));
    vi.stubGlobal("fetch", mock);
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    expect(screen.getByText("Loading agency…")).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: /Kappa Overseas/ })).toBeInTheDocument();
    expect(mock).toHaveBeenCalledTimes(1);
    expect(mock.mock.calls[0][0]).toBe(DETAIL);
    const tiles = screen.getByRole("list", { name: "Agency figures" });
    expect(within(tiles).getByText("Enrollments").parentElement).toHaveTextContent("0");
    expect(within(tiles).getByText("Staff").parentElement).toHaveTextContent("3");
    const commission = screen.getByRole("table", { name: "Commission" });
    expect(within(commission).getAllByRole("row").map((r) => r.textContent)).toEqual(expect.arrayContaining([expect.stringMatching(/Claimable.*INR/), expect.stringMatching(/Claimable.*USD/)]));
    expect(screen.getByRole("table", { name: "Deposits" })).toHaveTextContent("50,000");
    expect(screen.getByText(/KAP-M001/)).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("confirms before suspending, sends one request on a double click, announces it and focuses Reinstate (AC4, AC9, AC10)", async () => {
    let release!: (r: Response) => void;
    const mock = vi
      .fn()
      .mockResolvedValueOnce(json(detail()))
      .mockReturnValueOnce(new Promise<Response>((r) => (release = r)))
      .mockResolvedValueOnce(json(detail({ status: "suspended" })));
    vi.stubGlobal("fetch", mock);
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Suspend Kappa Overseas" }));
    const confirm = screen.getByRole("button", { name: "Confirm suspend" });
    fireEvent.click(confirm);
    fireEvent.click(confirm);
    await act(async () => release(json({ id: ID, status: "suspended" })));
    expect(await screen.findByText("Kappa Overseas suspended.")).toBeInTheDocument();
    const posts = mock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(posts[0][0]).toBe(`${DETAIL}/suspend`);
    const reinstate = await screen.findByRole("button", { name: "Reinstate Kappa Overseas" });
    expect(document.activeElement).toBe(reinstate);
  });

  it("shows a 409 and refetches the summary; a dropped network says so", async () => {
    const mock = vi
      .fn()
      .mockResolvedValueOnce(json(detail()))
      .mockResolvedValueOnce(json({ detail: "Cannot suspend an organisation that is suspended" }, 409))
      .mockResolvedValueOnce(json(detail({ status: "suspended" })))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", mock);
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Suspend Kappa Overseas" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm suspend" }));
    expect(await screen.findByText("Cannot suspend an organisation that is suspended")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Reinstate Kappa Overseas" }));
    expect(await screen.findByText("Network error. Check your connection and try again.")).toBeInTheDocument();
  });

  it("gives Super Admin no actions and a pending agency a link to Agent Approvals (N3)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(detail())));
    render(<AgentOrgDetailPanel orgId={ID} canAct={false} />);
    await screen.findByRole("heading", { level: 2, name: /Kappa Overseas/ });
    expect(screen.queryByRole("button", { name: /Suspend|Reinstate/ })).toBeNull();
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(detail({ status: "pending" }))));
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    expect(await screen.findByRole("link", { name: "Review in Agent Approvals" })).toHaveAttribute("href", "/overseas/admin/agents");
    expect(screen.queryByRole("button", { name: /Suspend/ })).toBeNull();
  });

  it("says when the agency does not exist, and offers Retry on other failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Organisation not found" }, 404)));
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    expect(await screen.findByText("Organisation not found")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Agent network/ })[0]).toHaveAttribute("href", "/overseas/admin/agent-network");
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    cleanup();
    const mock = vi.fn().mockResolvedValueOnce(new Response("oops", { status: 500 })).mockResolvedValueOnce(json(detail()));
    vi.stubGlobal("fetch", mock);
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load this agency.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { level: 2, name: /Kappa Overseas/ })).toBeInTheDocument();
  });

  it("opens the students list only when chosen (AC9)", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json(detail())).mockResolvedValueOnce(json({ items: [], total: 0, limit: 20, offset: 0 }));
    vi.stubGlobal("fetch", mock);
    render(<AgentOrgDetailPanel orgId={ID} canAct />);
    const students = await screen.findByRole("button", { name: "Students" });
    expect(students).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(students);
    expect(await screen.findByText("No students yet.")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${DETAIL}/students?status=active&limit=20&offset=0`);
    expect(students).toHaveAttribute("aria-pressed", "true");
  });
});
