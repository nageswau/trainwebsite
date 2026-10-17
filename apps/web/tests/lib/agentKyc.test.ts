import { describe, expect, it } from "vitest";

import { KYC_DOCS } from "@/lib/agentKyc";

// Browsers compile the HTML `pattern` attribute with the `v` flag and silently ignore one that fails to compile.
function re(type: string) {
  const doc = KYC_DOCS.find((d) => d.type === type)!;
  return new RegExp(`^(?:${doc.pattern})$`, "v");
}

describe("KYC_DOCS patterns (AGN-024)", () => {
  it("every pattern compiles under the v flag", () => {
    for (const doc of KYC_DOCS) expect(() => new RegExp(`^(?:${doc.pattern})$`, "v")).not.toThrow();
  });
  it("PAN", () => {
    expect(re("pan").test("ABCDE1234F")).toBe(true);
    expect(re("pan").test("ABCD1234FF")).toBe(false);
  });
  it("Aadhaar last 4", () => {
    expect(re("aadhaar").test("1234")).toBe(true);
    expect(re("aadhaar").test("12345")).toBe(false);
  });
  it("business licence number", () => {
    for (const ok of ["LIC-2026/001", "AB 12.3"]) expect(re("business_license").test(ok)).toBe(true);
    for (const bad of ["ab", "LIC<1>"]) expect(re("business_license").test(bad)).toBe(false);
  });
});
