import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import MeetingRequestsCard from "@/components/MeetingRequestsCard";
import type { MeetingRequest } from "@/lib/meetingRequests";

afterEach(cleanup);
const item = { id: "r1", code: "MRQ-000001", type_label: "School meeting", organization_name: "St Mary", proposed_at: "2030-01-02T05:30:00+00:00", bdm: null } as MeetingRequest;

describe("MeetingRequestsCard (tel-019, My Day)", () => {
  it("counts the pending requests and links each one", () => {
    render(<MeetingRequestsCard page={{ items: [item], total: 3, limit: 5, offset: 0 }} />);
    expect(screen.getByText(/3 pending requests/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "MRQ-000001" }).getAttribute("href")).toBe("/bdm/meeting-requests/r1");
    expect(screen.getByRole("link", { name: "Open requests" }).getAttribute("href")).toBe("/bdm/meeting-requests");
  });

  it("has an empty state and survives a failed read", () => {
    const { rerender } = render(<MeetingRequestsCard page={{ items: [], total: 0, limit: 5, offset: 0 }} />);
    expect(screen.getByText("No pending meeting requests.")).toBeTruthy();
    rerender(<MeetingRequestsCard page={null} />);
    expect(screen.getByText(/Unable to load your meeting requests/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open requests" })).toBeTruthy();
  });
});
