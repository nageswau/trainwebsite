import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, serverApi } from "@/lib/api";

vi.mock("next/headers", () => ({ cookies: async () => ({ toString: () => "edusphere_access=abc" }) }));

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

afterEach(() => vi.unstubAllGlobals());

// ENH-006 QA-002: a page that calls serverApi must be able to tell "the API said 401" (signed out) from "the API is
// down or erroring" -- the old plain Error carried only a message, so callers treated every failure as signed out.
describe("serverApi", () => {
  it("returns the parsed JSON and forwards the caller's cookies to the API", async () => {
    const mock = vi.fn().mockResolvedValue(json({ ok: true }, 200));
    vi.stubGlobal("fetch", mock);
    await expect(serverApi("/api/v1/auth/me")).resolves.toEqual({ ok: true });
    expect(mock.mock.calls[0][1].headers.cookie).toBe("edusphere_access=abc");
  });

  it("throws an ApiError that carries the HTTP status and the API's detail, and is still an Error with the same message", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ detail: "Not authenticated" }, 401)));
    const error = await serverApi("/api/v1/auth/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toBeInstanceOf(Error);
    expect((error as ApiError).status).toBe(401);
    expect((error as Error).message).toBe("Not authenticated");
  });

  it("falls back to the status line when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("Internal Server Error", { status: 500, statusText: "Internal Server Error" })));
    const error = await serverApi("/api/v1/auth/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(500);
    expect((error as Error).message).toBe("500 Internal Server Error");
  });

  it("lets a network failure through unchanged, so it is never mistaken for an HTTP answer", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const error = await serverApi("/api/v1/auth/me").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(TypeError);
    expect(error).not.toBeInstanceOf(ApiError);
  });
});
