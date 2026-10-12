import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import SnapshotPage from "@/app/management/snapshot/page";
import ManagementSnapshot from "@/components/ManagementSnapshot";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe, ManagementSnapshot as Snapshot } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/snapshot" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const LABELS = [
  "Total Students", "Active Students", "IT Training Students", "Abroad Education Students", "Agent Students", "Placement Students", "Active Agents",
  "Partner Schools", "University Partners", "Partner Companies", "Trainers", "Counselors", "Telecallers", "BDMs", "Recruiters",
]; // prettier-ignore
const snapshot: Snapshot = {
  as_of: "2026-10-12",
  kpis: LABELS.map((label, i) => ({ id: `S${i + 1}`, key: label.toLowerCase().replaceAll(" ", "_"), label, value: i === 0 ? 5240 : i })),
};

function answer(me: ManagementMe | Error, figures: Snapshot | Error = snapshot) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const result = path === "/api/v1/management/me" ? me : path === "/api/v1/management/snapshot" ? figures : ({ id: "x", role: "accountant", division: "global", full_name: "Ravi" } as never);
    if (result instanceof Error) throw result;
    return result as never;
  });
}

beforeEach(() => vi.mocked(serverApi).mockReset());
afterEach(() => cleanup());

describe("mgmt-003 snapshot page", () => {
  it("reads the caller and the snapshot, and shows the partner the fifteen figures in the management shell", async () => {
    answer(partner);
    const tree = elements(await SnapshotPage());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/me");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/snapshot");
    const shell = tree.find((el) => el.type === PortalShell)!;
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Business snapshot", href: "/management/snapshot" });
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("heading", { level: 2, name: "Business snapshot" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Command Center" }).getAttribute("href")).toBe("/management");
  });

  it("keeps the super admin's own sidebar", async () => {
    answer(superAdmin);
    const shell = elements(await SnapshotPage()).find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows the access card when the snapshot is refused (the accountant's 403)", async () => {
    answer({ ...partner, role: "accountant", tiers: { operational: false, finance: true, partner_only: false } }, new ApiError("Operational access required", 403));
    render(await SnapshotPage());
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Operational access required")).toBeTruthy();
  });
});

describe("mgmt-003 ManagementSnapshot tiles", () => {
  it("lists the fifteen figures in source order with Indian digit grouping and the as-of date", () => {
    render(<ManagementSnapshot snapshot={snapshot} />);
    const items = within(screen.getByRole("list", { name: "Business snapshot figures" })).getAllByRole("listitem");
    expect(items.map((item) => item.querySelector("span")?.textContent)).toEqual(LABELS);
    expect(within(items[0]).getByText("5,240")).toBeTruthy();
    expect(within(items[3]).getByText("3")).toBeTruthy();
    expect(screen.getByText(/As of 12 Oct 2026/)).toBeTruthy();
  });

  it("shows a zero as 0", () => {
    render(<ManagementSnapshot snapshot={{ as_of: "2026-10-12", kpis: [{ id: "S7", key: "active_agents", label: "Active Agents", value: 0 }] }} />);
    expect(within(screen.getByRole("listitem")).getByText("0")).toBeTruthy();
  });
});
