import { afterEach, describe, expect, it, vi } from "vitest";

import { NOT_COMPLETED, sendJson } from "@/lib/apiErrors";

afterEach(() => vi.unstubAllGlobals());

// ENH-022: the one write helper the older School panels share for their save-failure path.
describe("sendJson", () => {
  it("returns the server's string detail on a 403", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, json: async () => ({ detail: "This school has no active partnership tier." }) }));
    expect(await sendJson("/x", "POST", {})).toEqual({ ok: false, message: "This school has no active partnership tier.", status: 403, detail: "This school has no active partnership tier." });
  });

  it("passes a 422's raw detail through, so a form can put the error on its field (AGN-013 QA13-09)", async () => {
    const detail = [{ loc: ["body", "university_student_id"], msg: "Value error, too long" }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail }) }));
    expect(await sendJson("/x", "PUT", {})).toEqual({ ok: false, message: "Too long", status: 422, detail });
  });

  it("never throws on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    expect(await sendJson("/x", "PATCH", {})).toEqual({ ok: false, message: NOT_COMPLETED });
  });

  it("falls back to a generic message for a non-JSON error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 502, json: async () => { throw new Error("not json"); } }));
    expect(await sendJson("/x", "POST", {})).toEqual({ ok: false, message: "Something went wrong.", status: 502 });
  });

  it("reports the HTTP status of a failed response, and none for a network failure (QA27-03/-04)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 401, json: async () => ({ detail: "Not authenticated" }) }));
    expect(await sendJson("/x", "PATCH", {})).toEqual({ ok: false, message: "Not authenticated", status: 401, detail: "Not authenticated" });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const failed = await sendJson("/x", "PATCH", {});
    expect(failed.ok || failed.status).toBeUndefined();
  });

  it("returns the JSON body on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, status: 201, json: async () => ({ id: "a1" }) });
    vi.stubGlobal("fetch", fetchMock);
    expect(await sendJson("/x", "POST", { a: 1 })).toEqual({ ok: true, data: { id: "a1" } });
    expect(fetchMock).toHaveBeenCalledWith("/x", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ a: 1 }) });
  });
});
