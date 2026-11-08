import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PlacementDetail from "@/components/PlacementDetail";
import PlacementSurveyForm from "@/components/PlacementSurveyForm";
import type { Placement, Survey } from "@/lib/placements";

// pob-026 (DEC-SCOPE-435 S10/S12): the public survey (loading, form, rating required, thank-you, a used/expired or unknown link, a
// dropped network with a retry) and the Satisfaction section on the placement.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const SURVEY = { respondent: "client", role: "Java Developer", company: "Acme Technologies" };
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("PlacementSurveyForm", () => {
  it("asks for a rating, then sends it once with the trimmed comment", async () => {
    fetchMock.mockResolvedValueOnce(res(SURVEY)).mockResolvedValueOnce(res({ ok: true }, 201));
    render(<PlacementSurveyForm token="tok.en" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your survey");
    expect(await screen.findByText(/the candidate we placed in the Java Developer role at Acme Technologies/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/public/placement-surveys/tok.en", { cache: "no-store" });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(await screen.findByText("Choose a rating from 1 to 5")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("radio", { name: /4 · Satisfied/ }));
    fireEvent.change(screen.getByLabelText("Comment (optional)"), { target: { value: "  Smooth hire  " } });
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(await screen.findByRole("heading", { name: "Thank you for your feedback" })).toHaveFocus();
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/public/placement-surveys/tok.en");
    expect(JSON.parse(init.body)).toEqual({ rating: 4, comment: "Smooth hire" });
  });

  it.each([
    [410, "already been used or has expired"],
    [404, "is not valid"],
    [429, "Too many attempts"],
  ])("explains a %i link", async (status, text) => {
    fetchMock.mockResolvedValueOnce(res({ detail: "x" }, status));
    render(<PlacementSurveyForm token="t" />);
    expect(await screen.findByRole("heading", { name: "Feedback link closed" })).toBeInTheDocument();
    expect(screen.getByText(new RegExp(text))).toBeInTheDocument();
    expect(screen.queryByText(/nothing more to do/)).toBeNull(); // QA-01: an expired, unanswered link must not thank the reader
  });

  it("closes the form when the answer races another (410 on send)", async () => {
    fetchMock.mockResolvedValueOnce(res({ ...SURVEY, respondent: "candidate" })).mockResolvedValueOnce(res({ detail: "gone" }, 410));
    render(<PlacementSurveyForm token="t" />);
    expect(await screen.findByText(/your placement as Java Developer/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /5 · Very satisfied/ }));
    fireEvent.click(screen.getByRole("button", { name: "Send feedback" }));
    expect(await screen.findByText(/already been used/)).toBeInTheDocument();
  });

  it("offers a retry when the network drops", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(res(SURVEY));
    render(<PlacementSurveyForm token="t" />);
    const alert = await screen.findByRole("alert");
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("radio", { name: /1 · Very dissatisfied/ })).toBeInTheDocument();
  });
});

const survey = (over: Partial<NonNullable<Survey>>): Survey => ({
  status: "sent", status_label: "Sent", sent_at: "2026-11-01T04:00:00Z", resent_at: null, responded_at: null, rating: null, comment: null,
  skip_reason: null, skip_reason_label: null, ...over,
});
const placement = (satisfaction: Placement["satisfaction"]): Placement => ({
  id: "P1", status: "joined", status_label: "Joined", role: "Java Developer", offer_id: "O1", application: { id: "A1", code: "APP-1" },
  candidate: { id: "C1", code: "CAN-000001", name: "Rahul Kumar" }, requirement: { id: "J1", code: "REQ-000001", title: "Java Developer" },
  company: { id: "CO1", name: "Acme Technologies" }, vendor: null, recruiter: null, po_owner: null, source: null, package: null,
  joining: { expected_joining_date: null, actual_joining_date: "2026-10-01" }, candidate_confirmation: null, client_confirmation: null,
  commercials: null, satisfaction, permissions: { can_edit: false, can_change_owner: false, can_invoice: false },
});

describe("PlacementDetail satisfaction", () => {
  it("shows not-yet-due, answered and not-sent surveys", async () => {
    render(<PlacementDetail initial={placement({ client: null, candidate: null })} />);
    const client = screen.getByRole("region", { name: "Client survey" });
    expect(within(client).getByText("Sent 30 days after joining.")).toBeInTheDocument();
    cleanup();
    render(<PlacementDetail initial={placement({
      client: survey({ status: "responded", status_label: "Responded", responded_at: "2026-11-05T04:00:00Z", rating: 5, comment: "Great hire" }),
      candidate: survey({ status: "skipped", status_label: "Not sent", sent_at: null, skip_reason: "no_email", skip_reason_label: "The candidate has no email address" }),
    })} />);
    await waitFor(() => expect(screen.getByText("5 / 5")).toBeInTheDocument());
    expect(screen.getByText("Great hire")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Candidate survey" })).getByText("The candidate has no email address")).toBeInTheDocument();
  });

  it("is hidden when the API sends no satisfaction block", () => {
    render(<PlacementDetail initial={placement(undefined)} />);
    expect(screen.queryByRole("heading", { name: "Satisfaction" })).toBeNull();
  });
});
