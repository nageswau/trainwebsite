import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItStudent360View from "@/components/ItStudent360View";
import type { Student360 } from "@/lib/itStudent360";

// The lead timeline is its own client list (LeadTimeline's tests); here only where it is mounted.
vi.mock("@/components/LeadTimeline", () => ({ default: ({ url }: { url: string }) => <div data-testid="lead-timeline">{url}</div> }));

const base = (extra: Partial<Student360> = {}): Student360 => ({
  student: { id: "s1", full_name: "Asha Rao", student_code: "AB12CD34", active: true },
  viewer: "counselor",
  sections: [],
  contact: { email: "asha@example.local", phone: "+919876543210", counselor: { id: "c1", full_name: "Nora Counselor" } },
  enrollments: [{ id: "e1", enrollment_code: "EDU-1", program: "Python Full Stack", batch: "PY-Jan", trainer: "Tara Trainer", status: "active",
    start_date: "2026-01-05", end_date: "2026-04-05", delivery_mode: "Online", progress_percent: 40, attendance_percent: 75, attendance_marked: 4 }],
  feedback: [{ kind: "assignment", title: "SQL joins", score: 72, max_score: 100, feedback: "Revise GROUP BY.", by: "Tara Trainer", at: "2026-02-05T10:00:00Z" }],
  resumes: { items: [{ version: 2, file_name: "cv.pdf", content_type: "application/pdf", size_bytes: 2048, visibility: "hr", uploaded_by: { id: "c1", full_name: "Nora Counselor" },
    uploaded_by_role: "counselor", created_at: "2026-02-01T10:00:00Z" }] },
  hr_review: { task: null },
  notes: { items: [], total: 0 },
  ...extra,
} as Student360);

const counselorView = () =>
  base({
    profile: { city: "Hyderabad", qualification: "B.Tech", emergency_contact_name: "Ravi", emergency_contact_relation: "Father", emergency_contact_phone: "+919812345678", calls_allowed: true },
    lead: { id: "l1", lead_code: "LD-000042", stage: "converted", stage_label: "Converted", owner: "Nora Counselor", created_at: "2026-01-01T10:00:00Z", converted_at: null, href: "/it/counselor/leads/l1" },
    fee: { accounts: [{ enrollment_id: "e1", enrollment_code: "EDU-1", course: "Python Full Stack", batch: "PY-Jan", currency: "INR", course_fee: 45000, discount_approved: 0, tax: 0,
      total_payable: 45000, paid_confirmed: 15000, credits: 0, balance: 30000, state: "partially_paid" }], balance: 30000 },
    risk: [{ enrollment_id: "e1", batch: "PY-Jan", reasons: ["attendance"], attendance_percent: 60, assessment_percent: null, consecutive_absences: 0, raised_at: "2026-02-06T10:00:00Z" }],
    notifications: [{ id: "n1", title: "Payment received", event_type: "it.fee.payment_received", sent_at: "2026-02-07T10:00:00Z", read: false }],
  });

const heading = (name: string) => screen.queryByRole("heading", { level: 3, name });

afterEach(cleanup);

describe("ItStudent360View (itc-029)", () => {
  it("shows every section the counselor may see, from the API's figures", () => {
    render(<ItStudent360View portal="counselor" data={counselorView()} />);
    for (const name of ["Contact", "Lead history", "Courses and progress", "Risk", "Fees", "Recent trainer feedback", "Resume and HR stage", "Notes", "Notifications sent"]) {
      expect(heading(name)).toBeInTheDocument();
    }
    expect(screen.getByText("Ravi (Father) +919812345678")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "LD-000042" })).toHaveAttribute("href", "/it/counselor/leads/l1");
    expect(screen.getByTestId("lead-timeline")).toHaveTextContent("/api/v1/it/students/s1/360/lead-timeline");
    const courses = screen.getByRole("table", { name: "Courses and progress" });
    expect(within(courses).getByText("40%")).toBeInTheDocument();
    expect(within(courses).getByText("75%")).toBeInTheDocument();
    expect(screen.getByText("Total balance: INR 30,000.00")).toBeInTheDocument();
    expect(screen.getByText(/Attendance 60%/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download resume version 2" })).toHaveAttribute("href", "/api/v1/counselor/it/students/s1/resumes/2/file");
    expect(screen.getByText(/Payment received/)).toBeInTheDocument();
  });

  it("renders only HR's sections when the API omits the rest (Q-28)", () => {
    const seat = { ...base().enrollments[0] };
    delete seat.attendance_percent; // no `attendance.view`: the API leaves the figures out
    delete seat.attendance_marked;
    render(<ItStudent360View portal="hr" data={base({ viewer: "hr", enrollments: [seat] })} />);
    for (const name of ["Lead history", "Risk", "Fees", "Notifications sent"]) expect(heading(name)).not.toBeInTheDocument();
    expect(screen.queryByText(/Emergency contact/)).not.toBeInTheDocument();
    expect(screen.queryByText(/INR/)).not.toBeInTheDocument();
    expect(screen.getByText("Attendance: not available to your role.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download resume version 2" })).toHaveAttribute("href", "/api/v1/hr/students/s1/resumes/2/file");
    expect(screen.getByRole("link", { name: "Open notes" })).toHaveAttribute("href", "/it/hr/students/s1/notes");
  });

  it("says so when a student has no enrolment, lead, risk, feedback or resume yet", () => {
    render(
      <ItStudent360View
        portal="admin"
        data={base({ enrollments: [], feedback: [], resumes: { items: [] }, lead: null, risk: [], fee: { accounts: [], balance: null }, notifications: [] })}
      />,
    );
    expect(screen.getByText("No enrolments yet.")).toBeInTheDocument();
    expect(screen.getByText("This student did not come from an IT lead.")).toBeInTheDocument();
    expect(screen.getByText("Not flagged at risk.")).toBeInTheDocument();
    expect(screen.getByText("No fee account yet: the student has no enrolment.")).toBeInTheDocument();
    expect(screen.getByText("No graded feedback yet.")).toBeInTheDocument();
    expect(screen.getByText("No resume uploaded yet.")).toBeInTheDocument();
    expect(screen.getByText("No HR review yet.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("No notifications sent to the student yet.")).toBeInTheDocument();
  });
});
