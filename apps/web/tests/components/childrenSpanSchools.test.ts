import { describe, expect, it, vi } from "vitest";

import { childrenSpanSchools, type ChildOverview } from "@/components/SchoolChildOverview";

// ENH-005 (spec §7.1, AC-25): after a transfer a parent can have children at two schools, so a child's card must then name its school.
// A single-school parent's dashboard must stay exactly as it was. `serverApi` reads next/headers cookies, so it is mocked.
vi.mock("@/lib/api", () => ({ serverApi: vi.fn() }));

const overview = (school: string | null) => ({ student: { school_name: school } }) as unknown as ChildOverview;

describe("childrenSpanSchools", () => {
  it("is false for no children, one child, or several children at the same school", () => {
    expect(childrenSpanSchools([])).toBe(false);
    expect(childrenSpanSchools([overview("Sunrise School")])).toBe(false);
    expect(childrenSpanSchools([overview("Sunrise School"), overview("Sunrise School")])).toBe(false);
  });

  it("is true once the children are at different schools", () => {
    expect(childrenSpanSchools([overview("Sunrise School"), overview("Lakeview School")])).toBe(true);
  });

  it("ignores a child whose overview could not be loaded or has no school name", () => {
    expect(childrenSpanSchools([overview("Sunrise School"), null])).toBe(false);
    expect(childrenSpanSchools([overview("Sunrise School"), overview(null)])).toBe(false);
    expect(childrenSpanSchools([null, null])).toBe(false);
  });
});
