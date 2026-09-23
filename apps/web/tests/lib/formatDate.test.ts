import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { formatDate, SCHOOL_TIME_ZONE } from "@/lib/formatDate";

// QA-022-06: the server renders in UTC and the browser in the user's zone; a date shown on both must not depend on either,
// or React throws hydration error #418. Simulate the server by running this file in UTC.
let savedTz: string | undefined;
beforeEach(() => {
  savedTz = process.env.TZ;
  process.env.TZ = "UTC";
});
afterEach(() => {
  process.env.TZ = savedTz;
});

describe("formatDate with a time zone", () => {
  it("shows the school's local time whatever zone renders it", () => {
    expect(SCHOOL_TIME_ZONE).toBe("Asia/Kolkata");
    expect(formatDate("2027-01-15T04:30:00Z", true, SCHOOL_TIME_ZONE)).toBe("15 Jan 2027, 10:00");
  });

  it("is unchanged for existing callers that pass no zone", () => {
    expect(formatDate("2027-01-15T04:30:00Z")).toBe("15 Jan 2027");
    expect(formatDate(null)).toBe("-");
  });
});
