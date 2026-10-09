import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import UniversityFollowUp from "@/components/UniversityFollowUp";

afterEach(cleanup);

describe("UniversityFollowUp (upc-020 §20)", () => {
  it("shows the XYZ example: last action, next action, date, owner and priority", () => {
    render(
      <UniversityFollowUp followUp={{
        next_action: { id: "t1", title: "Follow-up call", due_on: "2026-09-18", priority: "high", band: "overdue", assignee: { id: "p", full_name: "Rahul", active: true } },
        last_action: { title: "Proposal sent", at: "2026-09-10T10:00:00Z" },
      }} />,
    );
    expect(screen.getByText("Proposal sent")).toBeInTheDocument();
    expect(screen.getByText("Follow-up call")).toBeInTheDocument();
    expect(screen.getByText(/18 Sept? 2026/)).toBeInTheDocument();
    expect(screen.getByText("Overdue")).toBeInTheDocument();
    expect(screen.getByText("Rahul")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("says when nothing is planned or done yet", () => {
    render(<UniversityFollowUp followUp={{ next_action: null, last_action: null }} />);
    expect(screen.getByText("No follow-up planned")).toBeInTheDocument();
    expect(screen.getByText("Nothing recorded yet")).toBeInTheDocument();
  });
});
