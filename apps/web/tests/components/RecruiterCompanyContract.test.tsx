import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyContract from "@/components/RecruiterCompanyContract";
import { type Contract, contractConflict, feeText } from "@/lib/recruiterContracts";

// rec-030 (spec §4; CT1-CT10): the company's contract -- empty state, start, the status ladder in source order, Expired, documents,
// the field-placed 422, a coded 409, read only without permissions, and previous contracts.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

function contract(over: Partial<Contract> = {}): Contract {
  return {
    id: "K1", status: "proposal_sent", status_label: "Proposal Sent", status_changed_at: "2026-10-01T05:30:00Z", agreement_type: "Permanent hiring",
    start_date: "2026-04-01", end_date: "2027-03-31", expired_on: null, fee_basis: "fixed", fee_value: "50000.00", payment_terms: "30 days",
    replacement_policy: "90 days free replacement", contract_document: null, mou_document: null, is_current: true,
    created_by: { id: "U1", full_name: "Priya Recruiter", active: true }, permissions: { can_edit: true, can_upload: true, can_renew: false },
    created_at: "2026-10-01T05:30:00Z", updated_at: "2026-10-01T05:30:00Z", ...over,
  };
}

let read: () => Response;
let write: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  read = () => res({ current: contract(), previous: [], can_start: false });
  write = () => res({ contract: contract({ status: "negotiation", status_label: "Negotiation" }) });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PATCH" || init?.method === "PUT") return Promise.resolve(write());
    if (url === "/api/v1/recruiter/companies/C1/contracts") return Promise.resolve(read());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const sent = (method: string) => {
  const call = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === method)!;
  return { url: String(call[0]), body: JSON.parse(String((call[1] as RequestInit).body)) };
};

describe("RecruiterCompanyContract (rec-030)", () => {
  it("shows no contract yet and starts one with the section 22 fields", async () => {
    read = () => res({ current: null, previous: [], can_start: true });
    write = () => res({ contract: contract() }, 201);
    const onChanged = vi.fn();
    render(<RecruiterCompanyContract companyId="C1" onChanged={onChanged} />);
    expect(await screen.findByText("No contract yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start contract" }));
    const form = screen.getByRole("form", { name: "Start contract" });
    fireEvent.change(within(form).getByLabelText("Status"), { target: { value: "proposal_sent" } });
    fireEvent.change(within(form).getByLabelText("Agreement type"), { target: { value: "Permanent hiring" } });
    fireEvent.change(within(form).getByLabelText("Fee basis"), { target: { value: "fixed" } });
    fireEvent.change(within(form).getByLabelText("Recruitment fee (₹)"), { target: { value: "50000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Start contract" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Contract started."));
    expect(sent("POST").body).toEqual({ status: "proposal_sent", agreement_type: "Permanent hiring", fee_basis: "fixed", fee_value: "50000" });
  });

  it("draws the ladder in source order with the current step, the terms and the fee", async () => {
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    const steps = within(await screen.findByRole("list", { name: "Contract statuses" })).getAllByRole("listitem");
    expect(steps.map((s) => s.querySelector(".jny-name")?.textContent)).toEqual(["Discussion", "Proposal Sent", "Negotiation", "Contract Sent", "Signed", "Active", "Expired"]);
    expect(steps[0].textContent).toContain("Done");
    expect(steps[1].getAttribute("aria-current")).toBe("step");
    expect(screen.getByText("₹50,000 per hire")).toBeTruthy();
    expect(screen.getByText("No contract document on file.")).toBeTruthy();
    expect(screen.getByLabelText(/Upload contract document/)).toBeTruthy();
  });

  it("sends only the changed fields with from_status and the version, and places a 422 on its field", async () => {
    write = () => res({ detail: [{ loc: ["body", "status"], msg: "Upload the signed contract document first", type: "value_error" }] }, 422);
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit contract" }));
    const form = screen.getByRole("form", { name: "Edit contract" });
    expect(within(form).getByText(/Signed and Active need the contract document/)).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Status"), { target: { value: "signed" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save contract" }));
    expect(await within(form).findByText("Upload the signed contract document first")).toBeTruthy();
    expect(sent("PATCH").body).toEqual({ status: "signed", from_status: "proposal_sent", expected_updated_at: "2026-10-01T05:30:00Z" });
  });

  it("shows Expired automatically, locks the status and offers a renewal", async () => {
    read = () => res({
      current: contract({ status: "expired", status_label: "Expired", expired_on: "2026-04-01", end_date: "2026-03-31",
        contract_document: { name: "signed.pdf", content_type: "application/pdf", uploaded_at: "2026-01-01T05:30:00Z" },
        permissions: { can_edit: true, can_upload: true, can_renew: true } }),
      previous: [contract({ id: "K0", status: "expired", status_label: "Expired", is_current: false, permissions: { can_edit: false, can_upload: false, can_renew: false } })],
      can_start: true,
    });
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    expect(await screen.findByText(/^Expired on/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download contract document (PDF)" }).getAttribute("href")).toBe("/api/v1/recruiter/contracts/K1/documents/contract");
    expect(screen.getByText("Previous contracts (1)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit contract" }));
    expect((within(screen.getByRole("form", { name: "Edit contract" })).getByLabelText("Status") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Start renewal" }));
    expect(screen.getByRole("form", { name: "Start contract" })).toBeTruthy();
  });

  it("is read only without permissions and shows a coded 409 after reloading", async () => {
    read = () => res({ current: contract({ permissions: { can_edit: false, can_upload: false, can_renew: false } }), previous: [], can_start: false });
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    await screen.findByRole("list", { name: "Contract statuses" });
    expect(screen.queryByRole("button", { name: "Edit contract" })).toBeNull();
    expect(screen.queryByLabelText(/Upload contract document/)).toBeNull();
    expect(contractConflict({ code: "contract_changed", message: "This contract was changed meanwhile" })).toBe("This contract was changed meanwhile. Check it and try again.");
    expect(contractConflict({ code: "contract_overlap", message: "x" })).toBeNull(); // stays on the form
  });

  it("offers Try again when the first load fails", async () => {
    read = () => res({ detail: "boom" }, 500);
    render(<RecruiterCompanyContract companyId="C1" onChanged={vi.fn()} />);
    expect(await screen.findByText("Unable to load the contract.")).toBeTruthy();
    read = () => res({ current: null, previous: [], can_start: false });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No contract yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Start contract" })).toBeNull();
  });

  it("formats the fee for both bases", () => {
    expect(feeText({ fee_basis: "percent_of_ctc", fee_value: "8.33" })).toBe("8.33% of CTC");
    expect(feeText({ fee_basis: null, fee_value: null })).toBe("—");
  });
});
