import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// A "use client" component must not import anything that reaches `next/headers` (a server-only module). Vitest does not enforce that
// boundary -- only `next build` does -- so ENH-005's first production build failed on it (client components imported `formatDate` from
// SchoolChildOverview, which imports `serverApi`). This reads the sources and catches the same mistake without a build.
const COMPONENTS = path.resolve(__dirname, "../../components");
const SERVER_ONLY = ["@/lib/api", "@/components/SchoolChildOverview", "@/components/SchoolGradeHistory", "@/components/SchoolStudentTimeline", "@/components/SchoolTransferHistory", "next/headers"];
// ENH-021: lib/portfolio.ts holds the portfolio types AND the server loader (loadPortfolio -> serverApi). Type-only imports are
// erased at compile time and stay allowed; a value import from it is what broke ENH-021's first `next build`.
const SERVER_ONLY_VALUES = ["@/lib/portfolio"];

const clientFiles = readdirSync(COMPONENTS)
  .filter((f) => f.endsWith(".tsx"))
  .map((f) => ({ file: f, source: readFileSync(path.join(COMPONENTS, f), "utf8") }))
  .filter(({ source }) => /^\s*["']use client["']/.test(source));

describe("client components stay clear of server-only imports", () => {
  it("finds the client components it is meant to guard", () => {
    const names = clientFiles.map((c) => c.file);
    for (const expected of ["SchoolTransferRequestForm.tsx", "SchoolTransfersPanel.tsx", "AdminTransferRow.tsx", "AdminSchoolTransferPanel.tsx", "SchoolIncomingTransferForm.tsx"]) {
      expect(names).toContain(expected);
    }
  });

  it.each(clientFiles.map((c) => [c.file, c.source] as const))("%s imports no server-only module", (file, source) => {
    const imports = [...source.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    const bad = imports.filter((spec) => SERVER_ONLY.includes(spec));
    expect(bad, `${file} imports a server-only module`).toEqual([]);
  });

  it.each(clientFiles.map((c) => [c.file, c.source] as const))("%s imports only types from mixed server modules", (file, source) => {
    const valueImports = [...source.matchAll(/import\s+(?!type\b)[^;]*?from\s+["']([^"']+)["']/g)].map((m) => m[1]);
    const bad = valueImports.filter((spec) => SERVER_ONLY_VALUES.includes(spec));
    expect(bad, `${file} imports runtime values from a module that reaches next/headers`).toEqual([]);
  });
});
