import { beforeEach, describe, expect, it } from "vitest";

import { gaInlineScript } from "@/components/Analytics";

function gtagCalls(path: string): string[] {
  window.history.pushState({}, "", path);
  (window as unknown as { dataLayer?: unknown[] }).dataLayer = undefined;
  (0, eval)(gaInlineScript("G-TEST"));
  return (window as unknown as { dataLayer: IArguments[] }).dataLayer.map((entry) => String(entry[0]));
}

describe("Analytics inline script", () => {
  beforeEach(() => window.history.pushState({}, "", "/"));

  it("configures GA on ordinary pages", () => {
    expect(gtagCalls("/it/programs")).toContain("config");
  });

  it("never configures GA on reset-password pages, whose URL carries a live token", () => {
    expect(gtagCalls("/overseas/reset-password?token=abc")).not.toContain("config");
    expect(gtagCalls("/it/reset-password?token=abc")).not.toContain("config");
  });
});
