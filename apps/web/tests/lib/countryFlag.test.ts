import { readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { flagSrc } from "@/lib/countryFlag";

describe("flagSrc", () => {
  it("maps a two-letter code to the lower-case SVG path", () => {
    expect(flagSrc("GB")).toBe("/flags/gb.svg");
    expect(flagSrc("gb")).toBe("/flags/gb.svg");
    expect(flagSrc(" ae ")).toBe("/flags/ae.svg");
  });
  it.each([null, undefined, "", "  ", "G", "G1", "GBR", "../x", "g/"])("returns null for %j", (value) => {
    expect(flagSrc(value as string | null | undefined)).toBeNull();
  });
});

describe("public/flags", () => {
  const files = readdirSync(join(process.cwd(), "public", "flags")).filter((f) => f.endsWith(".svg"));
  it("holds only two-letter lower-case SVGs", () => {
    expect(files.length).toBeGreaterThan(240);
    for (const f of files) expect(f).toMatch(/^[a-z]{2}\.svg$/);
  });
  it("has the six published destinations", () => {
    for (const code of ["gb", "au", "us", "ae", "fr", "de"]) expect(files).toContain(`${code}.svg`);
  });
});
