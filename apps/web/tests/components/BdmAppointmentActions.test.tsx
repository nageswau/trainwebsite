import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentActions from "@/components/BdmAppointmentActions";
import type { Appointment, AppointmentPermissions } from "@/lib/bdmAppointments";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const none: AppointmentPermissions = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false, can_edit_report: false };
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "scheduled",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: false }, contact_name: "Dr Rao", contact_id: "c1", bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: null, contact_phone: null, contact_email: null, location: null, purpose: null, remarks: null, outcome: null, next_follow_up_on: null, outcome_pending: false, report: null, follow_up: null,
  expected_leads: null, expected_revenue: null, events: [], created_at: "", updated_at: "", permissions: none, ...over,
}) as Appointment;
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmAppointmentActions (bdm-006 §6.2, R-F4, R-F7)", () => {
  it("renders nothing without permissions (managers, closed appointments)", () => {
    const { container } = render(<BdmAppointmentActions appointment={appt()} bdmType="college" onChanged={() => {}} />);
    expect(container.querySelectorAll("button")).toHaveLength(0);
  });

  it("QA6-04: a 5xx shows an actionable sentence; a 422 still shows the server's detail", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(new Response("boom", { status: 500 })).mockResolvedValueOnce(res({ detail: "Only a scheduled appointment can be confirmed" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_confirm: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("We couldn't update the appointment. Please try again.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Only a scheduled appointment can be confirmed")).toBeInTheDocument();
  });

  it("confirms in one click and re-renders from the response", async () => {
    const onChanged = vi.fn();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "confirmed" }) }))));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_confirm: true } })} bdmType="college" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "confirmed" }), "Appointment confirmed."));
  });

  it("requires a reason to cancel; Escape closes and returns focus", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "cancelled" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_cancel: true } })} bdmType="college" onChanged={() => {}} />);
    const trigger = screen.getByRole("button", { name: "Cancel appointment" });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Yes, cancel it" }));
    expect(screen.getByText("Enter a reason.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(screen.getByLabelText("Reason (required)"), { key: "Escape" });
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel appointment" })));
  });

  it("on a 409 refetches and says what the appointment became", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "Appointment is already cancelled" }, 409)).mockResolvedValueOnce(res({ appointment: appt({ status: "cancelled" }) }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_confirm: true } })} bdmType="college" onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "cancelled" }), "This appointment changed — it is now Cancelled."));
  });

  it("completes by filing the meeting report", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: appt({ status: "completed", outcome: "agreement_required" }) })));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="agent" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "agreement_required" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Agreement terms" } });
    fireEvent.click(screen.getByRole("button", { name: "Save report and complete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(JSON.parse(String(((fetchMock.mock.calls[0] as unknown[])[1] as RequestInit).body))).toEqual({
      outcome: "agreement_required", discussion: "Agreement terms", requirements: null, opportunity: null, next_action: null, responsible_person: null, next_follow_up_on: null,
    });
  });

  it("keeps the typed report on a 409", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Appointment is already completed" }, 409))));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "Long notes" } });
    fireEvent.click(screen.getByRole("button", { name: "Save report and complete" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This appointment changed elsewhere — copy your notes, then reload.");
    expect(screen.getByLabelText("Discussion (required)")).toHaveValue("Long notes");
    expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("maps a 422 field error onto the report field", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: [{ loc: ["body", "opportunity"], msg: "Value error, Opportunity contains invalid characters" }] }, 422))));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_complete: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Complete" }));
    fireEvent.change(screen.getByLabelText("Outcome (required)"), { target: { value: "interested" } });
    fireEvent.change(screen.getByLabelText("Discussion (required)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Save report and complete" }));
    expect(await screen.findByText("Opportunity contains invalid characters")).toBeInTheDocument();
  });

  it("shows the overlap warning inside Reschedule and confirms past it", async () => {
    const detail = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-08T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail }, 409)).mockResolvedValueOnce(res({ appointment: appt({ status: "rescheduled" }) }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_reschedule: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-08T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new time" }));
    expect(await screen.findByText(/APT-000009/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(((fetchMock.mock.calls[1] as unknown[])[1] as RequestInit).body))).toMatchObject({ starts_at: "2030-01-08T10:00:00+05:30", confirm_overlap: true });
  });

  const overlapDetail = { code: "possible_overlap", message: "You already have an appointment at this time", total: 1, matches: [{ id: "x", code: "APT-000009", starts_at: "2030-01-08T04:30:00Z", duration_minutes: 60, organization_name: "Holy Cross" }] };
  const openOverlap = async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: overlapDetail }, 409)));
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_reschedule: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-08T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new time" }));
    await screen.findByText(/APT-000009/);
  };

  it("clears the overlap warning when the time changes, so Save anyway cannot confirm an unchecked time", async () => {
    await openOverlap();
    expect(screen.getByRole("button", { name: "Save new time" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-09T10:00" } });
    expect(screen.queryByText(/APT-000009/)).toBeNull();
    expect(screen.queryByRole("button", { name: "Save anyway" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save new time" })).toBeEnabled();
  });

  it("Save anyway resends the checked time even if it was edited while the request was pending", async () => {
    let settle!: (r: Response) => void;
    const fetchMock = vi.fn().mockReturnValueOnce(new Promise<Response>((r) => { settle = r; })).mockResolvedValueOnce(res({ appointment: appt({ status: "rescheduled" }) }));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmAppointmentActions appointment={appt({ permissions: { ...none, can_reschedule: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Reschedule" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-08T10:00" } });
    fireEvent.click(screen.getByRole("button", { name: "Save new time" }));
    fireEvent.change(screen.getByLabelText("New date and time (IST) (required)"), { target: { value: "2030-01-09T15:00" } });
    settle(res({ detail: overlapDetail }, 409));
    fireEvent.click(await screen.findByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(JSON.parse(String(((fetchMock.mock.calls[1] as unknown[])[1] as RequestInit).body))).toMatchObject({ starts_at: "2030-01-08T10:00:00+05:30", confirm_overlap: true });
  });

  it("dismisses only the warning on its Cancel or Escape and keeps the entered time", async () => {
    await openOverlap();
    fireEvent.click(within(screen.getByRole("alert")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByText(/APT-000009/)).toBeNull();
    expect((screen.getByLabelText("New date and time (IST) (required)") as HTMLInputElement).value).toBe("2030-01-08T10:00");
    cleanup();
    await openOverlap();
    fireEvent.keyDown(screen.getByRole("alert"), { key: "Escape" });
    expect(screen.queryByText(/APT-000009/)).toBeNull();
    expect((screen.getByLabelText("New date and time (IST) (required)") as HTMLInputElement).value).toBe("2030-01-08T10:00");
  });
});
