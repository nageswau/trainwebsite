import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CommissionTerms from "@/components/CommissionTerms";
import UniversityAgreements from "@/components/UniversityAgreements";
import { type CommissionTerm, rateText, scopeText, termPageHref, TRIGGERS } from "@/lib/commissionTerms";
import type { Agreement, AgreementOptions } from "@/lib/universityAgreements";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const person = { id: "p1", full_name: "Rahul Mehta", active: true };
const term = (over: Partial<CommissionTerm> = {}): CommissionTerm => ({
  id: "t1", agreement_id: "a1", commission_percent: "15.00", fixed_amount: null, currency: "GBP", trigger: "visa_and_enrolment",
  trigger_label: "Visa approval + enrolment", conditions: "On first-year tuition", courses: [], countries: [], payment_timeline: "60 days after census",
  payment_terms: null, created_by: person, updated_by: person, created_at: "2026-10-09T05:00:00Z", updated_at: "2026-10-09T05:00:00Z",
  permissions: { can_edit: true }, ...over,
});
const agreement = (over: Partial<Agreement> = {}): Agreement => ({
  id: "a1", mou_number: "MOU-000007", university: { id: "u1", name: "ABC", university_code: "UNV-000001" }, agreement_type: "mou", type_label: "MoU",
  status: "draft", effective_status: "draft", status_label: "Draft", days_to_expiry: 1000, start_date: "2026-10-01", expiry_date: "2029-10-01",
  renewal_date: null, commercial_terms: null, exclusivity: "exclusive", territory: null, recruitment_rights: null, all_courses: true, courses: [],
  countries: [], payment_terms: null, marketing_rights: null, document: null, edusphere_signatory: null, edusphere_signed_on: null,
  university_signatory_name: null, university_signed_on: null, previous: null, renewed_by: null, created_by: person, created_at: "2026-10-09T05:00:00Z",
  updated_at: "2026-10-09T05:00:00Z", permissions: { can_edit_terms: true, can_edit_signing: true, can_renew: false }, moves: [], events: [], ...over,
});
const options: AgreementOptions = { courses: [{ id: "k1", title: "MSc Data Science", level: "PG" }], documents: [] };

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("commissionTerms lib (upc-016)", () => {
  it("words the rate, the scope and the triggers", () => {
    expect(rateText(term())).toBe("15%");
    expect(rateText(term({ commission_percent: "12.50" }))).toBe("12.5%");
    expect(rateText(term({ commission_percent: null, fixed_amount: "1500.50", currency: "USD" }))).toBe("USD 1,500.50");
    expect(rateText(term({ commission_percent: null, fixed_amount: "2000.00", currency: "AUD" }))).toBe("AUD 2,000");
    expect(scopeText(term())).toBe("All programmes · All countries");
    expect(scopeText(term({ courses: [{ id: "k1", title: "MBA", level: "PG" }], countries: [{ id: "c1", name: "India" }] }))).toBe("MBA · India");
    expect(Object.keys(TRIGGERS)).toEqual(["enrolment", "visa_and_enrolment", "tuition_paid"]);
    expect(termPageHref({ trigger: "enrolment", q: " MOU ", offset: "50" }, 0)).toBe("/partnership/commercial-terms?trigger=enrolment&q=MOU");
  });
});

describe("CommissionTerms (upc-016)", () => {
  it("is absent from an agreement without commission terms in its payload (U2: other roles never receive them)", () => {
    render(<UniversityAgreements universityId="u1" agreements={[agreement()]} options={null} canManage={false} />);
    expect(screen.queryByText(/commission terms/i)).not.toBeInTheDocument();
  });

  it("appears inside the agreement card for commission roles, with an empty state", () => {
    render(<UniversityAgreements universityId="u1" agreements={[agreement({ commission_terms: [] })]} options={options} canManage />);
    const section = screen.getByRole("region", { name: "Commission terms of MOU-000007 (restricted)" });
    expect(within(section).getByText("No commission terms recorded yet.")).toBeInTheDocument();
    expect(within(section).getByRole("button", { name: "Add commission term" })).toBeInTheDocument();
  });

  it("lists each term's rate, trigger, scope and texts; read-only without edit rights", () => {
    render(<CommissionTerms agreement={agreement({ permissions: { can_edit_terms: false, can_edit_signing: false, can_renew: true } })} terms={[term({ permissions: { can_edit: false } })]} options={null} />);
    const item = screen.getByRole("listitem");
    expect(within(item).getByText("15%")).toBeInTheDocument();
    expect(within(item).getByText("GBP · Visa approval + enrolment")).toBeInTheDocument();
    expect(within(item).getByText("All programmes · All countries")).toBeInTheDocument();
    expect(within(item).getByText("On first-year tuition")).toBeInTheDocument();
    expect(within(item).getByText("60 days after census")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("adds a term with only the filled fields, refusing both or neither rate first", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ term: term() }, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<CommissionTerms agreement={agreement()} terms={[]} options={options} />);
    fireEvent.click(screen.getByRole("button", { name: "Add commission term" }));
    const form = screen.getByRole("form", { name: "New commission term" });
    fireEvent.click(within(form).getByRole("button", { name: "Save term" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Enter the commission percentage.");
    fireEvent.change(within(form).getByLabelText("Commission %"), { target: { value: "120" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save term" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("between 0 and 100");
    fireEvent.change(within(form).getByLabelText("Commission %"), { target: { value: "12.345" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save term" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("Use at most two decimal places."); // QA-01: not the validator's wording
    fireEvent.change(within(form).getByLabelText("Commission %"), { target: { value: "15" } });
    fireEvent.change(within(form).getByLabelText("Currency (required)"), { target: { value: "GBP" } });
    fireEvent.change(within(form).getByLabelText("Commission trigger (required)"), { target: { value: "visa_and_enrolment" } });
    fireEvent.click(within(form).getByLabelText(/MSc Data Science/));
    fireEvent.change(within(form).getByLabelText("Conditions"), { target: { value: "On first-year tuition" } });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(within(form).getByRole("button", { name: "Save term" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/partnership/agreements/a1/commission-terms");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({
      commission_percent: "15", currency: "GBP", trigger: "visa_and_enrolment", conditions: "On first-year tuition", course_ids: ["k1"], country_ids: [],
    });
    expect(screen.getByRole("status")).toHaveTextContent("Commission term added.");
  });

  it("switches an existing term to a fixed amount, sending the percentage as null", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ term: term() }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CommissionTerms agreement={agreement()} terms={[term()]} options={options} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit commission term 1" }));
    const form = screen.getByRole("form", { name: "Edit commission term 1" });
    fireEvent.click(within(form).getByLabelText("Fixed amount"));
    fireEvent.change(within(form).getByLabelText("Commission amount"), { target: { value: "1500" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save term" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/partnership/agreements/a1/commission-terms/t1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ commission_percent: null, fixed_amount: "1500" });
  });

  it("removes a term after a confirmation, and shows a server refusal", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "This agreement's terms are approved -- renew the agreement to change its commission" }, 409)).mockResolvedValueOnce(res(null, 204));
    vi.stubGlobal("fetch", fetchMock);
    render(<CommissionTerms agreement={agreement()} terms={[term()]} options={options} />);
    fireEvent.click(screen.getByRole("button", { name: "Remove commission term 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("renew the agreement");
    expect(refresh).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Yes, remove" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[1][1].method).toBe("DELETE");
    expect(screen.getByRole("status")).toHaveTextContent("Commission term removed.");
  });
});
