import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorDashboardPanel, { CounselorDashboardBoard, CounselorDashboardSkeleton, SECTIONS } from "@/components/CounselorDashboardPanel";
import { ApiError, serverApi } from "@/lib/api";
import type { CounselorDashboard, CounselorDashboardSection } from "@/lib/types";

// ccrm-032 (DEC-SCOPE-277): the counselor's action dashboard -- every section, its count, items, links, empty, error and loading states.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);
afterEach(() => {
  cleanup();
  api.mockReset();
});

const none: CounselorDashboardSection = { count: 0, more: false, items: [] };
const data = (sections: Partial<CounselorDashboard["sections"]> = {}): CounselorDashboard => ({
  today: "2026-10-25",
  window_days: 14,
  follow_up_days: 7,
  sections: Object.fromEntries(SECTIONS.map((s) => [s.key, sections[s.key] ?? none])) as CounselorDashboard["sections"],
});
const region = (name: RegExp) => screen.getByRole("region", { name });

describe("CounselorDashboardBoard", () => {
  it("shows all twelve sections, each with its count and an empty line", () => {
    render(<CounselorDashboardBoard data={data()} />);
    expect(SECTIONS).toHaveLength(12);
    for (const s of SECTIONS) {
      const r = region(new RegExp(s.title.replace(/[()]/g, "\\$&")));
      expect(within(r).getByText(s.empty)).toBeTruthy();
      expect(within(r).getByText("0")).toBeTruthy();
    }
  });

  it("lists items as links, flags overdue ones and points to the full list when there are more", () => {
    render(
      <CounselorDashboardBoard
        data={data({
          follow_ups: {
            count: 14,
            more: true,
            items: [
              { id: "f1", label: "LD-1 · Asha", detail: "Call back", date: "2026-10-22T05:30:00Z", overdue: true, href: "/overseas/counselor/leads/l1" },
              { id: "f2", label: "LD-2 · Ravi", detail: "Counselor call", date: "2026-10-25T09:00:00Z", overdue: false, href: "/overseas/counselor/leads/l2" },
            ],
          },
          offers_due: {
            count: 1,
            more: false,
            items: [{ id: "o1", label: "APP-1 · Asha", detail: "Offer deadline 30 Oct 2026 · Oxford", date: "2026-10-30", overdue: false, href: "/overseas/counselor/students/s1" }],
          },
        })}
      />,
    );
    const fu = region(/Follow-ups due/);
    expect(within(fu).getByText("14")).toBeTruthy();
    expect(within(fu).getByRole("link", { name: /LD-1 · Asha/ }).getAttribute("href")).toBe("/overseas/counselor/leads/l1");
    expect(within(fu).getAllByText("Overdue")).toHaveLength(1);
    expect(within(fu).getByText(/22 Oct, 11:00 am/i, { selector: "time" })).toBeTruthy(); // IST
    expect(within(fu).getByRole("link", { name: /View all 14/ })).toBeTruthy();
    const offers = region(/Offer deadlines/);
    expect(within(offers).getByText("30 Oct 2026", { selector: "time" })).toBeTruthy();
    expect(within(offers).queryByRole("link", { name: /View all/ })).toBeNull();
  });

  it("states the approaching window in the offers heading", () => {
    render(<CounselorDashboardBoard data={data()} />);
    expect(screen.getByText(/due in the next 14 days/)).toBeTruthy();
  });

  it("ccrm-042: follow-ups and tasks cover overdue and the next 7 days", () => {
    render(<CounselorDashboardBoard data={data()} />);
    for (const [name, empty] of [[/^Follow-ups due/, "No follow-ups in the next 7 days."], [/^Tasks due/, "No tasks due in the next 7 days."]] as const) {
      const r = region(name);
      expect(within(r).getByText("Overdue or due in the next 7 days, soonest first.")).toBeTruthy();
      expect(within(r).getByText(empty)).toBeTruthy();
    }
    expect(screen.queryByRole("region", { name: /Overdue tasks/ })).toBeNull();
  });
});

describe("CounselorDashboardPanel", () => {
  it("reads its own endpoint", async () => {
    api.mockResolvedValue(data());
    render(await CounselorDashboardPanel());
    expect(api).toHaveBeenCalledWith("/api/v1/counselor/dashboard");
    expect(region(/Tasks due/)).toBeTruthy();
  });

  it("keeps the page working when the endpoint fails", async () => {
    api.mockRejectedValue(new ApiError("boom", 500));
    render(await CounselorDashboardPanel());
    expect(screen.getByRole("alert").textContent).toMatch(/Dashboard sections are unavailable right now/);
    expect(screen.getByRole("link", { name: "Try again" }).getAttribute("href")).toBe("/overseas/counselor/dashboard");
  });

  it("has a loading skeleton that is announced as busy", () => {
    const { container } = render(<CounselorDashboardSkeleton />);
    expect(container.querySelector("[aria-busy='true']")).toBeTruthy();
    expect(screen.getByText("Loading dashboard sections")).toBeTruthy();
  });
});
