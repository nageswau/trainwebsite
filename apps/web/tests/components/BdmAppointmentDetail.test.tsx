import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmAppointmentDetail from "@/components/BdmAppointmentDetail";
import type { Appointment } from "@/lib/bdmAppointments";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
const none = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false };
const appt = (over: Partial<Appointment> = {}) => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 90, appointment_type: "placement_discussion", status: "completed",
  organization: { id: "o1", code: "ORG-000001", name: "St Mary", archived: true }, contact_name: "Dr Rao", contact_id: null, bdm: { id: "b1", full_name: "Asha", active: true },
  contact_designation: "Principal", contact_phone: "+91 90000 00000", contact_email: "rao@x.edu", location: "<b>Main</b>", purpose: "Tie-up", remarks: null,
  outcome: "student_leads_expected", next_follow_up_on: "2030-01-10", expected_leads: 12, expected_revenue: "25000.50",
  events: [{ from_status: null, to_status: "scheduled", old_starts_at: null, new_starts_at: null, reason: null, actor_name: "Asha", created_at: "2030-01-01T04:30:00Z" }],
  created_at: "", updated_at: "", permissions: none, ...over,
}) as Appointment;
afterEach(cleanup);

describe("BdmAppointmentDetail (bdm-006 AC1, R-F1, R-F2, R-F12)", () => {
  it("shows every section 2 field, the outcome, and plain text only", () => {
    render(<BdmAppointmentDetail initial={appt()} basePath="/bdm/manager/appointments" bdmType={null} />);
    const details = screen.getByRole("region", { name: "Details" });
    const value = (label: string) => within(details).getByText(label).nextElementSibling;
    expect(value("Date & time")).toHaveTextContent(/07 Jan 2030, 10:00 IST · 1 h 30 min/);
    expect(value("Contact person")).toHaveTextContent("Dr Rao");
    expect(value("Mobile")).toHaveTextContent("+91 90000 00000");
    expect(value("Type")).toHaveTextContent("Placement Discussion");
    expect(value("Location")).toHaveTextContent("<b>Main</b>");
    expect(value("Expected revenue")).toHaveTextContent("₹25,000.50");
    expect(value("Remarks")).toHaveTextContent("—");
    expect(screen.getByRole("region", { name: "Outcome" })).toHaveTextContent("Student Leads Expected");
    expect(screen.getByText("Completed")).toHaveClass("status");
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "St Mary" })).toHaveAttribute("href", "/bdm/manager/organizations/o1");
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByRole("link", { name: /rao@x\.edu/ })).toBeNull();
  });

  it("hints when the start has passed and shows the booked notice once", () => {
    const replace = vi.spyOn(window.history, "replaceState");
    render(<BdmAppointmentDetail initial={appt({ status: "confirmed", outcome: null, next_follow_up_on: null, permissions: { ...none, can_complete: true, can_no_show: true } })} basePath="/bdm/appointments" bdmType="college" created />);
    expect(screen.getByRole("note")).toHaveTextContent("The start time has passed — complete it or mark it as a no-show.");
    expect(screen.getByRole("status")).toHaveTextContent("Appointment APT-000001 booked.");
    expect(replace).toHaveBeenCalledWith(null, "", "/bdm/appointments/a1");
  });
});
