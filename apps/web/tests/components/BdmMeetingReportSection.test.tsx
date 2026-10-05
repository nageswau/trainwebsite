import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmMeetingReportSection from "@/components/BdmMeetingReportSection";
import type { Appointment } from "@/lib/bdmAppointments";

const report = { discussion: "Line one\nLine two", requirements: null, opportunity: "Lab", next_action: "Send proposal", responsible_person: "Mrs Rao", legacy: false, author: { id: "b1", full_name: "Asha BDM", active: true }, submitted_at: "2030-01-01T05:00:00Z", updated_at: "2030-01-01T05:00:00Z" };
const none = { can_edit: false, can_confirm: false, can_reschedule: false, can_cancel: false, can_no_show: false, can_complete: false, can_edit_report: false };
const appt = (over: Partial<Appointment> = {}): Appointment => ({
  id: "a1", code: "APT-000001", starts_at: "2030-01-01T04:30:00Z", duration_minutes: 60, appointment_type: "college_meeting", status: "completed",
  organization: { id: "o1", code: "ORG-1", name: "Acme College", archived: false }, contact_name: "Dr Rao", bdm: { id: "b1", full_name: "Asha BDM", active: true },
  outcome_pending: false, contact_id: null, contact_designation: null, contact_phone: null, contact_email: null, location: null, purpose: null, remarks: null,
  outcome: "interested", next_follow_up_on: "2030-01-10", expected_leads: null, expected_revenue: null, events: [], permissions: none,
  report, follow_up: { id: "t1", due_on: "2030-01-10", status: "open" }, created_at: "2030-01-01T00:00:00Z", updated_at: "2030-01-01T00:00:00Z", ...over,
} as Appointment);
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmMeetingReportSection", () => {
  it("shows every report field as plain text with line breaks kept", () => {
    render(<BdmMeetingReportSection appointment={appt({ report: { ...report, discussion: "<b>bold</b>\nnext" } })} bdmType={null} onChanged={() => {}} />);
    const region = screen.getByRole("region", { name: "Meeting report" });
    expect(region).toHaveTextContent("Interested");
    expect(region).toHaveTextContent("<b>bold</b>");  // escaped, never rendered as HTML
    expect(region).toHaveTextContent("Send proposal");
    expect(region).toHaveTextContent("Mrs Rao");
    expect(region).toHaveTextContent("Asha BDM");
    expect(screen.queryByRole("button", { name: "Edit report" })).toBeNull();
  });

  it("says a legacy report has the outcome only", () => {
    render(<BdmMeetingReportSection appointment={appt({ report: { ...report, legacy: true, discussion: null } })} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByText("Recorded before meeting reports — outcome only.")).toBeInTheDocument();
  });

  it("edits on the filing day and re-renders from the response", async () => {
    const saved = appt({ report: { ...report, next_action: "Call back" }, permissions: { ...none, can_edit_report: true } });
    const fetchMock = vi.fn(() => Promise.resolve(res({ appointment: saved })));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<BdmMeetingReportSection appointment={appt({ permissions: { ...none, can_edit_report: true } })} bdmType="college" onChanged={onChanged} />);
    expect(screen.getByText("You can change this report until midnight IST today.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Edit report" }));
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Call back" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(saved, "Meeting report saved."));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect([url, init.method]).toEqual(["/api/v1/bdm/appointments/a1/report", "PATCH"]);
  });

  it("keeps the edit text when the window has closed (409)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Meeting reports can only be changed on the day they were filed" }, 409))));
    render(<BdmMeetingReportSection appointment={appt({ permissions: { ...none, can_edit_report: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit report" }));
    fireEvent.change(screen.getByLabelText("Next action"), { target: { value: "Late edit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Meeting reports can only be changed on the day they were filed");
    expect(screen.getByLabelText("Next action")).toHaveValue("Late edit");
    // QA7-02 / QA7-05: the form locks (text kept to copy), focus goes to the reason, and Close leaves a read-only report.
    expect(screen.getByLabelText("Next action")).toHaveAttribute("readonly");
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(alert));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("button", { name: "Edit report" })).toBeNull();
    expect(screen.queryByText("You can change this report until midnight IST today.")).toBeNull();
    expect(screen.getByText("This report can no longer be changed.")).toBeInTheDocument();
  });

  it("QA7-07: Cancel clears a field error, so editing again starts clean", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: [{ loc: ["body", "next_action"], msg: "Value error, Next action contains invalid characters" }] }, 422))));
    render(<BdmMeetingReportSection appointment={appt({ permissions: { ...none, can_edit_report: true } })} bdmType="college" onChanged={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit report" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("Next action contains invalid characters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit report" }));
    expect(screen.queryByText("Next action contains invalid characters")).toBeNull();
    expect(screen.getByLabelText("Next action")).not.toHaveAttribute("aria-invalid");
  });

  it("QA7-08: tells the BDM a filed report is read-only once its day has passed (not managers, not legacy)", () => {
    const { rerender } = render(<BdmMeetingReportSection appointment={appt()} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByText("This report can no longer be changed.")).toBeInTheDocument();
    rerender(<BdmMeetingReportSection appointment={appt()} bdmType={null} onChanged={() => {}} />);
    expect(screen.queryByText("This report can no longer be changed.")).toBeNull();
    rerender(<BdmMeetingReportSection appointment={appt({ report: { ...report, legacy: true } })} bdmType="college" onChanged={() => {}} />);
    expect(screen.queryByText("This report can no longer be changed.")).toBeNull();
  });

  it("offers booking the next meeting after a Reschedule outcome, for the BDM only", () => {
    const { rerender } = render(<BdmMeetingReportSection appointment={appt({ outcome: "reschedule" })} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByRole("link", { name: "Book the next meeting" })).toHaveAttribute("href", "/bdm/appointments/new?organization=o1");
    rerender(<BdmMeetingReportSection appointment={appt({ outcome: "reschedule" })} bdmType={null} onChanged={() => {}} />);
    expect(screen.queryByRole("link", { name: "Book the next meeting" })).toBeNull();
  });

  it("shows a cancelled follow-up as cancelled", () => {
    render(<BdmMeetingReportSection appointment={appt({ next_follow_up_on: null, follow_up: { id: "t1", due_on: "2030-01-10", status: "cancelled" } })} bdmType="college" onChanged={() => {}} />);
    expect(screen.getByRole("region", { name: "Meeting report" })).toHaveTextContent("—");
  });
});
