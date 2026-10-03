import { beforeEach, describe, expect, it, vi } from "vitest";

import PortalShell from "@/components/PortalShell";
import TripActions from "@/components/TripActions";
import TripDecision from "@/components/TripDecision";
import TripExpenses from "@/components/TripExpenses";
import TripForm from "@/components/TripForm";
import TripRemarks from "@/components/TripRemarks";
import TripTable from "@/components/TripTable";
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

  it("the detail shows the editor only while the trip is editable, and the rejection reason", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/trips/t1": trip({ can_edit: true, approval_status: "rejected", rejection_reason: "Too costly" }) });
    const tree = elements(await TripDetail(route("t1")));
    expect(tree.some((el) => el.type === TripForm)).toBe(true);
    expect(tree.some((el) => el.type === TripActions)).toBe(true);
    expect(tree.some((el) => el.type === TripExpenses)).toBe(true);
    expect(tree.some((el) => el.type === TripRemarks)).toBe(true);
    expect(allText(tree)).toContain("Too costly");
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/trips/t1": trip({ approval_status: "approved" }) });
    expect(elements(await TripDetail(route("t1"))).some((el) => el.type === TripForm)).toBe(false);
  });

  it("a trip that is not yours shows the access card", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/trips/zz": new ApiError("Trip not found", 404) });
    const tree = elements(await TripDetail(route("zz")));
    const card = tree.find((el) => typeof el.props.message === "string")!;
    expect(card.props.message).toBe("Trip not found");
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

  it("the manager's trip view is read-only with the decision panel", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Meera", role: "bdm_manager" }, "/api/v1/bdm/manager/trips/t1": trip({ can_decide: true }) });
    const tree = elements(await ManagerTrip(route("t1")));
    expect(tree.some((el) => el.type === TripDecision)).toBe(true);
    expect(tree.some((el) => el.type === TripForm || el.type === TripActions || el.type === TripRemarks)).toBe(false);
  });

  it("a super_admin's trip view uses the admin navigation", async () => {
    answer({ "/api/v1/auth/me": { full_name: "Root", role: "super_admin" }, "/api/v1/bdm/manager/trips/t1": trip() });
    const shell = elements(await ManagerTrip(route("t1"))).find((el) => el.type === PortalShell)!;
    expect(shell.props.nav).toBe(SUPER_ADMIN_NAV);
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
