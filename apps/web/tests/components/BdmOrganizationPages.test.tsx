import { beforeEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationDetail from "@/components/BdmOrganizationDetail";
import BdmOrganizationsPanel from "@/components/BdmOrganizationsPanel";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import ManagerOrganization from "@/app/bdm/manager/organizations/[id]/page";
import ManagerOrganizations from "@/app/bdm/manager/organizations/page";
import BdmOrganization from "@/app/bdm/organizations/[id]/page";
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

// The pages also read the unread badge (bdm-010 QA10-01), so call order is not fixed: refusals are answered by path. `first` is the
// page's own refusal; every other call (the badge read, the session look-up) gets `rest`.
function refuse(path: string, first: ApiError, rest = new ApiError("x", 401)) {
  vi.mocked(serverApi).mockImplementation(async (p: string) => {
    throw p === path ? first : rest;
  });
}

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
    refuse("/api/v1/bdm/me", new ApiError("BDM profile not set up — contact your administrator", 403));
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
    refuse("/api/v1/auth/me", new ApiError("Not authenticated", 401));
    tree = elements(await ManagerOrganizations());
    expect(card(tree)!.props.loginHref).toBe("/admin/login");
  });
});

describe("bdm-002 organization detail pages", () => {
  const organization = { id: "o1", code: "ORG-000001", name: "St Mary" };
  const params = (id = "o1") => Promise.resolve({ id });
  const noQuery = Promise.resolve({});

  it("the BDM detail page renders the organization, and announces a just-created one", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/bdm/me" ? me : { organization }) as never);
    const tree = elements(await BdmOrganization({ params: params(), searchParams: Promise.resolve({ created: "1" }) }));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1");
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props).toEqual({ initial: organization, basePath: "/bdm/organizations", created: true, activities: null, leads: null, stageHistory: null, tasks: null, mou: null, schoolActivity: null, agentPerformance: null });
  });

  it("bdm-005: both detail pages read the MoU card alongside the organization", async () => {
    const id = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b";
    const orgMou = { current: null, can_start: true };
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") return me as never;
      if (path === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" } as never;
      if (path === `/api/v1/bdm/organizations/${id}/mou`) return orgMou as never;
      if (path === `/api/v1/bdm/organizations/${id}`) return { organization } as never;
      throw new ApiError("x", 500);
    });
    let tree = elements(await BdmOrganization({ params: params(id), searchParams: noQuery }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.mou).toEqual(orgMou);
    tree = elements(await ManagerOrganization({ params: params(id) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.mou).toEqual(orgMou);
  });

  it("bdm-020: both detail pages read the School activity panel alongside the organization", async () => {
    const id = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b";
    const activity = { linked: false, school: null, total_students: null, metrics: [] };
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") return me as never;
      if (path === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" } as never;
      if (path === `/api/v1/bdm/organizations/${id}/school-activity`) return activity as never;
      if (path === `/api/v1/bdm/organizations/${id}`) return { organization } as never;
      throw new ApiError("x", 500);
    });
    let tree = elements(await BdmOrganization({ params: params(id), searchParams: noQuery }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.schoolActivity).toEqual(activity);
    tree = elements(await ManagerOrganization({ params: params(id) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.schoolActivity).toEqual(activity);
  });

  it("bdm-022: both detail pages read the Agent performance panel alongside the organization", async () => {
    const id = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b";
    const figures = { organization_id: id, linked: false, agency: null, steps: [], applications_by_stage: [], visa_applications: null, as_of: "2026-10-07T10:00:00Z" };
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") return me as never;
      if (path === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" } as never;
      if (path === `/api/v1/bdm/organizations/${id}/agent-performance`) return figures as never;
      if (path === `/api/v1/bdm/organizations/${id}`) return { organization } as never;
      throw new ApiError("x", 500);
    });
    let tree = elements(await BdmOrganization({ params: params(id), searchParams: noQuery }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.agentPerformance).toEqual(figures);
    tree = elements(await ManagerOrganization({ params: params(id) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.agentPerformance).toEqual(figures);
  });

  it("bdm-021: both detail pages pass the business figures for a College organization only", async () => {
    const id = "6f1d2c3b-4a5e-4f60-8a7b-9c0d1e2f3a4b";
    const figures = { organization_id: id, currency: "INR", funnel: [], revenue: null };
    let shown = { ...organization, bdm_type: "college" };
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") return me as never;
      if (path === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" } as never;
      if (path === `/api/v1/bdm/organizations/${id}/business`) return figures as never;
      if (path === `/api/v1/bdm/organizations/${id}`) return { organization: shown } as never;
      throw new ApiError("x", 500);
    });
    let tree = elements(await BdmOrganization({ params: params(id), searchParams: noQuery }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.business).toEqual(figures);
    tree = elements(await ManagerOrganization({ params: params(id) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.business).toEqual(figures);
    shown = { ...organization, bdm_type: "school" };
    tree = elements(await ManagerOrganization({ params: params(id) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.business).toBeUndefined();
  });

  it("an unknown or out-of-scope organization is a plain not-found with a way back", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/bdm/me") return me as never;
      throw new ApiError("Organization not found", 404);
    });
    const tree = elements(await BdmOrganization({ params: params("zzz"), searchParams: noQuery }));
    expect(allText(tree)).toContain("Organization not found");
    expect(tree.some((el) => el.props.href === "/bdm/organizations")).toBe(true);
    expect(tree.some((el) => el.type === BdmOrganizationDetail)).toBe(false);
  });

  it("a refused BDM detail page goes to the chooser; the manager detail page uses the manager list and /admin/login", async () => {
    refuse("/api/v1/bdm/me", new ApiError("BDM role required", 403));
    let tree = elements(await BdmOrganization({ params: params(), searchParams: noQuery }));
    expect(card(tree)!.props.loginHref).toBe("/bdm/sign-in");
    vi.mocked(serverApi).mockReset();
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? { id: "m1", full_name: "Meera", role: "bdm_manager" } : { organization }) as never);
    tree = elements(await ManagerOrganization({ params: params() }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props).toEqual({ initial: organization, basePath: "/bdm/manager/organizations", activities: null, leads: null, stageHistory: null, tasks: null, mou: null, schoolActivity: null, agentPerformance: null });
    vi.mocked(serverApi).mockReset();
    refuse("/api/v1/auth/me", new ApiError("Not authenticated", 401));
    tree = elements(await ManagerOrganization({ params: params() }));
    expect(card(tree)!.props.loginHref).toBe("/admin/login");
  });

  it("bdm-009: passes the first activity page, or null when only that call fails", async () => {
    const id = "00000000-0000-4000-8000-000000000001";
    const org = { id, code: "ORG-000001", name: "St Mary" };
    const activities = { items: [], total: 0, limit: 20, offset: 0 };
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me as never;
      if (p === `/api/v1/bdm/organizations/${id}`) return { organization: org } as never;
      if (p.startsWith(`/api/v1/bdm/organizations/${id}/activities`)) return activities as never;
      throw new ApiError("x", 401);
    });
    let tree = elements(await BdmOrganization({ params: Promise.resolve({ id }), searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.activities).toEqual(activities);
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me as never;
      if (p === `/api/v1/bdm/organizations/${id}`) return { organization: org } as never;
      throw new ApiError("boom", 500);
    });
    tree = elements(await BdmOrganization({ params: Promise.resolve({ id }), searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props.activities).toBeNull();
  });

  it("bdm-017: passes the first lead page on both profiles, or null when only that call fails", async () => {
    const id = "00000000-0000-4000-8000-000000000002";
    const org = { id, code: "ORG-000002", name: "Govt College" };
    const leads = { items: [], total: 3, limit: 20, offset: 0 };
    vi.mocked(serverApi).mockImplementation(async (p: string) => {
      if (p === "/api/v1/bdm/me") return me as never;
      if (p === "/api/v1/auth/me") return { id: "m1", full_name: "Meera", role: "bdm_manager" } as never;
      if (p === `/api/v1/bdm/organizations/${id}`) return { organization: org } as never;
      if (p === `/api/v1/bdm/organizations/${id}/leads?limit=20&offset=0`) return leads as never;
      throw new ApiError("boom", 500);
    });
    let tree = elements(await BdmOrganization({ params: Promise.resolve({ id }), searchParams: Promise.resolve({}) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props).toMatchObject({ leads, activities: null });
    tree = elements(await ManagerOrganization({ params: Promise.resolve({ id }) }));
    expect(tree.find((el) => el.type === BdmOrganizationDetail)!.props).toMatchObject({ leads, activities: null });
  });
});
