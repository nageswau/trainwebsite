import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AgentReportsPanel from "@/components/AgentReportsPanel";
import type { AgentReport } from "@/lib/types";

// AGN-020 (DEC-SCOPE-063; spec §6.2, §6.4): tabs per role, the address as state, and every loading / empty / error state.

vi.mock("@/components/AgentCommissionReportPanel", () => ({ default: () => <h3>Commission report</h3> }));

const REPORTS = "/api/v1/workflows/overseas/agent/crm/reports";
const report = (over: Partial<AgentReport> = {}): AgentReport => ({
  kind: "students", title: "Students", scope: "agency", columns: [{ key: "name", label: "Name", numeric: false }],
  items: [{ name: "Zoë" }], totals: null, total: 1, limit: 50, offset: 0, options: {}, as_of: "2026-10-03T08:05:00Z", ...over,
});
const reply = (status: number, body: unknown) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

let fetchMock: ReturnType<typeof vi.fn>;
const urls = () => fetchMock.mock.calls.map(([url]) => String(url));

beforeEach(() => {
  window.history.replaceState(null, "", "/overseas/agent/reports");
  fetchMock = vi.fn(() => reply(200, report()));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentReportsPanel tabs", () => {
  it("gives a Master eight tabs and loads the first report", async () => {
    render(<AgentReportsPanel memberRole="master" />);
    expect(within(screen.getByRole("tablist", { name: "Reports" })).getAllByRole("tab")).toHaveLength(8);
    expect(await screen.findByRole("rowheader", { name: "Zoë" })).toBeInTheDocument();
    expect(urls()).toEqual([`${REPORTS}/students?limit=50&offset=0`]);
    expect(screen.getByRole("tab", { name: "Students" })).toHaveAttribute("aria-selected", "true");
  });

  it("gives staff six tabs, without Staff performance or Commission", async () => {
    render(<AgentReportsPanel memberRole="staff" />);
    const names = within(screen.getByRole("tablist")).getAllByRole("tab").map((t) => t.textContent);
    expect(names).toEqual(["Students", "Applications", "Universities", "Countries", "Intakes", "Enrollments"]);
    await screen.findByRole("rowheader", { name: "Zoë" });
  });

  it("moves and activates with the arrow keys, and records the report in the address", async () => {
    render(<AgentReportsPanel memberRole="master" />);
    await screen.findByRole("rowheader", { name: "Zoë" });
    fireEvent.keyDown(screen.getByRole("tab", { name: "Students" }), { key: "ArrowRight" });
    const applications = screen.getByRole("tab", { name: "Applications" });
    expect(applications).toHaveFocus();
    expect(applications).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(urls()).toContain(`${REPORTS}/applications?limit=50&offset=0`));
    await waitFor(() => expect(window.location.search).toBe("?report=applications"));
    fireEvent.keyDown(applications, { key: "End" });
    expect(screen.getByRole("tab", { name: "Commission" })).toHaveFocus();
  });

  it("opens the report in the address, with its filters", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?report=countries&from=2026-01-01&member=ABC-S001");
    render(<AgentReportsPanel memberRole="master" />);
    await waitFor(() => expect(urls()).toEqual([`${REPORTS}/countries?date_from=2026-01-01&member=ABC-S001&limit=50&offset=0`]));
  });

  it("shows the unchanged commission report on the Commission tab, without a reports request", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?report=commission&from=2026-01-01");
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByRole("heading", { name: "Commission report" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("AgentReportsPanel states", () => {
  it("shows a busy skeleton on first load", () => {
    fetchMock.mockImplementation(() => new Promise(() => {}));
    render(<AgentReportsPanel memberRole="master" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading report…");
  });

  it("keeps only the newest response when tabs change quickly", async () => {
    let releaseFirst: (r: Response) => void = () => {};
    fetchMock.mockImplementationOnce(() => new Promise<Response>((resolve) => { releaseFirst = resolve; }));
    fetchMock.mockImplementationOnce(() => reply(200, report({ kind: "applications", items: [{ name: "Newest" }] })));
    render(<AgentReportsPanel memberRole="master" />);
    fireEvent.click(screen.getByRole("tab", { name: "Applications" }));
    expect(await screen.findByRole("rowheader", { name: "Newest" })).toBeInTheDocument();
    await act(async () => releaseFirst(new Response(JSON.stringify(report({ items: [{ name: "Stale" }] })), { status: 200 })));
    expect(screen.queryByRole("rowheader", { name: "Stale" })).toBeNull();
  });

  it("says there is nothing yet when no filter is set, and hides the CSV", async () => {
    fetchMock.mockImplementation(() => reply(200, report({ items: [], total: 0 })));
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByText("No students yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download CSV" })).toBeNull();
  });

  it("offers to clear filters when they match nothing", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?report=students&from=2000-01-01");
    fetchMock.mockImplementation(() => reply(200, report({ items: [], total: 0 })));
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByText("No records match these filters.")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    await waitFor(() => expect(urls().at(-1)).toBe(`${REPORTS}/students?limit=50&offset=0`));
  });

  it("offers the CSV of the applied filters when there are rows", async () => {
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    expect(screen.getByText(/1 row · As of/)).toBeInTheDocument();
  });

  it("sends an expired session to sign in", async () => {
    fetchMock.mockImplementation(() => reply(401, { detail: "Not authenticated" }));
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your session has expired.");
    expect(screen.getByRole("link", { name: "Sign in again" }).getAttribute("href")).toContain("/overseas/login?next=");
  });

  it("shows the server's refusal", async () => {
    fetchMock.mockImplementation(() => reply(403, { detail: "Your agency Master hasn't given you access to reports" }));
    render(<AgentReportsPanel memberRole="staff" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your agency Master hasn't given you access to reports");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("puts a 422 at its field", async () => {
    window.history.replaceState(null, "", "/overseas/agent/reports?report=countries&member=ABC-S999");
    fetchMock.mockImplementation(() => reply(422, { detail: [{ loc: ["query", "member"], msg: "Unknown staff member", type: "value_error" }] }));
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown staff member");
    expect(screen.getByLabelText("Staff member")).toHaveAttribute("aria-invalid", "true");
  });

  it("lets a failed load be tried again", async () => {
    fetchMock.mockImplementationOnce(() => reply(500, { detail: "boom" }));
    render(<AgentReportsPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load this report.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("rowheader", { name: "Zoë" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("moves focus to the table after a page change", async () => {
    fetchMock.mockImplementation((url: string) => reply(200, report({ total: 120, items: Array.from({ length: 50 }, (_, i) => ({ name: `S${i}` })), offset: url.includes("offset=50") ? 50 : 0 })));
    render(<AgentReportsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Next" }));
    await waitFor(() => expect(urls().at(-1)).toBe(`${REPORTS}/students?limit=50&offset=50`));
    await waitFor(() => expect(screen.getByRole("region", { name: "Students" })).toHaveFocus());
  });
});
