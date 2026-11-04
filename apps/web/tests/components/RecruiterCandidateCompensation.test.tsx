import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateDetail from "@/components/RecruiterCandidateDetail";
import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import RecruiterExchangeRatesPanel from "@/components/RecruiterExchangeRatesPanel";
import type { CandidateDetail } from "@/lib/recruiterCandidates";

// hrc-011 (DEC-SCOPE-372): the compensation group of the candidate form (with the grant), its display on the detail, and the manager's
// exchange-rate panel.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const sources = { items: [{ id: "s1", name: "Referral", active: true, sort_order: 1 }], total: 1, limit: 100, offset: 0 };
const rate = { currency: "USD", inr_per_unit: "83.2500", updated_at: "2026-11-04T05:00:00Z", updated_by: { id: "m", full_name: "Priya Manager" } };
const candidate = {
  id: "C1", candidate_code: "CAN-000001", name: "Asha Rao", location: null, experience_months: null, preferred_role: null,
  source: { id: "s1", name: "Referral", active: true }, source_detail: null, status: "available", archived: false, created_at: "2026-11-01T00:00:00Z",
  mobile: "9876543210", email: null, qualification: null, college: null, passing_year: null, current_company: null,
  current_salary: "50000.00", current_salary_currency: "INR", current_salary_period: "month", current_annual_inr: "600000.00",
  expected_salary: null, expected_salary_currency: null, expected_salary_period: null, expected_annual_inr: null,
  minimum_salary: null, minimum_salary_currency: null, minimum_salary_period: null, minimum_annual_inr: null, salary_negotiable: true,
  notice_days: null, preferred_locations: [], linkedin: null, archived_at: null, created_by: null, updated_by: null, updated_at: "2026-11-02T00:00:00Z",
  resumes: [], can_edit: true,
} as unknown as CandidateDetail;

let fetchMock: ReturnType<typeof vi.fn>;
let putReply: () => Response;
const sent = (method: string) => fetchMock.mock.calls.filter(([, init]) => init?.method === method);

beforeEach(() => {
  putReply = () => res(rate);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res(sources));
    if (url === "/api/v1/recruiter/catalogue/exchange-rates") return Promise.resolve(res({ items: [rate] }));
    if (init?.method === "PUT") return Promise.resolve(putReply());
    if (init?.method === "PATCH") return Promise.resolve(res({ ...candidate }));
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-011 candidate compensation", () => {
  it("edits each amount with its currency and period and sends them with Negotiable", async () => {
    render(<RecruiterCandidateForm initial={candidate} onSaved={vi.fn()} />);
    expect(screen.getByRole("group", { name: "Compensation" })).toBeInTheDocument();
    await screen.findAllByRole("option", { name: "USD" }); // the rate table's currencies are offered next to INR
    fireEvent.change(screen.getByLabelText("Expected salary"), { target: { value: "4000" } });
    fireEvent.change(screen.getByLabelText("Expected salary currency"), { target: { value: "USD" } });
    fireEvent.change(screen.getByLabelText("Expected salary pay period"), { target: { value: "month" } });
    fireEvent.change(screen.getByLabelText("Negotiable"), { target: { value: "no" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(sent("PATCH")).toHaveLength(1));
    expect(JSON.parse(String(sent("PATCH")[0][1].body))).toMatchObject({
      current_salary: "50000.00", current_salary_currency: "INR", current_salary_period: "month",
      expected_salary: "4000", expected_salary_currency: "USD", expected_salary_period: "month",
      minimum_salary: null, minimum_salary_currency: null, minimum_salary_period: null, salary_negotiable: false,
    });
  });

  it("has no compensation group when the API left salary out (no grant)", () => {
    const hidden: Record<string, unknown> = { ...candidate };
    delete hidden.expected_salary;
    render(<RecruiterCandidateForm initial={hidden as unknown as CandidateDetail} onSaved={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Compensation" })).toBeNull();
  });

  it("shows the amount as entered with its yearly rupee figure, and Negotiable", () => {
    render(<RecruiterCandidateDetail initial={candidate} />);
    expect(screen.getByText("₹50,000 per month (≈ ₹6,00,000 a year)")).toBeInTheDocument();
    expect(screen.getByText("Minimum acceptable salary")).toBeInTheDocument();
    expect(screen.getByText("Negotiable").nextSibling).toHaveTextContent("Yes");
  });
});

describe("hrc-011 exchange-rate panel", () => {
  it("lists the rates, prefills Change and saves the rate upper-cased", async () => {
    render(<RecruiterExchangeRatesPanel />);
    expect(await screen.findByText("USD")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Change the USD rate" }));
    expect(screen.getByLabelText(/Rupees for 1 unit/)).toHaveValue(83.25);
    fireEvent.change(screen.getByLabelText(/Currency code/), { target: { value: "aed" } });
    fireEvent.change(screen.getByLabelText(/Rupees for 1 unit/), { target: { value: "22.7" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rate" }));
    await waitFor(() => expect(sent("PUT")).toHaveLength(1));
    expect(sent("PUT")[0][0]).toBe("/api/v1/recruiter/catalogue/exchange-rates/AED");
    expect(JSON.parse(String(sent("PUT")[0][1].body))).toEqual({ inr_per_unit: "22.7" });
    expect(await screen.findByText(/Saved: 1 AED = ₹22.7/)).toBeInTheDocument();
  });

  it("refuses an incomplete form without a request, and shows the API's refusal", async () => {
    render(<RecruiterExchangeRatesPanel />);
    await screen.findByText("USD");
    fireEvent.click(screen.getByRole("button", { name: "Save rate" }));
    expect(await screen.findByText(/three-letter currency code/)).toBeInTheDocument();
    expect(sent("PUT")).toHaveLength(0);
    putReply = () => res({ detail: "INR is the base currency; it needs no rate" }, 422);
    fireEvent.change(screen.getByLabelText(/Currency code/), { target: { value: "INR" } });
    fireEvent.change(screen.getByLabelText(/Rupees for 1 unit/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save rate" }));
    expect(await screen.findByText("INR is the base currency; it needs no rate")).toBeInTheDocument();
  });

  it("offers Retry when the rates cannot be read", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({}, 500)));
    render(<RecruiterExchangeRatesPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the exchange rates.");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});
