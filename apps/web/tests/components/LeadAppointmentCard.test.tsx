import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LeadAppointmentCard from "@/components/LeadAppointmentCard";
import type { LeadAppointment } from "@/lib/leadAppointments";

const none = { can_confirm: false, can_complete: false, can_no_show: false, can_cancel: false, can_reschedule: false };
const base: LeadAppointment = {
  id: "a1", code: "CAP-000001", lead: { id: "l1", lead_code: "LD-000001", name: "Asha", phone: "9876543210", email: null, status: "counselling_scheduled", status_label: "Counselling Scheduled" },
  appointment_type: "it_course_counselling", type_label: "IT course counselling", counselor: { id: "c1", full_name: "Kavya" }, booked_by: { id: "t1", full_name: "Ravi" },
  scheduled_at: "2030-01-02T05:30:00+00:00", duration_minutes: 60, mode: "Online", meeting_link: "https://meet.example.com/x", location: null, purpose: null, remarks: null,
  status: "scheduled", created_at: "2030-01-01T05:30:00+00:00", events: [{ from_status: null, to_status: "scheduled", old_scheduled_at: null, new_scheduled_at: null, reason: null, actor_name: "Ravi", created_at: "2030-01-01T05:30:00+00:00" }],
  permissions: { ...none, can_cancel: true, can_reschedule: true },
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LeadAppointmentCard (tel-016)", () => {
  it("shows only the actions the API allows, and nothing for a reader", () => {
    const { rerender } = render(<LeadAppointmentCard appointment={base} showLead={false} onChanged={() => {}} />);
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(["Reschedule", "Cancel appointment"]);
    rerender(<LeadAppointmentCard appointment={{ ...base, permissions: none }} showLead={false} onChanged={() => {}} />);
    expect(screen.queryAllByRole("button")).toEqual([]);
    rerender(<LeadAppointmentCard appointment={{ ...base, permissions: { ...base.permissions, can_confirm: true } }} showLead onChanged={() => {}} />);
    expect(screen.getByRole("button", { name: "Confirm" })).toBeTruthy();
    expect(screen.getByText("Asha (LD-000001)")).toBeTruthy(); // the counselor's view names the lead (AP13)
  });

  it("never links a non-http meeting link (spec §5)", () => {
    render(<LeadAppointmentCard appointment={{ ...base, meeting_link: "javascript:alert(1)" }} showLead={false} onChanged={() => {}} />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("javascript:alert(1)")).toBeTruthy();
  });

  it("asks for a cancel reason, clears the error as it is typed, then hands the result back", async () => {
    const cancelled = { ...base, status: "cancelled" as const, permissions: none };
    const fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify(cancelled), { status: 200 })));
    vi.stubGlobal("fetch", fetch);
    const onChanged = vi.fn();
    render(<LeadAppointmentCard appointment={base} showLead={false} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    expect(screen.getByText("Add a reason for cancelling.")).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Reason for cancelling"), { target: { value: "Lead travelling" } });
    expect(screen.queryByText("Add a reason for cancelling.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(cancelled));
    expect(fetch).toHaveBeenCalledWith("/api/v1/lead-appointments/a1/cancel", expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "Lead travelling" }) }));
  });
});
