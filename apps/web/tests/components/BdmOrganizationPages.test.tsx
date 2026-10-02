import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationsPanel from "@/components/BdmOrganizationsPanel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import ManagerOrganizations from "@/app/bdm/manager/organizations/page";
import BdmOrganizations from "@/app/bdm/organizations/page";
import { elements, text } from "@/tests/helpers/elementTree";

// bdm-002 (spec §6.1): the organization pages. Only serverApi is replaced; the real ApiError stays (accessUnavailable reads it).
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "overseas",
  bdm_profile: { bdm_type: "school", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");
const card = (tree: ReturnType<typeof elements>) => tree.find((el) => typeof el.props.message === "string");

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("bdm-002 organization list pages", () => {
  it("the BDM page is gated by /bdm/me and lists the module's organizations", async () => {
    vi.mocked(serverApi).mockResolvedValue(me);
    const tree = elements(await BdmOrganizations());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/me");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("School BDM");
    const panel = tree.find((el) => el.type === BdmOrganizationsPanel)!;
    expect(panel.props).toEqual({ basePath: "/bdm/organizations", isBdm: true });
    expect(allText(tree)).toContain("School organizations");
  });

  it("a refused BDM page links to the BDM sign-in chooser", async () => {
    vi.mocked(serverApi).mockRejectedValueOnce(new ApiError("BDM profile not set up — contact your administrator", 403)).mockRejectedValueOnce(new ApiError("x", 401));
    const tree = elements(await BdmOrganizations());
    expect(card(tree)!.props.message).toBe("BDM profile not set up — contact your administrator");
    expect(card(tree)!.props.loginHref).toBe("/bdm/sign-in");
  });

  it("the manager page lists the team's organizations without create", async () => {
    vi.mocked(serverApi).mockResolvedValue({ id: "m1", full_name: "Meera", role: "bdm_manager" });
    const tree = elements(await ManagerOrganizations());
    expect(serverApi).toHaveBeenCalledWith("/api/v1/auth/me");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("BDM Manager");
    expect(tree.find((el) => el.type === BdmOrganizationsPanel)!.props).toEqual({ basePath: "/bdm/manager/organizations", isBdm: false });
  });

  it("the manager page refuses a BDM and signs a refused manager in at /admin/login", async () => {
    vi.mocked(serverApi).mockResolvedValue({ id: "b1", full_name: "Asha", role: "bdm" });
    let tree = elements(await ManagerOrganizations());
    expect(card(tree)!.props.message).toBe("This page is for BDM managers.");
    expect(tree.some((el) => el.type === BdmOrganizationsPanel)).toBe(false);
    vi.mocked(serverApi).mockReset();
    vi.mocked(serverApi).mockRejectedValueOnce(new ApiError("Not authenticated", 401));
    tree = elements(await ManagerOrganizations());
    expect(card(tree)!.props.loginHref).toBe("/admin/login");
  });
});
