import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import StudentCandidateDocumentsCard from "@/components/StudentCandidateDocumentsCard";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const ok = (body: object, status = 200) => new Response(JSON.stringify(body), { status });
const URL = "/api/v1/account/candidate-documents";
const pending = {
  id: "r1", document_type: "certificate", note: "Your Python certificate", due_date: null, status: "pending", created_at: "2026-11-04T05:00:00Z",
  received_at: null, cancelled_at: null, document_id: null,
};
const mine = {
  id: "d1", document_type: "certificate", title: null, file_name: "python.pdf", content_type: "application/pdf", size_bytes: 1024,
  preview_status: null, request_id: "r1", uploaded_by: "you", created_at: "2026-11-04T06:00:00Z",
};

describe("StudentCandidateDocumentsCard (hrc-015)", () => {
  it("asks a student outside the pool to join first", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ available: false, requests: [], documents: [] }));
    render(<StudentCandidateDocumentsCard />);
    expect(screen.getByText("Loading your documents…")).toBeInTheDocument();
    expect(await screen.findByText("Join the placement candidate pool to share documents with the placement team.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toBe(URL);
  });

  it("shows a pending request, uploads against it and then shows it received", async () => {
    vi.mocked(global.fetch)
      .mockResolvedValueOnce(ok({ available: true, requests: [pending], documents: [] }))
      .mockResolvedValueOnce(ok(mine, 201))
      .mockResolvedValueOnce(ok({ available: true, requests: [{ ...pending, status: "received", document_id: "d1" }], documents: [mine] }));
    render(<StudentCandidateDocumentsCard />);
    const requests = await screen.findByRole("list", { name: "Documents the placement team asked for" });
    expect(within(requests).getByText("Pending")).toBeInTheDocument();
    expect(within(requests).getByText("Your Python certificate")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Fulfils request (optional)"), { target: { value: "r1" } });
    fireEvent.change(screen.getByLabelText("File"), { target: { files: [new File(["%PDF-1.4"], "python.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByText("Received")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[1][0]).toBe(URL);
    const documents = screen.getByRole("list", { name: "Your documents" });
    expect(within(documents).getByText(/Uploaded by you/)).toBeInTheDocument();
    expect(within(documents).getByRole("button", { name: "Download Certificate" })).toBeInTheDocument();
  });

  it("shows an empty state when nothing is requested or uploaded", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ available: true, requests: [], documents: [] }));
    render(<StudentCandidateDocumentsCard />);
    expect(await screen.findByText("Nothing has been requested from you.")).toBeInTheDocument();
    expect(screen.getByText("You haven't uploaded any documents yet.")).toBeInTheDocument();
  });

  it("offers a retry when loading fails", async () => {
    vi.mocked(global.fetch).mockRejectedValueOnce(new TypeError("offline")).mockResolvedValueOnce(ok({ available: true, requests: [], documents: [] }));
    render(<StudentCandidateDocumentsCard />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Nothing has been requested from you.")).toBeInTheDocument();
  });
});
