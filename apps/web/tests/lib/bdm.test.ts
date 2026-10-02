import { afterEach, describe, expect, it, vi } from "vitest";

import { BDM_TYPE_LABEL, creatableTypes, managerSearch, statusLabel } from "@/lib/bdm";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("managerSearch (bdm-001 QA-02/QA-03)", () => {
  it("queries the picker endpoint and shows the manager's email as the detail", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [{ id: "m1", full_name: "Meera", email: "m@x.local" }], total: 30, limit: 20, offset: 0 }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const page = await managerSearch("mee ra", new AbortController().signal);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/admin/bdm-managers?limit=20&q=mee+ra");
    expect(page).toEqual({ items: [{ id: "m1", label: "Meera", detail: "m@x.local" }], truncated: true });
  });

  it("throws on a failed response so the picker offers Retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 500 })));
    await expect(managerSearch("", new AbortController().signal)).rejects.toThrow();
  });
});

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
