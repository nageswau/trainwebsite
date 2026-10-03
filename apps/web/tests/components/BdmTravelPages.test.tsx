import { beforeEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import TripForm from "@/components/TripForm";
import TripTable from "@/components/TripTable";
import TripWorkspace from "@/components/TripWorkspace";
import AdminApprovals from "@/app/admin/bdm-travel-approvals/page";
import ManagerApprovals from "@/app/bdm/manager/approvals/page";
import ManagerTrip from "@/app/bdm/manager/trips/[id]/page";
import TripDetail from "@/app/bdm/travel/[id]/page";
import NewTrip from "@/app/bdm/travel/new/page";
import MyTrips from "@/app/bdm/travel/page";
import { ApiError, serverApi } from "@/lib/api";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements, text } from "@/tests/helpers/elementTree";

import { row, trip } from "./tripFixtures";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const me = {
  id: "b1", full_name: "Asha", email: "a@x.local", phone: null, active: true, division: "it",
  bdm_profile: { bdm_type: "college", employee_id: "E-1", designation: null, department: null, territory: null, reporting_manager: { id: "m1", full_name: "Meera", active: true } },
};
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 50, offset });
const allText = (tree: ReturnType<typeof elements>) => tree.map((el) => text(el)).join(" ");
const hrefs = (tree: ReturnType<typeof elements>) => tree.map((el) => el.props.href).filter((h): h is string => typeof h === "string");
const params = (p: Record<string, string> = {}) => ({ searchParams: Promise.resolve(p) });
const route = (id: string) => ({ params: Promise.resolve({ id }) });
const UUID = "9184f803-d155-4ec1-8008-8d65ff92412d";
const UUID2 = "57520286-b155-4737-af41-79d81aa0d50b";

function answer(byPath: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    const key = Object.keys(byPath).find((k) => path.startsWith(k));
    if (!key) throw new Error(`unexpected ${path}`);
    const value = byPath[key];
    if (value instanceof Error) throw value;
    return value as never;
  });
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset(); // a block body: a returned function would run as a cleanup hook
});

describe("bdm-010 BDM travel pages", () => {
  it("the list says what to do when there are no trips", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/trips": page([]) });
    const tree = elements(await MyTrips(params()));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/trips?limit=50&offset=0");
    expect(allText(tree)).toContain("No trips yet");
    expect(hrefs(tree)).toContain("/bdm/travel/new");
    expect(tree.some((el) => el.type === TripTable)).toBe(false);
  });

  it("the list passes a valid filter, ignores a junk one, and renders the table", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/trips": page([row()]) });
    const tree = elements(await MyTrips(params({ approval_status: "submitted", offset: "x" })));
    expect(serverApi).toHaveBeenCalledWith("/api/v1/bdm/trips?limit=50&offset=0&approval_status=submitted");
    const table = tree.find((el) => el.type === TripTable)!;
    expect(table.props.query).toBe("approval_status=submitted");
    await MyTrips(params({ approval_status: "nope" }));
    expect(serverApi).toHaveBeenLastCalledWith("/api/v1/bdm/trips?limit=50&offset=0");
  });

  it("a filter with no match offers to clear it", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/trips": page([]) });
    const tree = elements(await MyTrips(params({ approval_status: "rejected" })));
    expect(allText(tree)).toContain("No trips match this filter");
    expect(hrefs(tree)).toContain("/bdm/travel");
  });

  it("the new-trip page renders the form with India's date", async () => {
    answer({ "/api/v1/bdm/me": me });
    const tree = elements(await NewTrip());
    expect(tree.find((el) => el.type === TripForm)!.props.today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("the detail hands the trip to the owner workspace (QA10-16), with India's date", async () => {
    const t = trip({ can_edit: true });
    answer({ "/api/v1/bdm/me": me, [`/api/v1/bdm/trips/${UUID}`]: t });
    const ws = elements(await TripDetail(route(UUID))).find((el) => el.type === TripWorkspace)!;
    expect(ws.props.initialTrip).toEqual(t);
    expect(ws.props.view).toBe("owner");
    expect(ws.props.today).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(ws.props.backHref).toBe("/bdm/travel");
  });

  it("QA10-04: a malformed trip link is 'Trip not found', without asking the API", async () => {
    answer({ "/api/v1/bdm/me": me });
    for (const page of [await TripDetail(route("not-a-uuid")), await ManagerTrip(route("TRV-000001"))]) {
      const card = elements(page).find((el) => typeof el.props.message === "string")!;
      expect(card.props.message).toBe("Trip not found");
    }
    expect(vi.mocked(serverApi).mock.calls.map((c) => c[0]).some((p) => p.includes("/trips/"))).toBe(false);
  });

  it("a trip that is not yours shows the access card", async () => {
    answer({ "/api/v1/bdm/me": me, [`/api/v1/bdm/trips/${UUID2}`]: new ApiError("Trip not found", 404) });
    const tree = elements(await TripDetail(route(UUID2)));
    const card = tree.find((el) => typeof el.props.message === "string")!;
    expect(card.props.message).toBe("Trip not found");
  });
});

describe("bdm-010 review fixes", () => {
  it("I2: a server error offers Retry on the same page; a 404 still shows the access card", async () => {
    answer({ "/api/v1/bdm/me": me, [`/api/v1/bdm/trips/${UUID}`]: new ApiError("Internal Server Error", 500) });
    const tree = elements(await TripDetail(route(UUID)));
    expect(hrefs(tree)).toContain(`/bdm/travel/${UUID}`);
    expect(allText(tree)).toContain("Retry");
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/bdm/manager/approvals": new TypeError("fetch failed") });
    expect(hrefs(elements(await ManagerApprovals(params())))).toContain("/bdm/manager/approvals");
  });

});

describe("bdm-010 approval pages", () => {
  it("the manager queue has an empty state", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/bdm/manager/approvals": page([]) });
    const tree = elements(await ManagerApprovals(params()));
    expect(allText(tree)).toContain("Nothing waiting for approval");
  });

  it("the manager queue lists trips with the BDM column, linking to the manager's trip view", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/bdm/manager/approvals": page([row()]) });
    const table = elements(await ManagerApprovals(params())).find((el) => el.type === TripTable)!;
    expect(table.props.showBdm).toBe(true);
    expect((table.props.detailHref as (id: string) => string)("t1")).toBe("/bdm/manager/trips/t1");
  });

  it("the manager's trip view is the read-only workspace", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, [`/api/v1/bdm/manager/trips/${UUID}`]: trip({ can_decide: true }) });
    const ws = elements(await ManagerTrip(route(UUID))).find((el) => el.type === TripWorkspace)!;
    expect([ws.props.view, ws.props.backHref, ws.props.note]).toEqual(["manager", "/bdm/manager/approvals", undefined]);
  });

  it("QA10-13: a super_admin keeps the admin navigation and is told why they can't decide while the manager is active", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Root", role: "super_admin" }, [`/api/v1/bdm/manager/trips/${UUID}`]: trip({ approval_status: "submitted" }) });
    const tree = elements(await ManagerTrip(route(UUID)));
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
    const ws = tree.find((el) => el.type === TripWorkspace)!;
    expect(ws.props.backHref).toBe("/admin/bdm-travel-approvals");
    expect(ws.props.note).toBe("This BDM's reporting manager is active and decides this trip. A Super Administrator can decide only while that manager is inactive.");
  });

  it("the admin fallback page is for super_admins only", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Ivy", role: "it_admin" } });
    const denied = elements(await AdminApprovals(params()));
    expect(denied.find((el) => typeof el.props.message === "string")!.props.message).toBe("Super Administrator role required");
    answer({ "/api/v1/auth/me": { full_name: "Root", role: "super_admin" }, "/api/v1/bdm/manager/approvals": page([]) });
    const tree = elements(await AdminApprovals(params()));
    expect(tree.find((el) => el.type === PortalShell)!.props.nav).toBe(SUPER_ADMIN_NAV);
    expect(allText(tree)).toContain("No trips are waiting on an inactive manager");
  });
});
