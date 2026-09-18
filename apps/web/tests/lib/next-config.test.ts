import { describe, expect, it } from "vitest";

import nextConfig from "../../next.config";

// ENH-003 security review: the reset / set-password link carries a live token in its query string.
describe("next.config security headers for the reset page", () => {
  it("sends Referrer-Policy: no-referrer and no-store for both divisions' reset-password routes", async () => {
    const rules = await nextConfig.headers!();
    const rule = rules.find((r) => r.source === "/:division(it|overseas)/reset-password");
    expect(rule).toBeDefined();
    const headers = Object.fromEntries(rule!.headers.map((h) => [h.key, h.value]));
    expect(headers["Referrer-Policy"]).toBe("no-referrer");
    expect(headers["Cache-Control"]).toBe("no-store");
  });

  it("keeps the existing build settings", () => {
    expect(nextConfig.output).toBe("standalone");
    expect(nextConfig.poweredByHeader).toBe(false);
  });
});
