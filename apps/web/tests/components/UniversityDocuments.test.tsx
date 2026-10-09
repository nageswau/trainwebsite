import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityDocuments from "@/components/UniversityDocuments";
import { DOCUMENT_KINDS, type UniversityDocument } from "@/lib/universityDocuments";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const person = { id: "p1", full_name: "Rahul Mehta", active: true };
const version = (n: number) => ({ version: n, file_name: `fees-v${n}.pdf`, content_type: "application/pdf", size_bytes: 2048 * n, uploaded_by: person, uploaded_at: "2026-10-09T05:00:00Z" });
const doc = (over: Partial<UniversityDocument> = {}): UniversityDocument => ({
  id: "d1", university: { id: "u1", name: "ABC", university_code: "UNV-000001" }, kind: "fee_structure", title: "Fee structure 2026",
  shareable: true, current_version: 2, versions: [version(2), version(1)], created_at: "", updated_at: "", ...over,
});
const pdf = (size = 10) => new File([new Uint8Array(size)], "fees.pdf", { type: "application/pdf" });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("UniversityDocuments (upc-026)", () => {
  it("lists the §28 kinds exactly, in source order", () => {
    expect(Object.values(DOCUMENT_KINDS)).toEqual([
      "MoU", "Partnership agreement", "Commission agreement", "University brochure", "Course list", "Fee structure", "Entry requirements",
      "Scholarship information", "Marketing materials", "Application guidelines", "Contact documents", "Training documents",
    ]);
  });

  it("shows each document with its kind, version, sharing, current file and earlier versions", () => {
    render(<UniversityDocuments universityId="u1" documents={[doc(), doc({ id: "d2", kind: "mou", title: "MoU", shareable: false, current_version: 1, versions: [version(1)] })]} canManage={false} />);
    const [first, second] = screen.getAllByRole("listitem").filter((li) => li.className === "card");
    expect(within(first).getByText("Fee structure")).toBeInTheDocument();
    expect(within(first).getByText("Version 2")).toBeInTheDocument();
    expect(within(first).getByText("Shareable")).toBeInTheDocument();
    expect(within(first).getByText(/fees-v2\.pdf · 4 KB · uploaded by Rahul Mehta/)).toBeInTheDocument();
    expect(within(first).getByRole("link", { name: "Download Fee structure 2026" })).toHaveAttribute("href", "/api/v1/partnership/universities/u1/documents/d1/file");
    expect(within(first).getByRole("link", { name: "Version 1 of Fee structure 2026" })).toHaveAttribute("href", "/api/v1/partnership/universities/u1/documents/d1/file?version=1");
    expect(within(second).getByText("Internal")).toBeInTheDocument();
    expect(within(second).queryByText(/Earlier versions/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload document" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /New version/ })).not.toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<UniversityDocuments universityId="u1" documents={[]} canManage />);
    expect(screen.getByText("No documents uploaded yet.")).toBeInTheDocument();
  });

  it("uploads with the kind's sharing default, then refreshes", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ document: doc() }, 201)));
    vi.stubGlobal("fetch", mock);
    render(<UniversityDocuments universityId="u1" documents={[]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "fee_structure" } });
    expect(screen.getByLabelText("Visible to counsellors (shareable)")).toBeChecked();
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: " Fees 2026 " } });
    fireEvent.change(screen.getByLabelText("File (required)"), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = mock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/partnership/universities/u1/documents");
    const form = init.body as FormData;
    expect([form.get("kind"), form.get("title"), form.get("shareable")]).toEqual(["fee_structure", "Fees 2026", "true"]);
    expect((form.get("file") as File).name).toBe("fees.pdf");
    expect(await screen.findByRole("status")).toHaveTextContent("Document uploaded.");
  });

  it("keeps the commission agreement internal", () => {
    render(<UniversityDocuments universityId="u1" documents={[]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "commission_agreement" } });
    const box = screen.getByLabelText("Visible to counsellors (shareable)");
    expect(box).toBeDisabled();
    expect(box).not.toBeChecked();
    expect(screen.getByText("A commission agreement is always internal.")).toBeInTheDocument();
  });

  it("checks the form and the size before sending anything", () => {
    const mock = vi.fn();
    vi.stubGlobal("fetch", mock);
    render(<UniversityDocuments universityId="u1" documents={[]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the kind of document.");
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "brochure" } });
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Brochure" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a file first.");
    fireEvent.change(screen.getByLabelText("File (required)"), { target: { files: [pdf(20 * 1024 * 1024 + 1)] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The file must be at most 20 MB.");
    expect(mock).not.toHaveBeenCalled();
  });

  it("shows the API's refusal (e.g. an executable) and keeps the form open", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Upload a PDF, Word, Excel, PowerPoint, JPEG or PNG file" }, 422))));
    render(<UniversityDocuments universityId="u1" documents={[]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "brochure" } });
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Brochure" } });
    fireEvent.change(screen.getByLabelText("File (required)"), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload document" }));
    expect(await screen.findByText("Upload a PDF, Word, Excel, PowerPoint, JPEG or PNG file")).toHaveAttribute("role", "alert");
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Brochure");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("a server error without a detail gets a plain sentence", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response("oops", { status: 500 }))));
    render(<UniversityDocuments universityId="u1" documents={[doc()]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Fee structure 2026" }));
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Fees" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByText("The change could not be saved. Try again.")).toBeInTheDocument();
  });

  it("uploads a new version of a document", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ document: doc({ current_version: 3 }) }, 201)));
    vi.stubGlobal("fetch", mock);
    render(<UniversityDocuments universityId="u1" documents={[doc()]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "New version of Fee structure 2026" }));
    fireEvent.change(screen.getByLabelText("New file (saves version 3)"), { target: { files: [pdf()] } });
    fireEvent.click(screen.getByRole("button", { name: "Upload version" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock.mock.calls[0]).toEqual(["/api/v1/partnership/universities/u1/documents/d1/versions", expect.objectContaining({ method: "POST" })]);
    expect(await screen.findByRole("status")).toHaveTextContent("Version 3 uploaded.");
  });

  it("edits only what changed", async () => {
    const mock = vi.fn(() => Promise.resolve(res({ document: doc() })));
    vi.stubGlobal("fetch", mock);
    render(<UniversityDocuments universityId="u1" documents={[doc()]} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Edit Fee structure 2026" }));
    fireEvent.click(screen.getByLabelText("Visible to counsellors (shareable)"));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = mock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/partnership/universities/u1/documents/d1");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({ shareable: false });
  });
});
