import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManagementReview from "@/components/ManagementReview";
import ManagementReviewEditor from "@/components/ManagementReviewEditor";
import ManagementReviewGenerate from "@/components/ManagementReviewGenerate";
import ManagementReviews from "@/components/ManagementReviews";
import type { MonthlyReview, ReviewNarrative } from "@/lib/managementReviews";

const router = { replace: vi.fn(), refresh: vi.fn(), push: vi.fn() };
vi.mock("next/navigation", () => ({ useRouter: () => router, redirect: vi.fn(), usePathname: () => "/management/reviews/2026-09" }));

const EMPTY: ReviewNarrative = { went_wrong: "", delayed: "", intervention: "", initiatives: "", hiring: "", investments: "", partnerships: "" };

function review(overrides: Partial<MonthlyReview> = {}): MonthlyReview {
  return {
    id: "r1", month: "2026-09", label: "September 2026", status: "draft", narrative: EMPTY, generated_at: "2026-10-01T00:30:00Z", finalised_at: null,
    finalised_by: null, updated_at: "2026-10-01T00:30:00Z", updated_by: null,
    snapshot: {
      revenue: { lines: [{ key: "abroad", label: "Abroad Education", amount: "120000.00" }, { key: "it", label: "IT Training", amount: "5000.00" }, { key: "recruitment", label: "Recruitment", amount: "0.00" }, { key: "other", label: "Other", amount: "0.00" }], total: "125000.00" },
      expenses: { lines: [{ key: "salaries", label: "Salaries", amount: "50000.00" }, { key: "technology", label: "Operations (technology)", amount: "2000.00" }], total: "52000.00" },
      profitability: { revenue: "125000.00", expenses: "52000.00", net_profit: "73000.00", margin: 58.4 },
      sales: { leads: 40, students: 6, applications: 9, enrollments: 2, placements: 1 },
      partnerships: { agents: 3, schools: 1, universities: 0, companies: 2 },
      people: { employees: null, departments: [], attendance: null, attendance_note: "Not tracked", productivity: null },
      marketing: { budget: null, spend: "0.00", leads: 40, customers: 4, conversion: 10, revenue: "0.00", roi: null },
      investments: { new_count: 1, new_amount: "500000.00", total: "900000.00", return: "0.00", roi: null },
      next_month: { month: "2026-10", label: "October 2026", targets: [{ vertical: "Abroad Education", text: "Recruit agents", kpi: "New agents", unit: "count", target: "30.00" }], budget: "75000.00" },
    },
    ...overrides,
  };
}

type Call = { url: string; method: string; body: unknown };
let calls: Call[];
function respond(...answers: { status?: number; body?: unknown }[]) {
  const queue = [...answers];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({ url, method: init.method ?? "GET", body: init.body ? JSON.parse(String(init.body)) : undefined });
    const answer = queue.shift() ?? { body: { id: "r1" } };
    return new Response(JSON.stringify(answer.body ?? { id: "r1" }), { status: answer.status ?? 200, headers: { "Content-Type": "application/json" } });
  }));
}

beforeEach(() => {
  calls = [];
  router.push.mockReset();
  router.refresh.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("mgmt-032 review list", () => {
  it("shows an error, the empty state, or the months with their status", () => {
    const { rerender } = render(<ManagementReviews data={null} error="Reviews are unavailable" />);
    expect(screen.getByRole("alert").textContent).toBe("Reviews are unavailable");
    rerender(<ManagementReviews data={{ items: [] }} error="" />);
    expect(screen.getByText(/No reviews yet/)).toBeTruthy();
    rerender(<ManagementReviews data={{ items: [{ month: "2026-09", label: "September 2026", status: "final", generated_at: "2026-10-01T00:30:00Z", finalised_at: "2026-10-03T06:00:00Z" }]} } error="" />);
    const link = screen.getByRole("link", { name: "September 2026" });
    expect(link.getAttribute("href")).toBe("/management/reviews/2026-09");
    expect(screen.getByText("Final")).toBeTruthy();
  });

  it("generates a chosen finished month and opens it", async () => {
    respond({ status: 201 });
    render(<ManagementReviewGenerate today="2026-10-14" reviewed={["2026-09"]} />);
    const select = screen.getByLabelText("Month", { selector: "select" }) as HTMLSelectElement;
    expect(select.value).toBe("2026-08");
    fireEvent.click(screen.getByRole("button", { name: "Generate review" }));
    await waitFor(() => expect(router.push).toHaveBeenCalledWith("/management/reviews/2026-08"));
    expect(calls).toEqual([{ url: "/api/v1/management/reviews/2026-08/generate", method: "POST", body: undefined }]);
  });

  it("re-reads the list when it is shown again, so Back after generating lists the new month (QA32-02)", () => {
    const { rerender } = render(<ManagementReviewGenerate today="2026-10-14" reviewed={[]} />);
    expect(router.refresh).toHaveBeenCalledTimes(1);
    expect((screen.getByLabelText("Month", { selector: "select" }) as HTMLSelectElement).value).toBe("2026-09");
    rerender(<ManagementReviewGenerate today="2026-10-14" reviewed={["2026-09"]} />); // the re-read lists September now
    expect((screen.getByLabelText("Month", { selector: "select" }) as HTMLSelectElement).value).toBe("2026-08");
    expect(router.refresh).toHaveBeenCalledTimes(1);
  });
});

describe("mgmt-032 review sections", () => {
  it("renders the frozen figures in §32 order", () => {
    render(<ManagementReview review={review()} />);
    const headings = screen.getAllByRole("heading", { level: 3 }).map((h) => h.textContent);
    expect(headings).toEqual(["1. Revenue", "2. Expenses", "3. Profitability", "4. Sales", "5. Partnerships", "6. People", "7. Marketing", "8. Investments"]);
    const revenue = screen.getByRole("region", { name: "1. Revenue" });
    expect(within(revenue).getByText("₹1,20,000.00")).toBeTruthy();
    expect(within(revenue).getByText("₹1,25,000.00")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "3. Profitability" })).getByText("58.4%")).toBeTruthy();
    const people = screen.getByRole("region", { name: "6. People" });
    expect(within(people).getByText("Not tracked")).toBeTruthy();
    expect(within(people).getByText("No department salaries entered for the month.")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "7. Marketing" })).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("sizes the two-column figure tables to their content, so phones see the values (QA32-03)", () => {
    render(<ManagementReview review={review()} />);
    for (const table of within(screen.getByRole("region", { name: "1. Revenue" })).getAllByRole("table")) expect(table.className).toBe("table compact figures");
  });

  it("shows a final review's narrative read-only", () => {
    render(<ManagementReviewEditor review={review({ status: "final", finalised_at: "2026-10-03T06:00:00Z", narrative: { ...EMPTY, went_wrong: "Fees <b>late</b>" } })} />);
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByText("Fees <b>late</b>")).toBeTruthy();
    expect(screen.getAllByText("Not answered").length).toBe(6);
    expect(within(screen.getByRole("region", { name: "10. Next month" })).getByText("₹75,000.00")).toBeTruthy();
  });
});

describe("mgmt-032 review editor", () => {
  it("saves only the answers that changed", async () => {
    respond({ body: review() });
    render(<ManagementReviewEditor review={review()} />);
    fireEvent.change(screen.getByLabelText("What went wrong?"), { target: { value: "Churn." } });
    fireEvent.click(screen.getByRole("button", { name: "Save answers" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Answers saved."));
    expect(calls).toEqual([{ url: "/api/v1/management/reviews/2026-09", method: "PATCH", body: { went_wrong: "Churn." } }]);
    expect(router.refresh).toHaveBeenCalled();
  });

  it("says which Problems answers are missing without calling the API", () => {
    respond();
    render(<ManagementReviewEditor review={review()} />);
    fireEvent.change(screen.getByLabelText("What went wrong?"), { target: { value: "Churn." } });
    fireEvent.click(screen.getByRole("button", { name: "Finalise review" }));
    expect(screen.getByRole("alert").textContent).toBe("Answer every Problems question before finalising: What is delayed?, What needs management intervention?");
    expect(calls).toEqual([]);
  });

  it("saves then finalises after confirmation", async () => {
    respond({ body: review() }, { body: review({ status: "final" }) });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<ManagementReviewEditor review={review()} />);
    for (const label of ["What went wrong?", "What is delayed?", "What needs management intervention?"]) fireEvent.change(screen.getByLabelText(label), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Finalise review" }));
    await waitFor(() => expect(router.refresh).toHaveBeenCalled());
    expect(calls.map((c) => `${c.method} ${c.url}`)).toEqual(["PATCH /api/v1/management/reviews/2026-09", "POST /api/v1/management/reviews/2026-09/finalise"]);
  });

  it("does nothing when the finalise is not confirmed", () => {
    respond();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<ManagementReviewEditor review={review({ narrative: { ...EMPTY, went_wrong: "a", delayed: "b", intervention: "c" } })} />);
    fireEvent.click(screen.getByRole("button", { name: "Finalise review" }));
    expect(calls).toEqual([]);
  });

  it("regenerates the figures and shows an API refusal", async () => {
    respond({ status: 409, body: { detail: "This review is final and cannot change" } });
    render(<ManagementReviewEditor review={review()} />);
    fireEvent.click(screen.getByRole("button", { name: "Regenerate figures" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("This review is final and cannot change"));
    expect(calls).toEqual([{ url: "/api/v1/management/reviews/2026-09/generate", method: "POST", body: undefined }]);
  });
});
