import { beforeEach, describe, expect, it, vi } from "vitest";

import AppointmentPage from "@/app/bdm/appointments/[id]/page";
import NewAppointmentPage from "@/app/bdm/appointments/new/page";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import { ApiError, serverApi } from "@/lib/api";
import { elements } from "@/tests/helpers/elementTree";

import { row } from "./tripFixtures";

// bdm-011: the appointment pages read the BDM's open trips once, beside their own data, and hand them to the form.
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/lib/bdmNav", () => ({ bdmNav: async () => [] }));

const me = { id: "b1", full_name: "Asha", bdm_profile: { bdm_type: "college" } };
const LINKABLE = "/api/v1/bdm/trips?linkable=true&limit=100";
const trips = [row()];

function answer(byPath: Record<string, unknown>) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (!(path in byPath)) throw new Error(`unexpected ${path}`);
    const value = byPath[path];
    if (value instanceof Error) throw value;
    return value as never;
  });
}

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("appointment pages read the trip choices (bdm-011)", () => {
  it("booking passes the open trips to the form", async () => {
    answer({ "/api/v1/bdm/me": me, [LINKABLE]: { items: trips, total: 1, limit: 100, offset: 0 } });
    const form = elements(await NewAppointmentPage({ searchParams: Promise.resolve({}) })).find((el) => el.type === BdmAppointmentForm)!;
    expect(form.props).toMatchObject({ trips, tripsUnavailable: false });
  });

  it("a failed trip read never blocks booking: the form says the trips couldn't be loaded", async () => {
    answer({ "/api/v1/bdm/me": me, [LINKABLE]: new ApiError("Internal Server Error", 500) });
    const form = elements(await NewAppointmentPage({ searchParams: Promise.resolve({}) })).find((el) => el.type === BdmAppointmentForm)!;
    expect(form.props).toMatchObject({ trips: [], tripsUnavailable: true });
  });

  it("the appointment page passes them to the editor", async () => {
    answer({ "/api/v1/bdm/me": me, "/api/v1/bdm/appointments/a1": { appointment: { id: "a1" } }, [LINKABLE]: { items: trips, total: 1, limit: 100, offset: 0 } });
    const detail = elements(await AppointmentPage({ params: Promise.resolve({ id: "a1" }), searchParams: Promise.resolve({}) })).find((el) => el.type === BdmAppointmentDetail)!;
    expect(detail.props).toMatchObject({ trips, tripsUnavailable: false });
  });
});
