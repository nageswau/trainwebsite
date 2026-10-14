import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementHealthPage from "@/app/management/health/page";
import ManagementHealth from "@/components/ManagementHealth";
import PortalShell from "@/components/PortalShell";
import { ApiError, serverApi } from "@/lib/api";
import type { ManagementMe } from "@/lib/management";
import { managementNavFor } from "@/lib/management";
import type { BusinessHealth, HealthFactor } from "@/lib/managementHealth";
import { SUPER_ADMIN_NAV } from "@/lib/navigation";
import { elements } from "@/tests/helpers/elementTree";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), redirect: vi.fn(), usePathname: () => "/management/health" }));
vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), serverApi: vi.fn() }));

const partner: ManagementMe = { id: "p1", full_name: "Priya Partner", role: "partner", tiers: { operational: true, finance: true, partner_only: true } };
const superAdmin: ManagementMe = { id: "s1", full_name: "Sam Admin", role: "super_admin", tiers: { operational: true, finance: false, partner_only: false } };
const LABELS = ["Revenue", "Profit", "Cash flow", "Sales pipeline", "Student growth", "Enrollment", "Agent growth", "School growth", "University partnerships", "Employee productivity", "Marketing ROI", "Expenses"];
const OPERATIONAL = ["Sales pipeline", "Student growth", "Enrollment", "Agent growth", "School growth", "University partnerships"];

const factor = (label: string, over: Partial<HealthFactor> = {}): HealthFactor => ({
  key: label.toLowerCase().replaceAll(" ", "_"), label, tier: OPERATIONAL.includes(label) ? "operational" : "finance", weight: 5, unit: "count",
  current: "12", previous: "10", change: 20, score: 100, rag: "green", points: 7, note: null, ...over,
}); // prettier-ignore

function health(over: Partial<BusinessHealth> = {}): BusinessHealth {
  return {
    month: "2026-09", previous_month: "2026-08", partial: false, scope: "business", score: 84, rag: "green",
    factors: LABELS.map((label) => factor(label, label === "Expenses" ? { score: 20, rag: "red", points: 1 } : label === "Cash flow" ? { score: 55, rag: "amber", points: 5 } : {})),
    ...over,
  }; // prettier-ignore
}

afterEach(cleanup);

describe("mgmt-030 ManagementHealth", () => {
  it("shows the overall score out of 100 with its band in words", () => {
    render(<ManagementHealth data={health()} error="" query={{ month: "" }} maxMonth="2026-10" />);
    const overall = screen.getByRole("list", { name: "Overall health" });
    expect(within(overall).getByText("Overall business health")).toBeTruthy();
    expect(within(overall).getByText("84/100")).toBeTruthy();
    expect(within(overall).getByText("Green")).toBeTruthy();
    expect(screen.getByText(/September 2026 compared with August 2026/)).toBeTruthy();
  });

  it("gives one RAG line per factor in source order (§30)", () => {
    render(<ManagementHealth data={health()} error="" query={{ month: "" }} maxMonth="2026-10" />);
    const lines = within(screen.getByRole("list", { name: "Health by factor" })).getAllByRole("listitem");
    expect(lines.map((li) => li.textContent)).toEqual(LABELS.map((l) => `${l}: ${l === "Expenses" ? "Red" : l === "Cash flow" ? "Amber" : "Green"}`));
  });

  it("breaks the score down so the points add up to it (AC)", () => {
    render(<ManagementHealth data={health()} error="" query={{ month: "" }} maxMonth="2026-10" />);
    const table = screen.getByRole("table", { name: /Business health breakdown/ });
    const rows = within(table).getAllByRole("row");
    expect(rows).toHaveLength(1 + 12 + 1);
    expect(within(rows[1]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["12 against 10 (+20.0%)", "100 Green", "5", "7"]); // QA30-02: five columns, the band beside the score
    expect(within(table).getAllByRole("columnheader").map((c) => c.textContent)).toEqual(["Factor", "Measure", "Score", "Weight", "Points"]);
    // QA30-02: on a phone the shared `.table.stack` turns each factor into labelled lines, so nothing sits off-screen at any width.
    expect(table.className).toContain("stack");
    expect(within(rows[1]).getAllByRole("cell").map((c) => c.getAttribute("data-label"))).toEqual(["Measure", "Score", "Weight", "Points"]);
    // QA30-04/05: the score and its band are one item (they stay together on a stacked phone row); the total carries no "Points" label.
    expect(within(rows[1]).getAllByRole("cell")[1].children).toHaveLength(1);
    expect(within(rows[13]).getAllByRole("cell").at(-1)!.hasAttribute("data-label")).toBe(false);
    expect(within(rows[13]).getByRole("rowheader").textContent).toBe("Overall score");
    expect(within(rows[13]).getAllByRole("cell").at(-1)!.textContent).toBe("84");
  });

  it("names a factor that is not available and why", () => {
    const factors = health().factors.map((f) => (f.label === "Cash flow" ? { ...f, score: null, rag: null, points: null, note: "Cash/bank balance not entered for both months" } : f));
    render(<ManagementHealth data={health({ factors })} error="" query={{ month: "" }} maxMonth="2026-10" />);
    const row = screen.getByRole("rowheader", { name: "Cash flow" }).closest("tr")!;
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["Cash/bank balance not entered for both months", "—", "5", "—"]);
    expect(screen.getByText(/A factor that is not available is left out/)).toBeTruthy();
  });

  it("labels the super admin's score as operational health and says finance factors are partners' (BH1)", () => {
    const factors = OPERATIONAL.map((label) => factor(label));
    render(<ManagementHealth data={health({ scope: "operational", score: 61, rag: "amber", factors })} error="" query={{ month: "" }} maxMonth="2026-10" />);
    expect(within(screen.getByRole("list", { name: "Overall health" })).getByText("Operational health")).toBeTruthy();
    expect(screen.getByText(/finance factors are shown to partners only/)).toBeTruthy();
    expect(within(screen.getByRole("list", { name: "Health by factor" })).getAllByRole("listitem")).toHaveLength(6);
    expect(screen.queryByText("Revenue")).toBeNull();
    // QA30-01: the scoring note explains only the factors shown -- no margin, ROI or revenue wording for the operational scope.
    const note = screen.getByText(/Each factor is scored 0–100/).textContent!;
    expect(note).not.toMatch(/margin|ROI|revenue|Profit|Expenses/);
  });

  it("explains the finance scales to partners (QA30-01)", () => {
    render(<ManagementHealth data={health()} error="" query={{ month: "" }} maxMonth="2026-10" />);
    expect(screen.getByText(/Each factor is scored 0–100/).textContent).toMatch(/Profit is scored on the margin/);
  });

  it("says when there is not enough data, and when the month is still running", () => {
    const factors = health().factors.map((f) => ({ ...f, score: null, rag: null, points: null, note: "Nothing recorded in either month" }));
    render(<ManagementHealth data={health({ score: null, rag: null, partial: true, month: "2026-10", previous_month: "2026-09", factors })} error="" query={{ month: "2026-10" }} maxMonth="2026-10" />);
    expect(screen.getByRole("status").textContent).toBe("Not enough data to score October 2026.");
    expect(within(screen.getByRole("list", { name: "Overall health" })).getByText("Not scored")).toBeTruthy();
    expect(screen.getByText(/so far, against the whole of September 2026/)).toBeTruthy();
  });

  it("holds the month in a GET form and shows the API's error", () => {
    render(<ManagementHealth data={null} error="Choose this month or an earlier one" query={{ month: "2026-09" }} maxMonth="2026-10" />);
    expect(screen.getByRole("alert").textContent).toBe("Choose this month or an earlier one");
    const form = screen.getByRole("form", { name: "Choose a month" });
    expect(form.getAttribute("method")).toBe("get");
    expect(form.getAttribute("action")).toBe("/management/health");
    const month = screen.getByLabelText("Month") as HTMLInputElement;
    expect([month.value, month.max, month.min]).toEqual(["2026-09", "2026-10", "2000-01"]);
  });
});

describe("mgmt-030 ManagementHealthPage", () => {
  beforeEach(() => {
    vi.mocked(serverApi).mockReset();
  });

  it("gives the super admin their own sidebar and the partner the Command Center one, reading the month from the address", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/management/me" ? superAdmin : health({ scope: "operational" })) as never);
    let tree = await ManagementHealthPage({ searchParams: Promise.resolve({ month: "2026-08" }) });
    expect(vi.mocked(serverApi)).toHaveBeenCalledWith("/api/v1/management/health?month=2026-08");
    expect((elements(tree).find((el) => el.type === PortalShell)!.props as { nav: unknown }).nav).toBe(SUPER_ADMIN_NAV);
    vi.mocked(serverApi).mockImplementation(async (path: string) => (path === "/api/v1/management/me" ? partner : health()) as never);
    tree = await ManagementHealthPage({ searchParams: Promise.resolve({}) });
    expect(vi.mocked(serverApi)).toHaveBeenCalledWith("/api/v1/management/health");
    expect((elements(tree).find((el) => el.type === PortalShell)!.props as { nav: unknown }).nav).toEqual(managementNavFor(partner.tiers));
  });

  it("shows the API's 422 words, and an unavailable notice otherwise", async () => {
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return partner as never;
      throw new ApiError("Choose this month or an earlier one", 422);
    });
    let tree = await ManagementHealthPage({ searchParams: Promise.resolve({}) });
    let view = elements(tree).find((el) => el.type === ManagementHealth)!;
    expect((view.props as { error: string }).error).toBe("Choose this month or an earlier one");
    vi.mocked(serverApi).mockImplementation(async (path: string) => {
      if (path === "/api/v1/management/me") return partner as never;
      throw new ApiError("boom", 500);
    });
    tree = await ManagementHealthPage({ searchParams: Promise.resolve({}) });
    view = elements(tree).find((el) => el.type === ManagementHealth)!;
    expect((view.props as { error: string }).error).toBe("Business health is unavailable right now. Please try again.");
  });
});
