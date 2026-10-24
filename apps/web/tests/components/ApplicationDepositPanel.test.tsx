import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationDepositPanel from "@/components/ApplicationDepositPanel";

// ccrm-025 (DEC-SCOPE-255, D2): the counselor's manual deposit record beside the Offers panel.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const EMPTY = { record: null, agency_deposit: null, prefill: { amount: "3000.00", currency: "GBP", due_date: "2026-11-30" }, receipts: [] };
const DEPOSIT = "/api/v1/workflows/overseas/applications/a1/deposit";

describe("ApplicationDepositPanel", () => {
  it("shows loading, then the empty state, and a load failure with a retry", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Application not found" }, false, 404)).mockReturnValue(json(EMPTY));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDepositPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(screen.getByText("Loading deposit…")).toBeInTheDocument();
    expect(await screen.findByText("Application not found")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No deposit recorded yet.")).toBeInTheDocument();
  });

  it("shows an agency deposit read-only, with no form", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ ...EMPTY, agency_deposit: { status: "not_required", amount: null, currency: "INR", due_date: null } })));
    render(<ApplicationDepositPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText(/Paid by the agency through EduSphere: no amount, status not required/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record deposit" })).not.toBeInTheDocument();
  });

  it("starts from the offer's deposit and saves a paid record", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ changed: true, record: {} }) : json(EMPTY)));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDepositPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record deposit" }));
    expect(screen.getByLabelText("Amount")).toHaveValue(3000);
    expect(screen.getByLabelText("Currency")).toHaveValue("GBP");
    fireEvent.change(screen.getByLabelText("Payment status"), { target: { value: "paid_via_edusphere" } });
    fireEvent.change(screen.getByLabelText("Paid on"), { target: { value: "2026-10-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Save deposit" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Deposit saved."));
    const put = fetchMock.mock.calls.find(([url, init]) => url === DEPOSIT && init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({
      required: true, amount: "3000.00", currency: "GBP", due_date: "2026-11-30", payment_status: "paid_via_edusphere", paid_on: "2026-10-20", receipt_document_id: null,
    });
  });

  it("records that no deposit is required", async () => {
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => (init?.method === "PUT" ? json({ detail: "Application is closed" }, false, 409) : json(EMPTY)));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDepositPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record deposit" }));
    fireEvent.click(screen.getByLabelText("No"));
    expect(screen.queryByLabelText("Amount")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save deposit" }));
    expect(await screen.findByText("Application is closed")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([url, init]) => url === DEPOSIT && init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ required: false, payment_status: "not_required" });
  });
});
