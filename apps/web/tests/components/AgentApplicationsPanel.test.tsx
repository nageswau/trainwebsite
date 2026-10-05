import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationsPanel from "@/components/AgentApplicationsPanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", course: null, intake: "Fall 2027",
  status: "offer", application_reference: "UCAS-1", submitted_on: null, application_deadline: null, offer_deadline: null,
  nearest_deadline: null, next_action: "Send deposit", updated_at: "", ...over,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApplicationsPanel (AGN-008)", () => {
  it("shows loading, then cards with text status and a no-login tag", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(page([item()])))));
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    expect(screen.getByText("Loading applications…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Applications" });
    const card = within(list).getByRole("listitem");
    expect(card).toHaveTextContent("Asha Rao");
    expect(card).toHaveTextContent("Offer");
    expect(card).toHaveTextContent("no login");
  });

  it("requests the filter it is given", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json(page([]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationsPanel group="visa" reloadKey={0} />);
    await screen.findByText("No applications match this filter.");
    expect(String((fetchMock.mock.calls as unknown[][])[0][0])).toContain("status=visa");
    expect(screen.getByRole("link", { name: "Show all applications" })).toHaveAttribute("href", "/overseas/agent/applications");
  });

  it("shows the unfiltered empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json(page([])))));
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    expect(await screen.findByText(/No applications yet/)).toBeInTheDocument();
  });

  it("shows an error with Retry that refetches", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({ detail: "boom" }, 500)).mockResolvedValue(json(page([item()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("pages with Previous and Next", async () => {
    const many = Array.from({ length: 20 }, (_, i) => item({ id: `a${i}`, student: `S${i}` }));
    const fetchMock = vi.fn((url: string) => Promise.resolve(json(url.includes("offset=20") ? page([item({ id: "z", student: "Last" })], 21, 20) : page(many, 21))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Last")).toBeInTheDocument();
    expect(screen.getByText("Showing 21–21 of 21")).toBeInTheDocument();
  });

  it("opens the detail under its card and returns focus on Close", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(json(url.includes("/a1") ? { application: { ...item(), university_id: "u1", university_slug: "u1", course_id: null, created_at: "", read_only_reason: null, history: [] } } : page([item()])))));
    render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    const view = await screen.findByRole("button", { name: "View Asha Rao — Uni One" });
    fireEvent.click(view);
    expect(view).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(await screen.findByRole("button", { name: "Close" }));
    expect(view).toHaveFocus();
  });

  it("refetches when reloadKey changes (after a create)", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(json(page([]))));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<AgentApplicationsPanel group="all" reloadKey={0} />);
    await screen.findByText(/No applications yet/);
    await act(async () => rerender(<AgentApplicationsPanel group="all" reloadKey={1} />));
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
