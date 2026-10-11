import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterTimeline from "@/components/RecruiterTimeline";
import type { RecTimelineRow } from "@/lib/recruiterTimeline";

// rec-027 (TL10): the company / candidate Timeline section -- loads its first page, the empty and failure states, and the re-read on `version`.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = (id: string, over: Partial<RecTimelineRow> = {}): RecTimelineRow => ({
  id, kind: "call", at: "2026-10-07T05:00:00Z", actor: { id: "r1", full_name: "Rita Recruiter" }, event: "outgoing", from_value: "connected",
  from_label: "Connected", to_value: "", to_label: "Priya", subject: null, status: null, reason: "Discussed the JD", context: null, duration_seconds: null,
  scheduled_for: null, ...over,
});
const page = (items: RecTimelineRow[], total = items.length) => ({ items, total, limit: 50, offset: 0 });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(res(page([]))));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterTimeline", () => {
  it("loads the company timeline newest first under a Timeline heading", async () => {
    fetchMock.mockResolvedValueOnce(res(page([row("m", { kind: "message", event: "whatsapp", reason: "Profiles Friday" }), row("c")])));
    render(<RecruiterTimeline party={{ kind: "company", id: "C1" }} />);
    expect(screen.getByRole("heading", { name: "Timeline" })).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Company timeline" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText(/^WhatsApp sent/)).toBeTruthy();
    expect(within(items[1]).getByText(/^Outgoing call: Connected/)).toBeTruthy();
    expect(within(items[1]).getByText(/Rita Recruiter/)).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/companies/C1/timeline?limit=50&offset=0");
  });

  it("reads the candidate timeline and says when there is nothing yet", async () => {
    render(<RecruiterTimeline party={{ kind: "candidate", id: "K1" }} />);
    expect(await screen.findByText("No activity yet.")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/candidates/K1/timeline?limit=50&offset=0");
  });

  it("offers Retry after a failed read", async () => {
    fetchMock.mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([row("c")])));
    render(<RecruiterTimeline party={{ kind: "company", id: "C1" }} />);
    expect(await screen.findByText(/Unable to load the activity/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Company timeline" })).toBeTruthy();
  });

  it("re-reads the first page when the version changes", async () => {
    const { rerender } = render(<RecruiterTimeline party={{ kind: "company", id: "C1" }} version={0} />);
    await screen.findByText("No activity yet.");
    fetchMock.mockResolvedValueOnce(res(page([row("c")])));
    rerender(<RecruiterTimeline party={{ kind: "company", id: "C1" }} version={1} />);
    await waitFor(() => expect(screen.getByText(/^Outgoing call: Connected/)).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
