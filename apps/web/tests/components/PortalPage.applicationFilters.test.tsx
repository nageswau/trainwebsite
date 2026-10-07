import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PortalPage from "@/components/PortalPage";
import { ApiError, serverApi } from "@/lib/api";

// AGN-023 (DEC-SCOPE-090 H11): the overseas Admin/counselor Students/Applications filter bar, the query forwarded to the API, and the
// 422 fallback to the unfiltered list.
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, serverApi: vi.fn() };
});
vi.mock("next/navigation", () => ({
  notFound: () => { throw new Error("notFound"); },
  useSearchParams: () => new URLSearchParams(""),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/overseas/admin/applications",
}));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/WorkflowPanel", () => ({ default: () => null }));
vi.mock("@/components/RefreshOnHistoryNav", () => ({ default: () => null }));

const api = vi.mocked(serverApi);
const ME = { id: "u1", role: "overseas_admin", full_name: "Ola Admin", email: "a@example.local" };
const FILTERS = { agency: null, counselor: null, agencies: [{ value: "org1", label: "Demo Global Education" }], counselors: [{ value: "c1", label: "Asha Rao" }] };
const payload = (extra: Record<string, unknown> = {}) => ({
  title: "Applications", subtitle: "All applications", metrics: [], actions: [], panels: [],
  columns: [{ key: "student", label: "Student" }], rows: [{ student: "Riya Patel" }], ...extra,
});

function portalCalls() {
  return api.mock.calls.map((c) => c[0] as string).filter((p) => p.startsWith("/api/v1/portal/"));
}

beforeEach(() => {
  api.mockReset();
  api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve(ME) : Promise.resolve(payload({ filters: FILTERS }))));
});
afterEach(cleanup);

describe("PortalPage application filters (AGN-023)", () => {
  it("falls back to the unfiltered list with the refusal when the API says 422", async () => {
    api.mockImplementation((path: string) => {
      if (path === "/api/v1/auth/me") return Promise.resolve(ME);
      if (path.includes("?agency=bad")) return Promise.reject(new ApiError("Unknown filter value", 422));
      return Promise.resolve(payload({ filters: FILTERS }));
    });
    render(await PortalPage({ division: "overseas", role: "admin", section: "applications", query: { agency: "bad" } }));
    expect(portalCalls()).toEqual(["/api/v1/portal/overseas/admin/applications?agency=bad", "/api/v1/portal/overseas/admin/applications"]);
    expect(screen.getByRole("alert")).toHaveTextContent("Unknown filter value -- showing all applications.");
    expect(screen.getByText("Riya Patel")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: "Access unavailable" })).toBeNull();
  });

  it("renders the filter bar for the overseas Admin and counselor", async () => {
    render(await PortalPage({ division: "overseas", role: "admin", section: "applications" }));
    expect(screen.getByLabelText("Agency")).toBeInTheDocument();
    expect(screen.getByLabelText("Counsellor")).toBeInTheDocument();
    cleanup();
    api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve({ ...ME, role: "counselor" }) : Promise.resolve(payload({ filters: { ...FILTERS, counselors: undefined } }))));
    render(await PortalPage({ division: "overseas", role: "counselor", section: "students" }));
    expect(screen.getByLabelText("Agency")).toBeInTheDocument();
    expect(screen.queryByLabelText("Counsellor")).toBeNull();
  });

  it("renders no filter bar when the payload has no filters", async () => {
    api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve(ME) : Promise.resolve(payload({ title: "Reports" }))));
    render(await PortalPage({ division: "overseas", role: "admin", section: "reports" }));
    expect(screen.getByText("Riya Patel")).toBeInTheDocument();
    expect(screen.queryByLabelText("Agency")).toBeNull();
    expect(screen.queryByRole("form", { name: "Filter applications" })).toBeNull();
  });

  it("shows the no-match empty state when a filter is applied and nothing matches", async () => {
    api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve(ME) : Promise.resolve(payload({ rows: [], filters: { ...FILTERS, agency: "org1" } }))));
    render(await PortalPage({ division: "overseas", role: "admin", section: "applications", query: { agency: "org1" } }));
    expect(screen.getByRole("heading", { name: "No applications match these filters" })).toBeInTheDocument();
  });

  it("sends agency and counselor to the API, and nothing for other keys", async () => {
    render(await PortalPage({ division: "overseas", role: "admin", section: "applications", query: { agency: "x", counselor: "none", foo: "1" } }));
    expect(portalCalls()).toEqual(["/api/v1/portal/overseas/admin/applications?agency=x&counselor=none"]);
    cleanup();
    api.mockClear();
    render(await PortalPage({ division: "overseas", role: "admin", section: "applications", query: { foo: "1" } }));
    expect(portalCalls()).toEqual(["/api/v1/portal/overseas/admin/applications"]);
  });

  it("never forwards the filters from a page other than the overseas Admin/counselor ones", async () => {
    api.mockImplementation((path: string) => (path === "/api/v1/auth/me" ? Promise.resolve({ ...ME, role: "super_admin" }) : Promise.resolve(payload({ title: "Reports" }))));
    render(await PortalPage({ division: "overseas", role: "agent", section: "reports", query: { agency: "x" } }));
    expect(portalCalls()).toEqual(["/api/v1/portal/overseas/agent/reports"]);
  });
});
