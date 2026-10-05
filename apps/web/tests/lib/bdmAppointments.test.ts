import { describe, expect, it } from "vitest";

import { appointmentOutcomes, appointmentTypes, formatInr, formatMinutes, isoToIstInput, istInputToIso, overlap, STATUS_LABEL, TYPE_LABEL } from "@/lib/bdmAppointments";

describe("bdmAppointments (bdm-006)", () => {
  it("lists the common types plus the module's, once each, all labelled", () => {
    expect(appointmentTypes("agent")).toHaveLength(16);
    expect(appointmentTypes("school")).toHaveLength(18);
    expect(appointmentTypes("college")).toHaveLength(19);
    for (const t of ["agent", "school", "college"] as const) {
      const types = appointmentTypes(t);
      expect(new Set(types).size).toBe(types.length);
      expect(types).toContain("seminar_workshop");
      types.forEach((key) => expect(TYPE_LABEL[key]).toBeTruthy());
    }
    expect(appointmentTypes("agent")).not.toContain("principal_meeting");
  });

  it("uses the agent outcome list only for agent BDMs", () => {
    expect(appointmentOutcomes("agent")).toContain("agreement_required");
    expect(appointmentOutcomes("college")).toContain("course_promotion_interested");
    expect(appointmentOutcomes("school")).not.toContain("agreement_required");
  });

  it("converts the datetime-local value to and from India time across midnight (Review Focus 4)", () => {
    expect(istInputToIso("2030-01-07T23:30")).toBe("2030-01-07T23:30:00+05:30");
    expect(isoToIstInput("2030-01-07T18:00:00Z")).toBe("2030-01-07T23:30");
    expect(isoToIstInput("2030-01-06T19:00:00Z")).toBe("2030-01-07T00:30");
    expect(isoToIstInput(istInputToIso("2030-03-01T00:00"))).toBe("2030-03-01T00:00");
  });

  it("parses the overlap 409 and nothing else", () => {
    const detail = { code: "possible_overlap", message: "m", total: 1, matches: [{ id: "a", code: "APT-000001", starts_at: "2030-01-07T04:30:00Z", duration_minutes: 60, organization_name: "St Mary" }] };
    expect(overlap(detail)?.matches[0].code).toBe("APT-000001");
    expect(overlap({ code: "possible_duplicate", matches: [] })).toBeNull();
    expect(overlap("Appointment is already cancelled")).toBeNull();
  });

  it("formats durations, money and statuses", () => {
    expect(formatMinutes(45)).toBe("45 min");
    expect(formatMinutes(90)).toBe("1 h 30 min");
    expect(formatMinutes(120)).toBe("2 h");
    expect(formatInr("25000.50")).toBe("₹25,000.50");
    expect(formatInr(null)).toBe("—");
    expect(STATUS_LABEL.no_show).toBe("No show");
  });
});
