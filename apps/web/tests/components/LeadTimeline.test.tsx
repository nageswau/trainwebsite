import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LeadTimeline from "@/components/LeadTimeline";
import type { TimelineRow } from "@/lib/leadTimeline";

// tel-015 (DEC-SCOPE-114 D8): the shared timeline -- rows, empty / error states, "Show older" paging and the refresh on `version`.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (id: string, over: Partial<TimelineRow> = {}): TimelineRow => ({
  id, kind: "call", at: "2026-10-07T05:00:00Z", actor: { id: "t1", full_name: "Tara Caller" }, from_value: "outgoing", from_label: "outgoing",
  to_value: "busy", to_label: "busy", reason: null, event: null, subject: null, status: null, duration_seconds: 30, scheduled_for: null, ...over,
});
const page = (items: TimelineRow[], total: number, offset = 0) => ({ items, total, limit: 50, offset });
const URL = "/api/v1/telecaller/leads/L1/timeline";

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(res(page([], 0))));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadTimeline", () => {
  it("renders the server's first page without a request: title, actor, badge and excerpt", () => {
    render(<LeadTimeline url={URL} initial={page([row("a", { reason: "Wants fees" })], 1)} version={0} />);
    const list = screen.getByRole("list", { name: "Lead activity" });
    expect(within(list).getByText(/^Outgoing call: /)).toBeTruthy();
    expect(within(list).getByText(/Tara Caller/)).toBeTruthy();
    expect(within(list).getByText("Call")).toBeTruthy();
    expect(within(list).getByText("Wants fees")).toBeTruthy();
    expect(within(list).getByText("Duration 0:30")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Show older/ })).toBeNull();
  });

  it("shows System for an event with no actor", () => {
    render(<LeadTimeline url={URL} initial={page([row("a", { kind: "assignment", actor: null, from_value: "", to_value: "t1", to_label: "Tara", event: "round_robin" })], 1)} version={0} />);
    expect(screen.getByText("Assigned to Tara")).toBeTruthy();
    expect(screen.getByText(/^System/)).toBeTruthy();
  });

  it("loads on mount when no first page is given, then says when there is nothing", async () => {
    render(<LeadTimeline url={URL} version={0} />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading the activity…");
    expect(await screen.findByText("No activity yet.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith(`${URL}?limit=50&offset=0`, expect.anything());
  });

  it("offers a retry when the first page fails", async () => {
    fetchMock.mockResolvedValueOnce(res({ detail: "boom" }, 500));
    render(<LeadTimeline url={URL} version={0} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the activity.");
    fetchMock.mockResolvedValueOnce(res(page([row("a")], 1)));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/^Outgoing call: /)).toBeTruthy();
  });

  it("appends older entries until the total is reached, keeping rows when a page fails", async () => {
    render(<LeadTimeline url={URL} initial={page([row("a")], 3)} version={0} />);
    expect(screen.getByText("Showing 1 of 3 entries.")).toBeTruthy();
    fetchMock.mockResolvedValueOnce(res({}, 500));
    fireEvent.click(screen.getByRole("button", { name: "Show older entries" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load older entries.");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    fetchMock.mockResolvedValueOnce(res(page([row("b"), row("c", { kind: "follow_up", event: "done", from_value: "fee_details" })], 3, 1)));
    fireEvent.click(screen.getByRole("button", { name: "Show older entries" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(fetchMock).toHaveBeenLastCalledWith(`${URL}?limit=50&offset=1`, expect.anything());
    expect(screen.queryByRole("button", { name: "Show older entries" })).toBeNull();
    expect(screen.getByText("Follow-up done: Need fee details")).toBeTruthy();
  });

  it("reloads the first page when the version changes", async () => {
    const { rerender } = render(<LeadTimeline url={URL} initial={page([row("a")], 1)} version={0} />);
    fetchMock.mockResolvedValueOnce(res(page([row("n", { kind: "message", from_value: "whatsapp", to_value: "" }), row("a")], 2)));
    rerender(<LeadTimeline url={URL} initial={page([row("a")], 1)} version={1} />);
    expect(await screen.findByText("WhatsApp sent")).toBeTruthy();
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("names the list for its host and keeps keys distinct for a follow-up's entries", () => {
    const fu = (event: string) => row("f1", { kind: "follow_up", event, from_value: "fee_details" });
    render(<LeadTimeline url={URL} label="Activity for Asha" initial={page([fu("done"), fu("scheduled")], 2)} version={0} />);
    expect(within(screen.getByRole("list", { name: "Activity for Asha" })).getAllByRole("listitem")).toHaveLength(2);
  });
});
