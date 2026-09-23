import { describe, expect, it, vi } from "vitest";

const { serverApi } = vi.hoisted(() => ({ serverApi: vi.fn() }));
vi.mock("@/lib/api", () => ({ serverApi }));

import { loadStudent360 } from "@/lib/student360";
import { isTabKey, safeHref, student360Href, TAB_KEYS, TAB_LABELS } from "@/lib/student360Links";

describe("student360 library", () => {
  it("loads through serverApi (per-request, never cached)", async () => {
    serverApi.mockResolvedValue({ ok: true });
    await loadStudent360("abc");
    expect(serverApi).toHaveBeenCalledWith("/api/v1/school/students/abc/360-view");
  });

  it("has sixteen labelled tabs in display order", () => {
    expect(TAB_KEYS).toHaveLength(16);
    expect(TAB_KEYS[0]).toBe("overview");
    expect(TAB_KEYS[15]).toBe("edusphere_programs");
    for (const k of TAB_KEYS) expect(TAB_LABELS[k]).toBeTruthy();
  });

  it("recognises only real tab keys", () => {
    expect(isTabKey("skills")).toBe(true);
    expect(isTabKey("<script>")).toBe(false);
    expect(isTabKey(undefined)).toBe(false);
  });

  it.each([
    ["school_coordinator", "/school/coordinator/students/s1/360"],
    ["school_principal", "/school/principal/students/s1/360"],
    ["school_teacher", "/school/teacher/students/s1/360"],
    ["school_parent", "/school/parent/children/s1/360"],
    ["academic_team", "/school/academic-team/students/s1/360"],
    ["career_counselor", "/school/career-counselor/students/s1/360"],
    ["psychometric_team", "/school/psychometric-team/students/s1/360"],
    ["overseas_admin", null],
  ])("builds the %s route", (role, href) => {
    expect(student360Href(role, "s1")).toBe(href);
  });

  it.each([
    ["/local-files/uploads/r.pdf", "/local-files/uploads/r.pdf"],
    ["https://files.example.org/r.pdf", "https://files.example.org/r.pdf"],
    ["javascript:alert(1)", null],
    ["JavaScript:alert(1)", null],
    ["data:text/html,<b>x</b>", null],
    ["//evil.example/r.pdf", null],
    ["/\\evil.example", null],
    ["http://plain.example/r.pdf", null],
    ["", null],
    [null, null],
  ])("safeHref(%j) -> %j", (input, expected) => {
    expect(safeHref(input)).toBe(expected);
  });
});
