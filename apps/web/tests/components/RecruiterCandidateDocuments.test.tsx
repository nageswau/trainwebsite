import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateDocuments from "@/components/RecruiterCandidateDocuments";

afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const ok = (body: object, status = 200) => new Response(JSON.stringify(body), { status });
const fail = (status: number, detail: string) => new Response(JSON.stringify({ detail }), { status });
const URL = "/api/v1/recruiter/candidates/c1/documents";
const pending = {
  id: "r1", document_type: "education", note: "Degree certificate", due_date: "2026-11-20", status: "pending", created_at: "2026-11-04T05:00:00Z",
  received_at: null, cancelled_at: null, document_id: null, requested_by: { id: "u1", full_name: "Riya Recruiter" },
};
const cert = {
  id: "d1", document_type: "certificate", title: "AWS Cloud Practitioner", file_name: "aws.png", content_type: "image/png", size_bytes: 2048,
  preview_status: null, request_id: null, uploaded_by: { id: "u1", full_name: "Riya Recruiter" }, created_at: "2026-11-04T06:00:00Z",
};
const empty = { documents: [], requests: [] };

describe("RecruiterCandidateDocuments (hrc-015)", () => {
  it("loads, then shows empty states", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(empty));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    expect(screen.getByText("Loading documents…")).toBeInTheDocument();
    expect(await screen.findByText("No documents requested yet.")).toBeInTheDocument();
    expect(screen.getByText("No documents uploaded yet.")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[0][0]).toBe(URL);
  });

  it("lists requests with their status and documents with preview and download", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ documents: [cert], requests: [pending] }));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    const requests = await screen.findByRole("list", { name: "Requested documents" });
    expect(within(requests).getByText("Education (degree or marksheet)")).toBeInTheDocument();
    expect(within(requests).getByText("Pending")).toBeInTheDocument();
    expect(within(requests).getByText("Degree certificate")).toBeInTheDocument();
    const documents = screen.getByRole("list", { name: "Uploaded documents" });
    expect(within(documents).getByText(/AWS Cloud Practitioner/)).toBeInTheDocument();
    expect(within(documents).getByRole("button", { name: "Preview AWS Cloud Practitioner" })).toBeInTheDocument();
    expect(within(documents).getByRole("button", { name: "Download AWS Cloud Practitioner" })).toBeInTheDocument();
  });

  it("requests a document and shows it pending", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(empty)).mockResolvedValueOnce(ok(pending, 201)).mockResolvedValueOnce(ok({ documents: [], requests: [pending] }));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    await screen.findByText("No documents requested yet.");
    fireEvent.change(screen.getByLabelText("Document to request"), { target: { value: "education" } });
    fireEvent.change(screen.getByLabelText("Note for the candidate (optional)"), { target: { value: "Degree certificate" } });
    fireEvent.click(screen.getByRole("button", { name: "Request document" }));
    expect(await screen.findByText("Document requested.")).toBeInTheDocument();
    const [url, init] = vi.mocked(global.fetch).mock.calls[1];
    expect(url).toBe("/api/v1/recruiter/candidates/c1/document-requests");
    expect(JSON.parse(String(init?.body))).toEqual({ document_type: "education", note: "Degree certificate", due_date: null });
    expect(await screen.findByText("Pending")).toBeInTheDocument();
  });

  it("shows the API's refusal of a duplicate request", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok(empty)).mockResolvedValueOnce(fail(409, "A request for this document type is already pending"));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    await screen.findByText("No documents requested yet.");
    fireEvent.change(screen.getByLabelText("Document to request"), { target: { value: "education" } });
    fireEvent.click(screen.getByRole("button", { name: "Request document" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("A request for this document type is already pending");
  });

  it("uploads a document against a pending request", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok({ documents: [], requests: [pending] })).mockResolvedValueOnce(ok(cert, 201))
      .mockResolvedValueOnce(ok({ documents: [cert], requests: [{ ...pending, status: "received", document_id: "d1" }] }));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    await screen.findByText("Pending");
    fireEvent.change(screen.getByLabelText("Fulfils request (optional)"), { target: { value: "r1" } });
    expect(screen.getByLabelText("Document type")).toHaveValue("education");
    const file = new File(["%PDF-1.4"], "degree.pdf", { type: "application/pdf" });
    fireEvent.change(screen.getByLabelText("File"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByText("Document uploaded.")).toBeInTheDocument();
    const [url, init] = vi.mocked(global.fetch).mock.calls[1];
    expect(url).toBe(URL);
    const form = init?.body as FormData;
    expect(form.get("document_type")).toBe("education");
    expect(form.get("request_id")).toBe("r1");
    expect(await screen.findByText("Received")).toBeInTheDocument();
  });

  it("asks for a file and a title for Other before sending", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok(empty));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    await screen.findByText("No documents uploaded yet.");
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose a file first.");
    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "other" } });
    fireEvent.change(screen.getByLabelText("File"), { target: { files: [new File(["x"], "x.pdf")] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Give the document a title.");
    expect(vi.mocked(global.fetch)).toHaveBeenCalledTimes(1);
  });

  it("cancels a pending request", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(ok({ documents: [], requests: [pending] })).mockResolvedValueOnce(ok({ ...pending, status: "cancelled" }))
      .mockResolvedValueOnce(ok({ documents: [], requests: [{ ...pending, status: "cancelled" }] }));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel request for Education (degree or marksheet)" }));
    expect(await screen.findByText("Cancelled")).toBeInTheDocument();
    expect(vi.mocked(global.fetch).mock.calls[1][0]).toBe("/api/v1/recruiter/candidates/c1/document-requests/r1/cancel");
  });

  it("is read only without edit rights", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ documents: [cert], requests: [pending] }));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit={false} />);
    await screen.findByText("Pending");
    expect(screen.queryByRole("button", { name: "Request document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancel request/ })).not.toBeInTheDocument();
  });

  it("offers a retry when the list fails to load", async () => {
    vi.mocked(global.fetch).mockResolvedValueOnce(fail(500, "boom")).mockResolvedValueOnce(ok(empty));
    render(<RecruiterCandidateDocuments candidateId="c1" canEdit />);
    fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No documents uploaded yet.")).toBeInTheDocument();
  });
});
