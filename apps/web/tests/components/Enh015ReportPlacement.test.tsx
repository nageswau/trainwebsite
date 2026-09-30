import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CoordinatorReportsPage from "@/app/school/coordinator/reports/page";
import PrincipalReportsPage from "@/app/school/principal/reports/page";
import CoordinatorStudentPage from "@/app/school/coordinator/students/[id]/page";
import PrincipalStudentPage from "@/app/school/principal/students/[id]/page";
import ParentChildPage from "@/app/school/parent/children/[id]/page";
import { serverApi } from "@/lib/api";
import { SCHOOL_NAV } from "@/lib/navigation";

// ENH-015 (spec §7): the download buttons sit on existing pages; the pages' own panels are stubbed -- only placement is under test.
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/SchoolReportsPanel", () => ({ default: () => <div>reports panel</div> }));
vi.mock("@/components/SchoolAnalyticsSections", () => ({ default: () => <div>analytics</div> }));
vi.mock("@/lib/schoolAnalytics", () => ({ loadSchoolAnalytics: async () => ({}) }));
vi.mock("@/components/SchoolStudentDetailPanel", () => ({ default: () => <div>student detail</div> }));
vi.mock("@/components/StudentScorecard", () => ({ default: () => <div>scorecard</div> }));
vi.mock("@/components/SchoolChildOverview", () => ({ default: () => <div>overview</div>, loadChildOverview: async () => ({}) }));
vi.mock("@/components/SchoolGradeHistory", () => ({ default: () => null, loadGradeHistory: async () => ({ history: [] }) }));
vi.mock("@/components/SchoolStudentTimeline", () => ({ default: () => null, loadStudentTimeline: async () => ({ events: [] }) }));
vi.mock("@/components/SchoolTransferHistory", () => ({ default: () => null, loadTransferHistory: async () => [] }));
vi.mock("@/components/PortfolioPanel", () => ({ default: () => null }));
vi.mock("@/lib/portfolio", () => ({ loadPortfolio: async () => null }));

const user = (role: string) => ({ id: "u1", email: "u@example.local", full_name: "Test User", role, division: "overseas", profile: { school_id: "s1" } });

function serve(role: string) {
  vi.mocked(serverApi).mockImplementation(async (path: string) => {
    if (path === "/api/v1/auth/me") return user(role) as never;
    if (path === "/api/v1/school/reports") return {} as never;
    if (path.startsWith("/api/v1/school/students/")) return { id: "stu-1", student_code: "S1", full_name: "Kid", date_of_birth: null, grade_or_class: null } as never;
    throw new Error(`unexpected request ${path}`);
  });
}

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

const schoolButton = () => screen.getByRole("button", { name: "Download school report (PDF)" });
const studentButton = () => screen.getByRole("button", { name: "Download progress report (PDF)" });

describe("ENH-015 report download placement", () => {
  it.each([
    ["coordinator", "school_coordinator", CoordinatorReportsPage],
    ["principal", "school_principal", PrincipalReportsPage],
  ])("puts the school report download on the %s Reports page, above the existing report", async (_label, role, Page) => {
    serve(role);
    render(await Page({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { level: 2, name: "Download reports" })).toBeInTheDocument();
    expect(schoolButton().compareDocumentPosition(screen.getByText("reports panel")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it.each([
    ["coordinator", "school_coordinator", CoordinatorStudentPage],
    ["principal", "school_principal", PrincipalStudentPage],
  ])("puts the progress report download on the %s student page", async (_label, role, Page) => {
    serve(role);
    render(await Page({ params: Promise.resolve({ id: "stu-1" }) }));
    expect(screen.getByRole("heading", { level: 2, name: "Progress report" })).toBeInTheDocument();
    expect(studentButton()).toBeEnabled();
  });

  it("puts the progress report download in the parent's child page action row", async () => {
    serve("school_parent");
    render(await ParentChildPage({ params: Promise.resolve({ id: "stu-1" }) }));
    expect(studentButton()).toBeEnabled();
    expect(screen.getByRole("link", { name: "Open 360° view" }).parentElement).toContainElement(studentButton());
  });

  // QA15-04: a compact card (smaller heading, no second page padding below it) so the report stays the page's focus.
  it.each([
    ["coordinator Reports", "school_coordinator", () => CoordinatorReportsPage({ searchParams: Promise.resolve({}) }), "Download reports"],
    ["principal Reports", "school_principal", () => PrincipalReportsPage({ searchParams: Promise.resolve({}) }), "Download reports"],
    ["coordinator student", "school_coordinator", () => CoordinatorStudentPage({ params: Promise.resolve({ id: "stu-1" }) }), "Progress report"],
    ["principal student", "school_principal", () => PrincipalStudentPage({ params: Promise.resolve({ id: "stu-1" }) }), "Progress report"],
  ])("uses the compact download card on the %s page", async (_label, role, page, heading) => {
    serve(role);
    render(await page());
    expect(screen.getByRole("heading", { level: 2, name: heading }).closest(".report-downloads")).not.toBeNull();
  });

  // QA15-11: only the parent's button row narrows the hint (globals.css `.child-page-actions`); in the cards it runs full width.
  it("marks the parent's action row as the one place that narrows the hint", async () => {
    serve("school_parent");
    render(await ParentChildPage({ params: Promise.resolve({ id: "stu-1" }) }));
    expect(screen.getByRole("link", { name: "Open 360° view" }).parentElement).toHaveClass("child-page-actions");
  });

  // QA15-03: a message under the button must not stretch the other buttons in the row.
  it("keeps the parent's action row from stretching its buttons", async () => {
    serve("school_parent");
    render(await ParentChildPage({ params: Promise.resolve({ id: "stu-1" }) }));
    expect(screen.getByRole("link", { name: "Open 360° view" }).parentElement).toHaveStyle({ alignItems: "flex-start" });
  });

  // QA15-08: each Reports page belongs to its own role; the other role gets the access card, not a borrowed shell.
  it.each([
    ["coordinator page, principal user", CoordinatorReportsPage, "school_principal", "School Coordinator role required"],
    ["principal page, coordinator user", PrincipalReportsPage, "school_coordinator", "Principal role required"],
  ])("refuses the %s", async (_label, Page, role, message) => {
    serve(role);
    render(await Page({ searchParams: Promise.resolve({}) }));
    expect(screen.getByRole("heading", { level: 1, name: "Access unavailable" })).toBeInTheDocument();
    expect(screen.getByText(message)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Download school report (PDF)" })).toBeNull();
    expect(vi.mocked(serverApi).mock.calls.map(([path]) => path)).toEqual(["/api/v1/auth/me"]);
  });

  // QA15-10: each button names where the PDF's content can be read accessibly -- which differs by page.
  it.each([
    ["coordinator Reports", "school_coordinator", () => CoordinatorReportsPage({ searchParams: Promise.resolve({}) }), schoolButton, /same figures are on your dashboard/],
    ["principal Reports", "school_principal", () => PrincipalReportsPage({ searchParams: Promise.resolve({}) }), schoolButton, /same figures are on your dashboard/],
    ["coordinator student", "school_coordinator", () => CoordinatorStudentPage({ params: Promise.resolve({ id: "stu-1" }) }), studentButton, /360° view/],
    ["principal student", "school_principal", () => PrincipalStudentPage({ params: Promise.resolve({ id: "stu-1" }) }), studentButton, /360° view/],
    ["parent child", "school_parent", () => ParentChildPage({ params: Promise.resolve({ id: "stu-1" }) }), studentButton, /same information is on this page/],
  ])("says where to read the PDF accessibly on the %s page", async (_label, role, page, button, hint) => {
    serve(role);
    render(await page());
    expect(button()).toHaveAccessibleDescription(hint);
  });

  it("adds no navigation items (spec §2 non-goal)", () => {
    expect(SCHOOL_NAV.parent.map((item) => item.label)).toEqual(["Dashboard", "Notifications"]);
    expect(SCHOOL_NAV.principal.map((item) => item.label)).toEqual(["Dashboard", "Reports", "Global Education", "Feedback", "Entitlements", "Notifications"]);
  });
});
