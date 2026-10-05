import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BdmActivityCounts from "@/components/BdmActivityCounts";
import BdmActivityDay from "@/components/BdmActivityDay";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ActivityDayPage } from "@/lib/bdmActivities";
import ManagerActivities from "@/app/bdm/manager/activities/page";
import MyActivities from "@/app/bdm/activities/page";
import { indiaToday } from "@/lib/bdmTravel";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const B1 = "00000000-0000-4000-8000-0000000000b1"; // the manager page only sends a UUID as ?bdm
const counts = { day: "2026-10-03", by_channel: { call: 3, whatsapp: 1, email: 0, visit: 1, meeting: 0, other: 0 }, calls_made: 2, organizations_contacted: 2 };
const day = (over: Partial<ActivityDayPage> = {}): ActivityDayPage => ({ items: [], total: 0, limit: 50, offset: 0, counts, ...over });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

// A block body: mockReset() returns the mock, and vitest would call a returned function as a cleanup hook.
beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("bdm-009 activity pages", () => {
  it("My Activities reads the chosen IST date and ignores a malformed one", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : p.includes("unread") ? { unread: 0 } : day()));
    const tree = elements(await MyActivities({ searchParams: Promise.resolve({ date: "2026-10-01" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/activities?date=2026-10-01&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmActivityDay)!.props.canLog).toBe(true);
    vi.mocked(serverApi).mockClear();
    await MyActivities({ searchParams: Promise.resolve({ date: "20261-10-01" }) });
    expect(vi.mocked(serverApi).mock.calls.some(([p]) => String(p).includes("20261"))).toBe(false);
  });

  it("the team page passes the BDM filter and never logs", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" };
      if (p.startsWith("/api/v1/bdm/manager/team")) return { items: [{ id: B1, full_name: "Asha" }], total: 1, limit: 100, offset: 0 };
      if (p.includes("unread")) return { unread: 0 };
      return day();
    });
    const tree = elements(await ManagerActivities({ searchParams: Promise.resolve({ date: "2026-10-01", bdm: B1 }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/activities?date=2026-10-01&bdm_user_id=${B1}&limit=50&offset=0`);
    const dayList = tree.find((el) => el.type === BdmActivityDay)!;
    expect(dayList.props.canLog).toBe(false);
    expect(dayList.props.emptyText).toBe("No activities from Asha on this day.");
  });

  const teamApi = () => vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" };
    if (p.startsWith("/api/v1/bdm/manager/team")) return { items: [{ id: B1, full_name: "Asha" }], total: 1, limit: 100, offset: 0 };
    if (p.includes("unread")) return { unread: 0 };
    return day();
  });
  // The notes live in the day list's `header` prop, which `elements` does not walk.
  const hasText = (tree: ReturnType<typeof elements>, note: string) => text(tree.find((el) => el.type === BdmActivityDay)!.props.header as ReactNode).includes(note);
  const NOT_VALID = "That isn't a valid date — showing today.";
  const FUTURE = "Dates after today can't be shown — showing today.";

  it.each([["2026-02-30", NOT_VALID], ["2099-12-31", FUTURE]])("My Activities with date=%s reads today and says so (QA9B-01)", async (date, note) => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : p.includes("unread") ? { unread: 0 } : day()));
    const tree = elements(await MyActivities({ searchParams: Promise.resolve({ date }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/activities?date=${indiaToday()}&limit=50&offset=0`);
    expect(vi.mocked(serverApi).mock.calls.some(([p]) => String(p).includes(date))).toBe(false);
    expect(hasText(tree, note)).toBe(true);
  });

  it.each([["2026-02-30", NOT_VALID], ["2099-12-31", FUTURE]])("the team page with date=%s reads today and says so (QA9B-01)", async (date, note) => {
    teamApi();
    const tree = elements(await ManagerActivities({ searchParams: Promise.resolve({ date }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/bdm/manager/activities?date=${indiaToday()}&limit=50&offset=0`);
    expect(hasText(tree, note)).toBe(true);
  });

  it("the team page drops a BDM who is not in the team and says so (QA9B-05)", async () => {
    teamApi();
    const tree = elements(await ManagerActivities({ searchParams: Promise.resolve({ bdm: "00000000-0000-4000-8000-0000000000ff" }) }));
    expect(vi.mocked(serverApi).mock.calls.some(([p]) => String(p).includes("bdm_user_id"))).toBe(false);
    expect(hasText(tree, "That BDM isn't in your team — showing everyone.")).toBe(true);
  });

  it("a refused page shows the access card", async () => {
    vi.mocked(serverApi).mockImplementation(async () => {
      throw new ApiError("BDM role required", 403);
    });
    const tree = elements(await MyActivities({ searchParams: Promise.resolve({}) }));
    expect(tree.some((el) => el.props && el.props.message === "BDM role required")).toBe(true);
  });

  it("the counts strip shows every channel, calls made and organizations contacted", () => {
    render(<BdmActivityCounts counts={counts} />);
    for (const [label, value] of [["Call", "3"], ["WhatsApp", "1"], ["Email", "0"], ["Calls made", "2"], ["Organizations contacted", "2"]]) {
      expect(screen.getByText(label).nextElementSibling).toHaveTextContent(value);
    }
  });

  it("the day list shows the empty state and opens Log activity with the organization picker", () => {
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day()} url="/api/v1/bdm/activities?date=2026-10-03" pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    expect(screen.getByText("No activities on this day.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    expect(screen.getByRole("form", { name: "Log activity" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: /Organization/ })).toBeInTheDocument();
  });

  it("the day list re-reads the day after a delete so the counts stay exact", async () => {
    const item = { id: "a1", organization: { id: "o1", code: "ORG-1", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
      contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
      note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true } } as const;
    const after = day({ counts: { ...counts, by_channel: { ...counts.by_channel, call: 2 }, calls_made: 1 } });
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.includes("/activities/a1") ? new Response(null, { status: 204 }) : res(after)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ items: [item], total: 1 })} url="/api/v1/bdm/activities?date=2026-10-03" pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/bdm/activities?date=2026-10-03&limit=50&offset=0"));
    await waitFor(() => expect(screen.getByText("Calls made").nextElementSibling).toHaveTextContent("1"));
    expect(screen.getByText("No activities on this day.")).toBeInTheDocument();
  });

  const mk = (id: string) => ({ id, organization: { id: "o1", code: "ORG-1", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
    contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: "2026-10-03T05:00:00Z",
    note: null, created_at: "2026-10-03T05:00:00Z", updated_at: "2026-10-03T05:00:00Z", permissions: { can_change: true } }) as const;
  const URL_DAY = "/api/v1/bdm/activities?date=2026-10-03";
  const withCalls = (n: number) => day({ counts: { ...counts, calls_made: n } });

  it("the Log activity form is absent before the click", () => {
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day()} url={URL_DAY} pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    expect(screen.queryByRole("form", { name: "Log activity" })).toBeNull();
  });

  it("the counts and the list are marked busy while a re-read is pending", async () => {
    let release: (r: Response) => void = () => {};
    const pending = new Promise<Response>((r) => { release = r; });
    vi.stubGlobal("fetch", vi.fn((url: string) => (url.includes("/activities/a1") ? Promise.resolve(new Response(null, { status: 204 })) : pending)));
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ items: [mk("a1"), mk("a2")], total: 2 })} url={URL_DAY} pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(screen.getByLabelText("Day counts")).toHaveAttribute("aria-busy", "true"));
    expect(screen.getByRole("list", { name: "Activities" })).toHaveAttribute("aria-busy", "true");
    release(res(day({ items: [mk("a2")], total: 1 })));
    await waitFor(() => expect(screen.getByLabelText("Day counts")).not.toHaveAttribute("aria-busy"));
  });

  it("Load more leaves focus where it is instead of jumping to the status region", async () => {
    const more = day({ items: [mk("a1"), mk("a2")], total: 2 });
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(more))));
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ items: [mk("a1")], total: 2 })} url={URL_DAY} pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    const button = screen.getByRole("button", { name: "Load more" });
    button.focus();
    fireEvent.click(button);
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(2));
    expect(document.activeElement?.id).not.toBe("activity-day-status");
  });

  it("an older response never overwrites a newer one", async () => {
    const resolvers: ((r: Response) => void)[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string) => (url.includes("/activities/a") ? Promise.resolve(new Response(null, { status: 204 })) : new Promise<Response>((r) => resolvers.push(r)))));
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ items: [mk("a1"), mk("a2")], total: 2 })} url={URL_DAY} pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(resolvers).toHaveLength(1));
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(resolvers).toHaveLength(2));
    resolvers[1](res(withCalls(7))); // the newer read answers first
    await waitFor(() => expect(screen.getByText("Calls made").nextElementSibling).toHaveTextContent("7"));
    resolvers[0](res(withCalls(9))); // the older one answers late
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText("Calls made").nextElementSibling).toHaveTextContent("7");
  });

  it("a refused delete (409) locks the item locally: no re-read and no success notice", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ items: [mk("a1")], total: 1 })} url={URL_DAY} pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText("Only today's activities can be changed")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Delete" })).toBeNull());
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  const logOnto = async (pageDay: string) => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(res({ ...mk("n1"), occurred_at: new Date().toISOString() }, 201));
      if (url.includes("assigned=me")) return Promise.resolve(res({ items: [{ id: "o1", code: "ORG-1", name: "St Mary", city: "Kochi" }], total: 1 }));
      if (url.includes("/organizations/o1")) return Promise.resolve(res({ organization: { id: "o1", contacts: [] } }));
      return Promise.resolve(res(day({ counts: { ...counts, day: pageDay } })));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day({ counts: { ...counts, day: pageDay } })} url={`/api/v1/bdm/activities?date=${pageDay}`} pageDay={pageDay} canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    const picker = screen.getByRole("combobox", { name: /Organization/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Mary" } });
    fireEvent.click(await screen.findByRole("option", { name: /St Mary/ }));
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
  };

  it("a write that succeeds but whose re-read fails still says it was saved (QA9B-02)", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return Promise.resolve(res({ ...mk("n1"), occurred_at: new Date().toISOString() }, 201));
      if (url.includes("assigned=me")) return Promise.resolve(res({ items: [{ id: "o1", code: "ORG-1", name: "St Mary", city: "Kochi" }], total: 1 }));
      if (url.includes("/organizations/o1")) return Promise.resolve(res({ organization: { id: "o1", contacts: [] } }));
      return Promise.resolve(res({ detail: "boom" }, 500));
    });
    vi.stubGlobal("fetch", fetchMock);
    const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date());
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day()} url={`/api/v1/bdm/activities?date=${today}`} pageDay={today} canLog orgBasePath="/bdm/organizations" />);
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    const picker = screen.getByRole("combobox", { name: /Organization/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Mary" } });
    fireEvent.click(await screen.findByRole("option", { name: /St Mary/ }));
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/^Activity logged\.$/));
    expect(screen.getByRole("alert")).toHaveTextContent("The list couldn't be refreshed. Reload the page to see the latest entries and counts.");
  });

  it("the Log activity title button stays on one line (QA9B-06)", () => {
    render(<BdmActivityDay header={<h2>My activities</h2>} initial={day()} url={URL_DAY} pageDay="2026-10-03" canLog orgBasePath="/bdm/organizations" />);
    expect(screen.getByRole("button", { name: "Log activity" })).toHaveClass("no-wrap");
  });

  it("logging onto another day announces which day it went to", async () => {
    await logOnto("2026-09-01");
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(`Activity logged for ${new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short", year: "numeric" }).format(new Date())}. Change the day to see it.`));
  });

  it("starting the next Log activity clears the previous notice (QA9-03)", async () => {
    await logOnto(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Activity logged."));
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("logging onto the page's own day keeps the plain notice", async () => {
    await logOnto(new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(new Date()));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/^Activity logged\.$/));
  });
});
