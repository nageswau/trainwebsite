import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UniversityCalls from "@/components/UniversityCalls";
import type { UniversityCall } from "@/lib/partnershipComms";

// upc-012 (UC1, AC3): the Calls section of a university -- loading/empty/error states, log a call on a contact (with a tel: link and an
// optional next follow-up date), server field errors on their fields, and the page refresh that moves the contact's last interaction.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn(), replace: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const call = (over: Partial<UniversityCall> = {}): UniversityCall => ({
  id: "L1", university_id: "U1", contact: { id: "K1", name: "Priya Raman" }, occurred_at: "2026-10-08T05:30:00Z", duration_seconds: 185,
  direction: "outgoing", outcome: "connected", outcome_label: "Connected", connected: true, notes: "Discussed the proposal",
  next_follow_up_on: "2026-10-12", caller: { id: "m1", full_name: "Maya Manager" }, created_at: "2026-10-08T05:31:00Z", ...over,
});
const contacts = [{ id: "K1", name: "Priya Raman", phone: "+44 20 7000 0000" }, { id: "K2", name: "Ravi Kumar", phone: null }];

let listReply: () => Promise<Response>;
let postReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  refresh.mockReset();
  listReply = () => Promise.resolve(res(pageOf([call(), call({ id: "L2", contact: null, outcome: "busy", outcome_label: "Busy", connected: false, notes: null, next_follow_up_on: null })])));
  postReply = () => res(call({ id: "L3" }), 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "POST" ? Promise.resolve(postReply()) : listReply()));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const posted = () => {
  const found = fetchMock.mock.calls.find(([, init]) => (init as RequestInit | undefined)?.method === "POST")!;
  return { url: String(found[0]), body: JSON.parse(String((found[1] as RequestInit).body)) };
};

describe("UniversityCalls (upc-012)", () => {
  it("lists calls newest first with outcome, contact, details, notes and the follow-up date", async () => {
    render(<UniversityCalls universityId="U1" contacts={contacts} canWrite />);
    expect(screen.getByText("Loading calls…")).toBeTruthy();
    const [first, second] = within(await screen.findByRole("list", { name: "Calls" })).getAllByRole("listitem");
    expect(first.textContent).toContain("Connected");
    expect(first.textContent).toContain("with Priya Raman");
    expect(first.textContent).toContain("3 min 5 s");
    expect(first.textContent).toContain("Maya Manager");
    expect(first.textContent).toContain("Discussed the proposal");
    expect(first.textContent).toMatch(/Next follow-up: .*12 Oct 2026/);
    expect(second.textContent).toContain("Not connected");
    expect(second.textContent).toContain("a removed contact");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/U1/calls?limit=50");
    expect(screen.queryAllByRole("status")).toHaveLength(0); // QA-02: no empty live region beside the page's own status messages
  });

  it("shows the empty state and hides Log call for a reader", async () => {
    listReply = () => Promise.resolve(res(pageOf([])));
    render(<UniversityCalls universityId="U1" contacts={contacts} canWrite={false} />);
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log call" })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    listReply = () => Promise.resolve(res({ detail: "boom" }, 500));
    render(<UniversityCalls universityId="U1" contacts={contacts} canWrite />);
    expect(await screen.findByText("Unable to load the calls.")).toBeTruthy();
    listReply = () => Promise.resolve(res(pageOf([])));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No calls logged yet.")).toBeTruthy();
  });

  it("logs a call on a contact, offers its tel: link, and refreshes the page (AC3)", async () => {
    render(<UniversityCalls universityId="U1" contacts={contacts} canWrite />);
    await screen.findByRole("list", { name: "Calls" });
    fireEvent.click(screen.getByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await within(form).findByText("Choose a contact")).toBeTruthy();
    expect(within(form).getByText("Choose an outcome")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("Contact (required)"), { target: { value: "K1" } });
    expect(within(form).getByRole("link", { name: /Call Priya Raman/ }).getAttribute("href")).toBe("tel:+442070000000");
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "connected" } });
    fireEvent.change(within(form).getByLabelText("Notes"), { target: { value: "  Sent the MoU draft  " } });
    fireEvent.change(within(form).getByLabelText("Next follow-up (optional)"), { target: { value: "2026-10-20" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    await waitFor(() => expect(screen.getByText("Call logged.")).toBeTruthy());
    const { url, body } = posted();
    expect(url).toBe("/api/v1/partnership/calls");
    expect(body).toMatchObject({ contact_id: "K1", outcome: "connected", direction: "outgoing", notes: "Sent the MoU draft", next_follow_up_on: "2026-10-20", duration_seconds: null });
    expect(refresh).toHaveBeenCalled();
  });

  it("places the server's field errors on the fields", async () => {
    postReply = () => res({ detail: [{ loc: ["body", "next_follow_up_on"], msg: "Choose a follow-up date from today to 365 days ahead" }] }, 422);
    render(<UniversityCalls universityId="U1" contacts={contacts} canWrite />);
    await screen.findByRole("list", { name: "Calls" });
    fireEvent.click(screen.getByRole("button", { name: "Log call" }));
    const form = screen.getByRole("form", { name: "Log call" });
    fireEvent.change(within(form).getByLabelText("Contact (required)"), { target: { value: "K2" } });
    expect(within(form).queryByRole("link", { name: /Call Ravi/ })).toBeNull(); // no phone, no tel: link
    fireEvent.change(within(form).getByLabelText("Outcome (required)"), { target: { value: "busy" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save call" }));
    expect(await within(form).findByText("Choose a follow-up date from today to 365 days ahead")).toBeTruthy();
    expect(refresh).not.toHaveBeenCalled();
  });

  it("says why a call cannot be logged when the university has no contacts", async () => {
    render(<UniversityCalls universityId="U1" contacts={[]} canWrite />);
    await screen.findByRole("list", { name: "Calls" });
    expect(screen.getByText("Add a contact to log a call.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Log call" })).toBeNull();
  });
});
