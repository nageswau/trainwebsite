import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminBdmPanel from "@/components/AdminBdmPanel";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pg = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const row = (n: number, managerActive = true) => ({
  id: `b${n}`, full_name: `BDM ${n}`, email: `b${n}@x.local`, phone: null, active: true, bdm_type: "college", employee_id: `E-${n}`,
  designation: null, department: null, territory: "Kochi", reporting_manager: { id: "m1", full_name: "Meera", active: managerActive }, manager_active: managerActive,
});

/** BDM list responses are served in order; the manager picker always gets one manager. */
function route(bdms: Response[]) {
  const mock = vi.fn((url: string) => Promise.resolve(url.startsWith("/api/v1/admin/bdm-managers") ? res(pg([{ id: "m1", full_name: "Meera" }])) : bdms.shift()!));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminBdmPanel (bdm-001 AC13)", () => {
  it("shows loading, then rows with a no-active-manager badge", async () => {
    route([res(pg([row(1), row(2, false)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    expect(screen.getByText("Loading BDMs…")).toBeInTheDocument();
    expect(await screen.findByText("E-1")).toBeInTheDocument();
    expect(screen.getByText("No active manager")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "BDMs" })).toHaveAttribute("tabindex", "0");
  });

  it("announces loading as a status", () => {
    route([res(pg([row(1)]))]);
    render(<AdminBdmPanel role="super_admin" />);
    expect(screen.getByText("Loading BDMs…")).toHaveAttribute("role", "status");
  });

  it("tells a failed manager load apart from 'no managers', with Retry", async () => {
    let managersOk = false;
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(
      url.startsWith("/api/v1/admin/bdm-managers")
        ? (managersOk ? res(pg([{ id: "m1", full_name: "Meera" }])) : res({ detail: "boom" }, 500))
        : res(pg([row(1)])),
    )));
    render(<AdminBdmPanel role="super_admin" />);
    expect(await screen.findByText("Unable to load BDM managers.")).toBeInTheDocument();
    expect(screen.queryByText(/No active BDM manager/)).toBeNull();
    expect(screen.getByRole("button", { name: "Create BDM" })).toBeDisabled();
    managersOk = true;
    fireEvent.click(screen.getByRole("button", { name: "Retry loading managers" }));
    expect(await screen.findByRole("option", { name: "Meera" })).toBeInTheDocument();
    expect(screen.queryByText("Unable to load BDM managers.")).toBeNull();
  });

  it("shows the empty state", async () => {
    route([res(pg([]))]);
    render(<AdminBdmPanel role="it_admin" />);
    expect(await screen.findByText("No BDMs yet. Use Create BDM above to add the first one.")).toBeInTheDocument();
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
    expect(mock).toHaveBeenCalledWith("/api/v1/admin/bdms?limit=50&offset=50");
  });
});
