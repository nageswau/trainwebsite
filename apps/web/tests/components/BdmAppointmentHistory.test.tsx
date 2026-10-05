import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import BdmAppointmentHistory from "@/components/BdmAppointmentHistory";

afterEach(cleanup);

it("lists booking, transitions, the old and new time, and reasons in order (AC3, AC4)", () => {
  render(
    <BdmAppointmentHistory
      events={[
        { from_status: null, to_status: "scheduled", old_starts_at: null, new_starts_at: null, reason: null, actor_name: "Asha", created_at: "2030-01-01T04:30:00Z" },
        { from_status: "scheduled", to_status: "rescheduled", old_starts_at: "2030-01-07T04:30:00Z", new_starts_at: "2030-01-08T05:30:00Z", reason: "Principal travelling", actor_name: "Asha", created_at: "2030-01-02T04:30:00Z" },
      ]}
    />,
  );
  const items = screen.getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Booked");
  expect(items[1]).toHaveTextContent("Scheduled → Rescheduled");
  expect(items[1]).toHaveTextContent(/from 07 Jan 2030, 10:00 IST to 08 Jan 2030, 11:00 IST/);
  expect(items[1]).toHaveTextContent("Reason: Principal travelling");
});
