import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorDocumentReviewPanel from "@/components/CounselorDocumentReviewPanel";

const { refresh } = vi.hoisted(() => ({ refresh: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const rows = [
  { id: "d1", student: "Asha Rao", document: "Passport", status: "pending" },
  { id: "d2", student: "Ravi Iyer", document: "Transcript", status: "verified" },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockClear();
});

const card = (name: string) => screen.getByText(name).closest(".card") as HTMLElement;

describe("CounselorDocumentReviewPanel -- counselor defaults (unchanged by AGN-003)", () => {
  it("loads the counselor queue and offers all three decisions", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ id: "d1", verification_status: "rejected" })).mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel />);
    expect(mock).toHaveBeenCalledWith("/api/v1/portal/overseas/counselor/documents");
    fireEvent.click((await screen.findAllByRole("button", { name: "Review" }))[1]); // decided rows stay reviewable for counselors
    const select = screen.getByLabelText("Decision") as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(["verified", "rejected", "changes_required"]);
    fireEvent.change(select, { target: { value: "rejected" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText("Document reviewed -- the student has been notified.")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe("/api/v1/workflows/overseas/documents/d2/verify");
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ verification_status: "rejected", notes: null });
  });

  it("says when nothing is waiting", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: [] })));
    render(<CounselorDocumentReviewPanel />);
    expect(await screen.findByText("No documents are awaiting your review yet.")).toBeInTheDocument();
  });
});

describe("CounselorDocumentReviewPanel -- AGN-003 options", () => {
  it("shows a load error with Try again instead of an empty queue", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ detail: "boom" }, 500)).mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load documents.");
    expect(screen.queryByText("No documents are awaiting your review yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Passport")).toBeInTheDocument();
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("announces loading", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));
    render(<CounselorDocumentReviewPanel />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your review queue…");
  });

  it("with pendingOnly offers Review on pending rows only, from the given queue", async () => {
    const mock = vi.fn().mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel queueUrl="/api/v1/portal/overseas/agent/documents" pendingOnly />);
    expect(await screen.findAllByRole("button", { name: "Review" })).toHaveLength(1);
    expect(mock).toHaveBeenCalledWith("/api/v1/portal/overseas/agent/documents");
  });

  it("with one decision shows a single Mark verified button, no select", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ id: "d1", verification_status: "verified" })).mockResolvedValue(json({ rows }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel pendingOnly decisions={["verified"]} />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    expect(screen.queryByLabelText("Decision")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Mark verified" }));
    await waitFor(() => expect(mock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ verification_status: "verified", notes: null });
  });

  it("shows the server's refusal on the row and keeps the form open", async () => {
    const refusal = "Only an agency Master can reject documents or request changes";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ detail: refusal }, 403)));
    render(<CounselorDocumentReviewPanel pendingOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText(refusal)).toBeInTheDocument();
    expect(screen.getByLabelText("Decision")).toBeInTheDocument();
  });

  // AGN-003 browser QA (2026-10-01).
  it("QA-01: a dropped connection on submit says so and frees the button", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ rows })).mockRejectedValueOnce(new TypeError("Failed to fetch")));
    render(<CounselorDocumentReviewPanel pendingOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText("The request did not complete. Check your connection and try again; your entry is kept.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Submit review" })).toBeEnabled();
  });

  it("QA-02: a dropped connection on View document says so and frees the button", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ rows })).mockRejectedValueOnce(new TypeError("Failed to fetch")));
    render(<CounselorDocumentReviewPanel />);
    fireEvent.click(within(await screen.findByText("Passport").then(() => card("Passport"))).getByRole("button", { name: "View document" }));
    expect(await screen.findByText("Couldn't reach the server. Check your connection and try again.")).toBeInTheDocument();
    expect(within(card("Passport")).getByRole("button", { name: "View document" })).toBeEnabled();
  });

  it("QA-03: a document someone else already decided refreshes the queue and closes the form", async () => {
    const decided = [{ ...rows[0], status: "rejected" }, rows[1]];
    const mock = vi.fn()
      .mockResolvedValueOnce(json({ rows }))
      .mockResolvedValueOnce(json({ detail: "This document has already been reviewed" }, 409))
      .mockResolvedValue(json({ rows: decided }));
    vi.stubGlobal("fetch", mock);
    render(<CounselorDocumentReviewPanel pendingOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText("This document has already been reviewed")).toBeInTheDocument();
    await waitFor(() => expect(within(card("Passport")).getByText("Rejected")).toBeInTheDocument());
    expect(screen.queryByLabelText("Decision")).toBeNull();
    expect(screen.queryByRole("button", { name: "Review" })).toBeNull();
    expect(refresh).toHaveBeenCalled();
  });

  it("QA-04: a server error is worded for people, not shown raw", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ rows })).mockResolvedValueOnce(json({ detail: "Internal Server Error" }, 500)));
    render(<CounselorDocumentReviewPanel pendingOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByText("The server couldn't complete this. Please try again in a moment.")).toBeInTheDocument();
    expect(screen.queryByText("Internal Server Error")).toBeNull();
  });

  it("QA-05: statuses read as words", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: [{ id: "d3", student: "S", document: "IELTS", status: "changes_required" }, ...rows] })));
    render(<CounselorDocumentReviewPanel />);
    expect(await screen.findByText("Changes required")).toBeInTheDocument();
    expect(within(card("Passport")).getByText("Pending")).toBeInTheDocument();
    expect(screen.queryByText("changes_required")).toBeNull();
  });

  it("QA-06: submitting leaves View document alone", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(json({ rows })).mockReturnValueOnce(new Promise(() => {})));
    render(<CounselorDocumentReviewPanel pendingOnly />);
    fireEvent.click(await screen.findByRole("button", { name: "Review" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit review" }));
    expect(await screen.findByRole("button", { name: "Submitting…" })).toBeDisabled();
    expect(within(card("Passport")).getByRole("button", { name: "View document" })).toBeEnabled();
  });

  it("QA-08: View document and Review sit together in one wrapping row", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows })));
    render(<CounselorDocumentReviewPanel />);
    await screen.findByText("Passport");
    const view = within(card("Passport")).getByRole("button", { name: "View document" });
    const review = within(card("Passport")).getByRole("button", { name: "Review" });
    expect(view.parentElement).toBe(review.parentElement);
    expect(view.parentElement).toHaveStyle({ display: "flex", flexWrap: "wrap" });
    expect(review).not.toHaveStyle({ marginLeft: "8px" });
  });

  it("uses the given empty text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: [] })));
    render(<CounselorDocumentReviewPanel emptyText="No documents have been uploaded for your agency's applications yet." />);
    expect(await screen.findByText("No documents have been uploaded for your agency's applications yet.")).toBeInTheDocument();
  });
});
