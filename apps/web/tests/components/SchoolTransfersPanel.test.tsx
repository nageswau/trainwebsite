import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolTransfersPanel from "@/components/SchoolTransfersPanel";
import type { TransferRequest } from "@/lib/transfers";

// ENH-005 -- the coordinator's own filed requests (spec §5.2, §7.1): status filter, "Load more", cancel, redaction, and the incoming form.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const LAKE = { id: "b", name: "Lakeview School" };
const SUN = { id: "a", name: "Sunrise School" };

function outgoing(n: string, over: Partial<TransferRequest> = {}): TransferRequest {
  return { id: `out-${n}`, direction: "outgoing", status: "pending", student_id: `s-${n}`, student_code: `CODE000${n}`, student_name: `Child ${n}`, from_school: SUN, to_school: LAKE, reason: null, decision_note: null, created_at: "2026-09-20T10:00:00Z", decided_at: null, ...over };
}
const redactedIncoming: TransferRequest = { id: "in-1", direction: "incoming", status: "pending", student_id: null, student_code: "A3F9C21B", student_name: null, from_school: null, to_school: SUN, reason: null, decision_note: null, created_at: "2026-09-20T11:00:00Z", decided_at: null };
const page = (items: TransferRequest[], total = items.length, offset = 0) => ({ items, total, limit: 25, offset });

// A listitem takes no accessible name from its content, so rows are found by their text (as ENH-004's promotion tests do).
const findRow = (text: RegExp) => screen.queryAllByRole("listitem").find((li) => text.test(li.textContent ?? "")) ?? null;
const row = (text: RegExp) => {
  const found = findRow(text);
  if (!found) throw new Error(`No row matching ${text}`);
  return found;
};

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SchoolTransfersPanel", () => {
  it("lists outgoing rows with the student, destination and a text status", () => {
    render(<SchoolTransfersPanel initial={page([outgoing("1")])} />);
    const item = row(/Child 1/);
    expect(within(item).getByText(/Lakeview School/)).toBeTruthy();
    expect(within(item).getByText("Pending review")).toBeTruthy();
    expect(screen.getByText("Showing 1 of 1")).toBeTruthy();
  });

  it("shows a redacted incoming row by its Student ID only, never blank cells or the word null", () => {
    render(<SchoolTransfersPanel initial={page([redactedIncoming])} />);
    const item = row(/A3F9C21B/);
    expect(within(item).getByText(/Student details are shown once approved/)).toBeTruthy();
    expect(item.textContent).not.toMatch(/null|undefined/);
  });

  it("explains how to start a request when nothing is pending, with a way to the roster", () => {
    render(<SchoolTransfersPanel initial={page([])} />);
    expect(screen.getByText("No pending requests.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Go to the student roster" }).getAttribute("href")).toBe("/school/coordinator/students");
  });

  it("changes filter: skeleton with aria-busy while loading, then the new rows; filtered-empty offers to show pending again", async () => {
    let release!: (r: Response) => void;
    const fetchMock = stubFetch((url) => (url.includes("status=cancelled") ? (new Promise<Response>((resolve) => (release = resolve)) as unknown as Response) : json(page([outgoing("1")]))));
    render(<SchoolTransfersPanel initial={page([outgoing("1")])} />);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "cancelled" } });
    await waitFor(() => expect(screen.getByRole("list", { name: "Transfer requests" }).getAttribute("aria-busy")).toBe("true"));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/school/transfer-requests?status=cancelled&limit=25&offset=0");
    release(json(page([])));
    expect(await screen.findByText("No cancelled requests.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Show pending" }));
    await waitFor(() => expect((screen.getByLabelText("Status") as HTMLSelectElement).value).toBe("pending"));
  });

  it("loads more, appending rows and updating the count, and hides the button when everything is shown", async () => {
    stubFetch(() => json(page([outgoing("2")], 2, 1)));
    render(<SchoolTransfersPanel initial={{ items: [outgoing("1")], total: 2, limit: 25, offset: 0 }} />);
    expect(screen.getByText("Showing 1 of 2")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Showing 2 of 2")).toBeTruthy();
    expect(screen.getAllByRole("listitem").filter((li) => /Child/.test(li.textContent ?? ""))).toHaveLength(2);
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("shows a load failure with a retry", async () => {
    let ok = false;
    stubFetch(() => (ok ? json(page([outgoing("1")])) : json({ detail: "boom" }, 500)));
    render(<SchoolTransfersPanel initial={page([outgoing("9")])} />);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "all" } });
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load transfer requests");
    ok = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await waitFor(() => row(/Child 1/))).toBeTruthy();
  });

  it("cancels a pending request: the button is disabled while sending, the row leaves the pending list, and the result is announced", async () => {
    let release!: (r: Response) => void;
    stubFetch((url) => (url.endsWith("/cancel") ? (new Promise<Response>((resolve) => (release = resolve)) as unknown as Response) : json(page([]))));
    render(<SchoolTransfersPanel initial={page([outgoing("1")])} />);
    const button = screen.getByRole("button", { name: "Cancel request for Child 1" });
    fireEvent.click(button);
    await waitFor(() => expect((screen.getByRole("button", { name: "Cancel request for Child 1" }) as HTMLButtonElement).disabled).toBe(true));
    release(json({ ...outgoing("1"), status: "cancelled" }));
    await waitFor(() => expect(findRow(/Child 1/)).toBeNull());
    // The panel and the embedded incoming form each mount a live region, so look across all of them.
    expect(screen.getAllByRole("status").map((el) => el.textContent).join(" ")).toContain("Request cancelled");
  });

  it("tells the coordinator when a cancel is refused because the request was already decided", async () => {
    stubFetch((url) => (url.endsWith("/cancel") ? json({ detail: "This transfer request has already been decided" }, 409) : json(page([]))));
    render(<SchoolTransfersPanel initial={page([outgoing("1")])} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel request for Child 1" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already been decided");
  });

  it("does not announce a cancel for a 200 that is not a request, and leaves the row where it is (browser QA N2)", async () => {
    stubFetch((url) => (url.endsWith("/cancel") ? new Response("<html>proxy login</html>", { status: 200 }) : json(page([]))));
    render(<SchoolTransfersPanel initial={page([outgoing("1")])} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel request for Child 1" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/could not be confirmed/i);
    expect(findRow(/Child 1/)).not.toBeNull();
    expect(screen.getAllByRole("status").map((el) => el.textContent).join(" ")).not.toContain("Request cancelled");
  });

  it("offers Cancel only on pending rows", () => {
    render(<SchoolTransfersPanel initial={page([outgoing("1"), outgoing("2", { status: "approved", decided_at: "2026-09-21T09:00:00Z" })])} />);
    expect(screen.getAllByRole("button", { name: /Cancel request for/ })).toHaveLength(1);
  });

  it("embeds the incoming-request form and reloads the list after a submit", async () => {
    const fetchMock = stubFetch((url) => (url.includes("/incoming") ? json({ accepted: true }, 202) : json(page([redactedIncoming]))));
    render(<SchoolTransfersPanel initial={page([])} />);
    fireEvent.change(screen.getByLabelText("Student ID"), { target: { value: "A3F9C21B" } });
    fireEvent.click(screen.getByRole("button", { name: /Request student/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).startsWith("/api/v1/school/transfer-requests?status=pending"))).toBe(true));
    expect(await waitFor(() => row(/A3F9C21B/))).toBeTruthy();
  });

  it("cancels ONCE when Cancel is clicked twice before React re-renders, with no stray error", async () => {
    const fetchMock = stubFetch((url) => (url.endsWith("/cancel") ? json({ ...outgoing("1"), status: "cancelled" }) : json(page([]))));
    render(<SchoolTransfersPanel initial={page([outgoing("1")])} />);
    const button = screen.getByRole("button", { name: "Cancel request for Child 1" });
    act(() => {
      button.click();
      button.click();
    });
    await waitFor(() => expect(screen.getAllByRole("status").map((el) => el.textContent).join(" ")).toContain("Request cancelled"));
    expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith("/cancel"))).toHaveLength(1);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

// QA-023-07: server-rendered (UTC) then hydrated in the browser, so the date must use the school zone or React reports #418 between
// 18:30 and 00:00 UTC. 20:00Z on the 21st is already the 22nd in IST.
describe("SchoolTransfersPanel dates", () => {
  it("shows a request's date in the school zone whatever the machine zone is", () => {
    render(<SchoolTransfersPanel initial={page([outgoing("1", { created_at: "2026-09-21T20:00:00Z" })])} />);
    expect(screen.getByText(/22 Sep\w* 2026/)).toBeTruthy();
  });
});
