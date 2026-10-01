import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorDocumentReviewPanel from "@/components/CounselorDocumentReviewPanel";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const rows = [
  { id: "d1", student: "Asha Rao", document: "Passport", status: "pending" },
  { id: "d2", student: "Ravi Iyer", document: "Transcript", status: "verified" },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

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

  it("uses the given empty text", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: [] })));
    render(<CounselorDocumentReviewPanel emptyText="No documents have been uploaded for your agency's applications yet." />);
    expect(await screen.findByText("No documents have been uploaded for your agency's applications yet.")).toBeInTheDocument();
  });
});
