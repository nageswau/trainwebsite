import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { serverApi } = vi.hoisted(() => ({ serverApi: vi.fn() }));
vi.mock("@/lib/api", () => ({ serverApi }));

import SchoolAnalyticsSections from "@/components/SchoolAnalyticsSections";
import { loadSchoolAnalytics } from "@/lib/schoolAnalytics";

afterEach(cleanup);
beforeEach(() => serverApi.mockReset());

describe("loadSchoolAnalytics (ENH-016)", () => {
  it("forwards only allow-listed URL values to the API", async () => {
    serverApi.mockResolvedValue({ grades: [], students: {}, metrics: [] });
    const data = await loadSchoolAnalytics({ grade: "10&limit=1000", offset: "-5", at_risk_below: "30", top_from: "85;drop" });
    const paths = serverApi.mock.calls.map(([p]) => p as string);
    expect(paths).toContain("/api/v1/school/analytics/student-development?at_risk_below=30");
    expect(paths).toContain("/api/v1/school/analytics/scorecards?offset=0");
    expect(data.grade).toBe("");
  });

  it("keeps a valid grade and offset", async () => {
    serverApi.mockResolvedValue(null);
    await loadSchoolAnalytics({ grade: "12", offset: "50" });
    expect(serverApi.mock.calls.map(([p]) => p)).toContain("/api/v1/school/analytics/scorecards?offset=50&grade=12");
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
    render(<SchoolAnalyticsSections data={{ grade: "", grades: null, development: null, scorecards: null }} role="principal" />);
    expect(screen.getAllByRole("status")).toHaveLength(3);
    expect(screen.getByRole("heading", { name: "Student progress scorecards" })).toBeInTheDocument();
  });
});
