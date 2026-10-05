import Link from "next/link";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmPipelineBoard from "@/components/BdmPipelineBoard";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import ManagerPipeline from "@/app/bdm/manager/pipeline/page";
import BdmPipeline from "@/app/bdm/pipeline/page";
import { elements, text } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const view = (over = {}) => ({
  bdm_type: "college", lost_count: 1, total: 1, limit: 50, offset: 0,
  stages: [{ key: "prospect", label: "College Prospect", kind: "manual", count: 3 }, { key: "placement", label: "Placement", kind: "volume", count: null }],
  items: [{ id: "o1", code: "ORG-000001", name: "St Mary", city: "Kochi", org_type: "college", assigned_bdm: { id: "b1", full_name: "Asha", active: true }, stage: "prospect", stage_label: "College Prospect", lost: false }],
  ...over,
});
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");
const sp = (q: Record<string, string> = {}) => Promise.resolve(q);
type BoardProps = { href: (change: { stage?: string | null; offset?: number }) => string; orgBasePath: string; selected: string | null };
const board = (tree: ReturnType<typeof elements>) => ({ props: tree.find((el) => el.type === BdmPipelineBoard)!.props as BoardProps });

beforeEach(() => {
  vi.mocked(serverApi).mockReset(); // braces: a function returned from beforeEach is run as a teardown
});

describe("bdm-004 BDM pipeline page", () => {
  it("defaults to my organizations and keeps the filters in the links", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : view()) as never);
    const tree = elements(await BdmPipeline({ searchParams: sp() }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?assigned=me&limit=50&offset=0");
    expect(tree.find((el) => el.type === PortalShell)!.props.roleLabel).toBe("College BDM");
    const props = board(tree).props;
    expect(props.href({ stage: "lost", offset: 0 })).toBe("/bdm/pipeline?stage=lost");
    expect(props.orgBasePath).toBe("/bdm/organizations");
  });

  it("the All toggle drops the assignee and is kept in the links", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : view()) as never);
    const tree = elements(await BdmPipeline({ searchParams: sp({ scope: "all", stage: "prospect", offset: "50" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?stage=prospect&limit=50&offset=50");
    expect(board(tree).props.href({ offset: 100 })).toBe("/bdm/pipeline?scope=all&stage=prospect&offset=100");
    expect(board(tree).props.selected).toBe("prospect");
  });

  it("Mine / All are plain links that load the page and keep the selected stage (QA4-01, QA4-10)", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => (p === "/api/v1/bdm/me" ? me : view()) as never);
    const tree = elements(await BdmPipeline({ searchParams: sp({ stage: "contacted", offset: "50" }) }));
    const mine = tree.find((el) => text(el) === "Mine" && el.props.href)!;
    const all = tree.find((el) => text(el) === "All in module" && el.props.href)!;
    expect([mine.type, all.type]).toEqual(["a", "a"]);
    expect([mine.props.href, all.props.href]).toEqual(["/bdm/pipeline?stage=contacted", "/bdm/pipeline?scope=all&stage=contacted"]);
  });

  it("an invalid stage in the address shows a reset link", async () => {
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me as never;
      throw new ApiError("Choose a stage of this pipeline", 422);
    });
    const tree = elements(await BdmPipeline({ searchParams: sp({ stage: "<script>" }) }));
    expect(allText(tree)).toContain("That filter isn't valid");
    expect(tree.find((el) => el.props.href === "/bdm/pipeline" && text(el) === "Show my pipeline")!.type).toBe("a");
  });
});

describe("bdm-004 manager pipeline page", () => {
  const team = [{ id: "b2", full_name: "Ravi", bdm_type: "school" }, { id: "b1", full_name: "Asha", bdm_type: "college" }];
  // The team endpoint filtered by `bdm_type` (counts with limit=1, the chosen type's list with limit=100); `totals` overrides a type's
  // total to stand for a team larger than one page. An unfiltered read returns only the first page (school rows) -- the 100-row cap.
  const answer = (user: unknown, totals: Record<string, number> = {}) => vi.mocked(serverApi).mockImplementation(async (p: string) => {
    if (p === "/api/v1/auth/me") return user as never;
    if (p.startsWith("/api/v1/bdm/manager/team")) {
      const type = new URLSearchParams(p.split("?")[1]).get("bdm_type");
      const rows = team.filter((b) => (type ? b.bdm_type === type : b.bdm_type === "school"));
      return { items: rows, total: totals[type ?? ""] ?? rows.length, limit: 100, offset: 0 } as never;
    }
    return view() as never;
  });
  const bdmOptions = (tree: ReturnType<typeof elements>) =>
    tree.filter((el) => el.type === "option" && tree.some((s) => s.props.id === "pipeline-bdm" && elements(s.props.children as never).includes(el))).map((el) => el.props.value);

  it("falls back to the team's first type", async () => {
    answer({ id: "m1", full_name: "Meera", role: "bdm_manager" });
    const tree = elements(await ManagerPipeline({ searchParams: sp({ type: "agent" }) })); // no agent BDMs: first type in Agent, School, College order
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=school&limit=50&offset=0");
    expect(board(tree).props.orgBasePath).toBe("/bdm/manager/organizations");
  });

  it("filters to one BDM of the chosen type and says when the chosen BDM is of another type", async () => {
    answer({ id: "m1", full_name: "Meera", role: "bdm_manager" });
    let tree = elements(await ManagerPipeline({ searchParams: sp({ type: "school", bdm: "b2" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=school&assigned=b2&limit=50&offset=0");
    expect(bdmOptions(tree)).toEqual(["", "b2"]); // only the chosen type's BDMs are offered
    vi.mocked(serverApi).mockClear();
    tree = elements(await ManagerPipeline({ searchParams: sp({ type: "school", bdm: "b1" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=school&limit=50&offset=0");
    expect(allText(tree)).toContain("That BDM isn't a School BDM in your team — showing everyone.");
  });

  it("reaches a type whose BDMs come after the first 100 team rows", async () => {
    answer({ id: "m1", full_name: "Meera", role: "super_admin" }, { school: 150, college: 40 });
    await ManagerPipeline({ searchParams: sp({ type: "college" }) });
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/pipeline?bdm_type=college&limit=50&offset=0");
  });

  it("refuses a BDM and says when no BDMs report to the manager", async () => {
    answer({ id: "b1", full_name: "Asha", role: "bdm" });
    let tree = elements(await ManagerPipeline({ searchParams: sp() }));
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("This page is for BDM managers.");
    vi.mocked(serverApi).mockImplementation(async (p: string) =>
      (p === "/api/v1/auth/me" ? { id: "m1", full_name: "Meera", role: "bdm_manager" } : { items: [], total: 0, limit: 100, offset: 0 }) as never);
    tree = elements(await ManagerPipeline({ searchParams: sp() }));
    expect(allText(tree)).toContain("No BDMs report to you yet");
    expect(tree.some((el) => el.type === BdmPipelineBoard)).toBe(false);
  });
});

describe("bdm-004 pipeline board", () => {
  it("shows counts as links, volume steps as Not tracked, a Lost tile, and the list", () => {
    const tree = elements(BdmPipelineBoard({ view: view() as never, href: ({ stage }) => `/x?stage=${stage}`, orgBasePath: "/bdm/organizations", selected: "prospect", emptyText: "None" }));
    const tiles = tree.filter((el) => el.props.className === "metric" && typeof el.props.href === "string");
    expect(tiles.map((el) => text(el))).toEqual(["College Prospect3", "Lost1"]);
    expect(tiles.find((el) => el.props.href === "/x?stage=prospect")!.props["aria-current"]).toBe("true");
    expect(allText(tree)).toContain("Not tracked");
    expect(tree.some((el) => el.props.href === "/bdm/organizations/o1")).toBe(true);
  });

  it("filter links (tiles, Show all stages, pager) load the page; organization rows stay client links (QA4-01)", () => {
    const tree = elements(BdmPipelineBoard({ view: view({ total: 120, offset: 50 }) as never, href: ({ stage, offset }) => `/x?stage=${stage}&offset=${offset}`, orgBasePath: "/o", selected: "prospect", emptyText: "" }));
    const filters = tree.filter((el) => typeof el.props.href === "string" && el.props.href.startsWith("/x"));
    expect(filters.map((el) => text(el))).toEqual(expect.arrayContaining(["College Prospect3", "Lost1", "Show all stages", "Previous", "Next"]));
    expect(filters.every((el) => el.type === "a")).toBe(true);
    expect(tree.find((el) => el.props.href === "/o/o1")!.type).toBe(Link);
  });

  it("says when a stage is empty", () => {
    const tree = elements(BdmPipelineBoard({ view: view({ items: [], total: 0 }) as never, href: () => "/x", orgBasePath: "/o", selected: null, emptyText: "No organizations at this stage." }));
    expect(allText(tree)).toContain("No organizations at this stage.");
  });
});
