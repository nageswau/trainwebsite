import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UniversityActivity from "@/components/UniversityActivity";
import type { ActivityRow } from "@/lib/universityActivity";

// upc-013 (DEC-SCOPE-163 D5): the communication history renders through the shared LeadTimeline list with the university mappers.
const row = (id: string, over: Partial<ActivityRow> = {}): ActivityRow => ({
  id, kind: "stage", at: "2026-09-14T05:00:00Z", actor: { id: "p1", full_name: "Asha Menon" }, event: "move", from_value: "meeting_completed",
  from_label: "Meeting Completed", to_value: "proposal_sent", to_label: "Proposal Sent", subject: null, status: null, reason: null,
  duration_seconds: null, scheduled_for: null, ...over,
});
const page = (items: ActivityRow[], total = items.length) => ({ items, total, limit: 50, offset: 0 });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn(() => Promise.resolve(new Response(JSON.stringify(page([])), { status: 200 })));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("UniversityActivity", () => {
  it("lists the server's first page with the university titles, actor and System", () => {
    render(<UniversityActivity universityId="U1" initial={page([
      row("s1"),
      row("c1", { kind: "call", event: "outgoing", from_value: "connected", from_label: "Connected", to_value: "", to_label: "Priya", actor: null }),
    ])} />);
    const list = screen.getByRole("list", { name: "Communication history" });
    expect(within(list).getByText(/^Stage: Meeting Completed → Proposal Sent/)).toBeTruthy();
    expect(within(list).getByText(/^Outgoing call: Connected/)).toBeTruthy();
    expect(within(list).getByText(/Asha Menon/)).toBeTruthy();
    expect(within(list).getByText(/System/)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("says when nothing is recorded yet, and offers Retry when the first read failed", () => {
    const { unmount } = render(<UniversityActivity universityId="U1" initial={page([])} />);
    expect(screen.getByText("No activity yet.")).toBeTruthy();
    unmount();
    render(<UniversityActivity universityId="U1" initial={null} />);
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("shows a refreshed first page (the page re-renders after a write)", () => {
    const { rerender } = render(<UniversityActivity universityId="U1" initial={page([row("s1")])} />);
    rerender(<UniversityActivity universityId="U1" initial={page([row("m1", { kind: "message", event: "whatsapp", to_label: "Priya" }), row("s1")])} />);
    expect(screen.getByText(/^WhatsApp sent/)).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
