import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminLeadManagementPanel from "@/components/AdminLeadManagementPanel";
import TelecallerLeadTable from "@/components/TelecallerLeadTable";

// nehn-012 (DEC-SCOPE-296): the lead lists' created-date and counselor filters (in the URL, like every other filter) and the
// "Download Excel" of the filtered list -- the list's own query without the page, for the roles that may export.
let search = "";
const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }),
  usePathname: () => "/leads",
  useSearchParams: () => new URLSearchParams(search),
}));

const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const COUNSELOR = "0b0d6f3e-6a0b-4c1e-9d55-2f6a1a7f0009";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const lead = (id: string) => ({
  id, lead_code: `LD-0000${id}`, name: `Lead ${id}`, email: null, phone: null, whatsapp_number: null, division: "it", subject: "Python", status: "new",
  status_label: "New Lead", source: "website", crm_sync_status: "sent", priority: "warm", created_at: "2026-10-06T05:00:00Z",
  stage_changed_at: "2026-10-06T05:00:00Z", product: null, campaign: null, telecaller: null, counselor: null, organization: null, bdm: null,
  converted_user: null, read_only: false,
});

let items: unknown[];
let fetchMock: ReturnType<typeof vi.fn>;
const calls = (prefix: string) => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith(prefix));
const pushedQuery = () => new URLSearchParams(String(push.mock.calls.at(-1)?.[0]).split("?")[1] ?? "");
beforeEach(() => {
  search = "";
  items = [lead("1")];
  push.mockReset();
  fetchMock = vi.fn((url: string) => {
    if (url.includes("/leads.xlsx")) return Promise.resolve(new Response("x", { status: 200, headers: { "content-type": XLSX } }));
    if (url.startsWith("/api/v1/admin/leads?") || url.startsWith("/api/v1/telecaller/leads?")) return Promise.resolve(res(pageOf(items)));
    if (url.startsWith("/api/v1/admin/users?role=counselor")) return Promise.resolve(res([{ id: COUNSELOR, name: "Cara Counselor", role: "counselor" }]));
    if (url.startsWith("/api/v1/admin/users") || url.startsWith("/api/v1/telecaller/")) return Promise.resolve(res(url.includes("users") ? [] : pageOf([])));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:x", revokeObjectURL: () => undefined }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminLeadManagementPanel (nehn-012)", () => {
  it("sends the created range and counselor from the URL, and downloads the same filters without the page", async () => {
    search = `created_from=2026-10-20&created_to=2026-10-21&owner_id=${COUNSELOR}&q=asha&offset=50`;
    render(<AdminLeadManagementPanel />);
    await screen.findByRole("rowheader", { name: "Lead 1" });
    const listed = new URL(calls("/api/v1/admin/leads?")[0], "http://x").searchParams;
    expect([listed.get("created_from"), listed.get("created_to"), listed.get("owner_id"), listed.get("offset")]).toEqual(["2026-10-20", "2026-10-21", COUNSELOR, "50"]);
    fireEvent.click(screen.getByRole("button", { name: "Download Excel" }));
    await screen.findByText("Report downloaded.");
    const [url] = calls("/api/v1/admin/leads.xlsx");
    const sent = new URL(url, "http://x").searchParams;
    expect([sent.get("created_from"), sent.get("created_to"), sent.get("owner_id"), sent.get("q"), sent.get("limit"), sent.get("offset")])
      .toEqual(["2026-10-20", "2026-10-21", COUNSELOR, "asha", null, null]);
  });

  it("puts a chosen date or counselor in the URL and starts again from the first page", async () => {
    search = "offset=50";
    render(<AdminLeadManagementPanel />);
    fireEvent.change(await screen.findByLabelText("Created from"), { target: { value: "2026-10-20" } });
    expect([pushedQuery().get("created_from"), pushedQuery().get("offset")]).toEqual(["2026-10-20", null]);
    fireEvent.change(screen.getByLabelText("Created to"), { target: { value: "2026-10-21" } });
    expect(pushedQuery().get("created_to")).toBe("2026-10-21");
    const counselor = screen.getByLabelText("Counselor");
    await screen.findByRole("option", { name: "Cara Counselor" });
    fireEvent.change(counselor, { target: { value: COUNSELOR } });
    expect(pushedQuery().get("owner_id")).toBe(COUNSELOR);
  });

  it("says so when the start date is after the end date, and neither asks the API nor offers a download", async () => {
    search = "created_from=2026-10-21&created_to=2026-10-20";
    render(<AdminLeadManagementPanel />);
    expect(await screen.findByText("Choose a start date on or before the end date.")).toBeTruthy();
    expect(calls("/api/v1/admin/leads?")).toEqual([]);
    expect(screen.queryByRole("button", { name: "Download Excel" })).toBeNull();
  });

  it("offers no download for an empty list", async () => {
    items = [];
    render(<AdminLeadManagementPanel />);
    await screen.findByText("No leads found.");
    expect(screen.queryByRole("button", { name: "Download Excel" })).toBeNull();
  });
});

describe("TelecallerLeadTable (nehn-012)", () => {
  it("sends the created range from the URL and lets a manager download the filtered list", async () => {
    search = "created_from=2026-10-20&priority=hot&offset=50";
    render(<TelecallerLeadTable basePath="/telecaller/manager/leads" showTelecaller canExport />);
    await screen.findByRole("link", { name: "Lead 1" });
    expect(new URL(calls("/api/v1/telecaller/leads?")[0], "http://x").searchParams.get("created_from")).toBe("2026-10-20");
    fireEvent.click(screen.getByRole("button", { name: "Download Excel" }));
    await waitFor(() => expect(calls("/api/v1/telecaller/leads.xlsx")).toHaveLength(1));
    const sent = new URL(calls("/api/v1/telecaller/leads.xlsx")[0], "http://x").searchParams;
    expect([sent.get("created_from"), sent.get("priority"), sent.get("offset")]).toEqual(["2026-10-20", "hot", null]);
    fireEvent.change(screen.getByLabelText("Created to"), { target: { value: "2026-10-22" } });
    expect([pushedQuery().get("created_to"), pushedQuery().get("offset")]).toEqual(["2026-10-22", null]);
  });

  it("offers a telecaller no download, and ignores a malformed date in the URL", async () => {
    search = "created_from=20-10-2026";
    render(<TelecallerLeadTable basePath="/telecaller/leads" />);
    await screen.findByRole("link", { name: "Lead 1" });
    expect(new URL(calls("/api/v1/telecaller/leads?")[0], "http://x").searchParams.get("created_from")).toBeNull();
    expect(screen.queryByRole("button", { name: "Download Excel" })).toBeNull();
  });
});
