import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentActions from "@/components/BdmAppointmentActions";
import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import BdmAppointmentForm from "@/components/BdmAppointmentForm";
import type { Appointment, AppointmentTrip } from "@/lib/bdmAppointments";
import type { Organization } from "@/lib/bdmOrganizations";

import { row } from "./tripFixtures";

// bdm-011: the trip choice on the appointment form, the Trip row on the detail, and the notice when a reschedule leaves the trip.
const router = vi.hoisted(() => ({ push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => router }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const org = { id: "o1", code: "ORG-000001", name: "St Mary", contacts: [
  { id: "c2", name: "Dr Rao", designation: "Principal", role: "principal", phone: null, email: null, is_primary: true },
] } as unknown as Organization;
const tripRef = (over: Partial<AppointmentTrip> = {}): AppointmentTrip => ({
  id: "t1", code: "TRV-000001", from_place: "Hyderabad", to_place: "Vijayawada", travel_date: "2030-01-07", return_date: "2030-01-08",
  approval_status: "approved", travel_status: "planned", ...over,
});
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", contact_id: "c2", bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: "Principal", contact_phone: null, contact_email: null, location: null, purpose: null, remarks: null, outcome: null, next_follow_up_on: null,
  expected_leads: null, expected_revenue: null, events: [], created_at: "", updated_at: "", report: null, follow_up: null, trip: null,
  permissions: { can_edit: true, can_confirm: true, can_reschedule: true, can_cancel: true, can_no_show: false, can_complete: false, can_edit_report: false }, ...over,
}) as Appointment;
const TRIPS = [
  row({ id: "t1", code: "TRV-000001", travel_date: "2030-01-07", return_date: "2030-01-08" }),
  row({ id: "t2", code: "TRV-000002", travel_date: "2030-02-01", return_date: "2030-02-01", to_place: "Guntur" }),
];
const body = (fetchMock: ReturnType<typeof vi.fn>, n = 0) => JSON.parse(String(((fetchMock.mock.calls[n] as unknown[])[1] as RequestInit).body));
const tripOptions = () => Array.from((screen.getByLabelText("Trip") as HTMLSelectElement).options).map((o) => o.textContent);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  router.push.mockClear();
});

describe("appointment form trip choice (bdm-011 L2)", () => {
  it("offers only the trips covering the chosen IST date, and books with the chosen one", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt() }, 201)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} trips={TRIPS} />);
    expect(screen.getByLabelText("Trip")).toBeDisabled();
    expect(screen.getByText("Choose the date first.")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Date and time (IST) (required)"), { target: { value: "2030-01-08T10:00" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college_meeting" } });
    expect(tripOptions()).toEqual(["No trip", "TRV-000001 · Hyderabad → Vijayawada (07 Jan 2030 – 08 Jan 2030)"]);
    fireEvent.change(screen.getByLabelText("Trip"), { target: { value: "t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(body(fetchMock)).toMatchObject({ trip_id: "t1" });
  });

  it("clears a chosen trip when the date moves outside it, and says when no trip covers the date", () => {
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} trips={TRIPS} />);
    const when = screen.getByLabelText("Date and time (IST) (required)");
    fireEvent.change(when, { target: { value: "2030-01-07T10:00" } });
    fireEvent.change(screen.getByLabelText("Trip"), { target: { value: "t1" } });
    fireEvent.change(when, { target: { value: "2030-03-01T10:00" } });
    expect(screen.getByLabelText("Trip")).toHaveValue("");
    expect(screen.getByText("None of your open trips covers this date.")).toBeInTheDocument();
  });

  it("books without a trip as before", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt() }, 201)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} trips={TRIPS} />);
    fireEvent.change(screen.getByLabelText("Date and time (IST) (required)"), { target: { value: "2030-01-07T10:00" } });
    fireEvent.change(screen.getByLabelText("Type (required)"), { target: { value: "college_meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Book appointment" }));
    await waitFor(() => expect(router.push).toHaveBeenCalled());
    expect(body(fetchMock).trip_id).toBeNull();
  });

  it("an edit sends only a changed trip, keeps a current trip that is no longer open listed, and can unlink", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res({ organization: org }))
      .mockResolvedValueOnce(res({ appointment: appt() }));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    const current = tripRef({ id: "t9", code: "TRV-000009", travel_status: "cancelled" });
    render(<BdmAppointmentForm mode="edit" bdmType="college" appointment={appt({ trip: current })} trips={TRIPS} onSaved={onSaved} onCancel={vi.fn()} />);
    await waitFor(() => expect(screen.getByLabelText("Contact person (required)")).not.toBeDisabled());
    expect(screen.getByLabelText("Trip")).toHaveValue("t9");
    expect(tripOptions()).toContain("TRV-000009 · Hyderabad → Vijayawada (07 Jan 2030 – 08 Jan 2030) — Cancelled");
    fireEvent.change(screen.getByLabelText("Trip"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(body(fetchMock, 1)).toEqual({ trip_id: null });
  });

  it("without trips to offer the form says so and still books", () => {
    render(<BdmAppointmentForm mode="create" bdmType="college" initialOrganization={org} tripsUnavailable />);
    expect(screen.getByText("Your trips couldn't be loaded — you can link this appointment to a trip later.")).toBeInTheDocument();
  });
});

describe("appointment detail Trip row (bdm-011)", () => {
  it("links the BDM to the trip and says when it is not approved yet", () => {
    render(<BdmAppointmentDetail initial={appt({ trip: tripRef({ approval_status: "submitted" }) })} basePath="/bdm/appointments" bdmType="college" />);
    const link = screen.getByRole("link", { name: /TRV-000001/ });
    expect(link).toHaveAttribute("href", "/bdm/travel/t1#trip-appointments");
    expect(link.closest("dd")).toHaveTextContent("Trip not approved yet");
  });

  it("links a manager to the team trip; no trip reads as a dash", () => {
    render(<BdmAppointmentDetail initial={appt({ trip: tripRef(), permissions: { ...appt().permissions, can_edit: false } })} basePath="/bdm/manager/appointments" bdmType={null} />);
    expect(screen.getByRole("link", { name: /TRV-000001/ })).toHaveAttribute("href", "/bdm/manager/trips/t1#trip-appointments");
    cleanup();
    render(<BdmAppointmentDetail initial={appt()} basePath="/bdm/appointments" bdmType="college" />);
    expect(within(screen.getByText("Trip", { selector: "dt" }).nextElementSibling as HTMLElement).getByText("—")).toBeInTheDocument();
  });
});

describe("reschedule outside the trip (bdm-011 edge case)", () => {
  it("says the appointment left the trip", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ appointment: appt({ trip: null, status: "rescheduled" }) }))));
    const onChanged = vi.fn();
    render(<BdmAppointmentActions appointment={appt({ trip: tripRef() })} bdmType="college" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-20T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new time" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(onChanged.mock.calls[0][1]).toBe("Appointment rescheduled. It is now outside TRV-000001's dates, so it was removed from that trip.");
  });

  it("a reschedule within the trip keeps the usual message", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ appointment: appt({ trip: tripRef(), status: "rescheduled" }) }))));
    const onChanged = vi.fn();
    render(<BdmAppointmentActions appointment={appt({ trip: tripRef() })} bdmType="college" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-08T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new time" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(onChanged.mock.calls[0][1]).toBe("Appointment rescheduled.");
  });
});
