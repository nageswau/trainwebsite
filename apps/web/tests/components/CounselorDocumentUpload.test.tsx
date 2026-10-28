import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorDocumentUpload from "@/components/CounselorDocumentUpload";
import DocumentDownloadPanel from "@/components/DocumentDownloadPanel";

// ccrm-045 (DEC-SCOPE-316): the 360 Documents tab's upload form, and the student's Offer Letters download card.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh, push: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
type Fetch = (url: string, init?: RequestInit) => ReturnType<typeof json>;
const APPS = [{ id: "a1", label: "APP-000001 · Oxford" }];
const pdf = () => new File(["%PDF-1.4"], "passport.pdf", { type: "application/pdf" });

function choose(file: File) {
  fireEvent.change(screen.getByLabelText("File"), { target: { files: [file] } });
}

describe("CounselorDocumentUpload", () => {
  it("uploads a document without an application, then refreshes the list and resets the form", async () => {
    const fetchMock = vi.fn<Fetch>(() => json({ document: { id: "d1", name: "passport.pdf" } }, true, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorDocumentUpload studentId="s 1" applications={APPS} />);
    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "Passport" } });
    choose(pdf());
    fireEvent.submit(screen.getByRole("form", { name: "Upload a document" }));
    expect(await screen.findByText("Uploaded. The student can see it in their Documents.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/counselor/students/s%201/documents");
    expect(init?.method).toBe("POST");
    const body = init?.body as FormData;
    expect(body.get("document_type")).toBe("Passport");
    expect(body.get("application_id")).toBeNull();
    expect((body.get("file") as File).name).toBe("passport.pdf");
    expect(refresh).toHaveBeenCalled();
    expect((screen.getByLabelText("File") as HTMLInputElement).value).toBe("");
  });

  it("sends the name for Other and the application, and offers Offer letter only with an application", async () => {
    const fetchMock = vi.fn<Fetch>(() => json({ document: { id: "d1" } }, true, 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorDocumentUpload studentId="s1" applications={APPS} />);
    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "Offer letter" } });
    const application = screen.getByLabelText("Application") as HTMLSelectElement;
    expect(application.required).toBe(true);
    expect(screen.queryByRole("option", { name: "Not tied to an application" })).toBeNull();
    fireEvent.change(application, { target: { value: "a1" } });
    choose(pdf());
    fireEvent.submit(screen.getByRole("form", { name: "Upload a document" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const body = fetchMock.mock.calls[0][1]?.body as FormData;
    expect(body.get("document_type")).toBe("Offer letter");
    expect(body.get("application_id")).toBe("a1");

    fireEvent.change(screen.getByLabelText("Document type"), { target: { value: "Other" } });
    expect(screen.getByLabelText("Name")).toBeRequired();
  });

  it("hides Offer letter when the reader has no open application", () => {
    render(<CounselorDocumentUpload studentId="s1" applications={[]} />);
    expect(screen.queryByRole("option", { name: "Offer letter" })).toBeNull();
    expect(screen.queryByLabelText("Application")).toBeNull();
  });

  it("shows the server's refusal, keeps the entry and allows one upload at a time", async () => {
    type Reply = Awaited<ReturnType<typeof json>>;
    let release: (v: Reply) => void = () => undefined;
    const fetchMock = vi.fn<Fetch>(() => new Promise<Reply>((resolve) => (release = resolve)));
    vi.stubGlobal("fetch", fetchMock);
    render(<CounselorDocumentUpload studentId="s1" applications={APPS} />);
    choose(pdf());
    const form = screen.getByRole("form", { name: "Upload a document" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Uploading…" })).toBeDisabled();
    release({ ok: false, status: 415, json: async () => ({ detail: "Upload a PDF, JPEG or PNG file" }) });
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload a PDF, JPEG or PNG file");
    expect(refresh).not.toHaveBeenCalled();
    expect((screen.getByLabelText("File") as HTMLInputElement).files?.[0]?.name).toBe("passport.pdf");
  });
});

describe("DocumentDownloadPanel filtered to offer letters", () => {
  it("lists only the given type under its own title and empty text", async () => {
    vi.stubGlobal("fetch", vi.fn<Fetch>(() => json({ rows: [{ id: "d1", type: "Passport", status: "Pending review", notes: null }, { id: "d2", type: "Offer letter", status: "Pending review", notes: null }] })));
    render(<DocumentDownloadPanel type="Offer letter" title="Your offer letters" empty="No offer letter has been uploaded yet." />);
    expect(await screen.findByRole("heading", { name: "Your offer letters" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Offer letter" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Passport" })).toBeNull();
    cleanup();
    vi.stubGlobal("fetch", vi.fn<Fetch>(() => json({ rows: [{ id: "d1", type: "Passport", status: "Pending review", notes: null }] })));
    render(<DocumentDownloadPanel type="Offer letter" title="Your offer letters" empty="No offer letter has been uploaded yet." />);
    expect(await screen.findByText("No offer letter has been uploaded yet.")).toBeInTheDocument();
  });
});
