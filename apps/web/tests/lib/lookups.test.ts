import { afterEach, describe, expect, it, vi } from "vitest";

import { lookupSearch, optionText } from "@/lib/lookups";

afterEach(() => vi.unstubAllGlobals());

describe("lookups client (ENH-031)", () => {
  it("builds the lookup URL with q, limit and non-empty params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [], truncated: false })));
    vi.stubGlobal("fetch", fetchMock);
    await lookupSearch("overseas-applications", { student_id: "s1", empty: undefined })("Asha", new AbortController().signal);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/lookups/overseas-applications?limit=20&q=Asha&student_id=s1");
  });

  it("omits q when blank and throws on a failed response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 403 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(lookupSearch("schools")("", new AbortController().signal)).rejects.toThrow("Lookup failed (403)");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/lookups/schools?limit=20");
  });

  it("joins label and detail for display", () => {
    expect(optionText({ id: "1", label: "Asha", detail: "asha@example.local" })).toBe("Asha — asha@example.local");
    expect(optionText({ id: "1", label: "Asha" })).toBe("Asha");
  });
});
