import { beforeEach, describe, expect, it, vi } from "vitest";

import AdminBdmPanel from "@/components/AdminBdmPanel";
import AdminBdmPage from "@/components/AdminBdmPage";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const props = { roles: ["it_admin", "super_admin"], nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator", loginHref: "/it/login" };

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("AdminBdmPage (bdm-001)", () => {
  it("renders the panel for an allowed role, passing the role through", async () => {
    vi.mocked(serverApi).mockResolvedValue({ id: "u", role: "it_admin", full_name: "Ira", division: "it", email: "i@x", profile: {} });
    const tree = elements(await AdminBdmPage(props));
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("IT Administrator");
    expect(tree.find((el) => el.type === AdminBdmPanel)!.props.role).toBe("it_admin");
  });

  it("sends a signed-out visitor to this page's own sign-in, not the Overseas one", async () => {
    vi.mocked(serverApi).mockRejectedValue(new ApiError("Not authenticated", 401));
    const tree = elements(await AdminBdmPage({ ...props, loginHref: "/it/login" }));
    expect(tree.find((el) => typeof el.props.message === "string")!.props.loginHref).toBe("/it/login");
  });

  it("refuses any other role before rendering a screen that can only fail", async () => {
    vi.mocked(serverApi).mockResolvedValue({ id: "u", role: "overseas_admin", full_name: "Oz", division: "overseas", email: "o@x", profile: {} });
    const tree = elements(await AdminBdmPage(props));
    expect(tree.some((el) => el.type === AdminBdmPanel)).toBe(false);
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("IT Administrator role required");
  });
});
