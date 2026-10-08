import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterFollowUpsPanel from "@/components/RecruiterFollowUpsPanel";
import { recFollowUp } from "@/tests/helpers/recruiterFollowUps";

// rec-024 (spec §4; AC1, FU2): the daily list -- Today / Overdue / Upcoming tabs with counts, the card, Done with an outcome.
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/recruiter/follow-ups",
  useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[], over: Record<string, unknown> = {}) =>
  ({ items, total: items.length, limit: 50, offset: 0, day: "2026-10-08", counts: { today: 2, overdue: 1, upcoming: 4 }, ...over });

let listReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
const listCalls = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith("/api/v1/recruiter/follow-ups?"));
beforeEach(() => {
  search = "";
  push.mockReset();
  listReply = () => res(page([recFollowUp({ overdue: true }), recFollowUp({ id: "F2", reason: "offer_status", contact: null, can_change: false })]));
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res(recFollowUp({ status: "done", can_change: false })));
    return Promise.resolve(listReply());
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterFollowUpsPanel (rec-024)", () => {
  it("shows Today with the three counts and a card per follow-up linking to its company", async () => {
    render(<RecruiterFollowUpsPanel />);
    const cards = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    expect(within(cards[0]).getByRole("link", { name: "Acme Technologies" }).getAttribute("href")).toBe("/recruiter/companies/C1");
    for (const text of ["CMP-000042", "Follow-up for JD", "Priya HR", "Overdue", "Riya Recruiter", "Ask for the Java JD"]) expect(cards[0].textContent).toContain(text);
    expect(cards[1].textContent).toContain("Offer status");
    expect(within(cards[1]).queryByRole("button", { name: "Done" })).toBeNull(); // can_change false: read only
    expect(listCalls()[0]).toBe("/api/v1/recruiter/follow-ups?due=today&limit=50&offset=0");
    expect(screen.getByRole("button", { name: "Today (2)" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("button", { name: "Overdue (1)" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Upcoming (4)" })).toBeTruthy();
  });

  it("switches tab through the URL", async () => {
    render(<RecruiterFollowUpsPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Upcoming (4)" }));
    expect(push).toHaveBeenCalledWith("/recruiter/follow-ups?due=upcoming", { scroll: false });
    cleanup();
    search = "due=overdue";
    render(<RecruiterFollowUpsPanel />);
    await screen.findByRole("list", { name: "Follow-ups" });
    expect(listCalls().at(-1)).toBe("/api/v1/recruiter/follow-ups?due=overdue&limit=50&offset=0");
  });

  it("says when a list is empty and offers a retry when it fails", async () => {
    listReply = () => res(page([], { counts: { today: 0, overdue: 0, upcoming: 0 } }));
    render(<RecruiterFollowUpsPanel />);
    expect(await screen.findByText("Nothing due today and nothing overdue.")).toBeTruthy();
    cleanup();
    listReply = () => res({ detail: "boom" }, 500);
    render(<RecruiterFollowUpsPanel />);
    expect(await screen.findByText("Unable to load follow-ups.")).toBeTruthy();
    listReply = () => res(page([recFollowUp()]));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Follow-ups" })).toBeTruthy();
  });

  it("marks one done with an optional outcome and reloads the list", async () => {
    render(<RecruiterFollowUpsPanel />);
    const [first] = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    fireEvent.click(within(first).getByRole("button", { name: "Done" }));
    fireEvent.change(within(first).getByLabelText("Outcome (optional)"), { target: { value: "JD received" } });
    fireEvent.click(within(first).getByRole("button", { name: "Mark done" }));
    await screen.findByText("Marked done.");
    const post = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")!;
    expect(post[0]).toBe("/api/v1/recruiter/follow-ups/F1/complete");
    expect(JSON.parse(String((post[1] as RequestInit).body))).toEqual({ outcome: "JD received" });
    await waitFor(() => expect(listCalls().length).toBe(2));
  });
});
