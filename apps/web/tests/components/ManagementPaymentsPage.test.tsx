import { beforeEach, describe, expect, it, vi } from "vitest";

import ManagementPaymentsPage from "@/app/management/payments/page";
import PortalSection from "@/components/PortalSection";
import PortalShell from "@/components/PortalShell";
import WorkflowPanel from "@/components/WorkflowPanel";
import { ApiError, serverApi } from "@/lib/api";
import { managementNavFor, type ManagementMe } from "@/lib/management";
import type { PortalPayload, User } from "@/lib/types";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/payments" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

// nehn-021 (DEC-SCOPE-309 D4/D6): the finance roles' Payments page -- the payments list (payments.view) and the discount form.
const accountantMe: ManagementMe = { id: "a1", full_name: "Ravi Accountant", role: "accountant", tiers: { operational: false, finance: true, partner_only: false } };
const accountant = { id: "a1", full_name: "Ravi Accountant", role: "accountant", division: "global" } as unknown as User;
const PAYMENT = { id: "p1", student: "Asha", division: "overseas", type: "enrollment_fee", amount: 50000, currency: "INR", status: "pending" };

function api(payments: () => unknown) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/management/me") return accountantMe as never;
    if (path === "/api/v1/auth/me") return accountant as never;
    return payments() as never;
  });
}

const section = (tree: unknown) => elements(tree as never).find((el) => el.type === PortalSection)!.props as { data: PortalPayload; table: boolean };

describe("nehn-021 ManagementPaymentsPage", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });

  it("lists every payment the API returns, in the management sidebar, with the discount form for the signed-in user", async () => {
    api(() => [PAYMENT]);
    const tree = await ManagementPaymentsPage();
    expect(vi.mocked(serverApi)).toHaveBeenCalledWith("/api/v1/admin/payments");
    expect((elements(tree).find((el) => el.type === PortalShell)!.props as { nav: unknown }).nav).toEqual(managementNavFor(accountantMe.tiers));
    expect(section(tree).data.rows).toEqual([PAYMENT]);
    expect(section(tree).table).toBe(true);
    expect(elements(tree).find((el) => el.type === WorkflowPanel)!.props).toMatchObject({ user: accountant, section: "payments" });
  });

  it("replaces the table with a grant hint on 403, and a retry notice on any other failure", async () => {
    api(() => { throw new ApiError("Admin role required", 403); });
    let view = section(await ManagementPaymentsPage());
    expect(view.table).toBe(false);
    expect(view.data.panels[0].items[0]).toMatch(/permission to view payments/);
    api(() => { throw new ApiError("boom", 500); });
    view = section(await ManagementPaymentsPage());
    expect(view.data.panels[0].items[0]).toBe("Payments are unavailable right now. Please try again.");
  });

  it("shows the access card when the caller is not a management role", async () => {
    vi.mocked(serverApi).mockRejectedValue(new ApiError("Management access required", 403));
    const tree = await ManagementPaymentsPage();
    expect(elements(tree).some((el) => el.type === PortalShell)).toBe(false);
  });
});
