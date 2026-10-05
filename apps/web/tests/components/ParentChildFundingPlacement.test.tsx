import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ParentChildPage from "@/app/school/parent/children/[id]/page";
import { serverApi } from "@/lib/api";

vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
vi.mock("@/components/PortalShell", () => ({ default: ({ children }: { children: React.ReactNode }) => <div>{children}</div> }));
vi.mock("@/components/SchoolChildOverview", () => ({ default: () => <h2>Child overview</h2>, loadChildOverview: async () => ({}) }));
vi.mock("@/components/SchoolGradeHistory", () => ({ default: () => null, loadGradeHistory: async () => ({ history: [] }) }));
vi.mock("@/components/SchoolStudentTimeline", () => ({ default: () => null, loadStudentTimeline: async () => ({ events: [] }) }));
vi.mock("@/components/SchoolTransferHistory", () => ({ default: () => null, loadTransferHistory: async () => [] }));
vi.mock("@/components/PortfolioPanel", () => ({ default: () => <h3>Digital Portfolio</h3> }));
vi.mock("@/lib/portfolio", () => ({ loadPortfolio: async () => ({}) }));

afterEach(() => {
  cleanup();
  vi.mocked(serverApi).mockReset();
});

const before = (a: HTMLElement, b: HTMLElement) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

// QA-04 (browser QA 2026-10-01): the parent had to scroll past every portfolio section to find the funding support card.
describe("parent child page", () => {
  it("shows funding support right after the child's overview, before the history sections and the portfolio", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "p1", email: "p@example.local", full_name: "Parent", role: "school_parent", division: "overseas", profile: {} } as never;
      if (path.endsWith("/funding-records")) return [] as never;
      throw new Error(`unexpected request ${path}`);
    });
    render(await ParentChildPage({ params: Promise.resolve({ id: "s1" }) }));
    const funding = screen.getByRole("heading", { name: "Funding support" });
    expect(before(screen.getByRole("heading", { name: "Child overview" }), funding)).toBe(true);
    expect(before(funding, screen.getByRole("heading", { name: "Grade history" }))).toBe(true);
    expect(before(funding, screen.getByRole("heading", { name: "Digital Portfolio" }))).toBe(true);
  });
});
