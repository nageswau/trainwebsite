import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterApplicationOffer from "@/components/RecruiterApplicationOffer";
import StudentOffersCard from "@/components/StudentOffersCard";
import type { ApplicationOffer } from "@/lib/recruiterOffers";
import { recOffer } from "@/tests/helpers/recruiterOffers";

// rec-022 (spec §4; OF3-OF8; AC1, AC2): an application's offer (record with the suggested position, the moves the API allows, revise,
// the letter upload and download, history, a refusal in the server's words, read-only) and the student's own offers card.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/recruiter/requirements/J1" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let current: ApplicationOffer;
let writeReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  current = { offer: recOffer(), can_create: false };
  writeReply = () => res({ offer: recOffer({ status: "offer_received", status_label: "Offer Received" }) });
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method) return Promise.resolve(writeReply());
    if (url.endsWith("/applications/A1/offer")) return Promise.resolve(res(current));
    if (url === "/api/v1/workflows/it/student/offers") {
      return Promise.resolve(res({ items: [{ id: "O1", company: "Acme Technologies", requirement: "Java Dev", position: "Java Developer", status: "offer_received",
        status_label: "Offer Received", compensation: "600000.00", currency: "INR", offered_on: "2026-10-09", joining_date: null, has_letter: true, letter_url: null }] }));
    }
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

describe("RecruiterApplicationOffer", () => {
  it("shows the offer's §16 details, history and the letter download", async () => {
    current = { offer: recOffer({ letter: { name: "letter.pdf", content_type: "application/pdf", uploaded_at: "2026-10-09T06:00:00Z" } }), can_create: false };
    section();
    expect(screen.getByText("Loading offer…")).toBeTruthy();
    const card = await screen.findByRole("region", { name: /Offer for Rahul Kumar/ });
    for (const text of ["Offer Pending", "Java Developer", "INR 6,00,000.00", "Acme Technologies"]) expect(card.textContent).toContain(text);
    expect(within(card).getByRole("link", { name: /Download offer letter/ }).getAttribute("href")).toBe("/api/v1/recruiter/offers/O1/letter");
    expect(card.textContent).toContain("Recorded as Offer Pending");
  });

  it("records an offer for a Selected candidate, starting from the requirement title", async () => {
    current = { offer: null, can_create: true, suggested_position: "Java Dev" };
    writeReply = () => res({ offer: recOffer() }, 201);
    const onChanged = vi.fn();
    section(onChanged);
    expect(await screen.findByText("No offer yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Record offer/ }));
    const position = screen.getByLabelText(/Position/) as HTMLInputElement;
    expect(position.value).toBe("Java Dev");
    fireEvent.change(screen.getByLabelText(/Salary/), { target: { value: "600000" } });
    fireEvent.change(screen.getByLabelText(/Status/), { target: { value: "offer_received" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Offer recorded for Rahul Kumar."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/applications/A1/offer", "POST", { status: "offer_received", position: "Java Dev", compensation: 600000, currency: "INR" }]);
  });

  it("places a 422 on its field and keeps the typed values", async () => {
    current = { offer: null, can_create: true, suggested_position: "Java Dev" };
    writeReply = () => res({ detail: [{ loc: ["body", "joining_date"], msg: "The joining date cannot be before the offer date", type: "value_error" }] }, 422);
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Record offer/ }));
    fireEvent.change(screen.getByLabelText(/Joining date/), { target: { value: "2020-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    expect(await screen.findByText("The joining date cannot be before the offer date")).toBeTruthy();
    expect((screen.getByLabelText(/Joining date/) as HTMLInputElement).value).toBe("2020-01-01");
  });

  it("offers no record button when the API does not allow one (not Selected, or a reader)", async () => {
    current = { offer: null, can_create: false };
    section();
    expect(await screen.findByText("No offer yet.")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Record offer/ })).toBeNull();
  });

  it("moves the status with a note and reports it", async () => {
    const onChanged = vi.fn();
    section(onChanged);
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    fireEvent.change(screen.getByLabelText(/New status/), { target: { value: "offer_received" } });
    fireEvent.change(screen.getByLabelText(/Note/), { target: { value: "Letter emailed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save status" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Offer for Rahul Kumar is now Offer Received."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/offers/O1/status", "POST", { status: "offer_received", note: "Letter emailed" }]);
  });

  it("shows a refusal in the server's words", async () => {
    writeReply = () => res({ detail: "This offer is already decided" }, 409);
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Change status/ }));
    fireEvent.change(screen.getByLabelText(/New status/), { target: { value: "accepted" } });
    fireEvent.click(screen.getByRole("button", { name: "Save status" }));
    expect(await screen.findByText("This offer is already decided")).toBeTruthy();
  });

  it("revises only the changed fields", async () => {
    section();
    fireEvent.click(await screen.findByRole("button", { name: /Edit offer/ }));
    fireEvent.change(screen.getByLabelText(/Salary/), { target: { value: "650000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save offer" }));
    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/offers/O1", "PATCH", { compensation: 650000 }]);
  });

  it("uploads a letter", async () => {
    const onChanged = vi.fn();
    section(onChanged);
    const input = (await screen.findByLabelText(/Upload offer letter/)) as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["%PDF-1.4"], "letter.pdf", { type: "application/pdf" })] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Offer letter uploaded for Rahul Kumar."));
    expect(writes()[0]).toEqual(["/api/v1/recruiter/offers/O1/letter", "PUT", "form"]);
  });

  it("is read-only when the API allows nothing", async () => {
    current = { offer: recOffer({ allowed_statuses: [], can_edit: false, can_upload: false }), can_create: false };
    section();
    await screen.findByRole("region", { name: /Offer for Rahul Kumar/ });
    expect(screen.queryByRole("button", { name: /Change status|Edit offer/ })).toBeNull();
    expect(screen.queryByLabelText(/Upload offer letter/)).toBeNull();
  });

  it("offers Retry when the load fails", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({}, 500)));
    section();
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("region", { name: /Offer for Rahul Kumar/ })).toBeTruthy();
  });
});

describe("StudentOffersCard", () => {
  it("lists the student's own offers with the letter download", async () => {
    render(<StudentOffersCard />);
    const list = await screen.findByRole("list", { name: "My offers" });
    for (const text of ["Acme Technologies", "Java Developer", "Offer Received", "INR 6,00,000.00"]) expect(list.textContent).toContain(text);
    expect(within(list).getByRole("link", { name: /Download offer letter/ }).getAttribute("href")).toBe("/api/v1/workflows/it/student/offers/O1/letter");
  });

  it("has an empty state", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ items: [] })));
    render(<StudentOffersCard />);
    expect(await screen.findByText("No offers yet.")).toBeTruthy();
  });
});
