import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterMeetingsPanel from "@/components/RecruiterMeetingsPanel";
import { recMeeting } from "@/tests/helpers/recruiterMeetings";

// rec-028 (spec §4; MT10): the meetings list -- Upcoming / Awaiting outcome / Completed / Cancelled tabs with counts, the card, cancel.
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/recruiter/meetings",
  useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const COUNTS = { upcoming: 2, awaiting_outcome: 1, completed: 5, cancelled: 0 };
const page = (items: unknown[], over: Record<string, unknown> = {}) => ({ items, total: items.length, limit: 50, offset: 0, counts: COUNTS, ...over });

let listReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
const listCalls = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith("/api/v1/recruiter/meetings?"));
beforeEach(() => {
  search = "";
  push.mockReset();
  listReply = () => res(page([recMeeting(), recMeeting({ id: "M2", meeting_type: "hr_meeting", contact: null, can_change: false })]));
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res(recMeeting({ status: "cancelled", can_change: false, cancelled_at: "2026-10-08T07:00:00Z", cancel_reason: "Postponed" })));
    return Promise.resolve(listReply());
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterMeetingsPanel (rec-028)", () => {
  it("shows Upcoming with the four counts and a card per meeting linking to its company", async () => {
    render(<RecruiterMeetingsPanel />);
    const cards = within(await screen.findByRole("list", { name: "Meetings" })).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByRole("link", { name: "Acme Technologies" }).getAttribute("href")).toBe("/recruiter/companies/C1");
    for (const text of ["CMP-000042", "Contract discussion", "Priya HR", "Online", "Riya Recruiter", "Fee per hire"]) expect(cards[0].textContent).toContain(text);
    expect(cards[1].textContent).toContain("HR meeting");
    expect(within(cards[1]).queryByRole("button", { name: "Cancel meeting" })).toBeNull(); // can_change false: read only
    expect(listCalls()[0]).toBe("/api/v1/recruiter/meetings?view=upcoming&limit=50&offset=0");
    expect(screen.getByRole("button", { name: "Upcoming (2)" }).getAttribute("aria-current")).toBe("page");
    for (const name of ["Awaiting outcome (1)", "Completed (5)", "Cancelled (0)"]) expect(screen.getByRole("button", { name })).toBeTruthy();
  });

  it("switches tab through the URL", async () => {
    render(<RecruiterMeetingsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Awaiting outcome (1)" }));
    expect(push).toHaveBeenCalledWith("/recruiter/meetings?view=awaiting_outcome", { scroll: false });
    cleanup();
    search = "view=completed";
    render(<RecruiterMeetingsPanel />);
    await screen.findByRole("list", { name: "Meetings" });
    expect(listCalls().at(-1)).toBe("/api/v1/recruiter/meetings?view=completed&limit=50&offset=0");
  });

  it("says when a list is empty and offers a retry when it fails", async () => {
    listReply = () => res(page([]));
    render(<RecruiterMeetingsPanel />);
    expect(await screen.findByText("No upcoming meetings.")).toBeTruthy();
    cleanup();
    listReply = () => res({ detail: "boom" }, 500);
    render(<RecruiterMeetingsPanel />);
    expect(await screen.findByText("Unable to load meetings.")).toBeTruthy();
    listReply = () => res(page([recMeeting()]));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Meetings" })).toBeTruthy();
  });

  it("cancels one with a reason and reloads the list", async () => {
    render(<RecruiterMeetingsPanel />);
    const [first] = within(await screen.findByRole("list", { name: "Meetings" })).getAllByRole("listitem");
    fireEvent.click(within(first).getByRole("button", { name: "Cancel meeting" }));
    fireEvent.change(within(first).getByRole("textbox"), { target: { value: "Postponed" } });
    fireEvent.click(within(first).getByRole("button", { name: "Cancel it" }));
    await screen.findByText("Meeting cancelled.");
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")!;
    expect(post[0]).toBe("/api/v1/recruiter/meetings/M1/cancel");
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ reason: "Postponed" });
    await waitFor(() => expect(listCalls().length).toBe(2));
  });
});
