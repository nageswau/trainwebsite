import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// ENH-003 / DEC-SCOPE-019: no admin ever knows or chooses a credential for an account they provision.
// Guards the shipped UI source (not tests) against the retired default password and the
// "Temporary password" field coming back. Built in two parts so this file never matches itself.
const RETIRED_DEFAULT = "Change" + "Me@12345";
const TEMP_PASSWORD_FIELD = "Temporary " + "password";
const ROOT = path.resolve(__dirname, "../..");
const SOURCE_DIRS = ["app", "components", "lib"];

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "node_modules" || name === ".next" ? [] : sourceFiles(full);
    return /\.(tsx?|css)$/.test(name) ? [full] : [];
  });
}

describe("no default or temporary password in the shipped UI", () => {
  const files = SOURCE_DIRS.flatMap((dir) => sourceFiles(path.join(ROOT, dir)));

  it("scans a meaningful number of source files", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it("does not contain the retired default password anywhere", () => {
    const offenders = files.filter((file) => readFileSync(file, "utf8").includes(RETIRED_DEFAULT)).map((file) => path.relative(ROOT, file));
    expect(offenders).toEqual([]);
  });

  it('does not ask an admin for a "Temporary password" when creating an account', () => {
    const offenders = files.filter((file) => readFileSync(file, "utf8").includes(TEMP_PASSWORD_FIELD)).map((file) => path.relative(ROOT, file));
    expect(offenders).toEqual([]);
  });
});
