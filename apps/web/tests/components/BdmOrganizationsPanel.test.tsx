import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(responses.shift()!));
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

  it("signals a later load: the card is busy and says so while the old rows stay (browser QA-15)", async () => {
    nav.search = "";
    let release: (r: Response) => void = () => {};
    const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>()
      .mockResolvedValueOnce(res(pg([row(1)])))
      .mockImplementationOnce(() => new Promise<Response>((resolve) => { release = resolve; }));
    vi.stubGlobal("fetch", mock);
    const { rerender } = render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    nav.search = "q=College";
    rerender(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await waitFor(() => expect(screen.getByText("Updating organizations…")).toBeInTheDocument());
    expect(screen.getByRole("region", { name: "Organizations" }).closest("[aria-busy]")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByRole("link", { name: "College 1" })).toBeInTheDocument();
    release(res(pg([row(2)])));
    await screen.findByRole("link", { name: "College 2" });
    expect(screen.queryByText("Updating organizations…")).toBeNull();
  });

  it("lets long names and codes lay out: names wrap anywhere, codes never break (browser QA-01, QA-02)", async () => {
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    const link = await screen.findByRole("link", { name: "College 1" });
    expect(link.closest("table")).toHaveStyle({ overflowWrap: "anywhere" }); // every column (a 120-character city did the same)
    expect(screen.getByText("ORG-000001").closest("td")).toHaveStyle({ whiteSpace: "nowrap" });
  });

  it("is busy from the moment a filter changes, before the router has moved to the new URL (browser QA-15 re-check)", async () => {
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    fireEvent.change(screen.getByLabelText("Name or code"), { target: { value: "College" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" })); // push is mocked: the URL does not change yet
    expect(screen.getByText("Updating organizations…")).toBeInTheDocument();
    expect(nav.push).toHaveBeenCalledWith("/bdm/organizations?q=College", { scroll: false });
  });

  it("does not stay busy when a search changes nothing", async () => {
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    fireEvent.click(screen.getByRole("button", { name: "Search" })); // same (empty) filters
    expect(screen.queryByText("Updating organizations…")).toBeNull();
  });

  it("styles organization names as links (browser QA-03)", async () => {
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    expect(await screen.findByRole("link", { name: "College 1" })).toHaveStyle({ textDecoration: "underline" });
  });

  it("is not left busy when a filter change is undone before the router moves (simplify review A6)", async () => {
    serve(res(pg([row(1)])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "school" } });
    expect(screen.getByText("Updating organizations…")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Type"), { target: { value: "" } }); // back to the current URL: no navigation will land
    expect(screen.queryByText("Updating organizations…")).toBeNull();
  });

  it("settles when the URL lands somewhere else than the requested filter (Back/Forward)", async () => {
    serve(res(pg([row(1)])), res(pg([row(2)])));
    const { rerender } = render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    fireEvent.change(screen.getByLabelText("Name or code"), { target: { value: "College" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" })); // requests ?q=College
    nav.search = "org_type=school"; // ...but Back lands on another URL
    rerender(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 2" });
    expect(screen.queryByText("Updating organizations…")).toBeNull();
  });

  it("shows real meeting times in IST (bdm-006 AC9)", async () => {
    serve(res(pg([{ ...row(1), next_meeting_at: "2030-01-07T18:00:00Z" }])));
    render(<BdmOrganizationsPanel basePath="/bdm/organizations" isBdm />);
    await screen.findByRole("link", { name: "College 1" });
    expect(screen.getByText(/07 Jan 2030, 23:30 IST/)).toBeInTheDocument();
  });
});
