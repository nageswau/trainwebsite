import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PerformancePage from "@/app/partnership/performance/page";
import PartnershipHealth, { HealthBadge } from "@/components/PartnershipHealth";
import { ApiError, serverApi } from "@/lib/api";
import { healthText, type PerformanceHealth, type PerformancePage as Page } from "@/lib/partnershipPerformance";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/partnership/performance" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const factor = (key: string, label: string, weight: number, points: number | null, measure: string, has_data = true, tracked = true) => ({ key, label, tracked, has_data, measure, weight, points });
const FACTORS = [
  factor("applications", "Student applications", 15, 10, "13 in the last 12 months"),
  factor("offers", "Offers", 10, null, "No applications in the last 12 months", false),
  factor("visa_success", "Visa success", 10, 11, "3 of 4 decisions approved (75%)"),
  factor("enrolments", "Enrolments", 15, 5, "3 in the last 12 months"),
  factor("commission", "Commission", 10, 6, "50% of expected commission received"),
  factor("response_time", "Response time", 10, 9, "Median 4 days to a reply (3 messages)"),
  factor("meetings", "Meeting frequency", 15, 11, "2 completed in the last 90 days"),
  factor("agreement", "Agreement status", 15, 20, "Active"),
  factor("satisfaction", "Student satisfaction", 0, null, "Not tracked", false, false),
];
const GOOD: PerformanceHealth = { as_of: "2026-10-10", score: 72, band: "good", band_label: "Good", factors: FACTORS };
const BARE: PerformanceHealth = { as_of: "2026-10-10", score: 48, band: "needs_attention", band_label: "Needs attention" };
const UNKNOWN: PerformanceHealth = { as_of: "2026-10-10", score: null, band: "insufficient_data", band_label: "Insufficient data" };

beforeEach(() => {
  vi.mocked(serverApi).mockReset();
});
afterEach(() => cleanup());

describe("upc-028 health text and badge", () => {
  it("reads like the source and says when there is no data", () => {
    expect(healthText({ ...GOOD, score: 92, band: "excellent", band_label: "Excellent" })).toBe("92/100 – Excellent");
    expect(healthText(BARE)).toBe("48/100 – Needs attention");
    expect(healthText(UNKNOWN)).toBe("Insufficient data");
  });

  it("colours the band with the existing pills, and the text always names the band", () => {
    const cases: [PerformanceHealth, string][] = [
      [{ ...GOOD, score: 92, band: "excellent", band_label: "Excellent" }, "status"], [GOOD, "badge"], [BARE, "status error"], [UNKNOWN, "badge health-unknown"],
    ];
    for (const [health, className] of cases) {
      const { container, unmount } = render(<HealthBadge health={health} />);
      expect(container.firstElementChild!.className).toBe(className);
      expect(container.textContent).toBe(healthText(health));
      unmount();
    }
  });
});

describe("upc-028 health card", () => {
  it("shows the breakdown for a commission role, whose points add up to the score", () => {
    render(<PartnershipHealth health={GOOD} />);
    const card = screen.getByRole("region", { name: "Partnership health" });
    expect(within(card).getByText("72/100 – Good")).toBeTruthy();
    const table = within(card).getByRole("table", { name: /Health score breakdown/ });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(1 + 9 + 1); // header, factors, total
    expect(rows[2].textContent).toContain("No data");
    expect(rows[9].textContent).toContain("Not tracked");
    expect(rows[10].textContent).toContain("72");
    expect(FACTORS.reduce((sum, f) => sum + (f.points ?? 0), 0)).toBe(72);
    expect(card.textContent).toContain("as of 10 Oct 2026");
  });

  it("shows only the score and band when the API sent no breakdown", () => {
    render(<PartnershipHealth health={BARE} />);
    const card = screen.getByRole("region", { name: "Partnership health" });
    expect(within(card).getByText("48/100 – Needs attention")).toBeTruthy();
    expect(within(card).queryByRole("table")).toBeNull();
    expect(card.textContent).not.toContain("expected commission");
  });

  it("explains insufficient data", () => {
    render(<PartnershipHealth health={UNKNOWN} />);
    expect(screen.getByRole("region", { name: "Partnership health" }).textContent).toContain("Not enough activity yet");
  });
});

describe("upc-028 ranking column", () => {
  const university = (id: string, partner: boolean) => ({ id, university_code: `UNV-${id}`, name: `Uni ${id}`, country: "UK", stage: "x", stage_label: "X", partner });
  const counts = { leads: null, counselling: null, eligible: null, interested: 0, applications: 1, offers: 0, deposits: 0, visas: 0, enrolled: 0 };
  const data: Page = {
    from: "2026-10-01", to: "2026-10-10", steps: [{ key: "applications", label: "Applications", tracked: true }], totals: counts, total: 3, limit: 25, offset: 0,
    items: [
      { rank: 1, university: university("1", true), counts, health: GOOD },
      { rank: 2, university: university("2", true), counts, health: UNKNOWN },
      { rank: 3, university: university("3", false), counts, health: null },
    ],
  };

  it("adds a Health column: the badge for partners, Not scored for the rest", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/auth/me") return { id: "o1", full_name: "Olga", role: "overseas_admin" } as never;
      if (path.startsWith("/api/v1/partnership/performance?")) return data as never;
      throw new ApiError("unexpected", 500);
    });
    render(await PerformancePage({ searchParams: Promise.resolve({}) }));
    const table = screen.getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "Health" })).toBeTruthy();
    const [, first, second, third] = within(table).getAllByRole("row");
    expect(first.textContent).toContain("72/100 – Good");
    expect(second.textContent).toContain("Insufficient data");
    expect(third.textContent).toContain("Not scored");
    expect(screen.getByText(/Health is scored as of today/)).toBeTruthy();
  });
});
