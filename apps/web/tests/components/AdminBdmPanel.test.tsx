import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmPanel from "@/components/AdminBdmPanel";

// QA-13: the page and search live in the URL. `search` is what useSearchParams returns at mount; push records navigations.
const nav = vi.hoisted(() => ({ search: "", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/admin/bdms",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pg = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const row = (n: number, managerActive = true) => ({
  id: `b${n}`, full_name: `BDM ${n}`, email: `b${n}@x.local`, phone: null, active: true, bdm_type: "college", employee_id: `E-${n}`,
  designation: null, department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: managerActive }, manager_active: managerActive,
});
const MANAGERS = pg([{ id: "m1", full_name: "Meera", email: "m@x.local" }]);

/** BDM list responses are served in order; the manager check gets `managers` (one manager by default). */
function route(bdms: Response[], managers: () => Response = () => res(MANAGERS)) {
  const mock = vi.fn((url: string) => Promise.resolve(String(url).startsWith("/api/v1/admin/bdm-managers") ? managers() : bdms.shift()!));
  vi.stubGlobal("fetch", mock);
  return mock;
}
const listCalls = (mock: ReturnType<typeof route>) => mock.mock.calls.map(([url]) => String(url)).filter((url) => url.startsWith("/api/v1/admin/bdms"));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  nav.search = "";
  nav.push.mockClear();
});

describe("AdminBdmPanel (bdm-001 AC13)", () => {
  it("shows loading as a status, then rows with a no-active-manager badge", async () => {
    route([res(pg([row(1), row(2, false)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    expect(screen.getByText("Loading BDMs…")).toHaveAttribute("role", "status");
    expect(await screen.findByText("E-1")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "BDMs" })).toHaveAttribute("tabindex", "0");
  });

  it("gives the BDM list the full row width, so its columns are never clipped (QA-01)", async () => {
    route([res(pg([row(1)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    const region = await screen.findByRole("region", { name: "BDMs" });
    expect(region.closest(".action-card")).toHaveClass("wide");
    expect(region.closest(".action-card")).toHaveClass("bdm-list"); // QA-15: CSS moves it above the form on small screens
    // The actions column is named for screen readers only, with the project's real class (.visually-hidden, not .sr-only).
    expect(within(region).getByText("Actions")).toHaveClass("visually-hidden");
  });

  it("checks for managers once, without loading the whole picker list", async () => {
    const mock = route([res(pg([row(1)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    await screen.findByText("E-1");
    expect(mock.mock.calls.map(([url]) => String(url))).toContain("/api/v1/admin/bdm-managers?limit=1");
    expect(screen.getByRole("button", { name: "Create BDM" })).not.toBeDisabled();
  });

  it("says when there are no managers yet", async () => {
    route([res(pg([row(1)]))], () => res(pg([], 0)));
    render(<AdminBdmPanel role="super_admin" />);
    expect(await screen.findByText("No active BDM manager — a Super Admin must create one first.")).toBeInTheDocument();
  });

  it("tells a failed manager check apart from 'no managers', with Retry", async () => {
    let managersOk = false;
    route([res(pg([row(1)]))], () => (managersOk ? res(MANAGERS) : res({ detail: "boom" }, 500)));
    render(<AdminBdmPanel role="super_admin" />);
    expect(await screen.findByText("Unable to load BDM managers.")).toBeInTheDocument();
    expect(screen.queryByText(/No active BDM manager/)).toBeNull();
    expect(screen.getByRole("button", { name: "Create BDM" })).toBeDisabled();
    expect(screen.queryByText(/Loading managers/)).toBeNull(); // QA-11: a failed check never reads as "loading"
    managersOk = true;
    fireEvent.click(screen.getByRole("button", { name: "Retry loading managers" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Create BDM" })).not.toBeDisabled());
    expect(screen.queryByText("Unable to load BDM managers.")).toBeNull();
  });

  it("shows the empty state", async () => {
    route([res(pg([]))]);
    render(<AdminBdmPanel role="it_admin" />);
    // QA-15: the list comes first on small screens, so the hint no longer says "above".
    expect(await screen.findByText("No BDMs yet. Use the Create BDM form to add the first one.")).toBeInTheDocument();
  });

  it("shows an error with Retry, including for a non-page body", async () => {
    route([res({ detail: "boom" }, 500), res("<html>"), res(pg([row(1)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("E-1")).toBeInTheDocument();
  });

  it("pages, keeping the current rows visible while the next page loads", async () => {
    const fifty = Array.from({ length: 50 }, (_, i) => row(i + 1));
    const mock = route([res(pg(fifty, 51)), res(pg([row(51)], 51, 50))]);
    render(<AdminBdmPanel role="super_admin" />);
    const pager = await screen.findByRole("navigation", { name: "BDM pages" });
    expect(within(pager).getByText("Showing 1–50 of 51")).toBeInTheDocument();
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(screen.getByText("E-1")).toBeInTheDocument();
    expect(await screen.findByText("E-51")).toBeInTheDocument();
    expect(listCalls(mock)).toContain("/api/v1/admin/bdms?limit=50&offset=50");
  });
});

describe("AdminBdmPanel keeps its page and search in the URL (QA-13)", () => {
  it("opens on the page and search the URL names, with the search box filled", async () => {
    nav.search = "offset=50&q=asha";
    const mock = route([res(pg([row(51)], 60, 50))]);
    render(<AdminBdmPanel role="super_admin" />);
    expect(await screen.findByText("E-51")).toBeInTheDocument();
    expect(listCalls(mock)[0]).toBe("/api/v1/admin/bdms?limit=50&offset=50&q=asha");
    expect(screen.getByRole("searchbox", { name: "Search BDMs" })).toHaveValue("asha");
  });

  it("ignores a junk offset in the URL", async () => {
    nav.search = "offset=-7x";
    const mock = route([res(pg([row(1)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    await screen.findByText("E-1");
    expect(listCalls(mock)[0]).toBe("/api/v1/admin/bdms?limit=50&offset=0");
  });

  it("records paging and searching as navigations, so refresh and Back keep the place", async () => {
    const fifty = Array.from({ length: 50 }, (_, i) => row(i + 1));
    route([res(pg(fifty, 51)), res(pg([row(51)], 51, 50)), res(pg([row(7)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    fireEvent.click(within(await screen.findByRole("navigation", { name: "BDM pages" })).getByRole("button", { name: "Next page" }));
    expect(nav.push).toHaveBeenLastCalledWith("/admin/bdms?offset=50", { scroll: false });
    await screen.findByText("E-51");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search BDMs" }), { target: { value: "e-7" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(nav.push).toHaveBeenLastCalledWith("/admin/bdms?q=e-7", { scroll: false });
  });

  it("past the last page, offers a way back to the first (QA-14)", async () => {
    nav.search = "offset=500";
    const mock = route([res(pg([], 12, 500)), res(pg([row(1)], 12))]);
    render(<AdminBdmPanel role="super_admin" />);
    expect(await screen.findByText("This page is past the end of the list.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Go to the first page" }));
    expect(await screen.findByText("E-1")).toBeInTheDocument();
    expect(listCalls(mock)[1]).toBe("/api/v1/admin/bdms?limit=50&offset=0");
  });
});

describe("AdminBdmPanel search (QA-04)", () => {
  it("searches by name, email or Employee ID from the first page, and clears", async () => {
    const mock = route([res(pg([row(1)], 120)), res(pg([row(7)])), res(pg([row(1)], 120))]);
    render(<AdminBdmPanel role="super_admin" />);
    await screen.findByText("E-1");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search BDMs" }), { target: { value: " e-7 " } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("E-7")).toBeInTheDocument();
    expect(listCalls(mock)).toContain("/api/v1/admin/bdms?limit=50&offset=0&q=e-7");
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(await screen.findByText("E-1")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search BDMs" })).toHaveValue("");
  });

  it("says when a search matches nothing (not the 'no BDMs yet' message)", async () => {
    route([res(pg([row(1)])), res(pg([]))]);
    render(<AdminBdmPanel role="super_admin" />);
    await screen.findByText("E-1");
    fireEvent.change(screen.getByRole("searchbox", { name: "Search BDMs" }), { target: { value: "nobody" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("No BDMs match “nobody”.")).toBeInTheDocument();
  });

  it("shows the BDM just created by filtering to its Employee ID", async () => {
    const created = { ...row(9), employee_id: "E-NEW" };
    const mock = vi.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.startsWith("/api/v1/admin/bdm-managers")) return Promise.resolve(res(MANAGERS));
      if (init?.method === "POST") return Promise.resolve(res({ id: "b9", email_status: "sent", bdm_profile: {} }, 201));
      return Promise.resolve(res(u.includes("q=E-NEW") ? pg([created]) : pg([row(1)], 120)));
    });
    vi.stubGlobal("fetch", mock);
    render(<AdminBdmPanel role="it_admin" />);
    await screen.findByText("E-1");
    fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "New" } });
    fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "new@x.local" } });
    fireEvent.change(screen.getByLabelText("Employee ID (required)"), { target: { value: "E-NEW" } });
    const combo = screen.getByRole("combobox", { name: "Reporting manager (required)" });
    fireEvent.focus(combo);
    fireEvent.change(combo, { target: { value: "mee" } });
    fireEvent.click(await screen.findByRole("option", { name: "Meera — m@x.local" }));
    fireEvent.click(screen.getByRole("button", { name: "Create BDM" }));
    expect(await screen.findByText("E-NEW")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Search BDMs" })).toHaveValue("E-NEW");
    expect(screen.queryByText("E-1")).toBeNull();
  });
});
