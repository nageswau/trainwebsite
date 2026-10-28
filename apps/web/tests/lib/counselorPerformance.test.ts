import { describe, expect, it } from "vitest";

import { PERFORMANCE_API, performanceUrl } from "@/lib/counselorPerformance";

const NONE = { from: "", to: "", intake: "", division: "" };

describe("ccrm-036 performanceUrl", () => {
  it("asks for this month when no period is chosen, and carries a chosen period", () => {
    expect(performanceUrl(NONE)).toBe(PERFORMANCE_API);
    expect(performanceUrl({ ...NONE, from: "2026-05-01" })).toBe("/api/v1/counselor/performance?from=2026-05-01");
    expect(performanceUrl({ ...NONE, from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/counselor/performance?from=2026-05-01&to=2026-05-31");
  });

  it("ccrm-053: carries the intake and lead division when chosen", () => {
    expect(performanceUrl({ ...NONE, intake: "Sep 2027", division: "it" })).toBe("/api/v1/counselor/performance?intake=Sep+2027&division=it");
  });
});
