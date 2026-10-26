import { beforeEach, describe, expect, it, vi } from "vitest";

import StudentSearch from "@/components/StudentSearch";
import StudentSearchPage from "@/components/StudentSearchPage";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const it_admin = { id: "u", role: "it_admin", full_name: "Ira", division: "it", email: "i@x", profile: {} };
const props = { base: "/it/admin/student-search", role: "it_admin" as const, nav: PORTAL_NAV["it/admin"], roleLabel: "IT Administrator", loginHref: "/it/login" };
const PROGRAMS = [{ id: "p1", title: "Python" }];
const result = { q: "Asha", groups: { it_student: { items: [], more: false } } };
const signedInAs = (user: unknown, search: unknown = result) =>
  vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/auth/me" ? user : path === "/api/v1/admin/programs" ? PROGRAMS : search) as never);
const calls = () => vi.mocked(serverApi).mock.calls.map(([path]) => path).filter((path) => path !== "/api/v1/auth/me");
const PROGRAM_ID = "6f1c1a52-8d5b-4f7e-9a0e-0c1d2e3f4a5b";

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});

describe("StudentSearchPage (nehn-041)", () => {
  it("shows only the form, and asks nothing, before a search is typed", async () => {
    signedInAs(it_admin);
    const tree = elements(await StudentSearchPage({ ...props, searchParams: {} }));
    expect(calls()).toEqual(["/api/v1/admin/programs"]);
    const search = tree.find((el) => el.type === StudentSearch)!;
    expect(search.props.result).toBeNull();
    expect(search.props.error).toBe("");
    expect(search.props.kinds).toEqual(["it_student"]);
    expect(search.props.programs).toEqual(PROGRAMS);
  });

  it("searches with the address's filters and hands the result to the cards", async () => {
    signedInAs(it_admin);
    const tree = elements(await StudentSearchPage({ ...props, searchParams: { q: " Asha ", program: PROGRAM_ID, type: "bogus" } }));
    expect(calls()).toContain(`/api/v1/search/students?q=Asha&program=${PROGRAM_ID}`);
    expect(tree.find((el) => el.type === StudentSearch)!.props.result).toEqual(result);
  });

  it("explains a too-short search without asking the API", async () => {
    signedInAs(it_admin);
    const tree = elements(await StudentSearchPage({ ...props, searchParams: { q: "a" } }));
    expect(calls().some((path) => path.startsWith("/api/v1/search"))).toBe(false);
    expect(tree.find((el) => el.type === StudentSearch)!.props.error).toBe("Type at least 3 characters.");
  });

  it("gives the Overseas Admin no program filter (only IT admins read programs)", async () => {
    signedInAs({ ...it_admin, role: "overseas_admin", division: "overseas" });
    const tree = elements(await StudentSearchPage({ ...props, base: "/overseas/admin/student-search", role: "overseas_admin", nav: PORTAL_NAV["overseas/admin"], roleLabel: "Overseas Administrator", loginHref: "/overseas/login", searchParams: {} }));
    expect(calls()).toEqual([]);
    const search = tree.find((el) => el.type === StudentSearch)!;
    expect(search.props.programs).toBeNull();
    expect(search.props.kinds).toEqual(["overseas_student", "agency_student"]);
  });

  it("refuses any other role before searching", async () => {
    signedInAs({ ...it_admin, role: "super_admin", division: "global" });
    const tree = elements(await StudentSearchPage({ ...props, searchParams: { q: "Asha" } }));
    expect(calls()).toEqual([]);
    expect(tree.find((el) => typeof el.props.message === "string")!.props.message).toBe("IT Administrator role required");
  });

  it("shows the API's worded refusal (e.g. the 30-a-minute limit) and a generic message on other failures", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { ...it_admin, role: "super_admin", division: "global" } as never;
      if (path === "/api/v1/admin/programs") return PROGRAMS as never;
      throw new ApiError("Too many searches; try again in 12 seconds", 429);
    });
    const superProps = { ...props, base: "/admin/student-search", role: "super_admin" as const, nav: SUPER_ADMIN_NAV, roleLabel: "Super Administrator", loginHref: "/admin/login" };
    let tree = elements(await StudentSearchPage({ ...superProps, searchParams: { q: "Asha" } }));
    expect(tree.find((el) => el.type === StudentSearch)!.props.error).toBe("Too many searches; try again in 12 seconds");
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { ...it_admin, role: "super_admin", division: "global" } as never;
      if (path === "/api/v1/admin/programs") return PROGRAMS as never;
      throw new ApiError("boom", 500);
    });
    tree = elements(await StudentSearchPage({ ...superProps, searchParams: { q: "Asha" } }));
    expect(tree.find((el) => el.type === StudentSearch)!.props.error).toBe("Student search is unavailable right now. Please try again.");
  });

  it("still searches when the program list cannot be read", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return it_admin as never;
      if (path === "/api/v1/admin/programs") throw new ApiError("boom", 500);
      return result as never;
    });
    const tree = elements(await StudentSearchPage({ ...props, searchParams: { q: "Asha" } }));
    const search = tree.find((el) => el.type === StudentSearch)!;
    expect(search.props.programs).toBeNull();
    expect(search.props.result).toEqual(result);
  });
});
