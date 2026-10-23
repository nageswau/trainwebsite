import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationOffersPanel from "@/components/ApplicationOffersPanel";
import { money } from "@/lib/applicationOffers";

// ccrm-023 (DEC-SCOPE-245): the counselor's Offers panel on an application card -- history, record (with a picked or uploaded
// letter) and close.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const offer = (over: Record<string, unknown> = {}) => ({
  id: "o1", offer_type: "conditional", offer_type_label: "Conditional", issue_date: "2026-10-01", offer_deadline: "2026-11-01", conditions: "IELTS 6.5",
  currency: "GBP", tuition_amount: "18500.00", scholarship_amount: null, deposit_amount: "3000.00", deposit_deadline: null,
  document: { id: "d1", name: "offer.pdf" }, status: "active", status_reason: null, recorded_by: "Asha", recorded_at: "2026-10-01T10:00:00Z", closed_by: null, closed_at: null, ...over,
});
const OFFERS = "/api/v1/workflows/overseas/applications/a1/offers";
const LETTERS = "/api/v1/workflows/overseas/applications/a1/offer-letters";

function fillOffer() {
  fireEvent.click(screen.getByLabelText("Conditional"));
  fireEvent.change(screen.getByLabelText("Issue date"), { target: { value: "2026-10-02" } });
  fireEvent.change(screen.getByLabelText(/^Conditions/), { target: { value: "IELTS 7.0" } });
  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "gbp" } });
  fireEvent.change(screen.getByLabelText("Tuition fee"), { target: { value: "18000" } });
}

describe("money", () => {
  it("formats an amount with its currency, and nothing when absent", () => {
    expect(money("GBP", "18500.00")).toBe("GBP 18,500.00");
    expect(money("GBP", null)).toBeNull();
  });
});

describe("ApplicationOffersPanel", () => {
  it("shows loading, then the empty state", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ offers: [], offer_letters: [] })));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(screen.getByText("Loading offers…")).toBeInTheDocument();
    expect(await screen.findByText("No offer recorded yet.")).toBeInTheDocument();
  });

  it("shows a load failure with a retry", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Application is outside your assigned scope" }, false, 403)).mockReturnValue(json({ offers: [], offer_letters: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText("Application is outside your assigned scope")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No offer recorded yet.")).toBeInTheDocument();
  });

  it("lists the current offer first and keeps superseded and closed ones", async () => {
    const offers = [offer(), offer({ id: "o0", status: "superseded", offer_type: "pathway", offer_type_label: "Pathway" }), offer({ id: "oz", status: "expired", status_reason: "Deadline passed" })];
    vi.stubGlobal("fetch", vi.fn(() => json({ offers, offer_letters: [] })));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    const items = await screen.findAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(items[0]).getByText("Current")).toBeInTheDocument();
    expect(within(items[0]).getByText("GBP 18,500.00")).toBeInTheDocument();
    expect(within(items[1]).getByText("Superseded")).toBeInTheDocument();
    expect(within(items[2]).getByText(/Deadline passed/)).toBeInTheDocument();
  });

  it("records an offer with a letter picked from the uploaded ones", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return json({ changed: true, offer: offer() }, true, 201);
      return json({ offers: [], offer_letters: [{ id: "d1", name: "offer.pdf" }] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationOffersPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record offer" }));
    fillOffer();
    fireEvent.change(screen.getByLabelText("Offer letter"), { target: { value: "d1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Offer recorded."));
    const post = fetchMock.mock.calls.find(([url, init]) => url === OFFERS && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({
      offer_type: "conditional", issue_date: "2026-10-02", offer_deadline: null, conditions: "IELTS 7.0", currency: "GBP",
      tuition_amount: "18000", scholarship_amount: null, deposit_amount: null, deposit_deadline: null, offer_document_id: "d1",
    });
  });

  it("uploads a new letter first, then records the offer with it", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url === LETTERS) return json({ document: { id: "d9", name: "new.pdf" } }, true, 201);
      if (init?.method === "POST") return json({ changed: true, offer: offer() }, true, 201);
      return json({ offers: [], offer_letters: [] });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record offer" }));
    fillOffer();
    fireEvent.change(screen.getByLabelText("Upload the offer letter (PDF or image)"), { target: { files: [new File(["%PDF-1.4"], "new.pdf", { type: "application/pdf" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => url === OFFERS && init?.method === "POST")).toBe(true));
    const order = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST").map(([url]) => url);
    expect(order).toEqual([LETTERS, OFFERS]);
    const post = fetchMock.mock.calls.find(([url, init]) => url === OFFERS && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body)).offer_document_id).toBe("d9");
  });

  it("asks for a letter before sending anything", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => ReturnType<typeof json>>(() => json({ offers: [], offer_letters: [] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record offer" }));
    fillOffer();
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    expect(await screen.findByText("Attach the offer letter: pick an uploaded one or upload the file.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.every(([, init]) => !init?.method)).toBe(true);
  });

  it("shows the server's refusal and keeps the form", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => (init?.method === "POST" ? json({ detail: "Choose the currency of the amounts" }, false, 422) : json({ offers: [], offer_letters: [{ id: "d1", name: "offer.pdf" }] }))));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record offer" }));
    fillOffer();
    fireEvent.change(screen.getByLabelText("Offer letter"), { target: { value: "d1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    expect(await screen.findByText("Choose the currency of the amounts")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save offer" })).toBeEnabled();
  });

  it("hides conditions for an unconditional offer", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ offers: [], offer_letters: [] })));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record offer" }));
    fireEvent.click(screen.getByLabelText("Unconditional"));
    expect(screen.queryByLabelText(/^Conditions/)).not.toBeInTheDocument();
  });

  it("closes the current offer with a reason", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "POST" ? json({ changed: true, offer: offer({ status: "expired" }) }) : json({ offers: [offer()], offer_letters: [] })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationOffersPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Close offer" }));
    fireEvent.change(screen.getByLabelText("Outcome"), { target: { value: "expired" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Deadline passed" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Offer marked expired."));
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
    expect(post?.[0]).toBe(`${OFFERS}/o1/withdraw`);
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ status: "expired", reason: "Deadline passed" });
  });
});
