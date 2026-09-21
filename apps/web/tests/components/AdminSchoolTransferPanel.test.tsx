import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolTransferPanel from "@/components/AdminSchoolTransferPanel";
import type { AdminTransferRequest } from "@/lib/transfers";

// ENH-005 -- the admin's queue (spec §5.3, §7.1): loads after first paint, two-step approve/reject, and every state.
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const A = { id: "a", name: "Sunrise School" };
const B = { id: "b", name: "Lakeview School" };

function request(n: string, over: Partial<AdminTransferRequest> = {}): AdminTransferRequest {
  return {
    id: `req-${n}`, direction: "outgoing", status: "pending", student_id: `s-${n}`, student_code: `CODE000${n}`, student_name: `Child ${n}`, from_school: A, to_school: B, filed_by_school: A,
    requester: { id: "u1", name: "Fatima Coordinator" }, reason: "Family is moving", decision_note: null, decided_by: null, outcome: null,
    preview: { linked_parents: 2, in_flight_results: 3, to_school_has_portfolio_staff: true }, created_at: "2026-09-20T10:00:00Z", decided_at: null, ...over,
  };
}
const page = (items: AdminTransferRequest[], total = items.length) => ({ items, total, limit: 25, offset: 0 });
const OUTCOME = { parents_moved: 1, parents_kept: 1, results_withdrawn: 3, teacher_cleared: true, pending_parent_email_cleared: false };

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const rowOf = (text: RegExp) => screen.getAllByRole("listitem").find((li) => text.test(li.textContent ?? ""))!;
const trigger = (name: RegExp) => screen.getByRole("button", { name });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolTransferPanel", () => {
  it("loads after first paint: a skeleton with aria-busy, then the queue with its count", async () => {
    let release!: (r: Response) => void;
    stubFetch(() => new Promise<Response>((resolve) => (release = resolve)) as unknown as Response);
    render(<AdminSchoolTransferPanel />);
    expect(screen.getByText("Loading transfer requests…")).toBeTruthy();
    expect(document.querySelector("[aria-busy=true]")).toBeTruthy();
    release(json(page([request("1")])));
    expect(await screen.findByRole("heading", { name: "Transfer requests (1)" })).toBeTruthy();
    expect(document.querySelector("[aria-busy=true]")).toBeNull();
  });

  it("shows who, from and to, the requester, the reason, and what approval would touch", async () => {
    stubFetch(() => json(page([request("1")])));
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    const row = rowOf(/Child 1/);
    for (const text of [/CODE0001/, /Sunrise School/, /Lakeview School/, /Fatima Coordinator/, /Family is moving/, /2 linked parent accounts/, /3 unpublished results/]) {
      expect(within(row).getByText(text)).toBeTruthy();
    }
    expect(within(row).getByText("Pending review")).toBeTruthy();
  });

  it("warns, in words, when the destination has no staff portfolio", async () => {
    stubFetch(() => json(page([request("1", { preview: { linked_parents: 0, in_flight_results: 0, to_school_has_portfolio_staff: false } })])));
    render(<AdminSchoolTransferPanel />);
    const warning = await screen.findByText(/has no assigned staff portfolio/);
    expect(warning.closest(".form-warning")).toBeTruthy();
  });

  it("names the student and the school on every action button", async () => {
    stubFetch(() => json(page([request("1")])));
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    expect(trigger(/^Approve transfer of Child 1 to Lakeview School$/).textContent).toBe("Approve");
    expect(trigger(/^Reject transfer of Child 1 to Lakeview School$/).textContent).toBe("Reject");
  });

  it("approve is two-step: consequences and Confirm take focus, Escape puts focus back on Approve and sends nothing", async () => {
    const fetchMock = stubFetch(() => json(page([request("1")])));
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    fireEvent.click(trigger(/^Approve transfer of Child 1/));
    const confirm = screen.getByRole("button", { name: "Confirm approval" });
    expect(document.activeElement).toBe(confirm);
    expect(screen.getByText(/Moves Child 1 to Lakeview School/)).toBeTruthy();
    expect(screen.getByText(/Up to 2 linked parent accounts move to Lakeview School if they have no other child at Sunrise School/)).toBeTruthy();
    expect(screen.getByText(/3 unpublished results are withdrawn/)).toBeTruthy();
    fireEvent.keyDown(confirm, { key: "Escape" });
    await waitFor(() => expect(document.activeElement).toBe(trigger(/^Approve transfer of Child 1/)));
    expect(screen.queryByRole("button", { name: "Confirm approval" })).toBeNull();
    expect(fetchMock.mock.calls.every(([, init]) => (init?.method ?? "GET") === "GET")).toBe(true);
  });

  it("approves: disabled while sending, then the row leaves the pending queue and the outcome is announced", async () => {
    let release!: (r: Response) => void;
    const fetchMock = stubFetch((url) => (url.endsWith("/approve") ? (new Promise<Response>((resolve) => (release = resolve)) as unknown as Response) : json(page([request("1")]))));
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    fireEvent.click(trigger(/^Approve transfer of Child 1/));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    const busy = await screen.findByRole("button", { name: "Approving…" });
    expect((busy as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(busy);
    expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/approve"))).toHaveLength(1);
    release(json(request("1", { status: "approved", outcome: OUTCOME, preview: null, decided_at: "2026-09-21T10:00:00Z" })));
    await waitFor(() => expect(screen.queryAllByRole("listitem").some((li) => /Child 1/.test(li.textContent ?? ""))).toBe(false));
    const announced = screen.getByRole("status").textContent ?? "";
    expect(announced).toContain("Moved Child 1 to Lakeview School.");
    expect(announced).toContain("1 parent moved, 1 kept, 3 results withdrawn");
  });

  it("rejects with an optional note, shown with the visibility hint, and sends it", async () => {
    const fetchMock = stubFetch((url) => (url.endsWith("/reject") ? json(request("1", { status: "rejected", decision_note: "Resubmit next term" })) : json(page([request("1")]))));
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    fireEvent.click(trigger(/^Reject transfer of Child 1/));
    expect(screen.getByText(/Visible to the requesting coordinator\. Do not include student details\./)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Note for the requesting coordinator (optional)"), { target: { value: "Resubmit next term" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm rejection" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Request rejected"));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/reject"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({ note: "Resubmit next term" });
  });

  it("shows the server's message for an already-decided request and refreshes the queue", async () => {
    let calls = 0;
    const fetchMock = stubFetch((url) => {
      if (url.endsWith("/approve")) return json({ detail: "This transfer request has already been decided" }, 409);
      calls += 1;
      return json(page(calls === 1 ? [request("1")] : []));
    });
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    fireEvent.click(trigger(/^Approve transfer of Child 1/));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already been decided");
    await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => String(u).includes("school-transfer-requests?status=")).length).toBeGreaterThanOrEqual(2));
  });

  it("shows an empty queue, and a load failure with a retry", async () => {
    let ok = false;
    stubFetch(() => (ok ? json(page([])) : json({ detail: "boom" }, 500)));
    render(<AdminSchoolTransferPanel />);
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load transfer requests");
    ok = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No pending transfer requests.")).toBeTruthy();
  });

  it("approves ONCE when Confirm is clicked twice before React re-renders, and shows no stray error after the success", async () => {
    const fetchMock = stubFetch((url) => (url.endsWith("/approve") ? json(request("1", { status: "approved", outcome: OUTCOME, preview: null, decided_at: "2026-09-21T10:00:00Z" })) : json(page([request("1")]))));
    render(<AdminSchoolTransferPanel />);
    await screen.findByText(/Child 1/);
    fireEvent.click(trigger(/^Approve transfer of Child 1/));
    const confirm = screen.getByRole("button", { name: "Confirm approval" });
    act(() => {
      confirm.click();
      confirm.click();
    });
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Moved Child 1"));
    expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/approve"))).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
