import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmCalendar from "@/components/BdmCalendar";
import BdmCalendarPicker from "@/components/BdmCalendarPicker";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { CalendarData } from "@/lib/bdmCalendar";
import BdmCalendarPage from "@/app/bdm/calendar/page";
import ManagerCalendarPage from "@/app/bdm/manager/calendar/page";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-013 (DEC-SCOPE-078): the calendar view and its two pages. The view is a plain function of its props, so it is called directly.
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const org = { id: "o1", code: "ORG-1", name: "Govt College", archived: false };
const data = (over: Partial<CalendarData> = {}): CalendarData => ({
  bdm: { id: "b1", full_name: "Asha", active: true }, date_from: "2031-03-03", date_to: "2031-03-09", today: "2031-03-04", truncated: false,
  appointments: [
    { id: "a1", code: "APT-1", day: "2031-03-04", starts_at: "2031-03-04T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled", seminar: false, organization: org },
    { id: "a2", code: "APT-2", day: "2031-03-05", starts_at: "2031-03-05T04:30:00Z", duration_minutes: 90, appointment_type: "seminar_workshop", status: "completed", seminar: true, organization: org },
  ],
  trips: [{ id: "t1", code: "TRV-1", travel_date: "2031-03-04", return_date: "2031-03-06", from_place: "Hyderabad", to_place: "Vijayawada", mode: "train", approval_status: "submitted", travel_status: "planned" }],
  tasks: [{ id: "k1", kind: "follow_up", title: "Send MoU draft", due_on: "2031-03-07", status: "open", overdue: false, organization: null }],
  ...over,
});
const props = (over = {}) => ({ data: data(), view: "week" as const, date: "2031-03-05", basePath: "/bdm/calendar", managerOf: null, ...over });
const hrefs = (tree: ReturnType<typeof elements>) => tree.map((el) => el.props.href).filter((h): h is string => typeof h === "string");
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");
const me = { id: "b1", full_name: "Asha", bdm_profile: { bdm_type: "college" } };

function answer(byPath: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/workflows/notifications/unread-count") return { unread: 0 } as never;
    const key = Object.keys(byPath).find((k) => path.startsWith(k));
    const value = key === undefined ? undefined : byPath[key];
    if (value instanceof Error) throw value;
    return value as never;
  });
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("BdmCalendar view", () => {
  it("lists the seven days with the §5 headline and each item on its day (AC1, AC2)", () => {
    const tree = elements(BdmCalendar(props()));
    const days = tree.filter((el) => el.type === "section");
    expect(days).toHaveLength(7);
    expect(days.map((d) => text(elements(d.props.children).find((el) => el.type === "h4")))).toEqual([
      "Monday 3 Mar — Nothing planned",
      "Tuesday 4 Mar Today — Vijayawada – College Meetings",
      "Wednesday 5 Mar — Vijayawada – Seminar / Workshops",
      "Thursday 6 Mar — Return travel",
      "Friday 7 Mar — Follow-ups",
      "Saturday 8 Mar — Nothing planned",
      "Sunday 9 Mar — Nothing planned",
    ]);
    const wed = allText(elements(days[2].props.children));
    expect(wed).toContain("Seminar");
    expect(wed).toContain("10:00");
    expect(wed).toContain("Completed");
    expect(wed).toContain("Trip TRV-1");
    expect(allText(elements(days[1].props.children))).toContain("Submitted");
  });

  it("links each item to its page and offers day / week / previous / today / next links (AC5, AC7)", () => {
    const links = hrefs(elements(BdmCalendar(props())));
    expect(links).toEqual(expect.arrayContaining([
      "/bdm/appointments/a1", "/bdm/appointments/a2", "/bdm/travel/t1", "/bdm/follow-ups",
      "/bdm/calendar?view=day&date=2031-03-05", "/bdm/calendar?view=week&date=2031-03-05",
      "/bdm/calendar?view=week&date=2031-02-26", "/bdm/calendar?view=week&date=2031-03-12", "/bdm/calendar?view=week&date=2031-03-04",
    ]));
  });

  it("styles every item link as a link (QA13-01)", () => {
    const itemLinks = elements(BdmCalendar(props())).filter((el) => typeof el.props.href === "string" && /\/(appointments|travel|follow-ups)/.test(el.props.href as string));
    expect(itemLinks).toHaveLength(6); // the 3-day trip on each of its days, 2 appointments, 1 follow-up
    for (const link of itemLinks) expect(link.props.style).toMatchObject({ textDecoration: "underline" });
  });

  it("keeps the manager on manager pages and the chosen BDM in every calendar link", () => {
    const links = hrefs(elements(BdmCalendar(props({ basePath: "/bdm/manager/calendar", managerOf: "b1", view: "day" }))));
    expect(links).toEqual(expect.arrayContaining(["/bdm/manager/appointments/a2", "/bdm/manager/trips/t1", "/bdm/manager/calendar?view=day&date=2031-03-04&bdm=b1"]));
    expect(links.filter((h) => h.startsWith("/bdm/manager/calendar")).every((h) => h.endsWith("bdm=b1"))).toBe(true);
  });

  it("day view shows one day", () => {
    const tree = elements(BdmCalendar(props({ view: "day" })));
    expect(tree.filter((el) => el.type === "section")).toHaveLength(1);
    expect(allText(tree)).toContain("Wednesday 5 Mar 2031");
  });

  it("shows the empty, error and truncated states", () => {
    const empty = allText(elements(BdmCalendar(props({ data: data({ appointments: [], trips: [], tasks: [] }) }))));
    expect(empty).toContain("Nothing planned this week.");
    const failed = elements(BdmCalendar(props({ data: null })));
    expect(failed.find((el) => el.props.role === "alert")).toBeDefined();
    expect(hrefs(failed)).toContain("/bdm/calendar?view=week&date=2031-03-05");
    expect(allText(elements(BdmCalendar(props({ data: data({ truncated: true }) }))))).toContain("Some items are not shown");
  });
});

describe("pages", () => {
  it("the BDM page reads its own week (today when no date)", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/calendar": data() });
    const tree = elements(await BdmCalendarPage({ searchParams: Promise.resolve({ view: "week", date: "2031-03-05" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/calendar?date_from=2031-03-03&date_to=2031-03-09");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmCalendar)!.props.data).toEqual(data());
  });

  it("the BDM page shows an inline error when only the calendar fails", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/calendar": new ApiError("boom", 500) });
    const tree = elements(await BdmCalendarPage({ searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmCalendar)!.props.data).toBeNull();
  });

  it("the BDM page sends the signed-out user to sign in", async () => {
    answer({ "/api/v1/bdm/me": new ApiError("Not authenticated", 401), "/api/v1/auth/me": new ApiError("x", 401) });
    const tree = elements(await BdmCalendarPage({ searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => typeof el.props.loginHref === "string")!.props.loginHref).toBe("/bdm/sign-in");
  });

  it("the manager page asks for a BDM, then reads that BDM's calendar", async () => {
    answer({ "/api/v1/auth/me": { role: "bdm_manager", full_name: "Meera" }, "/api/v1/bdm/calendar": data() });
    let tree = elements(await ManagerCalendarPage({ searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmCalendarPicker)).toBeDefined();
    expect(tree.find((el) => el.type === BdmCalendar)).toBeUndefined();
    expect(allText(tree)).toContain("Choose a BDM");
    tree = elements(await ManagerCalendarPage({ searchParams: Promise.resolve({ bdm: "b1", view: "day", date: "2031-03-05" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/calendar?date_from=2031-03-05&date_to=2031-03-05&bdm_user_id=b1");
    expect(tree.find((el) => el.type === BdmCalendar)!.props.managerOf).toBe("b1");
    expect(tree.find((el) => el.type === BdmCalendarPicker)!.props.current).toEqual({ id: "b1", label: "Asha" });
  });

  it("the manager page says when the BDM is not on the team (404)", async () => {
    answer({ "/api/v1/auth/me": { role: "bdm_manager", full_name: "Meera" }, "/api/v1/bdm/calendar": new ApiError("BDM not found", 404) });
    const tree = elements(await ManagerCalendarPage({ searchParams: Promise.resolve({ bdm: "zz" }) }));
    expect(allText(tree)).toContain("This BDM is not on your team.");
    expect(tree.find((el) => el.type === BdmCalendar)).toBeUndefined();
  });

  it("the manager page refuses other roles", async () => {
    answer({ "/api/v1/auth/me": { role: "it_admin", full_name: "X" } });
    const tree = elements(await ManagerCalendarPage({ searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.props.message === "This page is for BDM managers.")).toBeDefined();
  });
});
