import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { formatCalendarDate, formatDate, formatSchoolDateTime, SCHOOL_TIME_ZONE, viewerTimeZone, zoneLabel } from "@/lib/formatDate";

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

// Date sweep: a calendar date (YYYY-MM-DD) has no time of day, so it must name the same day for every viewer -- a zone west of UTC
// otherwise turns "2026-10-01" (UTC midnight) into 30 Sept.
describe("formatCalendarDate", () => {
  it.each(["UTC", "Asia/Kolkata", "America/New_York", "Pacific/Honolulu"])("names the stored day in %s", (tz) => {
    process.env.TZ = tz;
    expect(formatCalendarDate("2026-10-01")).toBe("01 Oct 2026");
  });

  it("keeps the missing and unparseable fallbacks", () => {
    expect(formatCalendarDate(null)).toBe("-");
    expect(formatCalendarDate("not a date")).toBe("not a date");
  });
});

// Date sweep: school portal timestamps are in India time (D10); a scheduled one (activity, session) says so.
describe("formatSchoolDateTime", () => {
  it("formats in India time whatever zone renders it, labelled only when asked", () => {
    expect(formatSchoolDateTime("2026-09-21T20:00:00Z")).toBe("22 Sept 2026, 01:30");
    expect(formatSchoolDateTime("2026-09-21T20:00:00Z", true)).toBe("22 Sept 2026, 01:30 IST");
  });

  it("never labels a missing value", () => {
    expect(formatSchoolDateTime(null, true)).toBe("-");
  });
});

// Date sweep: the zone label on scheduled times. India reads "IST" (en-US would say "GMT+5:30"); other zones use the short en-US name.
describe("zoneLabel", () => {
  it("names India time IST under either IANA spelling", () => {
    expect(zoneLabel("2026-09-21T20:00:00Z", "Asia/Kolkata")).toBe("IST");
    expect(zoneLabel("2026-09-21T20:00:00Z", "Asia/Calcutta")).toBe("IST");
  });

  it("uses the short name for other zones, including daylight saving", () => {
    expect(zoneLabel("2026-09-21T20:00:00Z", "UTC")).toBe("UTC");
    expect(zoneLabel("2026-07-01T12:00:00Z", "America/New_York")).toBe("EDT");
    expect(zoneLabel("2026-12-01T12:00:00Z", "America/New_York")).toBe("EST");
  });
});

describe("viewerTimeZone", () => {
  it("is the zone this runtime reports", () => {
    process.env.TZ = "America/New_York";
    expect(viewerTimeZone()).toBe("America/New_York");
  });

  it("falls back to India time when the runtime reports a zone Intl cannot use (e.g. Etc/Unknown)", () => {
    process.env.TZ = "Not/AZone";
    expect(viewerTimeZone()).toBe(SCHOOL_TIME_ZONE);
  });
});
