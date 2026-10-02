import { describe, expect, it } from "vitest";

import { BDM_TYPE_LABEL, creatableTypes, statusLabel } from "@/lib/bdm";

describe("lib/bdm (bdm-001)", () => {
  it("mirrors the server's creator matrix, for display only", () => {
    expect(creatableTypes("super_admin")).toEqual(["agent", "school", "college"]);
    expect(creatableTypes("it_admin")).toEqual(["college"]);
    expect(creatableTypes("overseas_admin")).toEqual(["agent", "school"]);
    expect(creatableTypes("counselor")).toEqual([]);
  });

  it("labels types and status in words", () => {
    expect(BDM_TYPE_LABEL).toEqual({ agent: "Agent", school: "School", college: "College" });
    expect(statusLabel(true)).toBe("Active");
    expect(statusLabel(false)).toBe("Inactive");
  });
});
