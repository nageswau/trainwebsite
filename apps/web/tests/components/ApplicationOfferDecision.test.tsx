import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationOffersPanel from "@/components/ApplicationOffersPanel";
import { acceptedMessage } from "@/lib/applicationOffers";

// ccrm-025 (DEC-SCOPE-255): recording the student's decision on the current offer from the counselor's Offers panel.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const offer = (over: Record<string, unknown> = {}) => ({
  id: "o1", offer_type: "conditional", offer_type_label: "Conditional", issue_date: "2026-10-01", offer_deadline: "2026-11-01", conditions: "IELTS 6.5",
  currency: "GBP", tuition_amount: "18500.00", scholarship_amount: null, deposit_amount: "3000.00", deposit_deadline: null, document: null,
  status: "active", status_reason: null, recorded_by: "Asha", recorded_at: "2026-10-01T10:00:00Z", closed_by: null, closed_at: null,
  decision: "considering", decision_label: "Considering", decision_date: null, decided_by: null, ...over,
});
const DECISION = "/api/v1/workflows/overseas/applications/a1/offers/o1/decision";

function mockFetch(current: Record<string, unknown>, post: () => Promise<unknown>) {
  const fetchMock = vi.fn((_url: string, init?: RequestInit) => (init?.method === "POST" ? post() : json({ offers: [current], offer_letters: [] })));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("acceptedMessage", () => {
  it("names the other accepted offers, or says nothing more", () => {
    expect(acceptedMessage([])).toBe("Offer accepted.");
    expect(acceptedMessage([{ id: "x", application_code: "APP-000007", university: "Leeds" }])).toBe("Offer accepted. Note: this student has also accepted an offer on APP-000007 (Leeds).");
  });
});

describe("Offer decision", () => {
  it("shows the decision and offers accept and decline only on an undecided current offer", async () => {
    mockFetch(offer(), () => json({}));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText("Considering")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record acceptance" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record decline" })).toBeInTheDocument();
  });

  it("an accepted offer can still be declined but not accepted again", async () => {
    mockFetch(offer({ decision: "accepted", decision_label: "Accepted", decision_date: "2026-10-05", decided_by: "Asha" }), () => json({}));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText(/on 2026-10-05 \(recorded by Asha\)/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Record acceptance" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Record decline" })).toBeInTheDocument();
  });

  it("records an acceptance and passes on the D1 warning", async () => {
    const onChanged = vi.fn();
    const fetchMock = mockFetch(offer(), () => json({ changed: true, other_accepted: [{ id: "a2", application_code: "APP-000002", university: "Leeds" }] }));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record acceptance" }));
    fireEvent.change(screen.getByLabelText("Acceptance date"), { target: { value: "2026-10-03" } });
    fireEvent.click(screen.getByRole("button", { name: "Save acceptance" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Offer accepted. Note: this student has also accepted an offer on APP-000002 (Leeds)."));
    const post = fetchMock.mock.calls.find(([url, init]) => url === DECISION && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toEqual({ decision: "accepted", decision_date: "2026-10-03" });
  });

  it("records a decline with its reason, and shows a server refusal", async () => {
    const onChanged = vi.fn();
    const fetchMock = mockFetch(offer(), () => json({ detail: "This application is on hold -- resume it before changing its stage" }, false, 409));
    render(<ApplicationOffersPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Record decline" }));
    expect(screen.getByText(/only the Overseas Admin can reopen it/)).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Chose Leeds" } });
    fireEvent.click(screen.getByLabelText("The student prefers another offer"));
    fireEvent.click(screen.getByRole("button", { name: "Save decline" }));
    expect(await screen.findByText("This application is on hold -- resume it before changing its stage")).toBeInTheDocument();
    expect(onChanged).not.toHaveBeenCalled();
    const post = fetchMock.mock.calls.find(([url, init]) => url === DECISION && init?.method === "POST");
    expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ decision: "declined", reason: "Chose Leeds", another_offer_preferred: true });
  });
});
