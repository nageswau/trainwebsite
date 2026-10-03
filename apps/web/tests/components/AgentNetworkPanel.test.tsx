import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentNetworkPanel from "@/components/AgentNetworkPanel";

const LIST = "/api/v1/overseas-admin/agent-orgs";
const master = { id: "m1", code: "ABC-M001", full_name: "Asha Rao", email: "asha@example.local", status: "active" };
const org = (id: string, over: Record<string, unknown> = {}) => ({
  id,
  name: `Agency ${id}`,
  prefix: "ABC",
  status: "active",
  created_at: "2026-09-28T00:00:00Z",
  masters: [master],
  staff_count: 3,
  counts: { students: 4, applications: 7, enrollments: 1 },
  ...over,
});
const page = (items: unknown[], total = items.length, offset = 0) => new Response(JSON.stringify({ items, total, limit: 20, offset }), { status: 200 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/overseas/admin/agent-network");
});

describe("AgentNetworkPanel (AGN-022)", () => {
  it("loads every agency first and shows each row's status, Masters and counts, linked to its detail (AC1, AC9)", async () => {
    const mock = vi.fn().mockResolvedValue(page([org("o1", { name: "Kappa Overseas" })]));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    expect(screen.getByText("Loading agencies…")).toBeInTheDocument();
    const link = await screen.findByRole("link", { name: /Kappa Overseas/ });
    expect(link).toHaveAttribute("href", "/overseas/admin/agent-network/o1");
    expect(mock.mock.calls[0][0]).toBe(`${LIST}?limit=20&offset=0`);
    const row = link.closest("tr") as HTMLElement;
    expect(within(row).getByText("Active")).toBeInTheDocument();
    expect(within(row).getByText("ABC-M001")).toBeInTheDocument();
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(expect.arrayContaining(["3", "4", "7", "1"]));
    expect(screen.getByRole("heading", { level: 2, name: "Agent network" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByText("Agent Approvals")).toBeNull();
  });

  it("filters by status and searches by agency, prefix, Master code or email", async () => {
    const mock = vi.fn().mockImplementation(async () => page([])); // a fresh Response per call: a body reads once
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    await screen.findByText("No agencies yet.");
    fireEvent.click(screen.getByRole("button", { name: "Suspended" }));
    expect(await screen.findByText("No suspended agencies.")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${LIST}?status=suspended&limit=20&offset=0`);
    fireEvent.change(screen.getByLabelText("Search agencies"), { target: { value: " kappa " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No agencies match “kappa”.")).toBeInTheDocument();
    expect(mock.mock.calls[2][0]).toBe(`${LIST}?status=suspended&limit=20&offset=0&q=kappa`);
  });

  it("keeps the current page on screen, dimmed, while the next loads, then focuses the results heading (AC9, AC10)", async () => {
    let release!: (r: Response) => void;
    const twenty = Array.from({ length: 20 }, (_, i) => org(`a${i}`));
    const mock = vi.fn().mockResolvedValueOnce(page(twenty, 45)).mockReturnValueOnce(new Promise<Response>((r) => (release = r)));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    expect(await screen.findByText("Showing 1–20 of 45")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(screen.getByRole("link", { name: /Agency a0/ })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "All agencies" })).toHaveAttribute("aria-busy", "true");
    expect(mock.mock.calls[1][0]).toBe(`${LIST}?limit=20&offset=20`);
    await act(async () => release(page([org("b1")], 45, 20)));
    expect(await screen.findByText("Showing 21–21 of 45")).toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "All agencies" }));
  });

  it("drops a slow older response that arrives after a newer one", async () => {
    let releaseFirst!: (r: Response) => void;
    const mock = vi
      .fn()
      .mockReturnValueOnce(new Promise<Response>((r) => (releaseFirst = r)))
      .mockResolvedValueOnce(page([org("new", { name: "Newer Agency", status: "suspended" })]));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Suspended" }));
    expect(await screen.findByRole("link", { name: /Newer Agency/ })).toBeInTheDocument();
    await act(async () => releaseFirst(page([org("old", { name: "Older Agency" })])));
    expect(screen.queryByText(/Older Agency/)).toBeNull();
  });

  it("shows the server's error with a working Retry", async () => {
    const mock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "Overseas Admin role required" }), { status: 403 }))
      .mockResolvedValueOnce(page([org("o1")]));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Overseas Admin role required");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: /Agency o1/ })).toBeInTheDocument();
  });

  it("renders agency names as text, never markup (AC11)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([org("x", { name: '<img src=x onerror="alert(1)">' })])));
    const { container } = render(<AgentNetworkPanel />);
    expect(await screen.findByText('<img src=x onerror="alert(1)">')).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("on a page past the end, says so and offers the first page instead of claiming there are no agencies (final review)", async () => {
    window.history.replaceState(null, "", "/overseas/admin/agent-network?page=5");
    const mock = vi.fn().mockResolvedValueOnce(page([], 3, 80)).mockResolvedValueOnce(page([org("o1")], 3, 0));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    expect(await screen.findByText("No agencies on this page.")).toBeInTheDocument();
    expect(screen.queryByText("No agencies yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Go to the first page" }));
    expect(await screen.findByRole("link", { name: /Agency o1/ })).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${LIST}?limit=20&offset=0`);
  });

  it("restores tab, page and search from the URL", async () => {
    window.history.replaceState(null, "", "/overseas/admin/agent-network?tab=pending&page=2&q=abc");
    const mock = vi.fn().mockResolvedValue(page([], 0, 20));
    vi.stubGlobal("fetch", mock);
    render(<AgentNetworkPanel />);
    await screen.findByText("No agencies match “abc”.");
    expect(mock).toHaveBeenCalledTimes(1);
    expect(mock.mock.calls[0][0]).toBe(`${LIST}?status=pending&limit=20&offset=20&q=abc`);
  });
});
