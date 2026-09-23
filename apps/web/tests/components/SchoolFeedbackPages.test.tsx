import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolCoordinatorFeedbackPage from "@/app/school/coordinator/feedback/page";
import SchoolPrincipalFeedbackPage from "@/app/school/principal/feedback/page";
import { serverApi } from "@/lib/api";

// ENH-018 browser QA: QA-018-12 (each Feedback page refuses the other role instead of rendering a form it cannot submit or a
// mislabelled shell) and QA-018-09 (?activity=<id> narrows the coordinator page to that one activity). serverApi reads next/headers
// cookies, so it is mocked; the shell and the panel are stubbed -- this is about who sees the page and what it asks the API for.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children, roleLabel }: { children: React.ReactNode; roleLabel: string }) => <div data-testid="shell" data-role={roleLabel}>{children}</div> }));
vi.mock("@/components/SchoolActivityFeedbackPanel", () => ({
  default: ({ canSubmit, focusActivityId }: { canSubmit: boolean; focusActivityId?: string }) => <div data-testid="panel" data-submit={String(canSubmit)} data-focus={focusActivityId ?? ""} />,
}));

const ID = "0f8fad5b-d9cb-469f-a165-70867728950e";
const page = { items: [], total: 0, limit: 25, offset: 0 };
const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "overseas", profile: { school_id: "s1" } });
const params = (activity?: string) => ({ searchParams: Promise.resolve(activity === undefined ? {} : { activity }) });

function serve(role: string) {
  const requested: string[] = [];
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    requested.push(path);
    if (path === "/api/v1/auth/me") return user(role) as never;
    if (path.startsWith("/api/v1/school/activity-feedback")) return page as never;
    throw new Error(`unexpected request ${path}`);
  });
  return requested;
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

describe("Feedback pages", () => {
  it("coordinator page: the coordinator gets the submit panel", async () => {
    serve("school_coordinator");
    render(await SchoolCoordinatorFeedbackPage(params()));
    expect(screen.getByTestId("panel").dataset.submit).toBe("true");
    expect(screen.getByTestId("shell").dataset.role).toBe("School Coordinator");
  });

  it("coordinator page: a principal is refused, never shown a form they cannot submit (QA-018-12)", async () => {
    serve("school_principal");
    render(await SchoolCoordinatorFeedbackPage(params()));
    expect(screen.getByText("School Coordinator role required")).toBeTruthy();
    expect(screen.queryByTestId("panel")).toBeNull();
    expect(screen.getByRole("link", { name: "Go to your dashboard" })).toHaveAttribute("href", "/school/principal/dashboard");
  });

  it("principal page: a coordinator is refused rather than shown a shell labelled Principal (QA-018-12)", async () => {
    serve("school_coordinator");
    render(await SchoolPrincipalFeedbackPage());
    expect(screen.getByText("Principal role required")).toBeTruthy();
    expect(screen.queryByTestId("panel")).toBeNull();
  });

  it("principal page: the principal reads, read-only", async () => {
    serve("school_principal");
    render(await SchoolPrincipalFeedbackPage());
    expect(screen.getByTestId("panel").dataset.submit).toBe("false");
  });

  it("?activity=<id> asks the API for just that activity and focuses it (QA-018-09)", async () => {
    const requested = serve("school_coordinator");
    render(await SchoolCoordinatorFeedbackPage(params(ID)));
    expect(requested).toContain(`/api/v1/school/activity-feedback?status=all&limit=25&offset=0&activity_id=${ID}`);
    expect(screen.getByTestId("panel").dataset.focus).toBe(ID);
  });

  it("a malformed ?activity= is ignored rather than turned into an error page", async () => {
    const requested = serve("school_coordinator");
    render(await SchoolCoordinatorFeedbackPage(params("not-a-uuid")));
    expect(requested).toContain("/api/v1/school/activity-feedback?status=all&limit=25&offset=0");
    expect(screen.getByTestId("panel").dataset.focus).toBe("");
  });
});
