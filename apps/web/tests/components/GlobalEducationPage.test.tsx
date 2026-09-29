import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CoordinatorPage from "@/app/school/coordinator/global-education/page";
import PrincipalPage from "@/app/school/principal/global-education/page";
import { ApiError, serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";

vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children, roleLabel }: { children: React.ReactNode; roleLabel: string }) => <div data-testid="shell" data-role={roleLabel}>{children}</div> }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "overseas", profile: { school_id: "s1" } });
const pipeline = { grade: null, students_in_scope: 0, bridged_students: 0, funnel: [], not_tracked: [], students: { items: [], total: 0, limit: 25, offset: 0 } };
const params = (p: Record<string, string> = {}) => ({ searchParams: Promise.resolve(p) });

function serve(role: string, pipelineResult: unknown = pipeline) {
  const requested: string[] = [];
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    requested.push(path);
    if (path === "/api/v1/auth/me") return user(role) as never;
    if (path.startsWith("/api/v1/school/global-education/pipeline")) {
      if (pipelineResult instanceof Error) throw pipelineResult;
      return pipelineResult as never;
    }
    throw new Error(`unexpected request ${path}`);
  });
  return requested;
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("Global education pages", () => {
  it("coordinator page renders inside the coordinator shell with an h1", async () => {
    serve("school_coordinator");
    render(await CoordinatorPage(params()));
    expect(screen.getByTestId("shell").dataset.role).toBe("School Coordinator");
    expect(screen.getByRole("heading", { level: 1, name: "Global education" })).toBeTruthy();
  });

  it("principal page renders inside the principal shell", async () => {
    serve("school_principal");
    render(await PrincipalPage(params()));
    expect(screen.getByTestId("shell").dataset.role).toBe("Principal");
  });

  it("each page refuses the other school role instead of a mislabelled shell", async () => {
    serve("school_principal");
    render(await CoordinatorPage(params()));
    expect(screen.getByText("School Coordinator role required")).toBeTruthy();
    cleanup();
    serve("school_coordinator");
    render(await PrincipalPage(params()));
    expect(screen.getByText("Principal role required")).toBeTruthy();
  });

  it("forwards digit-only grade/offset and drops anything else (Review Focus 5)", async () => {
    const requested = serve("school_coordinator");
    render(await CoordinatorPage(params({ grade: "12", offset: "25" })));
    expect(requested).toContain("/api/v1/school/global-education/pipeline?grade=12&offset=25");
    cleanup();
    const again = serve("school_coordinator");
    render(await CoordinatorPage(params({ grade: "abc", offset: "-5" })));
    expect(again).toContain("/api/v1/school/global-education/pipeline");
  });

  it("drops an out-of-range grade/offset and forwards the boundary values", async () => {
    const bare = serve("school_coordinator");
    render(await CoordinatorPage(params({ grade: "13", offset: "20000" })));
    expect(bare.filter((p) => p.includes("pipeline"))).toEqual(["/api/v1/school/global-education/pipeline"]);
    cleanup();
    const edge = serve("school_coordinator");
    render(await CoordinatorPage(params({ grade: "8", offset: "10000" })));
    expect(edge).toContain("/api/v1/school/global-education/pipeline?grade=8&offset=10000");
  });

  it("a pipeline failure keeps the shell and shows the section error", async () => {
    serve("school_coordinator", new ApiError("boom", 500));
    render(await CoordinatorPage(params()));
    expect(screen.getByTestId("shell")).toBeTruthy();
    expect(screen.getByText("This section couldn't load. Refresh to try again.")).toBeTruthy();
  });

  it("a 403 from the pipeline shows the access card", async () => {
    serve("school_coordinator", new ApiError("School Coordinator or Principal role required", 403));
    render(await CoordinatorPage(params()));
    expect(screen.getByText("Access unavailable")).toBeTruthy();
    expect(screen.queryByTestId("shell")).toBeNull();
  });

  it("nav lists Global Education for coordinator and principal only", () => {
    expect(SCHOOL_NAV.coordinator.map((i) => i.href)).toContain("/school/coordinator/global-education");
    expect(SCHOOL_NAV.principal.map((i) => [i.label, i.href])).toContainEqual(["Global Education", "/school/principal/global-education"]);
    expect(SCHOOL_NAV.teacher.map((i) => i.href)).not.toContain("/school/teacher/global-education");
  });
});
