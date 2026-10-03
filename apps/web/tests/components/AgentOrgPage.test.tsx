import { beforeEach, describe, expect, it, vi } from "vitest";

import AgentOrgPage from "@/app/overseas/admin/agent-network/[orgId]/page";
import AgentOrgDetailPanel from "@/components/AgentOrgDetailPanel";
import { serverApi } from "@/lib/api";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("next/navigation", async (importOriginal) => ({
  ...(await importOriginal<typeof import("next/navigation")>()),
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));

const ID = "3f2b8c1e-9d4a-4b7e-8f21-0c6d5e4a3b2f";
const user = (role: string) => ({ id: "u", role, full_name: "Oz", division: "overseas", email: "o@x", profile: {} });
const params = (orgId: string) => ({ params: Promise.resolve({ orgId }) });

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("Agent network organisation page (AGN-022)", () => {
  it("renders not-found for an id that is not a UUID, without calling the API (AC11)", async () => {
    await expect(AgentOrgPage(params("..%2Fagents"))).rejects.toThrow("NEXT_NOT_FOUND");
    expect(serverApi).not.toHaveBeenCalled();
  });

  it("lets Overseas Admin act and keeps Super Admin read-only (N3)", async () => {
    vi.mocked(serverApi).mockResolvedValue(user("overseas_admin"));
    let tree = elements(await AgentOrgPage(params(ID)));
    expect(tree.find((el) => el.type === AgentOrgDetailPanel)!.props).toMatchObject({ orgId: ID, canAct: true });
    vi.mocked(serverApi).mockResolvedValue(user("super_admin"));
    tree = elements(await AgentOrgPage(params(ID)));
    expect(tree.find((el) => el.type === AgentOrgDetailPanel)!.props.canAct).toBe(false);
  });

  it("refuses every other role before rendering the panel", async () => {
    vi.mocked(serverApi).mockResolvedValue(user("agent"));
    const tree = elements(await AgentOrgPage(params(ID)));
    expect(tree.some((el) => el.type === AgentOrgDetailPanel)).toBe(false);
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("Overseas Administrator role required");
  });
});
