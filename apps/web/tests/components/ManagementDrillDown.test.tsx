import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DrillPage from "@/app/management/drill/[chain]/page";
import ManagementDrillDown from "@/components/ManagementDrillDown";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import type { Drill, DrillQuery } from "@/lib/managementDrill";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), notFound: vi.fn(() => { throw new Error("NEXT_NOT_FOUND"); }), usePathname: () => "/management/drill/it" })); // prettier-ignore
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const COURSE = "11111111-1111-4111-8111-111111111111";
const BATCH = "22222222-2222-4222-8222-222222222222";
const QUERY: DrillQuery = { month: "2026-05", period: "month", path: [COURSE], page: 1 };

function drill(overrides: Partial<Drill> = {}): Drill {
  return {
    chain: "it", chain_label: "IT Training revenue", month: "2026-05", period: "month", label: "May 2026", start: "2026-05-01", end: "2026-05-31",
    total: "42000.00", count: 2,
    breadcrumbs: [{ level: "course", level_label: "Course", key: COURSE, name: "Python Full Stack" }],
    level: { key: "batch", label: "Batch" },
    rows: [
      { key: BATCH, name: "Morning", amount: "30000.00", count: 1, latest: "2026-05-09" },
      { key: "none", name: "No batch", amount: "12000.00", count: 1, latest: "2026-05-10" },
    ],
    total_rows: 2, limit: 25, offset: 0, record: null,
    ...overrides,
  }; // prettier-ignore
}

function view(props: Partial<Parameters<typeof ManagementDrillDown>[0]> = {}) {
  return render(<ManagementDrillDown chain="it" data={drill()} error="" query={QUERY} maxMonth="2026-10" {...props} />);
}

describe("mgmt-033 ManagementDrillDown", () => {
  afterEach(cleanup);

  it("shows the path as breadcrumbs, the total and the next level's rows, each linking one level down", () => {
    view();
    const crumbs = screen.getByRole("navigation", { name: "Drill-down path" });
    expect(within(crumbs).getByRole("link", { name: "IT Training revenue" })).toHaveAttribute("href", "/management/drill/it?month=2026-05&period=month");
    expect(within(crumbs).getByText("Python Full Stack").closest("[aria-current]")).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("list", { name: "Drill-down figures" })).toHaveTextContent("₹42,000.00");
    const table = screen.getByRole("table", { name: "By batch" });
    expect(within(table).getByRole("link", { name: "Morning" })).toHaveAttribute("href", `/management/drill/it?month=2026-05&period=month&path=${COURSE}%2C${BATCH}`);
    expect(within(table).getByRole("link", { name: "No batch" })).toHaveAttribute("href", `/management/drill/it?month=2026-05&period=month&path=${COURSE}%2Cnone`);
    expect(within(table).getByRole("row", { name: /^Total/ })).toHaveTextContent("₹42,000.00");
  });

  it("keeps the path in the period form", () => {
    view();
    const form = screen.getByRole("form", { name: "Choose a period" });
    expect(form).toHaveAttribute("method", "get");
    expect(form.querySelector('input[name="path"]')).toHaveAttribute("value", COURSE);
  });

  it("pages a long level", () => {
    view({ data: drill({ total_rows: 30, offset: 25 }), query: { ...QUERY, page: 2 } });
    expect(screen.getByText(/Showing 26–27 of 30/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Previous" })).toHaveAttribute("href", `/management/drill/it?month=2026-05&period=month&path=${COURSE}`);
  });

  it("shows the record read-only at the end, with its outcomes and the audit note", () => {
    view({
      data: drill({
        level: null, rows: [], total_rows: 0, total: "30000.00", count: 1,
        breadcrumbs: [
          { level: "course", level_label: "Course", key: COURSE, name: "Python Full Stack" },
          { level: "payment", level_label: "Payment", key: "p9", name: "Enrolment fee · receipt RCP-1" },
        ],
        record: {
          source: "payment", id: "p9", entry_date: "2026-05-09", amount: "30000.00", currency: "INR", description: "Enrolment fee · receipt RCP-1",
          details: [{ label: "Enrolment", value: "ENR-1" }], outcomes: { title: "Placement", items: [{ name: "Java · Acme", detail: null, status: "Joined" }] },
        },
      }),
    }); // prettier-ignore
    const record = screen.getByRole("region", { name: "Payment record" });
    expect(record).toHaveTextContent("₹30,000.00");
    expect(record).toHaveTextContent("ENR-1");
    expect(within(record).getByRole("list", { name: "Placement" })).toHaveTextContent("Java · Acme — Joined");
    expect(record.querySelector("input, button, form")).toBeNull();
    expect(screen.getByText(/recorded in Management activity/)).toBeInTheDocument();
  });

  it("says when nothing is recorded and when the outcome list is empty", () => {
    view({ data: drill({ breadcrumbs: [], level: { key: "course", label: "Course" }, rows: [], total_rows: 0, total: "0.00", count: 0 }), query: { ...QUERY, path: [] } });
    expect(screen.getByRole("status")).toHaveTextContent("No counted IT Training revenue in May 2026.");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("says a page past the last row is empty, not that nothing is recorded (QA33-01)", () => {
    view({ data: drill({ rows: [], total_rows: 1, offset: 975 }), query: { ...QUERY, page: 40 } });
    expect(screen.getByRole("status")).toHaveTextContent("This page is past the last of 1 row.");
    expect(screen.queryByText(/No counted/)).toBeNull();
    expect(screen.getByRole("link", { name: "First page" })).toHaveAttribute("href", `/management/drill/it?month=2026-05&period=month&path=${COURSE}`);
  });

  it("fits a phone: the figure tiles stack and the level table needs no sideways scroll (QA33-02, QA33-03)", () => {
    view();
    expect(screen.getByRole("list", { name: "Drill-down figures" })).toHaveClass("accounts-tiles");
    const table = screen.getByRole("table", { name: "By batch" });
    expect(table).toHaveStyle({ minWidth: "0" });
    expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Batch", "Lines", "Amount"]);
    cleanup();
    view({ data: drill({ level: { key: "payment", label: "Payment" }, rows: [{ key: "p9", name: "Enrolment fee · receipt RCP-1", amount: "30000.00", count: 1, latest: "2026-05-09" }], total_rows: 1 }) });
    const payments = screen.getByRole("table", { name: "By payment" });
    expect(within(payments).getAllByRole("columnheader").map((th) => th.textContent)).toEqual(["Payment", "Date", "Amount"]);
    expect(within(payments).getByRole("row", { name: /RCP-1/ })).toHaveTextContent("09 May 2026");
  });

  it("shows an error with a way back to the top of the chain", () => {
    view({ data: null, error: "Nothing to show for this selection in this period" });
    expect(screen.getByText("Nothing to show for this selection in this period")).toHaveClass("form-error");
    expect(screen.getByRole("link", { name: "Start again from the top" })).toHaveAttribute("href", "/management/drill/it?month=2026-05&period=month");
  });
});

describe("mgmt-033 drill-down page", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });
  afterEach(cleanup);

  function answer(data: Drill | Error) {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      const result = path === "/api/v1/management/me" ? partner : data;
      if (result instanceof Error) throw result;
      return result as never;
    });
  }

  it("asks the API for the level in the address and renders it", async () => {
    answer(drill());
    render(await DrillPage({ params: Promise.resolve({ chain: "it" }), searchParams: Promise.resolve({ month: "2026-05", path: COURSE }) }));
    expect(serverApi).toHaveBeenCalledWith(`/api/v1/management/drill/it?month=2026-05&period=month&path=${COURSE}&limit=25&offset=0`);
    expect(screen.getByRole("heading", { name: "IT Training revenue: drill-down" })).toBeInTheDocument();
  });

  it("shows the API's 404 and 422 messages", async () => {
    answer(new ApiError("Nothing to show for this selection in this period", 404));
    render(await DrillPage({ params: Promise.resolve({ chain: "it" }), searchParams: Promise.resolve({ path: COURSE }) }));
    expect(screen.getByText("Nothing to show for this selection in this period")).toBeInTheDocument();
  });

  it("shows the access card to the super admin", async () => {
    answer(new ApiError("Finance access required", 403));
    render(await DrillPage({ params: Promise.resolve({ chain: "abroad" }), searchParams: Promise.resolve({}) }));
    expect(screen.queryByRole("navigation", { name: "Drill-down path" })).toBeNull();
    expect(screen.getByText(/Finance access required/)).toBeInTheDocument();
  });

  it("is not found for an unknown chain", async () => {
    answer(drill());
    await expect(DrillPage({ params: Promise.resolve({ chain: "visa" }), searchParams: Promise.resolve({}) })).rejects.toThrow("NEXT_NOT_FOUND");
  });
});
