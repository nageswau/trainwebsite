import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CounselorLeadsPanel from "@/components/CounselorLeadsPanel";
import ExportButtons, { XLSX_TYPE } from "@/components/ExportButtons";

// ccrm-035 (DEC-SCOPE-268): Download CSV / Download Excel, side by side and named for what they export; each fetches first
// (ReportDownloadButton), so a refusal is a message, never a saved file.
let search = new URLSearchParams();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/overseas/counselor/leads", useSearchParams: () => search }));

const lead = { id: "l1", lead_code: "LD-000001", name: "Asha", subject: "Study abroad", status_label: "Follow-up", telecaller: null, created_at: "2026-10-01T10:00:00Z" };
const page = (items: unknown[]) => new Response(JSON.stringify({ items, total: items.length, limit: 20, offset: 0 }), { status: 200 });
const file = (type: string) => new Response("data", { status: 200, headers: { "content-type": type } });

beforeEach(() => {
  search = new URLSearchParams();
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ExportButtons (ccrm-035)", () => {
  it("offers CSV and Excel in a named group and asks for each format", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(file("text/csv; charset=utf-8")).mockResolvedValueOnce(file(XLSX_TYPE));
    vi.stubGlobal("fetch", fetchMock);
    render(<ExportButtons url="/api/v1/counselor/exports/leads?stage=new" filename="my-leads" label="Export my leads" />);
    const group = screen.getByRole("group", { name: "Export my leads" });
    fireEvent.click(within(group).getByRole("button", { name: "Download CSV" }));
    await screen.findByText("Report downloaded.");
    fireEvent.click(within(group).getByRole("button", { name: "Download Excel" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/v1/counselor/exports/leads?stage=new&format=csv", "/api/v1/counselor/exports/leads?stage=new&format=xlsx"]);
  });

  it("shows the API's refusal instead of saving a file", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "This list has more than 5,000 rows; narrow the filters" }), { status: 422 })));
    render(<ExportButtons url="/api/v1/counselor/exports/applications" filename="my-applications" label="Export my applications" />);
    fireEvent.click(screen.getByRole("button", { name: "Download Excel" }));
    expect(await screen.findByText("This list has more than 5,000 rows; narrow the filters")).toBeInTheDocument();
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
  });
});

describe("CounselorLeadsPanel export (ccrm-035)", () => {
  it("exports the overseas counselor's leads with the filters in use", async () => {
    search = new URLSearchParams("priority=hot");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(page([lead])));
    render(<CounselorLeadsPanel division="overseas" />);
    const group = await screen.findByRole("group", { name: "Export my leads" });
    expect(within(group).getByRole("button", { name: "Download CSV" })).toBeInTheDocument();
    fireEvent.click(within(group).getByRole("button", { name: "Download CSV" }));
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([url]) => url === "/api/v1/counselor/exports/leads?priority=hot&format=csv")).toBe(true));
  });

  it("offers no export of an empty list or to the IT counselor", async () => {
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => page([lead])));
    render(<CounselorLeadsPanel division="it" />);
    await screen.findByText("LD-000001");
    expect(screen.queryByRole("group", { name: "Export my leads" })).toBeNull();
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockImplementation(async () => page([])));
    render(<CounselorLeadsPanel division="overseas" />);
    await screen.findByText("No leads have been handed to you yet.");
    expect(screen.queryByRole("group", { name: "Export my leads" })).toBeNull();
  });
});
