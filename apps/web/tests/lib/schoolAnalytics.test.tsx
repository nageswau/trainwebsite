import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { serverApi } = vi.hoisted(() => ({ serverApi: vi.fn() }));
vi.mock("@/lib/api", () => ({ serverApi }));

import SchoolAnalyticsSections from "@/components/SchoolAnalyticsSections";
import { THRESHOLD_ORDER_ERROR, THRESHOLD_RANGE_ERROR, loadSchoolAnalytics } from "@/lib/schoolAnalytics";

afterEach(cleanup);
beforeEach(() => serverApi.mockReset());

describe("loadSchoolAnalytics (ENH-016)", () => {
  it("forwards only allow-listed URL values to the API", async () => {
    serverApi.mockResolvedValue({ grades: [], students: {}, metrics: [] });
    const data = await loadSchoolAnalytics({ grade: "10&limit=1000", offset: "-5", at_risk_below: "30", top_from: "85;drop" });
    const paths = serverApi.mock.calls.map(([p]) => p as string);
    // QA-016-05: a malformed threshold is no longer dropped silently -- both fall back to the defaults, with a reason.
    expect(paths).toContain("/api/v1/school/analytics/student-development?");
    expect(paths).toContain("/api/v1/school/analytics/scorecards?offset=0");
    expect(data.grade).toBe("");
    expect(data.thresholdError).toBe(THRESHOLD_RANGE_ERROR);
    expect(data.thresholds).toEqual({});
  });

  it("an in-order pair outside 0-100 never reaches the API; it explains the range (QA-016-05)", async () => {
    serverApi.mockResolvedValue(null);
    const data = await loadSchoolAnalytics({ at_risk_below: "150", top_from: "200" });
    expect(serverApi.mock.calls.map(([p]) => String(p))).toContain("/api/v1/school/analytics/student-development?");
    expect(data.thresholdError).toBe(THRESHOLD_RANGE_ERROR);
    expect((await loadSchoolAnalytics({ at_risk_below: "150", top_from: "85" })).thresholdError).toBe(THRESHOLD_RANGE_ERROR);
  });

  it("returns accepted thresholds so the grid form can carry them (QA-016-12)", async () => {
    serverApi.mockResolvedValue(null);
    const data = await loadSchoolAnalytics({ at_risk_below: "30", top_from: "90" });
    expect(data.thresholds).toEqual({ at_risk_below: "30", top_from: "90" });
    expect(data.thresholdError).toBeNull();
  });

  it("keeps a valid grade and offset", async () => {
    serverApi.mockResolvedValue(null);
    await loadSchoolAnalytics({ grade: "12", offset: "50" });
    expect(serverApi.mock.calls.map(([p]) => p)).toContain("/api/v1/school/analytics/scorecards?offset=50&grade=12");
  });

  it("drops an out-of-order threshold pair instead of losing the section, and says why (final review, Important 2)", async () => {
    serverApi.mockResolvedValue(null);
    const both = await loadSchoolAnalytics({ at_risk_below: "90", top_from: "85" });
    const oneSided = await loadSchoolAnalytics({ at_risk_below: "90" }); // against the default top_from of 85
    const paths = serverApi.mock.calls.map(([p]) => String(p)).filter((p) => p.includes("student-development"));
    expect(paths).toEqual(["/api/v1/school/analytics/student-development?", "/api/v1/school/analytics/student-development?"]);
    expect(both.thresholdError).toBe(THRESHOLD_ORDER_ERROR);
    expect(oneSided.thresholdError).toBe(THRESHOLD_ORDER_ERROR);
    expect((await loadSchoolAnalytics({ at_risk_below: "30", top_from: "90" })).thresholdError).toBeNull();
  });

  it("clamps a huge offset to the API's bound", async () => {
    serverApi.mockResolvedValue(null);
    await loadSchoolAnalytics({ offset: "100000000000000000000" });
    expect(serverApi.mock.calls.map(([p]) => String(p))).toContain("/api/v1/school/analytics/scorecards?offset=10000");
  });

  it("turns each failed section into null without failing the others", async () => {
    // String(...): the harness also probes the mocked module once with no arguments.
    serverApi.mockImplementation((...args: unknown[]) => (String(args[0]).includes("grade-performance") ? Promise.reject(new Error("boom")) : Promise.resolve({ items: [], total: 0, limit: 25, offset: 0 })));
    const data = await loadSchoolAnalytics({});
    expect(data.grades).toBeNull();
    expect(data.scorecards).not.toBeNull();
  });
});

describe("SchoolAnalyticsSections", () => {
  it("shows the unavailable card for every missing section", () => {
    render(<SchoolAnalyticsSections data={{ grade: "", thresholds: {}, grades: null, development: null, scorecards: null, thresholdError: null }} role="principal" />);
    expect(screen.getAllByRole("status")).toHaveLength(3);
    expect(screen.getByRole("heading", { name: "Student progress scorecards" })).toBeInTheDocument();
  });
});
