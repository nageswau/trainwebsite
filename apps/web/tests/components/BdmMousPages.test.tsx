import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import BdmMousPanel from "@/components/BdmMousPanel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import ManagerMous from "@/app/bdm/manager/mous/page";
import BdmMous from "@/app/bdm/mous/page";
import { elements, text } from "@/tests/helpers/elementTree";
import { mou } from "./BdmMouFixtures";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const page = <T,>(items: T[], over: Record<string, number> = {}) => ({ items, total: items.length, limit: 50, offset: 0, ...over });
const row = mou("signed", { signed_on: "2026-01-10", valid_until: "2027-01-09", has_document: true });

beforeEach(() => {
  vi.mocked(serverApi).mockReset(); // braces: a returned function would run as teardown
});
afterEach(cleanup);

describe("BdmMousPanel (bdm-005 §8)", () => {
  it("links each row to its organization and marks the document", () => {
    render(<BdmMousPanel page={page([row])} status={null} path="/bdm/mous" orgBasePath="/bdm/organizations" />);
    const table = screen.getByRole("region", { name: "MoUs" });
    expect(within(table).getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/organizations/o1");
    expect(within(table).getByText("Signed")).toBeInTheDocument();
    expect(within(table).getByText("Yes")).toBeInTheDocument();
  });

  it("filters by status with plain links, the chosen one marked", () => {
    render(<BdmMousPanel page={page([row])} status="expired" path="/bdm/mous" orgBasePath="/bdm/organizations" />);
    const filters = screen.getByRole("navigation", { name: "Filter by status" });
    const links = within(filters).getAllByRole("link");
    expect(links.map((a) => a.textContent)).toEqual(["All", "Prospect", "Discussion Started", "Proposal Sent", "Under Negotiation", "Draft Shared", "Signed", "Active", "Expired", "Rejected"]);
    expect(within(filters).getByRole("link", { name: "Expired" })).toHaveAttribute("aria-current", "true");
    expect(within(filters).getByRole("link", { name: "Expired" })).toHaveAttribute("href", "/bdm/mous?status=expired");
    expect(within(filters).getByRole("link", { name: "All" })).toHaveAttribute("href", "/bdm/mous");
  });

  it("says what is empty for the chosen filter", () => {
    render(<BdmMousPanel page={page([])} status={null} path="/bdm/mous" orgBasePath="/bdm/organizations" />);
    expect(screen.getByRole("status")).toHaveTextContent("No MoUs yet.");
    cleanup();
    render(<BdmMousPanel page={page([])} status="proposal_sent" path="/bdm/mous" orgBasePath="/bdm/organizations" />);
    expect(screen.getByRole("status")).toHaveTextContent("No MoUs at Proposal Sent.");
  });

  it("pages with plain links that keep the filter", () => {
    render(<BdmMousPanel page={page([row], { total: 120, offset: 50 })} status="active" path="/bdm/mous" orgBasePath="/bdm/organizations" />);
    const pager = screen.getByRole("navigation", { name: "MoU pages" });
    expect(within(pager).getByRole("link", { name: "Previous" })).toHaveAttribute("href", "/bdm/mous?status=active");
    expect(within(pager).getByRole("link", { name: "Next" })).toHaveAttribute("href", "/bdm/mous?status=active&offset=100");
  });
});

describe("bdm-005 MoU pages", () => {
  it("the BDM page is gated by /bdm/me and reads the scoped list with the filter", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/bdm/me" ? me : page([row])) as never);
    const tree = elements(await BdmMous({ searchParams: Promise.resolve({ status: "signed" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/mous?status=signed&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    expect(tree.find((el) => el.type === BdmMousPanel)!.props).toMatchObject({ status: "signed", path: "/bdm/mous", orgBasePath: "/bdm/organizations" });
  });

  it("an unknown filter offers a reset instead of an error", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") return me as never;
      throw new ApiError("bad", 422);
    });
    const tree = elements(await BdmMous({ searchParams: Promise.resolve({ status: "bogus" }) }));
    expect(tree.map((el) => text(el)).join(" ")).toContain("That filter isn't valid.");
    expect(tree.some((el) => el.props.href === "/bdm/mous")).toBe(true);
  });

  it("the manager page is for managers and super_admin, and links to the manager organization view", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { id: "m1", full_name: "Meera", role: "bdm_manager" } : page([row])) as never);
    let tree = elements(await ManagerMous({ searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmMousPanel)!.props).toMatchObject({ status: null, path: "/bdm/manager/mous", orgBasePath: "/bdm/manager/organizations" });
    vi.mocked(serverApi).mockReset();
    vi.mocked(serverApi).mockImplementation(async () => ({ id: "s1", full_name: "Stu", role: "student" }) as never);
    tree = elements(await ManagerMous({ searchParams: Promise.resolve({}) }));
    expect(tree.some((el) => el.type === BdmMousPanel)).toBe(false);
  });
});
