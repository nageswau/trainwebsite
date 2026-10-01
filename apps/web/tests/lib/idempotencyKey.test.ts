import { afterEach, describe, expect, it, vi } from "vitest";
import { newIdempotencyKey } from "@/lib/idempotencyKey";

// QA-029-01: `crypto.randomUUID` exists only in secure contexts (HTTPS or localhost); `crypto.getRandomValues` exists everywhere.
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

afterEach(() => vi.unstubAllGlobals());

describe("newIdempotencyKey", () => {
  it("uses crypto.randomUUID when the browser provides it", () => {
    vi.stubGlobal("crypto", { randomUUID: () => "from-random-uuid", getRandomValues: crypto.getRandomValues.bind(crypto) });
    expect(newIdempotencyKey()).toBe("from-random-uuid");
  });

  it("builds a version-4 UUID from getRandomValues on a plain-HTTP page, where randomUUID is missing", () => {
    vi.stubGlobal("crypto", { getRandomValues: crypto.getRandomValues.bind(crypto) });
    const keys = new Set(Array.from({ length: 200 }, () => newIdempotencyKey()));
    expect(keys.size).toBe(200);
    for (const key of keys) expect(key).toMatch(UUID_V4);
  });
});
