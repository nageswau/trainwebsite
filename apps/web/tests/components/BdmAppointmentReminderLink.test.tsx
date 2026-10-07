import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AppointmentPage from "@/app/bdm/appointments/[id]/page";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import { serverApi } from "@/lib/api";
import { type Appointment, reminderAction } from "@/lib/bdmAppointments";
import { elements } from "@/tests/helpers/elementTree";

// bdm-012 (DEC-SCOPE-102 R10, AC6): a reminder's button opens the appointment with ?action=. Reschedule / Cancel open their form;
// Confirm only focuses its button (a link never changes data); an action that is no longer possible says so. The query is dropped.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));
vi.mock("@/lib/bdmNav", () => ({ bdmNav: async () => [] }));

const none = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false, can_edit_report: false };
const open = { ...none, can_edit: true, can_confirm: true, can_reschedule: true, can_cancel: true };
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", contact_id: "c1", bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: null, contact_phone: null, contact_email: null, location: null, purpose: null, remarks: null, outcome: null, next_follow_up_on: null, outcome_pending: false, report: null, follow_up: null,
  expected_leads: null, expected_revenue: null, events: [], created_at: "", updated_at: "", permissions: open, ...over,
}) as Appointment;
const show = (action: "confirm" | "reschedule" | "cancel", over: Partial<Appointment> = {}) =>
  render(<BdmAppointmentDetail initial={appt(over)} basePath="/bdm/appointments" bdmType="college" action={action} />);
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("reminder deep links on the appointment page (bdm-012)", () => {
  it("accepts only the three reminder actions", () => {
    expect(["confirm", "reschedule", "cancel"].map(reminderAction)).toEqual(["confirm", "reschedule", "cancel"]);
    expect([undefined, "", "complete", "no-show", "CONFIRM", ["cancel"]].map((v) => reminderAction(v as never))).toEqual([null, null, null, null, null, null]);
  });

  it("the page passes a known action to the detail and ignores anything else", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) =>
      (path === "/api/v1/bdm/me" ? { full_name: "Asha", bdm_profile: { bdm_type: "college" } } : path.startsWith("/api/v1/bdm/trips") ? { items: [] } : { appointment: appt() }) as never);
    const detail = async (action: string) => elements(await AppointmentPage({ params: Promise.resolve({ id: "a1" }), searchParams: Promise.resolve({ action }) })).find((el) => el.type === BdmAppointmentDetail)!;
    expect((await detail("cancel")).props.action).toBe("cancel");
    expect((await detail("delete")).props.action).toBeNull();
  });

  it("?action=reschedule opens the reschedule form with its date field focused", () => {
    show("reschedule");
    expect(screen.getByRole("button", { name: "Reschedule" })).toHaveAttribute("aria-expanded", "true");
    expect(document.activeElement).toBe(document.getElementById("resched-a1"));
  });

  it("?action=cancel opens the cancel form; nothing is sent until it is submitted", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    show("cancel");
    expect(screen.getByRole("button", { name: "Cancel appointment" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("button", { name: "Yes, cancel it" })).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("?action=confirm focuses Confirm and explains, without confirming", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    show("confirm");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Confirm" })));
    expect(screen.getByRole("status")).toHaveTextContent("Check the details, then select Confirm.");
    expect(fetchMock).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("an action that is no longer possible says why and opens nothing", () => {
    show("reschedule", { status: "cancelled", permissions: none });
    expect(screen.getByRole("status")).toHaveTextContent("This appointment is Cancelled, so it can no longer be rescheduled.");
    show("confirm", { status: "confirmed", permissions: { ...open, can_confirm: false } });
    expect(screen.getAllByRole("status")[1]).toHaveTextContent("This appointment is already confirmed.");
  });

  it("drops ?action from the address so a refresh does not reopen the form", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    show("cancel");
    expect(replace).toHaveBeenCalledWith(null, "", "/bdm/appointments/a1");
  });
});
