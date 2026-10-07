import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import TodayFollowUps from "@/components/TodayFollowUps";
import { todayIst } from "@/lib/bdmAppointments";
import { followUp } from "@/tests/helpers/followUps";

// tel-011 (spec §4; AC1/AC2, §7 card): Today's follow-ups and the overdue list. The view and day live in the URL.
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/telecaller/follow-ups",
  useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[], over: Record<string, unknown> = {}) =>
  ({ items, total: items.length, limit: 50, offset: 0, day: todayIst(), counts: { day: 2, overdue: 1 }, ...over });

let listReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
const listCalls = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith("/api/v1/telecaller/follow-ups?"));
beforeEach(() => {
  search = "";
  push.mockReset();
  listReply = () => res(page([followUp({ overdue: true, due_at: "2026-10-06T04:30:00Z" }),
    followUp({ id: "F2", reason: "next_intake", next_action: null, lead: { ...followUp().lead, id: "L2", name: "Priya", priority: "cold", product: null } })]));
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return Promise.resolve(res(followUp({ status: "done", can_change: false })));
    return Promise.resolve(listReply());
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TodayFollowUps (tel-011)", () => {
  it("shows the §7 card: student, interest, action and time, priority, overdue", async () => {
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    const cards = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    expect(cards).toHaveLength(2);
    const first = cards[0];
    expect(within(first).getByRole("link", { name: "Rahul" }).getAttribute("href")).toBe("/telecaller/leads/L1");
    for (const text of ["Cyber Security", "Call at 4 PM", "10:00", "Hot", "Overdue", "Need fee details"]) expect(first.textContent).toContain(text);
    expect(cards[1].textContent).toContain("Interested next intake"); // no next action: the reason is the action
    expect(cards[1].textContent).toContain("Cold");
    expect(listCalls()[0]).toBe("/api/v1/telecaller/follow-ups?view=day&limit=50&offset=0");
    expect(screen.getByRole("button", { name: "Today (2)" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("button", { name: "Overdue (1)" })).toBeTruthy();
  });

  it("switches to the overdue view and another day through the URL", async () => {
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    fireEvent.click(await screen.findByRole("button", { name: "Overdue (1)" }));
    expect(push).toHaveBeenLastCalledWith("/telecaller/follow-ups?view=overdue", { scroll: false });
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2026-10-09" } });
    expect(push).toHaveBeenLastCalledWith("/telecaller/follow-ups?day=2026-10-09", { scroll: false });
    cleanup();
    search = "view=overdue";
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    await screen.findByRole("list", { name: "Follow-ups" });
    expect(listCalls().at(-1)).toBe("/api/v1/telecaller/follow-ups?view=overdue&limit=50&offset=0");
  });

  it("ignores a malformed day in the URL", async () => {
    search = "day=06-10-2026";
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    await screen.findByRole("list", { name: "Follow-ups" });
    expect(listCalls()[0]).toBe("/api/v1/telecaller/follow-ups?view=day&limit=50&offset=0");
  });

  it("marks a follow-up done from its card", async () => {
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    const [first] = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    fireEvent.click(within(first).getByRole("button", { name: "Done" }));
    expect(await screen.findByText("Marked done.")).toBeTruthy();
  });

  it("shows the telecaller for a manager, and no actions when it can't change", async () => {
    listReply = () => res(page([followUp({ can_change: false })]));
    render(<TodayFollowUps leadBasePath="/telecaller/manager/leads" showTelecaller />);
    const [card] = within(await screen.findByRole("list", { name: "Follow-ups" })).getAllByRole("listitem");
    expect(card.textContent).toContain("Tara Caller");
    expect(within(card).queryByRole("button")).toBeNull();
    expect(within(card).getByRole("link", { name: "Rahul" }).getAttribute("href")).toBe("/telecaller/manager/leads/L1");
  });

  it("has empty and failed states", async () => {
    listReply = () => res(page([], { counts: { day: 0, overdue: 0 } }));
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    expect(await screen.findByText("No follow-ups due on this day.")).toBeTruthy();
    cleanup();
    listReply = () => res({}, 500);
    render(<TodayFollowUps leadBasePath="/telecaller/leads" showTelecaller={false} />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load follow-ups");
  });
});
