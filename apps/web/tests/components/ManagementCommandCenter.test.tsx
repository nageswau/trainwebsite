import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementPage from "@/app/management/page";
import ManagementPillars from "@/components/ManagementPillars";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { MANAGEMENT_PILLARS, type ManagementMe } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const accountant: ManagementMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PortalShell)!;

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("mgmt-001 Command Center page", () => {
  it("reads /management/me and shows a partner every pillar in the management shell", async () => {
    vi.mocked(serverApi).mockResolvedValue(partner as never);
    const tree = elements(await ManagementPage());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/me");
    const shell = shellOf(tree);
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.userName).toBe("Arjun Partner");
    expect(shell.props.nav).toContainEqual({ label: "Command Center", href: "/management" });
    expect(shell.props.nav).toContainEqual({ label: "Business snapshot", href: "/management/snapshot" });
    expect(shell.props.nav).toContainEqual({ label: "Management activity", href: "/management/activity" }); // mgmt-002
    render(<>{shell.props.children}</>);
    expect(screen.getByRole("heading", { level: 2, name: "Management Command Center" })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual(MANAGEMENT_PILLARS.map((p) => p.title));
  });

  it("labels an accountant and shows Finance without the partner-only entries", async () => {
    vi.mocked(serverApi).mockResolvedValue(accountant as never);
    const shell = shellOf(elements(await ManagementPage()));
    expect(shell.props.roleLabel).toBe("Accountant");
    render(<>{shell.props.children}</>);
    const finance = screen.getByRole("region", { name: "Finance" });
    expect(within(finance).getByText("Salaries")).toBeTruthy();
    expect(within(finance).queryByText("Investments & ROI")).toBeNull();
    expect(screen.queryByRole("region", { name: "Students" })).toBeNull();
  });

  it("keeps the super admin's own sidebar and hides Finance", async () => {
    vi.mocked(serverApi).mockResolvedValue(superAdmin as never);
    const shell = shellOf(elements(await ManagementPage()));
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
    expect(shell.props.roleLabel).toBe("Super Administrator");
    render(<>{shell.props.children}</>);
    expect(screen.queryByRole("region", { name: "Finance" })).toBeNull();
    expect(screen.getByRole("region", { name: "Students" })).toBeTruthy();
  });

  it("shows the access card when the API refuses (403) instead of the shell", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") throw new ApiError("Management access required", 403);
      return { id: "x", role: "it_admin", division: "it", full_name: "IT" } as never;
    });
    render(await ManagementPage());
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Management access required")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to your dashboard" }).getAttribute("href")).toBe("/it/admin/dashboard");
  });
});

describe("mgmt-001 ManagementPillars", () => {
  it("lists upcoming entries as plain text, never as links", () => {
    render(<ManagementPillars pillars={MANAGEMENT_PILLARS} />);
    const live = MANAGEMENT_PILLARS.flatMap((p) => p.entries.flatMap((e) => (e.href ? [e.href] : [])));
    expect(screen.queryAllByRole("link").map((link) => link.getAttribute("href"))).toEqual(live);
    const students = screen.getByRole("region", { name: "Students" });
    expect(within(students).getAllByText("Coming soon").length).toBe(MANAGEMENT_PILLARS[0].entries.length);
  });

  it("links a live entry", () => {
    render(<ManagementPillars pillars={[{ title: "Finance", entries: [{ label: "Salaries", item: "mgmt-011", tier: "finance", href: "/management/salaries" }] }]} />);
    expect(screen.getByRole("link", { name: "Salaries" }).getAttribute("href")).toBe("/management/salaries");
    expect(screen.queryByText("Coming soon")).toBeNull();
  });
});
