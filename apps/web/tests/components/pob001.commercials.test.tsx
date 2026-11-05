import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterComparisonPanel from "@/components/RecruiterComparisonPanel";
import RecruiterCompanyContract from "@/components/RecruiterCompanyContract";
import { navForPermissions, RECRUITER_MANAGER_NAV, RECRUITER_NAV } from "@/lib/navigation";
import type { Comparison, ComparisonRow } from "@/lib/recruiterComparison";
import type { Contract } from "@/lib/recruiterContracts";
import { canSeeRevenue } from "@/lib/recruiterRevenue";

// pob-001 (DEC-SCOPE-402 C5/C7/C8): without `commercials.client.view` the API leaves the terms out; the screens drop their rows, inputs,
// downloads, the Revenue column and the Receivables menu item instead of showing blanks.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const DOC = { name: "signed.pdf", content_type: "application/pdf", uploaded_at: "2026-10-01T05:30:00Z" };

function hidden(over: Partial<Contract> = {}): Contract {
  return {
    id: "K1", status: "proposal_sent", status_label: "Proposal Sent", status_changed_at: "2026-10-01T05:30:00Z", agreement_type: "Permanent hiring",
    start_date: "2026-04-01", end_date: "2027-03-31", expired_on: null, contract_document: DOC, mou_document: null, is_current: true,
    created_by: { id: "U1", full_name: "Priya Recruiter", active: true },
    permissions: { can_edit: true, can_upload: false, can_renew: false, can_view_terms: false, can_edit_terms: false },
    created_at: "2026-10-01T05:30:00Z", updated_at: "2026-10-01T05:30:00Z", ...over,
  };
}

let read: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  read = () => res({ current: hidden(), previous: [hidden({ id: "K0", is_current: false })], can_start: false, can_view_terms: false, can_edit_terms: false });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "PATCH" || init?.method === "POST") return Promise.resolve(res({ contract: hidden() }));
    if (url === "/api/v1/recruiter/companies/C1/contracts") return Promise.resolve(read());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("contract card without commercials.client.view (C5)", () => {
  it("shows no fee or terms rows and no document download, but says a document is on file", async () => {
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    await screen.findByText("Agreement type");
    for (const label of ["Recruitment fee", "Payment terms", "Replacement policy"]) expect(screen.queryByText(label)).toBeNull();
    expect(screen.queryByRole("link", { name: /Download/ })).toBeNull();
    expect(screen.getAllByText(/signed\.pdf/).length).toBe(2); // current and previous contract
    expect(screen.queryByText(/—/)).toBeNull(); // the previous contract's line has no fee placeholder either
  });

  it("edits without fee or terms inputs and sends only what changed", async () => {
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit contract" }));
    const form = screen.getByRole("form", { name: "Edit contract" });
    for (const label of ["Fee basis", /Recruitment fee/, "Payment terms", "Replacement policy"]) expect(within(form).queryByLabelText(label)).toBeNull();
    fireEvent.change(within(form).getByLabelText("Agreement type"), { target: { value: "Contract staffing" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save contract" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const [, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(JSON.parse(String(init.body))).toEqual({ agreement_type: "Contract staffing", expected_updated_at: "2026-10-01T05:30:00Z" });
  });

  it("starts a first contract without fee or terms inputs", async () => {
    read = () => res({ current: null, previous: [], can_start: true, can_view_terms: false, can_edit_terms: false });
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Start contract" }));
    const form = screen.getByRole("form", { name: "Start contract" });
    expect(within(form).queryByLabelText("Fee basis")).toBeNull();
    expect(within(form).queryByLabelText("Payment terms")).toBeNull();
  });

  it("view without edit reads the terms but the form has no fee inputs", async () => {
    const terms = { fee_basis: "fixed" as const, fee_value: "50000.00", payment_terms: "30 days", replacement_policy: "90 days" };
    const readable = hidden({ ...terms, permissions: { can_edit: true, can_upload: false, can_renew: false, can_view_terms: true, can_edit_terms: false } });
    read = () => res({ current: readable, previous: [], can_start: false, can_view_terms: true, can_edit_terms: false });
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    expect(await screen.findByText("Recruitment fee")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Download contract document/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit contract" }));
    expect(within(screen.getByRole("form", { name: "Edit contract" })).queryByLabelText("Fee basis")).toBeNull();
  });
});

describe("recruiter comparison without commercials.client.view (C7)", () => {
  const row = (id: string | null, name: string): ComparisonRow => ({
    user_id: id, full_name: name, active: true, companies_contacted: 5, meetings: 2, new_leads: 3, new_companies: 1, new_contracts: 1,
    new_requirements: 2, candidates_sourced: 12, profiles_shared: 8, interviews: 4, selections: 2, joining: 1,
  });
  const data: Comparison = { date_from: "2026-10-01", date_to: "2026-10-11", recruiter: null, revenue_visible: false, items: [row("r-1", "Asha")], totals: row(null, "Total") };

  it("drops the Revenue column and narrows the Recruitment heading", () => {
    render(<RecruiterComparisonPanel data={data} params={{ from: "2026-10-01", to: "2026-10-11" }} today="2026-10-11" own={false} />);
    const table = screen.getByRole("table");
    expect(within(table).queryByRole("columnheader", { name: "Revenue" })).toBeNull();
    expect(within(table).getByRole("columnheader", { name: "Recruitment" }).getAttribute("colspan")).toBe("5");
    expect(within(table).getAllByRole("row")[2].querySelectorAll("td").length).toBe(11);
  });
});

describe("revenue gate and menu (C8)", () => {
  it("needs the role and the grant", () => {
    expect(canSeeRevenue("placement_team", ["commercials.client.view"])).toBe(true);
    expect(canSeeRevenue("placement_team", [])).toBe(false);
    expect(canSeeRevenue("bdm", ["commercials.client.view"])).toBe(false); // RV10: the BDM never reads revenue
  });

  it("hides Receivables without the grant and keeps it with it", () => {
    for (const nav of [RECRUITER_NAV, RECRUITER_MANAGER_NAV]) {
      expect(navForPermissions(nav, []).some((item) => item.href === "/recruiter/receivables")).toBe(false);
      expect(navForPermissions(nav, ["commercials.client.view"]).some((item) => item.href === "/recruiter/receivables")).toBe(true);
    }
  });
});
