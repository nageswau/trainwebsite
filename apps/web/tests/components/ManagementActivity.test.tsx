import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementActivityPage from "@/app/management/activity/page";
import ManagementActivity from "@/components/ManagementActivity";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { activityFilters, activityHref, describeActivity, type ManagementActivityPage as ActivityData, type ManagementMe } from "@/lib/management";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/activity" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Arjun Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Root", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const UUID = "6f1c2b9e-3a4d-4e5f-8a7b-1c2d3e4f5a6b";
const meera = { id: "p2", full_name: "Meera Partner", role: "partner" };
const page = (overrides: Partial<ActivityData> = {}): ActivityData => ({
  items: [
    { id: "a1", at: "2026-10-12T04:30:00Z", actor: meera, kind: "mgmt.ledger", kind_label: "Ledger entry", verb: "approve", entity_id: "E-1", fields: ["status"], values: { status: { before: "pending", after: "approved" } }, count: null },
    { id: "a2", at: "2026-10-11T04:30:00Z", actor: null, kind: "mgmt.ledger", kind_label: "Ledger entry", verb: "import", entity_id: null, fields: [], values: null, count: 42 },
  ],
  total: 2, limit: 25, offset: 0,
  kinds: [{ value: "mgmt.task", label: "Task" }, { value: "mgmt.ledger", label: "Ledger entry" }],
  actors: [meera],
  ...overrides,
});
const shellOf = (tree: ReturnType<typeof elements>) => tree.find((el) => el.type === PortalShell)!;
const route = (activity: () => unknown, me: ManagementMe = partner) =>
  vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/management/me" ? me : activity()) as never);

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("mgmt-002 activity helpers", () => {
  it("keeps only known filters, and a whole-number offset", () => {
    expect(activityFilters({ actor: UUID, kind: "mgmt.ledger", date_from: "2026-10-01", date_to: "", offset: "25", other: "x" }))
      .toEqual({ actor: UUID, kind: "mgmt.ledger", date_from: "2026-10-01", date_to: "", offset: 25 });
    expect(activityFilters({ offset: "-3" }).offset).toBe(0);
    expect(activityFilters({ offset: ["5", "6"], kind: ["a", "b"] })).toEqual({ actor: "", kind: "", date_from: "", date_to: "", offset: 0 });
  });

  it("drops a malformed actor id and impossible dates (only a hand-edited address has them)", () => {
    expect(activityFilters({ actor: "nope", date_from: "2026-13-01", date_to: "2026-02-30" })).toEqual({ actor: "", kind: "", date_from: "", date_to: "", offset: 0 });
  });

  it("builds a query with only the filters set", () => {
    expect(activityHref({ actor: "", kind: "mgmt.task", date_from: "", date_to: "", offset: 0 })).toBe("/management/activity?kind=mgmt.task");
    expect(activityHref({ actor: "p2", kind: "", date_from: "", date_to: "2026-10-12", offset: 50 })).toBe("/management/activity?actor=p2&date_to=2026-10-12&offset=50");
    expect(activityHref({ actor: "", kind: "", date_from: "", date_to: "", offset: 0 })).toBe("/management/activity");
  });

  it("words an entry: what happened, which fields, values, counts", () => {
    const [approved, imported] = page().items;
    expect(describeActivity(approved)).toEqual({ title: "Ledger entry approved", detail: "status: pending → approved" });
    expect(describeActivity(imported)).toEqual({ title: "Ledger entry imported", detail: "42 records" });
    expect(describeActivity({ ...approved, kind_label: "Task", verb: "create", fields: ["title", "deadline"], values: null }).detail).toBe("title, deadline");
  });
});

describe("mgmt-002 ManagementActivity", () => {
  const filters = activityFilters({});

  it("lists who did what, newest first, with the actor and an IST time", () => {
    render(<ManagementActivity data={page()} error="" filters={filters} />);
    const rows = within(screen.getByRole("list", { name: "Management activity" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Ledger entry approved");
    expect(rows[0].textContent).toContain("by Meera Partner");
    expect(rows[0].textContent).toContain("12 Oct 2026, 10:00 IST");
    expect(rows[1].textContent).toContain("by System");
  });

  it("offers only the caller's kinds and actors as filters, keeping the current ones", () => {
    render(<ManagementActivity data={page()} error="" filters={{ ...filters, kind: "mgmt.ledger", actor: "p2" }} />);
    const kind = screen.getByLabelText("Kind") as HTMLSelectElement;
    expect([...kind.options].map((o) => o.textContent)).toEqual(["All kinds", "Task", "Ledger entry"]);
    expect(kind.value).toBe("mgmt.ledger");
    expect((screen.getByLabelText("Done by") as HTMLSelectElement).value).toBe("p2");
    expect(screen.getByRole("link", { name: "Clear filters" }).getAttribute("href")).toBe("/management/activity");
  });

  it("says so when nothing matches", () => {
    render(<ManagementActivity data={page({ items: [], total: 0 })} error="" filters={filters} />);
    expect(screen.getByText("No management activity matches these filters.")).toBeTruthy();
  });

  it("shows an error above the form and no list", () => {
    render(<ManagementActivity data={null} error="The end date must be on or after the start date" filters={filters} />);
    expect(screen.getByRole("alert").textContent).toBe("The end date must be on or after the start date");
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.getByRole("button", { name: "Apply" })).toBeTruthy();
  });

  it("pages with links that keep the filters", () => {
    render(<ManagementActivity data={page({ total: 60, limit: 25, offset: 25 })} error="" filters={{ ...filters, kind: "mgmt.ledger", offset: 25 }} />);
    expect(screen.getByText("Showing 26–27 of 60")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Previous page" }).getAttribute("href")).toBe("/management/activity?kind=mgmt.ledger");
    expect(screen.getByRole("link", { name: "Next page" }).getAttribute("href")).toBe("/management/activity?kind=mgmt.ledger&offset=50");
  });
});

describe("mgmt-002 activity page", () => {
  it("reads the filters into the API call and shows a partner the management sidebar", async () => {
    route(() => page());
    const tree = elements(await ManagementActivityPage({ searchParams: Promise.resolve({ kind: "mgmt.ledger", offset: "25" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/management/activity?kind=mgmt.ledger&offset=25&limit=25");
    const shell = shellOf(tree);
    expect(shell.props.roleLabel).toBe("Partner");
    expect(shell.props.nav).toContainEqual({ label: "Management activity", href: "/management/activity" });
  });

  it("keeps the super admin's own sidebar", async () => {
    route(() => page(), superAdmin);
    const shell = shellOf(elements(await ManagementActivityPage({ searchParams: Promise.resolve({}) })));
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
  });

  it("shows a 422 message above the form", async () => {
    route(() => Promise.reject(new ApiError("Unknown activity kind", 422)));
    render(<>{shellOf(elements(await ManagementActivityPage({ searchParams: Promise.resolve({ kind: "x" }) }))).props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("Unknown activity kind");
  });

  it("shows a generic message for any other failure", async () => {
    route(() => Promise.reject(new ApiError("boom", 500)));
    render(<>{shellOf(elements(await ManagementActivityPage({ searchParams: Promise.resolve({}) }))).props.children}</>);
    expect(screen.getByRole("alert").textContent).toBe("Management activity is unavailable right now. Please try again.");
  });

  it("shows the access card on a 403", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") throw new ApiError("Management access required", 403);
      return { id: "x", role: "it_admin", division: "it", full_name: "IT" } as never;
    });
    render(await ManagementActivityPage({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
  });
});
