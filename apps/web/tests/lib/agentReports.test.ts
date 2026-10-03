import { describe, expect, it } from "vitest";

import { csvFilename, csvUrl, isAgentReport, readState, reportQuery, tabsFor } from "@/lib/agentReports";

// AGN-020 (DEC-SCOPE-066; spec §6.2-§6.3): the Reports page's tabs, URL state and requests.

describe("tabsFor", () => {
  it("gives a Master all eight reports, Commission last", () => {
    expect(tabsFor("master").map((t) => t.key)).toEqual(["students", "applications", "universities", "countries", "intakes", "staff", "enrollments", "commission"]);
    expect(tabsFor(null).map((t) => t.key)).toHaveLength(8); // a legacy agent with no membership row is a Master (AGN-014)
  });

  it("gives staff six, never Staff performance or Commission", () => {
    expect(tabsFor("staff").map((t) => t.key)).toEqual(["students", "applications", "universities", "countries", "intakes", "enrollments"]);
  });
});

describe("readState", () => {
  const master = tabsFor("master");

  it("reads the report, dates, supported filters and offset", () => {
    const state = readState("?report=applications&from=2026-01-01&to=2026-01-31&country=aland&intake=2027-09&offset=50", master);
    expect(state).toEqual({ report: "applications", from: "2026-01-01", to: "2026-01-31", filters: { country: "aland", intake: "2027-09" }, offset: 50 });
  });

  it("drops filters the report does not offer, malformed dates and a bad offset", () => {
    const state = readState("?report=countries&from=2026-1-1&university=x&member=ABC-S001&offset=-5", master);
    expect(state).toEqual({ report: "countries", from: "", to: "", filters: { member: "ABC-S001" }, offset: 0 });
  });

  it("drops an offset beyond the last page an export could reach (final review I4)", () => {
    expect(readState("?report=students&offset=99999", master).offset).toBe(0);
    expect(readState("?report=students&offset=9950", master).offset).toBe(9950);
  });

  it("falls back to the first tab for an unknown or forbidden report", () => {
    expect(readState("?report=nope", master).report).toBe("students");
    expect(readState("?report=staff&member=ABC-S001", tabsFor("staff"))).toEqual({ report: "students", from: "", to: "", filters: {}, offset: 0 });
  });
});

describe("reportQuery and csvUrl", () => {
  const state = { report: "applications" as const, from: "2026-01-01", to: "", filters: { country: "aland", status: "" }, offset: 100 };

  it("sends only set values, as the API names them, with the page", () => {
    expect(reportQuery(state)).toBe("?date_from=2026-01-01&country=aland&limit=50&offset=100");
  });

  it("exports the same filters without paging", () => {
    expect(csvUrl(state)).toBe("/api/v1/workflows/overseas/agent/crm/reports/applications.csv?date_from=2026-01-01&country=aland");
  });
});

describe("csvFilename", () => {
  it("matches the server's attachment name", () => {
    expect(csvFilename("countries", "", "2026-09-30")).toBe("agency-countries-all-to-2026-09-30.csv");
  });
});

describe("isAgentReport", () => {
  const report = { kind: "countries", title: "t", scope: "agency", columns: [], items: [], totals: null, total: 0, limit: 0, offset: 0, options: {}, as_of: "2026-10-03T00:00:00Z" };

  it("accepts a report", () => expect(isAgentReport(report)).toBe(true));
  it.each([null, {}, { ...report, columns: undefined }, { ...report, items: "x" }])("rejects %j", (value) => expect(isAgentReport(value)).toBe(false));
});
