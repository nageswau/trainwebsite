import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import FundingPage from "@/app/school/career-counselor/funding/page";
import { serverApi } from "@/lib/api";

vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/SchoolFundingRecordsPanel", () => ({ default: () => <div>funding panel</div> }));

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

function serve(role: string) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return { id: "u1", email: "u@example.local", full_name: "Test User", role, division: "overseas", profile: {} } as never;
    if (path === "/api/v1/school/career-counselor/funding-records" || path === "/api/v1/school/portfolio-students") return [] as never;
    throw new Error(`unexpected request ${path}`);
  });
}

// QA-03 (browser QA 2026-10-01): a coordinator saw one of two refusal messages at random -- the page's three reads ran in parallel and
// whichever was refused first won. The role is now checked before anything else is read.
describe("counsellor funding page access", () => {
  it.each(["school_coordinator", "school_principal", "school_teacher", "school_parent", "academic_team"])("refuses %s with one message, before reading any cases", async (role) => {
    serve(role);
    render(await FundingPage());
    expect(screen.getByText("Career Counselor role required")).toBeInTheDocument();
    expect(screen.queryByText("funding panel")).not.toBeInTheDocument();
    const paths = vi.mocked(serverApi).mock.calls.map(([path]) => path);
    expect(paths).toEqual(["/api/v1/auth/me"]);
  });

  it("shows the panel to a career counsellor", async () => {
    serve("career_counselor");
    render(await FundingPage());
    expect(screen.getByText("funding panel")).toBeInTheDocument();
  });
});
