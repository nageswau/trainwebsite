import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationsPanel from "@/components/BdmOrganizationsPanel";

const nav = vi.hoisted(() => ({ search: "", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/bdm/organizations",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pg = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const row = (n: number, archived = false) => ({
  id: `o${n}`, code: `ORG-00000${n}`, name: `College ${n}`, org_type: "college", bdm_type: "college", city: "Kochi", state: null, existing_partner: false,
  assigned_bdm: { id: "b1", full_name: "Asha", active: true }, primary_contact: n === 1 ? { name: "Dr Rao", designation: "Principal", phone: null, email: null } : null,
  archived, last_meeting_at: null, next_meeting_at: null, permissions: { can_edit: true, can_archive: true, can_restore: false, can_reassign: false },
});
function serve(...responses: Response[]) {
  const mock = vi.fn(() => Promise.resolve(responses.shift()!));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  nav.search = "";
  nav.push.mockClear();
});

describe("BdmOrganizationsPanel (bdm-002 AC9)", () => {
  it("shows loading, then rows with dashes for meetings and an Archived badge", async () => {
    serve(res(pg([row(1), row(2, true)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    expect(screen.getByText("Loading organizations…")).toHaveAttribute("role", "status");
    expect(await screen.findByRole("link", { name: "College 1" })).toHaveAttribute("href", "/bdm/organizations/o1");
    expect(screen.getByText("Dr Rao")).toBeInTheDocument();
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByRole("region", { name: "Organizations" })).toHaveAttribute("tabindex", "0");
  });

  it("offers Add organization to a BDM on an empty list, and not to a manager", async () => {
    serve(res(pg([])));
    const { unmount } = render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    expect(await screen.findByText("No organizations yet.")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Add organization" })[0]).toHaveAttribute("href", "/bdm/organizations/new");
    unmount();
    serve(res(pg([])));
    render(<BdmOrganizationsPanel basePath="/bdm/manager/organizations" isBdm={false} />);
    expect(await screen.findByText("Your team has no organizations yet.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Add organization" })).toBeNull();
    expect(screen.queryByLabelText("Assigned to me")).toBeNull();
  });

  it("distinguishes no-match from empty and clears filters", async () => {
    nav.search = "q=zzz";
    serve(res(pg([])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    expect(await screen.findByText("No organizations match these filters.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(nav.push).toHaveBeenCalledWith("/bdm/organizations", { scroll: false });
  });

  it("puts filters in the URL and sends them to the API", async () => {
    nav.search = "org_type=school&archived=1&assigned=me&city=Goa";
    const mock = serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    expect(String(mock.mock.calls[0][0])).toBe("/api/v1/bdm/organizations?limit=50&offset=0&org_type=school&city=Goa&assigned=me&include_archived=true");
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "" } });
    expect(nav.push).toHaveBeenCalledWith("/bdm/organizations?city=Goa&assigned=me&archived=1", { scroll: false });
  });

  it("shows an error with Retry, and past-the-end with a way back", async () => {
    serve(res({ detail: "x" }, 500), res(pg([], 3, 100)));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    expect(await screen.findByText("Unable to load organizations.")).toHaveAttribute("role", "alert");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("This page is past the end of the list.")).toBeInTheDocument();
  });
});
