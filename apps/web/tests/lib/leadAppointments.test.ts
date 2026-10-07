import { describe, expect, it } from "vitest";

import { actionUrl, bookingBody, clashText, optionsUrl, appointmentsUrl, safeLink } from "@/lib/leadAppointments";

describe("tel-016 lead appointments", () => {
  it("builds the endpoints", () => {
    expect(appointmentsUrl("a b")).toBe("/api/v1/telecaller/leads/a%20b/appointments");
    expect(optionsUrl("x")).toBe("/api/v1/telecaller/leads/x/appointment-options");
    expect(actionUrl("x", "no_show")).toBe("/api/v1/lead-appointments/x/no-show");
    expect(actionUrl("x", "confirm")).toBe("/api/v1/lead-appointments/x/confirm");
  });

  it("only ever links to http(s) (spec §5)", () => {
    expect(safeLink("https://meet.example.com/a")).toBe("https://meet.example.com/a");
    expect(safeLink("HTTP://x.example")).toBe("HTTP://x.example");
    expect(safeLink("javascript:alert(1)")).toBeNull();
    expect(safeLink(" javascript:alert(1)")).toBeNull();
    expect(safeLink(null)).toBeNull();
  });

  it("sends the IST time with its offset and drops blank optional text", () => {
    expect(bookingBody({
      appointment_type: "it_course_counselling", counselor_id: "c1", when: "2026-10-08T11:00", mode: "Online",
      meeting_link: "  ", location: " Room 2 ", purpose: "", remarks: "Bring marksheets",
    })).toEqual({
      appointment_type: "it_course_counselling", counselor_id: "c1", scheduled_at: "2026-10-08T11:00:00+05:30", mode: "Online",
      location: "Room 2", remarks: "Bring marksheets",
    });
  });

  it("words a counselor clash with the busy times (AP1)", () => {
    const detail = { message: "The counselor already has an appointment at this time", code: "counselor_busy", matches: [{ scheduled_at: "2026-10-08T05:30:00+00:00", duration_minutes: 60 }] };
    expect(clashText(detail)).toMatch(/^The counselor already has an appointment at this time\. Busy: 08 Oct 2026, 11:00/);
    expect(clashText("plain")).toBeNull();
  });
});
