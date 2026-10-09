import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterApplicationOffer from "@/components/RecruiterApplicationOffer";
import RecruiterJoiningsPanel from "@/components/RecruiterJoiningsPanel";
import type { ApplicationOffer, JoiningItem } from "@/lib/recruiterOffers";
import { recJoining, recOffer } from "@/tests/helpers/recruiterOffers";

// rec-023 (spec §4; JN1-JN8; AC1, AC2): the Joining section of an Accepted offer (the §17 facts, update with Joined / Did Not Join, the
// field errors, the proof upload and download, read-only) and the Joinings list (tabs, counts, overdue, empty, error + retry).
const push = vi.fn();
let search = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ refresh: vi.fn(), push }), usePathname: () => "/recruiter/joinings", useSearchParams: () => new URLSearchParams(search),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const accepted = (joining = recJoining()) => recOffer({ status: "accepted", status_label: "Accepted", allowed_statuses: [], can_edit: false, joining });
let current: ApplicationOffer;
let writeReply: () => Response;
let listReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
const item = (over: Partial<JoiningItem> = {}): JoiningItem => ({
  id: "O1", position: "Java Developer", offered_on: "2026-10-09", application: { id: "A1", status: "selected", status_label: "Selected" },
  candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" },
  company: { id: "CO1", name: "Acme Technologies" }, joining: recJoining({ overdue: true }), ...over,
});
beforeEach(() => {
  search = "";
  push.mockReset();
  current = { offer: accepted(), can_create: false };
  writeReply = () => res({ offer: accepted(recJoining({ status: "joined", status_label: "Joined", actual_joining_date: "2026-11-03", allowed_statuses: [], can_edit: false })) });
  listReply = () => res({ items: [item()], total: 1, limit: 50, offset: 0, counts: { due: 1, joined: 4, did_not_join: 0 } });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method) return Promise.resolve(writeReply());
    if (url.endsWith("/applications/A1/offer")) return Promise.resolve(res(current));
    if (url.startsWith("/api/v1/recruiter/joinings")) return Promise.resolve(listReply());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const writes = () => fetchMock.mock.calls.filter(([, init]) => init?.method).map(([url, init]) => [url, init.method, init.body instanceof FormData ? "form" : JSON.parse(init.body)]);
const section = (onChanged = vi.fn()) => render(<RecruiterApplicationOffer applicationId="A1" candidateName="Rahul Kumar" onChanged={onChanged} />);

describe("the Joining section", () => {
  it("is absent before the offer is Accepted", async () => {
    current = { offer: recOffer(), can_create: false };
    section();
    await screen.findByRole("region", { name: /Offer for Rahul Kumar/ });
    expect(screen.queryByRole("region", { name: /Joining/ })).toBeNull();
  });

  it("shows the §17 facts, the proof download and the overdue badge", async () => {
    current = { offer: accepted(recJoining({ location: "Pune", reporting_manager: "Anil Kumar", overdue: true,
      proof: { name: "mail.pdf", content_type: "application/pdf", uploaded_at: "2026-10-09T06:00:00Z" } })), can_create: false };
    section();
    const card = await screen.findByRole("region", { name: /Joining for Rahul Kumar/ });
    for (const text of ["Pending", "Overdue", "Pune", "Anil Kumar", "02 Nov 2026"]) expect(card.textContent).toContain(text);
    expect(within(card).getByRole("link", { name: /Download joining proof/ }).getAttribute("href")).toBe("/api/v1/recruiter/offers/O1/joining/proof");
  });

  it("marks Joined with the actual date and confirmation in one PUT (AC1)", async () => {
    const onChanged = vi.fn();
    section(onChanged);
    fireEvent.click(await screen.findByRole("button", { name: /Update joining/ }));
    const form = screen.getByRole("form", { name: "Update joining" });
    fireEvent.change(within(form).getByLabelText(/Joining status/), { target: { value: "joined" } });
    expect(form.textContent).toContain("also moves the candidate to Joined");
    fireEvent.change(within(form).getByLabelText(/Actual joining date/), { target: { value: "2026-11-03" } });
    fireEvent.change(within(form).getByLabelText(/Joining location/), { target: { value: "Pune" } });
    fireEvent.change(within(form).getByLabelText(/Confirmed by/), { target: { value: "HR - Priya" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save joining" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Joining for Rahul Kumar is now Joined."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/offers/O1/joining", "PUT", {
      joining_status: "joined", expected_joining_date: "2026-11-02", actual_joining_date: "2026-11-03", joining_location: "Pune", reporting_manager: null,
      confirmed_by: "HR - Priya", confirmed_on: null, reason: null,
    }]);
    const card = await screen.findByRole("region", { name: /Joining for Rahul Kumar/ });
    expect(within(card).queryByRole("button", { name: /Update joining/ })).toBeNull();
  });

  it("asks for a reason for Did Not Join and places the API's 422 on its field (AC2)", async () => {
    writeReply = () => res({ detail: [{ loc: ["body", "reason"], msg: "Enter why the candidate did not join (at least 2 characters)", type: "value_error" }] }, 422);
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Update joining/ }));
    const form = screen.getByRole("form", { name: "Update joining" });
    expect(within(form).queryByLabelText(/Reason/)).toBeNull();
    fireEvent.change(within(form).getByLabelText(/Joining status/), { target: { value: "did_not_join" } });
    expect(form.textContent).toContain("also moves the candidate to Withdrawn");
    fireEvent.change(within(form).getByLabelText(/Reason/), { target: { value: "x" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save joining" }));
    expect(await within(form).findByText("Enter why the candidate did not join (at least 2 characters)")).toBeTruthy();
    expect((within(form).getByLabelText(/Reason/) as HTMLTextAreaElement).value).toBe("x");
  });

  it("uploads the proof as a file", async () => {
    writeReply = () => res({ offer: accepted(recJoining({ proof: { name: "mail.pdf", content_type: "application/pdf", uploaded_at: "2026-10-09T06:00:00Z" } })) });
    const onChanged = vi.fn();
    section(onChanged);
    const input = await screen.findByLabelText(/Upload joining proof/);
    fireEvent.change(input, { target: { files: [new File(["%PDF-1.4"], "mail.pdf", { type: "application/pdf" })] } });
    fireEvent.click(within(input.closest("form") as HTMLElement).getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Joining proof uploaded for Rahul Kumar."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/offers/O1/joining/proof", "PUT", "form"]);
  });

  it("returns focus to Update joining on Cancel, and to the Joining heading once a move ends the editing (QA-02)", async () => {
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Update joining/ }));
    fireEvent.click(within(screen.getByRole("form", { name: "Update joining" })).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: /Update joining/ })));
    fireEvent.click(screen.getByRole("button", { name: /Update joining/ }));
    const form = screen.getByRole("form", { name: "Update joining" });
    fireEvent.change(within(form).getByLabelText(/Joining status/), { target: { value: "joined" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save joining" }));
    await waitFor(() => expect(document.activeElement?.textContent).toContain("Joining for Rahul Kumar"));
  });

  it("is read only for a reader", async () => {
    current = { offer: accepted(recJoining({ can_edit: false, can_upload_proof: false, allowed_statuses: [] })), can_create: false };
    section();
    const card = await screen.findByRole("region", { name: /Joining for Rahul Kumar/ });
    expect(within(card).queryByRole("button", { name: /Update joining/ })).toBeNull();
    expect(screen.queryByLabelText(/joining proof/)).toBeNull();
  });
});

describe("RecruiterJoiningsPanel", () => {
  it("lists the due joinings with counts, overdue and a link to the requirement", async () => {
    render(<RecruiterJoiningsPanel />);
    expect(screen.getByText("Loading joinings…")).toBeTruthy();
    const list = await screen.findByRole("list", { name: "Joinings" });
    expect(list.textContent).toContain("Rahul Kumar");
    expect(list.textContent).toContain("Overdue");
    expect(within(list).getByRole("link", { name: /Java Developer/ }).getAttribute("href")).toBe("/recruiter/requirements/J1");
    expect(screen.getByRole("button", { name: "Joining due (1)" }).getAttribute("aria-current")).toBe("page");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/recruiter/joinings?view=due&limit=50&offset=0");
    fireEvent.click(screen.getByRole("button", { name: "Joined (4)" }));
    expect(push).toHaveBeenCalledWith("/recruiter/joinings?view=joined", { scroll: false });
  });

  it("shows the empty state of the view and the reason of a Did Not Join", async () => {
    search = "view=did_not_join";
    listReply = () => res({ items: [], total: 0, limit: 50, offset: 0, counts: { due: 0, joined: 0, did_not_join: 0 } });
    render(<RecruiterJoiningsPanel />);
    expect(await screen.findByText("No candidates marked Did Not Join.")).toBeTruthy();
  });

  it("offers a retry when the list fails", async () => {
    listReply = () => res({ detail: "boom" }, 500);
    render(<RecruiterJoiningsPanel />);
    expect(await screen.findByText("Unable to load joinings.")).toBeTruthy();
    listReply = () => res({ items: [item({ joining: recJoining({ status: "did_not_join", status_label: "Did Not Join", reason: "Took another offer", allowed_statuses: [] }) })], total: 1, limit: 50, offset: 0, counts: { due: 0, joined: 0, did_not_join: 1 } });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    const list = await screen.findByRole("list", { name: "Joinings" });
    expect(list.textContent).toContain("Took another offer");
  });
});
