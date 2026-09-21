import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// A "use client" component must not import anything that reaches `next/headers` (a server-only module). Vitest does not enforce that
// boundary -- only `next build` does -- so ENH-005's first production build failed on it (client components imported `formatDate` from
// SchoolChildOverview, which imports `serverApi`). This reads the sources and catches the same mistake without a build.
const COMPONENTS = path.resolve(__dirname, "../../components");
const SERVER_ONLY = ["@/lib/api", "@/components/SchoolChildOverview", "@/components/SchoolGradeHistory", "@/components/SchoolStudentTimeline", "@/components/SchoolTransferHistory", "next/headers"];

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
});
