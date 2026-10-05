import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import CareerRecordDetails from "@/components/CareerRecordDetails";

afterEach(cleanup);

describe("CareerRecordDetails", () => {
  it("shows status as text, dates and only the fields that have content", () => {
    render(<CareerRecordDetails record={{ id: "r", school_student_id: "s", record_type: "counselling_note", notes: "Met.", created_at: "2026-09-01T00:00:00Z", status: "follow_up_required", next_follow_up_date: "2026-10-05", weak_areas: ["Essays"], recommended_careers: null, counselor_name: "Priya" }} />);
    expect(screen.getByText("Follow-up Required")).toBeInTheDocument();
    expect(screen.getByText("Weak areas")).toBeInTheDocument();
    expect(screen.getByText("Essays")).toBeInTheDocument();
    expect(screen.queryByText("Recommended careers")).not.toBeInTheDocument();
    expect(screen.getByText("Priya")).toBeInTheDocument();
  });

  it("labels a legacy record without inventing fields", () => {
    render(<CareerRecordDetails record={{ id: "r", school_student_id: "s", record_type: "guidance_session", notes: "Old.", created_at: "2026-09-01T00:00:00Z", status: null }} />);
    expect(screen.getByText("No status (recorded before tracking)")).toBeInTheDocument();
    expect(screen.queryByRole("term")).toBeNull();
  });
});
