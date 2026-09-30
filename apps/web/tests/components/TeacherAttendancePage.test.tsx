import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTeacherAttendancePage from "@/app/school/teacher/attendance/page";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-030 spec §6: the page reads the roster for ?date= (passed on only when it is a well-formed YYYY-MM-DD) and hands it to the client
// form; a refused read (403/422) renders the shared Access-unavailable card with the server's message. Same shape as
// AdminSchoolAnalyticsPage.test.tsx: serverApi is mocked (it reads next/headers cookies) and the shell records its nav.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));
const shellNav = vi.hoisted(() => ({ current: [] as { href: string }[] }));
vi.mock("@/components/PortalShell", () => ({
  default: ({ nav, children }: { nav: { href: string }[]; children: React.ReactNode }) => {
    shellNav.current = nav;
    return <div data-testid="shell">{children}</div>;
  },
}));

const ME = { id: "t1", email: "t@example.local", full_name: "Tara Teacher", role: "school_teacher", division: "overseas", profile: {} };
const ROSTER = { session_date: "2026-09-29", today: "2026-09-30", students: [{ id: "s1", full_name: "Asha Rao", grade_or_class: "Grade 5", status: null }] };
const calls: string[] = [];

function serve(roster: (path: string) => unknown) {
  calls.length = 0;
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    calls.push(path);
    return (path === "/api/v1/auth/me" ? ME : roster(path)) as never;
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("Teacher attendance page", () => {
  it("loads the roster for the requested date inside the teacher's shell", async () => {
    serve(() => ROSTER);
    render(await SchoolTeacherAttendancePage({ searchParams: Promise.resolve({ date: "2026-09-29" }) }));
    expect(calls).toContain("/api/v1/school/attendance?date=2026-09-29");
    expect(shellNav.current).toBe(SCHOOL_NAV.teacher);
    expect(screen.getByRole("heading", { level: 1, name: "Attendance" })).toBeTruthy();
    expect(screen.getByRole("group", { name: /Asha Rao/ })).toBeTruthy();
  });

  it("ignores a malformed date and asks for the school's today", async () => {
    serve(() => ROSTER);
    await SchoolTeacherAttendancePage({ searchParams: Promise.resolve({ date: "../../admin" }) });
    expect(calls).toContain("/api/v1/school/attendance");
    expect(calls.some((c) => c.includes("admin"))).toBe(false);
  });

  it("QA30-03: an impossible calendar date (well-formed but not a real day) falls back to today, never '[object Object]'", async () => {
    serve(() => ROSTER);
    for (const bad of ["2026-02-30", "2026-13-01", "2026-00-10", "2025-02-29"]) {
      calls.length = 0;
      await SchoolTeacherAttendancePage({ searchParams: Promise.resolve({ date: bad }) });
      expect(calls, bad).toContain("/api/v1/school/attendance");
    }
    calls.length = 0;
    await SchoolTeacherAttendancePage({ searchParams: Promise.resolve({ date: "2024-02-29" }) }); // a real leap day passes through
    expect(calls).toContain("/api/v1/school/attendance?date=2024-02-29");
  });

  it("shows the server's reason when the roster cannot be read", async () => {
    serve(() => {
      throw new ApiError("Attendance cannot be marked for a future date", 422);
    });
    render(await SchoolTeacherAttendancePage({ searchParams: Promise.resolve({ date: "2099-01-01" }) }));
    expect(screen.getByRole("heading", { name: "Access unavailable" })).toBeTruthy();
    expect(screen.getByText("Attendance cannot be marked for a future date")).toBeTruthy();
  });
});
