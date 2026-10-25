import { describe, expect, it } from "vitest";

import { PERFORMANCE_API, performanceUrl } from "@/lib/counselorPerformance";

describe("ccrm-036 performanceUrl", () => {
  it("asks for this month when no period is chosen, and carries a chosen period", () => {
    expect(performanceUrl({ from: "", to: "" })).toBe(PERFORMANCE_API);
    expect(performanceUrl({ from: "2026-05-01", to: "" })).toBe("/api/v1/counselor/performance?from=2026-05-01");
    expect(performanceUrl({ from: "2026-05-01", to: "2026-05-31" })).toBe("/api/v1/counselor/performance?from=2026-05-01&to=2026-05-31");
  });
});
