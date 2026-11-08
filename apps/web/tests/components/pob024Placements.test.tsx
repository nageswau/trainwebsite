import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PlacementDetail from "@/components/PlacementDetail";
import PlacementsPanel from "@/components/PlacementsPanel";
import type { Placement, PlacementItem } from "@/lib/placements";

// pob-024 (DEC-SCOPE-432): the placements list (tabs, counts, empty, error + retry) and one placement (facts, confirmations, the invoice
// draft review: issue and discard, the commercial block hidden without the grant).
const push = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }), usePathname: () => "/recruiter/placements", useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const item = (over: Partial<PlacementItem> = {}): PlacementItem => ({
  id: "P1", status: "joined", status_label: "Joined", role: "Java Developer", joined_on: "2026-11-01",
  candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" },
  company: { id: "CO1", name: "Acme Technologies" }, invoice_status: "draft", invoice_status_label: "Draft to review", ...over,
});
const placement = (over: Partial<Placement> = {}): Placement => ({
  id: "P1", status: "joined", status_label: "Joined", role: "Java Developer", offer_id: "O1", application: { id: "A1", code: "APP-1" },
  candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" },
  company: { id: "CO1", name: "Acme Technologies" }, vendor: null, recruiter: { id: "U1", full_name: "Asha Rao", active: true }, po_owner: null,
  source: "Referral", package: { compensation: "600000.00", currency: "INR" },
  joining: { expected_joining_date: "2026-11-01", actual_joining_date: "2026-11-01" }, candidate_confirmation: null, client_confirmation: null,
  commercials: { expected_fee: "50000.00", invoice: { status: "draft", status_label: "Draft to review", draft_amount: "50000.00", draft_due_date: "2026-12-01",
    draft_created_at: "2026-11-01T10:00:00Z", discard_reason: null, invoice: null } },
  permissions: { can_edit: true, can_change_owner: false, can_invoice: true }, ...over,
});
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  search = "";
  push.mockReset();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PlacementsPanel", () => {
  it("lists the view with its counts and links each placement", async () => {
    fetchMock.mockResolvedValue(res({ items: [item()], total: 1, limit: 25, offset: 0, counts: { pending: 2, joined: 1, did_not_join: 0, invoice_drafts: 1 } }));
    render(<PlacementsPanel />);
    const list = await screen.findByRole("list", { name: "Placements" });
    expect(within(list).getByRole("link", { name: "Rahul Kumar" })).toHaveAttribute("href", "/recruiter/placements/P1");
    expect(within(list).getByText("Invoice: Draft to review")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Joining pending (2)" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("button", { name: "Invoice drafts (1)" }));
    expect(push).toHaveBeenCalledWith("/recruiter/placements?view=invoice_drafts", { scroll: false });
  });

  it("shows the empty text, and an error with a retry", async () => {
    search = "view=invoice_drafts";
    fetchMock.mockResolvedValueOnce(res({ detail: "x" }, 500)).mockResolvedValueOnce(res({ items: [], total: 0, limit: 25, offset: 0, counts: { pending: 0, joined: 0, did_not_join: 0, invoice_drafts: 0 } }));
    render(<PlacementsPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load placements.");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No invoice drafts to review.")).toBeInTheDocument();
  });
});

describe("PlacementDetail", () => {
  it("shows the record, the package and the draft", () => {
    render(<PlacementDetail initial={placement()} />);
    expect(screen.getByText("Referral")).toBeInTheDocument();
    expect(screen.getByText("INR 6,00,000")).toBeInTheDocument();
    const invoice = screen.getByRole("region", { name: "Invoice" });
    expect(within(invoice).getByText("Draft to review")).toBeInTheDocument();
    expect(within(invoice).getAllByText("₹50,000.00").length).toBe(2);
  });

  it("issues the draft with the reviewed values and shows the issued state", async () => {
    const issued = placement({ permissions: { can_edit: true, can_change_owner: false, can_invoice: false } });
    issued.commercials!.invoice = { ...issued.commercials!.invoice, status: "issued", status_label: "Issued" };
    fetchMock.mockResolvedValue(res({ placement: issued }, 201));
    render(<PlacementDetail initial={placement()} />);
    fireEvent.click(screen.getByRole("button", { name: "Issue invoice" }));
    const form = screen.getByRole("form", { name: "Issue invoice" });
    fireEvent.change(within(form).getByLabelText("Invoice number"), { target: { value: " INV-77 " } });
    expect(within(form).getByLabelText("Amount (₹)")).toHaveValue("50000.00");
    expect(within(form).getByLabelText("Payment due date")).toHaveValue("2026-12-01");
    fireEvent.click(within(form).getByRole("button", { name: "Issue invoice" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Invoice issued. It now shows in Receivables."));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/recruiter/placements/P1/invoice-draft/issue");
    expect(JSON.parse(init.body)).toMatchObject({ invoice_number: "INV-77", amount: "50000.00", due_date: "2026-12-01", note: null });
    expect(screen.queryByRole("button", { name: "Issue invoice" })).not.toBeInTheDocument();
  });

  it("keeps a refusal on the form and puts 422s on their fields", async () => {
    fetchMock
      .mockResolvedValueOnce(res({ detail: { message: "This invoice number is already used", code: "invoice_number_taken" } }, 409))
      .mockResolvedValueOnce(res({ detail: [{ loc: ["body", "reason"], msg: "Enter a reason" }] }, 422));
    render(<PlacementDetail initial={placement()} />);
    fireEvent.click(screen.getByRole("button", { name: "Issue invoice" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Issue invoice" })).getByRole("button", { name: "Issue invoice" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This invoice number is already used");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    fireEvent.click(within(screen.getByRole("form", { name: "Discard invoice draft" })).getByRole("button", { name: "Discard draft" }));
    expect(await screen.findByText("Enter a reason")).toBeInTheDocument();
  });

  it("records a confirmation", async () => {
    const saved = placement({ client_confirmation: { by: "HR - Priya", on: "2026-11-01", via: "email", via_label: "Email" } });
    fetchMock.mockResolvedValue(res({ placement: saved }));
    render(<PlacementDetail initial={placement()} />);
    const card = screen.getByRole("region", { name: "Client confirmation" });
    fireEvent.click(within(card).getByRole("button", { name: "Record confirmation" }));
    fireEvent.change(within(card).getByLabelText("Confirmed by"), { target: { value: "HR - Priya" } });
    fireEvent.change(within(card).getByLabelText("How"), { target: { value: "email" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save" }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Client confirmation saved."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).client_confirmation).toMatchObject({ by: "HR - Priya", via: "email" });
    expect(screen.getByText(/HR - Priya · .* · Email/)).toBeInTheDocument();
  });

  it("hides the commercials and the writes without access", () => {
    render(<PlacementDetail initial={placement({ commercials: null, package: null, permissions: { can_edit: false, can_change_owner: false, can_invoice: false } })} />);
    expect(screen.queryByRole("region", { name: "Invoice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record confirmation" })).not.toBeInTheDocument();
    expect(screen.queryByText("Package")).not.toBeInTheDocument();
  });
});
