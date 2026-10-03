import { describe, expect, it } from "vitest";

import { APPROVAL_LABEL, MODE_LABEL, TRIPS_URL, fieldErrors, formatInr, travelDateBounds, tripSummary, tripUrl } from "@/lib/bdmTravel";

describe("bdmTravel", () => {
  it("labels every mode and status", () => {
    expect(Object.keys(MODE_LABEL)).toEqual(["flight", "train", "bus", "car", "cab", "local"]);
    expect(APPROVAL_LABEL.submitted).toBe("Submitted");
  });
  it("builds urls", () => {
    expect(TRIPS_URL).toBe("/api/v1/bdm/trips");
    expect(tripUrl("abc")).toBe("/api/v1/bdm/trips/abc");
  });
  it("formats rupees", () => {
    expect(formatInr("1650.50")).toBe("₹1,650.50");
    expect(formatInr("10000000.00")).toBe("₹1,00,00,000.00");
  });
  it("bounds the travel date to 30 days back", () => {
    expect(travelDateBounds("2026-10-03")).toEqual({ min: "2026-09-03" });
  });
  it("maps a 422 list to fields and ignores string details", () => {
    expect(fieldErrors([{ loc: ["body", "purpose"], msg: "Value error, Purpose is required" }, { loc: ["body"], msg: "x" }]))
      .toEqual({ purpose: "Purpose is required" });
    expect(fieldErrors("Trip not found")).toEqual({});
  });
  it("summarises a trip for screen readers and notices", () => {
    expect(tripSummary({ code: "TRV-000001", from_place: "Hyderabad", to_place: "Vijayawada" } as never)).toBe("TRV-000001, Hyderabad to Vijayawada");
  });
});
