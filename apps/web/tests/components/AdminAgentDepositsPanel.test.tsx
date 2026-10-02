import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminAgentDepositsPanel from "@/components/AdminAgentDepositsPanel";

// AGN-011 (DEC-SCOPE-058 §4.7, D3, D5): Overseas Admin's Agent deposits -- one status tab at a time, remittance and the one refund
// recorded by hand; super_admin reads only.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const ROW = {
  id: "dep1", application_id: "a1", agency: "Bright Futures", student: "Asha Rao", university: "Uni One", amount: "50000.00", currency: "INR",
  status: "paid", due_date: "2026-12-01", paid_at: "2026-10-01T10:00:00Z", paid_by: "Apps Staff", remitted_at: null, remittance_reference: null,
  refunded_at: null, refund_amount: null, refund_reason: null, unlinked_paid_payments: 0,
};
const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });

function serve(handler: (url: string, init?: RequestInit) => Response | undefined = () => undefined) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(url, init) ?? json(page([ROW]))));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
const posts = (fetchMock: ReturnType<typeof serve>) => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");

beforeEach(() => window.history.replaceState(null, "", "/overseas/admin/agent-deposits"));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminAgentDepositsPanel (AGN-011)", () => {
  it("lists paid deposits with agency, student, amount and payer", async () => {
    const fetchMock = serve();
    render(<AdminAgentDepositsPanel canAct />);
    const card = (await screen.findByText("Asha Rao")).closest(".card") as HTMLElement;
    expect(within(card).getByText(/Bright Futures/)).toBeTruthy();
    expect(within(card).getByText("₹50,000.00")).toBeTruthy();
    expect(within(card).getByText(/Apps Staff/)).toBeTruthy();
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/overseas-admin/deposits?status=paid&limit=20&offset=0");
  });

  it("shows the empty state and refetches on a tab change", async () => {
    const fetchMock = serve(() => json(page([])));
    render(<AdminAgentDepositsPanel canAct />);
    expect(await screen.findByText("No deposits with this status.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remitted" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("status=remitted"))).toBe(true));
    expect(window.location.search).toBe("?tab=remitted");
  });

  it("reports a load failure and retries", async () => {
    let fail = true;
    serve(() => (fail ? json({ detail: "boom" }, 500) : undefined));
    render(<AdminAgentDepositsPanel canAct />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load deposits.");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Asha Rao")).toBeTruthy();
  });

  it("records a remittance and announces it", async () => {
    const fetchMock = serve((url, init) => (init?.method === "POST" ? json({ ...ROW, status: "remitted", remitted_at: "2026-10-02", remittance_reference: "UTR 1" }) : undefined));
    render(<AdminAgentDepositsPanel canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Record remittance for Asha Rao" }));
    const form = screen.getByRole("form", { name: "Record remittance for Asha Rao" });
    fireEvent.change(within(form).getByLabelText("Remitted on"), { target: { value: "2026-10-02" } });
    fireEvent.change(within(form).getByLabelText("Remittance reference"), { target: { value: "UTR 1" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save remittance" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Remittance recorded for Asha Rao."));
    const [url, init] = posts(fetchMock)[0];
    expect(url).toBe("/api/v1/overseas-admin/deposits/dep1/remit");
    expect(JSON.parse(String(init!.body))).toEqual({ remitted_on: "2026-10-02", reference: "UTR 1" });
  });

  it("asks before recording a refund and keeps the entry on a 422", async () => {
    const fetchMock = serve((url, init) => (init?.method === "POST" ? json({ detail: "A refund cannot exceed the paid amount" }, 422) : undefined));
    render(<AdminAgentDepositsPanel canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Record refund for Asha Rao" }));
    const form = screen.getByRole("form", { name: "Record refund for Asha Rao" });
    expect(within(form).getByText("At most ₹50,000.00")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Refunded on"), { target: { value: "2026-10-02" } });
    fireEvent.change(within(form).getByLabelText(/Refund amount/), { target: { value: "60000" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "Visa refused" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save refund" }));
    expect(posts(fetchMock)).toHaveLength(0);
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm refund" })).getByRole("button", { name: "Yes, record refund" }));
    expect((await within(form).findByRole("alert")).textContent).toBe("A refund cannot exceed the paid amount");
    expect((within(form).getByLabelText(/Refund amount/) as HTMLInputElement).value).toBe("60000");
    expect(JSON.parse(String(posts(fetchMock)[0][1]!.body))).toEqual({ refunded_on: "2026-10-02", amount: "60000", reason: "Visa refused" });
  });

  it("warns about unlinked captured payments", async () => {
    serve(() => json(page([{ ...ROW, unlinked_paid_payments: 1 }])));
    render(<AdminAgentDepositsPanel canAct />);
    expect(await screen.findByText("1 other captured payment for this deposit needs a manual refund.")).toBeTruthy();
  });

  it("QA11-02: focus follows the result -- the error, the announced success, Save after Escape, the opener after Cancel", async () => {
    let fail = true;
    serve((url, init) => {
      if (init?.method !== "POST") return undefined;
      return fail ? json({ detail: "A refund cannot exceed the paid amount" }, 422) : json({ ...ROW, status: "refunded" });
    });
    render(<AdminAgentDepositsPanel canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Record refund for Asha Rao" }));
    const form = screen.getByRole("form", { name: "Record refund for Asha Rao" });
    fireEvent.change(within(form).getByLabelText(/Refund amount/), { target: { value: "60000" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "Visa refused" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save refund" }));
    fireEvent.keyDown(screen.getByRole("group", { name: "Confirm refund" }), { key: "Escape" });
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Save refund"));
    fireEvent.click(within(form).getByRole("button", { name: "Save refund" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, record refund" }));
    await waitFor(() => expect(document.activeElement?.getAttribute("role")).toBe("alert"));
    fail = false;
    fireEvent.change(within(form).getByLabelText(/Refund amount/), { target: { value: "20000" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save refund" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, record refund" }));
    await waitFor(() => expect(document.activeElement?.textContent).toBe("Refund recorded for Asha Rao."));
  });

  it("QA11-02: Cancel returns focus to the button that opened the form", async () => {
    serve();
    render(<AdminAgentDepositsPanel canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Record remittance for Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement?.getAttribute("aria-label")).toBe("Record remittance for Asha Rao"));
  });

  it("QA11-03: a refund amount that is not a number never reaches the confirmation", async () => {
    const fetchMock = serve();
    render(<AdminAgentDepositsPanel canAct />);
    fireEvent.click(await screen.findByRole("button", { name: "Record refund for Asha Rao" }));
    const form = screen.getByRole("form", { name: "Record refund for Asha Rao" });
    fireEvent.change(within(form).getByLabelText(/Refund amount/), { target: { value: "abc" } });
    fireEvent.change(within(form).getByLabelText("Reason"), { target: { value: "Visa refused" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save refund" }));
    expect(screen.queryByRole("group", { name: "Confirm refund" })).toBeNull();
    expect(posts(fetchMock)).toHaveLength(0);
  });

  it("QA11-06: a page past the end falls back to the last page", async () => {
    window.history.replaceState(null, "", "/overseas/admin/agent-deposits?page=99");
    const fetchMock = serve((url) => (String(url).includes("offset=1960") ? json({ items: [], total: 1, limit: 20, offset: 1960 }) : undefined));
    render(<AdminAgentDepositsPanel canAct />);
    expect(await screen.findByText("Asha Rao")).toBeTruthy();
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("offset=0"))).toBe(true);
    expect(window.location.search).toBe("");
  });

  it("offers no actions to a reader (super_admin)", async () => {
    serve();
    render(<AdminAgentDepositsPanel canAct={false} />);
    await screen.findByText("Asha Rao");
    expect(screen.queryByRole("button", { name: /Record remittance/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Record refund/ })).toBeNull();
  });
});
